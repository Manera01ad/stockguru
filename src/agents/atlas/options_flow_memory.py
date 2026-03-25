# ══════════════════════════════════════════════════════════════════════════════
# ATLAS MODULE 1 — OPTIONS FLOW MEMORY
# ══════════════════════════════════════════════════════════════════════════════
# The market's most honest signal — options traders put real money behind
# their conviction. This module captures and learns from:
#
#   • Historical PCR (Put-Call Ratio) → market outcome mapping
#   • Unusual OI buildup at specific strikes → institutional positioning
#   • IV Percentile patterns → when is market underpricing/overpricing risk
#   • Max Pain drift → how markets migrate toward max pain at expiry
#   • PCR reversal signals → when extreme PCR flips (contrarian setups)
#   • Options-technical confluence → PCR + RSI + regime = best entries
#
# Learning questions answered:
#   "What % of trades succeeded when PCR < 0.65 in BULL regime?"
#   "How often does market mean-revert when PCR > 1.4?"
#   "Which IV percentile zones produce the cleanest breakouts?"
# ══════════════════════════════════════════════════════════════════════════════

import json
import os
import logging
from datetime import datetime, timedelta

log = logging.getLogger("atlas.options_flow_memory")

_BASE       = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
HISTORY_PATH = os.path.join(_BASE, "options_flow_history.json")
INSIGHTS_PATH = os.path.join(_BASE, "options_flow_insights.json")


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(_BASE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# PCR ZONE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

PCR_ZONES = {
    (0.0,  0.55): {"label": "EXTREME_EUPHORIA", "signal": "STRONG_SELL",   "contrarian": True,  "emoji": "🔴🔴"},
    (0.55, 0.65): {"label": "EUPHORIA",         "signal": "CAUTION",       "contrarian": True,  "emoji": "🔴"},
    (0.65, 0.80): {"label": "BULLISH",           "signal": "BUY",           "contrarian": False, "emoji": "🟢"},
    (0.80, 1.00): {"label": "NEUTRAL_BULL",      "signal": "BUY_MILD",      "contrarian": False, "emoji": "🟡"},
    (1.00, 1.15): {"label": "NEUTRAL_BEAR",      "signal": "HOLD",          "contrarian": False, "emoji": "🟡"},
    (1.15, 1.30): {"label": "FEAR",              "signal": "AVOID_NEW",     "contrarian": False, "emoji": "🟠"},
    (1.30, 1.50): {"label": "EXTREME_FEAR",      "signal": "CONTRARIAN_BUY","contrarian": True,  "emoji": "🟢🟢"},
    (1.50, 9.99): {"label": "CAPITULATION",      "signal": "STRONG_BUY",    "contrarian": True,  "emoji": "🟢🟢🟢"},
}


def classify_pcr(pcr: float) -> dict:
    """Classify a PCR value into zone with signal."""
    if pcr is None:
        return {"label": "UNKNOWN", "signal": "NEUTRAL", "contrarian": False, "emoji": "⚪"}
    for (lo, hi), info in PCR_ZONES.items():
        if lo <= pcr < hi:
            return {**info, "pcr": pcr, "zone_range": f"{lo}-{hi}"}
    return {"label": "UNKNOWN", "signal": "NEUTRAL", "contrarian": False, "emoji": "⚪", "pcr": pcr}


# ─────────────────────────────────────────────────────────────────────────────
# RECORD OPTIONS SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

def record_options_snapshot(
    symbol: str,                # "NIFTY" or "BANKNIFTY"
    pcr: float,
    max_pain: float,
    spot_price: float,
    iv_percentile: float,
    call_oi: int,
    put_oi: int,
    unusual_oi_strikes: list,   # list of dicts: {strike, side, oi_spike_ratio}
    expiry_days: int,
    market_regime: str = None,
) -> dict:
    """
    Record a point-in-time options snapshot.
    Called every 15 minutes by options_flow agent.
    Returns classified signal for immediate use.
    """
    history = _load(HISTORY_PATH, [])

    pcr_info  = classify_pcr(pcr)
    iv_signal = _classify_iv(iv_percentile)
    pain_dist = _max_pain_distance(spot_price, max_pain)

    snapshot = {
        "timestamp":        datetime.now().isoformat(),
        "symbol":           symbol,
        "pcr":              round(pcr, 3) if pcr else None,
        "pcr_zone":         pcr_info["label"],
        "pcr_signal":       pcr_info["signal"],
        "max_pain":         max_pain,
        "spot_price":       spot_price,
        "max_pain_dist_pct": pain_dist,
        "iv_percentile":    iv_percentile,
        "iv_signal":        iv_signal,
        "call_oi":          call_oi,
        "put_oi":           put_oi,
        "unusual_oi_strikes": unusual_oi_strikes or [],
        "has_unusual_oi":   len(unusual_oi_strikes or []) > 0,
        "expiry_days":      expiry_days,
        "market_regime":    market_regime,
        "composite_signal": _compute_composite_signal(pcr_info, iv_signal, pain_dist, unusual_oi_strikes),
    }

    history.append(snapshot)
    # Keep last 500 snapshots
    if len(history) > 500:
        history = history[-500:]

    _save(HISTORY_PATH, history)
    return snapshot


def _classify_iv(iv_pct: float) -> str:
    if iv_pct is None:  return "UNKNOWN"
    if iv_pct < 15:     return "VERY_LOW"     # sell premium hard to do
    if iv_pct < 30:     return "LOW"          # good for long options
    if iv_pct < 50:     return "NORMAL"
    if iv_pct < 70:     return "ELEVATED"     # caution on long options
    if iv_pct < 85:     return "HIGH"         # favour selling
    return "EXTREME"                           # sell premium / expect mean revert


def _max_pain_distance(spot: float, max_pain: float) -> float:
    if not spot or not max_pain:
        return None
    return round(((max_pain - spot) / spot) * 100, 2)


def _compute_composite_signal(pcr_info: dict, iv_signal: str, pain_dist: float,
                               unusual_oi: list) -> str:
    """
    Combine PCR + IV + Max Pain distance + unusual OI into one signal.
    Returns: STRONG_BUY / BUY / NEUTRAL / AVOID / STRONG_SELL
    """
    score = 0

    # PCR contribution
    pcr_scores = {
        "STRONG_SELL": -2, "CAUTION": -1, "BUY": +1, "BUY_MILD": +1,
        "HOLD": 0, "AVOID_NEW": -1, "CONTRARIAN_BUY": +2, "STRONG_BUY": +3,
    }
    score += pcr_scores.get(pcr_info.get("signal", "HOLD"), 0)

    # IV contribution (low IV = good for directional, high = risky)
    iv_scores = {"VERY_LOW": +1, "LOW": +1, "NORMAL": 0, "ELEVATED": -1, "HIGH": -1, "EXTREME": -2}
    score += iv_scores.get(iv_signal, 0)

    # Max Pain gravity (if spot below max pain, market might pull up)
    if pain_dist is not None:
        if pain_dist > 1.5:   score += 1    # max pain significantly above spot → bullish pull
        elif pain_dist < -1.5: score -= 1   # max pain below spot → bearish pull

    # Unusual OI (smart money moving)
    unusual_calls = [x for x in (unusual_oi or []) if x.get("side") == "CALL"]
    unusual_puts  = [x for x in (unusual_oi or []) if x.get("side") == "PUT"]
    if len(unusual_calls) > len(unusual_puts): score += 1
    elif len(unusual_puts) > len(unusual_calls): score -= 1

    if score >= 3:   return "STRONG_BUY"
    if score >= 1:   return "BUY"
    if score == 0:   return "NEUTRAL"
    if score >= -1:  return "AVOID"
    return "STRONG_SELL"


# ─────────────────────────────────────────────────────────────────────────────
# LEARN FROM HISTORY
# ─────────────────────────────────────────────────────────────────────────────

def build_pcr_outcome_map(signal_history: list) -> dict:
    """
    Cross-reference options snapshots with trade outcomes.
    For each PCR zone, compute: how often did the market move as expected?

    signal_history: list of dicts from signal_tracker (with outcomes)
    Returns: dict of {pcr_zone: {expected_moves, actual_wins, win_rate, avg_move}}
    """
    history = _load(HISTORY_PATH, [])
    if not history or not signal_history:
        return {}

    # Build time-indexed PCR lookup
    pcr_by_time = {}
    for snap in history:
        if snap.get("symbol") == "NIFTY":
            ts = snap["timestamp"][:16]  # truncate to minute
            pcr_by_time[ts] = snap

    outcome_map = {}

    for trade in signal_history:
        if trade.get("outcome") in ("OPEN", "EXPIRED"):
            continue

        issued_ts = (trade.get("issued_at") or "")[:16]
        snap = pcr_by_time.get(issued_ts)

        if not snap:
            # Try ±5 minute window
            for snap_ts, s in pcr_by_time.items():
                if abs(_ts_diff_mins(issued_ts, snap_ts)) <= 5:
                    snap = s
                    break

        if not snap:
            continue

        zone = snap.get("pcr_zone", "UNKNOWN")
        is_win = trade.get("outcome") in ("T1_HIT", "T2_HIT")
        pnl = trade.get("pnl_pct", 0) or 0

        if zone not in outcome_map:
            outcome_map[zone] = {"trades": 0, "wins": 0, "pnls": [], "win_rate": 0.0}

        outcome_map[zone]["trades"] += 1
        outcome_map[zone]["wins"] += 1 if is_win else 0
        outcome_map[zone]["pnls"].append(pnl)

    # Compute win rates
    for zone, stats in outcome_map.items():
        n = stats["trades"]
        if n > 0:
            stats["win_rate"] = round(stats["wins"] / n, 3)
            stats["avg_pnl"]  = round(sum(stats["pnls"]) / n, 2)
        del stats["pnls"]

    return outcome_map


def _ts_diff_mins(ts1: str, ts2: str) -> float:
    try:
        t1 = datetime.fromisoformat(ts1)
        t2 = datetime.fromisoformat(ts2)
        return (t1 - t2).total_seconds() / 60
    except Exception:
        return 999


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER (called before each trade signal)
# ─────────────────────────────────────────────────────────────────────────────

def get_options_context(pcr_nifty: float = None, pcr_banknifty: float = None,
                        iv_percentile: float = None, limit_history: int = 5) -> dict:
    """
    Returns rich options context for Claude Intelligence.
    Called before each trade decision.
    """
    history = _load(HISTORY_PATH, [])
    insights = _load(INSIGHTS_PATH, {})

    nifty_info    = classify_pcr(pcr_nifty)
    banknifty_info = classify_pcr(pcr_banknifty)

    # Recent trend: is PCR rising or falling?
    recent_pcrs = []
    for snap in reversed(history[-20:]):
        if snap.get("symbol") == "NIFTY" and snap.get("pcr"):
            recent_pcrs.append(snap["pcr"])
    pcr_trend = "RISING" if (len(recent_pcrs) >= 2 and recent_pcrs[0] > recent_pcrs[-1]) else \
                "FALLING" if (len(recent_pcrs) >= 2 and recent_pcrs[0] < recent_pcrs[-1]) else "STABLE"

    # Historical win rate at current PCR zone
    zone = nifty_info.get("label")
    zone_stats = insights.get("pcr_outcome_map", {}).get(zone, {})

    return {
        "nifty_pcr":         pcr_nifty,
        "nifty_pcr_zone":    nifty_info["label"],
        "nifty_pcr_signal":  nifty_info["signal"],
        "banknifty_pcr":     pcr_banknifty,
        "banknifty_signal":  banknifty_info["signal"],
        "iv_percentile":     iv_percentile,
        "iv_signal":         _classify_iv(iv_percentile),
        "pcr_trend":         pcr_trend,
        "zone_win_rate":     zone_stats.get("win_rate"),
        "zone_trade_count":  zone_stats.get("trades", 0),
        "zone_avg_pnl":      zone_stats.get("avg_pnl"),
        "historical_insight": (
            f"PCR zone {zone}: {zone_stats.get('win_rate', '?')*100:.0f}% win rate "
            f"over {zone_stats.get('trades', 0)} trades"
            if zone_stats.get("trades", 0) >= 5 else
            f"PCR zone {zone}: insufficient history yet"
        ),
    }


def rebuild_insights(signal_history: list) -> dict:
    """Rebuild and save the options insights file. Called by self_upgrader nightly."""
    insights = {
        "pcr_outcome_map": build_pcr_outcome_map(signal_history),
        "updated_at": datetime.now().isoformat(),
    }
    _save(INSIGHTS_PATH, insights)
    log.info("📊 Options Flow Memory: Insights rebuilt | %d PCR zones mapped",
             len(insights["pcr_outcome_map"]))
    return insights


def get_current_snapshot(symbol: str = "NIFTY") -> dict:
    """Get the most recent options snapshot."""
    history = _load(HISTORY_PATH, [])
    for snap in reversed(history):
        if snap.get("symbol") == symbol:
            return snap
    return {}
