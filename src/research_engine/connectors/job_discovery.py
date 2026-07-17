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
from research_engine.connectors.web import fetch_page
from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.targets import ResearchTarget, match_role_family, match_role_title


JsonFetcher = Callable[[str], Any]
TextFetcher = Callable[[str], str]
HtmlFetcher = Callable[[str], str]


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
        self.text_fetcher = text_fetcher or fetch_page
        self.html_fetcher = html_fetcher or fetch_html

    def collect(self, request: CollectionRequest) -> CollectionResult:
        target = ResearchTarget.from_mapping(dict(request.source.get("target") or {}))
        registered = find_company(target.company)
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        telemetry = {
            "endpoint_attempts": 0,
            "endpoint_successes": 0,
            "endpoint_failures": 0,
        }

        for provider, url in ats_endpoints(
            target.company,
            registered=list((registered or {}).get("ats") or []),
        ):
            if len(rows) >= request.max_results:
                break
            telemetry["endpoint_attempts"] += 1
            try:
                payload = self.json_fetcher(url)
            except Exception as exc:
                telemetry["endpoint_failures"] += 1
                warnings.append(
                    f"official ATS {provider} fetch failed: {type(exc).__name__}"
                )
                continue
            telemetry["endpoint_successes"] += 1
            parsed = parse_ats(provider, payload, company=target.company)
            for candidate in parsed:
                if candidate_maybe_matches(candidate, target=target):
                    rows.append(self._verify_candidate(candidate, provider=provider, warnings=warnings))
                if len(rows) >= request.max_results:
                    break

        remaining = max(0, request.max_results - len(rows))
        if remaining and registered and registered.get("careers_search_url"):
            rows.extend(
                self._discover_custom_site(
                    registered,
                    target=target,
                    warnings=warnings,
                    max_results=remaining,
                    telemetry=telemetry,
                )
            )

        normalized_rows = dedupe_rows(rows)[: request.max_results]
        for row in normalized_rows:
            row.setdefault("source_id", request.source_id)
            row.setdefault("query_id", str(request.source.get("query_id") or ""))
            row.setdefault("facet_id", str(request.source.get("facet_id") or ""))
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=normalized_rows,
            warnings=warnings,
            metadata={
                "target_key": target.target_key,
                "registered_company": bool(registered),
                "authority": "official_urls_refetched",
                "status": (
                    "ready" if telemetry["endpoint_successes"] else "failed"
                ),
                "official_source_retrieved": bool(telemetry["endpoint_successes"]),
                **telemetry,
            },
        )

    def _verify_candidate(
        self,
        candidate: dict[str, Any],
        *,
        provider: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        url = str(candidate.get("url") or "")
        fetched = ""
        try:
            fetched_value = self.text_fetcher(url) if url else ""
            if isinstance(fetched_value, tuple):
                fetched = str(fetched_value[0] or "")
                final_url = str(fetched_value[1] or "")
            else:
                fetched = str(fetched_value or "")
                final_url = url if fetched.strip() else ""
        except Exception as exc:
            warnings.append(f"official final URL fetch failed for {url}: {type(exc).__name__}")
            final_url = ""
        api_text = str(candidate.get("text") or "")
        text = fetched.strip() or api_text.strip()
        return {
            **candidate,
            "connector": self.connector_id,
            "final_url": final_url,
            "text": text,
            "captured_at": utc_now(),
            "source_confidence": "high",
            "access_mode": f"official_{provider}_api_and_final_url",
            "discovered_via": f"official_{provider}_api",
            "is_final_page": bool(fetched.strip() and final_url),
        }

    def _discover_custom_site(
        self,
        company: dict[str, Any],
        *,
        target: ResearchTarget,
        warnings: list[str],
        max_results: int,
        telemetry: dict[str, int],
    ) -> list[dict[str, Any]]:
        template = str(company.get("careers_search_url") or "")
        query = " ".join(value for value in (target.role_title, target.level, target.team) if value)
        search_url = template.format(
            query=quote_plus(query),
            location=quote_plus(target.geography),
        )
        telemetry["endpoint_attempts"] += 1
        try:
            html = self.html_fetcher(search_url)
        except Exception as exc:
            telemetry["endpoint_failures"] += 1
            warnings.append(
                f"official careers search fetch failed for {company.get('company_key')}: {type(exc).__name__}"
            )
            return []
        telemetry["endpoint_successes"] += 1
        rows: list[dict[str, Any]] = [
            {
                "company": target.company,
                "connector": self.connector_id,
                "title": f"{target.company} careers search",
                "url": search_url,
                "final_url": "",
                "text": strip_html(html)[:4000],
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
                rows.append(self._verify_candidate(candidate, provider="custom_site", warnings=warnings))
            if len(rows) >= max_results:
                break
        return rows


def ats_endpoints(company: str, *, registered: list[dict[str, Any]]) -> list[tuple[str, str]]:
    slug = company_slug(company)
    provider_tokens: list[tuple[str, str]] = []
    for row in registered:
        provider = str(row.get("provider") or "").lower()
        token = str(row.get("board_token") or slug)
        if provider in {"greenhouse", "ashby", "lever"} and token:
            provider_tokens.append((provider, token))
    for provider in ("greenhouse", "ashby", "lever"):
        if not any(item[0] == provider for item in provider_tokens):
            provider_tokens.append((provider, slug))
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
    text = " ".join(
        (str(candidate.get("title") or ""), str(candidate.get("location") or ""))
    ).lower()
    return not (
        match_role_title(target.role_title, text) == "mismatch"
        and match_role_family(target.role_family, text) == "mismatch"
    )


def fetch_json(url: str, *, timeout: float = 8.0) -> Any:
    request = Request(url, headers={"User-Agent": "research-engine/0.2", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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
