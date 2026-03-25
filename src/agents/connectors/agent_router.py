"""
Agent Router
════════════
Confidence-based conditional routing for the 14-agent pipeline.

Before firing expensive LLM calls (Claude + Gemini), evaluates Tier 1
agent confidence scores from shared_state["agent_confidence"].

Decision logic:
  - If avg Tier 1 confidence >= 55 AND scanner has >= 3 hits → run LLM
  - If VIX > 28 → always run LLM (high-volatility needs more intelligence)
  - Otherwise → skip LLM, saves ~$0.002 per skipped cycle

Writes routing_decisions to shared_state so dashboard can display
how often LLM cycles are being saved.
"""

import logging
from datetime import datetime
from statistics import mean

log = logging.getLogger("AgentRouter")

# Threshold: avg Tier 1 confidence required to justify LLM call
CONFIDENCE_THRESHOLD = 55.0
MIN_SCANNER_HITS     = 3
HIGH_VIX_OVERRIDE    = 28.0   # always run LLM in high volatility


class AgentRouter:
    """
    Evaluates Tier 1 output quality and decides whether downstream
    LLM agents should run this cycle.
    """

    def __init__(self):
        self._cycles_total  = 0
        self._cycles_saved  = 0

    def route(self, shared_state: dict) -> dict:
        """
        Evaluate shared_state and return a routing decision dict.
        Call this before claude_intelligence.run() in the agent cycle.
        """
        self._cycles_total += 1

        confidence_map = shared_state.get("agent_confidence", {})
        scores = [
            v.get("confidence", 0)
            for v in confidence_map.values()
            if isinstance(v, dict) and "confidence" in v
        ]
        avg_confidence = round(mean(scores), 1) if scores else 0.0

        scanner_hits = len(shared_state.get("scanner_results", []))
        vix = (
            shared_state.get("index_prices", {})
            .get("INDIA VIX", {})
            .get("price", 15.0)
        )
        try:
            vix = float(vix)
        except (TypeError, ValueError):
            vix = 15.0

        high_impact_news = len(shared_state.get("news_high_impact", []))

        # Decision
        if vix >= HIGH_VIX_OVERRIDE:
            run_llm = True
            reason  = f"VIX={vix:.1f} override — high volatility demands LLM analysis"
        elif avg_confidence >= CONFIDENCE_THRESHOLD and scanner_hits >= MIN_SCANNER_HITS:
            run_llm = True
            reason  = (
                f"Tier 1 confidence {avg_confidence}% ≥ {CONFIDENCE_THRESHOLD}% "
                f"with {scanner_hits} scanner hits"
            )
        elif high_impact_news >= 5:
            run_llm = True
            reason  = f"{high_impact_news} high-impact news items — LLM needed"
        else:
            run_llm = False
            self._cycles_saved += 1
            reason  = (
                f"Low signal quality: confidence={avg_confidence}% "
                f"(need {CONFIDENCE_THRESHOLD}%), scanner_hits={scanner_hits} "
                f"(need {MIN_SCANNER_HITS})"
            )

        save_rate = round(self._cycles_saved / self._cycles_total * 100, 1) if self._cycles_total else 0

        result = {
            "run_llm":             run_llm,
            "avg_tier1_confidence": avg_confidence,
            "scanner_hits":        scanner_hits,
            "vix":                 vix,
            "high_impact_news":    high_impact_news,
            "routing_reason":      reason,
            "cycle_saved":         not run_llm,
            "cycles_total":        self._cycles_total,
            "cycles_saved":        self._cycles_saved,
            "llm_save_rate_pct":   save_rate,
            "decided_at":          datetime.now().strftime("%H:%M:%S"),
        }

        log.info(
            f"AgentRouter: LLM={'RUN' if run_llm else 'SKIP'} | "
            f"confidence={avg_confidence}% | scanner={scanner_hits} | "
            f"VIX={vix:.1f} | saved={self._cycles_saved}/{self._cycles_total}"
        )
        return result
