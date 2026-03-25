"""
conftest.py — Shared fixtures for StockGuru agent unit tests
=============================================================
All external I/O (Yahoo Finance, Anthropic, Gemini, NSE APIs,
Telegram, file reads) is mocked so tests run fully offline
and deterministically.
"""

import sys
import os
import json
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

# ── Import path: agents live in stockguru_agents/agents/ ──────────────────────
REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENTS_DIR = os.path.join(REPO_ROOT, "stockguru_agents")
sys.path.insert(0, AGENTS_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# Core shared_state fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def shared_state():
    """
    Minimal shared_state dict seeded with all keys that downstream
    agents typically read from upstream agents.
    """
    return {
        # ── Market Scanner outputs ──────────────────────────────────────────
        "scanner_results": [
            {
                "symbol": "RELIANCE.NS", "name": "Reliance Industries",
                "sector": "Energy", "industry": "Oil & Gas",
                "price": 2800.0, "change": 1.5, "change_pct": 1.5,
                "volume": 1_000_000, "vol_ratio": 2.1, "vol_surge": 2.1,
                "adx": 28.0, "rsi": 62.0, "score": 78,
                "signal": "BUY", "signals": ["Bullish momentum"],
                "tech_score": 75, "above_ema50": True, "macd_bullish": True,
            },
            {
                "symbol": "TCS.NS", "name": "TCS",
                "sector": "Technology", "industry": "IT Services",
                "price": 4100.0, "change": 0.8, "change_pct": 0.8,
                "volume": 500_000, "vol_ratio": 1.4, "vol_surge": 1.4,
                "adx": 22.0, "rsi": 55.0, "score": 65,
                "signal": "WATCH", "signals": ["Volume spike"],
                "tech_score": 60, "above_ema50": True, "macd_bullish": False,
            },
        ],
        "full_scan": [],
        "advance_decline": {"advances": 1200, "declines": 800, "unchanged": 100},
        "scanner_last_run": "01 Mar 09:15",
        "scanner_elapsed": 12.3,

        # ── News Sentiment outputs ─────────────────────────────────────────
        "news_results": [
            {
                "title": "Reliance JIO launches 5G in new cities",
                "source": "Economic Times",
                "sentiment": 0.75,
                "impact": "HIGH",
                "stocks": ["RELIANCE.NS"],
                "summary": "Positive news for Reliance.",
            }
        ],
        "market_sentiment_score": 65.0,
        "news_high_impact": [],
        "stock_sentiment_map": {"RELIANCE.NS": 0.75},
        "news_last_run": "01 Mar 09:16",

        # ── Technical Analysis outputs ────────────────────────────────────
        "technical_data": {
            "RELIANCE.NS": {
                "rsi": 62.0, "macd": 15.2, "macd_signal": 12.1,
                "bb_upper": 2900.0, "bb_lower": 2700.0,
                "sma20": 2780.0, "sma50": 2720.0, "ema9": 2810.0,
                "support": 2750.0, "resistance": 2850.0,
                "trend": "BULLISH", "signals": ["RSI in healthy zone"],
            }
        },
        "technical_last_run": "01 Mar 09:17",

        # ── Trade Signal outputs ──────────────────────────────────────────
        "trade_signals": [
            {
                "symbol": "RELIANCE.NS", "action": "BUY",
                "entry": 2800.0, "target1": 3080.0, "target2": 3360.0,
                "stop_loss": 2576.0, "risk_reward": 2.5,
                "confidence": 82, "score": 78,
                "rationale": ["Bullish momentum", "Volume spike", "RSI healthy"],
                "gates_passed": 6, "gates_total": 8,
            }
        ],
        "actionable_signals": [],
        "signals_last_run": "01 Mar 09:18",

        # ── Commodity outputs ──────────────────────────────────────────────
        # morning_brief expects a list of dicts with "name" key
        "commodity_results": [
            {"name": "Gold", "price": 72000.0, "change": 0.3, "sentiment": "NEUTRAL"},
            {"name": "Crude Oil", "price": 6800.0, "change": -1.1, "sentiment": "BEARISH"},
        ],
        "commodity_sentiment": "NEUTRAL",
        "commodity_last_run": "01 Mar 09:19",

        # ── Institutional Flow outputs ─────────────────────────────────────
        "institutional_flow": {
            "fii_net": -250.0, "dii_net": 400.0,
            "fii_sentiment": "BEARISH", "dii_sentiment": "BULLISH",
            "overall": "MILDLY_BULLISH",
        },
        "delivery_data": {},
        "institutional_last_run": "01 Mar 09:20",

        # ── Claude Intelligence outputs ───────────────────────────────────
        "claude_analysis": {
            "market_view": "CAUTIOUSLY_BULLISH",
            "key_themes": ["FII selling offset by DII buying"],
            "top_picks": ["RELIANCE.NS"],
            "risk_factors": ["Global cues weak"],
            "confidence": 70,
        },

        # ── Web Research outputs ──────────────────────────────────────────
        "web_research": {
            "RELIANCE.NS": ["Reliance 5G expansion bullish for stock"],
        },
        "web_research_last": "01 Mar 09:21",

        # ── Sector Rotation outputs ───────────────────────────────────────
        "sector_rotation": {
            "top_sectors": ["IT", "Energy"],
            "bottom_sectors": ["Metals", "PSU Banks"],
            "rotation_signal": "RISK_ON",
        },

        # ── Risk Manager outputs ──────────────────────────────────────────
        "risk_reviewed_signals": [],
        "risk_summary": {"total": 1, "approved": 1, "rejected": 0},

        # ── Paper Portfolio ───────────────────────────────────────────────
        # Structure matches paper_trader._load_portfolio() defaults exactly
        "paper_portfolio": {
            "capital":          500_000.0,
            "available_cash":   500_000.0,
            "invested":         0.0,
            "unrealized_pnl":   0.0,
            "realized_pnl":     0.0,
            "total_pnl":        0.0,
            "total_return_pct": 0.0,
            "positions":        {},
            "daily_pnl":        {},
            "daily_pnl_pct":    0.0,
            "stats": {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
                "best_trade": None, "worst_trade": None, "max_drawdown": 0.0,
            },
        },

        # ── Options Flow outputs ──────────────────────────────────────────
        # claude_intelligence expects dicts with .get() for these
        "india_vix": {"level": 14.5, "regime": "LOW", "alert": ""},
        "options_flow": {
            "pcr": 1.1, "max_pain": 22000, "sentiment": "NEUTRAL",
            "total_call_oi": 5_000_000, "total_put_oi": 5_500_000,
        },
        "iv_rank": {
            "nifty_ivr": 35.0, "iv_regime": "NORMAL",
            "strategy_bias": "BALANCED", "nifty_iv_pct": 14.5,
        },

        # ── Events Calendar outputs ───────────────────────────────────────
        "events_calendar": {
            "today_events": [],
            "upcoming_earnings": [],
        },

        # ── Pattern Memory outputs ────────────────────────────────────────
        "pattern_library": [],

        # ── Agent status / confidence tracking ────────────────────────────
        "agent_status": {},
        "agent_confidence": {},

        # ── Misc ──────────────────────────────────────────────────────────
        "last_cycle_time": "01 Mar 09:00",
        "last_morning_brief": None,
        "accuracy_stats": {
            "total_trades": 20, "winning_trades": 12,
            "win_rate": 60.0, "avg_return": 3.2,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Yahoo Finance / yfinance mock helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_yf_ticker(symbol="RELIANCE.NS", price=2800.0, volume=1_000_000,
                   change_pct=1.5):
    """Return a mock yfinance Ticker object with realistic fast_info."""
    ticker = MagicMock()
    ticker.fast_info.last_price   = price
    ticker.fast_info.last_volume  = volume
    ticker.fast_info.previous_close = price / (1 + change_pct / 100)
    # info dict
    ticker.info = {
        "symbol": symbol, "shortName": symbol.split(".")[0],
        "regularMarketPrice": price,
        "regularMarketChangePercent": change_pct,
        "regularMarketVolume": volume,
        "averageVolume": volume // 2,
        "fiftyDayAverage": price * 0.97,
        "twoHundredDayAverage": price * 0.93,
        "beta": 1.1,
    }
    # history() → small DataFrame
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    prices = [price * (1 + 0.001 * i) for i in range(60)]
    ticker.history.return_value = pd.DataFrame({
        "Open":   prices,
        "High":   [p * 1.01 for p in prices],
        "Low":    [p * 0.99 for p in prices],
        "Close":  prices,
        "Volume": [volume] * 60,
    }, index=dates)
    return ticker


@pytest.fixture
def mock_yf_ticker():
    return make_yf_ticker()


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic mock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_anthropic_response():
    """Stub Anthropic client that returns a canned text response."""
    client = MagicMock()
    msg    = MagicMock()
    msg.content = [MagicMock(text=json.dumps({
        "market_view": "CAUTIOUSLY_BULLISH",
        "key_themes": ["FII selling offset by DII buying"],
        "top_picks": ["RELIANCE.NS"],
        "risk_factors": ["Global cues weak"],
        "confidence": 72,
    }))]
    client.messages.create.return_value = msg
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Gemini mock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_gemini_response():
    """Stub Gemini GenerativeModel that returns a canned text."""
    model    = MagicMock()
    response = MagicMock()
    response.text = "RELIANCE.NS looks bullish based on 5G expansion news."
    model.generate_content.return_value = response
    return model


# ─────────────────────────────────────────────────────────────────────────────
# requests.get mock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_requests_get():
    """Generic requests.get mock returning 200 with empty JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {}
    resp.text = ""
    resp.raise_for_status.return_value = None
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Telegram mock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_telegram_fn():
    """Mock send_telegram_fn for morning_brief."""
    return MagicMock(return_value=True)


@pytest.fixture
def mock_n8n_fn():
    """Mock send_n8n_fn for morning_brief."""
    return MagicMock(return_value=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data-file helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_data_dir(tmp_path):
    """
    Create a temporary /data/ directory seeded with the JSON files
    that agents read/write (paper_portfolio, accuracy_stats, etc.).
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    (data_dir / "paper_portfolio.json").write_text(json.dumps({
        "capital": 500_000.0, "available_cash": 500_000.0,
        "invested": 0.0, "positions": {},
        "unrealized_pnl": 0.0, "realized_pnl": 0.0,
        "total_pnl": 0.0, "total_return_pct": 0.0,
        "daily_pnl": {}, "daily_pnl_pct": 0.0,
        "stats": {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "best_trade": None, "worst_trade": None, "max_drawdown": 0.0,
        },
    }))
    (data_dir / "accuracy_stats.json").write_text(json.dumps({
        "total_trades": 20, "winning_trades": 12,
        "win_rate": 60.0, "avg_return": 3.2,
    }))
    (data_dir / "signal_history.json").write_text(json.dumps([]))
    (data_dir / "pattern_library.json").write_text(json.dumps([]))
    (data_dir / "paper_trades.json").write_text(json.dumps([]))
    return str(data_dir)


@pytest.fixture
def patched_file_paths(tmp_data_dir):
    """
    Patch the module-level file path constants used by agents that read/write
    JSON files under <project>/data/.  Agents compute these at import time
    from _BASE (project root), so we override the constants directly.
    """
    data_dir  = tmp_data_dir
    portfolio = os.path.join(data_dir, "paper_portfolio.json")
    trades    = os.path.join(data_dir, "paper_trades.json")
    history   = os.path.join(data_dir, "signal_history.json")
    patterns  = os.path.join(data_dir, "pattern_library.json")

    with patch("agents.paper_trader.PORTFOLIO_FILE", portfolio), \
         patch("agents.paper_trader.TRADES_FILE",    trades), \
         patch("agents.pattern_memory.HISTORY_FILE", history), \
         patch("agents.pattern_memory.PATTERN_FILE", patterns):
        yield data_dir
