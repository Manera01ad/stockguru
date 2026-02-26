"""
SIGNAL TRACKER — Learning Foundation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Records every signal issued by paper_trader, then periodically
checks actual market outcomes (T1 hit / T2 hit / SL hit).

This is the ground truth that feeds the entire learning loop:
  record_signal() → signal_history.json
  check_outcomes() → accuracy_stats.json + pattern data
  get_accuracy_stats() → fed into Claude Intelligence prompt
"""

import json
import os
import logging
from datetime import datetime, timedelta

log = logging.getLogger("SignalTracker")

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HISTORY_FILE  = os.path.join(_BASE, "data", "signal_history.json")
ACCURACY_FILE = os.path.join(_BASE, "data", "accuracy_stats.json")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def _load(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def _save(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        log.error("Save failed %s: %s", path, e)

# ── RECORD NEW SIGNAL ─────────────────────────────────────────────────────────
def record_signal(name, sector, signal_type, entry_price,
                  target1, target2, stop_loss, score,
                  confidence, gates_passed, source_agent="paper_trader"):
    """
    Called when paper_trader executes a position.
    Creates a permanent record of the prediction for later outcome tracking.
    """
    history = _load(HISTORY_FILE, [])

    record = {
        "id":            f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "name":          name,
        "sector":        sector,
        "signal_type":   signal_type,         # STRONG BUY / BUY
        "entry_price":   round(entry_price, 2),
        "target1":       round(target1, 2),
        "target2":       round(target2, 2),
        "stop_loss":     round(stop_loss, 2),
        "score":         score,
        "confidence":    confidence,           # HIGH / MEDIUM / LOW
        "gates_passed":  gates_passed,         # out of 8
        "source_agent":  source_agent,
        "issued_at":     datetime.now().isoformat(),
        "outcome":       "OPEN",               # updated later: T1_HIT / T2_HIT / SL_HIT / EXPIRED
        "exit_price":    None,
        "exit_at":       None,
        "pnl_pct":       None,
        "checked_count": 0,
    }

    history.append(record)
    _save(HISTORY_FILE, history)
    log.info("📝 SignalTracker: Recorded %s %s @ ₹%s (gates: %d/8)",
             signal_type, name, entry_price, gates_passed)
    return record["id"]

# ── CHECK OUTCOMES ────────────────────────────────────────────────────────────
def check_outcomes(price_cache, shared_state=None):
    """
    Called every 5-minute price cycle.
    Checks all OPEN signals against current prices.
    Updates outcomes → feeds accuracy stats.
    """
    history = _load(HISTORY_FILE, [])
    if not history:
        return

    updated = False
    now     = datetime.now()

    for rec in history:
        if rec["outcome"] != "OPEN":
            continue

        name  = rec["name"]
        price = None

        # Try to get current price from price_cache
        cached = price_cache.get(name)
        if cached and cached.get("price"):
            price = cached["price"]
        elif shared_state:
            # Try scanner results
            for s in shared_state.get("scanner_results", []):
                if s.get("name") == name and s.get("price"):
                    price = s["price"]
                    break

        if not price:
            rec["checked_count"] = rec.get("checked_count", 0) + 1
            # Expire after 30 failed checks (1.5 days of no price data)
            if rec["checked_count"] > 30:
                rec["outcome"]   = "EXPIRED"
                rec["exit_at"]   = now.isoformat()
                rec["pnl_pct"]   = 0.0
                updated = True
            continue

        entry  = rec["entry_price"]
        t1     = rec["target1"]
        sl     = rec["stop_loss"]
        t2     = rec["target2"]

        # Check outcomes in order of priority
        if price >= t2:
            outcome   = "T2_HIT"
            pnl_pct   = round(((t2 - entry) / entry) * 100, 2)
        elif price >= t1:
            outcome   = "T1_HIT"
            pnl_pct   = round(((t1 - entry) / entry) * 100, 2)
        elif price <= sl:
            outcome   = "SL_HIT"
            pnl_pct   = round(((sl - entry) / entry) * 100, 2)
        else:
            # Still open — check for expiry (20 trading days = ~1 month)
            issued = datetime.fromisoformat(rec["issued_at"])
            if (now - issued).days > 30:
                # Expired — record at current price
                outcome = "EXPIRED"
                pnl_pct = round(((price - entry) / entry) * 100, 2)
            else:
                rec["checked_count"] = rec.get("checked_count", 0) + 1
                continue  # Still open, check next time

        rec["outcome"]    = outcome
        rec["exit_price"] = price
        rec["exit_at"]    = now.isoformat()
        rec["pnl_pct"]    = pnl_pct
        updated           = True

        log.info("📊 SignalTracker: %s %s → %s (P&L: %+.1f%%)",
                 rec["name"], rec["signal_type"], outcome, pnl_pct)

    if updated:
        _save(HISTORY_FILE, history)
        _rebuild_accuracy_stats(history)

# ── REBUILD ACCURACY STATS ────────────────────────────────────────────────────
def _rebuild_accuracy_stats(history):
    """Rebuild accuracy_stats.json from full signal history."""
    settled   = [r for r in history if r["outcome"] not in ("OPEN", "EXPIRED")]
    by_sector = {}
    by_stock  = {}

    wins_t1 = losses_sl = wins_t2 = 0
    win_pnls = []
    loss_pnls = []

    for r in settled:
        is_win = r["outcome"] in ("T1_HIT", "T2_HIT")
        pnl    = r.get("pnl_pct", 0) or 0

        if r["outcome"] == "T1_HIT":  wins_t1 += 1
        if r["outcome"] == "T2_HIT":  wins_t2 += 1
        if r["outcome"] == "SL_HIT":  losses_sl += 1

        if is_win:  win_pnls.append(pnl)
        else:       loss_pnls.append(pnl)

        # By sector
        sec = r.get("sector", "Unknown")
        if sec not in by_sector:
            by_sector[sec] = {"total": 0, "wins": 0, "losses": 0,
                              "win_rate": 0.0, "avg_pnl": 0.0, "pnls": []}
        by_sector[sec]["total"]  += 1
        by_sector[sec]["wins"]   += 1 if is_win else 0
        by_sector[sec]["losses"] += 0 if is_win else 1
        by_sector[sec]["pnls"].append(pnl)

        # By stock
        stk = r["name"]
        if stk not in by_stock:
            by_stock[stk] = {"total": 0, "wins": 0, "losses": 0,
                             "win_rate": 0.0, "avg_pnl": 0.0}
        by_stock[stk]["total"]  += 1
        by_stock[stk]["wins"]   += 1 if is_win else 0
        by_stock[stk]["losses"] += 0 if is_win else 1

    # Calculate rates
    for sec, d in by_sector.items():
        if d["total"] > 0:
            d["win_rate"] = round(d["wins"] / d["total"], 3)
            d["avg_pnl"]  = round(sum(d["pnls"]) / len(d["pnls"]), 2)
        del d["pnls"]  # don't need raw array in stats

    for stk, d in by_stock.items():
        if d["total"] > 0:
            d["win_rate"] = round(d["wins"] / d["total"], 3)

    total = len(settled)
    wins  = wins_t1 + wins_t2

    overall = {
        "total_signals":      len(history),
        "outcomes_recorded":  total,
        "wins_t1":            wins_t1,
        "wins_t2":            wins_t2,
        "losses_sl":          losses_sl,
        "open":               len([r for r in history if r["outcome"] == "OPEN"]),
        "win_rate":           round(wins / total, 3) if total > 0 else 0.0,
        "avg_win_pct":        round(sum(win_pnls) / len(win_pnls), 2) if win_pnls else 0.0,
        "avg_loss_pct":       round(sum(loss_pnls) / len(loss_pnls), 2) if loss_pnls else 0.0,
        "expectancy":         round(
            ((wins / total) * (sum(win_pnls)/len(win_pnls) if win_pnls else 0)) +
            (((total - wins) / total) * (sum(loss_pnls)/len(loss_pnls) if loss_pnls else 0)),
            2
        ) if total > 0 else 0.0,
    }

    stats = {
        "by_sector":    by_sector,
        "by_stock":     by_stock,
        "overall":      overall,
        "last_updated": datetime.now().isoformat(),
    }
    _save(ACCURACY_FILE, stats)
    log.info("📈 Accuracy: Win rate %.1f%% | %d settled trades | Expectancy: %.2f%%",
             overall["win_rate"] * 100, total, overall["expectancy"])
    return stats

# ── GET ACCURACY SUMMARY ──────────────────────────────────────────────────────
def get_accuracy_stats():
    """Returns current accuracy stats dict (for Claude Intelligence prompt)."""
    return _load(ACCURACY_FILE, {"by_sector": {}, "by_stock": {}, "overall": {}})

def get_open_signals():
    """Returns all currently OPEN signals."""
    history = _load(HISTORY_FILE, [])
    return [r for r in history if r["outcome"] == "OPEN"]

def get_recent_outcomes(n=20):
    """Returns the last N settled signals with outcomes."""
    history = _load(HISTORY_FILE, [])
    settled = [r for r in history if r["outcome"] not in ("OPEN",)]
    return sorted(settled, key=lambda x: x.get("exit_at",""), reverse=True)[:n]
