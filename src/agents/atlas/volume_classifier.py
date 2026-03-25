# ══════════════════════════════════════════════════════════════════════════════
# ATLAS MODULE 4 — VOLUME SPIKE CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════════
# Volume is the MOST honest indicator in markets — it cannot be faked.
# This module classifies EVERY volume event by type and tracks outcomes.
#
# Volume Spike Types:
#   ACCUMULATION   — High vol + price holding / creeping up = institutions buying quietly
#   DISTRIBUTION   — High vol + price falling = institutions selling into strength
#   CLIMAX_BUY     — Extreme vol + rapid price rise = final euphoric surge (sell signal)
#   CLIMAX_SELL    — Extreme vol + sharp price drop = capitulation (contrarian buy)
#   BREAKOUT       — Volume surge at resistance = genuine breakout (buy signal)
#   FAKE_BREAKOUT  — Volume surge at resistance then price retreats = trap
#   DRY_UP         — Very low volume before big move = coiling spring
#   NORMAL         — Nothing notable
#   INSIDER_SPIKE  — Extreme volume before corporate news = possible insider activity
#
# The system learns:
#   "Which volume patterns before entry predict the biggest winners?"
#   "Do CLIMAX_SELL events recover in 3 days?"
#   "How often do BREAKOUT spikes hold vs reverse?"
#   "What volume pattern immediately precedes our worst losses?"
# ══════════════════════════════════════════════════════════════════════════════

import json
import os
import logging
from datetime import datetime

log = logging.getLogger("atlas.volume")

_BASE          = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
VOL_LOG_PATH   = os.path.join(_BASE, "volume_spike_log.json")
VOL_STATS_PATH = os.path.join(_BASE, "volume_stats.json")


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
# CLASSIFICATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def classify_volume(
    ticker: str,
    current_volume: int,
    avg_volume_20d: int,
    price_change_pct: float,        # % price change during this candle/session
    price_vs_high_52w: float,       # current price as % of 52-week high (e.g. 95 = 5% below)
    price_vs_resistance: float,     # % distance from key resistance (neg = below, pos = above)
    is_near_corporate_event: bool = False,  # earnings / result / agm within 3 days
) -> dict:
    """
    Classify a volume event into its type with associated trading signal.
    Returns: {volume_class, volume_ratio, signal, description, confidence}
    """
    if not avg_volume_20d or avg_volume_20d == 0:
        return {
            "volume_class": "UNKNOWN", "volume_ratio": None,
            "signal": "NEUTRAL", "description": "Insufficient volume history",
            "confidence": 0.0
        }

    ratio = current_volume / avg_volume_20d

    # Low volume — DRY_UP (coiling)
    if ratio < 0.4:
        return {
            "volume_class": "DRY_UP",
            "volume_ratio": round(ratio, 2),
            "signal":       "WATCH",
            "description":  "Volume dry-up: market coiling, big move may follow",
            "confidence":   0.5,
            "trading_note": "Set alerts — breakout on returning volume could be large",
        }

    if ratio < 0.8:
        return {
            "volume_class": "BELOW_AVERAGE",
            "volume_ratio": round(ratio, 2),
            "signal":       "NEUTRAL",
            "description":  "Below-average volume: avoid chasing",
            "confidence":   0.3,
        }

    if ratio < 1.2:
        return {
            "volume_class": "NORMAL",
            "volume_ratio": round(ratio, 2),
            "signal":       "NEUTRAL",
            "description":  "Normal volume, no special signal",
            "confidence":   0.4,
        }

    # Above average — classify type from price action
    if ratio >= 3.0 and is_near_corporate_event:
        return {
            "volume_class": "INSIDER_SPIKE",
            "volume_ratio": round(ratio, 2),
            "signal":       "CAUTION",
            "description":  f"Extreme volume ({ratio:.1f}x) before corporate event — possible insider activity",
            "confidence":   0.6,
            "trading_note": "Monitor but don't chase — gap risk on event day",
        }

    if ratio >= 4.0 and price_change_pct > 4.0:
        return {
            "volume_class": "CLIMAX_BUY",
            "volume_ratio": round(ratio, 2),
            "signal":       "AVOID",
            "description":  f"Climax buying ({ratio:.1f}x vol, +{price_change_pct:.1f}%) — euphoric top likely",
            "confidence":   0.7,
            "trading_note": "Do NOT buy here. Wait for pullback to consolidation.",
        }

    if ratio >= 4.0 and price_change_pct < -4.0:
        return {
            "volume_class": "CLIMAX_SELL",
            "volume_ratio": round(ratio, 2),
            "signal":       "CONTRARIAN_BUY",
            "description":  f"Climax selling ({ratio:.1f}x vol, {price_change_pct:.1f}%) — capitulation, recovery likely",
            "confidence":   0.65,
            "trading_note": "Contrarian setup: wait for next-day confirmation before entering long",
        }

    if ratio >= 2.0 and price_change_pct > 1.5 and (price_vs_resistance or 0) > 0:
        return {
            "volume_class": "BREAKOUT",
            "volume_ratio": round(ratio, 2),
            "signal":       "STRONG_BUY",
            "description":  f"Volume breakout ({ratio:.1f}x) above resistance — genuine institutional buying",
            "confidence":   0.75,
            "trading_note": "High-conviction entry. First pullback to breakout level = add.",
        }

    if ratio >= 2.0 and price_change_pct > 1.0:
        return {
            "volume_class": "ACCUMULATION",
            "volume_ratio": round(ratio, 2),
            "signal":       "BUY",
            "description":  f"Accumulation pattern ({ratio:.1f}x vol) — institutions building positions",
            "confidence":   0.7,
            "trading_note": "Buy on next minor dip. Do not chase current candle.",
        }

    if ratio >= 2.0 and price_change_pct < -1.0:
        return {
            "volume_class": "DISTRIBUTION",
            "volume_ratio": round(ratio, 2),
            "signal":       "SELL",
            "description":  f"Distribution ({ratio:.1f}x vol, falling price) — institutions selling",
            "confidence":   0.7,
            "trading_note": "Avoid longs. If holding, consider tightening stops.",
        }

    if ratio >= 1.5 and abs(price_change_pct) < 0.5:
        return {
            "volume_class": "ABSORPTION",
            "volume_ratio": round(ratio, 2),
            "signal":       "NEUTRAL",
            "description":  f"Volume absorption ({ratio:.1f}x) — high vol, price not moving = supply/demand balance",
            "confidence":   0.5,
            "trading_note": "Watch breakout direction — whoever wins the absorption battle leads next move",
        }

    return {
        "volume_class": "ABOVE_AVERAGE",
        "volume_ratio": round(ratio, 2),
        "signal":       "BUY_MILD",
        "description":  f"Above-average volume ({ratio:.1f}x) with modest price action",
        "confidence":   0.5,
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECORD & LEARN
# ─────────────────────────────────────────────────────────────────────────────

def record_volume_event(
    ticker: str,
    sector: str,
    volume_class: str,
    volume_ratio: float,
    price_change_pct: float,
    regime: str = None,
) -> None:
    """Record a classified volume event for historical analysis."""
    log_data = _load(VOL_LOG_PATH, [])
    log_data.append({
        "timestamp":    datetime.now().isoformat(),
        "ticker":       ticker.upper(),
        "sector":       sector,
        "volume_class": volume_class,
        "volume_ratio": volume_ratio,
        "price_change": price_change_pct,
        "regime":       regime,
        "outcome":      None,   # filled later
    })
    if len(log_data) > 3000:
        log_data = log_data[-3000:]
    _save(VOL_LOG_PATH, log_data)


def build_volume_stats(conn=None) -> dict:
    """
    Build win-rate stats by volume class from ATLAS knowledge_events.
    Called nightly by self_upgrader.
    """
    stats = {}

    if conn is None:
        try:
            from src.agents.atlas.core import _get_conn
            conn = _get_conn()
        except Exception:
            return {}

    try:
        rows = conn.execute("""
            SELECT volume_class, outcome, pnl_pct
            FROM knowledge_events
            WHERE outcome NOT IN ('OPEN', 'EXPIRED') AND volume_class IS NOT NULL
        """).fetchall()
    except Exception as e:
        log.error("volume stats query error: %s", e)
        return {}

    from collections import defaultdict
    groups = defaultdict(lambda: {"wins": 0, "total": 0, "pnls": []})

    for row in rows:
        r = dict(row)
        vc = r.get("volume_class", "UNKNOWN")
        is_win = r["outcome"] in ("T1_HIT", "T2_HIT")
        pnl = r.get("pnl_pct", 0) or 0
        groups[vc]["wins"]  += 1 if is_win else 0
        groups[vc]["total"] += 1
        groups[vc]["pnls"].append(pnl)

    for vc, d in groups.items():
        n = d["total"]
        if n == 0:
            continue
        stats[vc] = {
            "win_rate": round(d["wins"] / n, 3),
            "count":    n,
            "avg_pnl":  round(sum(d["pnls"]) / n, 2),
        }

    _save(VOL_STATS_PATH, stats)
    log.info("📊 VolumeClassifier: Stats built | %d volume classes", len(stats))
    return stats


def get_volume_context(volume_class: str) -> dict:
    """Return historical win rate for this volume class."""
    stats = _load(VOL_STATS_PATH, {})
    data  = stats.get(volume_class, {})

    if data.get("count", 0) >= 5:
        insight = (
            f"Volume class {volume_class}: "
            f"{data['win_rate']*100:.0f}% win rate, avg P&L {data['avg_pnl']:+.1f}% "
            f"(n={data['count']})"
        )
    else:
        insight = f"Volume class {volume_class}: insufficient history yet"

    return {
        "volume_class": volume_class,
        "win_rate":     data.get("win_rate"),
        "avg_pnl":      data.get("avg_pnl"),
        "count":        data.get("count", 0),
        "insight":      insight,
    }
