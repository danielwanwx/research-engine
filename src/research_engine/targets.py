"""Structured target contracts and deterministic target-evidence gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from research_engine.company_matrix import load_company_matrix
from research_engine.models import utc_now


TARGET_SCHEMA = "research_target.v1"
EVIDENCE_SCHEMA = "target_evidence.v1"
CLAIM_REVIEW_SCHEMA = "target_claim_review.v1"

SOURCE_CLASSES = {
    "official_jd",
    "official_company_material",
    "community_report",
    "expert_guide",
    "generic_resource",
    "discovery_only",
}

SEARCH_HOST_PATHS = (
    ("google.com", "/search"),
    ("youtube.com", "/results"),
    ("reddit.com", "/search"),
    ("github.com", "/search"),
    ("x.com", "/search"),
    ("linkedin.com", "/jobs/search"),
)
GENERIC_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "leetcode.com",
    "youtube.com",
    "youtu.be",
}
COMMUNITY_HOSTS = {
    "reddit.com",
    "www.reddit.com",
    "x.com",
    "twitter.com",
    "glassdoor.com",
    "www.glassdoor.com",
    "teamblind.com",
    "www.teamblind.com",
}
EXPERT_HOSTS = {
    "interviewing.io",
    "www.interviewing.io",
    "hellointerview.com",
    "www.hellointerview.com",
    "tryexponent.com",
    "www.tryexponent.com",
}
ATS_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.ashbyhq.com",
    "jobs.lever.co",
}

COMPANY_DOMAINS: dict[str, tuple[str, ...]] = {
    str(row["company_key"]): tuple(str(domain) for domain in row["official_domains"])
    for row in load_company_matrix()["companies"]
}

LEVEL_ALIASES: dict[str, tuple[str, ...]] = {
    "l3": ("l3", "software engineer ii", "swe ii", "early career"),
    "l4": ("l4",),
    "l5": ("l5", "senior software engineer", "senior engineer"),
    "l6": ("l6", "staff software engineer", "staff engineer"),
    "staff": ("staff", "l6"),
    "senior staff": ("senior staff", "l7"),
    "sde ii": ("sde ii", "software development engineer ii", "sde 2"),
}

COMPANY_LEVEL_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("google", "l4"): ("software engineer iii", "swe iii", "mid level", "mid-level", "mid"),
}

US_COUNTRY_RE = re.compile(
    r"\b(united states(?: of america)?|u\.?s\.?a\.?|remote[- ](?:in[- ])?u\.?s\.?)\b",
    re.IGNORECASE,
)
US_STATE_NAME_RE = re.compile(
    r"\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|"
    r"georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|"
    r"massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|"
    r"new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|"
    r"oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|"
    r"vermont|virginia|washington|west virginia|wisconsin|wyoming)\b",
    re.IGNORECASE,
)
US_STATE_CODE_RE = re.compile(
    r"(?:,\s*|\blocation\s*:\s*|\()(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|"
    r"KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|"
    r"TN|TX|UT|VT|VA|WA|WV|WI|WY)(?:\b|\))"
)


def _key(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


@dataclass(frozen=True)
class ResearchTarget:
    company: str
    role_family: str
    role_title: str
    level: str
    geography: str
    team: str = ""
    schema_version: str = TARGET_SCHEMA

    @classmethod
    def from_mapping(cls, value: "ResearchTarget | dict[str, Any]") -> "ResearchTarget":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError("target must be a ResearchTarget or mapping")
        schema = str(value.get("schema_version") or TARGET_SCHEMA)
        if schema != TARGET_SCHEMA:
            raise ValueError(f"unsupported target schema: {schema}")
        required = ("company", "role_family", "role_title", "level", "geography")
        missing = [field for field in required if not str(value.get(field) or "").strip()]
        if missing:
            raise ValueError("structured target missing required field(s): " + ", ".join(missing))
        return cls(
            company=str(value["company"]).strip(),
            role_family=str(value["role_family"]).strip(),
            role_title=str(value["role_title"]).strip(),
            level=str(value["level"]).strip(),
            geography=str(value["geography"]).strip(),
            team=str(value.get("team") or "").strip(),
            schema_version=schema,
        )

    @property
    def target_key(self) -> str:
        return "|".join(
            _key(value)
            for value in (
                self.company,
                self.role_family,
                self.role_title,
                self.level,
                self.geography,
            )
        )

    def as_dict(self) -> dict[str, str]:
        return {**asdict(self), "target_key": self.target_key}


def classify_target_evidence(
    rows: list[dict[str, Any]],
    *,
    target: ResearchTarget | dict[str, Any],
    run_date: str | None = None,
) -> list[dict[str, Any]]:
    resolved = ResearchTarget.from_mapping(target)
    return [classify_target_row(row, target=resolved, run_date=run_date) for row in rows]


def classify_target_row(
    row: dict[str, Any],
    *,
    target: ResearchTarget,
    run_date: str | None,
) -> dict[str, Any]:
    enriched = dict(row)
    raw_url = str(row.get("final_url") or row.get("url") or row.get("source_url") or "").strip()
    canonical_url = canonicalize_url(raw_url)
    host = urlsplit(canonical_url).netloc.lower().removeprefix("www.")
    title = str(row.get("title") or "")
    text = str(row.get("text") or row.get("text_excerpt") or "")
    raw_combined = " ".join((title, text, str(row.get("publisher") or "")))
    combined = _norm(raw_combined)
    role_anchor = build_role_anchor(row, url=canonical_url)
    source_class = classify_source(row, url=canonical_url, host=host, text=combined)
    dynamic_official = is_dynamic_official_domain(host, company=target.company, text=combined)
    if source_class == "generic_resource" and dynamic_official:
        source_class = (
            "official_jd"
            if is_dynamic_official_job_page(
                canonical_url,
                role_title=target.role_title,
                anchor_text=role_anchor,
                text=combined,
            )
            else "official_company_material"
        )
    is_final = (
        bool(row.get("is_final_page"))
        if "is_final_page" in row
        else infer_final_page(canonical_url, source_class=source_class)
    )
    if is_search_url(canonical_url) or is_landing_url(canonical_url):
        is_final = False
    current_status = infer_current_status(row, text=combined, source_class=source_class)
    target_match = build_target_match(
        row,
        target=target,
        host=host,
        url=canonical_url,
        text=combined,
        raw_text=raw_combined,
    )
    reasons: list[str] = []
    eligible_claims: list[str] = []

    if source_class == "discovery_only":
        reasons.append("search_page" if is_search_url(canonical_url) else "not_final_page")
        disposition = "discovery_only"
    elif source_class == "generic_resource":
        reasons.append("generic_resource")
        disposition = "background_only"
    else:
        if target_match["company"] == "mismatch":
            reasons.append("wrong_company")
        if target_match["role_title"] == "mismatch" or target_match["role_family"] == "mismatch":
            reasons.append("wrong_role")
        elif source_class == "official_jd" and target_match["role_title"] != "exact":
            reasons.append("near_role_match")
        if target_match["level"] == "mismatch":
            reasons.append("wrong_level")
        elif (
            source_class == "official_jd"
            and target_match["level"] == "unknown"
            and _norm(target.level) not in {"unspecified", "any"}
        ):
            reasons.append("unknown_level")
        if target_match["geography"] == "mismatch" and source_class == "official_jd":
            reasons.append("wrong_geography")
        elif target_match["geography"] == "unknown" and source_class == "official_jd":
            reasons.append("unknown_geography")
        if not is_final:
            reasons.append("landing_page" if is_landing_url(canonical_url) else "not_final_page")
        if source_class.startswith("official_") and not is_verified_official(
            row, target=target, host=host, text=combined
        ):
            reasons.append("unverified_official_host")
        if current_status == "closed":
            reasons.append("stale_or_closed")
        elif source_class == "official_jd" and current_status == "unknown":
            reasons.append("unknown_current_status")
        if bool(row.get("access_blocked")):
            reasons.append("access_blocked")
        if source_class == "official_jd" and len(text.strip()) < 80:
            reasons.append("insufficient_content")
        if bool(row.get("is_duplicate")):
            reasons.append("duplicate")

        if not reasons and source_class == "official_jd" and current_status == "active":
            if (
                target_match["overall"] in {"exact", "compatible"}
                and target_match["role_title"] == "exact"
            ):
                eligible_claims.append("current_official_role")
        if not reasons and source_class == "official_company_material":
            if (
                target_match["company"] == "exact"
                and target_match["role_family"] != "mismatch"
                and target_match["level"] != "mismatch"
                and contains_interview_process(combined)
            ):
                eligible_claims.append("interview_loop")
        if not reasons and source_class in {"community_report", "expert_guide"}:
            if target_match["company"] == "exact" and target_match["role_family"] != "mismatch":
                if contains_interview_process(combined) and is_recent_report(row, run_date=run_date):
                    eligible_claims.extend(("interview_loop", "public_discussion_signals"))
                elif contains_interview_process(combined):
                    reasons.append("stale_or_closed")

        if source_class == "official_jd" and not eligible_claims and not reasons:
            reasons.append("current_role_threshold_not_met")
        if not eligible_claims and not reasons:
            reasons.append("no_supported_target_claim")

        if eligible_claims:
            disposition = "accepted"
        elif bool(row.get("is_duplicate")):
            disposition = "duplicate"
        else:
            disposition = "rejected"

    independence_key = build_independence_key(row, host=host, canonical_url=canonical_url)
    content_hash = hashlib.sha256(_norm(text).encode("utf-8")).hexdigest() if text else ""
    enriched.update(
        {
            "schema_version": EVIDENCE_SCHEMA,
            "canonical_url": canonical_url,
            "final_url": str(row.get("final_url") or raw_url),
            "source_class": source_class,
            "access_mode": str(row.get("access_mode") or "public_fetch"),
            "is_final_page": is_final,
            "discovered_via": str(row.get("discovered_via") or row.get("connector") or ""),
            "current_status": current_status,
            "published_at": str(row.get("published_at") or row.get("updated_at") or ""),
            "captured_at": str(row.get("captured_at") or utc_now()),
            "target": target.as_dict(),
            "target_key": target.target_key,
            "target_match": target_match,
            "claim_fitness": {
                "disposition": disposition,
                "eligible_claims": eligible_claims,
                "rejection_reasons": sorted(set(reasons)),
            },
            "independence_key": independence_key,
            "content_hash": content_hash,
            "text_excerpt": text[:500],
        }
    )
    return enriched


def classify_source(row: dict[str, Any], *, url: str, host: str, text: str) -> str:
    explicit = str(row.get("source_class") or "")
    if explicit in SOURCE_CLASSES:
        return explicit
    source_kind = _norm(row.get("source_kind") or row.get("entity_type") or "")
    source_id = _norm(row.get("source_id") or "")
    if (
        "discovery" in source_kind
        or "search_page" in source_kind
        or source_id == "platform_search_pages"
        or is_search_url(url)
    ):
        return "discovery_only"
    if "official_job" in source_kind or "job_posting" in source_kind:
        return "official_jd"
    if "official" in source_kind or "career_page" in source_kind or source_id == "company_careers":
        if infer_final_page(url, source_class="official_jd") and contains_job_description(text):
            return "official_jd"
        return "official_company_material"
    if host in COMMUNITY_HOSTS or "community" in source_kind or "candidate_report" in source_kind:
        return "community_report"
    if host in EXPERT_HOSTS or "expert" in source_kind:
        return "expert_guide"
    if host in GENERIC_HOSTS or "repo" in source_kind or "generic" in source_kind:
        return "generic_resource"
    if host in ATS_HOSTS and infer_final_page(url, source_class="official_jd"):
        return "official_jd"
    return "generic_resource"


def build_target_match(
    row: dict[str, Any],
    *,
    target: ResearchTarget,
    host: str,
    url: str,
    text: str,
    raw_text: str = "",
) -> dict[str, str]:
    row_company = _norm(row.get("company") or "")
    target_company = _norm(target.company)
    company_owner = company_for_host(host)
    if row_company:
        company = "exact" if _key(row_company) == _key(target_company) else "mismatch"
    elif company_owner:
        company = "exact" if company_owner == _key(target_company) else "mismatch"
    elif target_company in text:
        company = "exact"
    else:
        company = "unknown"

    title_text = _norm(row.get("title") or "")
    role_haystack = _norm(" ".join((title_text, text)))
    anchor_match = match_role_title(target.role_title, build_role_anchor(row, url=url))
    body_match = match_role_title(target.role_title, role_haystack)
    if anchor_match == "exact":
        role_title = "exact"
    elif anchor_match == "compatible" or body_match in {"exact", "compatible"}:
        role_title = "compatible"
    elif anchor_match == "mismatch" and body_match == "mismatch":
        role_title = "mismatch"
    else:
        role_title = "unknown"
    family = match_role_family(target.role_family, role_haystack)
    level = match_level(target.level, role_haystack, company=target.company)
    geography = match_geography(
        target.geography,
        " ".join(
            (
                str(row.get("target_detail_text") or raw_text or text),
                str(row.get("location") or ""),
                str(row.get("geography") or ""),
            )
        ),
    )
    values = (company, family, role_title, level, geography)
    if "mismatch" in values:
        overall = "mismatch"
    elif company == "exact" and role_title == "exact" and level == "exact" and geography == "exact":
        overall = "exact"
    elif company == "exact" and family in {"exact", "compatible"} and role_title in {
        "exact",
        "compatible",
    } and level in {"exact", "compatible", "unknown"} and geography in {
        "exact",
        "compatible",
        "unknown",
    }:
        overall = "compatible"
    else:
        overall = "unknown"
    return {
        "company": company,
        "role_family": family,
        "role_title": role_title,
        "level": level,
        "geography": geography,
        "overall": overall,
    }


def match_role_title(role_title: str, text: str) -> str:
    normalized_text = _norm(re.sub(r"[^a-z0-9]+", " ", text.lower()))
    normalized_title = _norm(re.sub(r"[^a-z0-9]+", " ", role_title.lower()))
    if normalized_title and re.search(rf"\b{re.escape(normalized_title)}\b", normalized_text):
        return "exact"
    tokens = _key(role_title).split("_")
    found = [token for token in tokens if re.search(rf"\b{re.escape(token)}\b", text)]
    if tokens and len(found) == len(tokens):
        return "exact"
    role_nouns = {"engineer", "developer", "architect", "scientist", "manager", "researcher"}
    if found and (role_nouns & set(found)):
        return "compatible"
    if role_nouns & set(tokens) and any(
        re.search(rf"\b{re.escape(noun)}\b", text) for noun in role_nouns
    ):
        return "compatible"
    return "unknown" if not text else "mismatch"


def match_role_family(role_family: str, text: str) -> str:
    family = _key(role_family)
    aliases = {
        "software_engineering": (
            "software engineer",
            "software development engineer",
            "backend engineer",
            "frontend engineer",
            "full stack",
            "developer",
            "sde",
            "site reliability",
        ),
        "machine_learning": ("machine learning", "ml engineer", "ai engineer", "research engineer"),
        "data_engineering": ("data engineer", "analytics engineer", "data platform"),
    }.get(family, tuple(family.split("_")))
    if family.replace("_", " ") in text:
        return "exact"
    if any(alias in text for alias in aliases):
        return "compatible"
    return "unknown" if not text else "mismatch"


def match_level(level: str, text: str, *, company: str = "") -> str:
    normalized = _norm(level)
    if normalized in {"unspecified", "any"}:
        return "compatible"
    aliases = LEVEL_ALIASES.get(normalized, (normalized,)) + COMPANY_LEVEL_ALIASES.get(
        (_key(company), normalized), ()
    )
    if normalized and phrase_in_text(normalized, text):
        return "exact"
    if any(alias and phrase_in_text(alias, text) for alias in aliases):
        return "compatible"
    seniority_terms = ("intern", "junior", "entry level", "mid level", "senior", "staff", "principal", "director")
    if any(term in text for term in seniority_terms):
        return "mismatch"
    return "unknown"


def phrase_in_text(phrase: str, text: str) -> bool:
    normalized_phrase = _norm(re.sub(r"[^a-z0-9]+", " ", phrase.lower()))
    normalized_text = _norm(re.sub(r"[^a-z0-9]+", " ", text.lower()))
    return bool(
        normalized_phrase
        and re.search(rf"\b{re.escape(normalized_phrase)}\b", normalized_text)
    )


def match_geography(geography: str, text: str) -> str:
    normalized = _norm(geography)
    haystack = _norm(text)
    us_targets = {"us", "usa", "united states"}
    if normalized and normalized not in us_targets and normalized in haystack:
        return "exact"
    if normalized in us_targets and (
        US_COUNTRY_RE.search(haystack)
        or US_STATE_NAME_RE.search(haystack)
        or US_STATE_CODE_RE.search(text)
    ):
        return "compatible"
    if normalized in {"remote", "global", "worldwide"} and "remote" in haystack:
        return "compatible"
    foreign_markers = ("london", "dublin", "singapore", "india", "germany", "france", "canada", "australia")
    if normalized in us_targets and any(marker in haystack for marker in foreign_markers):
        return "mismatch"
    return "unknown"


def build_target_claim_review(
    target: ResearchTarget | dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    warnings: list[str],
    run_date: str | None = None,
) -> dict[str, Any]:
    resolved = ResearchTarget.from_mapping(target)
    role_rows = eligible_rows(rows, "current_official_role")
    interview_rows = eligible_rows(rows, "interview_loop")
    official_process = [row for row in interview_rows if row.get("source_class") == "official_company_material"]
    reports = [
        row
        for row in interview_rows
        if row.get("source_class") in {"community_report", "expert_guide"}
    ]
    independent_reports = unique_by_independence(reports)
    role_supported = bool(role_rows)
    interview_supported = bool(official_process) or len(independent_reports) >= 2
    if role_supported and interview_supported:
        support_level = "company_role_calibrated"
    elif role_supported:
        support_level = "role_calibrated"
    elif interview_supported:
        support_level = "company_calibrated"
    else:
        support_level = "baseline_only"
    overall_status = "supported" if role_supported else "unsupported"
    resolved_date = parse_date(run_date) or date.today()
    accepted_ids = {
        str(row.get("evidence_id") or "")
        for row in rows
        if (row.get("claim_fitness") or {}).get("disposition") == "accepted"
    }
    rejected = [
        {
            "evidence_id": str(row.get("evidence_id") or ""),
            "source_class": str(row.get("source_class") or ""),
            "reasons": list((row.get("claim_fitness") or {}).get("rejection_reasons") or []),
        }
        for row in rows
        if str(row.get("evidence_id") or "") not in accepted_ids
    ]
    return {
        "schema_version": CLAIM_REVIEW_SCHEMA,
        "generated_at": utc_now(),
        "target": resolved.as_dict(),
        "overall": {
            "status": overall_status,
            "support_level": support_level,
            "stance": "supported" if role_supported else "insufficient_target_evidence",
            "confidence": "high" if role_supported and interview_supported else "medium" if role_supported else "low",
            "summary": (
                "A current final official target JD passed deterministic gates."
                if role_supported
                else "No current final official JD passed the complete target tuple gates."
            ),
            "valid_until": (resolved_date + timedelta(days=7)).isoformat(),
            "risk_flags": list(warnings),
        },
        "claims": [
            {
                "claim_id": "current_official_role",
                "question": "Is a current final official JD available for the complete target tuple?",
                "verdict": "supported" if role_supported else "unsupported",
                "eligible_evidence_ids": evidence_ids(role_rows),
                "independent_source_count": len(unique_by_independence(role_rows)),
                "threshold": "one active, final, official, target-compatible JD",
                "missing": [] if role_supported else ["current_final_official_jd"],
                "valid_until": (resolved_date + timedelta(days=7)).isoformat(),
            },
            {
                "claim_id": "interview_loop",
                "question": "Is the target interview loop independently supported?",
                "verdict": "supported" if interview_supported else "unsupported",
                "eligible_evidence_ids": evidence_ids(official_process or independent_reports),
                "independent_source_count": len(unique_by_independence(official_process or reports)),
                "threshold": "one official process page or two independent target-matched reports",
                "missing": [] if interview_supported else ["official_process_or_two_independent_reports"],
                "valid_until": (resolved_date + timedelta(days=30)).isoformat(),
            },
            {
                "claim_id": "public_discussion_signals",
                "question": "Are public discussion signals corroborated?",
                "verdict": "corroborated" if len(independent_reports) >= 2 else "hypothesis_only",
                "eligible_evidence_ids": evidence_ids(independent_reports),
                "independent_source_count": len(independent_reports),
                "threshold": "two independent current target-matched reports",
                "missing": [] if len(independent_reports) >= 2 else ["independent_public_corroboration"],
                "valid_until": (resolved_date + timedelta(days=30)).isoformat(),
            },
        ],
        "rejected_evidence": rejected,
        "connector_warnings": warnings,
    }


def eligible_rows(rows: Iterable[dict[str, Any]], claim_id: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if claim_id in list((row.get("claim_fitness") or {}).get("eligible_claims") or [])
        and (row.get("claim_fitness") or {}).get("disposition") == "accepted"
    ]


def unique_by_independence(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("independence_key") or row.get("canonical_url") or row.get("evidence_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def evidence_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    return [str(row.get("evidence_id") or "") for row in rows if row.get("evidence_id")]


def company_for_host(host: str) -> str:
    normalized = host.removeprefix("www.")
    for company, domains in COMPANY_DOMAINS.items():
        if any(normalized == domain or normalized.endswith("." + domain) for domain in domains):
            return company
    return ""


def is_dynamic_official_domain(host: str, *, company: str, text: str) -> bool:
    """Conservatively recognize an unregistered company's fetched first-party domain."""
    normalized_host = host.lower().removeprefix("www.").rstrip(".")
    labels = normalized_host.split(".")
    if len(labels) < 2 or labels[-1] not in {"com", "io", "ai", "co", "org", "dev"}:
        return False
    company_key = _key(company).replace("_", "")
    domain_key = _key(labels[-2]).replace("_", "")
    prefix_ok = len(labels) == 2 or (len(labels) == 3 and labels[0] in {"careers", "jobs"})
    company_mentioned = company_key and company_key in _key(text).replace("_", "")
    return bool(prefix_ok and domain_key == company_key and company_mentioned)


def is_dynamic_official_job_page(
    url: str, *, role_title: str, anchor_text: str, text: str
) -> bool:
    parsed = urlsplit(url)
    path = parsed.path.lower().rstrip("/")
    if is_landing_url(url) or not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2 or segments[0] not in {"careers", "jobs"}:
        return False
    non_job_slugs = {
        "about",
        "benefits",
        "culture",
        "departments",
        "engineering",
        "faq",
        "how-we-hire",
        "open-roles",
        "people",
        "teams",
        "values",
    }
    if segments[1] in non_job_slugs:
        return False
    return (
        contains_job_description(text)
        and match_role_title(role_title, anchor_text) == "exact"
    )


def build_role_anchor(row: dict[str, Any], *, url: str) -> str:
    parts: list[str] = []
    page_heading = str(row.get("page_heading") or "").strip()
    if page_heading:
        parts.append(page_heading)
    title = str(row.get("title") or "").strip()
    normalized_title = _norm(title)
    if title and not normalized_title.startswith("xai cited candidate") and not title.startswith(
        ("http://", "https://")
    ):
        parts.append(title)
    path_segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    ignored_segments = {
        "applications",
        "careers",
        "job",
        "jobs",
        "listing",
        "positions",
        "postings",
        "results",
    }
    for segment in reversed(path_segments):
        cleaned = re.sub(r"^\d+[-_]", "", segment)
        words = re.sub(r"[^a-zA-Z0-9]+", " ", cleaned).strip()
        if words and not words.isdigit() and _key(words) not in ignored_segments:
            parts.append(words)
            break
    return _norm(" ".join(parts))


def is_verified_official(
    row: dict[str, Any], *, target: ResearchTarget, host: str, text: str = ""
) -> bool:
    target_key = _key(target.company)
    owner = company_for_host(host)
    if owner:
        return owner == target_key
    if is_dynamic_official_domain(host, company=target.company, text=text):
        return True
    return host in ATS_HOSTS and bool(row.get("ats_ownership_verified"))


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url.strip())
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    path = re.sub(r"/+$", "", path) or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def is_search_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    if any((host == h or host.endswith("." + h)) and path.startswith(p) for h, p in SEARCH_HOST_PATHS):
        return True
    return any(token in path for token in ("/search", "/jobs/results")) and bool(parsed.query)


def is_landing_url(url: str) -> bool:
    parsed = urlsplit(url)
    path = parsed.path.lower().rstrip("/")
    return path in {
        "",
        "/jobs",
        "/careers",
        "/jobs/search",
        "/careers/jobs",
        "/about/careers/applications/jobs/results",
    }


def infer_final_page(url: str, *, source_class: str) -> bool:
    if not url or is_search_url(url) or is_landing_url(url):
        return False
    path = urlsplit(url).path.lower()
    if source_class == "official_jd":
        return any(token in path for token in ("/job/", "/jobs/", "/listing/", "/postings/", "/positions/"))
    return True


def infer_current_status(row: dict[str, Any], *, text: str, source_class: str) -> str:
    closed_markers = ("job is no longer available", "position has been filled", "job has expired", "no longer accepting applications")
    if any(marker in text for marker in closed_markers):
        return "closed"
    explicit = _norm(row.get("current_status") or "")
    if explicit in {"active", "closed"}:
        return explicit
    if source_class == "official_jd" and contains_job_description(text):
        if re.search(r"\b(apply|submit application)\b", text):
            return "active"
    if explicit == "not_applicable" and source_class != "official_jd":
        return explicit
    return "unknown" if source_class == "official_jd" else "not_applicable"


def contains_job_description(text: str) -> bool:
    return any(term in text for term in ("responsibilities", "qualifications", "requirements", "what you'll do", "what you’ll do"))


def contains_interview_process(text: str) -> bool:
    return any(term in text for term in ("interview loop", "interview process", "onsite", "phone screen", "technical screen", "interview rounds", "hiring manager"))


def is_recent_report(row: dict[str, Any], *, run_date: str | None) -> bool:
    published = parse_date(str(row.get("published_at") or row.get("updated_at") or ""))
    if not published:
        return False
    today = parse_date(run_date) or date.today()
    return timedelta(days=0) <= today - published <= timedelta(days=730)


def parse_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).date()
        except ValueError:
            return None


def build_independence_key(row: dict[str, Any], *, host: str, canonical_url: str) -> str:
    author = _key(str(row.get("author") or row.get("publisher") or ""))
    if host in {"x.com", "twitter.com", "reddit.com", "www.reddit.com"} and author:
        return f"{host}:{author}"
    return host or canonical_url
