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
    assert report["unique_evidence_count"] == 2
    assert report["unique_content_count"] == 2
    assert report["conflict_flags"][0]["flag_id"] == "availability_pressure"
    assert "directional conflict" in " ".join(report["warnings"])


def test_quality_layer_quarantines_invalid_web_content():
    rows = [
        {
            "evidence_id": "ev-invalid",
            "connector": "web_page",
            "title": "Blocked page",
            "url": "https://example.com/blocked",
            "text": "You've been blocked by network security. Please sign in to continue.",
            "http_status": 200,
            "content_type": "text/html",
            "final_url": "https://example.com/blocked",
        }
    ]

    enriched, report = enrich_rows_with_quality(rows, topic="blocked", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is False
    assert enriched[0]["quality_score"] == 0.0
    assert enriched[0]["quality_tier"] == "low"
    assert "blocked_by_network_security" in enriched[0]["content_invalid_reasons"]
    assert report["invalid_evidence_count"] == 1
    assert "excluded from claims" in " ".join(report["warnings"])


def test_quality_layer_detects_generic_sign_in_wall():
    rows = [
        {
            "evidence_id": "ev-login",
            "connector": "web_page",
            "title": "GitHub",
            "url": "https://github.com/login",
            "final_url": "https://github.com/login",
            "http_status": 200,
            "content_type": "text/html",
            "text": "Sign in to GitHub to continue. Username or email address. Password.",
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="login", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is False
    assert "login_wall" in enriched[0]["content_invalid_reasons"]


def test_quality_layer_keeps_legitimate_github_integration_documentation():
    rows = [
        {
            "evidence_id": "ev-github-doc",
            "connector": "web_page",
            "title": "Configure the GitHub integration",
            "url": "https://docs.example.com/github-integration",
            "final_url": "https://docs.example.com/github-integration",
            "http_status": 200,
            "content_type": "text/html",
            "text": (
                "To configure the integration, sign in to GitHub, open organization settings, "
                "create a read-only application, copy its public identifier, and verify the "
                "requested permissions before enabling the integration."
            ),
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="github docs", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is True


def test_quality_layer_keeps_github_documentation_with_credentials_terms():
    rows = [
        {
            "evidence_id": "ev-github-credentials-doc",
            "connector": "web_page",
            "title": "Connect a GitHub account",
            "url": "https://docs.example.com/github-authentication",
            "final_url": "https://docs.example.com/github-authentication",
            "http_status": 200,
            "content_type": "text/html",
            "text": (
                "For a local development account, sign in to GitHub with your username and "
                "password, then open settings and authorize the read-only integration. The "
                "production setup should use an application token instead."
            ),
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="github auth", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is True


def test_quality_layer_matches_complete_login_path_segments_only():
    rows = [
        {
            "evidence_id": "ev-signin-guide",
            "connector": "web_page",
            "title": "GitHub sign-in guide",
            "url": "https://docs.example.com/guides/signin-to-github",
            "final_url": "https://docs.example.com/guides/signin-to-github",
            "http_status": 200,
            "content_type": "text/html",
            "text": (
                "This guide explains how to sign in to GitHub, configure organization access, "
                "review application permissions, and troubleshoot the integration safely."
            ),
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="github guide", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is True


def test_quality_layer_keeps_legitimate_captcha_article():
    rows = [
        {
            "evidence_id": "ev-captcha-article",
            "connector": "web_page",
            "title": "How CAPTCHA systems work",
            "url": "https://example.com/captcha-research",
            "final_url": "https://example.com/captcha-research",
            "http_status": 200,
            "content_type": "text/html",
            "text": (
                "CAPTCHA systems distinguish automated traffic from people. This research article "
                "compares image, audio, behavioral, accessibility, privacy, and security tradeoffs."
            ),
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="captcha", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is True


def test_quality_layer_does_not_apply_web_shell_length_to_external_evidence():
    rows = [
        {
            "evidence_id": "ev-external",
            "connector": "external_jsonl",
            "title": "Quarterly result",
            "url": "https://example.com/result",
            "final_url": "https://example.com/result",
            "text": "Revenue increased 12% year over year.",
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="result", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is True


def test_quality_layer_reports_duplicate_evidence_ids_when_normalization_is_bypassed():
    rows = [
        {"evidence_id": "ev-0001", "connector": "manual", "title": "one", "text": "one"},
        {"evidence_id": "ev-0001", "connector": "manual", "title": "two", "text": "two"},
    ]

    _, report = enrich_rows_with_quality(rows, topic="collision", pack={"id": "demo"})

    assert report["unique_evidence_count"] == 2
    assert report["unique_evidence_id_count"] == 1
    assert report["evidence_id_collision_count"] == 1
    assert "evidence id collision" in " ".join(report["warnings"]).lower()


def test_platform_search_pages_do_not_create_conflict_flags():
    rows = [
        {
            "evidence_id": "ev-0001",
            "connector": "web_page",
            "source_kind": "platform_search_page",
            "title": "Search shell",
            "text": "The query asks whether tight supply or an oversupply glut will prevail.",
        }
    ]

    enriched, report = enrich_rows_with_quality(rows, topic="memory", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is True
    assert enriched[0]["claim_eligible"] is False
    assert report["conflict_flags"] == []
    assert "discovery-only" in " ".join(report["warnings"])


def test_stale_current_evidence_is_observable_but_claim_ineligible():
    rows = [
        {
            "evidence_id": "ev-stale",
            "connector": "web_page",
            "title": "Memory price update",
            "url": "https://example.com/old-memory-price",
            "text": "Memory contract price evidence remains visible for historical review.",
            "freshness_status": "stale",
            "freshness_window_days": 30,
        }
    ]

    enriched, report = enrich_rows_with_quality(
        rows,
        topic="current memory prices",
        pack={"id": "demo"},
        query_plan={
            "queries": [
                {
                    "query_id": "q-1",
                    "facet_id": "pricing",
                    "query": "current memory prices",
                    "required": True,
                }
            ]
        },
    )

    assert enriched[0]["content_valid"] is True
    assert enriched[0]["claim_eligible"] is False
    assert report["claim_ineligible_count"] == 1
    assert "facet_coverage" in report


def test_freshness_required_claims_reject_undated_and_future_dated_evidence():
    rows = [
        {
            "evidence_id": "ev-undated",
            "connector": "manual",
            "title": "Undated current update",
            "text": "Substantive current evidence without a verifiable publication date.",
            "freshness_status": "undated",
            "freshness_window_days": 30,
        },
        {
            "evidence_id": "ev-future",
            "connector": "manual",
            "title": "Future-dated update",
            "text": "Substantive evidence carrying an impossible future publication date.",
            "freshness_status": "future_dated",
            "freshness_window_days": 30,
            "age_days": -1,
        },
        {
            "evidence_id": "ev-negative-age",
            "connector": "manual",
            "title": "Incorrectly marked fresh",
            "text": "Substantive evidence with a negative age despite a fresh status marker.",
            "freshness_status": "fresh",
            "freshness_window_days": 30,
            "age_days": -0.5,
        },
    ]

    enriched, report = enrich_rows_with_quality(rows, topic="current update", pack={"id": "demo"})

    assert [row["claim_eligible"] for row in enriched] == [False, False, False]
    assert report["claim_ineligible_count"] == 3


def test_not_applicable_freshness_remains_claim_eligible():
    rows = [
        {
            "evidence_id": "ev-historical",
            "connector": "manual",
            "title": "Historical record",
            "text": "A dated historical record for a claim without a current-state window.",
            "freshness_status": "not_applicable",
            "freshness_window_days": None,
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="historical record", pack={"id": "demo"})

    assert enriched[0]["claim_eligible"] is True


def test_successfully_extracted_pdf_can_pass_quality_without_allowing_binary():
    rows = [
        {
            "evidence_id": "ev-pdf",
            "connector": "web_page",
            "title": "Extracted report",
            "url": "https://example.com/report.pdf",
            "final_url": "https://example.com/report.pdf",
            "http_status": 200,
            "content_type": "application/pdf",
            "text": (
                "Successfully extracted PDF report with substantive evidence, methods, "
                "results, and limitations for deterministic review."
            ),
            "extracted_content": True,
        }
    ]

    enriched, _ = enrich_rows_with_quality(rows, topic="extracted report", pack={"id": "demo"})

    assert enriched[0]["content_valid"] is True
    assert enriched[0]["claim_eligible"] is True
