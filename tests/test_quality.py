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


def test_discovery_refetch_lineage_does_not_create_duplicate_pressure():
    url = "https://jobs.example.com/jobs/123"
    rows = [
        {
            "evidence_id": "ev-discovery",
            "connector": "xai_discovery",
            "title": "xAI cited candidate",
            "url": url,
            "text": "",
            "source_class": "discovery_only",
            "claim_fitness": {"disposition": "discovery_only"},
        },
        {
            "evidence_id": "ev-final",
            "connector": "web_page",
            "title": "Staff Backend Engineer",
            "url": url,
            "text": "Current official job description with substantive role details.",
            "source_class": "official_jd",
            "is_final_page": True,
            "claim_fitness": {"disposition": "accepted"},
        },
    ]

    enriched, report = enrich_rows_with_quality(rows, topic="target research")

    assert [row["evidence_id"] for row in enriched] == ["ev-discovery", "ev-final"]
    assert all(row["duplicate_cluster_id"] is None for row in enriched)
    assert all(row["is_duplicate"] is False for row in enriched)
    assert report["duplicate_cluster_count"] == 0
    assert report["duplicate_clusters"] == []
    assert not any("duplicate evidence" in warning for warning in report["warnings"])


def test_discovery_rows_do_not_mask_real_final_page_duplicates():
    url = "https://jobs.example.com/jobs/123"
    rows = [
        {
            "evidence_id": "ev-discovery",
            "connector": "xai_discovery",
            "url": url,
            "source_class": "discovery_only",
        },
        {
            "evidence_id": "ev-final-1",
            "connector": "web_page",
            "url": url,
            "source_class": "official_jd",
            "is_final_page": True,
        },
        {
            "evidence_id": "ev-final-2",
            "connector": "web_page",
            "url": url,
            "source_class": "official_jd",
            "is_final_page": True,
        },
    ]

    enriched, report = enrich_rows_with_quality(rows, topic="target research")

    cluster = report["duplicate_clusters"][0]
    assert cluster["evidence_ids"] == ["ev-final-1", "ev-final-2"]
    assert report["duplicate_cluster_count"] == 1
    assert enriched[0]["duplicate_cluster_id"] is None
    assert enriched[0]["is_duplicate"] is False
