"""
AGENT 13 — PATTERN MEMORY (Self-Learning)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Analyze signal history, identify which COMBINATIONS
          of conditions consistently produce winning trades.
          This is how the system learns the "top 5% trader" behavior.

How it works:
  1. Reads signal_history.json (all past trades with outcomes)
  2. Groups signals by condition combos (RSI range + sector + FII)
  3. Computes win rate per pattern combo
  4. Saves top patterns to pattern_library.json
  5. Claude Intelligence reads pattern_library to calibrate confidence

Example patterns discovered:
  "Banking + RSI 40-55 + FII buying + PCR<0.8 → 78% win rate (18 trades)"
  "Defence + Volume surge >2x + above EMA50 → 82% win rate (11 trades)"
"""

import os
import json
import logging
from datetime import datetime
from collections import defaultdict

log = logging.getLogger("PatternMemory")

_BASE        = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HISTORY_FILE = os.path.join(_BASE, "data", "signal_history.json")
PATTERN_FILE = os.path.join(_BASE, "data", "pattern_library.json")

MIN_PATTERN_TRADES = 5  # need at least 5 trades to call it a pattern

def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def _save(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        log.error("PatternMemory save failed: %s", e)

def _bucket_rsi(rsi):
    """Bucket RSI into meaningful ranges."""
    if rsi is None: return "rsi_unknown"
    if rsi < 30:    return "rsi_oversold"
    if rsi < 45:    return "rsi_low"
    if rsi < 60:    return "rsi_mid"
    if rsi < 72:    return "rsi_high"
    return "rsi_overbought"

def _bucket_vol(vol_surge):
    """Bucket volume surge."""
    if vol_surge is None: return "vol_unknown"
    if vol_surge >= 2.0:  return "vol_huge"
    if vol_surge >= 1.5:  return "vol_high"
    if vol_surge >= 1.2:  return "vol_above"
    return "vol_normal"

def _bucket_score(score):
    """Bucket agent score."""
    if score >= 90: return "score_top"
    if score >= 83: return "score_high"
    if score >= 75: return "score_mid"
    return "score_low"

def _bucket_gates(gates):
    """Bucket gates passed."""
    if gates >= 7: return "gates_7_8"
    if gates >= 6: return "gates_6"
    if gates >= 5: return "gates_5"
    return "gates_low"

def extract_patterns(history):
    """
    Extract pattern signatures from signal history.
    Each signal gets a set of feature buckets → compute win rate per combo.
    """
    # Group outcomes by feature combinations
    pattern_groups = defaultdict(lambda: {"wins": 0, "losses": 0, "trades": []})

    for record in history:
        outcome = record.get("outcome", "OPEN")
        if outcome in ("OPEN", "EXPIRED"):
            continue

        is_win = outcome in ("T1_HIT", "T2_HIT")

        sector  = record.get("sector", "Unknown")
        score   = record.get("score", 0)
        gates   = record.get("gates_passed", 0)
        conf    = record.get("confidence", "MEDIUM")
        sig_type = record.get("signal_type", "BUY")

        # Build feature combos (from most specific to least)
        combos = [
            # 3-factor patterns
            f"{sector}|{_bucket_rsi(record.get('rsi'))}|{_bucket_vol(record.get('vol_surge'))}",
            f"{sector}|{_bucket_score(score)}|{_bucket_gates(gates)}",
            f"{sig_type}|{_bucket_gates(gates)}|{conf}",
            # 2-factor patterns
            f"{sector}|{_bucket_gates(gates)}",
            f"{sector}|{conf}",
            f"{_bucket_score(score)}|{_bucket_vol(record.get('vol_surge'))}",
        ]

        for combo in combos:
            d = pattern_groups[combo]
            d["wins"]   += 1 if is_win else 0
            d["losses"] += 0 if is_win else 1
            d["trades"].append({
                "name":    record["name"],
                "outcome": outcome,
                "pnl_pct": record.get("pnl_pct", 0),
            })

    return pattern_groups

def build_readable_description(combo_key):
    """Convert a pipe-separated combo key into a human-readable pattern description."""
    parts = combo_key.split("|")
    desc_map = {
        "rsi_oversold":    "RSI<30 (oversold)",
        "rsi_low":         "RSI 30-45 (dip zone)",
        "rsi_mid":         "RSI 45-60 (momentum)",
        "rsi_high":        "RSI 60-72 (strong)",
        "rsi_overbought":  "RSI>72 (overbought)",
        "vol_huge":        "Volume >2x avg",
        "vol_high":        "Volume >1.5x avg",
        "vol_above":       "Volume >1.2x avg",
        "vol_normal":      "Normal volume",
        "score_top":       "Score 90+",
        "score_high":      "Score 83-90",
        "score_mid":       "Score 75-83",
        "score_low":       "Score <75",
        "gates_7_8":       "7-8/8 gates",
        "gates_6":         "6/8 gates",
        "gates_5":         "5/8 gates",
        "gates_low":       "<5 gates",
    }
    readable = [desc_map.get(p, p) for p in parts]
    return " + ".join(readable)

def run(shared_state):
    """Analyze signal history, rebuild pattern library, update shared_state."""
    log.info("🧬 PatternMemory: Analyzing signal history for patterns...")

    history = _load(HISTORY_FILE, [])
    settled = [r for r in history if r.get("outcome") not in ("OPEN", "EXPIRED")]

    if len(settled) < MIN_PATTERN_TRADES:
        log.info("PatternMemory: Only %d settled trades — need %d minimum to extract patterns",
                 len(settled), MIN_PATTERN_TRADES)
        shared_state["pattern_library"] = []
        return []

    pattern_groups = extract_patterns(settled)

    # Build ranked pattern list
    patterns = []
    for combo, stats in pattern_groups.items():
        total = stats["wins"] + stats["losses"]
        if total < MIN_PATTERN_TRADES:
            continue

        win_rate = stats["wins"] / total
        avg_pnl  = sum(t.get("pnl_pct", 0) or 0 for t in stats["trades"]) / total

        patterns.append({
            "pattern_key":  combo,
            "description":  build_readable_description(combo),
            "win_rate":     round(win_rate, 3),
            "count":        total,
            "wins":         stats["wins"],
            "losses":       stats["losses"],
            "avg_pnl_pct":  round(avg_pnl, 2),
            "expectancy":   round(win_rate * avg_pnl, 2),
            "quality":      "GOLD"  if win_rate >= 0.70 and total >= 10 else
                            "SILVER" if win_rate >= 0.60 and total >= 5  else
                            "LEARNING",
            "updated_at":   datetime.now().isoformat(),
        })

    # Sort by win rate + count (favor patterns with both high accuracy AND data)
    patterns.sort(key=lambda x: -(x["win_rate"] * min(x["count"] / 10, 1.0)))

    top_patterns = patterns[:20]

    _save(PATTERN_FILE, top_patterns)
    shared_state["pattern_library"] = top_patterns

    gold    = [p for p in top_patterns if p["quality"] == "GOLD"]
    silver  = [p for p in top_patterns if p["quality"] == "SILVER"]

    log.info("✅ PatternMemory: %d patterns found | GOLD=%d | SILVER=%d | Best: %.0f%% (%s)",
             len(top_patterns), len(gold), len(silver),
             (top_patterns[0]["win_rate"] * 100) if top_patterns else 0,
             top_patterns[0]["description"][:40] if top_patterns else "none")
    return top_patterns
