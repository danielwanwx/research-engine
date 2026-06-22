import json

from research_engine.connectors.external import ExternalJsonlConnector
from research_engine.connectors.finance import FinanceQuoteConnector
from research_engine.connectors.web import WebPageConnector
from research_engine.models import CollectionRequest


def test_web_connector_turns_timeout_into_warning(monkeypatch):
    def timeout_fetch(url):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr("research_engine.connectors.web.fetch_text", timeout_fetch)
    result = WebPageConnector().collect(
        CollectionRequest(
            source={
                "source_id": "web_seed_pages",
                "pages": [{"url": "https://example.com/slow", "title": "Slow page"}],
            },
            topic="slow page research",
            run_date="2026-06-21",
            depth="quick",
            max_results=3,
        )
    )

    assert result.rows == []
    assert "simulated timeout" in result.warnings[0]


def test_finance_connector_turns_timeout_into_warning(monkeypatch):
    def timeout_quote(symbol):
        raise TimeoutError("simulated quote timeout")

    monkeypatch.setattr("research_engine.connectors.finance.fetch_quote", timeout_quote)
    result = FinanceQuoteConnector().collect(
        CollectionRequest(
            source={
                "source_id": "finance_quote_watchlist",
                "tickers": [{"symbol": "MU", "name": "Micron Technology"}],
            },
            topic="quote research",
            run_date="2026-06-21",
            depth="quick",
            max_results=3,
        )
    )

    assert result.rows == []
    assert "simulated quote timeout" in result.warnings[0]


def test_external_jsonl_connector_imports_logged_in_rows(tmp_path):
    evidence_path = tmp_path / "logged_in.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "title": "Lenny memory discussion",
                "url": "https://www.lennysnewsletter.com/p/memory",
                "text": "Subscriber-visible notes say HBM supply remains tight.",
                "metadata": {"platform": "lenny"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = ExternalJsonlConnector().collect(
        CollectionRequest(
            source={
                "source_id": "external_evidence_jsonl",
                "paths": [str(evidence_path)],
            },
            topic="memory research",
            run_date="2026-06-21",
            depth="quick",
            max_results=3,
        )
    )

    assert result.warnings == []
    assert result.rows[0]["connector"] == "external_jsonl"
    assert result.rows[0]["platform"] == "lenny"
    assert result.rows[0]["access_mode"] == "external_authorized_capture"
