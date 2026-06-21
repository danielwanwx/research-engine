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
