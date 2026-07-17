from research_engine.extraction import build_chunks, extract_content


def test_html_extraction_drops_boilerplate_and_preserves_table_rows():
    result = extract_content(
        """
        <html><nav>Account Sign in Privacy Home</nav><main>
        <h1>Memory demand</h1><p>HBM demand grew in the reported quarter.</p>
        <table><tr><th>Vendor</th><th>Product</th></tr>
        <tr><td>Micron</td><td>HBM3E</td></tr></table>
        </main><footer>Terms Cookies Contact</footer></html>
        """,
        content_type="text/html",
        parent_evidence_id="ev-1",
    )

    assert result["content_valid"] is True
    assert "Memory demand" in result["text"]
    assert "Account Sign in" not in result["text"]
    assert result["tables"] == [
        [["Vendor", "Product"], ["Micron", "HBM3E"]]
    ]
    assert result["chunks"][0]["parent_evidence_id"] == "ev-1"


def test_long_content_produces_stable_bounded_chunks():
    blocks = [f"Section {index} " + ("x" * 900) for index in range(8)]

    first = build_chunks(blocks, parent_evidence_id="ev-long", max_chars=2_000)
    second = build_chunks(blocks, parent_evidence_id="ev-long", max_chars=2_000)

    assert len(first) > 1
    assert first == second
    assert all(len(chunk["text"]) <= 2_000 for chunk in first)
    assert len({chunk["chunk_id"] for chunk in first}) == len(first)
    assert all(chunk["content_hash"] for chunk in first)


def test_json_retains_structured_data_and_pdf_adapter_is_explicit():
    json_result = extract_content(
        '{"company":"Micron","revenue":42}',
        content_type="application/json",
        parent_evidence_id="ev-json",
    )
    assert json_result["structured_data"] == {"company": "Micron", "revenue": 42}
    assert "Micron" in json_result["text"]

    pdf_result = extract_content(
        b"%PDF fixture",
        content_type="application/pdf",
        parent_evidence_id="ev-pdf",
        pdf_extractor=lambda body: "Extracted PDF evidence",
    )
    assert pdf_result["content_valid"] is True
    assert pdf_result["text"] == "Extracted PDF evidence"

    failed = extract_content(
        b"%PDF fixture",
        content_type="application/pdf",
        parent_evidence_id="ev-pdf-fail",
        pdf_extractor=lambda body: "",
    )
    assert failed["content_valid"] is False
    assert failed["content_invalid_reasons"] == ["pdf_extraction_failed"]
    assert failed["text"] == ""


def test_oversized_and_binary_content_stays_bounded():
    result = extract_content(
        "z" * 10_000,
        content_type="text/plain",
        parent_evidence_id="ev-large",
        max_bytes=1_000,
        chunk_chars=400,
    )
    assert len(result["text"].encode()) <= 1_000
    assert "content_truncated" in result["warnings"]
    assert all(len(chunk["text"]) <= 400 for chunk in result["chunks"])

    binary = extract_content(
        b"\x00\x01\x02",
        content_type="application/octet-stream",
        parent_evidence_id="ev-bin",
    )
    assert binary["content_valid"] is False
    assert binary["content_invalid_reasons"] == ["unsupported_content_type"]

    empty = extract_content(
        "<html><nav>Only boilerplate</nav></html>",
        content_type="text/html",
        parent_evidence_id="ev-empty",
    )
    assert empty["content_valid"] is False
    assert empty["content_invalid_reasons"] == ["empty_content"]
