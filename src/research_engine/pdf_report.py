"""Dependency-light boundary for rendering standard run reports as PDF."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from research_engine.models import utc_now


INK = "#172033"
MUTED = "#607086"
ACCENT = "#2563EB"
ACCENT_DARK = "#1D4ED8"
ACCENT_PALE = "#EFF6FF"
LINE = "#DCE4EE"
TABLE_HEAD = "#E8F0FE"
TABLE_ALT = "#F8FAFC"


def render_pdf_report(run_dir: Path) -> dict[str, Any]:
    """Render ``research_report.md`` atomically and return a serializable status."""

    run_dir = Path(run_dir)
    output = run_dir / "research_report.pdf"
    temp_path: Path | None = None
    try:
        markdown = (run_dir / "research_report.md").read_text(encoding="utf-8")
        if not markdown.strip():
            raise ValueError("research_report.md is empty")
        manifest = _read_json(run_dir / "run_manifest.json")
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".research-report-",
            suffix=".pdf",
            dir=run_dir,
        )
        os.close(descriptor)
        temp_path = Path(temp_name)
        page_count, font_mode = _build_pdf(
            markdown,
            output=temp_path,
            title=str(manifest.get("topic") or "Research Report"),
            as_of=str(manifest.get("as_of") or ""),
        )
        os.replace(temp_path, output)
        temp_path = None
        return {
            "schema_version": "pdf_report_status.v1",
            "status": "generated",
            "path": output.name,
            "generated_at": utc_now(),
            "page_count": page_count,
            "byte_count": output.stat().st_size,
            "font_mode": font_mode,
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:
        return {
            "schema_version": "pdf_report_status.v1",
            "status": "failed",
            "path": output.name,
            "generated_at": utc_now(),
            "page_count": 0,
            "byte_count": 0,
            "font_mode": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _build_pdf(markdown: str, *, output: Path, title: str, as_of: str) -> tuple[int, str]:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

    body_font, bold_font, font_mode = _register_fonts()
    page_width, page_height = A4
    left = right = 17 * mm
    top = bottom = 18 * mm
    styles = _styles(body_font, bold_font)
    story = _markdown_story(markdown, styles=styles, content_width=page_width - left - right)

    def draw_page(canvas, doc) -> None:
        canvas.saveState()
        page = canvas.getPageNumber()
        canvas.setStrokeColor(colors.HexColor(LINE))
        canvas.setLineWidth(0.5)
        if page > 1:
            canvas.line(left, page_height - 10.5 * mm, page_width - right, page_height - 10.5 * mm)
            canvas.setFont(body_font, 6.8)
            canvas.setFillColor(colors.HexColor(MUTED))
            canvas.drawString(left, page_height - 8 * mm, _short(title, 72))
        canvas.line(left, 10.5 * mm, page_width - right, 10.5 * mm)
        canvas.setFont(body_font, 6.8)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(left, 7.3 * mm, f"Research Engine | As of {as_of or 'unknown'}")
        canvas.drawRightString(page_width - right, 7.3 * mm, str(page))
        canvas.restoreState()

    frame = Frame(
        left,
        bottom,
        page_width - left - right,
        page_height - top - bottom,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="report-frame",
    )
    doc = BaseDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=title,
        author="Research Engine",
        subject=f"Research report as of {as_of or 'unknown'}",
    )
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame], onPage=draw_page)])
    doc.build(story)
    return int(doc.page), font_mode


def _register_fonts() -> tuple[str, str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    regular = [
        ("/System/Library/Fonts/STHeiti Light.ttc", 0),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ]
    bold = [
        ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ]

    regular_font = _register_first_ttf("ResearchBody", regular, TTFont, pdfmetrics)
    bold_font = _register_first_ttf("ResearchBold", bold, TTFont, pdfmetrics)
    if regular_font and bold_font:
        pdfmetrics.registerFontFamily(
            regular_font,
            normal=regular_font,
            bold=bold_font,
            italic=regular_font,
            boldItalic=bold_font,
        )
        return regular_font, bold_font, "embedded_ttf"

    fallback = "STSong-Light"
    if fallback not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(fallback))
    return fallback, fallback, "cid_fallback"


def _register_first_ttf(name: str, candidates, ttfont, pdfmetrics) -> str:
    for path, index in candidates:
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(ttfont(name, path, subfontIndex=index))
            return name
        except Exception:
            continue
    return ""


def _styles(body_font: str, bold_font: str) -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ResearchTitle",
            parent=base["Title"],
            fontName=bold_font,
            fontSize=22,
            leading=29,
            textColor=colors.HexColor(INK),
            spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "ResearchH2",
            parent=base["Heading2"],
            fontName=bold_font,
            fontSize=14,
            leading=19,
            textColor=colors.HexColor(INK),
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "ResearchH3",
            parent=base["Heading3"],
            fontName=bold_font,
            fontSize=11,
            leading=15,
            textColor=colors.HexColor(ACCENT_DARK),
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ResearchBody",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=9,
            leading=14,
            textColor=colors.HexColor(INK),
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "ResearchBullet",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=8.8,
            leading=13.5,
            leftIndent=15,
            firstLineIndent=-10,
            bulletIndent=2,
            textColor=colors.HexColor(INK),
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "number": ParagraphStyle(
            "ResearchNumber",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=8.8,
            leading=13.5,
            leftIndent=18,
            firstLineIndent=-18,
            textColor=colors.HexColor(INK),
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "table": ParagraphStyle(
            "ResearchTable",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=7.6,
            leading=11,
            textColor=colors.HexColor(INK),
            wordWrap="CJK",
        ),
        "table_head": ParagraphStyle(
            "ResearchTableHead",
            parent=base["BodyText"],
            fontName=bold_font,
            fontSize=7.7,
            leading=11,
            textColor=colors.HexColor(INK),
            wordWrap="CJK",
        ),
    }


def _markdown_story(markdown: str, *, styles: dict[str, Any], content_width: float) -> list[Any]:
    from reportlab.lib import colors
    from reportlab.platypus import HRFlowable, Paragraph, Spacer

    lines = markdown.splitlines()
    story: list[Any] = []
    index = 0
    first_heading = True
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if _is_table_start(lines, index):
            table_lines = [stripped, lines[index + 1].strip()]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            story.append(_table(table_lines, styles=styles, width=content_width))
            story.append(Spacer(1, 8))
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            value = _inline(heading.group(2))
            if level == 1 and first_heading:
                story.append(
                    HRFlowable(
                        width=68,
                        thickness=4,
                        color=colors.HexColor(ACCENT),
                        hAlign="LEFT",
                        spaceAfter=12,
                    )
                )
                story.append(Paragraph(value, styles["title"]))
                first_heading = False
            else:
                story.append(Paragraph(value, styles["h2" if level == 2 else "h3"]))
            index += 1
            continue
        numbered = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if numbered:
            story.append(
                Paragraph(
                    f"<b>{numbered.group(1)}.</b> {_inline(numbered.group(2))}",
                    styles["number"],
                )
            )
            index += 1
            continue
        if stripped.startswith("- "):
            story.append(Paragraph(_inline(stripped[2:]), styles["bullet"], bulletText="•"))
            index += 1
            continue

        parts = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if not next_line or _starts_block(lines, index):
                break
            parts.append(next_line)
            index += 1
        story.append(Paragraph(_inline(" ".join(parts)), styles["body"]))
    return story


def _table(lines: list[str], *, styles: dict[str, Any], width: float):
    from reportlab.lib import colors
    from reportlab.platypus import LongTable, Paragraph, TableStyle

    parsed = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for position, line in enumerate(lines)
        if position != 1
    ]
    columns = max(len(row) for row in parsed)
    data = []
    for row_index, row in enumerate(parsed):
        style = styles["table_head" if row_index == 0 else "table"]
        padded = [*row, *([""] * (columns - len(row)))]
        data.append([Paragraph(_inline(cell), style) for cell in padded])
    table = LongTable(data, colWidths=[width / columns] * columns, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TABLE_HEAD)),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_index in range(2, len(data), 2):
        commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor(TABLE_ALT)))
    table.setStyle(TableStyle(commands))
    return table


_INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def _inline(value: str) -> str:
    text = _sanitize(value)
    output: list[str] = []
    cursor = 0
    for match in _INLINE.finditer(text):
        output.append(html.escape(text[cursor : match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            output.append(f"<b>{html.escape(token[2:-2])}</b>")
        elif token.startswith("`"):
            output.append(html.escape(token[1:-1]))
        else:
            linked = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", token)
            if linked:
                label, url = linked.groups()
                output.append(
                    f'<link href="{html.escape(url, quote=True)}" color="{ACCENT_DARK}">'
                    f"{html.escape(label)}</link>"
                )
        cursor = match.end()
    output.append(html.escape(text[cursor:]))
    return "".join(output)


def _sanitize(value: str) -> str:
    return (
        value.replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00a0", " ")
    )


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        lines[index].strip().startswith("|")
        and index + 1 < len(lines)
        and bool(re.fullmatch(r"\|?[\s|:\-]+\|?", lines[index + 1].strip()))
    )


def _starts_block(lines: list[str], index: int) -> bool:
    value = lines[index].strip()
    return bool(
        re.match(r"^(#{1,3})\s+", value)
        or re.match(r"^\d+\.\s+", value)
        or value.startswith("- ")
        or _is_table_start(lines, index)
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _short(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."
