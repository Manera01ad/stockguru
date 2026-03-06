"""
test_integration.py — Full 15-minute cycle integration test
============================================================
Simulates one complete StockGuru cycle running all agents in order,
using mocked external APIs.  Verifies that:
  1. Each agent writes its expected keys to shared_state
  2. Downstream agents read upstream keys without KeyError
  3. The final state contains all keys the dashboard needs
  4. paper_portfolio cash never goes negative
  5. No uncaught exceptions propagate

Run with:
    pytest tests/test_integration.py -v
"""

import sys
import os
import json
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, call
from datetime import datetime

# ── Import path set by conftest.py ────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers (local to this module)
# ─────────────────────────────────────────────────────────────────────────────

SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS",
    "HDFCBANK.NS", "ICICIBANK.NS",
]


def make_price_series(base=2800.0, periods=60):
    dates  = pd.date_range("2024-01-01", periods=periods, freq="B")
    prices = [base * (1 + 0.001 * i) for i in range(periods)]
    return pd.DataFrame({
        "Open":   prices,
        "High":   [p * 1.005 for p in prices],
        "Low":    [p * 0.995 for p in prices],
        "Close":  prices,
        "Volume": [1_000_000] * periods,
    }, index=dates)


def make_yf_ticker(symbol="RELIANCE.NS", price=2800.0, volume=1_000_000):
    ticker = MagicMock()
    ticker.fast_info.last_price    = price
    ticker.fast_info.last_volume   = volume
    ticker.fast_info.previous_close = price * 0.985
    ticker.history.return_value = make_price_series(base=price)
    ticker.info = {
        "shortName": symbol.split(".")[0],
        "regularMarketPrice": price,
        "regularMarketChangePercent": 1.5,
        "regularMarketVolume": volume,
        "averageVolume": volume // 2,
        "fiftyDayAverage": price * 0.97,
        "twoHundredDayAverage": price * 0.93,
    }
    return ticker


def make_rss_xml(title="Reliance 5G expansion bullish"):
    return f"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>{title}</title>
        <description>Strong growth expected in Indian markets</description>
        <pubDate>Mon, 01 Mar 2026 09:00:00 +0530</pubDate>
      </item>
    </channel></rss>"""


def make_anthropic_client():
    client = MagicMock()
    msg    = MagicMock()
    msg.content = [MagicMock(text=json.dumps({
        "market_view": "CAUTIOUSLY_BULLISH",
        "key_themes": ["FII selling offset by DII buying", "Tech rally"],
        "top_picks": ["TCS.NS", "RELIANCE.NS"],
        "risk_factors": ["Global cues weak", "Dollar strength"],
        "confidence": 72,
    }))]
    client.messages.create.return_value = msg
    return client


def make_nse_response(data=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data or {}
    resp.text = ""
    resp.raise_for_status.return_value = None
    return resp


def requests_get_router(url, *args, **kwargs):
    """Route requests.get to appropriate mock based on URL."""
    url_lower = url.lower()

    # RSS / news feeds
    if any(x in url_lower for x in ["rss", "feed", "news", "economictimes",
                                     "moneycontrol", "business-standard"]):
        r = MagicMock()
        r.status_code = 200
        r.text = make_rss_xml()
        return r

    # NSE VIX
    if "vix" in url_lower or "indices" in url_lower:
        return make_nse_response({"data": [
            {"index": "INDIA VIX", "last": 14.5, "variation": -0.3}
        ]})

    # NSE option chain
    if "option" in url_lower or "optionchain" in url_lower:
        return make_nse_response({
            "records": {
                "underlyingValue": 22100.0,
                "expiryDates": ["27-Mar-2026"],
                "data": [{
                    "strikePrice": 22000,
                    "expiryDate": "27-Mar-2026",
                    "CE": {"openInterest": 50000, "changeinOpenInterest": 5000,
                           "totalTradedVolume": 100000, "impliedVolatility": 15.5,
                           "lastPrice": 200.0},
                    "PE": {"openInterest": 60000, "changeinOpenInterest": -2000,
                           "totalTradedVolume": 90000, "impliedVolatility": 16.0,
                           "lastPrice": 180.0},
                }],
            }
        })

    # NSE FII/DII flow
    if "fii" in url_lower or "institutional" in url_lower or "participant" in url_lower:
        return make_nse_response({"data": [
            {"buyValue": "5000.00", "sellValue": "4750.00",
             "category": "FII/FPI", "date": "01-Mar-2026"},
            {"buyValue": "3000.00", "sellValue": "2600.00",
             "category": "DII", "date": "01-Mar-2026"},
        ]})

    # NSE corporate actions / earnings
    if "corporate" in url_lower or "calendar" in url_lower or "event" in url_lower:
        return make_nse_response({"data": [
            {"symbol": "RELIANCE", "companyName": "Reliance Industries",
             "bMeetingDate": "15-Mar-2026", "purpose": "Quarterly Results"}
        ]})

    # DuckDuckGo search
    if "duckduckgo" in url_lower or "api.dg" in url_lower:
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {
            "AbstractText": "Indian markets showing bullish momentum.",
            "RelatedTopics": [],
        }
        return r

    # Default: empty 200
    return make_nse_response({})


# ─────────────────────────────────────────────────────────────────────────────
# Integration test
# ─────────────────────────────────────────────────────────────────────────────

class TestFullCycle:

    def test_full_cycle_all_keys_written(self, tmp_data_dir):
        """
        Run all agents in cycle order.  Verify every expected shared_state
        key is populated after the cycle completes.
        """
        from agents import (
            market_scanner, news_sentiment, technical_analysis,
            commodity_crypto, institutional_flow, claude_intelligence,
            web_researcher, trade_signal, sector_rotation, risk_manager,
            morning_brief, paper_trader, pattern_memory,
            earnings_calendar, options_flow,
        )

        shared_state = {}
        fake_ticker  = make_yf_ticker()
        fake_gemini  = MagicMock()
        fake_gemini.generate_content.return_value.text = "Bullish outlook."
        fake_telegram = MagicMock(return_value=True)

        data_dir   = tmp_data_dir
        portfolio  = os.path.join(data_dir, "paper_portfolio.json")
        trades     = os.path.join(data_dir, "paper_trades.json")
        history    = os.path.join(data_dir, "signal_history.json")
        patterns   = os.path.join(data_dir, "pattern_library.json")

        with patch("yfinance.Ticker", return_value=fake_ticker), \
             patch("requests.get",    side_effect=requests_get_router), \
             patch("anthropic.Anthropic", return_value=make_anthropic_client()), \
             patch("google.generativeai.GenerativeModel", return_value=fake_gemini), \
             patch.dict(os.environ, {
                 "ANTHROPIC_API_KEY": "sk-ant-test",
                 "GEMINI_API_KEY":    "fake-gemini-key",
             }), \
             patch("agents.paper_trader.PORTFOLIO_FILE", portfolio), \
             patch("agents.paper_trader.TRADES_FILE",    trades), \
             patch("agents.pattern_memory.HISTORY_FILE", history), \
             patch("agents.pattern_memory.PATTERN_FILE", patterns), \
             patch("agents.claude_intelligence._BASE",   os.path.dirname(data_dir)), \
             patch("agents.risk_manager._BASE",          os.path.dirname(data_dir)):

            # ── Tier 1: Data agents ───────────────────────────────────────
            market_scanner.run(shared_state)
            news_sentiment.run(shared_state)
            technical_analysis.run(shared_state)
            commodity_crypto.run(shared_state)
            institutional_flow.run(shared_state)
            earnings_calendar.run(shared_state)
            options_flow.run(shared_state)

            # ── Tier 2: Intelligence ─────────────────────────────────────
            claude_intelligence.run(shared_state)
            web_researcher.run(shared_state)

            # ── Tier 3: Strategy ─────────────────────────────────────────
            trade_signal.run(shared_state)
            sector_rotation.run(shared_state)
            risk_manager.run(shared_state)

            # ── Tier 4: Output / Learning ────────────────────────────────
            morning_brief.run(shared_state, fake_telegram, force=True)
            paper_trader.run(shared_state)
            pattern_memory.run(shared_state)

        # ── Assert all critical keys present ─────────────────────────────
        required_keys = [
            "scanner_results",
            "market_sentiment_score",
            "technical_data",
            "commodity_results",
            "institutional_flow",
            "events_calendar",
            "india_vix",
            "options_flow",
            "claude_analysis",
            "web_research",
            "trade_signals",
            "sector_rotation",
            "risk_reviewed_signals",
            "paper_portfolio",
            "pattern_library",
        ]

        missing = [k for k in required_keys if k not in shared_state]
        assert not missing, f"Missing keys after full cycle: {missing}"

    def test_paper_portfolio_cash_non_negative(self, tmp_data_dir):
        """Cash in paper_portfolio must never go negative after a cycle."""
        from agents import (
            market_scanner, trade_signal, risk_manager, paper_trader,
        )

        shared_state = {}
        fake_ticker  = make_yf_ticker()
        data_dir     = tmp_data_dir
        portfolio    = os.path.join(data_dir, "paper_portfolio.json")
        trades       = os.path.join(data_dir, "paper_trades.json")

        with patch("yfinance.Ticker", return_value=fake_ticker), \
             patch("requests.get",    side_effect=requests_get_router), \
             patch("agents.risk_manager._BASE",       os.path.dirname(data_dir)), \
             patch("agents.paper_trader.PORTFOLIO_FILE", portfolio), \
             patch("agents.paper_trader.TRADES_FILE",    trades):

            market_scanner.run(shared_state)
            trade_signal.run(shared_state)
            risk_manager.run(shared_state)
            paper_trader.run(shared_state)

        portfolio_val = shared_state.get("paper_portfolio", {})
        cash = portfolio_val.get("cash", 100_000)
        assert cash >= 0, f"Paper portfolio cash went negative: {cash}"

    def test_cycle_idempotent(self, tmp_data_dir):
        """Running the cycle twice should not raise or corrupt state."""
        from agents import market_scanner, trade_signal, risk_manager

        shared_state = {}
        fake_ticker  = make_yf_ticker()
        data_dir     = tmp_data_dir

        with patch("yfinance.Ticker", return_value=fake_ticker), \
             patch("requests.get",    side_effect=requests_get_router), \
             patch("agents.risk_manager._BASE", os.path.dirname(data_dir)):

            # First run
            market_scanner.run(shared_state)
            trade_signal.run(shared_state)
            risk_manager.run(shared_state)

            first_scanner_count = len(shared_state.get("scanner_results", []))

            # Second run (simulates next 15-min tick)
            market_scanner.run(shared_state)
            trade_signal.run(shared_state)
            risk_manager.run(shared_state)

        assert "scanner_results"       in shared_state
        assert "trade_signals"         in shared_state
        assert "risk_reviewed_signals" in shared_state

    def test_dashboard_keys_available(self, tmp_data_dir):
        """
        The dashboard API (/api/state) returns shared_state directly.
        Verify all keys the frontend index.html references are present.
        """
        from agents import (
            market_scanner, news_sentiment, trade_signal,
            risk_manager, paper_trader,
        )

        shared_state = {}
        fake_ticker  = make_yf_ticker()
        data_dir     = tmp_data_dir
        portfolio    = os.path.join(data_dir, "paper_portfolio.json")
        trades       = os.path.join(data_dir, "paper_trades.json")

        with patch("yfinance.Ticker", return_value=fake_ticker), \
             patch("requests.get",    side_effect=requests_get_router), \
             patch("agents.risk_manager._BASE",       os.path.dirname(data_dir)), \
             patch("agents.paper_trader.PORTFOLIO_FILE", portfolio), \
             patch("agents.paper_trader.TRADES_FILE",    trades):

            market_scanner.run(shared_state)
            news_sentiment.run(shared_state)
            trade_signal.run(shared_state)
            risk_manager.run(shared_state)
            paper_trader.run(shared_state)

        # Keys the dashboard JS reads
        dashboard_keys = [
            "scanner_results",
            "trade_signals",
            "paper_portfolio",
            "market_sentiment_score",
            "risk_reviewed_signals",
        ]

        for key in dashboard_keys:
            assert key in shared_state, \
                f"Dashboard key '{key}' missing from shared_state"
