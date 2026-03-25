# ══════════════════════════════════════════════════════════════════════════════
# StockGuru Sovereign — The Quant
# Role: Overreaction Engine + Composite Conviction Scoring + Tier Routing
#   • Turns Scryer shock deltas into actionable overreaction setups
#   • Scores each stock with a composite conviction (0-100)
#   • Routes to AUTO_EXECUTE / HITL_REQUIRED / DEBATE_REQUIRED / SKIP
# ══════════════════════════════════════════════════════════════════════════════
import json, logging, os
from datetime import datetime

log = logging.getLogger("sovereign.quant")

CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "sovereign_config.json")
)

# ─────────────────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {
            "conviction_thresholds": {"auto_execute_min": 85, "hitl_lower_bound": 70, "debate_lower_bound": 55},
            "conviction_weights":    {"gate_score": 0.30, "claude_score": 0.25, "overreaction_score": 0.20,
                                      "technical_score": 0.15, "news_confidence": 0.10},
            "gate_overrides":        {"shock_delta_threshold": 3.0}
        }


# ─────────────────────────────────────────────────────────────────────────────
def run(shared_state: dict) -> dict:
    """
    Main entry point — called by Tier 5 after Scryer.
    Reads: scryer_output, actionable_signals, risk_reviewed_signals, claude_analysis, technical_data
    Writes: shared_state["quant_output"]
    """
    log.info("📐 Quant: Running overreaction engine + conviction scoring...")
    config = _load_config()
    thresholds = config.get("conviction_thresholds", {})
    weights    = config.get("conviction_weights", {})

    # Collect all candidate stocks from existing pipeline
    candidates = _collect_candidates(shared_state)

    conviction_map   = {}
    overreaction_setups = []
    auto_candidates  = []
    hitl_candidates  = []
    debate_candidates = []
    skipped          = []

    for stock in candidates:
        # Step 1: Compute composite conviction
        score, components = _compute_composite_conviction(stock, shared_state, weights)

        # Step 2: Detect overreaction setup
        over_setup = _generate_overreaction_setup(stock, score, shared_state, config)
        if over_setup:
            overreaction_setups.append(over_setup)
            # Boost conviction if confirmed overreaction
            if over_setup["type"] == "BUY_THE_PANIC" and over_setup["overreaction_confidence"] > 60:
                score = min(100, score + 5)
                components["overreaction_boost"] = 5

        # Step 3: Tier routing
        tier = _classify_conviction_tier(score, thresholds)
        conviction_map[stock] = {"composite": round(score, 1), "tier": tier, "components": components}

        if tier == "AUTO_EXECUTE":
            auto_candidates.append(stock)
        elif tier == "HITL_REQUIRED":
            hitl_candidates.append(stock)
        elif tier == "DEBATE_REQUIRED":
            debate_candidates.append(stock)
        else:
            skipped.append(stock)

    output = {
        "conviction_map":       conviction_map,
        "overreaction_setups":  overreaction_setups,
        "auto_candidates":      auto_candidates,
        "hitl_candidates":      hitl_candidates,
        "debate_candidates":    debate_candidates,
        "skipped":              skipped,
        "total_candidates":     len(candidates),
        "last_run":             datetime.now().strftime("%d %b %H:%M:%S")
    }

    shared_state["quant_output"] = output
    log.info("✅ Quant: %d auto | %d HITL | %d debate | %d skip",
             len(auto_candidates), len(hitl_candidates), len(debate_candidates), len(skipped))
    return output


# ─────────────────────────────────────────────────────────────────────────────
def _collect_candidates(shared_state: dict) -> list:
    """
    Gather unique stock names from all signal lists in the existing pipeline.
    Uses risk_reviewed_signals first (highest quality), falls back to actionable_signals.
    Deduplicates by name.
    """
    seen = set()
    candidates = []

    # Priority 1: risk-reviewed (have position sizing, RR already checked)
    for sig in shared_state.get("risk_reviewed_signals", []):
        name = sig.get("name", "")
        if name and name not in seen and sig.get("risk", {}).get("approved"):
            seen.add(name)
            candidates.append(name)

    # Priority 2: actionable signals (score >= 78, RR >= 1.2)
    for sig in shared_state.get("actionable_signals", []):
        name = sig.get("name", "")
        if name and name not in seen:
            seen.add(name)
            candidates.append(name)

    # Priority 3: Claude conviction picks
    for pick in shared_state.get("claude_analysis", {}).get("conviction_picks", []):
        name = pick.get("name", "")
        if name and name not in seen:
            seen.add(name)
            candidates.append(name)

    # Priority 4: Overreaction stocks from Scryer (even if not in signal list)
    for name in shared_state.get("scryer_output", {}).get("overreaction_stocks", []):
        if name and name not in seen:
            seen.add(name)
            candidates.append(name)

    return candidates


# ─────────────────────────────────────────────────────────────────────────────
def _compute_composite_conviction(stock: str, shared_state: dict, weights: dict) -> tuple:
    """
    Composite conviction formula:
      conviction = gate_score*0.30 + claude_score*0.25 + overreaction*0.20 + tech*0.15 + news_conf*0.10
    Returns (score: float, components: dict)
    """
    components = {}

    # ── Gate score (0-100): from paper_trader gate logic (gates_passed / 8 * 100)
    gate_score = _get_gate_score(stock, shared_state)
    components["gate_score"] = gate_score

    # ── Claude score (0-100): from claude_analysis conviction_picks
    claude_score = _get_claude_score(stock, shared_state)
    components["claude_score"] = claude_score

    # ── Overreaction score (0-100): from Scryer shock delta
    overreaction_score = _get_overreaction_score(stock, shared_state)
    components["overreaction_score"] = overreaction_score

    # ── Technical score (0-100): from technical_data.tech_score
    tech_score = _get_technical_score(stock, shared_state)
    components["technical_score"] = tech_score

    # ── News confidence (0-100): from Scryer confidence-weighted news
    news_conf = _get_news_confidence(stock, shared_state)
    components["news_confidence"] = news_conf

    # ── Weighted composite
    w_gate  = weights.get("gate_score",         0.30)
    w_claude= weights.get("claude_score",        0.25)
    w_over  = weights.get("overreaction_score",  0.20)
    w_tech  = weights.get("technical_score",     0.15)
    w_news  = weights.get("news_confidence",     0.10)

    composite = (
        gate_score         * w_gate  +
        claude_score       * w_claude +
        overreaction_score * w_over  +
        tech_score         * w_tech  +
        news_conf          * w_news
    )
    components["composite"] = round(composite, 2)
    return composite, components


def _get_gate_score(stock: str, shared_state: dict) -> float:
    """Get gates_passed from Claude analysis conviction_picks, normalized 0-100."""
    for pick in shared_state.get("claude_analysis", {}).get("conviction_picks", []):
        if pick.get("name") == stock:
            gates = pick.get("gates_passed", 0)
            return min(100, gates / 8 * 100)
    # Fallback: check risk_reviewed_signals
    for sig in shared_state.get("risk_reviewed_signals", []):
        if sig.get("name") == stock:
            score = sig.get("score", 0)
            return min(100, score)
    return 50.0  # neutral default


def _get_claude_score(stock: str, shared_state: dict) -> float:
    """Get revised_score from Claude conviction picks, else use scanner score."""
    for pick in shared_state.get("claude_analysis", {}).get("conviction_picks", []):
        if pick.get("name") == stock:
            return float(pick.get("revised_score", pick.get("original_score", 50)))
    for sig in shared_state.get("actionable_signals", []) + shared_state.get("trade_signals", []):
        if sig.get("name") == stock:
            return float(sig.get("score", 50))
    return 50.0


def _get_overreaction_score(stock: str, shared_state: dict) -> float:
    """
    Convert Scryer shock delta to 0-100 score.
    delta=0 → score=50 (neutral)
    delta=+5 → score=85 (strong overreaction → buy opportunity)
    delta=-5 → score=15 (underreaction → caution)
    """
    delta_data = shared_state.get("scryer_output", {}).get("shock_vs_reality", {}).get(stock)
    if not delta_data:
        return 50.0
    delta = delta_data.get("delta", 0.0)
    # Map: delta [-10, +10] → score [0, 100] with 0 mapping to 50
    score = 50 + (delta * 5)
    return max(0, min(100, score))


def _get_technical_score(stock: str, shared_state: dict) -> float:
    """Get tech_score from technical_data, normalized 0-100."""
    tech = shared_state.get("technical_data", {}).get(stock, {})
    raw = tech.get("tech_score", None)
    if raw is not None:
        return max(0, min(100, float(raw) * 10))  # tech_score 0-10 → 0-100
    # Fallback: compute from RSI + EMA + MACD
    score = 50.0
    rsi = tech.get("rsi", 50)
    if 40 <= rsi <= 60:
        score += 10
    elif rsi < 35 or rsi > 70:
        score -= 10
    if tech.get("above_ema50"):
        score += 10
    if tech.get("macd_bullish"):
        score += 10
    return max(0, min(100, score))


def _get_news_confidence(stock: str, shared_state: dict) -> float:
    """
    Average credibility of news items mentioning this stock.
    Returns 0-100 (multiply raw 0-1 credibility by 100).
    """
    weighted_news = shared_state.get("scryer_output", {}).get("confidence_weighted_news", [])
    relevant = [n for n in weighted_news
                if stock in n.get("stocks_affected", []) or stock.lower() in (n.get("headline", "")).lower()]
    if not relevant:
        return 60.0  # neutral default
    avg_cred = sum(n.get("credibility_score", 0.6) for n in relevant) / len(relevant)
    return round(avg_cred * 100, 1)


# ─────────────────────────────────────────────────────────────────────────────
def _classify_conviction_tier(score: float, thresholds: dict) -> str:
    """Route stock to AUTO_EXECUTE / HITL_REQUIRED / DEBATE_REQUIRED / SKIP."""
    auto_min  = thresholds.get("auto_execute_min",    85)
    hitl_min  = thresholds.get("hitl_lower_bound",    70)
    debate_min= thresholds.get("debate_lower_bound",  55)

    if score >= auto_min:
        return "AUTO_EXECUTE"
    elif score >= hitl_min:
        return "HITL_REQUIRED"
    elif score >= debate_min:
        return "DEBATE_REQUIRED"
    else:
        return "SKIP"


# ─────────────────────────────────────────────────────────────────────────────
def _generate_overreaction_setup(stock: str, conviction: float,
                                  shared_state: dict, config: dict) -> dict | None:
    """
    If a stock has a meaningful Scryer delta, generate an overreaction trade setup.
    Returns setup dict or None.
    """
    delta_data = shared_state.get("scryer_output", {}).get("shock_vs_reality", {}).get(stock)
    if not delta_data:
        return None

    delta     = delta_data.get("delta", 0.0)
    threshold = config.get("gate_overrides", {}).get("shock_delta_threshold", 3.0)

    if abs(delta) < threshold:
        return None

    # Overreaction confidence: scaled from delta magnitude
    overreaction_confidence = min(100, int(abs(delta) * 12))

    # Get signal for context
    signal = _get_signal(stock, shared_state)
    entry  = signal.get("entry_low", signal.get("cmp", 0)) if signal else 0
    t2     = signal.get("target2", 0) if signal else 0
    sl     = signal.get("stop_loss", 0) if signal else 0

    setup_type = "BUY_THE_PANIC" if delta > 0 else "FADE_THE_GAP"

    # Quant thesis
    direction = "negative" if delta_data.get("avg_sentiment", 0) < 0 else "mild"
    thesis = (
        f"News shock {abs(delta):.1f}pts {'above' if delta > 0 else 'below'} price reality — "
        f"smart money {'absorbing selling' if delta > 0 else 'distributing into rally'}"
    )

    return {
        "name":                   stock,
        "type":                   setup_type,
        "shock_delta":            round(delta, 2),
        "overreaction_confidence": overreaction_confidence,
        "composite_conviction":   round(conviction, 1),
        "quant_thesis":           thesis,
        "entry":                  entry,
        "target2":                t2,
        "stop_loss":              sl,
        "avg_sentiment":          delta_data.get("avg_sentiment", 0),
        "price_chg_pct":          delta_data.get("price_chg_pct", 0),
        "headlines":              delta_data.get("headlines", [])
    }


# ─────────────────────────────────────────────────────────────────────────────
def _get_signal(stock: str, shared_state: dict) -> dict:
    """Find the trade signal for a stock from all signal lists."""
    for sig in (shared_state.get("risk_reviewed_signals", []) +
                shared_state.get("actionable_signals", []) +
                shared_state.get("trade_signals", [])):
        if sig.get("name") == stock:
            return sig
    return {}


def get_conviction(stock: str, shared_state: dict) -> dict:
    """Convenience: return conviction_map entry for a stock."""
    return shared_state.get("quant_output", {}).get("conviction_map", {}).get(stock, {})
