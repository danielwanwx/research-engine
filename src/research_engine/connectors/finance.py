"""Public quote connector backed by the Yahoo chart endpoint."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.network_errors import TransientNetworkError, transient_network_reason


class FinanceQuoteConnector:
    connector_id = "finance_quote"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        rows: list[dict] = []
        warnings: list[str] = []
        transient_failures: list[str] = []
        for ticker in (request.source.get("tickers") or [])[: request.max_results]:
            if not isinstance(ticker, dict):
                continue
            symbol = str(ticker.get("symbol") or "")
            if not symbol:
                continue
            try:
                quote = fetch_quote(symbol)
            except Exception as exc:
                reason = transient_network_reason(exc)
                if reason:
                    transient_failures.append(reason)
                    warnings.append(f"finance_quote failed for {symbol}: {reason}")
                else:
                    warnings.append(f"finance_quote failed for {symbol}: {type(exc).__name__}")
                continue
            meta = quote["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            rows.append(
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": f"{ticker.get('name') or symbol} quote",
                    "url": f"https://finance.yahoo.com/quote/{symbol}",
                    "captured_at": utc_now(),
                    "text": f"{symbol} regular market price: {price} {meta.get('currency') or ''}",
                    "metrics": {
                        "symbol": symbol,
                        "name": ticker.get("name") or symbol,
                        "currency": meta.get("currency") or "",
                        "regular_market_price": price,
                        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
                        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
                    },
                    "source_confidence": "medium",
                }
            )
        if not rows and transient_failures:
            raise TransientNetworkError(transient_failures[0])
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=warnings,
        )


def fetch_quote(symbol: str, *, timeout: float = 12.0) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    request = Request(url, headers={"User-Agent": "research-engine/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
