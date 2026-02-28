# ══════════════════════════════════════════════════════════════════════════════
# StockGuru Sovereign — The Risk Master
# Role: Governance & Veto Authority
#   • Hard VETO: Absolute blocks (VIX, daily loss, panic, loss streak)
#   • Soft VETO: Escalates borderline cases to HITL
#   • Self-tightening: Writes stricter thresholds to sovereign_config.json
# ══════════════════════════════════════════════════════════════════════════════
import json, logging, os
from datetime import datetime, date

log = logging.getLogger("sovereign.risk_master")

CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "sovereign_config.json")
)
DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))

# ─────────────────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"veto_thresholds": {}, "self_correction": {}}


def _save_config(config: dict):
    try:
        config["_last_modified"] = datetime.now().isoformat()
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log.error("Config save failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
def run(shared_state: dict, send_telegram_fn=None) -> dict:
    """
    Main entry point — called by Tier 5 after Quant.
    Reads: index_prices, paper_portfolio, quant_output, scryer_output, signal_history
    Writes: shared_state["risk_master_output"]
    """
    log.info("⚖️  Risk Master: Running governance checks...")
    config   = _load_config()
    veto_cfg = config.get("veto_thresholds", {})

    # ── 1. Check Hard VETO conditions ─────────────────────────────────────────
    hard_veto, hard_reason = _check_hard_veto(shared_state, veto_cfg)

    # ── 2. Get Quant candidates ────────────────────────────────────────────────
    quant_out = shared_state.get("quant_output", {})
    all_candidates = (
        quant_out.get("auto_candidates",  []) +
        quant_out.get("hitl_candidates",  []) +
        quant_out.get("debate_candidates",[])
    )

    # ── 3. Check Soft VETO per candidate ──────────────────────────────────────
    soft_veto_flags = []
    escalated       = []
    cleared_auto    = []
    cleared_debate  = []
    cleared_hitl    = []

    if not hard_veto:
        portfolio = shared_state.get("paper_portfolio", {})
        for stock in all_candidates:
            flags = _check_soft_veto(stock, shared_state, veto_cfg, portfolio)
            if flags:
                soft_veto_flags.append({"name": stock, "flags": flags})
                escalated.append(stock)   # Soft veto → HITL regardless of tier
            else:
                tier = quant_out.get("conviction_map", {}).get(stock, {}).get("tier", "SKIP")
                if tier == "AUTO_EXECUTE":
                    cleared_auto.append(stock)
                elif tier == "DEBATE_REQUIRED":
                    cleared_debate.append(stock)
                elif tier == "HITL_REQUIRED":
                    cleared_hitl.append(stock)
    else:
        # Hard veto active — send Telegram alert
        if send_telegram_fn:
            _send_hard_veto_alert(hard_reason, send_telegram_fn)

    # ── 4. Count consecutive losses ───────────────────────────────────────────
    consecutive_losses = _count_consecutive_losses(shared_state)

    # ── 5. Self-tightening thresholds ─────────────────────────────────────────
    adjustments = _maybe_tighten_thresholds(config, shared_state)

    # ── 6. Assemble output ────────────────────────────────────────────────────
    output = {
        "hard_veto_active":    hard_veto,
        "hard_veto_reason":    hard_reason,
        "soft_veto_flags":     soft_veto_flags,
        "escalated_to_hitl":   escalated,
        "cleared_auto":        cleared_auto,
        "cleared_for_debate":  cleared_debate,
        "cleared_hitl":        cleared_hitl,
        "consecutive_losses":  consecutive_losses,
        "vix_level":           _get_vix(shared_state),
        "daily_pnl_pct":       _get_daily_pnl(shared_state),
        "governance_log":      _build_governance_log(hard_veto, hard_reason, soft_veto_flags, consecutive_losses),
        "config_adjustments":  adjustments,
        "last_run":            datetime.now().strftime("%d %b %H:%M:%S")
    }

    shared_state["risk_master_output"] = output
    log.info("✅ Risk Master: hard_veto=%s | soft_flags=%d | consecutive_losses=%d",
             hard_veto, len(soft_veto_flags), consecutive_losses)
    return output


# ─────────────────────────────────────────────────────────────────────────────
def _check_hard_veto(shared_state: dict, veto_cfg: dict) -> tuple:
    """Returns (True, reason_str) or (False, None)."""
    vix            = _get_vix(shared_state)
    daily_pnl      = _get_daily_pnl(shared_state)
    market_read    = shared_state.get("scryer_output", {}).get("scryer_market_read", "")
    consec_losses  = _count_consecutive_losses(shared_state)

    hard_vix       = veto_cfg.get("hard_veto_vix",          25)
    loss_halt      = veto_cfg.get("daily_loss_halt_pct",     3.0)
    sl_circuit     = veto_cfg.get("consecutive_sl_circuit",  3)

    if vix > hard_vix:
        return True, f"VIX HALT: India VIX {vix:.1f} > {hard_vix} — no new entries"
    if daily_pnl <= -loss_halt:
        return True, f"DAILY LOSS CIRCUIT: Portfolio down {daily_pnl:.1f}% — halted for today"
    if market_read == "PANIC":
        return True, "PANIC SIGNAL: Scryer detected market-wide panic — no new longs"
    if consec_losses >= sl_circuit:
        return True, f"LOSS STREAK: {consec_losses} consecutive SL_HIT trades — circuit breaker active"

    return False, None


def _check_soft_veto(stock: str, shared_state: dict, veto_cfg: dict, portfolio: dict) -> list:
    """Returns list of soft-veto flag strings. Empty = no soft veto."""
    flags = []

    vix        = _get_vix(shared_state)
    soft_vix   = veto_cfg.get("soft_veto_vix",              20)
    soft_sect  = veto_cfg.get("sector_concentration_soft",  20)
    ext_shock  = veto_cfg.get("extreme_shock_delta",        8.0)
    min_wr     = veto_cfg.get("min_win_rate_warning",       0.45)

    # VIX caution zone
    if 20 <= vix <= 25:
        flags.append(f"VIX_CAUTION: VIX {vix:.1f} — reduce size 40%")

    # Sector concentration
    sig = _get_signal_for_stock(stock, shared_state)
    sector = sig.get("sector", "")
    if sector:
        sector_pct = _get_sector_exposure_pct(sector, portfolio)
        if soft_sect <= sector_pct < veto_cfg.get("sector_concentration_hard", 25):
            flags.append(f"NEAR_SECTOR_LIMIT: {sector} at {sector_pct:.0f}% (limit {veto_cfg.get('sector_concentration_hard', 25)}%)")

    # Extreme shock delta
    delta = shared_state.get("scryer_output", {}).get("shock_vs_reality", {}).get(stock, {}).get("delta", 0)
    if abs(delta) > ext_shock:
        flags.append(f"EXTREME_SHOCK: delta {delta:.1f} — extreme news event, confirm before entry")

    # Win rate warning
    accuracy = shared_state.get("accuracy_stats", {})
    overall_wr = accuracy.get("overall", {}).get("win_rate", 1.0)
    if isinstance(overall_wr, (int, float)) and overall_wr < min_wr:
        recent_trades = accuracy.get("overall", {}).get("total", 0)
        if recent_trades >= 10:
            flags.append(f"LOW_WIN_RATE: {overall_wr:.0%} win rate over last {recent_trades} trades")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
def _count_consecutive_losses(shared_state: dict) -> int:
    """Count consecutive SL_HIT trades from the end of signal_history."""
    try:
        sig_file = os.path.join(DATA_DIR, "signal_history.json")
        if not os.path.exists(sig_file):
            return 0
        with open(sig_file) as f:
            history = json.load(f)
        if not isinstance(history, list):
            return 0
        # Count from most recent settled trade backwards
        count = 0
        for trade in reversed(history):
            outcome = trade.get("outcome", "OPEN")
            if outcome == "OPEN":
                continue
            if outcome == "SL_HIT":
                count += 1
            else:
                break  # streak broken
        return count
    except Exception as e:
        log.debug("consecutive_losses check error: %s", e)
        return 0


def _get_vix(shared_state: dict) -> float:
    """Extract India VIX from multiple possible locations in shared_state."""
    # Try index_prices dict
    for k, v in shared_state.get("index_prices", {}).items():
        if "VIX" in k.upper():
            return float(v.get("price", 0)) if isinstance(v, dict) else float(v or 0)
    # Try direct key
    vix = shared_state.get("india_vix", 0) or shared_state.get("INDIA VIX", 0)
    return float(vix or 0)


def _get_daily_pnl(shared_state: dict) -> float:
    """Get today's portfolio P&L % from paper_portfolio."""
    port = shared_state.get("paper_portfolio", {})
    stats = port.get("stats", {}) if isinstance(port, dict) else {}
    return float(stats.get("daily_pnl_pct", 0) or port.get("daily_pnl_pct", 0) or 0)


def _get_sector_exposure_pct(sector: str, portfolio: dict) -> float:
    """Calculate current % of capital allocated to a sector."""
    if not portfolio:
        return 0.0
    capital = float(portfolio.get("capital", 100000) or 100000)
    positions = portfolio.get("positions", {})
    sector_val = sum(
        float(p.get("position_value", 0) or 0)
        for p in positions.values()
        if p.get("sector") == sector and p.get("status") == "OPEN"
    )
    return (sector_val / capital * 100) if capital > 0 else 0.0


def _get_signal_for_stock(stock: str, shared_state: dict) -> dict:
    """Find trade signal for a stock."""
    for sig in (shared_state.get("risk_reviewed_signals", []) +
                shared_state.get("actionable_signals", []) +
                shared_state.get("trade_signals", [])):
        if sig.get("name") == stock:
            return sig
    return {}


# ─────────────────────────────────────────────────────────────────────────────
def _maybe_tighten_thresholds(config: dict, shared_state: dict) -> list:
    """
    Self-correction: if same veto condition triggers 3+ times in a row,
    tighten the threshold in sovereign_config.json.
    Returns list of adjustments made.
    """
    adjustments = []
    sc = config.get("self_correction", {})
    n_triggers = sc.get("veto_tighten_after_n_triggers", 3)
    veto_cfg   = config.get("veto_thresholds", {})

    # Load recent governance log from shared_state (previous cycles)
    gov_logs = []
    for past in shared_state.get("_risk_master_history", []):
        gov_logs.extend(past.get("soft_veto_flags", []))

    # Check VIX soft veto frequency
    vix_triggers = sum(
        1 for item in gov_logs[-9:]
        if any("VIX_CAUTION" in str(f) for f in item.get("flags", []))
    )
    if vix_triggers >= n_triggers:
        old_val = veto_cfg.get("soft_veto_vix", 20)
        new_val = max(16, old_val - 1)
        if new_val != old_val:
            config["veto_thresholds"]["soft_veto_vix"] = new_val
            _save_config(config)
            adjustments.append({
                "parameter": "soft_veto_vix", "old": old_val, "new": new_val,
                "reason": f"VIX soft veto triggered {vix_triggers}x — tightened"
            })
            log.info("⚙️  Risk Master self-tightened: soft_veto_vix %s → %s", old_val, new_val)

    # Keep rolling history
    if "_risk_master_history" not in shared_state:
        shared_state["_risk_master_history"] = []
    shared_state["_risk_master_history"].append({
        "soft_veto_flags": shared_state.get("risk_master_output", {}).get("soft_veto_flags", []),
        "ts": datetime.now().isoformat()
    })
    shared_state["_risk_master_history"] = shared_state["_risk_master_history"][-20:]

    return adjustments


def _build_governance_log(hard_veto: bool, reason: str, soft_flags: list, losses: int) -> list:
    entry = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "hard_veto": hard_veto,
        "reason": reason,
        "soft_count": len(soft_flags),
        "consecutive_losses": losses
    }
    return [entry]


def _send_hard_veto_alert(reason: str, send_telegram_fn):
    """Send a Hard VETO Telegram alert."""
    msg = (
        "🛑 *SOVEREIGN HARD VETO ACTIVATED*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Reason: {reason}\n\n"
        "All new entries blocked.\n"
        "_Paper simulation only — no real orders._"
    )
    try:
        send_telegram_fn(msg)
        log.info("Hard veto alert sent via Telegram")
    except Exception as e:
        log.error("Telegram hard veto alert failed: %s", e)
