# ══════════════════════════════════════════════════════════════════════════════
# StockGuru Sovereign — Post-Mortem Agent
# Role: Learning & Self-Correction
#   • Analyzes every SL_HIT (failed) trade
#   • Writes LLM-generated "reflexions" to SQLite (agent_memory.db)
#   • Auto-adjusts learned_weights.json and sovereign_config.json
#   • No code changes needed — all corrections via JSON files
#   • LLM call: once per 24 hours max (configurable)
# ══════════════════════════════════════════════════════════════════════════════
import json, logging, os
from datetime import datetime, timedelta

log = logging.getLogger("sovereign.post_mortem")

CONFIG_PATH  = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "sovereign_config.json"))
PM_LOG_PATH  = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "post_mortem_log.json"))
SIG_HIST     = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "signal_history.json"))
WEIGHTS_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "learned_weights.json"))

_last_llm_call_ts = [None]  # module-level timestamp guard


# ─────────────────────────────────────────────────────────────────────────────
def run(shared_state: dict) -> dict:
    """
    Main entry. Runs every 15-min cycle; LLM max once per 24h.
    Reads: data/signal_history.json, data/learned_weights.json
    Writes: agent_memory.db, learned_weights.json, sovereign_config.json
    """
    log.info("🪦  Post-Mortem: Scanning for new failures...")
    config = _load_config()
    pm_hours = config.get("post_mortem_llm_hours", 24)

    # Load signal history
    history  = _load_signal_history()
    pm_log   = _load_pm_log()

    # Find new SL_HIT trades since last Post-Mortem run
    last_run_ts = _get_last_run_ts(pm_log)
    new_failures = _get_new_failures(history, last_run_ts)

    if not new_failures:
        log.info("✅ Post-Mortem: No new failures to analyze")
        output = {
            "analyzed_this_cycle": 0,
            "total_analyzed": len([r for r in pm_log if r.get("outcome") == "FAILURE"]),
            "adjustments_made": [],
            "llm_diagnosis": None,
            "last_run": datetime.now().strftime("%d %b %H:%M:%S")
        }
        shared_state["post_mortem_output"] = output
        return output

    log.info("🪦  Post-Mortem: %d new failures to analyze", len(new_failures))

    adjustments_made = []

    # ── 1. Rule-based adjustments (no LLM needed) ─────────────────────────────
    for trade in new_failures:
        adj = _apply_rule_based_corrections(trade, history, config)
        adjustments_made.extend(adj)

    # ── 2. LLM reflexion (max once per 24h) ───────────────────────────────────
    llm_diagnosis = None
    can_use_llm = _can_use_llm(pm_hours)

    if can_use_llm and new_failures:
        llm_batch = new_failures[-5:]  # last 5 failures
        llm_diagnosis, llm_adj = _run_llm_reflexion(llm_batch, config, shared_state)
        if llm_adj:
            adjustments_made.extend(llm_adj)
        _last_llm_call_ts[0] = datetime.now()

    # ── 3. Write lessons to SQLite ────────────────────────────────────────────
    from src.agents.sovereign import memory_engine
    for trade in new_failures:
        meta = {
            "sector":         trade.get("sector", ""),
            "gates_passed":   trade.get("gates_passed", 0),
            "rsi":            trade.get("rsi", None),
            "score":          trade.get("score", 0),
            "confidence":     trade.get("confidence", ""),
            "sentiment_score": None,  # populated if available
            "shock_delta":    None,
            "vix":            None
        }
        # Try to enrich with Scryer data
        scryer_out = shared_state.get("scryer_output", {})
        stock = trade.get("name", "")
        delta_data = scryer_out.get("shock_vs_reality", {}).get(stock, {})
        if delta_data:
            meta["shock_delta"] = delta_data.get("delta")

        root_cause = _classify_root_cause(trade, shared_state)
        reflexion  = _build_simple_reflexion(trade, root_cause)

        memory_engine.store_lesson(
            trade_id   = trade.get("id", f"{stock}_{datetime.now().strftime('%Y%m%d')}"),
            ticker     = stock,
            sector     = trade.get("sector", ""),
            outcome    = "FAILURE",
            metadata   = meta,
            reflexion  = reflexion,
            root_cause = root_cause
        )

    # ── 4. Log Post-Mortem records ────────────────────────────────────────────
    pm_records = []
    for trade in new_failures:
        pm_records.append({
            "trade_id":    trade.get("id", ""),
            "ticker":      trade.get("name", ""),
            "sector":      trade.get("sector", ""),
            "outcome":     "FAILURE",
            "root_cause":  _classify_root_cause(trade, shared_state),
            "adjustments": [a for a in adjustments_made if a.get("ticker") == trade.get("name", "")],
            "reflexion":   _build_simple_reflexion(trade, _classify_root_cause(trade, shared_state)),
            "analyzed_at": datetime.now().isoformat()
        })
    _append_pm_log(pm_records)

    output = {
        "analyzed_this_cycle":  len(new_failures),
        "total_analyzed":       len(pm_log) + len(new_failures),
        "new_failures":         [t.get("name") for t in new_failures],
        "adjustments_made":     adjustments_made,
        "llm_diagnosis":        llm_diagnosis,
        "last_run":             datetime.now().strftime("%d %b %H:%M:%S")
    }
    shared_state["post_mortem_output"] = output
    log.info("✅ Post-Mortem: %d analyzed | %d adjustments | LLM=%s",
             len(new_failures), len(adjustments_made), bool(llm_diagnosis))
    return output


# ─────────────────────────────────────────────────────────────────────────────
# RULE-BASED CORRECTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _apply_rule_based_corrections(trade: dict, all_history: list, config: dict) -> list:
    """
    Apply deterministic weight/config adjustments based on failure patterns.
    Returns list of adjustment records.
    """
    adjustments = []
    sc  = config.get("self_correction", {})
    stock  = trade.get("name", "")
    sector = trade.get("sector", "")

    # ── Sector dampening: 3+ failures in last 20 trades ──────────────────────
    n_thresh = sc.get("weight_dampen_sector_threshold", 3)
    recent_sector_failures = sum(
        1 for t in all_history[-20:]
        if t.get("sector") == sector and t.get("outcome") == "SL_HIT"
    )
    if recent_sector_failures >= n_thresh:
        adj = _dampen_sector_weight(sector, 0.05)
        if adj:
            adj["trigger"] = f"{recent_sector_failures} SL_HIT in {sector} last 20 trades"
            adj["ticker"]  = stock
            adjustments.append(adj)

    # ── Stock dampening: 2 consecutive SL_HIT for same stock ─────────────────
    consec = sc.get("weight_dampen_stock_consecutive", 2)
    stock_recent = [t for t in all_history if t.get("name") == stock][-consec:]
    if len(stock_recent) >= consec and all(t.get("outcome") == "SL_HIT" for t in stock_recent):
        adj = _dampen_stock_weight(stock, 0.10)
        if adj:
            adj["trigger"] = f"{consec} consecutive SL_HIT for {stock}"
            adj["ticker"]  = stock
            adjustments.append(adj)

    # ── RSI gate tightening: borderline RSI (65-68) in failures ──────────────
    rsi = trade.get("rsi") or 0
    rsi_n = sc.get("rsi_tighten_after_n_failures", 2)
    rsi_borderline_count = sum(
        1 for t in all_history[-10:]
        if t.get("outcome") == "SL_HIT" and 65 <= (t.get("rsi") or 0) <= 68
    )
    if rsi_borderline_count >= rsi_n:
        adj = _tighten_config_param("gate_overrides.rsi_upper_bound", 1, min_val=60, config=config)
        if adj:
            adj["trigger"] = f"RSI 65-68 borderline in {rsi_borderline_count} failures"
            adj["ticker"]  = stock
            adjustments.append(adj)

    # ── Volume gate tightening: barely-passing volume in failures ─────────────
    vol_n = sc.get("volume_tighten_after_n_failures", 2)
    vol_borderline = sum(
        1 for t in all_history[-10:]
        if t.get("outcome") == "SL_HIT"
        # We can't easily check vol_surge in signal_history, use score proxy
        and t.get("score", 100) < 82
    )
    if vol_borderline >= vol_n:
        max_vol = sc.get("max_volume_gate_min", 2.0)
        adj = _tighten_config_param("gate_overrides.volume_gate_min", 0.1, max_val=max_vol, config=config)
        if adj:
            adj["trigger"] = f"Low-score failures: {vol_borderline} in last 10 trades"
            adj["ticker"]  = stock
            adjustments.append(adj)

    return adjustments


def _dampen_sector_weight(sector: str, step: float) -> dict | None:
    """Lower sector weight in learned_weights.json."""
    try:
        with open(WEIGHTS_PATH) as f:
            weights = json.load(f)
        sect_w = weights.get("sector_weights", {})
        old = sect_w.get(sector, 1.0)
        new = round(max(0.70, old - step), 3)
        if new == old:
            return None
        sect_w[sector] = new
        weights["sector_weights"] = sect_w
        weights["last_updated"] = datetime.now().isoformat()
        with open(WEIGHTS_PATH, "w") as f:
            json.dump(weights, f, indent=2)

        from src.agents.sovereign import memory_engine
        memory_engine.log_config_change("post_mortem", f"sector_weights.{sector}", old, new,
                                         f"Sector failure dampening")
        log.info("⚙️  Post-Mortem: sector_weights.%s %s → %s", sector, old, new)
        return {"file": "learned_weights.json", "key": f"sector_weights.{sector}", "old": old, "new": new}
    except Exception as e:
        log.error("Sector weight dampen error: %s", e)
        return None


def _dampen_stock_weight(stock: str, step: float) -> dict | None:
    """Lower individual stock weight in learned_weights.json."""
    try:
        with open(WEIGHTS_PATH) as f:
            weights = json.load(f)
        stock_w = weights.get("stock_weights", {})
        old = stock_w.get(stock, 1.0)
        new = round(max(0.70, old - step), 3)
        if new == old:
            return None
        stock_w[stock] = new
        weights["stock_weights"] = stock_w
        weights["last_updated"] = datetime.now().isoformat()
        with open(WEIGHTS_PATH, "w") as f:
            json.dump(weights, f, indent=2)
        log.info("⚙️  Post-Mortem: stock_weights.%s %s → %s", stock, old, new)
        return {"file": "learned_weights.json", "key": f"stock_weights.{stock}", "old": old, "new": new}
    except Exception as e:
        log.error("Stock weight dampen error: %s", e)
        return None


def _tighten_config_param(dot_key: str, step: float,
                           min_val: float = None, max_val: float = None,
                           config: dict = None) -> dict | None:
    """
    Tighten a sovereign_config.json parameter by key path (e.g., "gate_overrides.rsi_upper_bound").
    step > 0 means subtract (tighten upper bound) or add (raise minimum).
    """
    try:
        if config is None:
            with open(CONFIG_PATH) as f:
                config = json.load(f)

        keys = dot_key.split(".")
        section = config
        for k in keys[:-1]:
            section = section.setdefault(k, {})

        param = keys[-1]
        old = section.get(param, 0)

        # Determine direction: for upper bounds (rsi_upper_bound), subtract
        # For lower bounds (volume_gate_min), add
        if "upper" in param or "max" in param:
            new = round(old - step, 3)
            if min_val is not None:
                new = max(min_val, new)
        else:
            new = round(old + step, 3)
            if max_val is not None:
                new = min(max_val, new)

        if new == old:
            return None

        section[param] = new
        _save_config(config)

        from src.agents.sovereign import memory_engine
        memory_engine.log_config_change("post_mortem", dot_key, old, new, "Rule-based tightening")
        log.info("⚙️  Post-Mortem: %s %s → %s", dot_key, old, new)
        return {"file": "sovereign_config.json", "key": dot_key, "old": old, "new": new}
    except Exception as e:
        log.error("Config tighten error [%s]: %s", dot_key, e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# LLM REFLEXION
# ─────────────────────────────────────────────────────────────────────────────

def _run_llm_reflexion(failures: list, config: dict, shared_state: dict) -> tuple:
    """
    One Claude Haiku call for batch of failures.
    Returns (global_lesson: str, adjustments: list).
    """
    try:
        import anthropic, os as _os
        key = _os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return None, []

        # Build compact failure summary
        failure_lines = []
        for t in failures:
            gates = t.get("gates_passed", "?")
            failure_lines.append(
                f"- {t.get('name', '?')} ({t.get('sector', '?')}) | "
                f"Score:{t.get('score', '?')} | Gates:{gates}/8 | "
                f"SL hit {t.get('pnl_pct', '?')}%"
            )

        prompt = (
            "You are a Post-Mortem analyst for a quant trading system targeting 25-30% monthly return on Indian equities.\n"
            "Analyze these recent Stop-Loss hit trades:\n\n"
            + "\n".join(failure_lines) + "\n\n"
            "For the batch, identify:\n"
            "1. The most common root cause pattern (TIMING/SECTOR/MACRO/OVEREXTENDED/FAKE_OUT)\n"
            "2. Which specific signal was most misleading\n"
            "3. One sovereign_config.json parameter to tighten (format: section.key direction value, e.g., gate_overrides.rsi_upper_bound decrease 2)\n"
            "4. A 2-sentence global lesson for the system\n\n"
            "Return ONLY valid JSON:\n"
            '{"root_cause_pattern": "TIMING", "misleading_signal": "RSI gate borderline at 66", '
            '"config_recommendation": {"key": "gate_overrides.rsi_upper_bound", "direction": "decrease", "amount": 2}, '
            '"global_lesson": "..."}'
        )

        client = anthropic.Anthropic(api_key=key)
        resp   = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        if "{" in text:
            text = text[text.index("{"):text.rindex("}")+1]
        result = json.loads(text)

        global_lesson = result.get("global_lesson", "")
        adjustments   = []

        # Apply the LLM's config recommendation
        rec = result.get("config_recommendation", {})
        if rec.get("key") and rec.get("amount"):
            step      = float(rec.get("amount", 1))
            direction = rec.get("direction", "")
            if direction == "increase":
                step = step  # add
            else:
                step = step  # will be subtracted by _tighten_config_param logic

            adj = _tighten_config_param(rec["key"], step, config=config)
            if adj:
                adj["source"] = "LLM_RECOMMENDATION"
                adj["llm_reasoning"] = result.get("misleading_signal", "")
                adjustments.append(adj)

        # Update shared_state learning_note
        shared_state["post_mortem_llm_note"] = global_lesson

        log.info("🤖 Post-Mortem LLM: %s", global_lesson[:80])
        return global_lesson, adjustments

    except Exception as e:
        log.error("Post-Mortem LLM call failed: %s", e)
        return None, []


# ─────────────────────────────────────────────────────────────────────────────
# ROOT CAUSE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def _classify_root_cause(trade: dict, shared_state: dict) -> str:
    """Heuristic root cause classification."""
    rsi    = trade.get("rsi", 50) or 50
    score  = trade.get("score", 80) or 80
    pnl    = trade.get("pnl_pct", 0) or 0
    chasing = trade.get("chasing", False)

    # VIX check
    vix = 0.0
    for k, v in shared_state.get("index_prices", {}).items():
        if "VIX" in k.upper():
            vix = float(v.get("price", 0)) if isinstance(v, dict) else float(v or 0)
    if vix > 20 and pnl < -5:
        return "MACRO"

    if chasing or rsi > 65:
        return "TIMING"

    if score >= 90 and pnl < -3:
        return "FAKE_OUT"  # High score but still failed = fake breakout

    sector = trade.get("sector", "")
    if sector:
        sector_failures = sum(
            1 for t in _load_signal_history()[-20:]
            if t.get("sector") == sector and t.get("outcome") == "SL_HIT"
        )
        if sector_failures >= 3:
            return "SECTOR"

    if pnl < -8:
        return "OVEREXTENDED"

    return "TIMING"  # default


def _build_simple_reflexion(trade: dict, root_cause: str) -> str:
    """Build a plain-English reflexion without LLM."""
    stock  = trade.get("name", "?")
    sector = trade.get("sector", "?")
    score  = trade.get("score", "?")
    pnl    = trade.get("pnl_pct", 0) or 0
    rsi    = trade.get("rsi", "?")

    templates = {
        "TIMING":       f"{stock} ({sector}) failed — entered when RSI={rsi}, possibly late momentum. Score {score}. Loss: {pnl:.1f}%. Avoid entries with RSI>65.",
        "SECTOR":       f"{stock} in {sector} — sector-wide reversal likely caused this {pnl:.1f}% loss. Reduce sector exposure when 3+ failures cluster.",
        "MACRO":        f"{stock} failed {pnl:.1f}% — high VIX environment at entry. Macro headwind overrode technical setup.",
        "OVEREXTENDED": f"{stock} already extended at entry — fell {pnl:.1f}%. Score {score} was inflated; underlying momentum was weakening.",
        "FAKE_OUT":     f"{stock} high-conviction (score={score}) but SL hit {pnl:.1f}%. Classic fake breakout — volume was not sustained.",
    }
    return templates.get(root_cause, f"{stock} SL hit {pnl:.1f}% — root cause: {root_cause}")


# ─────────────────────────────────────────────────────────────────────────────
# FILE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(config: dict):
    try:
        config["_last_modified"] = datetime.now().isoformat()
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log.error("Config save failed: %s", e)


def _load_signal_history() -> list:
    try:
        with open(SIG_HIST) as f:
            return json.load(f)
    except Exception:
        return []


def _load_pm_log() -> list:
    try:
        with open(PM_LOG_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def _append_pm_log(records: list):
    log_data = _load_pm_log()
    log_data.extend(records)
    log_data = log_data[-500:]  # rolling 500
    try:
        with open(PM_LOG_PATH, "w") as f:
            json.dump(log_data, f, indent=2, default=str)
    except Exception as e:
        log.error("PM log save failed: %s", e)


def _get_last_run_ts(pm_log: list) -> str | None:
    if not pm_log:
        return None
    last = max((r.get("analyzed_at", "") for r in pm_log if r.get("analyzed_at")), default=None)
    return last


def _get_new_failures(history: list, since_ts: str | None) -> list:
    """Return SL_HIT trades that haven't been post-mortemed yet (since since_ts)."""
    if not since_ts:
        return [r for r in history if r.get("outcome") in ("SL_HIT", "LOSS")]
    return [r for r in history
            if r.get("outcome") in ("SL_HIT", "LOSS")
            and r.get("analyzed_at", "") < since_ts]
