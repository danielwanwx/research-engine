"""Content-type-aware extraction and stable chunking with no core dependencies."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import os
import shutil
import subprocess
from typing import Any, Callable


PdfExtractor = Callable[[bytes], str]
_SKIP_TAGS = {"aside", "footer", "form", "header", "nav", "noscript", "script", "style"}
_BLOCK_TAGS = {"blockquote", "div", "li", "p", "pre", "section"}


class _SemanticHTMLParser(HTMLParser):
    def __init__(self, *, max_table_rows: int = 50, max_table_columns: int = 20) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict[str, str]] = []
        self.tables: list[list[list[str]]] = []
        self.heading = ""
        self._parts: list[str] = []
        self._block_tag = ""
        self._skip_depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._max_table_rows = max_table_rows
        self._max_table_columns = max_table_columns

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            self._skip_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._flush()
            self._skip_depth = 1
            return
        if tag in _BLOCK_TAGS or tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self._block_tag = tag
        elif tag == "table":
            self._flush()
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS or tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            if len(self._row) < self._max_table_columns:
                self._row.append(_clean(" ".join(self._cell))[:500])
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row) and len(self._table) < self._max_table_rows:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
                for row in self._table:
                    self.blocks.append({"heading": self.heading, "text": " | ".join(row)})
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._table is None:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = _clean(" ".join(self._parts))
        self._parts = []
        if not text:
            return
        if self._block_tag.startswith("h") and len(self._block_tag) == 2:
            self.heading = text
        self.blocks.append({"heading": self.heading, "text": text})
        self._block_tag = ""


def _clean(value: str) -> str:
    return " ".join(value.split())


def build_chunks(
    blocks: list[str | dict[str, Any]],
    *,
    parent_evidence_id: str,
    max_chars: int = 4_000,
) -> list[dict[str, Any]]:
    """Pack semantic blocks into bounded, stable chunks."""

    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    normalized = [
        {
            "heading": str(block.get("heading") or ""),
            "text": _clean(str(block.get("text") or "")),
        }
        if isinstance(block, dict)
        else {"heading": "", "text": _clean(str(block))}
        for block in blocks
    ]
    pieces: list[dict[str, str]] = []
    for block in normalized:
        text = block["text"]
        while text:
            pieces.append({"heading": block["heading"], "text": text[:max_chars]})
            text = text[max_chars:]

    packed: list[dict[str, str]] = []
    for piece in pieces:
        if packed and len(packed[-1]["text"]) + 1 + len(piece["text"]) <= max_chars:
            packed[-1]["text"] += "\n" + piece["text"]
        else:
            packed.append(dict(piece))

    chunks: list[dict[str, Any]] = []
    for index, item in enumerate(packed, start=1):
        content_hash = hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
        stable = hashlib.sha256(
            f"{parent_evidence_id}\0{index}\0{item['heading']}\0{content_hash}".encode("utf-8")
        ).hexdigest()[:16]
        chunks.append(
            {
                "chunk_id": f"chunk-{stable}",
                "parent_evidence_id": parent_evidence_id,
                "chunk_index": index,
                "content_hash": content_hash,
                "heading": item["heading"],
                "text": item["text"],
            }
        )
    return chunks


def extract_content(
    body: bytes | str,
    *,
    content_type: str,
    parent_evidence_id: str,
    max_bytes: int = 2_000_000,
    chunk_chars: int = 4_000,
    pdf_extractor: PdfExtractor | None = None,
) -> dict[str, Any]:
    """Extract content into a page-level result and stable child chunks."""

    raw = body if isinstance(body, bytes) else body.encode("utf-8")
    warnings: list[str] = []
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        warnings.append("content_truncated")
    media_type = content_type.lower().split(";", 1)[0].strip()
    blocks: list[dict[str, str]] = []
    tables: list[list[list[str]]] = []
    structured_data: Any = None
    invalid_reasons: list[str] = []

    if media_type in {"text/html", "application/xhtml+xml"}:
        parser = _SemanticHTMLParser()
        parser.feed(raw.decode("utf-8", errors="replace"))
        parser.close()
        blocks, tables = parser.blocks, parser.tables
    elif media_type == "application/json" or media_type.endswith("+json"):
        try:
            structured_data = json.loads(raw.decode("utf-8"))
            blocks = [{"heading": "", "text": line} for line in _json_lines(structured_data)]
        except (UnicodeDecodeError, ValueError):
            invalid_reasons.append("json_extraction_failed")
    elif media_type == "application/pdf":
        extractor = pdf_extractor or _local_pdftotext()
        if extractor is None:
            invalid_reasons.append("pdf_extractor_unavailable")
        else:
            try:
                text = _clean(extractor(raw))
            except Exception:
                text = ""
            if text:
                blocks = [{"heading": "", "text": text}]
            else:
                invalid_reasons.append("pdf_extraction_failed")
    elif media_type.startswith("text/") or media_type in {
        "application/xml",
        "application/rss+xml",
    }:
        text = raw.decode("utf-8", errors="replace")
        blocks = [{"heading": "", "text": line} for line in text.splitlines() if _clean(line)]
    else:
        invalid_reasons.append("unsupported_content_type")

    text = "\n".join(block["text"] for block in blocks if block["text"])
    if not text and not invalid_reasons:
        invalid_reasons.append("empty_content")
    chunks = build_chunks(
        blocks,
        parent_evidence_id=parent_evidence_id,
        max_chars=chunk_chars,
    )
    return {
        "content_type": media_type,
        "text": text,
        "blocks": blocks,
        "tables": tables,
        "structured_data": structured_data,
        "chunks": chunks,
        "content_valid": bool(text) and not invalid_reasons,
        "content_invalid_reasons": invalid_reasons,
        "warnings": warnings,
    }


def _json_lines(value: Any, *, prefix: str = "", limit: int = 200) -> list[str]:
    lines: list[str] = []

    def visit(current: Any, path: str) -> None:
        if len(lines) >= limit:
            return
        if isinstance(current, dict):
            for key, child in current.items():
                visit(child, f"{path}.{key}" if path else str(key))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                visit(child, f"{path}[{index}]")
        else:
            lines.append(f"{path}: {current}" if path else str(current))

    visit(value, prefix)
    return lines


def _local_pdftotext() -> PdfExtractor | None:
    executable = shutil.which("pdftotext")
    if not executable or os.path.basename(executable) != "pdftotext":
        return None

    def extract(body: bytes) -> str:
        completed = subprocess.run(
            [executable, "-", "-"],
            input=body,
            capture_output=True,
            check=True,
            timeout=15,
        )
        return completed.stdout.decode("utf-8", errors="replace")

    return extract
