import json

from pypdf import PdfReader

from research_engine.pdf_report import _styles, render_pdf_report


def test_pdf_report_renders_chinese_tables_links_and_metadata(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps(
            {
                "topic": "美国后端工程师就业市场",
                "as_of": "2026-07-16",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "research_report.md").write_text(
        """# Research Report: 美国后端工程师就业市场

## Executive Summary

市场正在温和修复，但仍低于疫情前水平。

| Metric | Count |
|---|---:|
| Active openings | 12 |

## Evidence

- [Federal Reserve data](https://fred.stlouisfed.org/) - quality `high`
""",
        encoding="utf-8",
    )

    status = render_pdf_report(tmp_path)

    assert status["status"] == "generated", status
    assert status["page_count"] >= 1
    assert (tmp_path / "research_report.pdf").read_bytes().startswith(b"%PDF")
    reader = PdfReader(tmp_path / "research_report.pdf")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "美国后端工程师就业市场" in text
    assert "Active openings" in text
    links = [
        annotation.get_object().get("/A", {}).get("/URI")
        for page in reader.pages
        for annotation in page.get("/Annots", [])
    ]
    assert "https://fred.stlouisfed.org/" in links
    font_names = {
        str(font.get_object().get("/BaseFont") or "")
        for page in reader.pages
        for font in page["/Resources"]["/Font"].get_object().values()
    }
    assert not any("Helvetica" in name for name in font_names)


def test_pdf_typography_uses_one_body_scale():
    styles = _styles("UnifiedBody", "UnifiedBold")

    for name in ("body", "bullet", "number"):
        assert styles[name].fontName == "UnifiedBody"
        assert styles[name].fontSize == 9.5
        assert styles[name].leading == 14.5
    assert styles["bullet"].bulletFontName == "UnifiedBody"
    assert styles["bullet"].bulletFontSize == 9.5
