from research_engine.quality import enrich_rows_with_quality


def test_quality_layer_scores_duplicates_and_conflicts():
    rows = [
        {
            "evidence_id": "ev-0001",
            "connector": "web_page",
            "title": "Supply tight",
            "url": "https://example.com/report?utm_source=x",
            "text": "Tight supply and strong demand are pushing prices higher.",
            "source_confidence": "high",
        },
        {
            "evidence_id": "ev-0002",
            "connector": "web_page",
            "title": "Supply tight duplicate",
            "url": "https://example.com/report#section",
            "text": "Tight supply and strong demand are pushing prices higher.",
        },
        {
            "evidence_id": "ev-0003",
            "connector": "manual",
            "title": "Opposing channel check",
            "text": "Some buyers report excess inventory and weak demand.",
        },
    ]

    enriched, report = enrich_rows_with_quality(rows, topic="market research", pack={"id": "demo"})

    assert enriched[0]["quality_tier"] == "high"
    assert enriched[1]["duplicate_cluster_id"] == enriched[0]["duplicate_cluster_id"]
    assert enriched[1]["is_duplicate"] is True
    assert report["duplicate_cluster_count"] == 1
    assert report["conflict_flags"][0]["flag_id"] == "availability_pressure"
    assert "directional conflict" in " ".join(report["warnings"])
