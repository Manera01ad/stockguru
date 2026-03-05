# ══════════════════════════════════════════════════════════════════════════════
# ATLAS MODULE 3 — MARKET REGIME & TIME PATTERN DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
# Markets behave differently depending on WHEN you are trading.
# This module detects and records:
#
# MARKET REGIME (macro state):
#   BULL_TREND    — Nifty above 200-EMA, FII buying, breadth positive
#   BEAR_TREND    — Nifty below 200-EMA, FII selling, breadth negative
#   SIDEWAYS      — Range-bound, no clear direction
#   VOLATILE      — High VIX, swinging both ways, news-driven
#   RECOVERY      — Bouncing from deep lows, early accumulation
#
# TIME PATTERNS (when to trade):
#   Session:    PRE_OPEN / FIRST_HOUR / MID_SESSION / LAST_HOUR / POST
#   Day:        MON-FRI (Monday opens / Friday closes have patterns)
#   Week type:  EXPIRY_WEEK / BUDGET_WEEK / EARNINGS_SEASON / NORMAL
#   Month:      Beginning-of-month (FII rebalancing) / End-of-month
#
# Learning questions:
#   "What % of strong entries in BULL_TREND vs SIDEWAYS succeed?"
#   "Is the last hour of expiry week unusually volatile?"
#   "Do Monday breakouts hold better than Friday breakouts?"
#   "Are mid-session signals more reliable than first-hour signals?"
# ══════════════════════════════════════════════════════════════════════════════

import json
import os
import logging
from datetime import datetime, date, timedelta

log = logging.getLogger("atlas.regime")

_BASE          = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
REGIME_LOG_PATH = os.path.join(_BASE, "regime_history.json")
TIME_STATS_PATH = os.path.join(_BASE, "time_pattern_stats.json")


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
# REGIME DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_regime(
    nifty_price: float,
    nifty_ema200: float,
    nifty_ema50: float,
    nifty_rsi: float,
    vix: float,
    fii_flow: str,          # "BUYING" / "SELLING" / "NEUTRAL"
    advance_decline: float, # A/D ratio (>1 = breadth positive)
    pcr_nifty: float = None,
) -> dict:
    """
    Classify the current market regime using multiple signals.
    Returns: {regime, strength, description, trading_bias}
    """
    score = 0
    signals = []

    # Nifty vs EMA200 (most important)
    if nifty_ema200:
        if nifty_price > nifty_ema200 * 1.02:
            score += 3
            signals.append("price_above_200ema")
        elif nifty_price > nifty_ema200:
            score += 1
            signals.append("price_just_above_200ema")
        elif nifty_price < nifty_ema200 * 0.98:
            score -= 3
            signals.append("price_below_200ema")
        else:
            score -= 1
            signals.append("price_just_below_200ema")

    # EMA50 alignment
    if nifty_ema50:
        if nifty_price > nifty_ema50:
            score += 1
            signals.append("above_50ema")
        else:
            score -= 1
            signals.append("below_50ema")

    # RSI regime
    if nifty_rsi:
        if nifty_rsi > 60:
            score += 1
            signals.append("rsi_bullish")
        elif nifty_rsi < 40:
            score -= 1
            signals.append("rsi_bearish")

    # FII flow
    if fii_flow == "BUYING":
        score += 2
        signals.append("fii_buying")
    elif fii_flow == "SELLING":
        score -= 2
        signals.append("fii_selling")

    # A/D ratio
    if advance_decline:
        if advance_decline > 1.5:
            score += 1
            signals.append("breadth_positive")
        elif advance_decline < 0.7:
            score -= 1
            signals.append("breadth_negative")

    # VIX (volatility measure)
    volatility_flag = False
    if vix:
        if vix > 22:
            volatility_flag = True
            signals.append("vix_elevated")
        elif vix > 18:
            signals.append("vix_moderate")

    # Determine regime
    if volatility_flag and abs(score) < 3:
        regime = "VOLATILE"
        strength = 0.5
        bias = "REDUCE_SIZE"
    elif score >= 5:
        regime = "BULL_TREND"
        strength = min(1.0, score / 8)
        bias = "AGGRESSIVE_LONG"
    elif score >= 2:
        regime = "BULL_TREND"
        strength = min(0.7, score / 8)
        bias = "LONG_BIAS"
    elif score <= -5:
        regime = "BEAR_TREND"
        strength = min(1.0, abs(score) / 8)
        bias = "AVOID_LONGS"
    elif score <= -2:
        regime = "BEAR_TREND"
        strength = min(0.7, abs(score) / 8)
        bias = "REDUCE_LONGS"
    else:
        regime = "SIDEWAYS"
        strength = 0.3
        bias = "RANGE_TRADE"

    # Recovery detection: recent deep lows + momentum turning
    if nifty_rsi and nifty_rsi < 35 and score > -3:
        regime = "RECOVERY"
        bias = "SELECTIVE_LONGS"

    return {
        "regime":      regime,
        "strength":    round(strength, 2),
        "score":       score,
        "signals":     signals,
        "trading_bias": bias,
        "vix":         vix,
        "fii_flow":    fii_flow,
        "description": _regime_description(regime, score, signals),
    }


def _regime_description(regime: str, score: int, signals: list) -> str:
    desc_map = {
        "BULL_TREND":  "Market in uptrend — favour longs, breakouts valid",
        "BEAR_TREND":  "Market in downtrend — avoid new longs, wait for reversal",
        "SIDEWAYS":    "Range-bound market — focus on support/resistance levels",
        "VOLATILE":    "High volatility regime — reduce position sizes, wider stops",
        "RECOVERY":    "Market recovering from lows — early accumulation possible",
    }
    return desc_map.get(regime, "Unknown regime")


# ─────────────────────────────────────────────────────────────────────────────
# TIME CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

def get_time_context(dt: datetime = None) -> dict:
    """
    Returns comprehensive time context for the current moment.
    This is fed into every trade entry snapshot.
    """
    dt = dt or datetime.now()

    # Market session
    hour = dt.hour
    minute = dt.minute
    total_mins = hour * 60 + minute

    if total_mins < 9 * 60 + 15:
        session = "PRE_OPEN"
    elif total_mins < 10 * 60:
        session = "FIRST_HOUR"
    elif total_mins < 13 * 60:
        session = "MID_SESSION"
    elif total_mins < 14 * 60 + 45:
        session = "POWER_HOUR"
    elif total_mins < 15 * 60 + 30:
        session = "LAST_HOUR"
    else:
        session = "POST_MARKET"

    # Day of week
    day_map = {0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI"}
    day = day_map.get(dt.weekday(), "SAT")

    # Week type
    week_type = _classify_week_type(dt)

    # Month position
    dom = dt.day
    if dom <= 5:
        month_position = "MONTH_START"    # FII typically deploy fresh capital
    elif dom >= 25:
        month_position = "MONTH_END"      # rebalancing flows
    else:
        month_position = "MID_MONTH"

    # Special session patterns
    session_notes = _get_session_notes(session, day, week_type)

    return {
        "session":        session,
        "day_of_week":    day,
        "week_type":      week_type,
        "month_position": month_position,
        "hour":           hour,
        "date":           dt.strftime("%Y-%m-%d"),
        "session_notes":  session_notes,
        "is_expiry_week": week_type == "EXPIRY_WEEK",
        "is_earnings_season": week_type == "EARNINGS_SEASON",
    }


def _classify_week_type(dt: datetime) -> str:
    """Classify the current week type."""
    # NSE monthly expiry = last Thursday of the month
    last_thursday = _last_thursday_of_month(dt.year, dt.month)
    days_to_expiry = (last_thursday - dt.date()).days

    if 0 <= days_to_expiry <= 4:
        return "EXPIRY_WEEK"

    # Earnings season: Apr 15 - May 15, Jul 15 - Aug 15, Oct 15 - Nov 15, Jan 15 - Feb 15
    month = dt.month
    day   = dt.day
    earnings_periods = [(4, 15, 5, 15), (7, 15, 8, 15), (10, 15, 11, 15), (1, 15, 2, 15)]
    for sm, sd, em, ed in earnings_periods:
        start = date(dt.year, sm, sd)
        end   = date(dt.year, em, ed)
        if start <= dt.date() <= end:
            return "EARNINGS_SEASON"

    # Union Budget: Feb 1
    if month == 2 and day <= 7:
        return "BUDGET_WEEK"

    return "NORMAL"


def _last_thursday_of_month(year: int, month: int) -> date:
    """Find last Thursday of a given month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    offset = (last_day.weekday() - 3) % 7  # 3 = Thursday
    return last_day - timedelta(days=offset)


def _get_session_notes(session: str, day: str, week_type: str) -> str:
    """Return human-readable notes about current trading conditions."""
    notes = []

    session_notes = {
        "PRE_OPEN":    "Pre-open: Await gap direction before entering",
        "FIRST_HOUR":  "First hour: Often volatile, wait for 10:00 confirmation",
        "MID_SESSION": "Mid-session: Steadiest trends, best for continuation",
        "POWER_HOUR":  "Power hour: Momentum can extend, also reversal risk",
        "LAST_HOUR":   "Last hour: Institutional squaring, avoid new entries",
        "POST_MARKET": "Post-market: Plan tomorrow's watchlist",
    }
    notes.append(session_notes.get(session, ""))

    if day == "MON":
        notes.append("Monday open: Often gaps up/down from weekend news")
    elif day == "FRI":
        notes.append("Friday: Avoid carry positions over weekend")

    if week_type == "EXPIRY_WEEK":
        notes.append("Expiry week: Options gamma high, max pain gravity in play")
    elif week_type == "EARNINGS_SEASON":
        notes.append("Earnings season: Avoid entries 2 days before results")
    elif week_type == "BUDGET_WEEK":
        notes.append("Budget week: High uncertainty, reduce position sizes")

    return " | ".join(filter(None, notes))


# ─────────────────────────────────────────────────────────────────────────────
# RECORD & LEARN
# ─────────────────────────────────────────────────────────────────────────────

def record_regime_snapshot(regime_data: dict, nifty_price: float, vix: float) -> None:
    """Record hourly regime snapshots for historical analysis."""
    history = _load(REGIME_LOG_PATH, [])
    entry = {
        "timestamp":  datetime.now().isoformat(),
        "nifty":      nifty_price,
        "vix":        vix,
        **regime_data
    }
    history.append(entry)
    if len(history) > 1000:
        history = history[-1000:]
    _save(REGIME_LOG_PATH, history)


def build_time_pattern_stats(signal_history: list) -> dict:
    """
    Learn which sessions/days/week_types have the best signal win rates.
    Called nightly by self_upgrader.
    """
    from stockguru_agents.atlas.core import _get_conn
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT market_session, day_of_week, week_type, regime,
                   outcome, pnl_pct
            FROM knowledge_events
            WHERE outcome NOT IN ('OPEN', 'EXPIRED')
        """).fetchall()
    except Exception:
        rows = []

    if not rows:
        return {}

    from collections import defaultdict
    stats = defaultdict(lambda: {"wins": 0, "total": 0, "pnls": []})

    for row in rows:
        r = dict(row)
        is_win = r["outcome"] in ("T1_HIT", "T2_HIT")
        pnl = r.get("pnl_pct", 0) or 0

        for key in [
            f"session:{r.get('market_session','')}",
            f"day:{r.get('day_of_week','')}",
            f"week:{r.get('week_type','')}",
            f"regime:{r.get('regime','')}",
            f"day:{r.get('day_of_week','')}|session:{r.get('market_session','')}",
            f"regime:{r.get('regime','')}|session:{r.get('market_session','')}",
        ]:
            stats[key]["wins"]  += 1 if is_win else 0
            stats[key]["total"] += 1
            stats[key]["pnls"].append(pnl)

    result = {}
    for key, d in stats.items():
        n = d["total"]
        if n < 3:
            continue
        result[key] = {
            "win_rate": round(d["wins"] / n, 3),
            "count":    n,
            "avg_pnl":  round(sum(d["pnls"]) / n, 2),
        }

    _save(TIME_STATS_PATH, result)
    log.info("⏰ RegimeDetector: Time pattern stats built | %d keys", len(result))
    return result


def get_time_win_rate(session: str = None, day: str = None,
                      week_type: str = None, regime: str = None) -> dict:
    """Look up historical win rate for current time context."""
    stats = _load(TIME_STATS_PATH, {})
    result = {}

    if session:
        result["session"]  = stats.get(f"session:{session}", {})
    if day:
        result["day"]      = stats.get(f"day:{day}", {})
    if week_type:
        result["week"]     = stats.get(f"week:{week_type}", {})
    if regime:
        result["regime"]   = stats.get(f"regime:{regime}", {})
    if session and day:
        result["day_session"] = stats.get(f"day:{day}|session:{session}", {})
    if regime and session:
        result["regime_session"] = stats.get(f"regime:{regime}|session:{session}", {})

    return result
