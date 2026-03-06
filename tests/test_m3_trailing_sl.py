"""
test_m3_trailing_sl.py — M3-4: Trailing Stop-Loss Tests
=========================================================
Tests for the trailing SL enhancement in PaperBroker.tick().

Trailing SL contract:
  • After T1 hit: SL is immediately set to avg_price (breakeven floor)
  • As LTP rises above T1: SL ratchets upward = max(avg_price, high * (1 - TRAIL_PCT))
  • SL NEVER moves downward (ratchet mechanism)
  • SL NEVER goes below avg_price (breakeven floor protected)
  • When LTP falls to current SL: position is exited (SL_EXIT tag)
"""

import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, "stockguru_agents")
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_broker(tmp_path):
    """Return a fresh PaperBroker with tmp files."""
    from broker_connector import PaperBroker
    pf = str(tmp_path / "portfolio.json")
    tf = str(tmp_path / "trades.json")
    return PaperBroker(portfolio_file=pf, trades_file=tf)


def _inject_position(broker, sym, avg_price, quantity, target1, target2, stop_loss):
    """Directly inject an open Position into broker._positions (bypasses order flow)."""
    from broker_connector import Position, ProductCode, Exchange
    pos = Position(
        symbol    = sym,
        exchange  = Exchange.NSE,
        product   = ProductCode.CNC,   # CNC avoids MIS auto-square (post-market test runs)
        quantity  = quantity,
        avg_price = avg_price,
        last_price = avg_price,
        target1   = target1,
        target2   = target2,
        stop_loss = stop_loss,
        status    = "OPEN",
        t1_booked = False,
        trail_sl_high = 0.0,
    )
    broker._positions[sym] = pos
    broker._portfolio["available_cash"] -= avg_price * quantity  # deduct notional cash
    return pos


def _tick(broker, sym, price):
    """Single tick with a synthetic price_cache."""
    return broker.tick({sym: price})


# ══════════════════════════════════════════════════════════════════════════════
# Test Suite
# ══════════════════════════════════════════════════════════════════════════════

class TestTrailingStopLoss:

    # ── T1 triggers ───────────────────────────────────────────────────────────

    def test_t1_sets_breakeven_sl(self, tmp_path):
        """When T1 is hit, SL immediately moves to avg_price (breakeven)."""
        broker = _make_broker(tmp_path)
        _inject_position(broker, "RELIANCE.NS",
                         avg_price=2800.0, quantity=10,
                         target1=2870.0, target2=2950.0, stop_loss=2730.0)

        # Tick at T1 price
        _tick(broker, "RELIANCE.NS", 2870.0)

        pos = broker._positions["RELIANCE.NS"]
        assert pos.t1_booked is True
        assert pos.stop_loss == pytest.approx(2800.0), (
            "After T1, SL must be set to avg_price (breakeven)"
        )

    def test_t1_seeds_trail_sl_high(self, tmp_path):
        """When T1 hits, trail_sl_high is seeded to the T1 price."""
        broker = _make_broker(tmp_path)
        _inject_position(broker, "TCS.NS",
                         avg_price=3500.0, quantity=5,
                         target1=3570.0, target2=3650.0, stop_loss=3430.0)

        _tick(broker, "TCS.NS", 3570.0)

        pos = broker._positions["TCS.NS"]
        assert pos.trail_sl_high == pytest.approx(3570.0), (
            "trail_sl_high must be seeded to the T1 hit price"
        )

    def test_t1_books_half_quantity(self, tmp_path):
        """T1 books 50% (floor 1 share): 10 qty → places SELL for 5 shares."""
        broker = _make_broker(tmp_path)
        _inject_position(broker, "INFY.NS",
                         avg_price=1500.0, quantity=10,
                         target1=1530.0, target2=1580.0, stop_loss=1470.0)

        _tick(broker, "INFY.NS", 1530.0)

        t1_orders = [o for o in broker._order_book.values()
                     if "T1_BOOKING" in str(o.tag)]
        assert len(t1_orders) == 1
        assert t1_orders[0].quantity == 5

    # ── Trailing SL ratchet ───────────────────────────────────────────────────

    def test_trail_sl_raises_as_price_climbs(self, tmp_path):
        """After T1, SL ratchets upward as price rises above T1."""
        from broker_connector import TRAILING_SL_PCT

        broker = _make_broker(tmp_path)
        _inject_position(broker, "HDFC.NS",
                         avg_price=1600.0, quantity=10,
                         target1=1640.0, target2=1700.0, stop_loss=1570.0)

        # Hit T1
        _tick(broker, "HDFC.NS", 1640.0)
        sl_after_t1 = broker._positions["HDFC.NS"].stop_loss  # breakeven = 1600

        # Price rises further
        _tick(broker, "HDFC.NS", 1660.0)
        sl_after_rise = broker._positions["HDFC.NS"].stop_loss
        expected_sl = round(max(1600.0, 1660.0 * (1 - TRAILING_SL_PCT)), 2)

        assert sl_after_rise > sl_after_t1, "SL must rise as price climbs after T1"
        assert sl_after_rise == pytest.approx(expected_sl, abs=0.01)

    def test_trail_sl_never_moves_backward(self, tmp_path):
        """SL must never decrease even when price pulls back (ratchet property)."""
        broker = _make_broker(tmp_path)
        _inject_position(broker, "WIPRO.NS",
                         avg_price=400.0, quantity=20,
                         target1=410.0, target2=430.0, stop_loss=392.0)

        # T1 hit + climb
        _tick(broker, "WIPRO.NS", 410.0)
        _tick(broker, "WIPRO.NS", 425.0)
        sl_at_high = broker._positions["WIPRO.NS"].stop_loss

        # Price pulls back (but not to SL)
        _tick(broker, "WIPRO.NS", 418.0)
        sl_after_pullback = broker._positions["WIPRO.NS"].stop_loss

        assert sl_after_pullback == pytest.approx(sl_at_high), (
            "SL must NOT decrease on pullback — ratchet only moves up"
        )

    def test_trail_sl_floors_at_avg_price(self, tmp_path):
        """SL must never drop below avg_price even if TRAILING_SL_PCT is large."""
        from broker_connector import TRAILING_SL_PCT

        broker = _make_broker(tmp_path)
        avg = 100.0
        t1  = 101.0   # Very tight T1 — trail formula would give < avg_price
        _inject_position(broker, "TINY.NS",
                         avg_price=avg, quantity=10,
                         target1=t1, target2=120.0, stop_loss=95.0)

        _tick(broker, "TINY.NS", t1)
        pos = broker._positions["TINY.NS"]

        # With a 3% trail on T1=101, new_sl = 101*0.97 = 97.97 < avg_price=100
        # Floor ensures SL = avg_price = 100
        assert pos.stop_loss >= avg, (
            f"SL ({pos.stop_loss}) must not go below avg_price ({avg})"
        )

    def test_trail_sl_multiple_steps(self, tmp_path):
        """SL steps upward across multiple price increments correctly."""
        from broker_connector import TRAILING_SL_PCT

        broker = _make_broker(tmp_path)
        _inject_position(broker, "SBIN.NS",
                         avg_price=500.0, quantity=10,
                         target1=515.0, target2=540.0, stop_loss=488.0)

        prices = [515.0, 520.0, 525.0, 530.0]  # T1 then rising prices
        for p in prices:
            _tick(broker, "SBIN.NS", p)

        pos = broker._positions["SBIN.NS"]
        expected_sl = round(max(500.0, 530.0 * (1 - TRAILING_SL_PCT)), 2)
        assert pos.stop_loss == pytest.approx(expected_sl, abs=0.01)
        assert pos.trail_sl_high == pytest.approx(530.0)

    # ── SL exit after trailing ────────────────────────────────────────────────

    def test_sl_exit_triggered_at_trailed_sl(self, tmp_path):
        """Position must be exited with SL_EXIT tag when LTP falls to trailed SL."""
        broker = _make_broker(tmp_path)
        _inject_position(broker, "BAJAJ.NS",
                         avg_price=7000.0, quantity=2,
                         target1=7140.0, target2=7350.0, stop_loss=6860.0)

        # T1 + climb to 7200
        _tick(broker, "BAJAJ.NS", 7140.0)
        _tick(broker, "BAJAJ.NS", 7200.0)
        trailed_sl = broker._positions["BAJAJ.NS"].stop_loss  # ~7200*0.97 = 6984

        # Price falls to trailed SL
        _tick(broker, "BAJAJ.NS", trailed_sl - 0.01)

        sl_orders = [o for o in broker._order_book.values()
                     if "SL_EXIT" in str(o.tag)]
        assert len(sl_orders) >= 1, "SL_EXIT order must be placed when trailing SL is hit"

    def test_no_trail_before_t1(self, tmp_path):
        """Before T1, trail_sl_high stays 0 and SL stays at original value."""
        broker = _make_broker(tmp_path)
        original_sl = 2730.0
        _inject_position(broker, "RELIANCE.NS",
                         avg_price=2800.0, quantity=10,
                         target1=2870.0, target2=2950.0, stop_loss=original_sl)

        # Price rises toward T1 but doesn't hit it
        _tick(broker, "RELIANCE.NS", 2850.0)

        pos = broker._positions["RELIANCE.NS"]
        assert pos.t1_booked is False
        assert pos.trail_sl_high == 0.0
        assert pos.stop_loss == pytest.approx(original_sl), (
            "SL must not change before T1 is booked"
        )

    # ── T2 exit ───────────────────────────────────────────────────────────────

    def test_t2_exit_after_trail(self, tmp_path):
        """T2 hit after T1 results in T2_EXIT order for remaining quantity."""
        broker = _make_broker(tmp_path)
        _inject_position(broker, "ICICI.NS",
                         avg_price=900.0, quantity=10,
                         target1=918.0, target2=945.0, stop_loss=882.0)

        # Hit T1 then T2
        _tick(broker, "ICICI.NS", 918.0)
        _tick(broker, "ICICI.NS", 945.0)

        t2_orders = [o for o in broker._order_book.values()
                     if "T2_EXIT" in str(o.tag)]
        assert len(t2_orders) == 1, "T2_EXIT order must be placed on T2 hit"

    # ── Constant safety check ─────────────────────────────────────────────────

    def test_trailing_sl_pct_constant_exists(self):
        """TRAILING_SL_PCT constant must exist and be a sensible float."""
        from broker_connector import TRAILING_SL_PCT

        assert isinstance(TRAILING_SL_PCT, float)
        assert 0.005 <= TRAILING_SL_PCT <= 0.10, (
            "TRAILING_SL_PCT should be between 0.5% and 10%"
        )

    def test_position_has_trail_sl_high_field(self):
        """Position dataclass must include trail_sl_high field (default 0.0)."""
        from broker_connector import Position, Exchange, ProductCode

        pos = Position(symbol="TEST", exchange=Exchange.NSE,
                       product=ProductCode.CNC, quantity=1, avg_price=100.0,
                       last_price=100.0)
        assert hasattr(pos, "trail_sl_high"), "Position must have trail_sl_high field"
        assert pos.trail_sl_high == 0.0, "trail_sl_high default must be 0.0"
