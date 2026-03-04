"""
AGENT — SPIKE DETECTOR
━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Detect sudden intraday price spikes in Nifty, BankNifty, and
          watchlist equities. Fires SPIKE_ALERT to shared_state and Telegram.

Triggers a SPIKE_ALERT when ANY of these conditions fire:
  • PRICE SPIKE : |Δprice| ≥ 1.5% in one 5-min tick vs the previous tick
  • VOLUME SURGE: Current volume ≥ 3.0× the trailing 5-tick average volume
  • DOUBLE HIT  : Both conditions fire simultaneously → CRITICAL level

Intent : Give the orchestrator and paper trader early warning so:
         1. Existing positions tighten SL (handled by volatility circuit breaker)
         2. No new entries are taken during the spike window
         3. User receives a Telegram alert with full context

Called from : app.py — after price_cache is refreshed each cycle
              (inject into the Tier 1 data collection block)
"""

import logging
from datetime import datetime
from collections import defaultdict, deque

log = logging.getLogger("SpikeDetector")

# ── CONFIGURATION ──────────────────────────────────────────────────────────────
SPIKE_PCT_THRESHOLD   = 1.5   # % price move in one tick → spike alert
VOLUME_SURGE_FACTOR   = 3.0   # × trailing average volume → surge alert
VOLUME_WINDOW         = 5     # ticks of history for volume baseline
ALERT_COOLDOWN_TICKS  = 3     # suppress repeat alerts for same symbol for N ticks
WATCHLIST_SYMBOLS     = [
    "NIFTY 50", "BANK NIFTY",
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "KOTAKBANK.NS", "WIPRO.NS", "AXISBANK.NS", "BAJFINANCE.NS",
]

# ── PERSISTENT HISTORY (in-process — resets on server restart) ────────────────
_price_history:   dict[str, deque]  = defaultdict(lambda: deque(maxlen=2))
_volume_history:  dict[str, deque]  = defaultdict(lambda: deque(maxlen=VOLUME_WINDOW))
_cooldown_counter: dict[str, int]   = defaultdict(int)


# ══════════════════════════════════════════════════════════════════════════════
# Core detection helpers
# ══════════════════════════════════════════════════════════════════════════════

def _check_price_spike(symbol: str, current_price: float) -> dict | None:
    """
    Compare current price vs the previous tick price.
    Returns a spike dict if |Δ%| ≥ SPIKE_PCT_THRESHOLD, else None.
    """
    hist = _price_history[symbol]
    if len(hist) < 1:
        return None

    prev_price = hist[-1]
    if prev_price == 0:
        return None

    delta_pct = (current_price - prev_price) / prev_price * 100
    if abs(delta_pct) < SPIKE_PCT_THRESHOLD:
        return None

    direction = "UP" if delta_pct > 0 else "DOWN"
    return {
        "type":        "PRICE_SPIKE",
        "symbol":      symbol,
        "prev_price":  round(prev_price, 2),
        "curr_price":  round(current_price, 2),
        "delta_pct":   round(delta_pct, 2),
        "direction":   direction,
        "severity":    "CRITICAL" if abs(delta_pct) >= SPIKE_PCT_THRESHOLD * 2 else "HIGH",
    }


def _check_volume_surge(symbol: str, current_volume: float) -> dict | None:
    """
    Compare current volume vs trailing average.
    Returns a surge dict if current ≥ VOLUME_SURGE_FACTOR × avg, else None.
    """
    hist = _volume_history[symbol]
    if len(hist) < 2 or current_volume is None:
        return None

    avg_vol = sum(hist) / len(hist)
    if avg_vol == 0:
        return None

    surge_factor = current_volume / avg_vol
    if surge_factor < VOLUME_SURGE_FACTOR:
        return None

    return {
        "type":         "VOLUME_SURGE",
        "symbol":       symbol,
        "current_vol":  int(current_volume),
        "avg_vol":      int(avg_vol),
        "surge_factor": round(surge_factor, 1),
        "severity":     "CRITICAL" if surge_factor >= VOLUME_SURGE_FACTOR * 2 else "HIGH",
    }


def _format_telegram_alert(spike: dict, volume: dict | None = None) -> str:
    """Build Telegram message for a spike event."""
    s = spike
    lines = [
        f"🚨 *SPIKE ALERT — {s['symbol']}*",
        f"⏰ {datetime.now().strftime('%H:%M:%S')} IST",
        "",
    ]
    if s["type"] == "PRICE_SPIKE":
        arrow = "📈" if s["direction"] == "UP" else "📉"
        lines += [
            f"{arrow} *Price {s['direction']}: {s['delta_pct']:+.2f}% in one tick*",
            f"   Prev: ₹{s['prev_price']:,.2f} → Now: ₹{s['curr_price']:,.2f}",
        ]
    if volume:
        lines += [
            f"📊 *Volume Surge: {volume['surge_factor']}× average*",
            f"   Current: {volume['current_vol']:,} | Avg: {volume['avg_vol']:,}",
        ]

    severity = "CRITICAL" if (
        s.get("severity") == "CRITICAL" or (volume and volume.get("severity") == "CRITICAL")
    ) else "HIGH"
    lines += [
        "",
        f"⚠️ Severity: *{severity}*",
        "_Positions: tighten SL. No new entries during spike window._",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def run(shared_state, send_telegram_fn=None) -> list:
    """
    Scan price_cache for spikes / volume surges.
    Stores alerts in shared_state["spike_alerts"] (list, cleared each cycle).
    Returns list of alert dicts.
    """
    price_cache = shared_state.get("price_cache", {})
    alerts      = []

    for symbol in WATCHLIST_SYMBOLS:
        entry = price_cache.get(symbol)
        if not entry:
            continue

        curr_price  = entry.get("price")
        curr_volume = entry.get("volume")

        if not curr_price:
            continue

        # ── Cooldown check ────────────────────────────────────────────────────
        if _cooldown_counter[symbol] > 0:
            _cooldown_counter[symbol] -= 1
            # Still update history so baseline stays current
            _price_history[symbol].append(curr_price)
            if curr_volume:
                _volume_history[symbol].append(curr_volume)
            continue

        # ── Spike detection ───────────────────────────────────────────────────
        spike_alert  = _check_price_spike(symbol, curr_price)
        volume_alert = _check_volume_surge(symbol, curr_volume) if curr_volume else None

        if spike_alert or volume_alert:
            base = spike_alert or volume_alert
            event = {
                **base,
                "timestamp":    datetime.now().isoformat(),
                "price_alert":  spike_alert,
                "volume_alert": volume_alert,
                "combined":     spike_alert is not None and volume_alert is not None,
            }
            # Elevate severity if both fire
            if event["combined"]:
                event["severity"] = "CRITICAL"

            alerts.append(event)
            _cooldown_counter[symbol] = ALERT_COOLDOWN_TICKS

            # Telegram alert
            if send_telegram_fn:
                try:
                    msg = _format_telegram_alert(
                        spike_alert or volume_alert,
                        volume_alert if spike_alert else None,
                    )
                    send_telegram_fn(msg)
                except Exception as e:
                    log.warning("Spike Telegram alert failed for %s: %s", symbol, e)

            log.warning("🚨 SPIKE ALERT [%s] %s | Δ=%.2f%% | Vol×=%.1f",
                        event["severity"], symbol,
                        (spike_alert or {}).get("delta_pct", 0),
                        (volume_alert or {}).get("surge_factor", 0))

        # ── Update history after detection (so history uses current tick) ─────
        _price_history[symbol].append(curr_price)
        if curr_volume:
            _volume_history[symbol].append(curr_volume)

    # Store in shared_state for downstream use (volatility circuit breaker, dashboard)
    shared_state["spike_alerts"]          = alerts
    shared_state["spike_detector_active"] = len(alerts) > 0
    if alerts:
        shared_state["last_spike_ts"] = datetime.now().isoformat()
        log.info("⚡ SpikeDetector: %d alert(s) fired this cycle", len(alerts))
    else:
        log.debug("SpikeDetector: clean cycle — no spikes")

    return alerts


def reset_history():
    """Clear all in-memory price/volume history (for testing)."""
    _price_history.clear()
    _volume_history.clear()
    _cooldown_counter.clear()
