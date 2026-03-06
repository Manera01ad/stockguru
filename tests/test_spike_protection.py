"""
test_spike_protection.py — Spike Detector + Volatility Circuit Breaker Tests
=============================================================================
Tests for:
  • spike_detector.py  — PRICE_SPIKE and VOLUME_SURGE detection
  • broker_connector   — 2-tick SL confirmation and VIX-aware trailing SL
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, "stockguru_agents")
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION A — SpikeDetector
# ══════════════════════════════════════════════════════════════════════════════

class TestSpikeDetector:

    def setup_method(self):
        """Fresh module state for every test."""
        from agents.spike_detector import reset_history
        reset_history()

    def _make_state(self, symbol, price, prev_price=None, volume=None):
        """Build a minimal shared_state with one price entry."""
        from agents.spike_detector import _price_history, _volume_history
        # Seed previous price so spike detection has something to compare
        if prev_price is not None:
            _price_history[symbol].append(prev_price)
        entry = {"price": price}
        if volume is not None:
            entry["volume"] = volume
        return {"price_cache": {symbol: entry}}

    # ── constants ─────────────────────────────────────────────────────────────

    def test_spike_pct_threshold_exists(self):
        from agents.spike_detector import SPIKE_PCT_THRESHOLD
        assert isinstance(SPIKE_PCT_THRESHOLD, (int, float))
        assert 0.5 <= SPIKE_PCT_THRESHOLD <= 5.0, "Should be between 0.5% and 5%"

    def test_volume_surge_factor_exists(self):
        from agents.spike_detector import VOLUME_SURGE_FACTOR
        assert isinstance(VOLUME_SURGE_FACTOR, (int, float))
        assert 1.5 <= VOLUME_SURGE_FACTOR <= 10.0, "Should be between 1.5× and 10×"

    # ── price spike ───────────────────────────────────────────────────────────

    def test_no_alert_on_first_tick(self):
        """First tick has no history — no alert should fire."""
        from agents import spike_detector
        state = {"price_cache": {"NIFTY 50": {"price": 22000}}}
        alerts = spike_detector.run(state)
        assert alerts == [], "First tick has no prior price — no alert"

    def test_no_alert_within_threshold(self):
        """A 1.0% move (below threshold) should not fire."""
        from agents import spike_detector
        state = self._make_state("NIFTY 50", prev_price=22000, price=22220)  # +1.0%
        alerts = spike_detector.run(state)
        assert alerts == [], "Sub-threshold move must not alert"

    def test_price_spike_fires(self):
        """A 2.0% up-move (above threshold) should fire PRICE_SPIKE."""
        from agents import spike_detector
        state = self._make_state("NIFTY 50", prev_price=22000, price=22440)  # +2.0%
        alerts = spike_detector.run(state)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "PRICE_SPIKE"
        assert alerts[0]["direction"] == "UP"
        assert alerts[0]["delta_pct"] == pytest.approx(2.0, abs=0.05)

    def test_price_spike_down_fires(self):
        """A 2.0% down-move should fire PRICE_SPIKE with DOWN direction."""
        from agents import spike_detector
        state = self._make_state("NIFTY 50", prev_price=22000, price=21560)  # -2.0%
        alerts = spike_detector.run(state)
        assert len(alerts) == 1
        assert alerts[0]["direction"] == "DOWN"

    def test_critical_severity_at_double_threshold(self):
        """A 3.0% move (2× threshold=1.5%) → CRITICAL severity."""
        from agents import spike_detector
        from agents.spike_detector import SPIKE_PCT_THRESHOLD
        state = self._make_state(
            "NIFTY 50",
            prev_price=22000,
            price=round(22000 * (1 + SPIKE_PCT_THRESHOLD * 2 / 100), 2),
        )
        alerts = spike_detector.run(state)
        assert len(alerts) >= 1
        assert alerts[0]["severity"] == "CRITICAL"

    # ── volume surge ──────────────────────────────────────────────────────────

    def test_volume_surge_fires(self):
        """Volume 4× average triggers VOLUME_SURGE."""
        from agents.spike_detector import _volume_history, VOLUME_SURGE_FACTOR
        sym = "NIFTY 50"
        for _ in range(5):
            _volume_history[sym].append(100_000)

        from agents import spike_detector
        state = {"price_cache": {sym: {"price": 22000, "volume": 400_000}}}
        alerts = spike_detector.run(state)
        vol_alerts = [a for a in alerts if a.get("volume_alert")]
        assert len(vol_alerts) >= 1, "Volume 4× avg should fire a surge alert"

    # ── cooldown ──────────────────────────────────────────────────────────────

    def test_cooldown_suppresses_repeat_alerts(self):
        """After an alert, the same symbol is suppressed for ALERT_COOLDOWN_TICKS cycles."""
        from agents import spike_detector
        from agents.spike_detector import ALERT_COOLDOWN_TICKS

        # Fire first alert
        state1 = self._make_state("NIFTY 50", prev_price=22000, price=22440)
        spike_detector.run(state1)

        # Immediately after — spike still active, but cooldown should suppress
        from agents.spike_detector import _price_history
        _price_history["NIFTY 50"].append(22440)
        state2 = {"price_cache": {"NIFTY 50": {"price": 22900}}}  # another +2%
        alerts2 = spike_detector.run(state2)
        nifty_alerts = [a for a in alerts2 if a.get("symbol") == "NIFTY 50"]
        assert nifty_alerts == [], "Cooldown must suppress repeat alert for same symbol"

    # ── telegram integration ──────────────────────────────────────────────────

    def test_telegram_called_on_spike(self):
        """spike_detector should call send_telegram_fn when a spike fires."""
        from agents import spike_detector
        mock_tg = MagicMock()
        state = self._make_state("NIFTY 50", prev_price=22000, price=22440)
        alerts = spike_detector.run(state, send_telegram_fn=mock_tg)
        assert len(alerts) == 1
        mock_tg.assert_called_once()

    def test_no_telegram_on_clean_cycle(self):
        """No telegram call when no spike."""
        from agents import spike_detector
        mock_tg = MagicMock()
        state = self._make_state("NIFTY 50", prev_price=22000, price=22100)  # +0.45%
        spike_detector.run(state, send_telegram_fn=mock_tg)
        mock_tg.assert_not_called()

    # ── shared_state keys ─────────────────────────────────────────────────────

    def test_spike_detector_active_flag(self):
        """spike_detector_active must be True when alerts fire, False otherwise."""
        from agents import spike_detector
        state_spike = self._make_state("NIFTY 50", prev_price=22000, price=22440)
        spike_detector.run(state_spike)
        assert state_spike["spike_detector_active"] is True

        reset_state = {"price_cache": {}}
        from agents.spike_detector import reset_history
        reset_history()
        spike_detector.run(reset_state)
        assert reset_state["spike_detector_active"] is False


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — Volatility Circuit Breaker (broker_connector)
# ══════════════════════════════════════════════════════════════════════════════

def _make_broker(tmp_path):
    from broker_connector import PaperBroker
    return PaperBroker(
        portfolio_file=str(tmp_path / "port.json"),
        trades_file=str(tmp_path / "trades.json"),
    )


def _inject_position(broker, sym, avg_price, quantity, target1, target2, stop_loss):
    from broker_connector import Position, ProductCode, Exchange
    pos = Position(
        symbol=sym, exchange=Exchange.NSE, product=ProductCode.CNC,
        quantity=quantity, avg_price=avg_price, last_price=avg_price,
        target1=target1, target2=target2, stop_loss=stop_loss,
        status="OPEN", t1_booked=False, trail_sl_high=0.0, sl_breach_ticks=0,
    )
    broker._positions[sym] = pos
    broker._portfolio["available_cash"] -= avg_price * quantity
    return pos


class TestVolatilityCircuitBreaker:

    # ── Constants ─────────────────────────────────────────────────────────────

    def test_circuit_breaker_constants_exist(self):
        from broker_connector import (
            VIX_CALM_THRESHOLD, VIX_HIGH_THRESHOLD,
            SL_CONFIRM_TICKS_NORMAL, SL_CONFIRM_TICKS_SPIKE,
        )
        assert VIX_CALM_THRESHOLD < VIX_HIGH_THRESHOLD, "Calm must be below high threshold"
        assert SL_CONFIRM_TICKS_NORMAL == 1, "Normal market: 1-tick exit"
        assert SL_CONFIRM_TICKS_SPIKE  == 2, "Elevated VIX: 2-tick exit"

    def test_sl_breach_ticks_field_on_position(self):
        from broker_connector import Position, Exchange, ProductCode
        pos = Position(symbol="X", exchange=Exchange.NSE,
                       product=ProductCode.CNC, quantity=1, avg_price=100.0,
                       last_price=100.0)
        assert hasattr(pos, "sl_breach_ticks")
        assert pos.sl_breach_ticks == 0

    # ── 1-tick exit in calm market (VIX not in cache) ─────────────────────────

    def test_sl_exit_on_first_breach_normal_market(self, tmp_path):
        """When VIX is absent (calm), SL exit fires on the first breach tick."""
        broker = _make_broker(tmp_path)
        _inject_position(broker, "RELIANCE.NS", 2800, 10,
                         target1=2870, target2=2950, stop_loss=2730)

        orders = broker.tick({"RELIANCE.NS": 2729})  # below SL, no VIX

        sl_orders = [o for o in orders if "SL_EXIT" in str(o.tag)]
        assert len(sl_orders) >= 1, "Calm market: SL exit must fire on tick 1"

    # ── 2-tick confirmation when VIX ≥ VIX_CALM_THRESHOLD ────────────────────

    def test_sl_not_exit_on_first_breach_elevated_vix(self, tmp_path):
        """When VIX ≥ 15, first tick below SL should NOT exit (waiting for confirmation)."""
        from broker_connector import VIX_CALM_THRESHOLD
        broker = _make_broker(tmp_path)
        _inject_position(broker, "INFY.NS", 1500, 10,
                         target1=1530, target2=1580, stop_loss=1470)

        vix_price = VIX_CALM_THRESHOLD + 5   # VIX = 20
        # Stock price as float (broker convention), VIX as dict (structured cache entry)
        price_cache = {"INFY.NS": 1469, "INDIA VIX": {"price": vix_price}}
        orders = broker.tick(price_cache)
        sl_orders = [o for o in orders if "SL_EXIT" in str(o.tag)]
        assert sl_orders == [], "Elevated VIX: first breach tick must NOT exit"

        pos = broker._positions["INFY.NS"]
        assert pos.sl_breach_ticks == 1, "sl_breach_ticks must be 1 after first breach"

    def test_sl_exits_on_second_breach_elevated_vix(self, tmp_path):
        """When VIX ≥ 15, SL exit fires on the second consecutive breach tick."""
        from broker_connector import VIX_CALM_THRESHOLD
        broker = _make_broker(tmp_path)
        _inject_position(broker, "TCS.NS", 3500, 5,
                         target1=3570, target2=3650, stop_loss=3430)

        vix_price = VIX_CALM_THRESHOLD + 5
        pc = {"TCS.NS": 3429, "INDIA VIX": {"price": vix_price}}

        # Tick 1 — breach but no exit
        broker.tick(pc)
        assert broker._positions["TCS.NS"].sl_breach_ticks == 1

        # Tick 2 — still breached → exit
        orders2 = broker.tick(pc)
        sl_orders = [o for o in orders2 if "SL_EXIT" in str(o.tag)]
        assert len(sl_orders) >= 1, "Second consecutive breach must trigger SL exit"

    def test_sl_breach_counter_resets_on_recovery(self, tmp_path):
        """If price recovers above SL between ticks, breach counter resets to 0."""
        from broker_connector import VIX_CALM_THRESHOLD
        broker = _make_broker(tmp_path)
        _inject_position(broker, "WIPRO.NS", 400, 20,
                         target1=410, target2=430, stop_loss=392)

        vix_price = VIX_CALM_THRESHOLD + 5
        # Tick 1 — breach
        broker.tick({"WIPRO.NS": 391, "INDIA VIX": {"price": vix_price}})
        assert broker._positions["WIPRO.NS"].sl_breach_ticks == 1

        # Tick 2 — recovery above SL
        broker.tick({"WIPRO.NS": 395, "INDIA VIX": {"price": vix_price}})
        assert broker._positions["WIPRO.NS"].sl_breach_ticks == 0, \
            "Breach counter must reset when price recovers"

    # ── VIX-aware trailing SL width ───────────────────────────────────────────

    def test_trail_sl_wider_when_vix_elevated(self, tmp_path):
        """After T1, trailing SL distance should be ≥ TRAILING_SL_PCT when VIX elevated."""
        from broker_connector import TRAILING_SL_PCT, VIX_HIGH_THRESHOLD
        broker = _make_broker(tmp_path)
        _inject_position(broker, "SBIN.NS", 500, 10,
                         target1=515, target2=540, stop_loss=488)

        vix_price = VIX_HIGH_THRESHOLD + 10  # VIX = 30 (elevated)

        # Hit T1 with elevated VIX
        broker.tick({"SBIN.NS": 515, "INDIA VIX": {"price": vix_price}})
        # Push price up to trigger trail update
        broker.tick({"SBIN.NS": 530, "INDIA VIX": {"price": vix_price}})

        pos = broker._positions["SBIN.NS"]
        trail_distance_pct = (pos.trail_sl_high - pos.stop_loss) / pos.trail_sl_high
        assert trail_distance_pct >= TRAILING_SL_PCT, \
            f"Trail distance {trail_distance_pct:.3f} must be ≥ base {TRAILING_SL_PCT}"

    def test_trail_sl_normal_when_no_vix(self, tmp_path):
        """Without VIX data, trailing SL uses the base TRAILING_SL_PCT exactly."""
        from broker_connector import TRAILING_SL_PCT
        broker = _make_broker(tmp_path)
        _inject_position(broker, "HDFC.NS", 1600, 10,
                         target1=1640, target2=1700, stop_loss=1570)

        # T1 hit (no VIX in cache)
        broker.tick({"HDFC.NS": 1640})
        # Push price higher
        broker.tick({"HDFC.NS": 1660})

        pos = broker._positions["HDFC.NS"]
        expected_sl = round(max(1600, 1660 * (1 - TRAILING_SL_PCT)), 2)
        assert pos.stop_loss == pytest.approx(expected_sl, abs=0.02)
