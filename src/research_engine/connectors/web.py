"""Public web-page connector."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.request import Request, urlopen

from research_engine.models import CollectionRequest, CollectionResult, utc_now


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text and not self._skip_depth:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


class WebPageConnector:
    connector_id = "web_page"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        rows: list[dict] = []
        warnings: list[str] = []
        pages = request.source.get("pages") or []
        for page in pages[: request.max_results]:
            if not isinstance(page, dict):
                continue
            url = str(page.get("url") or "")
            if not url:
                continue
            try:
                text = fetch_text(url)
            except Exception as exc:
                warnings.append(f"web_page failed for {url}: {exc}")
                continue
            rows.append(
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": str(page.get("title") or url),
                    "url": url,
                    "publisher": str(page.get("publisher") or ""),
                    "captured_at": utc_now(),
                    "text": text[:4000],
                    "source_confidence": str(page.get("source_confidence") or "medium"),
                }
            )
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=warnings,
        )


def fetch_text(url: str, *, timeout: float = 12.0) -> str:
    request = Request(url, headers={"User-Agent": "research-engine/0.1"})
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()
