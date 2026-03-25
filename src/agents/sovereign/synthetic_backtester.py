# ══════════════════════════════════════════════════════════════════════════════
# StockGuru — Synthetic Backtester (Phase 2)
# Runs 3 stress scenarios every 6 hours against open paper_portfolio positions.
# Pure Python math + 1 Claude Haiku call for narrative + hedge recommendation.
# Writes: shared_state["synthetic_backtest"] + data/backtest_scenarios.json
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import logging
from datetime import datetime

log = logging.getLogger(__name__)

_DATA_DIR  = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
_SCENARIOS_FILE = os.path.join(_DATA_DIR, "backtest_scenarios.json")
_HISTORY_MAX = 30

# Sector membership for SECTOR_SELLOFF scenario
_SECTOR_MAP = {
    "Banking":  ["HDFC BANK", "ICICI BANK", "BANK NIFTY"],
    "Telecom":  ["AIRTEL"],
    "Defence":  ["BEL"],
    "NBFC":     ["BAJAJ FIN", "MUTHOOT"],
    "Aviation": ["INDIGO"],
    "Food Tech":["ZOMATO"],
}


# ─── Public entry point ────────────────────────────────────────────────────────

def run(shared_state: dict) -> dict:
    """
    Run 3 stress scenarios against current open paper positions.
    Returns results dict and writes to shared_state["synthetic_backtest"].
    Fails gracefully — never raises.
    """
    portfolio = shared_state.get("paper_portfolio", {})
    positions = portfolio.get("positions", {})
    capital   = float(portfolio.get("capital", 100000))

    # Minimal run — even with no positions, update the run timestamp
    run_id = f"BACKTEST_{datetime.now().strftime('%Y%m%d_%H%M')}"

    if not positions:
        result = {
            "run_id":               run_id,
            "portfolio_snapshot":   {"capital": capital, "positions_count": 0, "invested": 0},
            "scenarios":            {
                "FLASH_CRASH":    {"positions_hit": [], "drawdown_pct": 0.0, "narrative": "No open positions."},
                "SECTOR_SELLOFF": {"positions_hit": [], "drawdown_pct": 0.0, "narrative": "No open positions."},
                "BLACK_SWAN":     {"positions_hit": [], "drawdown_pct": 0.0, "narrative": "No open positions."},
            },
            "black_swan_probability": "LOW",
            "max_drawdown_scenario":  "N/A",
            "recommended_hedge":      "No positions to hedge.",
            "last_run":               datetime.now().strftime("%d %b %H:%M:%S"),
        }
        shared_state["synthetic_backtest"] = result
        _save_to_file(result)
        return result

    # Compute invested amount
    invested = sum(
        p.get("qty", 0) * p.get("entry_price", 0)
        for p in positions.values()
    )
    portfolio_snap = {
        "capital":          capital,
        "positions_count":  len(positions),
        "invested":         round(invested, 2),
        "invested_pct":     round(invested / capital * 100, 1) if capital else 0,
    }

    # Run the 3 scenarios
    flash    = _simulate_flash_crash(positions, capital)
    sector   = _simulate_sector_selloff(positions, capital)
    black_sw = _simulate_black_swan(positions, capital)

    scenarios = {
        "FLASH_CRASH":    flash,
        "SECTOR_SELLOFF": sector,
        "BLACK_SWAN":     black_sw,
    }

    # LLM narrative (1 batched Haiku call)
    try:
        narratives = _get_claude_narrative(scenarios, portfolio_snap)
        for key in scenarios:
            scenarios[key]["narrative"] = narratives.get(key, "—")
        recommended_hedge = narratives.get("recommended_hedge", "Monitor positions closely.")
    except Exception as e:
        log.warning(f"Backtester: LLM narrative failed: {e}")
        for key in scenarios:
            scenarios[key]["narrative"] = "LLM unavailable."
        recommended_hedge = "LLM unavailable — review manually."

    probability     = _classify_probability(scenarios)
    max_dd_scenario = max(scenarios, key=lambda k: abs(scenarios[k].get("drawdown_pct", 0)))

    result = {
        "run_id":               run_id,
        "portfolio_snapshot":   portfolio_snap,
        "scenarios":            scenarios,
        "black_swan_probability": probability,
        "max_drawdown_scenario":  max_dd_scenario,
        "recommended_hedge":      recommended_hedge,
        "last_run":               datetime.now().strftime("%d %b %H:%M:%S"),
    }

    shared_state["synthetic_backtest"] = result
    _save_to_file(result)
    log.info(f"Backtester: complete — prob={probability} | max_dd={scenarios[max_dd_scenario]['drawdown_pct']:.1f}%")
    return result


# ─── Scenario Simulations ─────────────────────────────────────────────────────

def _simulate_flash_crash(positions: dict, capital: float) -> dict:
    """
    FLASH_CRASH: Nifty drops -5% in one session.
    All positions shocked by -5%. Check which hit their stop loss.
    """
    shock_factor = 0.95
    hits = []
    total_loss = 0.0

    for name, p in positions.items():
        entry = float(p.get("entry_price", 0))
        sl    = float(p.get("stop_loss", 0))
        qty   = int(p.get("qty", 0))
        sim_price = entry * shock_factor
        if sl > 0 and sim_price <= sl:
            loss = (entry - sl) * qty
            hits.append(name)
            total_loss += loss

    drawdown_pct = round(-total_loss / capital * 100, 2) if capital else 0.0
    return {
        "positions_hit": hits,
        "drawdown_pct":  drawdown_pct,
        "shock":         "-5% flash crash",
        "sl_triggered":  len(hits),
    }


def _simulate_sector_selloff(positions: dict, capital: float) -> dict:
    """
    SECTOR_SELLOFF: Worst portfolio sector drops -4%.
    Identify largest sector exposure, apply -4% shock to those positions only.
    """
    # Find sector with most positions
    sector_counts = {}
    for name in positions:
        for sector, stocks in _SECTOR_MAP.items():
            if any(s.upper() in name.upper() for s in stocks):
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                break

    worst_sector = max(sector_counts, key=sector_counts.get) if sector_counts else None
    sector_stocks = _SECTOR_MAP.get(worst_sector, []) if worst_sector else []

    shock_factor = 0.96  # -4%
    hits = []
    total_loss = 0.0

    for name, p in positions.items():
        is_in_sector = any(s.upper() in name.upper() for s in sector_stocks)
        if not is_in_sector:
            continue
        entry = float(p.get("entry_price", 0))
        sl    = float(p.get("stop_loss", 0))
        qty   = int(p.get("qty", 0))
        sim_price = entry * shock_factor
        if sl > 0 and sim_price <= sl:
            loss = (entry - sl) * qty
            hits.append(name)
            total_loss += loss

    drawdown_pct = round(-total_loss / capital * 100, 2) if capital else 0.0
    return {
        "positions_hit":  hits,
        "drawdown_pct":   drawdown_pct,
        "shock":          f"-4% sector selloff ({worst_sector or 'unknown'})",
        "worst_sector":   worst_sector or "N/A",
        "sl_triggered":   len(hits),
    }


def _simulate_black_swan(positions: dict, capital: float) -> dict:
    """
    BLACK_SWAN: All positions drop -10%, then recover +5% (net -5.5% from entry).
    Checks how many SLs are triggered before the bounce.
    """
    shock_factor   = 0.90   # initial -10%
    bounce_factor  = 1.05   # then +5%
    net_factor     = shock_factor * bounce_factor  # = 0.945

    hits_at_shock = []
    hits_net = []
    total_loss = 0.0

    for name, p in positions.items():
        entry = float(p.get("entry_price", 0))
        sl    = float(p.get("stop_loss", 0))
        qty   = int(p.get("qty", 0))
        sim_shock  = entry * shock_factor
        sim_net    = entry * net_factor
        if sl > 0 and sim_shock <= sl:
            # SL hit during the shock phase (before bounce)
            loss = (entry - sl) * qty
            hits_at_shock.append(name)
            total_loss += loss
        elif sl > 0 and sim_net <= sl:
            # SL not hit at shock but position underwater after bounce
            loss = (entry - sim_net) * qty
            hits_net.append(name)
            total_loss += loss * 0.5  # partial loss assumption

    all_hits = list(set(hits_at_shock + hits_net))
    drawdown_pct = round(-total_loss / capital * 100, 2) if capital else 0.0
    return {
        "positions_hit":  all_hits,
        "drawdown_pct":   drawdown_pct,
        "shock":          "-10% crash then +5% bounce",
        "sl_triggered":   len(hits_at_shock),
        "net_underwater": len(hits_net),
    }


# ─── LLM Narrative ────────────────────────────────────────────────────────────

def _get_claude_narrative(scenarios: dict, portfolio: dict) -> dict:
    """
    One Claude Haiku call to generate 1-sentence narrative per scenario
    + a recommended hedge action.
    Returns dict: {FLASH_CRASH: "...", SECTOR_SELLOFF: "...", BLACK_SWAN: "...", recommended_hedge: "..."}
    """
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("No ANTHROPIC_API_KEY")

        portfolio_str = (
            f"Portfolio: {portfolio['positions_count']} positions, "
            f"invested ₹{portfolio['invested']:,.0f} ({portfolio['invested_pct']}% of capital)"
        )
        sc_lines = []
        for k, v in scenarios.items():
            sc_lines.append(
                f"{k}: {len(v['positions_hit'])} SL hits, drawdown {v['drawdown_pct']:.1f}%"
            )

        prompt = (
            f"Indian stock market paper portfolio stress test results.\n"
            f"{portfolio_str}\n\nScenarios:\n" + "\n".join(sc_lines) +
            "\n\nProvide:\n"
            "1. FLASH_CRASH: one sentence assessment (max 12 words)\n"
            "2. SECTOR_SELLOFF: one sentence assessment (max 12 words)\n"
            "3. BLACK_SWAN: one sentence assessment (max 12 words)\n"
            "4. recommended_hedge: one actionable hedge (max 15 words)\n\n"
            "Respond ONLY in this JSON format:\n"
            '{"FLASH_CRASH":"...","SECTOR_SELLOFF":"...","BLACK_SWAN":"...","recommended_hedge":"..."}'
        )

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        # Extract JSON from response
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        log.warning(f"Backtester LLM: {e}")
    return {
        "FLASH_CRASH":    "Review flash crash exposure.",
        "SECTOR_SELLOFF": "Sector concentration risk noted.",
        "BLACK_SWAN":     "Tail risk is manageable.",
        "recommended_hedge": "Consider trailing stops on largest positions.",
    }


# ─── Probability Classification ───────────────────────────────────────────────

def _classify_probability(scenarios: dict) -> str:
    """
    Classify overall Black Swan probability based on max drawdown.
    HIGH if any scenario >8%, MEDIUM if >4%, else LOW.
    """
    max_dd = max(abs(v.get("drawdown_pct", 0)) for v in scenarios.values())
    if max_dd > 8:
        return "HIGH"
    if max_dd > 4:
        return "MEDIUM"
    return "LOW"


# ─── Persistence ──────────────────────────────────────────────────────────────

def _save_to_file(result: dict) -> None:
    """Append result to backtest_scenarios.json (rolling _HISTORY_MAX entries)."""
    try:
        if os.path.exists(_SCENARIOS_FILE):
            with open(_SCENARIOS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []

        if not isinstance(history, list):
            history = []

        history.append(result)
        if len(history) > _HISTORY_MAX:
            history = history[-_HISTORY_MAX:]

        with open(_SCENARIOS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, default=str)
    except Exception as e:
        log.error(f"Backtester: failed to save scenarios: {e}")
