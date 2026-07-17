from research_engine.freshness import (
    enrich_row_freshness,
    extract_published_date,
    extract_temporal_metadata,
)


def test_date_extraction_follows_structured_precedence():
    row = {
        "published_at": "2026-07-12T10:00:00Z",
        "url": "https://example.com/2026/07/01/report",
        "raw_html": """
            <script type="application/ld+json">{"datePublished":"2026-07-10"}</script>
            <meta property="article:published_time" content="2026-07-09">
            <time datetime="2026-07-08">July 8</time>
        """,
    }

    assert extract_published_date(row) == {
        "published_at": "2026-07-12",
        "date_source": "connector_native",
        "date_confidence": "high",
    }


def test_date_extraction_falls_back_from_jsonld_to_meta_time_and_url():
    cases = [
        (
            {"raw_html": '<script type="application/ld+json">'
            '{"@type":"NewsArticle","datePublished":"2026-07-10"}</script>'},
            ("2026-07-10", "json_ld", "high"),
        ),
        (
            {"raw_html": '<meta property="article:published_time" content="2026-07-09">'},
            ("2026-07-09", "html_meta", "high"),
        ),
        (
            {"raw_html": '<time datetime="2026-07-08T12:00:00Z">July 8</time>'},
            ("2026-07-08", "time_element", "medium"),
        ),
        (
            {"url": "https://example.com/archive/2026/07/07/report"},
            ("2026-07-07", "url_pattern", "low"),
        ),
    ]

    for row, expected in cases:
        result = extract_published_date(row)
        assert tuple(result.values()) == expected


def test_malformed_and_ambiguous_dates_remain_undated():
    row = {
        "published_at": "07/08/26",
        "raw_html": '<time datetime="yesterday">Yesterday</time>',
        "url": "https://example.com/2026/99/99/report",
    }

    assert extract_published_date(row) == {
        "published_at": "",
        "date_source": "",
        "date_confidence": "",
    }


def test_temporal_metadata_keeps_published_updated_and_observed_dates_distinct():
    result = extract_temporal_metadata(
        {
            "raw_html": """
                <script type="application/ld+json">
                  {"datePublished":"2025-01-02","dateModified":"2026-07-15"}
                </script>
            """,
            "tables": [
                [["DATE", "VALUE"], ["2026-07-09", "73.9"], ["2026-07-10", "74.56"]]
            ],
        }
    )

    assert result["published_at"] == "2025-01-02"
    assert result["updated_at"] == "2026-07-15"
    assert result["observed_at"] == "2026-07-10"
    assert result["observed_date_source"] == "table_observation"


def test_data_series_freshness_uses_latest_observation_before_publication_age():
    result = enrich_row_freshness(
        {
            "published_at": "2020-01-01",
            "updated_at": "2026-07-15",
            "tables": [[["2026-07-10", "74.56"]]],
        },
        as_of="2026-07-16",
        window_days=30,
    )

    assert result["freshness_status"] == "fresh"
    assert result["freshness_date_field"] == "observed_at"
    assert result["age_days"] == 6


def test_freshness_boundary_and_statuses_are_explicit():
    assert enrich_row_freshness(
        {"published_at": "2026-06-16"}, as_of="2026-07-16", window_days=30
    )["freshness_status"] == "fresh"
    stale = enrich_row_freshness(
        {"published_at": "2026-06-15"}, as_of="2026-07-16", window_days=30
    )
    assert stale["freshness_status"] == "stale"
    assert stale["age_days"] == 31
    assert enrich_row_freshness({}, as_of="2026-07-16", window_days=30)[
        "freshness_status"
    ] == "undated"
    assert enrich_row_freshness(
        {"published_at": "2020-01-01"}, as_of="2026-07-16", window_days=None
    )["freshness_status"] == "not_applicable"


def test_future_publication_date_is_never_fresh():
    result = enrich_row_freshness(
        {"published_at": "2026-07-17"},
        as_of="2026-07-16",
        window_days=30,
    )

    assert result["freshness_status"] == "future_dated"
    assert result["age_days"] == -1
    assert result["freshness_window_days"] == 30


def test_not_applicable_freshness_preserves_historical_semantics():
    result = enrich_row_freshness(
        {"published_at": "2030-01-01"},
        as_of="2026-07-16",
        window_days=None,
    )

    assert result["freshness_status"] == "not_applicable"
    assert result["age_days"] is None
    assert result["freshness_window_days"] is None
