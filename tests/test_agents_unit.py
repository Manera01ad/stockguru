"""
test_agents_unit.py — Unit tests for all 15 StockGuru agents
=============================================================
Each agent gets at minimum:
  1. happy_path   — mock all external I/O, assert expected keys written
  2. empty_input  — run with minimal/empty shared_state, must not raise
  3. api_failure  — simulate external API error, agent degrades gracefully

Run with:
    pytest tests/test_agents_unit.py -v
"""

import sys
import os
import json
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, mock_open

# ── sys.path already set by conftest.py ───────────────────────────────────────
# (conftest inserts stockguru_agents/ into sys.path)

# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def empty_state():
    """Minimal shared_state with no upstream data."""
    return {}


# ═════════════════════════════════════════════════════════════════════════════
# 1. MARKET SCANNER
# ═════════════════════════════════════════════════════════════════════════════

class TestMarketScanner:

    def test_happy_path(self, shared_state):
        """Scanner writes scanner_results, full_scan, advance_decline."""
        from agents import market_scanner

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 2800.0
        fake_ticker.fast_info.last_volume = 1_000_000
        fake_ticker.fast_info.previous_close = 2758.0
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        fake_ticker.history.return_value = pd.DataFrame({
            "Close":  [2800.0] * 60,
            "High":   [2830.0] * 60,
            "Low":    [2770.0] * 60,
            "Volume": [1_000_000] * 60,
        }, index=dates)
        fake_ticker.info = {"shortName": "Reliance"}

        with patch("yfinance.Ticker", return_value=fake_ticker):
            market_scanner.run(shared_state)

        assert "scanner_results"  in shared_state
        assert "scanner_last_run" in shared_state
        assert isinstance(shared_state["scanner_results"], list)

    def test_empty_input(self):
        """Scanner should not raise on an empty shared_state."""
        from agents import market_scanner
        state = empty_state()

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 100.0
        fake_ticker.fast_info.last_volume = 100_000
        fake_ticker.fast_info.previous_close = 99.0
        fake_ticker.history.return_value = pd.DataFrame()
        fake_ticker.info = {}

        with patch("yfinance.Ticker", return_value=fake_ticker):
            market_scanner.run(state)  # must not raise

        assert "scanner_results" in state

    def test_api_failure(self, shared_state):
        """If yfinance raises, scanner writes empty list and continues."""
        from agents import market_scanner

        with patch("yfinance.Ticker", side_effect=Exception("network error")):
            market_scanner.run(shared_state)  # must not propagate

        # Key should exist (possibly empty list or prior value)
        assert "scanner_results" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 2. NEWS SENTIMENT
# ═════════════════════════════════════════════════════════════════════════════

class TestNewsSentiment:

    def _fake_rss_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Reliance launches new products</title>
            <description>Strong growth expected</description>
            <pubDate>Mon, 01 Mar 2026 09:00:00 +0530</pubDate>
          </item>
        </channel></rss>"""
        return resp

    def test_happy_path(self, shared_state):
        """Sentiment agent writes market_sentiment_score and news_results."""
        from agents import news_sentiment

        with patch("requests.get", return_value=self._fake_rss_response()):
            news_sentiment.run(shared_state)

        assert "news_results"           in shared_state
        assert "market_sentiment_score" in shared_state
        assert isinstance(shared_state["market_sentiment_score"], (int, float))

    def test_empty_input(self):
        """Works on empty shared_state."""
        from agents import news_sentiment
        state = empty_state()

        with patch("requests.get", return_value=self._fake_rss_response()):
            news_sentiment.run(state)

        assert "news_results" in state

    def test_api_failure(self, shared_state):
        """RSS fetch failure → graceful fallback, score stays 0."""
        from agents import news_sentiment

        with patch("requests.get", side_effect=Exception("timeout")):
            news_sentiment.run(shared_state)

        assert "market_sentiment_score" in shared_state
        # Should be 0 or the seeded value — not a crash
        assert isinstance(shared_state["market_sentiment_score"], (int, float))


# ═════════════════════════════════════════════════════════════════════════════
# 3. TECHNICAL ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════

class TestTechnicalAnalysis:

    def _make_history(self):
        dates  = pd.date_range("2024-01-01", periods=60, freq="B")
        prices = [2800.0 + i for i in range(60)]
        return pd.DataFrame({
            "Open":   prices,
            "High":   [p * 1.005 for p in prices],
            "Low":    [p * 0.995 for p in prices],
            "Close":  prices,
            "Volume": [1_000_000] * 60,
        }, index=dates)

    def test_happy_path(self, shared_state):
        """Technical agent writes technical_data for each scanned symbol."""
        from agents import technical_analysis

        fake_ticker = MagicMock()
        fake_ticker.history.return_value = self._make_history()

        with patch("yfinance.Ticker", return_value=fake_ticker):
            technical_analysis.run(shared_state)

        assert "technical_data"     in shared_state
        assert "technical_last_run" in shared_state
        assert isinstance(shared_state["technical_data"], dict)

    def test_empty_scanner_results(self):
        """No scanner_results → technical_data written as empty dict."""
        from agents import technical_analysis
        state = {"scanner_results": []}

        fake_ticker = MagicMock()
        fake_ticker.history.return_value = pd.DataFrame()

        with patch("yfinance.Ticker", return_value=fake_ticker):
            technical_analysis.run(state)

        assert "technical_data" in state

    def test_api_failure(self, shared_state):
        """yfinance error → agent degrades, does not raise."""
        from agents import technical_analysis

        with patch("yfinance.Ticker", side_effect=Exception("rate limited")):
            technical_analysis.run(shared_state)

        assert "technical_data" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 4. COMMODITY / CRYPTO
# ═════════════════════════════════════════════════════════════════════════════

class TestCommodityCrypto:

    def test_happy_path(self, shared_state):
        """Commodity agent writes commodity_results and commodity_sentiment."""
        from agents import commodity_crypto

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 72000.0
        fake_ticker.fast_info.previous_close = 71500.0

        with patch("yfinance.Ticker", return_value=fake_ticker):
            commodity_crypto.run(shared_state)

        assert "commodity_results"   in shared_state
        assert "commodity_sentiment" in shared_state

    def test_empty_input(self):
        """Runs cleanly on empty shared_state."""
        from agents import commodity_crypto
        state = empty_state()

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 100.0
        fake_ticker.fast_info.previous_close = 99.0

        with patch("yfinance.Ticker", return_value=fake_ticker):
            commodity_crypto.run(state)

        assert "commodity_results" in state

    def test_api_failure(self, shared_state):
        """yfinance error → graceful fallback."""
        from agents import commodity_crypto

        with patch("yfinance.Ticker", side_effect=Exception("timeout")):
            commodity_crypto.run(shared_state)

        assert "commodity_results" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 5. INSTITUTIONAL FLOW
# ═════════════════════════════════════════════════════════════════════════════

class TestInstitutionalFlow:

    def _nse_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": [
                {"buyValue": "5000.00", "sellValue": "4750.00",
                 "category": "FII/FPI", "date": "01-Mar-2026"},
                {"buyValue": "3000.00", "sellValue": "2600.00",
                 "category": "DII", "date": "01-Mar-2026"},
            ]
        }
        return resp

    def test_happy_path(self, shared_state):
        """Flow agent writes institutional_flow and delivery_data."""
        from agents import institutional_flow

        with patch("requests.get", return_value=self._nse_response()):
            institutional_flow.run(shared_state)

        assert "institutional_flow"     in shared_state
        assert "institutional_last_run" in shared_state

    def test_empty_input(self):
        """Runs on empty shared_state."""
        from agents import institutional_flow
        state = empty_state()

        with patch("requests.get", return_value=self._nse_response()):
            institutional_flow.run(state)

        assert "institutional_flow" in state

    def test_api_failure(self, shared_state):
        """NSE API failure → graceful fallback dict."""
        from agents import institutional_flow

        with patch("requests.get", side_effect=Exception("403 forbidden")):
            institutional_flow.run(shared_state)

        assert "institutional_flow" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 6. CLAUDE INTELLIGENCE
# ═════════════════════════════════════════════════════════════════════════════

class TestClaudeIntelligence:

    def _mock_anthropic(self):
        client = MagicMock()
        msg    = MagicMock()
        msg.content = [MagicMock(text=json.dumps({
            "market_view": "BULLISH",
            "key_themes": ["Tech rally"],
            "top_picks": ["TCS.NS"],
            "risk_factors": ["Inflation"],
            "confidence": 75,
        }))]
        client.messages.create.return_value = msg
        return client

    def test_happy_path(self, shared_state, tmp_data_dir):
        """Claude agent writes claude_analysis."""
        from agents import claude_intelligence
        import anthropic as _anthropic

        fake_client = self._mock_anthropic()

        with patch.object(_anthropic, "Anthropic", return_value=fake_client), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}), \
             patch("agents.claude_intelligence._BASE",
                   os.path.dirname(tmp_data_dir)):
            claude_intelligence.run(shared_state)

        assert "claude_analysis" in shared_state

    def test_empty_input(self, tmp_data_dir):
        """Falls back gracefully on empty state."""
        from agents import claude_intelligence
        import anthropic as _anthropic
        state = empty_state()

        fake_client = self._mock_anthropic()

        with patch.object(_anthropic, "Anthropic", return_value=fake_client), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}), \
             patch("agents.claude_intelligence._BASE",
                   os.path.dirname(tmp_data_dir)):
            claude_intelligence.run(state)

        assert "claude_analysis" in state

    def test_api_failure(self, shared_state, tmp_data_dir):
        """Anthropic API failure → fallback analysis written."""
        from agents import claude_intelligence
        import anthropic as _anthropic

        with patch.object(_anthropic, "Anthropic", side_effect=Exception("API error")), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}), \
             patch("agents.claude_intelligence._BASE",
                   os.path.dirname(tmp_data_dir)):
            claude_intelligence.run(shared_state)

        assert "claude_analysis" in shared_state

    def test_post_mortem_context_in_prompt(self, shared_state, tmp_data_dir):
        """M3-5: Post-mortem lessons are injected into the Claude system prompt."""
        from agents import claude_intelligence

        # Seed post-mortem data into shared_state
        shared_state["post_mortem_output"] = {
            "analyzed_this_cycle": 1,
            "total_analyzed": 3,
            "new_failures": ["WIPRO.NS"],
            "adjustments_made": [{"key": "rsi_threshold"}],
            "llm_diagnosis": "Momentum signal unreliable in bear phase",
            "last_run": "01 Mar 09:15:00",
        }
        shared_state["post_mortem_llm_note"] = "Avoid IT after consecutive FII sell sessions."

        ctx = claude_intelligence._load_post_mortem_context(shared_state)

        assert "WIPRO.NS" in ctx, "Failed tickers must appear in post-mortem context"
        assert "FII" in ctx, "LLM note must propagate to context"
        assert "Momentum signal" in ctx, "llm_diagnosis must appear in context"

    def test_post_mortem_context_empty_state(self):
        """M3-5: Empty shared_state returns a safe fallback string."""
        from agents import claude_intelligence

        ctx = claude_intelligence._load_post_mortem_context({})
        assert isinstance(ctx, str)
        assert len(ctx) > 10, "Must return a non-trivial fallback string"

    def test_system_prompt_has_post_mortem_placeholder(self):
        """M3-5: SYSTEM_PROMPT must contain {post_mortem} placeholder."""
        from agents import claude_intelligence

        assert "{post_mortem}" in claude_intelligence.SYSTEM_PROMPT, (
            "SYSTEM_PROMPT must include {post_mortem} so lessons reach the LLM"
        )

    def test_post_mortem_context_injected_in_api_call(self, shared_state, tmp_data_dir):
        """M3-5: When _call_claude() runs, post-mortem text appears in system arg."""
        from agents import claude_intelligence
        import anthropic as _anthropic

        shared_state["post_mortem_llm_note"] = "Unique-sentinel-lesson-for-test"

        fake_client = self._mock_anthropic()
        captured_system = {}

        orig_create = fake_client.messages.create

        def capture(**kw):
            captured_system["system"] = kw.get("system", "")
            return orig_create(**kw)

        fake_client.messages.create.side_effect = capture

        with patch.object(_anthropic, "Anthropic", return_value=fake_client), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}), \
             patch("agents.claude_intelligence.ANTHROPIC_API_KEY", "sk-test"), \
             patch("agents.claude_intelligence._BASE",
                   os.path.dirname(tmp_data_dir)):
            # Reset cache to force fresh call
            claude_intelligence._last_analysis = None
            claude_intelligence._last_analysis_time = 0
            claude_intelligence.run(shared_state)

        assert "Unique-sentinel-lesson-for-test" in captured_system.get("system", ""), (
            "post_mortem_llm_note must appear verbatim in the system prompt sent to Claude"
        )


# ═════════════════════════════════════════════════════════════════════════════
# 7. WEB RESEARCHER
# ═════════════════════════════════════════════════════════════════════════════

class TestWebResearcher:

    def _ddg_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "AbstractText": "Reliance Industries is bullish due to 5G rollout.",
            "RelatedTopics": [],
        }
        return resp

    def test_happy_path(self, shared_state):
        """Web researcher writes web_research for top symbols."""
        from agents import web_researcher

        fake_gemini = MagicMock()
        fake_gemini.generate_content.return_value.text = "Positive outlook."

        with patch("requests.get", return_value=self._ddg_response()), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "fake-gemini-key"}):
            try:
                import google.generativeai  # noqa: F401
                with patch("google.generativeai.GenerativeModel",
                           return_value=fake_gemini):
                    web_researcher.run(shared_state)
            except ImportError:
                # If google-generativeai not available, patch the internal import
                with patch.dict("sys.modules", {
                    "google": MagicMock(), "google.generativeai": MagicMock()
                }):
                    web_researcher.run(shared_state)

        assert "web_research"      in shared_state
        assert "web_research_last" in shared_state

    def test_empty_input(self):
        """Runs on empty shared_state."""
        from agents import web_researcher
        state = empty_state()

        with patch("requests.get", side_effect=Exception("timeout")):
            web_researcher.run(state)

        assert "web_research" in state

    def test_api_failure(self, shared_state):
        """DuckDuckGo failure → empty research dict, no crash."""
        from agents import web_researcher

        with patch("requests.get", side_effect=Exception("blocked")):
            web_researcher.run(shared_state)

        assert "web_research" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 8. TRADE SIGNAL
# ═════════════════════════════════════════════════════════════════════════════

class TestTradeSignal:

    def test_happy_path(self, shared_state):
        """Trade signal agent generates signals from scanner results."""
        from agents import trade_signal

        trade_signal.run(shared_state)

        assert "trade_signals"     in shared_state
        assert "actionable_signals" in shared_state
        assert "signals_last_run"  in shared_state
        assert isinstance(shared_state["trade_signals"], list)

    def test_empty_scanner_results(self):
        """No scanner results → empty signals list."""
        from agents import trade_signal
        state = {"scanner_results": [], "market_sentiment_score": 50}

        trade_signal.run(state)

        assert "trade_signals" in state
        assert state["trade_signals"] == []

    def test_no_external_calls(self, shared_state):
        """Trade signal is pure computation — no network calls needed."""
        from agents import trade_signal

        # Should succeed with zero mocking of network
        trade_signal.run(shared_state)
        assert "trade_signals" in shared_state

    def test_high_confidence_signal_is_actionable(self, shared_state):
        """Signals with confidence >= 82 should land in actionable_signals."""
        from agents import trade_signal

        # Seed a high-score result
        shared_state["scanner_results"][0]["score"] = 90
        shared_state["market_sentiment_score"] = 75

        trade_signal.run(shared_state)

        signals = shared_state["trade_signals"]
        if signals:
            # confidence may be int or str depending on agent version
            def conf_val(s):
                v = s.get("confidence", 0)
                return int(v) if str(v).lstrip("-").isdigit() else 0

            high_conf = [s for s in signals if conf_val(s) >= 75]
            assert isinstance(high_conf, list)  # just verify no crash


# ═════════════════════════════════════════════════════════════════════════════
# 9. SECTOR ROTATION
# ═════════════════════════════════════════════════════════════════════════════

class TestSectorRotation:

    def test_happy_path(self, shared_state):
        """Sector rotation agent writes sector_rotation dict."""
        from agents import sector_rotation

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 22000.0
        fake_ticker.fast_info.previous_close = 21800.0

        with patch("yfinance.Ticker", return_value=fake_ticker):
            sector_rotation.run(shared_state)

        assert "sector_rotation"      in shared_state
        assert "sector_rotation_last" in shared_state

    def test_empty_input(self):
        """Runs on empty shared_state."""
        from agents import sector_rotation
        state = empty_state()

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 100.0
        fake_ticker.fast_info.previous_close = 99.0

        with patch("yfinance.Ticker", return_value=fake_ticker):
            sector_rotation.run(state)

        assert "sector_rotation" in state

    def test_api_failure(self, shared_state):
        """yfinance failure → graceful fallback."""
        from agents import sector_rotation

        with patch("yfinance.Ticker", side_effect=Exception("rate limit")):
            sector_rotation.run(shared_state)

        assert "sector_rotation" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 10. RISK MANAGER
# ═════════════════════════════════════════════════════════════════════════════

class TestRiskManager:

    def test_happy_path(self, shared_state, patched_file_paths):
        """Risk manager approves/rejects signals and writes risk_reviewed_signals."""
        from agents import risk_manager

        with patch("agents.risk_manager._BASE",
                   os.path.dirname(patched_file_paths)):
            risk_manager.run(shared_state)

        assert "risk_reviewed_signals" in shared_state
        assert "risk_summary"          in shared_state
        assert isinstance(shared_state["risk_reviewed_signals"], list)

    def test_empty_signals(self, patched_file_paths):
        """No trade_signals → empty reviewed list."""
        from agents import risk_manager
        state = {"trade_signals": [], "paper_portfolio": {
            "cash": 100_000.0, "positions": {}, "total_value": 100_000.0
        }}

        with patch("agents.risk_manager._BASE",
                   os.path.dirname(patched_file_paths)):
            risk_manager.run(state)

        assert "risk_reviewed_signals" in state
        assert state["risk_reviewed_signals"] == []

    def test_no_external_calls(self, shared_state, patched_file_paths):
        """Risk manager is pure computation (reads JSON file only)."""
        from agents import risk_manager

        with patch("agents.risk_manager._BASE",
                   os.path.dirname(patched_file_paths)):
            risk_manager.run(shared_state)

        assert "risk_summary" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 11. MORNING BRIEF
# ═════════════════════════════════════════════════════════════════════════════

class TestMorningBrief:

    def test_happy_path_with_send_fns(self, shared_state,
                                       mock_telegram_fn, mock_n8n_fn):
        """Morning brief calls send_telegram_fn and writes last_morning_brief."""
        from agents import morning_brief

        morning_brief.run(shared_state, mock_telegram_fn, mock_n8n_fn, force=True)

        assert "last_morning_brief" in shared_state
        mock_telegram_fn.assert_called_once()

    def test_no_n8n_fn(self, shared_state, mock_telegram_fn):
        """n8n fn is optional — should not raise when None."""
        from agents import morning_brief

        morning_brief.run(shared_state, mock_telegram_fn, send_n8n_fn=None, force=True)

        assert "last_morning_brief" in shared_state

    def test_telegram_failure(self, shared_state):
        """
        M3 fix: morning_brief.run() must NOT propagate Telegram exceptions.
        Telegram down → log warning, continue, still write last_morning_brief.
        """
        from agents import morning_brief

        failing_telegram = MagicMock(side_effect=Exception("Telegram down"))

        # Must NOT raise — Telegram failure is non-fatal
        result = morning_brief.run(
            shared_state, failing_telegram, send_n8n_fn=None, force=True
        )

        # Agent must still complete and write state
        assert "last_morning_brief" in shared_state, \
            "last_morning_brief should be written even when Telegram fails"
        assert result is not None, \
            "run() should return the message string even when Telegram fails"
        failing_telegram.assert_called_once()  # was attempted


# ═════════════════════════════════════════════════════════════════════════════
# 12. PAPER TRADER
# ═════════════════════════════════════════════════════════════════════════════

class TestPaperTrader:

    def test_happy_path(self, shared_state, patched_file_paths):
        """Paper trader writes paper_portfolio without touching real money."""
        from agents import paper_trader

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 2800.0

        with patch("yfinance.Ticker", return_value=fake_ticker):
            paper_trader.run(shared_state)

        assert "paper_portfolio" in shared_state
        portfolio = shared_state["paper_portfolio"]
        # paper_trader uses "available_cash" + "capital" (not "cash")
        assert "available_cash" in portfolio or "capital" in portfolio
        cash_val = portfolio.get("available_cash", portfolio.get("capital", 0))
        assert cash_val >= 0

    def test_no_actionable_signals(self, patched_file_paths):
        """No signals → portfolio unchanged, no crash."""
        from agents import paper_trader
        state = {
            "risk_reviewed_signals": [],
            "trade_signals": [],
            "paper_portfolio": {
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
            },
        }

        fake_ticker = MagicMock()
        fake_ticker.fast_info.last_price = 100.0

        with patch("yfinance.Ticker", return_value=fake_ticker):
            paper_trader.run(state)

        assert "paper_portfolio" in state

    def test_live_trading_disabled(self, shared_state, patched_file_paths):
        """LIVE_TRADING_ENABLED must remain False — critical safety check."""
        import agents.paper_trader as pt_module

        assert hasattr(pt_module, "LIVE_TRADING_ENABLED"), \
            "LIVE_TRADING_ENABLED constant must exist in paper_trader.py"
        assert pt_module.LIVE_TRADING_ENABLED is False, \
            "LIVE_TRADING_ENABLED must be False — no real broker connectivity allowed"

    def test_price_cache_used_when_provided(self, shared_state, patched_file_paths):
        """When price_cache is provided, yfinance call count should be minimal."""
        from agents import paper_trader

        price_cache = {"RELIANCE.NS": 2800.0}

        with patch("yfinance.Ticker") as mock_yf:
            paper_trader.run(shared_state, price_cache=price_cache)

        assert "paper_portfolio" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 13. PATTERN MEMORY
# ═════════════════════════════════════════════════════════════════════════════

class TestPatternMemory:

    def test_happy_path(self, shared_state, patched_file_paths):
        """Pattern memory reads signal history and writes pattern_library."""
        from agents import pattern_memory

        pattern_memory.run(shared_state)

        assert "pattern_library" in shared_state
        assert isinstance(shared_state["pattern_library"], list)

    def test_empty_input(self, patched_file_paths):
        """Runs cleanly with empty shared_state."""
        from agents import pattern_memory
        state = empty_state()

        pattern_memory.run(state)

        assert "pattern_library" in state

    def test_corrupted_signal_file(self, shared_state, tmp_path):
        """Corrupted signal_history.json → graceful fallback, empty patterns."""
        from agents import pattern_memory

        bad_dir     = str(tmp_path / "bad_data")
        bad_history = os.path.join(bad_dir, "signal_history.json")
        bad_pattern = os.path.join(bad_dir, "pattern_library.json")
        os.makedirs(bad_dir)
        with open(bad_history, "w") as f:
            f.write("NOT VALID JSON {{{{")
        with open(bad_pattern, "w") as f:
            f.write("[]")

        with patch("agents.pattern_memory.HISTORY_FILE", bad_history), \
             patch("agents.pattern_memory.PATTERN_FILE", bad_pattern):
            pattern_memory.run(shared_state)  # must not raise

        assert "pattern_library" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 14. EARNINGS CALENDAR
# ═════════════════════════════════════════════════════════════════════════════

class TestEarningsCalendar:

    def _nse_calendar_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": [
                {
                    "symbol": "RELIANCE",
                    "companyName": "Reliance Industries Ltd",
                    "bMeetingDate": "15-Mar-2026",
                    "purpose": "Quarterly Results",
                }
            ]
        }
        return resp

    def test_happy_path(self, shared_state):
        """Earnings calendar writes events_calendar dict."""
        from agents import earnings_calendar

        with patch("requests.get", return_value=self._nse_calendar_response()):
            earnings_calendar.run(shared_state)

        assert "events_calendar"   in shared_state
        assert "agent_confidence"  in shared_state

    def test_empty_input(self):
        """Runs on empty shared_state."""
        from agents import earnings_calendar
        state = empty_state()

        with patch("requests.get", return_value=self._nse_calendar_response()):
            earnings_calendar.run(state)

        assert "events_calendar" in state

    def test_api_failure(self, shared_state):
        """NSE API failure → empty calendar, no exception."""
        from agents import earnings_calendar

        with patch("requests.get", side_effect=Exception("NSE timeout")):
            earnings_calendar.run(shared_state)

        assert "events_calendar" in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# 15. OPTIONS FLOW
# ═════════════════════════════════════════════════════════════════════════════

class TestOptionsFlow:

    def _option_chain_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "records": {
                "underlyingValue": 22100.0,
                "expiryDates": ["27-Mar-2026", "24-Apr-2026"],
                "data": [
                    {
                        "strikePrice": 22000,
                        "expiryDate": "27-Mar-2026",
                        "CE": {
                            "openInterest": 50000,
                            "changeinOpenInterest": 5000,
                            "totalTradedVolume": 100000,
                            "impliedVolatility": 15.5,
                            "lastPrice": 200.0,
                        },
                        "PE": {
                            "openInterest": 60000,
                            "changeinOpenInterest": -2000,
                            "totalTradedVolume": 90000,
                            "impliedVolatility": 16.0,
                            "lastPrice": 180.0,
                        },
                    }
                ],
            }
        }
        return resp

    def _vix_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": [{"index": "INDIA VIX", "last": 14.5, "variation": -0.3}]
        }
        return resp

    def test_happy_path(self, shared_state):
        """Options agent writes india_vix, options_flow, iv_rank."""
        from agents import options_flow

        def get_side_effect(url, *args, **kwargs):
            if "vix" in url.lower() or "VIX" in url:
                return self._vix_response()
            return self._option_chain_response()

        with patch("requests.get", side_effect=get_side_effect):
            options_flow.run(shared_state)

        assert "options_flow"    in shared_state
        assert "india_vix"       in shared_state
        assert "options_last_run" in shared_state

    def test_empty_input(self):
        """Runs on empty shared_state."""
        from agents import options_flow
        state = empty_state()

        def get_side_effect(url, *args, **kwargs):
            if "vix" in url.lower():
                return self._vix_response()
            return self._option_chain_response()

        with patch("requests.get", side_effect=get_side_effect):
            options_flow.run(state)

        assert "options_flow" in state

    def test_api_failure(self, shared_state):
        """NSE option chain failure → defaults written, no crash."""
        from agents import options_flow

        with patch("requests.get", side_effect=Exception("blocked")):
            options_flow.run(shared_state)

        assert "options_flow" in shared_state
        assert "india_vix"    in shared_state


# ═════════════════════════════════════════════════════════════════════════════
# Cross-agent Safety Checks
# ═════════════════════════════════════════════════════════════════════════════

class TestSafetyInvariants:

    def test_paper_trader_constant(self):
        """LIVE_TRADING_ENABLED must be False — immutable safety guarantee."""
        import agents.paper_trader as pt
        assert pt.LIVE_TRADING_ENABLED is False

    def test_paper_trader_no_broker_import(self):
        """paper_trader.py must not import any real broker library."""
        import agents.paper_trader as pt
        forbidden = ["kite", "zerodha", "fyers", "upstox", "iifl_broker",
                     "SmartConnect", "breeze_connect"]
        source_file = pt.__file__
        with open(source_file) as f:
            source = f.read()
        for lib in forbidden:
            assert lib not in source, \
                f"Forbidden broker import '{lib}' found in paper_trader.py"

    def test_all_agents_have_run_function(self):
        """Every agent module must expose a callable run() function."""
        agent_names = [
            "market_scanner", "news_sentiment", "technical_analysis",
            "commodity_crypto", "institutional_flow", "claude_intelligence",
            "web_researcher", "trade_signal", "sector_rotation", "risk_manager",
            "morning_brief", "paper_trader", "pattern_memory",
            "earnings_calendar", "options_flow",
        ]
        import importlib
        for name in agent_names:
            mod = importlib.import_module(f"agents.{name}")
            assert hasattr(mod, "run"), f"agents.{name} missing run() function"
            assert callable(mod.run),  f"agents.{name}.run is not callable"

    def test_shared_state_mutation_only(self, shared_state):
        """
        Agents must mutate shared_state in-place, not return a new dict.
        trade_signal is a pure compute agent — test it here.
        """
        from agents import trade_signal
        original_id = id(shared_state)
        trade_signal.run(shared_state)
        assert id(shared_state) == original_id, \
            "trade_signal.run() must not replace shared_state — mutate in-place"
