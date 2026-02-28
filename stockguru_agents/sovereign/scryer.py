# ══════════════════════════════════════════════════════════════════════════════
# StockGuru Sovereign — The Scryer
# Role: Data Intake & Intelligence Enrichment
#   • Assigns credibility scores to news sources
#   • Computes "Shock vs Reality" delta per stock
#   • Classifies market noise level: NOISE / SIGNAL / PANIC / EUPHORIA
# ══════════════════════════════════════════════════════════════════════════════
import json, logging, os
from datetime import datetime

log = logging.getLogger("sovereign.scryer")

CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "sovereign_config.json")
)

# ─────────────────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"source_confidence": {}, "gate_overrides": {"shock_delta_threshold": 3.0}}


# ─────────────────────────────────────────────────────────────────────────────
def run(shared_state: dict) -> dict:
    """
    Main entry point — called by Tier 5 in run_all_agents().
    Reads: news_results, stock_sentiment_map, technical_data, _price_cache
    Writes: shared_state["scryer_output"]
    """
    log.info("🔮 Scryer: Starting intelligence enrichment...")
    config = _load_config()

    news            = shared_state.get("news_results", [])
    sentiment_map   = shared_state.get("stock_sentiment_map", {})
    technical_data  = shared_state.get("technical_data", {})
    price_cache     = shared_state.get("_price_cache", {})

    # ── 1. Weight news by source credibility ──────────────────────────────────
    weighted_news = _weight_by_source_confidence(news, config)
    high_conf_news = [n for n in weighted_news if n.get("credibility_score", 0) >= 0.80]

    # ── 2. Compute Shock vs Reality delta per stock ────────────────────────────
    shock_map = {}
    for stock, sdata in sentiment_map.items():
        price_info = price_cache.get(stock, {})
        tech_info  = technical_data.get(stock, {})
        delta_result = _compute_shock_delta(stock, sdata, price_info, tech_info, config)
        if delta_result:
            shock_map[stock] = delta_result

    # ── 3. Classify overall market noise ──────────────────────────────────────
    market_read = _classify_market_noise(shock_map, shared_state)

    # ── 4. Assemble output ────────────────────────────────────────────────────
    output = {
        "confidence_weighted_news": weighted_news,
        "high_confidence_news":     high_conf_news,
        "shock_vs_reality":         shock_map,
        "overreaction_stocks":      [s for s, d in shock_map.items() if d["type"] == "OVERREACTION"],
        "underreaction_stocks":     [s for s, d in shock_map.items() if d["type"] == "UNDERREACTION"],
        "scryer_market_read":       market_read,
        "news_analyzed":            len(weighted_news),
        "high_conf_count":          len(high_conf_news),
        "last_run":                 datetime.now().strftime("%d %b %H:%M:%S")
    }

    shared_state["scryer_output"] = output
    log.info("✅ Scryer: %d news weighted | %d overreaction | market=%s",
             len(weighted_news), len(output["overreaction_stocks"]), market_read)
    return output


# ─────────────────────────────────────────────────────────────────────────────
def _weight_by_source_confidence(news_results: list, config: dict) -> list:
    """
    Multiply each news item's sentiment_score by its source credibility weight.
    Adds 'credibility_score' and 'weighted_sentiment' fields to each item.
    """
    source_map = config.get("source_confidence", {})
    default_cred = source_map.get("default", 0.60)
    weighted = []

    for item in news_results:
        if not isinstance(item, dict):
            continue
        item = dict(item)  # copy
        source = item.get("source", "")
        # Match source substring (partial match for flexibility)
        credibility = default_cred
        for src_key, score in source_map.items():
            if src_key.lower() in source.lower():
                credibility = score
                break

        raw_score = item.get("sentiment_score", 0.0)
        item["credibility_score"]  = credibility
        item["weighted_sentiment"] = round(raw_score * credibility, 3)
        weighted.append(item)

    return weighted


# ─────────────────────────────────────────────────────────────────────────────
def _compute_shock_delta(stock: str, sdata: dict, price_info: dict,
                          tech_info: dict, config: dict) -> dict | None:
    """
    Shock vs Reality formula:
        shock_score   = abs(weighted_sentiment_score)   — how big is the news event
        reality_score = abs(price_change_pct / atr_pct) — price move vs ATR (normalized)
        delta         = shock_score - (reality_score * 10)

    delta > threshold → OVERREACTION  (news >> price  → buy the dip candidate)
    delta < -threshold → UNDERREACTION (price >> news → fade the gap candidate)
    """
    threshold = config.get("gate_overrides", {}).get("shock_delta_threshold", 3.0)

    # Get sentiment score for this stock (sum of weighted_sentiment across all items)
    raw_score = sdata.get("score", 0.0)
    count     = max(sdata.get("count", 1), 1)
    avg_sentiment = raw_score / count  # normalize per item

    # Price data
    price_chg_pct = price_info.get("change_pct", 0.0)
    if price_chg_pct == 0 and raw_score == 0:
        return None  # nothing to analyze

    # ATR normalization (use atr_pct if available, else assume 1.5% baseline)
    atr_pct = tech_info.get("atr_pct", 1.5)
    atr_pct = max(atr_pct, 0.1)  # guard against zero

    shock_score  = abs(avg_sentiment)
    reality_score = abs(price_chg_pct / atr_pct)
    delta         = round(shock_score - (reality_score * 10), 3)

    # Classify
    if delta > threshold:
        delta_type = "OVERREACTION"    # News shocked more than price moved
    elif delta < -threshold:
        delta_type = "UNDERREACTION"   # Price moved more than news justified
    else:
        delta_type = "ALIGNED"         # News and price roughly aligned

    return {
        "stock":           stock,
        "avg_sentiment":   round(avg_sentiment, 3),
        "news_count":      count,
        "price_chg_pct":   price_chg_pct,
        "atr_pct":         round(atr_pct, 3),
        "shock_score":     round(shock_score, 3),
        "reality_score":   round(reality_score, 3),
        "delta":           delta,
        "type":            delta_type,
        "headlines":       sdata.get("headlines", [])[:2]  # top 2 for context
    }


# ─────────────────────────────────────────────────────────────────────────────
def _classify_market_noise(shock_map: dict, shared_state: dict) -> str:
    """
    Classify overall market noise level based on aggregate delta signals
    and market mood score.

    PANIC     → Many extreme negative overreactions (large drops, small news)
    EUPHORIA  → Many extreme positive underreactions (large rallies, small news)
    SIGNAL    → Meaningful, credible, directional news driving prices
    NOISE     → No clear pattern; mixed or minimal news impact
    """
    if not shock_map:
        return "NOISE"

    deltas         = [v["delta"] for v in shock_map.values()]
    overreactions  = sum(1 for d in deltas if d > 5.0)
    underreactions = sum(1 for d in deltas if d < -5.0)
    total          = len(deltas)

    # Also check VIX
    vix = 0.0
    index_prices = shared_state.get("index_prices", {})
    for k, v in index_prices.items():
        if "VIX" in k.upper():
            vix = v.get("price", 0.0) if isinstance(v, dict) else float(v or 0)
            break
    if vix == 0.0:
        vix = shared_state.get("india_vix", 0.0) or 0.0

    if vix > 22 and overreactions > total * 0.4:
        return "PANIC"
    elif overreactions + underreactions > total * 0.5 and overreactions > underreactions:
        return "PANIC"
    elif underreactions > total * 0.4:
        return "EUPHORIA"
    elif abs(sum(deltas) / max(total, 1)) > 2.0:
        return "SIGNAL"
    else:
        return "NOISE"


# ─────────────────────────────────────────────────────────────────────────────
def get_stock_delta(stock: str, shared_state: dict) -> dict:
    """Convenience: get Scryer data for a specific stock. Returns {} if not found."""
    return shared_state.get("scryer_output", {}).get("shock_vs_reality", {}).get(stock, {})
