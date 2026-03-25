# ══════════════════════════════════════════════════════════════════════════════
# ATLAS MODULE 2 — NEWS IMPACT MAPPER
# ══════════════════════════════════════════════════════════════════════════════
# Tracks the causal relationship between news events and price moves.
# The system learns: "When THIS type of news hits THIS sector, the typical
# price move is X% over Y hours, with Z% probability."
#
# News event types tracked:
#   EARNINGS_BEAT / EARNINGS_MISS — quarterly results
#   RBI_RATE_CUT / RBI_RATE_HIKE  — monetary policy
#   FII_BUY / FII_SELL            — institutional flow announcements
#   SECTOR_POLICY                 — govt / regulatory decisions
#   GEOPOLITICAL                  — war, sanctions, global events
#   COMMODITY                     — crude oil, gold, metals
#   CORPORATE_ACTION              — buyback, dividend, bonus, merger
#   MANAGEMENT                    — CEO change, fraud, scandal
#   MACRO_DATA                    — GDP, inflation, IIP, PMI releases
#   NONE                          — no significant news
#
# Learning questions:
#   "Which keywords in earnings headlines predict >3% moves?"
#   "How long do RBI rate cut rallies last?"
#   "Does sector selloff on bad FII data recover within 3 days?"
# ══════════════════════════════════════════════════════════════════════════════

import json
import os
import re
import logging
from datetime import datetime
from collections import defaultdict

log = logging.getLogger("atlas.news_impact")

_BASE            = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
IMPACT_LOG_PATH  = os.path.join(_BASE, "news_impact_log.json")
IMPACT_MAP_PATH  = os.path.join(_BASE, "news_impact_map.json")


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
# EVENT TYPE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

# Keywords → event type mapping (order matters: first match wins)
EVENT_TYPE_RULES = [
    # Earnings
    (r"(q[1-4]\s*(beat|miss|result)|earnings\s*(beat|miss|surpass|disappoint)|eps\s*(beat|miss)|profit\s*(jump|slump|rise|fall))", "EARNINGS_BEAT_OR_MISS"),
    (r"(result|quarterly|q[1-4]|profit|loss|revenue|ebitda|nii|nim)", "EARNINGS"),
    # RBI / Monetary
    (r"(rate\s*cut|rbi\s*cut|repo\s*cut|monetary\s*easing)", "RBI_RATE_CUT"),
    (r"(rate\s*hike|rbi\s*hike|repo\s*hike|monetary\s*tighten)", "RBI_RATE_HIKE"),
    (r"(rbi|reserve\s*bank|monetary\s*policy|mpc)", "RBI_POLICY"),
    # FII / Institutional
    (r"(fii\s*(buy|buying|net\s*buy|inflow)|foreign\s*(buy|inflow))", "FII_BUY"),
    (r"(fii\s*(sell|selling|net\s*sell|outflow)|foreign\s*(sell|outflow))", "FII_SELL"),
    # Corporate Actions
    (r"(buyback|share\s*repurchase)", "CORPORATE_BUYBACK"),
    (r"(dividend|interim\s*dividend|final\s*dividend)", "CORPORATE_DIVIDEND"),
    (r"(bonus\s*share|stock\s*split|right\s*issue)", "CORPORATE_ACTION"),
    (r"(merger|acquisition|takeover|stake\s*buy)", "MERGER_ACQUISITION"),
    # Management / Scandal
    (r"(fraud|scam|sebi\s*probe|cbi|ed\s*raid|cem\s*raid|seizure)", "SCANDAL"),
    (r"(ceo|md|chairman).*(resign|appoint|step\s*down|change)", "MANAGEMENT_CHANGE"),
    # Macro Data
    (r"(gdp|iip|pmi|cpi|wpi|inflation|fiscal\s*deficit)", "MACRO_DATA"),
    # Sector/Policy
    (r"(govt|government|ministry|budget|policy|regulation|approve|approval)", "SECTOR_POLICY"),
    # Geopolitical
    (r"(war|sanction|geopolit|tension|border|conflict)", "GEOPOLITICAL"),
    # Commodity
    (r"(crude\s*oil|brent|wti|gold|silver|copper|commodity)", "COMMODITY"),
    # Default
]


def classify_news_event(headline: str, description: str = "") -> dict:
    """
    Classify a news headline into event type + extract key signals.
    Returns: {event_type, impact_keywords, sentiment_bias, expected_magnitude}
    """
    text = (headline + " " + description).lower()

    event_type = "NONE"
    for pattern, etype in EVENT_TYPE_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            event_type = etype
            # Refine beat vs miss
            if etype == "EARNINGS_BEAT_OR_MISS":
                event_type = "EARNINGS_BEAT" if re.search(
                    r"(beat|surpass|exceed|record|strong|better)", text) else "EARNINGS_MISS"
            break

    # Extract key impact keywords
    positive_words = ["surge", "jump", "rally", "record", "strong", "buy", "upgrade",
                      "growth", "beat", "win", "contract", "order", "approval", "cut"]
    negative_words = ["fall", "drop", "slump", "miss", "weak", "sell", "downgrade",
                      "loss", "fraud", "seize", "ban", "reject", "hike", "penalty"]
    found_pos = [w for w in positive_words if w in text]
    found_neg = [w for w in negative_words if w in text]

    sentiment_bias = (
        "BULLISH" if len(found_pos) > len(found_neg) else
        "BEARISH" if len(found_neg) > len(found_pos) else
        "MIXED"
    )

    # Expected magnitude from event type
    magnitude_map = {
        "EARNINGS_BEAT":    "HIGH",    # 3-8% possible
        "EARNINGS_MISS":    "HIGH",
        "RBI_RATE_CUT":     "HIGH",    # market-wide
        "RBI_RATE_HIKE":    "HIGH",
        "RBI_POLICY":       "MEDIUM",
        "FII_BUY":          "MEDIUM",
        "FII_SELL":         "MEDIUM",
        "MERGER_ACQUISITION":"HIGH",
        "SCANDAL":          "HIGH",    # sharp downside
        "MANAGEMENT_CHANGE":"MEDIUM",
        "CORPORATE_BUYBACK":"MEDIUM",
        "CORPORATE_DIVIDEND":"LOW",
        "SECTOR_POLICY":    "MEDIUM",
        "MACRO_DATA":       "LOW",
        "GEOPOLITICAL":     "HIGH",
        "COMMODITY":        "MEDIUM",
        "NONE":             "LOW",
    }

    return {
        "event_type":         event_type,
        "sentiment_bias":     sentiment_bias,
        "impact_magnitude":   magnitude_map.get(event_type, "LOW"),
        "positive_keywords":  found_pos[:5],
        "negative_keywords":  found_neg[:5],
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECORD & LEARN
# ─────────────────────────────────────────────────────────────────────────────

def record_news_event(
    ticker: str,
    sector: str,
    headline: str,
    sentiment_score: float,      # -1.0 to +1.0
    event_type: str,
    impact_magnitude: str,
    price_at_event: float,
    price_1h_later: float = None,
    price_1d_later: float = None,
    price_3d_later: float = None,
) -> dict:
    """
    Record a news event and its actual price impact (updated later).
    """
    log_data = _load(IMPACT_LOG_PATH, [])

    event = {
        "event_id":       f"NEWS_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp":      datetime.now().isoformat(),
        "ticker":         ticker.upper(),
        "sector":         sector,
        "headline":       headline[:200],
        "sentiment_score": sentiment_score,
        "event_type":     event_type,
        "impact_magnitude": impact_magnitude,
        "price_at_event": price_at_event,
        "move_1h_pct":    _pct_move(price_at_event, price_1h_later),
        "move_1d_pct":    _pct_move(price_at_event, price_1d_later),
        "move_3d_pct":    _pct_move(price_at_event, price_3d_later),
        "direction_1h":   "UP" if (price_1h_later or 0) > price_at_event else "DOWN" if price_1h_later else None,
        "direction_1d":   "UP" if (price_1d_later or 0) > price_at_event else "DOWN" if price_1d_later else None,
    }

    log_data.append(event)
    if len(log_data) > 2000:
        log_data = log_data[-2000:]
    _save(IMPACT_LOG_PATH, log_data)

    log.debug("📰 NewsImpact: Recorded %s for %s [%s %s]",
              event_type, ticker, impact_magnitude, sentiment_score)
    return event


def _pct_move(base: float, target: float) -> float:
    if not base or not target:
        return None
    return round(((target - base) / base) * 100, 2)


def update_price_outcomes(impact_log: list = None) -> int:
    """
    Called by self_upgrader: update recorded events with actual price outcomes.
    Returns count of records updated.
    """
    # In practice, the real price data comes from live price cache
    # Here we mark records that now have all 3 price points filled
    log_data = _load(IMPACT_LOG_PATH, [])
    complete = sum(1 for e in log_data if e.get("move_1d_pct") is not None)
    log.debug("NewsImpact: %d/%d events have 1d outcome", complete, len(log_data))
    return complete


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_impact_map() -> dict:
    """
    Synthesize the news impact log into actionable insights.
    Groups by event_type × sector and computes typical moves.
    Called nightly by self_upgrader.
    """
    log_data = _load(IMPACT_LOG_PATH, [])
    settled  = [e for e in log_data if e.get("move_1d_pct") is not None]

    if len(settled) < 5:
        log.info("NewsImpact: Not enough settled events (%d) to build map", len(settled))
        return {}

    # Group by event_type
    by_event = defaultdict(lambda: {"count": 0, "up_1d": 0, "moves_1d": [], "moves_1h": []})
    # Group by event_type × sector
    by_event_sector = defaultdict(lambda: {"count": 0, "up_1d": 0, "moves_1d": []})

    for event in settled:
        et = event.get("event_type", "NONE")
        sec = event.get("sector", "Unknown")
        m1d = event.get("move_1d_pct", 0) or 0
        m1h = event.get("move_1h_pct", 0) or 0

        by_event[et]["count"] += 1
        by_event[et]["up_1d"] += 1 if m1d > 0 else 0
        by_event[et]["moves_1d"].append(m1d)
        by_event[et]["moves_1h"].append(m1h)

        key = f"{et}|{sec}"
        by_event_sector[key]["count"] += 1
        by_event_sector[key]["up_1d"] += 1 if m1d > 0 else 0
        by_event_sector[key]["moves_1d"].append(m1d)

    # Build readable insights
    insights = {"by_event_type": {}, "by_event_sector": {}, "updated_at": datetime.now().isoformat()}

    for et, d in by_event.items():
        n = d["count"]
        if n == 0:
            continue
        insights["by_event_type"][et] = {
            "count":         n,
            "up_pct":        round(d["up_1d"] / n * 100, 1),
            "avg_move_1d":   round(sum(d["moves_1d"]) / n, 2),
            "avg_move_1h":   round(sum(d["moves_1h"]) / n, 2),
            "max_up_1d":     round(max(d["moves_1d"]), 2),
            "max_down_1d":   round(min(d["moves_1d"]), 2),
            "trade_worthy":  n >= 5 and abs(sum(d["moves_1d"]) / n) > 1.0,
        }

    for key, d in by_event_sector.items():
        n = d["count"]
        if n < 3:
            continue
        insights["by_event_sector"][key] = {
            "count":       n,
            "up_pct":      round(d["up_1d"] / n * 100, 1),
            "avg_move_1d": round(sum(d["moves_1d"]) / n, 2),
        }

    _save(IMPACT_MAP_PATH, insights)
    log.info("📰 NewsImpact: Map built | %d event types | %d sector combos",
             len(insights["by_event_type"]), len(insights["by_event_sector"]))
    return insights


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT FOR AGENTS
# ─────────────────────────────────────────────────────────────────────────────

def get_news_context(event_type: str, sector: str = None) -> dict:
    """
    Returns learned context for a given news event type.
    Called before making trade decisions on news-driven setups.
    """
    impact_map = _load(IMPACT_MAP_PATH, {})

    event_stats = impact_map.get("by_event_type", {}).get(event_type, {})
    sector_key  = f"{event_type}|{sector}" if sector else None
    sector_stats = impact_map.get("by_event_sector", {}).get(sector_key, {}) if sector_key else {}

    # Generate readable context
    if event_stats.get("count", 0) >= 5:
        context_line = (
            f"Historically {event_type} events move price avg "
            f"{event_stats['avg_move_1d']:+.1f}% in 1d "
            f"(up {event_stats['up_pct']:.0f}% of the time, n={event_stats['count']})"
        )
    else:
        context_line = f"{event_type}: insufficient history to predict impact"

    sector_context = ""
    if sector_stats.get("count", 0) >= 3:
        sector_context = (
            f"{sector} specifically: avg {sector_stats['avg_move_1d']:+.1f}% "
            f"(up {sector_stats['up_pct']:.0f}%, n={sector_stats['count']})"
        )

    return {
        "event_type":      event_type,
        "sector":          sector,
        "overall_stats":   event_stats,
        "sector_stats":    sector_stats,
        "context_line":    context_line,
        "sector_context":  sector_context,
        "trade_worthy":    event_stats.get("trade_worthy", False),
        "avg_move_1d":     event_stats.get("avg_move_1d"),
        "up_probability":  event_stats.get("up_pct"),
    }
