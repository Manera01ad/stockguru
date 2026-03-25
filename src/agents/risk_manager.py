"""
AGENT 11 — RISK MANAGER
━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Enforce professional risk management on all trade signals.
          Computes actual position sizes, checks portfolio concentration,
          applies VIX-based scaling, flags dangerous signals.
          The final gatekeeper before paper_trader executes.

Rules enforced:
  R9  — 2% capital risk per trade
  R10 — Minimum 2.5:1 R:R ratio
  R12 — Max 25% sector concentration
  R13 — Max 5 simultaneous positions
  R14 — VIX > 20: reduce 40% | VIX > 25: no new longs
  R15 — Daily 3% drawdown: halt new entries
"""

import os
import json
import logging
from datetime import datetime, date

log = logging.getLogger("RiskManager")

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _load_portfolio(portfolio_file):
    try:
        with open(portfolio_file) as f:
            return json.load(f)
    except Exception:
        return {"positions": {}, "capital": 500000, "daily_pnl_pct": 0.0}

def compute_position_size(capital, entry_price, stop_loss, risk_pct=0.02):
    """
    Kelly-inspired position sizing:
      Risk amount = capital × risk_pct (default 2%)
      Risk per share = entry - stop_loss
      Shares = risk_amount / risk_per_share
    Returns: shares, position_value, actual_risk_pct
    """
    if entry_price <= 0 or stop_loss <= 0 or entry_price <= stop_loss:
        return 0, 0, 0

    risk_amount   = capital * risk_pct
    risk_per_share = entry_price - stop_loss

    if risk_per_share <= 0:
        return 0, 0, 0

    shares          = int(risk_amount / risk_per_share)
    shares          = max(1, shares)
    position_value  = round(shares * entry_price, 2)
    actual_risk     = round((risk_per_share * shares / capital) * 100, 2)

    return shares, position_value, actual_risk

def check_rr_ratio(entry, target1, stop_loss, min_rr=2.5):
    """Check if Risk/Reward meets minimum threshold (R10)."""
    if entry <= 0 or stop_loss <= 0:
        return False, 0
    risk   = abs(entry - stop_loss)
    reward = abs(target1 - entry)
    if risk == 0:
        return False, 0
    rr = round(reward / risk, 2)
    return rr >= min_rr, rr

def check_concentration(sector, positions_map, capital, new_position_value, max_pct=0.25):
    """Check if adding new position exceeds sector concentration limit (R12)."""
    sector_value = sum(
        pos["position_value"]
        for pos in positions_map.values()
        if pos.get("sector") == sector
    )
    new_total = sector_value + new_position_value
    new_pct   = new_total / capital
    return new_pct <= max_pct, round(new_pct * 100, 1)

def get_vix_multiplier(vix_price):
    """R14: VIX-based position size multiplier."""
    if vix_price is None:
        return 1.0, "NORMAL"
    if vix_price > 25:
        return 0.0,  "HALT (VIX>25)"
    elif vix_price > 20:
        return 0.60, "REDUCED (VIX>20)"
    elif vix_price > 16:
        return 0.80, "CAUTIOUS (VIX>16)"
    else:
        return 1.0,  "NORMAL"

def run(shared_state):
    """
    Review all trade signals and compute risk-adjusted parameters.
    Flags which signals SHOULD and SHOULD NOT be paper-traded.
    """
    log.info("⚖️  RiskManager: Reviewing trade signals...")

    signals     = shared_state.get("trade_signals", [])
    portfolio_f = os.path.join(_BASE, "data", "paper_portfolio.json")
    portfolio   = _load_portfolio(portfolio_f)
    capital     = portfolio.get("capital", 500000)
    positions   = portfolio.get("positions", {})
    daily_loss  = portfolio.get("daily_pnl_pct", 0.0)

    # VIX check (R14)
    vix_data   = shared_state.get("index_prices", {}).get("INDIA VIX", {})
    vix_price  = vix_data.get("price") if vix_data else None
    vix_mult, vix_status = get_vix_multiplier(vix_price)

    # Daily loss circuit (R15)
    daily_halt = daily_loss <= -3.0

    # Active positions check (R13)
    active_count = len([p for p in positions.values() if p.get("status") == "OPEN"])

    reviewed_signals = []

    for sig in signals:
        entry  = sig.get("cmp", sig.get("price", 0))
        t1     = sig.get("target1", sig.get("target", 0))
        sl     = sig.get("stop_loss", sig.get("sl", 0))
        sector = sig.get("sector", "Unknown")
        name   = sig.get("name", "")
        score  = sig.get("score", 0)

        risk_assessment = {
            "approved":          False,
            "rejection_reasons": [],
            "risk_flags":        [],
            "position_size":     0,
            "position_value":    0,
            "actual_risk_pct":   0,
            "rr_ratio":          0,
            "vix_status":        vix_status,
            "adjusted_capital":  capital,
        }

        # ── GATE 1: VIX halt
        if vix_mult == 0.0:
            risk_assessment["rejection_reasons"].append(f"VIX HALT: {vix_status}")
            reviewed_signals.append({**sig, "risk": risk_assessment})
            continue

        # ── GATE 2: Daily loss circuit
        if daily_halt:
            risk_assessment["rejection_reasons"].append(
                f"DAILY HALT: portfolio down {daily_loss:.1f}% today"
            )
            reviewed_signals.append({**sig, "risk": risk_assessment})
            continue

        # ── GATE 3: Max simultaneous positions
        if active_count >= 5:
            risk_assessment["rejection_reasons"].append(
                f"MAX POSITIONS: {active_count}/5 already open (R13)"
            )
            reviewed_signals.append({**sig, "risk": risk_assessment})
            continue

        # ── GATE 4: R:R ratio check
        rr_ok, rr_ratio = check_rr_ratio(entry, t1, sl, min_rr=2.5)
        risk_assessment["rr_ratio"] = rr_ratio
        if not rr_ok:
            risk_assessment["rejection_reasons"].append(
                f"LOW R:R {rr_ratio:.1f}x (need 2.5x, R10)"
            )

        # ── GATE 5: Position sizing
        effective_capital = capital * vix_mult
        shares, pos_value, actual_risk = compute_position_size(
            effective_capital, entry, sl, risk_pct=0.02
        )
        risk_assessment["position_size"]   = shares
        risk_assessment["position_value"]  = pos_value
        risk_assessment["actual_risk_pct"] = actual_risk
        risk_assessment["adjusted_capital"] = round(effective_capital, 0)

        if shares == 0:
            risk_assessment["rejection_reasons"].append("Cannot compute valid position size")

        # ── GATE 6: Sector concentration
        conc_ok, sector_pct = check_concentration(
            sector, positions, capital, pos_value
        )
        risk_assessment["sector_pct"] = sector_pct
        if not conc_ok:
            risk_assessment["rejection_reasons"].append(
                f"SECTOR LIMIT: {sector} would be {sector_pct:.0f}% of portfolio (max 25%, R12)"
            )

        # ── RISK FLAGS (warnings, not blockers)
        if vix_mult < 1.0:
            risk_assessment["risk_flags"].append(f"Position reduced due to {vix_status}")
        if rr_ratio < 3.0 and rr_ratio >= 2.5:
            risk_assessment["risk_flags"].append("R:R is acceptable but not ideal (prefer 3x+)")
        if score < 82:
            risk_assessment["risk_flags"].append(f"Moderate conviction score {score} (prefer 82+)")

        # ── FINAL APPROVAL
        risk_assessment["approved"] = (
            len(risk_assessment["rejection_reasons"]) == 0 and shares > 0
        )

        reviewed_signals.append({**sig, "risk": risk_assessment})
        status = "✅ APPROVED" if risk_assessment["approved"] else "❌ REJECTED"
        log.info("  %s %s: R:R=%.1fx | Size=%d shares (₹%.0f) | %s",
                 status, name, rr_ratio, shares, pos_value,
                 risk_assessment["rejection_reasons"][0] if risk_assessment["rejection_reasons"] else "")

    # Summary
    approved_count = sum(1 for s in reviewed_signals if s.get("risk", {}).get("approved"))
    log.info("✅ RiskManager: %d/%d signals approved | VIX=%s | Positions=%d/5",
             approved_count, len(reviewed_signals), vix_status, active_count)

    shared_state["risk_reviewed_signals"] = reviewed_signals
    shared_state["risk_summary"] = {
        "approved_count": approved_count,
        "total_signals":  len(reviewed_signals),
        "vix_status":     vix_status,
        "active_positions": active_count,
        "daily_pnl_pct":  daily_loss,
        "daily_halt":     daily_halt,
        "last_run":       datetime.now().strftime("%d %b %H:%M:%S"),
    }
    return reviewed_signals
