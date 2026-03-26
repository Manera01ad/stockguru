# ══════════════════════════════════════════════════════════════════════════════
# ATLAS MODULE 5 — CAUSAL REASONING ENGINE
# ══════════════════════════════════════════════════════════════════════════════
# The most powerful learning tool: understanding WHY a trade worked or failed.
# Most systems only know WHAT happened (win/loss). ATLAS knows WHY.
#
# After every closed trade, this engine runs a multi-dimensional causal analysis:
#
# Primary Causes (what drove the move):
#   TECHNICAL     — Pure chart pattern / indicator alignment
#   OPTIONS_FLOW  — PCR / OI change was the leading signal
#   NEWS_CATALYST — A specific news event triggered the move
#   VOLUME_SIGNAL — Volume spike/pattern was the key signal
#   FII_FLOW      — Institutional buying/selling drove it
#   SECTOR_MOVE   — Sector rotation was the primary driver
#   MACRO_EVENT   — RBI policy, GDP, global event
#   REGIME_SHIFT  — Market regime changed (bull → bear)
#   NONE_CLEAR    — No single clear cause identified
#
# Failure Reasons (why losses happened):
#   WRONG_REGIME  — Entered long in bear market
#   NEWS_SHOCK    — Unexpected negative news post-entry
#   FAKE_BREAKOUT — Volume signal was a trap
#   TIMING        — Setup was right but entry was early/late
#   OVEREXTENDED  — Price too extended, low R:R
#   SECTOR_DRAG   — Individual stock dragged by sector selloff
#   OPTIONS_EXPIRE — Weekly options expiry distorted price action
#   MACRO_HEADWIND — Global/macro event overpowered technical setup
#   STOP_TOO_TIGHT — Stop loss was in noise zone
#
# The engine also does cross-dimensional analysis:
#   "When OPTIONS_FLOW was the primary cause AND regime was BULL_TREND,
#    win rate was 82% vs 51% when options flow conflicted with regime."
# ══════════════════════════════════════════════════════════════════════════════

import json
import os
import logging
from datetime import datetime
from collections import defaultdict

log = logging.getLogger("atlas.causal")

_BASE          = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
CAUSAL_STATS_PATH = os.path.join(_BASE, "causal_stats.json")


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
# CAUSAL ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def analyze_trade_cause(
    outcome: str,           # T1_HIT / T2_HIT / SL_HIT / EXPIRED
    pnl_pct: float,
    # Technical signals at entry
    rsi: float = None,
    macd_cross: str = None,     # BULL / BEAR / NONE
    ema_position: str = None,   # ABOVE_200 / ABOVE_50 / BELOW_50 / BELOW_200
    volume_class: str = None,
    volume_ratio: float = None,
    # Market context
    regime: str = None,
    pcr_nifty: float = None,
    options_signal: str = None,
    news_event_type: str = None,
    news_impact: str = None,    # HIGH / MEDIUM / LOW / NONE
    fii_flow: str = None,
    sector_momentum: str = None,
    week_type: str = None,
    market_session: str = None,
    # Outcome details
    hold_duration_hrs: float = None,
) -> dict:
    """
    Determine the PRIMARY cause of a trade outcome and extract a lesson.
    Returns: {primary_cause, secondary_causes, failure_reason, lesson, confidence}
    """
    is_win = outcome in ("T1_HIT", "T2_HIT")
    pnl = pnl_pct or 0

    signal_quality = {
        "technical": _score_technical(rsi, macd_cross, ema_position),
        "volume":    _score_volume(volume_class, volume_ratio),
        "options":   _score_options(pcr_nifty, options_signal),
        "news":      _score_news(news_event_type, news_impact),
        "macro":     _score_macro(regime, fii_flow, sector_momentum),
    }

    # Sort by strength of signal at entry
    sorted_signals = sorted(signal_quality.items(), key=lambda x: abs(x[1]), reverse=True)

    primary_cause = "NONE_CLEAR"
    secondary_causes = []
    failure_reason = None
    lesson = None

    # Determine primary cause from strongest signal that aligns with outcome
    if is_win:
        # For wins: primary cause = the strongest positive signal
        for sig_name, sig_score in sorted_signals:
            if sig_score > 0:
                primary_cause = _signal_to_cause(sig_name, sig_score, news_event_type)
                break
        secondary_causes = [
            _signal_to_cause(n, s, news_event_type)
            for n, s in sorted_signals[1:]
            if s > 0 and _signal_to_cause(n, s, news_event_type) != primary_cause
        ][:2]
        lesson = _generate_win_lesson(primary_cause, secondary_causes, regime, pnl)
    else:
        # For losses: find the conflict or failure
        primary_cause = "NONE_CLEAR"
        failure_reason = _determine_failure(
            signal_quality, regime, news_event_type, news_impact,
            volume_class, week_type, hold_duration_hrs, rsi
        )
        lesson = _generate_loss_lesson(failure_reason, regime, volume_class, news_event_type)

    # Confidence: higher if signals agree with outcome
    aligned_signals = sum(1 for n, s in sorted_signals if
                         (is_win and s > 0) or (not is_win and s < 0))
    confidence = round(0.3 + (aligned_signals / max(len(sorted_signals), 1)) * 0.7, 2)

    return {
        "primary_cause":   primary_cause,
        "secondary_causes": secondary_causes,
        "failure_reason":  failure_reason,
        "lesson":          lesson,
        "confidence":      confidence,
        "signal_quality":  signal_quality,
        "aligned_signals": aligned_signals,
    }


def _score_technical(rsi, macd_cross, ema_position) -> float:
    score = 0.0
    if rsi:
        if 40 <= rsi <= 65:   score += 1.0   # ideal buy zone
        elif rsi > 72:        score -= 1.5   # overbought
        elif rsi < 30:        score += 0.5   # oversold bounce
    if macd_cross == "BULL":  score += 1.5
    elif macd_cross == "BEAR": score -= 1.5
    if ema_position in ("ABOVE_200",): score += 1.5
    elif ema_position in ("ABOVE_50",): score += 0.5
    elif ema_position in ("BELOW_50",): score -= 0.5
    elif ema_position in ("BELOW_200",): score -= 1.5
    return score


def _score_volume(volume_class, volume_ratio) -> float:
    vol_scores = {
        "BREAKOUT":     3.0, "ACCUMULATION": 2.0, "CLIMAX_SELL": 1.5,
        "CLIMAX_BUY":  -2.0, "DISTRIBUTION": -2.0, "DRY_UP": 0.5,
        "INSIDER_SPIKE": 1.0, "NORMAL": 0.5, "ABOVE_AVERAGE": 0.8,
        "ABSORPTION":   0.3, "BELOW_AVERAGE": -0.5,
    }
    base = vol_scores.get(volume_class or "NORMAL", 0.0)
    # Boost for very high ratio
    if volume_ratio and volume_ratio > 3.0:
        base *= 1.2
    return base


def _score_options(pcr, options_signal) -> float:
    score = 0.0
    if pcr:
        if 0.65 <= pcr <= 0.9: score += 1.5   # ideal bullish zone
        elif pcr < 0.55:       score -= 1.0   # too euphoric
        elif pcr > 1.3:        score += 0.5   # contrarian opportunity
        elif 1.1 <= pcr <= 1.3: score -= 1.0  # bearish sentiment
    signal_scores = {
        "STRONG_BUY": 2.0, "BUY": 1.0, "NEUTRAL": 0,
        "AVOID": -1.0, "STRONG_SELL": -2.0,
    }
    score += signal_scores.get(options_signal or "NEUTRAL", 0)
    return score


def _score_news(news_event_type, news_impact) -> float:
    if not news_event_type or news_event_type == "NONE":
        return 0.0
    magnitude = {"HIGH": 2.0, "MEDIUM": 1.0, "LOW": 0.5, "NONE": 0.0}
    base = magnitude.get(news_impact or "NONE", 0.0)
    positive_types = {"EARNINGS_BEAT", "RBI_RATE_CUT", "FII_BUY", "CORPORATE_BUYBACK",
                      "CORPORATE_DIVIDEND", "MERGER_ACQUISITION"}
    negative_types = {"EARNINGS_MISS", "RBI_RATE_HIKE", "FII_SELL", "SCANDAL",
                      "MANAGEMENT_CHANGE"}
    if news_event_type in positive_types: return base
    if news_event_type in negative_types: return -base
    return 0.0


def _score_macro(regime, fii_flow, sector_momentum) -> float:
    score = 0.0
    regime_scores = {
        "BULL_TREND": 2.0, "RECOVERY": 1.0, "SIDEWAYS": 0.0,
        "VOLATILE": -0.5, "BEAR_TREND": -2.0,
    }
    score += regime_scores.get(regime or "UNKNOWN", 0.0)
    fii_scores = {"BUYING": 1.5, "NEUTRAL": 0, "SELLING": -1.5}
    score += fii_scores.get(fii_flow or "NEUTRAL", 0.0)
    mom_scores = {"STRONG": 1.0, "NEUTRAL": 0.0, "WEAK": -1.0}
    score += mom_scores.get(sector_momentum or "NEUTRAL", 0.0)
    return score


def _signal_to_cause(sig_name: str, score: float, news_event_type: str = None) -> str:
    mapping = {
        "technical": "TECHNICAL",
        "volume":    "VOLUME_SIGNAL",
        "options":   "OPTIONS_FLOW",
        "news":      f"NEWS_{news_event_type}" if news_event_type else "NEWS_CATALYST",
        "macro":     "MACRO_EVENT",
    }
    return mapping.get(sig_name, "NONE_CLEAR")


def _determine_failure(signal_quality, regime, news_event_type, news_impact,
                       volume_class, week_type, hold_duration_hrs, rsi) -> str:
    """Determine the most likely reason for a losing trade."""

    # Check for obvious causes
    if news_event_type in ("EARNINGS_MISS", "SCANDAL", "GEOPOLITICAL") and news_impact == "HIGH":
        return "NEWS_SHOCK"

    if regime == "BEAR_TREND":
        return "WRONG_REGIME"

    if volume_class in ("CLIMAX_BUY", "FAKE_BREAKOUT"):
        return "FAKE_BREAKOUT"

    if rsi and rsi > 72:
        return "OVEREXTENDED"

    if week_type == "EXPIRY_WEEK":
        return "OPTIONS_EXPIRY"

    if hold_duration_hrs and hold_duration_hrs < 1.0:
        return "STOP_TOO_TIGHT"

    # Sector drag: macro was negative but technical was positive
    if (signal_quality.get("macro", 0) < -1.0 and
        signal_quality.get("technical", 0) > 1.0):
        return "SECTOR_DRAG"

    # Timing: all signals ok but entered at wrong time
    if all(abs(v) < 1.5 for v in signal_quality.values()):
        return "TIMING"

    return "MACRO_HEADWIND"


def _generate_win_lesson(primary_cause: str, secondary_causes: list,
                         regime: str, pnl: float) -> str:
    lessons = {
        "TECHNICAL":     f"Clean technical setup in {regime} regime delivered {pnl:+.1f}% — trust aligned indicators",
        "VOLUME_SIGNAL": f"Volume classification was the key: {pnl:+.1f}% gain confirms volume accuracy",
        "OPTIONS_FLOW":  f"Options flow led price by {pnl:+.1f}% — PCR zone was predictive",
        "MACRO_EVENT":   f"Macro tailwind added {pnl:+.1f}% — always check regime before entry",
        "NONE_CLEAR":    f"Multi-factor alignment produced {pnl:+.1f}% — no single dominant signal",
    }
    base = lessons.get(primary_cause, f"Trade won {pnl:+.1f}% via {primary_cause}")
    if secondary_causes:
        base += f". Supported by: {', '.join(secondary_causes[:2])}"
    return base


def _generate_loss_lesson(failure_reason: str, regime: str,
                          volume_class: str, news_type: str) -> str:
    lessons = {
        "WRONG_REGIME":   "LESSON: Never go long when regime is BEAR_TREND — regime alignment is Rule 0",
        "NEWS_SHOCK":     f"LESSON: {news_type} surprise overrode all technicals — reduce size near scheduled events",
        "FAKE_BREAKOUT":  "LESSON: Breakout was a trap — always wait for retest confirmation before entry",
        "OVEREXTENDED":   "LESSON: RSI>72 entry = late. Always check RSI before entry, never chase",
        "OPTIONS_EXPIRY": "LESSON: Expiry week distortion — reduce position size or avoid entry Thu/Fri",
        "STOP_TOO_TIGHT": "LESSON: Stop was inside noise zone — use ATR-based stops, not arbitrary %",
        "SECTOR_DRAG":    "LESSON: Strong stock dragged by weak sector — sector alignment (R1) is non-negotiable",
        "TIMING":         "LESSON: Setup was correct but timing was wrong — wait for all 6+ gates before entry",
        "MACRO_HEADWIND": "LESSON: Global macro overpowered local setup — check DXY, crude, global indices first",
    }
    return lessons.get(failure_reason, f"LESSON: Investigate {failure_reason} in {regime} regime")


# ─────────────────────────────────────────────────────────────────────────────
# BUILD CAUSAL STATS (nightly)
# ─────────────────────────────────────────────────────────────────────────────

def build_causal_stats(conn=None) -> dict:
    """
    Build win-rate breakdown by primary cause + failure reason.
    Called nightly by self_upgrader.
    """
    if conn is None:
        try:
            from src.agents.atlas.core import _get_conn
            conn = _get_conn()
        except Exception:
            return {}

    try:
        rows = conn.execute("""
            SELECT primary_cause, failure_reason, outcome, pnl_pct
            FROM knowledge_events
            WHERE outcome NOT IN ('OPEN', 'EXPIRED')
        """).fetchall()
    except Exception as e:
        log.error("Causal stats query error: %s", e)
        return {}

    by_cause = defaultdict(lambda: {"wins": 0, "total": 0, "pnls": []})
    by_failure = defaultdict(lambda: {"count": 0, "pnls": []})

    for row in rows:
        r = dict(row)
        is_win = r["outcome"] in ("T1_HIT", "T2_HIT")
        pnl = r.get("pnl_pct", 0) or 0
        cause = r.get("primary_cause") or "NONE_CLEAR"
        failure = r.get("failure_reason")

        by_cause[cause]["wins"]  += 1 if is_win else 0
        by_cause[cause]["total"] += 1
        by_cause[cause]["pnls"].append(pnl)

        if failure and not is_win:
            by_failure[failure]["count"] += 1
            by_failure[failure]["pnls"].append(pnl)

    stats = {"by_cause": {}, "by_failure": {}, "updated_at": datetime.now().isoformat()}

    for cause, d in by_cause.items():
        n = d["total"]
        if n == 0: continue
        stats["by_cause"][cause] = {
            "win_rate": round(d["wins"] / n, 3),
            "count":    n,
            "avg_pnl":  round(sum(d["pnls"]) / n, 2),
        }

    for failure, d in by_failure.items():
        n = d["count"]
        stats["by_failure"][failure] = {
            "count":   n,
            "avg_pnl": round(sum(d["pnls"]) / n, 2),
        }

    _save(CAUSAL_STATS_PATH, stats)
    log.info("🔍 CausalEngine: Stats built | %d causes | %d failure types",
             len(stats["by_cause"]), len(stats["by_failure"]))
    return stats


def get_causal_context(primary_cause: str = None, failure_reason: str = None) -> str:
    """Return one-line causal insight for agent context."""
    stats = _load(CAUSAL_STATS_PATH, {})

    if primary_cause:
        data = stats.get("by_cause", {}).get(primary_cause, {})
        if data.get("count", 0) >= 5:
            return (f"{primary_cause}: {data.get('win_rate', 0)*100:.0f}% win rate "
                    f"(n={data.get('count', 0)})")
    return ""
