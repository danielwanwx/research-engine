"""Deterministic publication-date and as-of freshness helpers."""

from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
import json
import re
from typing import Any


_URL_DATE_RE = re.compile(
    r"(?<!\d)(?P<year>20\d{2})[-/](?P<month>0[1-9]|1[0-2])[-/]"
    r"(?P<day>0[1-9]|[12]\d|3[01])(?!\d)|"
    r"(?<!\d)(?P<compact>20\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))(?!\d)"
)
_META_DATE_NAMES = {
    "article:published_time",
    "date",
    "datepublished",
    "publication_date",
    "pubdate",
}
_META_UPDATED_NAMES = {
    "article:modified_time",
    "date_modified",
    "datemodified",
    "last-modified",
    "og:updated_time",
}


class _DateHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_dates: list[str] = []
        self.updated_meta_dates: list[str] = []
        self.time_dates: list[str] = []
        self.json_ld: list[str] = []
        self._in_json_ld = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): str(value or "") for key, value in attrs}
        if tag == "meta":
            name = (values.get("property") or values.get("name") or "").lower()
            if name in _META_DATE_NAMES and values.get("content"):
                self.meta_dates.append(values["content"])
            elif name in _META_UPDATED_NAMES and values.get("content"):
                self.updated_meta_dates.append(values["content"])
        elif tag == "time" and values.get("datetime"):
            self.time_dates.append(values["datetime"])
        elif tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._script_parts))
            self._in_json_ld = False
            self._script_parts = []


def _iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text or "/" in text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _json_ld_dates(value: Any, keys: tuple[str, ...]) -> list[str]:
    if isinstance(value, dict):
        direct = [str(value[key]) for key in keys if value.get(key)]
        return direct + [
            item for child in value.values() for item in _json_ld_dates(child, keys)
        ]
    if isinstance(value, list):
        return [item for child in value for item in _json_ld_dates(child, keys)]
    return []


def _first_valid(values: list[Any]) -> date | None:
    return next((parsed for value in values if (parsed := _iso_date(value))), None)


def extract_published_date(row: dict[str, Any]) -> dict[str, str]:
    """Extract one conservative publication date using the documented precedence."""

    temporal = extract_temporal_metadata(row)
    return {
        "published_at": temporal["published_at"],
        "date_source": temporal["date_source"],
        "date_confidence": temporal["date_confidence"],
    }


def extract_temporal_metadata(row: dict[str, Any]) -> dict[str, str]:
    """Extract publication, update, and latest observation dates without conflating them."""

    native = _first_valid(
        [row.get(key) for key in ("published_at", "published_date", "date_published")]
    )

    parser = _DateHTMLParser()
    html = str(row.get("raw_html") or row.get("html") or "")
    if html:
        try:
            parser.feed(html)
        except Exception:
            parser = _DateHTMLParser()

    json_published: list[str] = []
    json_updated: list[str] = []
    for block in parser.json_ld:
        try:
            payload = json.loads(block)
            json_published.extend(_json_ld_dates(payload, ("datePublished", "dateCreated")))
            json_updated.extend(_json_ld_dates(payload, ("dateModified",)))
        except (TypeError, ValueError):
            continue

    published = (
        _date_result(native, "connector_native", "high")
        if native
        else _publication_fallback(row, parser=parser, json_dates=json_published)
    )
    updated = _first_valid(
        [row.get(key) for key in ("updated_at", "modified_at", "date_modified")]
    )
    updated_source = "connector_native"
    updated_confidence = "high"
    if not updated:
        updated = _first_valid(json_updated)
        updated_source = "json_ld" if updated else ""
    if not updated:
        updated = _first_valid(parser.updated_meta_dates)
        updated_source = "html_meta" if updated else ""

    observed = _first_valid(
        [row.get(key) for key in ("observed_at", "latest_observation_at")]
    )
    observed_source = "connector_native"
    observed_confidence = "high"
    if not observed:
        observed = _latest_table_date(row.get("tables") or [])
        observed_source = "table_observation" if observed else ""
        observed_confidence = "medium" if observed else ""

    return {
        **published,
        "updated_at": updated.isoformat() if updated else "",
        "updated_date_source": updated_source,
        "updated_date_confidence": updated_confidence if updated else "",
        "observed_at": observed.isoformat() if observed else "",
        "observed_date_source": observed_source,
        "observed_date_confidence": observed_confidence if observed else "",
    }


def _publication_fallback(
    row: dict[str, Any],
    *,
    parser: _DateHTMLParser,
    json_dates: list[str],
) -> dict[str, str]:
    if parsed := _first_valid(json_dates):
        return _date_result(parsed, "json_ld", "high")
    if parsed := _first_valid(parser.meta_dates):
        return _date_result(parsed, "html_meta", "high")
    if parsed := _first_valid(parser.time_dates):
        return _date_result(parsed, "time_element", "medium")
    url = str(row.get("final_url") or row.get("url") or row.get("source_url") or "")
    if parsed := _latest_text_date(url):
        return _date_result(parsed, "url_pattern", "low")
    return {"published_at": "", "date_source": "", "date_confidence": ""}


def _latest_table_date(value: Any) -> date | None:
    values: list[date] = []
    if isinstance(value, list):
        for child in value:
            parsed = _latest_table_date(child)
            if parsed:
                values.append(parsed)
    elif parsed := _latest_text_date(str(value or "")):
        values.append(parsed)
    return max(values) if values else None


def _latest_text_date(text: str) -> date | None:
    values: list[date] = []
    for match in _URL_DATE_RE.finditer(text):
        compact = match.group("compact")
        candidate = (
            f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
            if compact
            else f"{match.group('year')}-{match.group('month')}-{match.group('day')}"
        )
        if parsed := _iso_date(candidate):
            values.append(parsed)
    return max(values) if values else None


def _date_result(value: date, source: str, confidence: str) -> dict[str, str]:
    return {
        "published_at": value.isoformat(),
        "date_source": source,
        "date_confidence": confidence,
    }


def enrich_row_freshness(
    row: dict[str, Any],
    *,
    as_of: str,
    window_days: int | None,
) -> dict[str, Any]:
    """Return a copy with extracted date, age, and freshness status."""

    as_of_date = _iso_date(as_of)
    if not as_of_date or len(as_of) != 10:
        raise ValueError("as_of must be an ISO date (YYYY-MM-DD)")
    if window_days is not None and window_days < 0:
        raise ValueError("window_days must be non-negative or None")

    enriched = dict(row)
    temporal = extract_temporal_metadata(row)
    enriched.update(temporal)
    enriched["freshness_window_days"] = window_days
    if window_days is None:
        enriched.update({"freshness_status": "not_applicable", "age_days": None})
        return enriched

    effective_dates = (
        ("observed_at", temporal["observed_at"]),
        ("published_at", temporal["published_at"]),
        ("updated_at", temporal["updated_at"]),
    )
    date_field, effective = next(
        ((field, parsed) for field, value in effective_dates if (parsed := _iso_date(value))),
        ("", None),
    )
    enriched["freshness_date_field"] = date_field
    enriched["freshness_date"] = effective.isoformat() if effective else ""
    if not effective:
        enriched.update({"freshness_status": "undated", "age_days": None})
        return enriched

    age = (as_of_date - effective).days
    if age < 0:
        enriched.update({"freshness_status": "future_dated", "age_days": age})
        return enriched
    enriched.update(
        {
            "freshness_status": "fresh" if age <= window_days else "stale",
            "age_days": age,
        }
    )
    return enriched
