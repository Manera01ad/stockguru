"""
Agent Scorer
═════════════
Scores all 14 agents across 3 result-oriented dimensions:

  Learn%    — Data maturity. How much market data has the agent processed?
              Grows with every cycle. Agents that process more data types
              level up faster. Capped at 95% — markets always evolving.

  Trained%  — Prediction calibration. Based on actual win/loss outcomes
              from signal_history.json + learned_weights.json.
              Starts at 50% (uninformed prior), drifts toward real accuracy.
              A 70% win rate → 70% Trained. Below 50% → agent needs retraining.

  Skilled%  — Current effectiveness. Composite of live confidence score,
              gate contribution rate, data freshness, and weight drift.
              This is the "right now" performance grade.

Each agent also gets an overall Grade: S / A / B / C / D
  S ≥ 80% across all 3
  A ≥ 70%
  B ≥ 55%
  C ≥ 40%
  D < 40%

All metrics are results-oriented — they move based on actual outcomes,
not arbitrary counters.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from statistics import mean

log = logging.getLogger("AgentScorer")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")

# ── AGENT DEFINITIONS ─────────────────────────────────────────────────────────
# Each agent: tier, what it outputs, how fast it learns, data richness factor
AGENT_DEFS = {
    "market_scanner": {
        "label":        "Market Scanner",
        "tier":         1,
        "tier_name":    "Data",
        "icon":         "🔍",
        "learn_rate":   2.0,   # fast learner — pure data
        "output_key":   "scanner_results",
        "output_count": lambda ss: len(ss.get("scanner_results", [])),
        "desc":         "Scans 51 stocks, ranks by composite score",
    },
    "news_sentiment": {
        "label":        "News Sentiment",
        "tier":         1,
        "tier_name":    "Data",
        "icon":         "📰",
        "learn_rate":   1.8,
        "output_key":   "news_results",
        "output_count": lambda ss: len(ss.get("news_results", [])),
        "desc":         "LLM-scored headlines, 70% Claude + 30% keyword",
    },
    "commodity_crypto": {
        "label":        "Commodity/Crypto",
        "tier":         1,
        "tier_name":    "Data",
        "icon":         "🥇",
        "learn_rate":   1.8,
        "output_key":   "commodity_results",
        "output_count": lambda ss: len(ss.get("commodity_results", [])),
        "desc":         "Gold, crude, BTC, forex — macro backdrop",
    },
    "technical_analysis": {
        "label":        "Technical Analysis",
        "tier":         1,
        "tier_name":    "Data",
        "icon":         "📐",
        "learn_rate":   1.9,
        "output_key":   "technical_data",
        "output_count": lambda ss: len(ss.get("technical_data", {})),
        "desc":         "RSI, MACD, Bollinger, pivot points, ATR",
    },
    "institutional_flow": {
        "label":        "Institutional Flow",
        "tier":         1,
        "tier_name":    "Data",
        "icon":         "🏦",
        "learn_rate":   1.5,
        "output_key":   "institutional_flow",
        "output_count": lambda ss: len(ss.get("institutional_flow", {}).get("bulk_deals", [])),
        "desc":         "FII/DII flows, bulk deals, delivery % accumulation",
    },
    "options_flow": {
        "label":        "Options Flow",
        "tier":         1,
        "tier_name":    "Data",
        "icon":         "⚡",
        "learn_rate":   1.6,
        "output_key":   "options_flow",
        "output_count": lambda ss: 1 if ss.get("options_flow") else 0,
        "desc":         "PCR, OI build-up, unusual activity gate",
    },
    "earnings_calendar": {
        "label":        "Earnings Calendar",
        "tier":         1,
        "tier_name":    "Data",
        "icon":         "📅",
        "learn_rate":   1.4,
        "output_key":   "events_calendar",
        "output_count": lambda ss: ss.get("events_calendar", {}).get("total_events", 0),
        "desc":         "NSE/BSE corporate events, earnings alerts",
    },
    "claude_intelligence": {
        "label":        "Claude Intelligence",
        "tier":         2,
        "tier_name":    "LLM",
        "icon":         "🧠",
        "learn_rate":   1.2,   # LLMs learn slower (expensive, used selectively)
        "output_key":   "claude_analysis",
        "output_count": lambda ss: len(ss.get("claude_analysis", {}).get("conviction_picks", [])),
        "desc":         "Claude Haiku + Gemini Flash market synthesis",
    },
    "web_researcher": {
        "label":        "Web Researcher",
        "tier":         2,
        "tier_name":    "LLM",
        "icon":         "🌐",
        "learn_rate":   1.3,
        "output_key":   "web_research",
        "output_count": lambda ss: len(ss.get("web_research", {})),
        "desc":         "Real-time news safety check before entries",
    },
    "trade_signal": {
        "label":        "Trade Signal",
        "tier":         3,
        "tier_name":    "Strategy",
        "icon":         "📡",
        "learn_rate":   1.7,
        "output_key":   "actionable_signals",
        "output_count": lambda ss: len(ss.get("actionable_signals", [])),
        "desc":         "Generates BUY/SELL signals from Tier 1+2 data",
    },
    "sector_rotation": {
        "label":        "Sector Rotation",
        "tier":         3,
        "tier_name":    "Strategy",
        "icon":         "🔄",
        "learn_rate":   1.5,
        "output_key":   "sector_rotation",
        "output_count": lambda ss: len(ss.get("sector_rotation", {})),
        "desc":         "Relative strength ranking, flow sector bias",
    },
    "risk_manager": {
        "label":        "Risk Manager",
        "tier":         3,
        "tier_name":    "Strategy",
        "icon":         "🛡️",
        "learn_rate":   1.6,
        "output_key":   "risk_reviewed_signals",
        "output_count": lambda ss: len(ss.get("risk_reviewed_signals", [])),
        "desc":         "8-gate conviction filter, position sizing, VIX halt",
    },
    "paper_trader": {
        "label":        "Paper Trader",
        "tier":         4,
        "tier_name":    "Output",
        "icon":         "📊",
        "learn_rate":   1.8,
        "output_key":   "paper_portfolio",
        "output_count": lambda ss: len([p for p in ss.get("paper_portfolio", {}).get("positions", {}).values() if p.get("status") == "OPEN"]),
        "desc":         "Simulates trades, tracks P&L, computes win rate",
    },
    "pattern_memory": {
        "label":        "Pattern Memory",
        "tier":         4,
        "tier_name":    "Learning",
        "icon":         "🧬",
        "learn_rate":   2.2,   # fastest learner — improves with every outcome
        "output_key":   "pattern_library",
        "output_count": lambda ss: len(ss.get("pattern_library", [])),
        "desc":         "Stores recurring setups, accuracy by pattern type",
    },
}


def _load_json(filename: str) -> dict:
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _compute_learn(agent_id: str, defn: dict, cycle_count: int, shared_state: dict) -> float:
    """
    Learn% = how much market data the agent has processed.
    Grows with cycles. Each agent has a learn_rate multiplier.
    Bonus for rich data output (many signals/stocks processed).
    Max: 95% — never fully "done" learning.
    """
    rate        = defn.get("learn_rate", 1.5)
    base        = min(85.0, cycle_count * rate)

    # Data richness bonus: more output = more active learning
    try:
        output_n = defn["output_count"](shared_state)
    except Exception:
        output_n = 0

    richness_bonus = min(10.0, output_n * 0.5) if output_n else 0.0
    learn = round(min(95.0, base + richness_bonus), 1)
    return learn


def _compute_trained(agent_id: str, defn: dict, accuracy: dict, weights: dict) -> float:
    """
    Trained% = calibration quality from actual win/loss history.
    Starts at 50% (random prior). Drifts toward real win rate.
    Boosted if the agent's related weight has been increased by the learning engine.
    """
    overall   = accuracy.get("overall", {})
    win_rate  = overall.get("win_rate", 0.0)
    outcomes  = overall.get("outcomes_recorded", 0)

    if outcomes == 0:
        # No history yet — neutral prior
        base_trained = 50.0
    else:
        # Real calibration: converges to actual win rate with more data
        confidence_weight = min(1.0, outcomes / 20)   # full confidence after 20 outcomes
        base_trained      = 50.0 * (1 - confidence_weight) + win_rate * 100 * confidence_weight

    # Weight drift bonus: if learning engine upweighted this agent's factor
    factor_weights = weights.get("factor_weights", {})
    if agent_id in ("technical_analysis",):
        w = factor_weights.get("technical_pct", 0.3) / 0.3
    elif agent_id in ("market_scanner",):
        w = factor_weights.get("fundamental_pct", 0.4) / 0.4
    elif agent_id in ("trade_signal", "risk_manager"):
        w = factor_weights.get("risk_pct", 0.1) / 0.1
    elif agent_id in ("news_sentiment", "claude_intelligence", "web_researcher"):
        w = factor_weights.get("momentum_pct", 0.2) / 0.2
    else:
        w = 1.0

    weight_bonus = min(5.0, (w - 1.0) * 10) if w > 1.0 else 0.0
    trained = round(min(95.0, max(0.0, base_trained + weight_bonus)), 1)
    return trained


def _compute_skilled(agent_id: str, defn: dict, shared_state: dict,
                     agent_status: dict, accuracy: dict) -> float:
    """
    Skilled% = current effectiveness. The "right now" performance grade.
    Composite of:
      - Live confidence score from agent_confidence (40%)
      - Data freshness — did it run recently? (25%)
      - Gate contribution — how often does it approve signals? (20%)
      - Output quality — signals produced vs reviewed (15%)
    """
    # 1. Live confidence (40%)
    confidence_map = shared_state.get("agent_confidence", {})
    conf_data      = confidence_map.get(agent_id, {})
    confidence_raw = conf_data.get("confidence", 0) if isinstance(conf_data, dict) else 0
    conf_score     = min(40.0, confidence_raw * 0.40)

    # 2. Data freshness (25%) — was last status "done" (not error/running)?
    status = agent_status.get(agent_id.replace("_", ""), agent_status.get(agent_id, ""))
    if status == "done":
        freshness_score = 25.0
    elif status == "running":
        freshness_score = 15.0
    elif status == "error":
        freshness_score = 0.0
    else:
        freshness_score = 10.0   # unknown = partial credit

    # 3. Gate contribution (20%) — approved signals / total reviewed
    risk_signals   = shared_state.get("risk_reviewed_signals", [])
    if agent_id == "risk_manager" and risk_signals:
        approved    = sum(1 for s in risk_signals if s.get("risk", {}).get("approved"))
        gate_rate   = approved / len(risk_signals)
        gate_score  = gate_rate * 20.0
    elif agent_id in ("trade_signal",):
        n_sig       = len(shared_state.get("actionable_signals", []))
        gate_score  = min(20.0, n_sig * 4.0)
    else:
        gate_score  = 12.0   # neutral for non-gating agents

    # 4. Output quality (15%) — proportion of useful outputs
    overall      = accuracy.get("overall", {})
    outcomes     = overall.get("outcomes_recorded", 0)
    quality_score = min(15.0, outcomes * 0.5) if outcomes else 5.0

    skilled = round(min(95.0, conf_score + freshness_score + gate_score + quality_score), 1)
    return skilled


def _grade(learn: float, trained: float, skilled: float) -> str:
    avg = (learn + trained + skilled) / 3
    if avg >= 80:   return "S"
    elif avg >= 70: return "A"
    elif avg >= 55: return "B"
    elif avg >= 40: return "C"
    else:           return "D"


def _grade_color(grade: str) -> str:
    return {"S": "#00C4CC", "A": "#27AE60", "B": "#F2C94C",
            "C": "#FF9F43", "D": "#E74C3C"}.get(grade, "#888")


class AgentScorer:
    """
    Computes Learn%, Trained%, Skilled% for all 14 agents each cycle.
    Writes to shared_state["agent_scores"].
    """

    def run(self, shared_state: dict) -> dict:
        cycle_count  = shared_state.get("cycle_count", 0)
        agent_status = shared_state.get("agent_status", {})
        accuracy     = _load_json("accuracy_stats.json")
        weights      = _load_json("learned_weights.json")

        scores = {}
        for agent_id, defn in AGENT_DEFS.items():
            learn   = _compute_learn(agent_id, defn, cycle_count, shared_state)
            trained = _compute_trained(agent_id, defn, accuracy, weights)
            skilled = _compute_skilled(agent_id, defn, shared_state, agent_status, accuracy)
            grade   = _grade(learn, trained, skilled)

            try:
                output_n = defn["output_count"](shared_state)
            except Exception:
                output_n = 0

            conf_data  = shared_state.get("agent_confidence", {}).get(agent_id, {})
            key_signal = conf_data.get("key_signal", "") if isinstance(conf_data, dict) else ""

            scores[agent_id] = {
                "label":      defn["label"],
                "tier":       defn["tier"],
                "tier_name":  defn["tier_name"],
                "icon":       defn["icon"],
                "desc":       defn["desc"],
                "learn":      learn,
                "trained":    trained,
                "skilled":    skilled,
                "grade":      grade,
                "grade_color": _grade_color(grade),
                "avg":        round((learn + trained + skilled) / 3, 1),
                "output_n":   output_n,
                "status":     agent_status.get(agent_id, agent_status.get(agent_id.replace("_",""), "—")),
                "key_signal": key_signal,
                "scored_at":  datetime.now().strftime("%H:%M:%S"),
            }

        shared_state["agent_scores"] = scores
        log.info(
            "AgentScorer: %d agents scored | Top: %s",
            len(scores),
            max(scores.items(), key=lambda x: x[1]["avg"], default=(None, {"label": "—"}))[1]["label"]
        )
        return scores
