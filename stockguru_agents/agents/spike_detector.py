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
SPIKE_PCT_THRESHOLD          = 1.5    # % price move in one tick → spike alert (equities/index)
OPTIONS_SPIKE_PCT_THRESHOLD  = 5.0    # % threshold for F&O options — naturally more volatile
FUTURES_SPIKE_PCT_THRESHOLD  = 1.0    # % threshold for index/stock futures (tighter than equity)
VOLUME_SURGE_FACTOR          = 3.0   # × trailing average volume → surge alert
VOLUME_WINDOW                = 5     # ticks of history for volume baseline
ALERT_COOLDOWN_TICKS         = 3     # suppress repeat alerts for same symbol for N ticks
WATCHLIST_SYMBOLS     = [
    "NIFTY 50", "BANK NIFTY", "SENSEX",
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "KOTAKBANK.NS", "WIPRO.NS", "AXISBANK.NS", "BAJFINANCE.NS",
]

import re as _re
# Regex patterns to auto-classify F&O symbols found in price_cache
_FNO_OPTIONS_RE = _re.compile(r'(?:NIFTY|BANKNIFTY|SENSEX|FINNIFTY)\s*\d{2}\w{3}\d{2,4}(?:PE|CE)|\d{4,6}(?:PE|CE)', _re.IGNORECASE)
_FNO_FUTURES_RE = _re.compile(r'(?:NIFTY|BANKNIFTY|SENSEX|FINNIFTY)\s*\d{2}\w{3}\d{2,4}FUT|(?:NIFTY|BANKNIFTY)FUT', _re.IGNORECASE)

def _classify_symbol(sym: str) -> str:
    """Return 'options', 'futures', or 'equity' for threshold selection."""
    if _FNO_OPTIONS_RE.search(sym):
        return "options"
    if _FNO_FUTURES_RE.search(sym):
        return "futures"
    # Heuristic: contains 5-digit strike price (e.g. '74500' in 'SENSEX 74500 PE')
    if _re.search(r'\b\d{4,6}\s*(PE|CE)\b', sym, _re.IGNORECASE):
        return "options"
    return "equity"

def _spike_threshold(sym: str) -> float:
    """Return the correct spike % threshold for this symbol type."""
    cls = _classify_symbol(sym)
    if cls == "options":  return OPTIONS_SPIKE_PCT_THRESHOLD
    if cls == "futures":  return FUTURES_SPIKE_PCT_THRESHOLD
    return SPIKE_PCT_THRESHOLD

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
    Uses per-symbol-type thresholds: equity 1.5%, futures 1.0%, options 5.0%.
    Returns a spike dict if |Δ%| ≥ threshold, else None.
    """
    hist = _price_history[symbol]
    if len(hist) < 1:
        return None

    prev_price = hist[-1]
    if prev_price == 0:
        return None

    delta_pct  = (current_price - prev_price) / prev_price * 100
    threshold  = _spike_threshold(symbol)
    if abs(delta_pct) < threshold:
        return None

    direction = "UP" if delta_pct > 0 else "DOWN"
    sym_type  = _classify_symbol(symbol)
    return {
        "type":        "PRICE_SPIKE",
        "symbol":      symbol,
        "sym_type":    sym_type,        # 'equity' | 'futures' | 'options'
        "prev_price":  round(prev_price, 2),
        "curr_price":  round(current_price, 2),
        "delta_pct":   round(delta_pct, 2),
        "direction":   direction,
        "severity":    "CRITICAL" if abs(delta_pct) >= threshold * 2 else "HIGH",
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
    s        = spike
    sym_type = s.get("sym_type", "equity")
    type_tag = {"options": "🎯 F&O OPTIONS", "futures": "📦 FUTURES", "equity": "📈 EQUITY"}.get(sym_type, "")

    lines = [
        f"🚨 *SPIKE ALERT — {s['symbol']}*",
        f"🏷 {type_tag} | ⏰ {datetime.now().strftime('%H:%M:%S')} IST",
        "",
    ]
    if s["type"] == "PRICE_SPIKE":
        arrow = "📈" if s["direction"] == "UP" else "📉"
        lines += [
            f"{arrow} *Price {s['direction']}: {s['delta_pct']:+.2f}% in one tick*",
            f"   Prev: ₹{s['prev_price']:,.2f} → Now: ₹{s['curr_price']:,.2f}",
        ]
        if sym_type == "options":
            lines.append(f"   _(Options threshold: {OPTIONS_SPIKE_PCT_THRESHOLD}% — this is a major move)_")
    if volume:
        lines += [
            f"📊 *Volume Surge: {volume['surge_factor']}× average*",
            f"   Current: {volume['current_vol']:,} | Avg: {volume['avg_vol']:,}",
        ]

    severity = "CRITICAL" if (
        s.get("severity") == "CRITICAL" or (volume and volume.get("severity") == "CRITICAL")
    ) else "HIGH"
    action = ("_Options spike: exit or hedge the position immediately if holding._"
              if sym_type == "options"
              else "_Positions: tighten SL. No new entries during spike window._")
    lines += [
        "",
        f"⚠️ Severity: *{severity}*",
        action,
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def run(shared_state, send_telegram_fn=None) -> list:
    """
    Scan price_cache for spikes / volume surges.
    Covers:
      1. Core WATCHLIST_SYMBOLS (equities + indices)
      2. Any F&O options / futures symbols present in price_cache this cycle
      3. Any symbols currently held in open positions (so open legs are always watched)

    Uses per-type thresholds: equity 1.5% | futures 1.0% | options 5.0%
    Stores alerts in shared_state["spike_alerts"] (list, cleared each cycle).
    Returns list of alert dicts.
    """
    price_cache = shared_state.get("price_cache", {})
    alerts      = []

    # Build the full scan set: watchlist + active F&O from price_cache + open positions
    fno_from_cache   = {sym for sym in price_cache if _classify_symbol(sym) in ("options", "futures")}
    open_pos_symbols = set()
    for pos in shared_state.get("open_positions", []):
        sym = pos.get("symbol") or pos.get("tradingsymbol") or ""
        if sym:
            open_pos_symbols.add(sym)

    scan_symbols = list(set(WATCHLIST_SYMBOLS) | fno_from_cache | open_pos_symbols)

    for symbol in scan_symbols:
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
    _cooldown_counter.clear()   # fix: was missing — caused tests to fail silently


# ══════════════════════════════════════════════════════════════════════════════
# PRE-SPIKE DETECTOR — detects conditions BEFORE the explosive move
# ══════════════════════════════════════════════════════════════════════════════
# Theory:
#   Spikes don't happen randomly. Before a large move, smart money/algos
#   leave forensic traces: rapid OI build, unusual volume, IV squeeze,
#   PCR flips, EMA reclaims, bid-ask compression. Catching 4-5 of these
#   concurrently with score >= 75 means an explosive move is likely in 1-3
#   cycles (15-45 minutes). Enter small, tight SL, asymmetric reward.
# ══════════════════════════════════════════════════════════════════════════════

# OI history for velocity calculation (symbol → deque of OI readings)
_oi_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=4))
# IV history for percentile calculation
_iv_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
# Price history for EMA approximation
_ema_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
# PCR history for delta calculation
_pcr_history: deque = deque(maxlen=5)

PRE_SPIKE_TRIGGER_SCORE = 75   # fire Telegram alert when score >= this
PRE_SPIKE_COOLDOWN_TICKS = 4   # suppress repeat pre-spike alerts

_pre_spike_cooldown: dict[str, int] = defaultdict(int)


def compute_pre_spike_score(symbol: str, shared_state: dict) -> dict:
    """
    Score 0-100 based on 6 pre-spike forensic signals.
    Returns dict with score, signals fired, and readable reason.

    Signals (each contributes up to ~17 points):
        1. OI Velocity     — rapid OI build (>15% in one cycle)
        2. Volume Surge    — current vol > 3× trailing avg
        3. IV Percentile   — implied volatility >80th percentile (tension building)
        4. PCR Delta       — PCR dropping sharply (<-0.20) = call buying dominates
        5. EMA Reclaim     — price crosses above its short EMA (momentum ignition)
        6. Bid-Ask Compr.  — tight spread = institutions absorbing at market (proxy)
    """
    signals_fired = []
    score         = 0
    details       = {}

    price_cache  = shared_state.get("price_cache", {})
    options_flow = shared_state.get("options_flow", {})
    entry        = price_cache.get(symbol, {})
    curr_price   = entry.get("price", 0)
    curr_vol     = entry.get("volume", 0)

    if not curr_price:
        return {"score": 0, "signals": [], "details": {}, "reason": "No price data"}

    # ── SIGNAL 1: OI VELOCITY ─────────────────────────────────────────────────
    # Options OI building rapidly → big players loading positions for imminent move
    oi_data = options_flow.get("oi_by_symbol", {}).get(symbol) or options_flow.get("total_oi", {})
    curr_oi = oi_data.get("call_oi", 0) + oi_data.get("put_oi", 0) if isinstance(oi_data, dict) else 0
    if curr_oi > 0:
        _oi_history[symbol].append(curr_oi)
        if len(_oi_history[symbol]) >= 2:
            prev_oi = _oi_history[symbol][-2]
            if prev_oi > 0:
                oi_vel = (curr_oi - prev_oi) / prev_oi * 100
                details["oi_velocity"] = round(oi_vel, 1)
                if oi_vel >= 25:
                    score += 20; signals_fired.append(f"OI velocity +{oi_vel:.0f}% (extreme build)")
                elif oi_vel >= 15:
                    score += 14; signals_fired.append(f"OI velocity +{oi_vel:.0f}% (strong build)")

    # ── SIGNAL 2: VOLUME SURGE RATIO ─────────────────────────────────────────
    # 3× volume = institutional accumulation ahead of move
    vol_hist = _volume_history.get(symbol)
    if vol_hist and len(vol_hist) >= 3 and curr_vol:
        avg_vol = sum(list(vol_hist)[:-1]) / (len(vol_hist) - 1)
        if avg_vol > 0:
            vol_ratio = curr_vol / avg_vol
            details["vol_ratio"] = round(vol_ratio, 1)
            if vol_ratio >= 5.0:
                score += 20; signals_fired.append(f"Volume {vol_ratio:.1f}× avg (very unusual)")
            elif vol_ratio >= 3.0:
                score += 14; signals_fired.append(f"Volume {vol_ratio:.1f}× avg (surge)")
            elif vol_ratio >= 2.0:
                score += 7;  signals_fired.append(f"Volume {vol_ratio:.1f}× avg (elevated)")

    # ── SIGNAL 3: IV PERCENTILE ───────────────────────────────────────────────
    # IV building before move (like spring being compressed)
    curr_iv = options_flow.get("iv_rank") or options_flow.get("iv_percentile", 0)
    if isinstance(curr_iv, (int, float)) and curr_iv > 0:
        _iv_history[symbol].append(curr_iv)
        details["iv_pct"] = curr_iv
        if curr_iv >= 85:
            score += 18; signals_fired.append(f"IV={curr_iv:.0f}th pct (extreme tension)")
        elif curr_iv >= 70:
            score += 12; signals_fired.append(f"IV={curr_iv:.0f}th pct (elevated)")
        elif curr_iv >= 55:
            score += 6;  signals_fired.append(f"IV={curr_iv:.0f}th pct (building)")

    # ── SIGNAL 4: PCR DELTA ───────────────────────────────────────────────────
    # PCR dropping = traders buying calls aggressively = bullish smart money
    curr_pcr = options_flow.get("pcr") or options_flow.get("put_call_ratio", 1.0)
    try: curr_pcr = float(curr_pcr)
    except: curr_pcr = 1.0
    _pcr_history.append(curr_pcr)
    if len(_pcr_history) >= 2:
        pcr_delta = curr_pcr - _pcr_history[-2]
        details["pcr"] = round(curr_pcr, 3)
        details["pcr_delta"] = round(pcr_delta, 3)
        if pcr_delta <= -0.30:
            score += 18; signals_fired.append(f"PCR delta {pcr_delta:+.2f} (strong call buying)")
        elif pcr_delta <= -0.15:
            score += 12; signals_fired.append(f"PCR delta {pcr_delta:+.2f} (call buying surge)")
        elif pcr_delta <= -0.05:
            score += 5;  signals_fired.append(f"PCR delta {pcr_delta:+.2f} (mild call buying)")

    # ── SIGNAL 5: EMA RECLAIM / MOMENTUM IGNITION ─────────────────────────────
    # Price crossing above short EMA = momentum ignition — machines follow this
    _ema_history[symbol].append(curr_price)
    if len(_ema_history[symbol]) >= 5:
        prices_list = list(_ema_history[symbol])
        # Simple 5-period EMA approximation
        k = 2 / (5 + 1)
        ema = prices_list[0]
        for p in prices_list[1:]:
            ema = p * k + ema * (1 - k)
        details["ema5"] = round(ema, 2)
        ema_gap = (curr_price - ema) / ema * 100
        details["ema_gap_pct"] = round(ema_gap, 2)
        prev_price_h = list(_ema_history[symbol])[-2] if len(_ema_history[symbol]) >= 2 else curr_price
        just_crossed_above = prev_price_h <= ema <= curr_price
        if just_crossed_above:
            score += 18; signals_fired.append(f"EMA reclaim (just crossed above EMA5={ema:.0f})")
        elif 0 < ema_gap < 0.5:
            score += 10; signals_fired.append(f"Price just above EMA5 +{ema_gap:.2f}% (coiling)")
        elif ema_gap < 0 and ema_gap > -0.3:
            score += 6;  signals_fired.append(f"Price below EMA5 {ema_gap:.2f}% (pre-reclaim zone)")

    # ── SIGNAL 6: BID-ASK SPREAD COMPRESSION ─────────────────────────────────
    # Tight spread = institutions absorbing the book = move about to happen
    bid  = entry.get("bid", 0)
    ask  = entry.get("ask", 0)
    if bid and ask and bid > 0:
        spread_pct = (ask - bid) / bid * 100
        details["spread_pct"] = round(spread_pct, 3)
        if spread_pct < 0.03:
            score += 12; signals_fired.append(f"Bid-ask spread {spread_pct:.3f}% (very tight — absorption)")
        elif spread_pct < 0.08:
            score += 6;  signals_fired.append(f"Bid-ask spread {spread_pct:.3f}% (tight)")

    score = min(score, 100)
    reason = (
        f"Pre-spike score {score}/100: {'; '.join(signals_fired[:4]) or 'No strong signals'}"
        if signals_fired else f"Pre-spike score {score}/100: No significant pre-spike signals detected"
    )

    return {
        "symbol":        symbol,
        "score":         score,
        "signals_count": len(signals_fired),
        "signals":       signals_fired,
        "details":       details,
        "reason":        reason,
    }


def _format_pre_spike_telegram(result: dict, price: float) -> str:
    """Telegram message for a pre-spike detection."""
    sym    = result["symbol"]
    score  = result["score"]
    sigs   = result["signals"]
    lines  = [
        f"⚡ *PRE-SPIKE ALERT — {sym}*",
        f"📊 Score: *{score}/100* | CMP: ₹{price:,.2f}",
        f"⏰ {datetime.now().strftime('%d %b %H:%M')} IST",
        "",
        "*Signals Fired:*",
    ]
    for sig in sigs[:5]:
        lines.append(f"  • {sig}")
    lines += [
        "",
        f"🎯 *Action:* Enter small position now, tight SL 1.5% below CMP.",
        f"   Target: explosive move within 15-45 minutes.",
        f"   Theory: {score}+ = 4+ forensic traces of imminent large move.",
        "",
        "_⚠️ Simulation only — not financial advice_",
    ]
    return "\n".join(lines)


def scan_pre_spikes(shared_state: dict, send_telegram_fn=None) -> list:
    """
    Scan all watchlist stocks for pre-spike conditions.
    Fires Telegram when score >= PRE_SPIKE_TRIGGER_SCORE.
    Returns list of high-score pre-spike results.
    """
    price_cache = shared_state.get("price_cache", {})
    pre_spikes  = []

    # Scan all available tickers (not just watchlist)
    all_symbols = list(set(WATCHLIST_SYMBOLS) | set(price_cache.keys()))

    for symbol in all_symbols:
        # Cooldown check
        if _pre_spike_cooldown[symbol] > 0:
            _pre_spike_cooldown[symbol] -= 1
            continue

        result = compute_pre_spike_score(symbol, shared_state)
        if result["score"] <= 0:
            continue

        result["ts"] = datetime.now().strftime("%H:%M:%S")
        price = price_cache.get(symbol, {}).get("price", 0)

        if result["score"] >= PRE_SPIKE_TRIGGER_SCORE:
            pre_spikes.append(result)
            _pre_spike_cooldown[symbol] = PRE_SPIKE_COOLDOWN_TICKS

            log.warning("⚡ PRE-SPIKE [%s] score=%d | %s",
                        symbol, result["score"],
                        "; ".join(result["signals"][:2]))

            if send_telegram_fn and price:
                try:
                    send_telegram_fn(_format_pre_spike_telegram(result, price))
                except Exception as e:
                    log.warning("Pre-spike Telegram failed %s: %s", symbol, e)

    # Store in shared_state
    if pre_spikes:
        shared_state["pre_spike_alerts"] = pre_spikes
        shared_state["pre_spike_last_ts"] = datetime.now().isoformat()
        log.info("⚡ PRE-SPIKE SCAN: %d high-score setups found", len(pre_spikes))
    else:
        shared_state.setdefault("pre_spike_alerts", [])

    return pre_spikes
