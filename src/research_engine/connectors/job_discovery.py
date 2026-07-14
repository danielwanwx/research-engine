"""Official ATS and company-careers discovery for structured hiring targets."""

from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any, Callable
from urllib.parse import quote_plus, urljoin, urlsplit
from urllib.request import Request, urlopen

from research_engine.company_matrix import find_company
from research_engine.connectors.web import fetch_page_with_status, page_body_status
from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.targets import (
    ResearchTarget,
    match_geography,
    match_role_family,
    match_role_title,
)


JsonFetcher = Callable[[str], Any]
TextFetcher = Callable[[str], str]
HtmlFetcher = Callable[[str], str]

MAX_ATS_CANDIDATES = 4
MAX_JSON_BYTES = 8_000_000
MIN_CANONICAL_API_TEXT = 80
ATS_PROVIDERS = {"greenhouse", "ashby", "lever"}
OFFICIAL_JOB_API_PROVIDERS = {"amazon_jobs"}


class OfficialJobDiscoveryConnector:
    connector_id = "official_job_discovery"

    def __init__(
        self,
        *,
        json_fetcher: JsonFetcher | None = None,
        text_fetcher: TextFetcher | None = None,
        html_fetcher: HtmlFetcher | None = None,
    ) -> None:
        self.json_fetcher = json_fetcher or fetch_json
        self.text_fetcher = text_fetcher or fetch_page_with_status
        self.html_fetcher = html_fetcher or fetch_html

    def collect(self, request: CollectionRequest) -> CollectionResult:
        target = ResearchTarget.from_mapping(dict(request.source.get("target") or {}))
        registered = find_company(target.company)
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        ranked_candidates: list[tuple[int, str, dict[str, Any], bool]] = []
        configured_ats = bool(registered and registered.get("ats"))

        for provider, url in ats_endpoints(
            target.company,
            registered=list((registered or {}).get("ats") or []),
            registered_company=bool(registered),
        ):
            try:
                payload = self.json_fetcher(url)
            except Exception:
                continue
            parsed = parse_ats(provider, payload, company=target.company)
            ownership_verified = configured_ats or dynamic_board_ownership_verified(
                provider,
                company=target.company,
                candidates=parsed,
            )
            if not ownership_verified:
                continue
            for candidate in parsed:
                score = candidate_match_score(candidate, target=target)
                if score >= 0:
                    ranked_candidates.append(
                        (score, provider, candidate, ownership_verified)
                    )

        verification_cap = min(MAX_ATS_CANDIDATES, max(1, request.max_results))
        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        for _score, provider, candidate, ownership_verified in ranked_candidates[
            :verification_cap
        ]:
            verified = self._verify_candidate(
                candidate,
                provider=provider,
                warnings=warnings,
                ats_ownership_verified=ownership_verified,
            )
            if verified is not None:
                rows.append(verified)

        if registered and registered.get("careers_search_url"):
            rows.extend(self._discover_custom_site(registered, target=target, warnings=warnings))

        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=dedupe_rows(rows)[: request.max_results],
            warnings=warnings,
            metadata={
                "target_key": target.target_key,
                "registered_company": bool(registered),
                "authority": "official_urls_refetched",
            },
        )

    def _verify_candidate(
        self,
        candidate: dict[str, Any],
        *,
        provider: str,
        warnings: list[str],
        ats_ownership_verified: bool,
    ) -> dict[str, Any] | None:
        url = str(candidate.get("url") or "")
        fetched = ""
        final_url = ""
        fetched_status = "empty"
        try:
            fetched_value = self.text_fetcher(url) if url else ""
            if isinstance(fetched_value, tuple):
                fetched = str(fetched_value[0] or "")
                final_url = str(fetched_value[1] or "")
                if len(fetched_value) >= 3:
                    fetched_status = str(fetched_value[2] or "empty")
            else:
                fetched = str(fetched_value or "")
                final_url = url if fetched.strip() else ""
        except Exception as exc:
            warnings.append(f"official final URL fetch failed for {url}: {type(exc).__name__}")
            final_url = ""
        api_text = str(candidate.get("text") or "")
        if fetched_status == "empty" and fetched:
            fetched_status = page_body_status(fetched)
        fetched_usable = fetched_status == "usable" and bool(final_url)
        api_usable = (
            page_body_status(api_text) == "usable"
            and len(api_text.strip()) >= MIN_CANONICAL_API_TEXT
        )
        api_canonical = (
            not fetched_usable
            and fetched_status != "not_found_or_closed"
            and provider in ATS_PROVIDERS | OFFICIAL_JOB_API_PROVIDERS
            and ats_ownership_verified
            and api_usable
            and str(candidate.get("current_status") or "") == "active"
        )
        if not fetched_usable and not api_canonical:
            return None

        if fetched_usable:
            text = fetched.strip()
            if api_usable and api_text.strip() not in text:
                text = f"{text}\n\n{api_text.strip()}"
            canonical_kind = "verified_final_url"
            access_mode = f"official_{provider}_api_and_final_url"
        else:
            text = api_text.strip()
            final_url = url
            canonical_kind = "official_ats_api_record"
            access_mode = f"official_{provider}_api_record"
        return {
            **candidate,
            "connector": self.connector_id,
            "final_url": final_url,
            "text": text,
            "captured_at": utc_now(),
            "source_confidence": "high",
            "access_mode": access_mode,
            "discovered_via": f"official_{provider}_api",
            "is_final_page": True,
            "ats_ownership_verified": ats_ownership_verified,
            "canonical_record_kind": canonical_kind,
            "human_page_status": fetched_status,
            "access_blocked": False,
        }

    def _discover_custom_site(
        self,
        company: dict[str, Any],
        *,
        target: ResearchTarget,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        template = str(company.get("careers_search_url") or "")
        query = " ".join(value for value in (target.role_title, target.level, target.team) if value)
        search_url = template.format(
            query=quote_plus(query),
            location=quote_plus(target.geography),
        )
        rows: list[dict[str, Any]] = [
            {
                "company": target.company,
                "connector": self.connector_id,
                "title": f"{target.company} careers search",
                "url": search_url,
                "final_url": "",
                "text": "",
                "source_kind": "official_careers_search",
                "source_class": "discovery_only",
                "current_status": "unknown",
                "captured_at": utc_now(),
                "source_confidence": "high",
                "access_mode": "official_company_search_page",
                "discovered_via": "official_company_search",
                "is_final_page": False,
            }
        ]
        api_template = str(company.get("careers_api_url") or "")
        api_provider = str(company.get("careers_api_provider") or "")
        if api_template and api_provider:
            api_url = api_template.format(
                query=quote_plus(query),
                location=quote_plus(target.geography),
            )
            try:
                payload = self.json_fetcher(api_url)
            except Exception as exc:
                warnings.append(
                    f"official careers API fetch failed for {company.get('company_key')}: "
                    f"{type(exc).__name__}"
                )
                return rows
            candidates = (
                parse_amazon_jobs(payload, company=target.company)
                if api_provider == "amazon_jobs"
                else []
            )
            ranked = sorted(
                (
                    (candidate_match_score(candidate, target=target), candidate)
                    for candidate in candidates
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            for score, candidate in ranked[:MAX_ATS_CANDIDATES]:
                if score < 0:
                    continue
                verified = self._verify_candidate(
                    candidate,
                    provider=api_provider,
                    warnings=warnings,
                    ats_ownership_verified=True,
                )
                if verified is not None:
                    verified["official_api_ownership_verified"] = True
                    rows.append(verified)
            return rows
        try:
            html = self.html_fetcher(search_url)
        except Exception as exc:
            warnings.append(
                f"official careers search fetch failed for {company.get('company_key')}: {type(exc).__name__}"
            )
            return []
        rows[0]["text"] = strip_html(html)[:4000]
        allowed_domains = set(company.get("official_domains") or [])
        for title, url in extract_job_links(html, base_url=search_url, allowed_domains=allowed_domains):
            candidate = {
                "company": target.company,
                "title": title,
                "url": url,
                "location": target.geography,
                "published_at": "",
                "text": "",
                "source_kind": "official_job_posting",
                "current_status": "active",
                "ats_provider": "custom_site",
            }
            if candidate_maybe_matches(candidate, target=target):
                verified = self._verify_candidate(
                    candidate,
                    provider="custom_site",
                    warnings=warnings,
                    ats_ownership_verified=False,
                )
                if verified is not None:
                    rows.append(verified)
        return rows


def ats_endpoints(
    company: str,
    *,
    registered: list[dict[str, Any]],
    registered_company: bool = False,
) -> list[tuple[str, str]]:
    slug = company_slug(company)
    provider_tokens: list[tuple[str, str]] = []
    for row in registered:
        provider = str(row.get("provider") or "").lower()
        token = str(row.get("board_token") or slug)
        if provider in ATS_PROVIDERS and token:
            provider_tokens.append((provider, token))
    if not provider_tokens and not registered_company:
        provider_tokens = [(provider, slug) for provider in ("greenhouse", "ashby", "lever")]
    urls = {
        "greenhouse": lambda token: f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
        "ashby": lambda token: f"https://api.ashbyhq.com/posting-api/job-board/{token}",
        "lever": lambda token: f"https://api.lever.co/v0/postings/{token}?mode=json",
    }
    return [(provider, urls[provider](token)) for provider, token in provider_tokens]


def company_slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", company.lower())


def parse_ats(provider: str, payload: Any, *, company: str) -> list[dict[str, Any]]:
    if provider == "greenhouse":
        return parse_greenhouse(payload, company=company)
    if provider == "ashby":
        return parse_ashby(payload, company=company)
    if provider == "lever":
        return parse_lever(payload, company=company)
    return []


def parse_greenhouse(payload: Any, *, company: str) -> list[dict[str, Any]]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else []
    return [
        standard_candidate(
            company=company,
            title=job.get("title"),
            url=job.get("absolute_url"),
            location=(job.get("location") or {}).get("name"),
            published_at=job.get("updated_at"),
            text=job.get("content"),
            provider="greenhouse",
        )
        for job in jobs or []
        if isinstance(job, dict) and job.get("absolute_url")
    ]


def parse_ashby(payload: Any, *, company: str) -> list[dict[str, Any]]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else []
    return [
        standard_candidate(
            company=company,
            title=job.get("title"),
            url=job.get("jobUrl") or job.get("applyUrl"),
            location=job.get("location"),
            published_at=job.get("publishedAt"),
            text=job.get("descriptionHtml") or job.get("descriptionPlain"),
            provider="ashby",
        )
        for job in jobs or []
        if isinstance(job, dict) and job.get("isListed", True) and (job.get("jobUrl") or job.get("applyUrl"))
    ]


def parse_lever(payload: Any, *, company: str) -> list[dict[str, Any]]:
    jobs = payload if isinstance(payload, list) else []
    rows: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict) or not job.get("hostedUrl"):
            continue
        created = job.get("createdAt")
        published = ""
        if isinstance(created, (int, float)):
            published = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
        rows.append(
            standard_candidate(
                company=company,
                title=job.get("text"),
                url=job.get("hostedUrl"),
                location=(job.get("categories") or {}).get("location"),
                published_at=published,
                text=job.get("descriptionPlain") or job.get("description"),
                provider="lever",
            )
        )
    return rows


def parse_amazon_jobs(payload: Any, *, company: str) -> list[dict[str, Any]]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else []
    rows: list[dict[str, Any]] = []
    for job in jobs or []:
        if not isinstance(job, dict) or not job.get("job_path"):
            continue
        text_parts = [
            job.get("description"),
            job.get("basic_qualifications"),
            job.get("preferred_qualifications"),
            job.get("url_next_step"),
        ]
        rows.append(
            standard_candidate(
                company=company,
                title=job.get("title"),
                url=urljoin("https://www.amazon.jobs", str(job.get("job_path"))),
                location=(
                    job.get("normalized_location")
                    or job.get("location")
                    or job.get("country_code")
                ),
                published_at=job.get("posted_date"),
                text=" ".join(str(value or "") for value in text_parts),
                provider="amazon_jobs",
            )
        )
    return rows


def standard_candidate(
    *,
    company: str,
    title: Any,
    url: Any,
    location: Any,
    published_at: Any,
    text: Any,
    provider: str,
) -> dict[str, Any]:
    return {
        "company": company,
        "title": str(title or ""),
        "url": str(url or ""),
        "location": str(location or ""),
        "published_at": str(published_at or ""),
        "text": strip_html(str(text or "")),
        "source_kind": "official_job_posting",
        "current_status": "active",
        "ats_provider": provider,
    }


def candidate_maybe_matches(candidate: dict[str, Any], *, target: ResearchTarget) -> bool:
    return candidate_match_score(candidate, target=target) >= 0


def candidate_match_score(candidate: dict[str, Any], *, target: ResearchTarget) -> int:
    title = normalize_words(candidate.get("title"))
    target_title = normalize_words(target.role_title)
    if not title or not target_title:
        return -1

    target_tokens = target_title.split()
    ignored = {
        "software",
        "development",
        "senior",
        "staff",
        "principal",
        "lead",
        "junior",
        "i",
        "ii",
        "iii",
        "iv",
    }
    role_nouns = {"engineer", "developer", "architect", "scientist", "researcher"}
    distinctive = [token for token in target_tokens if token not in ignored | role_nouns]
    exact_phrase = target_title in title
    distinct_match = bool(distinctive) and all(token in title.split() for token in distinctive)
    noun_match = bool(role_nouns & set(target_tokens) & set(title.split()))
    title_match = match_role_title(target.role_title, title)
    family_match = match_role_family(target.role_family, title)

    if not exact_phrase and not (distinct_match and noun_match):
        return -1
    if title_match == "mismatch" or family_match == "mismatch":
        return -1

    score = 100 if exact_phrase else 80
    level_text = normalize_words(f"{candidate.get('title', '')} {candidate.get('text', '')}")
    if normalize_words(target.level) in level_text:
        score += 10
    location = normalize_words(candidate.get("location"))
    geography_match = match_geography(target.geography, str(candidate.get("location") or ""))
    if geography_match == "mismatch":
        return -1
    if geography_match in {"exact", "compatible"}:
        score += 20
    if normalize_words(target.geography) in location or (
        normalize_words(target.geography) == "us" and "remote us" in location
    ):
        score += 5
    return score


def normalize_words(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def dynamic_board_ownership_verified(
    provider: str,
    *,
    company: str,
    candidates: list[dict[str, Any]],
) -> bool:
    token = company_slug(company)
    expected_hosts = {
        "greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io"},
        "ashby": {"jobs.ashbyhq.com"},
        "lever": {"jobs.lever.co"},
    }.get(provider, set())
    if not token or not expected_hosts:
        return False
    for candidate in candidates:
        parsed = urlsplit(str(candidate.get("url") or ""))
        host = parsed.netloc.lower().removeprefix("www.")
        segments = [company_slug(segment) for segment in parsed.path.split("/") if segment]
        if host in expected_hosts and segments and segments[0] == token:
            return True
    return False


def fetch_json(url: str, *, timeout: float = 8.0) -> Any:
    request = Request(url, headers={"User-Agent": "research-engine/0.2", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_JSON_BYTES + 1)
        if len(body) > MAX_JSON_BYTES:
            raise ValueError(f"ATS JSON response exceeds {MAX_JSON_BYTES} byte limit")
        return json.loads(body.decode("utf-8"))


def fetch_html(url: str, *, timeout: float = 8.0) -> str:
    request = Request(url, headers={"User-Agent": "research-engine/0.2"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = str(dict(attrs).get("href") or "")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((" ".join(self._parts).strip(), self._href))
            self._href = ""
            self._parts = []


def extract_job_links(
    html: str, *, base_url: str, allowed_domains: set[str]
) -> list[tuple[str, str]]:
    parser = _LinkExtractor()
    parser.feed(html)
    links: list[tuple[str, str]] = []
    for title, href in parser.links:
        url = urljoin(base_url, href)
        parsed = urlsplit(url)
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        official = any(host == domain or host.endswith("." + domain) for domain in allowed_domains)
        job_path = any(token in path for token in ("/job/", "/jobs/", "/listing/", "/positions/"))
        if official and job_path and title:
            links.append((strip_html(title), url))
    return links


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique
