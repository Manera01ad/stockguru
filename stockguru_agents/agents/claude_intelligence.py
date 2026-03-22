"""
AGENT 7 — CLAUDE INTELLIGENCE (LLM Brain)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : The master intelligence layer. Reviews ALL agent outputs
          together and provides:
          ① Market narrative (what is really happening)
          ② Conviction picks (with 8-gate scoring)
          ③ Score corrections (override rule-based scores)
          ④ Parallel Gemini review (second opinion)
          ⑤ Learning feedback (accuracy-aware confidence)

Strategy:
  ONE batched API call per cycle (cost ~$0.001 per call with Haiku)
  Caches result for 10 minutes (no duplicate calls in same cycle)
  Falls back gracefully if API unavailable

LLMs used:
  Primary: Claude Haiku 4.5 (~$2/month at 4 calls/hour)
  Parallel: Gemini 1.5 Flash (free tier: 15 req/min, 1M tokens/day)
"""

import os
import json
import time
import logging
from datetime import datetime

log = logging.getLogger("ClaudeIntelligence")

# ── API KEYS ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")

CLAUDE_MODEL      = "claude-haiku-4-5-20251001"   # cheapest, fast enough
GEMINI_MODEL      = "gemini-2.5-flash"

CACHE_SECONDS     = 600   # 10 min — avoid duplicate calls in same cycle

# ── CACHE ─────────────────────────────────────────────────────────────────────
_last_analysis      = None
_last_analysis_time = 0

# ── KNOWLEDGE LOADER ─────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _load_trading_skills():
    path = os.path.join(_BASE, "knowledge", "trading_skills.txt")
    try:
        with open(path) as f:
            # Return just the rules section (first 80 lines = enough context)
            lines = f.readlines()
            return "".join(lines[:80])
    except Exception:
        return "Apply professional risk management: 2% per trade, 2.5:1 R:R min, trend alignment."

def _load_accuracy_context(shared_state):
    stats = shared_state.get("accuracy_stats", {})
    overall = stats.get("overall", {})
    by_sec  = stats.get("by_sector", {})

    if not overall.get("outcomes_recorded"):
        return "No historical data yet — system learning. Apply conservative stance."

    lines = [
        f"ACCURACY (last {overall.get('outcomes_recorded',0)} outcomes):",
        f"  Overall win rate: {overall.get('win_rate',0)*100:.1f}%",
        f"  Avg win: +{overall.get('avg_win_pct',0):.1f}% | Avg loss: {overall.get('avg_loss_pct',0):.1f}%",
        f"  Expectancy: {overall.get('expectancy',0):.2f}% per trade",
    ]
    for sec, d in by_sec.items():
        if d.get("total", 0) >= 5:
            lines.append(f"  {sec}: {d.get('win_rate',0)*100:.0f}% ({d.get('total',0)} trades)")
    return "\n".join(lines)

def _load_top_patterns(shared_state):
    patterns = shared_state.get("pattern_library", [])
    if not patterns:
        return "No patterns established yet — learning in progress."
    return "\n".join([
        f"  P{i+1}: {p['description']} → {p.get('win_rate',0)*100:.0f}% win rate ({p.get('count',0)} trades)"
        for i, p in enumerate(patterns[:5])
    ])

_PM_LOG_PATH = os.path.join(_BASE, "data", "post_mortem_log.json")

def _load_post_mortem_context(shared_state) -> str:
    """
    Build a compact post-mortem brief for the LLM prompt.

    Sources (in priority order):
      1. shared_state["post_mortem_output"] — latest cycle summary
      2. shared_state["post_mortem_llm_note"] — LLM-generated global lesson
      3. data/post_mortem_log.json — last 3 failure reflexions
    """
    lines = []

    # ── LLM global lesson (written by post_mortem when it runs its own LLM) ──
    llm_note = shared_state.get("post_mortem_llm_note")
    if llm_note:
        lines.append(f"GLOBAL LESSON (post-mortem LLM): {llm_note}")

    # ── Latest cycle summary ──────────────────────────────────────────────────
    pm_out = shared_state.get("post_mortem_output", {})
    if pm_out.get("analyzed_this_cycle", 0) > 0:
        failures = ", ".join(pm_out.get("new_failures", []))
        adj_count = len(pm_out.get("adjustments_made", []))
        lines.append(
            f"This cycle: {pm_out['analyzed_this_cycle']} new failures ({failures}) "
            f"→ {adj_count} weight/config adjustments made."
        )
        llm_diag = pm_out.get("llm_diagnosis")
        if llm_diag:
            lines.append(f"Root diagnosis: {llm_diag}")
    elif pm_out.get("total_analyzed", 0) > 0:
        lines.append(
            f"No new failures this cycle. "
            f"Total post-mortems in history: {pm_out['total_analyzed']}."
        )

    # ── Last 3 failure reflexions from disk ───────────────────────────────────
    try:
        with open(_PM_LOG_PATH) as f:
            pm_log = json.load(f)
        # Most recent failures first
        failures_only = [r for r in pm_log if r.get("outcome") == "FAILURE"]
        recent = failures_only[-3:][::-1]
        if recent:
            lines.append("RECENT FAILURE REFLEXIONS:")
            for r in recent:
                ticker     = r.get("ticker", "?")
                root_cause = r.get("root_cause", "unknown")
                reflexion  = r.get("reflexion", "")[:120]  # cap length in prompt
                lines.append(f"  • {ticker} | cause={root_cause} | {reflexion}")
    except Exception:
        pass  # No log file yet — first run

    if not lines:
        return "No post-mortem data yet — system is learning from live results."

    return "\n".join(lines)

# ── PROMPT BUILDER ────────────────────────────────────────────────────────────
def _build_data_summary(shared_state):
    """Build a compact JSON summary of all agent data for the prompt."""
    scanner   = shared_state.get("scanner_results", [])
    technical = shared_state.get("technical_data", {})
    inst      = shared_state.get("institutional_flow", {})
    options   = shared_state.get("options_flow", {})
    news_hi   = shared_state.get("news_high_impact", [])
    sector_r  = shared_state.get("sector_rotation", {})
    commodity = shared_state.get("commodity_sentiment", "NEUTRAL")
    mood      = shared_state.get("market_sentiment_score", 0)

    # Compact scanner summary (top 8 only)
    scanner_s = []
    for s in scanner[:8]:
        tech = technical.get(s["name"], {})
        scanner_s.append({
            "name":       s["name"],
            "sector":     s["sector"],
            "score":      s["score"],
            "signal":     s["signal"],
            "chg_pct":    s.get("change_pct", 0),
            "vol_surge":  s.get("vol_surge", 1),
            "rsi":        tech.get("rsi"),
            "macd_bull":  tech.get("macd_bullish"),
            "above_ema50": tech.get("above_ema50"),
            "tech_score": tech.get("tech_score"),
        })

    # New enriched data feeds
    india_vix  = shared_state.get("india_vix", {})
    iv_rank    = shared_state.get("iv_rank", {})
    rollover   = shared_state.get("rollover_data", {})
    ad_data    = shared_state.get("advance_decline", {})

    summary = {
        "market": {
            "mood_score":      round(mood, 2),
            "commodity_macro": commodity,
            "fii_net_crore":   inst.get("fii_net_crore", "N/A"),
            "fii_signal":      inst.get("fii_signal", "NEUTRAL"),
            "nifty_pcr":       options.get("nifty_pcr"),
            "options_bias":    options.get("market_bias", "NEUTRAL"),
            "breadth":         sector_r.get("market_breadth", "UNKNOWN"),
            "top_sectors":     sector_r.get("top_sectors", [])[:3],
        },
        "volatility": {
            "india_vix":       india_vix.get("level"),
            "vix_regime":      india_vix.get("regime", "UNKNOWN"),
            "vix_alert":       india_vix.get("alert", ""),
            "nifty_ivr":       iv_rank.get("nifty_ivr"),
            "iv_regime":       iv_rank.get("iv_regime", "NORMAL"),
            "strategy_bias":   iv_rank.get("strategy_bias", "BALANCED"),
            "atm_iv_pct":      iv_rank.get("nifty_iv_pct"),
        },
        "positioning": {
            "rollover_pct":    rollover.get("nifty_rollover_pct"),
            "rollover_vs_avg": rollover.get("diff_vs_avg"),
            "rollover_read":   rollover.get("interpretation", ""),
            "rollover_strength": rollover.get("strength", ""),
            "ad_ratio":        ad_data.get("ad_ratio"),
            "advances":        ad_data.get("advances"),
            "declines":        ad_data.get("declines"),
            "breadth_signal":  ad_data.get("breadth_signal", ""),
        },
        "top_stocks": scanner_s,
        "high_impact_news": [
            {"h": n["headline"][:70], "s": n["sentiment_score"]}
            for n in news_hi[:4]
        ],
    }
    return json.dumps(summary, indent=2)

SYSTEM_PROMPT = """You are StockGuru's Master Intelligence — an expert Indian equity analyst who combines quantitative data with professional trading discipline.

You review outputs from 14 specialized agents and provide the master verdict, including market elaboration and short-term forecast.

Input data includes: FII/DII flows, PCR, India VIX, IV Rank, rollover data, Advance-Decline breadth, sector rotation, news sentiment, and individual stock technicals.

{skills}

{accuracy}

RECENT POST-MORTEM INSIGHTS (failures analyzed by the learning engine):
{post_mortem}

TOP PROVEN PATTERNS:
{patterns}

RESPONSE: Return ONLY valid JSON, no markdown, no explanation outside JSON:
{{
  "market_condition": "BULLISH|BEARISH|NEUTRAL|VOLATILE",
  "market_narrative": "<3-4 sentence elaboration — what agents are seeing right now, what the data collectively says>",
  "market_stance": "AGGRESSIVE|MODERATE|CONSERVATIVE|AVOID",
  "market_forecast": {{
    "next_session": "<1 sentence — what to expect in tomorrow's trading session>",
    "next_week":    "<1 sentence — directional view for the next 5 trading days>",
    "nifty_support":    <price level as number or null>,
    "nifty_resistance": <price level as number or null>,
    "bias_change_triggers": ["<event or data that would flip the current bias>", "<second trigger>"]
  }},
  "vix_read":        "<1 sentence — what today's VIX level means for position sizing and strategy>",
  "iv_environment":  "<1 sentence — IV rank implication: should traders buy or sell options premium?>",
  "breadth_read":    "<1 sentence — what A/D ratio and rollover data say about market participation>",
  "conviction_picks": [
    {{
      "name": "<STOCK NAME>",
      "original_score": <number>,
      "revised_score": <number>,
      "gates_passed": <0-8>,
      "gate_detail": {{
        "score_gate": <bool>,
        "rsi_gate": <bool>,
        "volume_gate": <bool>,
        "trend_gate": <bool>,
        "macd_gate": <bool>,
        "news_gate": <bool>,
        "fii_gate": <bool>,
        "options_gate": <bool>
      }},
      "execute_paper_trade": <bool — true only if gates_passed >= 6>,
      "entry_thesis": "<specific 1-sentence reason citing actual data>",
      "key_risk": "<specific 1-sentence risk>",
      "hold_period": "<1-2 weeks|2-4 weeks|monitor>"
    }}
  ],
  "signals_to_downgrade": ["<name>"],
  "key_risks": ["<risk1>", "<risk2>"],
  "rules_applied": ["R1", "R5", "R22"],
  "learning_note": "<what this cycle teaches the system>"
}}

CRITICAL RULES:
- execute_paper_trade = true ONLY when gates_passed >= 6 of 8
- Be conservative — no trade is better than a wrong trade
- If FII selling > ₹2000Cr, no new longs (R22)
- If VIX > 20, set market_stance to CONSERVATIVE minimum
- Use vix_read, iv_environment, breadth_read to elaborate the full market picture
- market_forecast must be actionable and specific (use actual numbers where data is available)"""

# ── CLAUDE API CALL ───────────────────────────────────────────────────────────
def _call_claude(data_summary, shared_state):
    if not ANTHROPIC_API_KEY:
        log.warning("ClaudeIntelligence: ANTHROPIC_API_KEY not set — skipping")
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        system = SYSTEM_PROMPT.format(
            skills      = _load_trading_skills(),
            accuracy    = _load_accuracy_context(shared_state),
            post_mortem = _load_post_mortem_context(shared_state),
            patterns    = _load_top_patterns(shared_state),
        )
        msg = client.messages.create(
            model      = CLAUDE_MODEL,
            max_tokens = 2800,
            system     = system,
            messages   = [{
                "role":    "user",
                "content": f"Review current market data and return your analysis:\n{data_summary}"
            }]
        )
        text = msg.content[0].text.strip()
        # Extract JSON (Claude sometimes adds text around it)
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return json.loads(text)
    except Exception as e:
        log.error("Claude API error: %s", e)
        return None

# ── GEMINI PARALLEL CALL ──────────────────────────────────────────────────────
def _call_gemini(data_summary):
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model  = genai.GenerativeModel(GEMINI_MODEL)
        prompt = (
            "You are a senior Indian equity analyst. Review this market data.\n"
            "Return ONLY JSON: {\"market_bias\":\"BULLISH|BEARISH|NEUTRAL\","
            "\"top_2_picks\":[\"STOCK1\",\"STOCK2\"],"
            "\"confidence\":\"HIGH|MEDIUM|LOW\","
            "\"biggest_risk\":\"<one sentence>\"}\n\n"
            f"Data:\n{data_summary}"
        )
        resp  = model.generate_content(prompt)
        text  = resp.text
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        log.debug("Gemini API error: %s", e)
    return None

# ── RECONCILE VIEWS ───────────────────────────────────────────────────────────
def _reconcile(claude_r, gemini_r):
    """Merge Claude + Gemini views. Flag disagreements."""
    if not gemini_r:
        return claude_r

    g_picks = set(gemini_r.get("top_2_picks", []))
    g_bias  = gemini_r.get("market_bias", "NEUTRAL")
    c_cond  = claude_r.get("market_condition", "NEUTRAL")

    # Flag divergence
    c_bull = "BULLISH" in c_cond
    g_bull = g_bias == "BULLISH"
    if c_bull != g_bull:
        claude_r["gemini_disagrees"] = f"Gemini={g_bias} vs Claude={c_cond} — reduce size"
        if claude_r.get("market_stance") == "AGGRESSIVE":
            claude_r["market_stance"] = "MODERATE"

    # Boost picks both agree on
    for pick in claude_r.get("conviction_picks", []):
        if pick["name"] in g_picks:
            pick["gemini_confirmed"] = True
            gates = pick.get("gates_passed", 0)
            pick["gates_passed"] = min(8, gates + 1)  # Gemini confirmation counts as +1 gate

    claude_r["gemini_bias"]      = g_bias
    claude_r["gemini_confidence"] = gemini_r.get("confidence", "MEDIUM")
    claude_r["gemini_risk"]      = gemini_r.get("biggest_risk", "")
    return claude_r

# ── APPLY ADJUSTMENTS ────────────────────────────────────────────────────────
def _apply_adjustments(analysis, shared_state):
    """Apply Claude's score revisions back to scanner + signal data."""
    picks_map    = {p["name"]: p for p in analysis.get("conviction_picks", [])}
    downgrade_set = set(analysis.get("signals_to_downgrade", []))

    for stock in shared_state.get("scanner_results", []):
        name = stock["name"]
        if name in picks_map:
            stock["claude_score"]    = picks_map[name].get("revised_score", stock["score"])
            stock["claude_gates"]    = picks_map[name].get("gates_passed", 0)
            stock["claude_reviewed"] = True
            stock["execute_paper"]   = picks_map[name].get("execute_paper_trade", False)
        if name in downgrade_set:
            stock["claude_score"]    = max(0, stock["score"] - 15)
            stock["claude_downgrade"] = True

    for sig in shared_state.get("trade_signals", []):
        name = sig["name"]
        if name in picks_map:
            sig["claude_score"]    = picks_map[name].get("revised_score", sig["score"])
            sig["claude_gates"]    = picks_map[name].get("gates_passed", 0)
            sig["claude_thesis"]   = picks_map[name].get("entry_thesis", "")
            sig["claude_risk"]     = picks_map[name].get("key_risk", "")
            sig["execute_paper"]   = picks_map[name].get("execute_paper_trade", False)

# ── FALLBACK ANALYSIS ─────────────────────────────────────────────────────────
def _fallback_analysis():
    return {
        "market_condition": "NEUTRAL",
        "market_narrative": "LLM unavailable — rule-based mode active. Signals from other agents still valid.",
        "market_stance":    "CONSERVATIVE",
        "market_forecast": {
            "next_session":        "Monitor key support levels — LLM offline.",
            "next_week":           "Insufficient data for forecast — LLM offline.",
            "nifty_support":       None,
            "nifty_resistance":    None,
            "bias_change_triggers": ["LLM reconnection"],
        },
        "vix_read":        "Check India VIX on F&O tab for volatility context.",
        "iv_environment":  "IV data available in Options Flow section.",
        "breadth_read":    "Review A/D ratio in Market tab for breadth context.",
        "conviction_picks": [],
        "key_risks":        ["LLM analysis unavailable"],
        "rules_applied":    [],
        "claude_model":     "unavailable",
        "gemini_used":      False,
        "analyzed_at":      datetime.now().strftime("%d %b %H:%M:%S"),
    }

# ── MAIN AGENT ────────────────────────────────────────────────────────────────
def run(shared_state):
    """Run Claude + Gemini intelligence review for current cycle."""
    global _last_analysis, _last_analysis_time

    now = time.time()
    # Cache: if called twice in same cycle, return cached result
    if _last_analysis and (now - _last_analysis_time) < CACHE_SECONDS:
        log.info("ClaudeIntelligence: Returning cached analysis (%.0fs old)",
                 now - _last_analysis_time)
        shared_state["claude_analysis"] = _last_analysis
        return _last_analysis

    log.info("🧠 ClaudeIntelligence: Running LLM analysis cycle...")

    data_summary = _build_data_summary(shared_state)

    # Load current accuracy stats into shared_state for prompt building
    try:
        import json as _json, os as _os
        acc_path = _os.path.join(_BASE, "data", "accuracy_stats.json")
        with open(acc_path) as f:
            shared_state["accuracy_stats"] = _json.load(f)
    except Exception:
        pass

    # Call Claude (primary)
    claude_result = _call_claude(data_summary, shared_state)

    # Call Gemini (parallel, free)
    gemini_result = _call_gemini(data_summary)

    if claude_result:
        final = _reconcile(claude_result, gemini_result)
        final["analyzed_at"] = datetime.now().strftime("%d %b %H:%M:%S")
        final["claude_model"] = CLAUDE_MODEL
        final["gemini_used"]  = gemini_result is not None

        _last_analysis      = final
        _last_analysis_time = now

        shared_state["claude_analysis"] = final
        _apply_adjustments(final, shared_state)

        log.info(
            "✅ ClaudeIntelligence: %s | Stance=%s | Picks=%d | Gemini=%s",
            final.get("market_condition", "?"),
            final.get("market_stance", "?"),
            len(final.get("conviction_picks", [])),
            "ALIGNED" if not final.get("gemini_disagrees") else "DISAGREES"
        )
        return final
    else:
        log.warning("⚠️  ClaudeIntelligence: LLM call failed — using fallback")
        fallback = _fallback_analysis()
        if gemini_result:
            fallback["gemini_bias"]      = gemini_result.get("market_bias")
            fallback["gemini_used"]      = True
            fallback["market_narrative"] += f" Gemini sees {gemini_result.get('market_bias','NEUTRAL')} market."
        shared_state["claude_analysis"] = fallback
        return fallback
