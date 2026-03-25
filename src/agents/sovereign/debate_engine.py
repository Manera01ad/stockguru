# ══════════════════════════════════════════════════════════════════════════════
# StockGuru Sovereign — Debate Engine
# 3-Round structured debate for DEBATE_REQUIRED candidates (conviction 55-69)
#   Round 1: Bull Advocate (Claude Haiku) — strongest case FOR entry
#   Round 2: Bear Advocate (Gemini Flash) — directly REBUTS Round 1
#   Round 3: Resolution Judge (Claude Haiku) — final verdict
# Cost: ~$0.001 per debate | Max 2 debates/cycle → ~$0.60/month additional
# ══════════════════════════════════════════════════════════════════════════════
import json, logging, os, time
from datetime import datetime

log = logging.getLogger("sovereign.debate")

CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "sovereign_config.json")
)
DEBATE_LOG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "debate_log.json")
)
PM_LOG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "post_mortem_log.json")
)

MAX_DEBATE_LOG = 200


# ─────────────────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"debate_max_per_cycle": 2}


def _load_pm_failures(sector: str) -> list:
    """Load recent post-mortem failures for this sector to brief the Bear."""
    try:
        with open(PM_LOG_PATH) as f:
            records = json.load(f)
        return [r for r in records if r.get("sector") == sector][-5:]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
def run_debate(stock_name: str, shared_state: dict) -> dict:
    """
    Main entry point. Runs full 3-round debate for one stock.
    Returns debate result dict. Always returns (never raises).
    """
    start = time.time()
    log.info("🎭 Debate: Starting for %s", stock_name)

    # Find the signal
    signal = _get_signal(stock_name, shared_state)
    if not signal:
        return {"stock": stock_name, "final_verdict": "DEBATE_SKIP",
                "reason": "No signal found", "send_to_hitl": False}

    sector = signal.get("sector", "")
    gates  = _get_gates(stock_name, shared_state)
    conviction = shared_state.get("quant_output", {}).get("conviction_map", {}).get(stock_name, {}).get("composite", 62)

    # ── Round 1: Bull Advocate ────────────────────────────────────────────────
    bull_ctx = _build_bull_context(stock_name, signal, gates, shared_state)
    bull     = _call_bull_advocate(bull_ctx, shared_state)
    log.info("  Bull [%s]: strength=%s", stock_name, bull.get("strength"))

    # ── Round 2: Bear Advocate ────────────────────────────────────────────────
    bear_ctx = _build_bear_context(stock_name, signal, gates, sector, bull, shared_state)
    bear     = _call_bear_advocate(bear_ctx, shared_state)
    log.info("  Bear [%s]: strength=%s", stock_name, bear.get("strength"))

    # ── Round 3: Resolution ───────────────────────────────────────────────────
    resolution = _call_resolution_judge(bull, bear, signal, gates, conviction)
    verdict    = resolution.get("final_verdict", "DEBATE_SKIP")
    log.info("  Resolution [%s]: %s — %s", stock_name, verdict, resolution.get("deciding_factor", ""))

    elapsed = round(time.time() - start, 2)

    # Build full record
    record = {
        "debate_id":        f"{stock_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}",
        "stock":            stock_name,
        "sector":           sector,
        "conviction_in":    conviction,
        "conviction_out":   conviction + resolution.get("confidence_adjustment", 0),
        "bull_verdict":     bull,
        "bear_verdict":     bear,
        "resolution":       resolution,
        "final_verdict":    verdict,
        "send_to_hitl":     verdict == "DEBATE_HITL",
        "auto_execute":     verdict == "DEBATE_BUY",
        "debate_summary":   resolution.get("debate_summary", ""),
        "deciding_factor":  resolution.get("deciding_factor", ""),
        "modified_entry":   resolution.get("modified_entry"),
        "elapsed_seconds":  elapsed,
        "timestamp":        datetime.now().isoformat()
    }

    _save_debate_log(record)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_bull_context(stock: str, signal: dict, gates: dict, shared_state: dict) -> str:
    sector   = signal.get("sector", "")
    cmp      = signal.get("cmp", 0)
    score    = signal.get("score", 0)
    rsi      = signal.get("rsi", "N/A")
    rationale= signal.get("rationale", [])
    sector_view = signal.get("sector_view", "")

    # Scryer delta
    delta_data = shared_state.get("scryer_output", {}).get("shock_vs_reality", {}).get(stock, {})
    delta = delta_data.get("delta", 0)
    delta_type = delta_data.get("type", "ALIGNED")

    # Pattern library
    patterns = []
    for p in shared_state.get("pattern_library", [])[:3]:
        if sector.lower() in p.get("pattern_key", "").lower():
            patterns.append(f"  {p.get('description', '')} → {p.get('win_rate', 0):.0%} win rate ({p.get('count', 0)} trades)")

    # FII
    fii = shared_state.get("institutional_flow", {})
    fii_signal = fii.get("fii_signal", "NEUTRAL")
    fii_net = fii.get("fii_net_crore", 0)

    gate_summary = ", ".join([k for k, v in gates.items() if v]) or "none"
    gate_fail = ", ".join([k for k, v in gates.items() if not v]) or "none"

    lines = [
        f"=== BULL CONTEXT: {stock} ({sector}) ===",
        f"CMP: ₹{cmp} | Score: {score}/100 | RSI: {rsi}",
        f"Gates PASSED: {gate_summary}",
        f"Gates FAILED: {gate_fail}",
        f"Quant Overreaction: delta={delta:.2f} ({delta_type})",
        f"FII: {fii_signal} (net ₹{fii_net:+.0f}Cr)",
        f"Sector view: {sector_view}",
        "Rationale from scanner:",
    ] + [f"  • {r}" for r in rationale[:3]]

    if patterns:
        lines += ["Proven patterns matching this setup:"] + patterns

    lines += [
        "HIGH-CONFIDENCE NEWS (credibility≥80%):",
    ]
    for n in shared_state.get("scryer_output", {}).get("high_confidence_news", [])[:3]:
        stocks_aff = n.get("stocks_affected", [])
        if stock in stocks_aff or any(stock.lower() in h.lower() for h in [n.get("headline", "")]):
            lines.append(f"  [{n.get('credibility_score', 0):.0%}] {n.get('headline', '')}")

    return "\n".join(lines)


def _build_bear_context(stock: str, signal: dict, gates: dict, sector: str,
                         bull_round: dict, shared_state: dict) -> str:
    vix = 0.0
    for k, v in shared_state.get("index_prices", {}).items():
        if "VIX" in k.upper():
            vix = float(v.get("price", 0)) if isinstance(v, dict) else float(v or 0)

    pm_failures = _load_pm_failures(sector)
    failure_notes = []
    for f in pm_failures[-3:]:
        failure_notes.append(f"  [{f.get('ticker', '?')}] {f.get('root_cause', '?')}: {(f.get('reflexion', '') or '')[:80]}")

    # Portfolio concentration
    portfolio = shared_state.get("paper_portfolio", {})
    positions = portfolio.get("positions", {}) if isinstance(portfolio, dict) else {}
    sector_count = sum(1 for p in positions.values() if p.get("sector") == sector and p.get("status") == "OPEN")

    # Recent signal quality
    delta_data = shared_state.get("scryer_output", {}).get("shock_vs_reality", {}).get(stock, {})
    price_chg = delta_data.get("price_chg_pct", 0)
    already_moved = abs(price_chg) > 1.5

    lines = [
        f"=== BEAR CONTEXT: {stock} — REBUTTAL BRIEF ===",
        f"VIX: {vix:.1f} | Sector existing positions: {sector_count}",
        f"Stock already moved: {price_chg:+.1f}% today {'⚠️ CHASING RISK' if already_moved else ''}",
        "",
        "THE BULL ARGUED:",
        f"  Verdict: {bull_round.get('verdict', '?')} | Strength: {bull_round.get('strength', '?')}",
    ]
    if bull_round.get("top_3_reasons"):
        for r in bull_round["top_3_reasons"][:3]:
            lines.append(f"  • {r}")
    lines += [
        "",
        "POST-MORTEM FAILURES IN THIS SECTOR:",
    ]
    lines += failure_notes if failure_notes else ["  No prior failures recorded"]
    lines += [
        "",
        "GATES THAT FAILED (risk signals):",
    ]
    fail_gates = [k for k, v in gates.items() if not v]
    lines += [f"  ✗ {g}" for g in fail_gates] if fail_gates else ["  All gates passed"]
    lines.append("")
    lines.append("Your job: Directly rebut each Bull point with hard data. What would make this trade FAIL?")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# LLM CALLS
# ─────────────────────────────────────────────────────────────────────────────

def _call_bull_advocate(context: str, shared_state: dict) -> dict:
    """Round 1: Bull via Claude Haiku."""
    prompt = (
        "You are the BULL ADVOCATE for a quant trading system. "
        "Make the strongest possible case for entering this trade today. "
        "Cite specific data points from the context. Be direct and quantitative.\n\n"
        f"{context}\n\n"
        "Return ONLY valid JSON:\n"
        '{"verdict": "BUY", "strength": <0-100>, "top_3_reasons": ["...", "...", "..."], '
        '"required_conditions": ["..."], "concede_if": "..."}'
    )
    return _call_claude(prompt, shared_state, max_tokens=400,
                        fallback={"verdict": "BUY", "strength": 65,
                                   "top_3_reasons": ["Score qualifies", "Gates mostly passed", "Sector aligned"],
                                   "required_conditions": ["VIX stays below 20"],
                                   "concede_if": "FII turns seller"})


def _call_bear_advocate(context: str, shared_state: dict) -> dict:
    """Round 2: Bear via Gemini Flash (free tier)."""
    prompt = (
        "You are the BEAR ADVOCATE for a quant trading system. "
        "Directly rebut each Bull argument with hard data. "
        "Identify the SINGLE fatal flaw in this trade setup.\n\n"
        f"{context}\n\n"
        "Return ONLY valid JSON:\n"
        '{"verdict": "NO_TRADE", "strength": <0-100>, "rebuttals": ["...", "..."], '
        '"fatal_flaw": "...", "would_change_if": "..."}'
    )
    return _call_gemini(prompt, shared_state,
                        fallback={"verdict": "NO_TRADE", "strength": 55,
                                   "rebuttals": ["Entry timing borderline", "Sector near concentration limit"],
                                   "fatal_flaw": "Risk/reward marginal at current price",
                                   "would_change_if": "Price pulls back to support"})


def _call_resolution_judge(bull: dict, bear: dict, signal: dict,
                            gates: dict, conviction: float) -> dict:
    """Round 3: Resolution via Claude Haiku."""
    gates_passed = sum(1 for v in gates.values() if v)
    prompt = (
        "You are the RESOLUTION JUDGE for a quant trading system. "
        "Consider the Bull vs Bear debate and render an objective verdict.\n\n"
        f"Gates passed: {gates_passed}/8 | Composite conviction: {conviction:.0f}/100\n\n"
        f"BULL said (strength {bull.get('strength', 0)}/100):\n"
        f"  Top reasons: {bull.get('top_3_reasons', [])}\n"
        f"  Concedes if: {bull.get('concede_if', '')}\n\n"
        f"BEAR said (strength {bear.get('strength', 0)}/100):\n"
        f"  Fatal flaw: {bear.get('fatal_flaw', '')}\n"
        f"  Rebuttals: {bear.get('rebuttals', [])}\n\n"
        "Verdict options:\n"
        "  DEBATE_BUY: Bull wins clearly, elevate to auto-execute\n"
        "  DEBATE_HITL: Borderline, send to human approval\n"
        "  DEBATE_SKIP: Bear wins, discard this cycle\n\n"
        "Return ONLY valid JSON:\n"
        '{"final_verdict": "DEBATE_BUY|DEBATE_HITL|DEBATE_SKIP", '
        '"deciding_factor": "...", "confidence_adjustment": <-20 to +20>, '
        '"modified_entry": null_or_"price level to wait for", '
        '"debate_summary": "<50 words>"}'
    )
    return _call_claude(prompt, shared_state=None, max_tokens=300,
                        fallback={"final_verdict": "DEBATE_HITL",
                                   "deciding_factor": "Borderline — human review recommended",
                                   "confidence_adjustment": 0,
                                   "modified_entry": None,
                                   "debate_summary": "Debate inconclusive — sent to HITL."})


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPERS (reuse patterns from claude_intelligence.py)
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude(prompt: str, shared_state, max_tokens: int = 400, fallback: dict = None) -> dict:
    """Call Claude Haiku. Returns parsed JSON or fallback."""
    try:
        import anthropic, os
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return fallback or {}
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        # Extract JSON
        if "{" in text:
            text = text[text.index("{"):text.rindex("}")+1]
        return json.loads(text)
    except Exception as e:
        log.warning("Claude debate call failed: %s", e)
        return fallback or {}


def _call_gemini(prompt: str, shared_state, fallback: dict = None) -> dict:
    """Call Gemini Flash (free tier) for Bear Advocate."""
    try:
        import google.generativeai as genai, os
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return fallback or {}
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        if "{" in text:
            text = text[text.index("{"):text.rindex("}")+1]
        return json.loads(text)
    except Exception as e:
        log.warning("Gemini Bear advocate failed: %s", e)
        return fallback or {}


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _get_signal(stock: str, shared_state: dict) -> dict:
    for sig in (shared_state.get("risk_reviewed_signals", []) +
                shared_state.get("actionable_signals", []) +
                shared_state.get("trade_signals", [])):
        if sig.get("name") == stock:
            return sig
    return {}


def _get_gates(stock: str, shared_state: dict) -> dict:
    """Get gate_detail from Claude conviction picks."""
    for pick in shared_state.get("claude_analysis", {}).get("conviction_picks", []):
        if pick.get("name") == stock:
            return pick.get("gate_detail", {})
    return {}


def _save_debate_log(record: dict):
    """Append to debate_log.json, rolling 200 entries."""
    try:
        log_data = []
        if os.path.exists(DEBATE_LOG_PATH):
            with open(DEBATE_LOG_PATH) as f:
                log_data = json.load(f)
        if not isinstance(log_data, list):
            log_data = []
        log_data.append(record)
        # Rolling window
        if len(log_data) > MAX_DEBATE_LOG:
            log_data = log_data[-MAX_DEBATE_LOG:]
        with open(DEBATE_LOG_PATH, "w") as f:
            json.dump(log_data, f, indent=2, default=str)
    except Exception as e:
        log.error("Debate log save failed: %s", e)
