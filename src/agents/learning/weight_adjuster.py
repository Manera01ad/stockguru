"""
WEIGHT ADJUSTER — Adaptive Scoring
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reads accuracy_stats.json and drifts learned_weights.json
based on sector/stock performance.

Rules:
  - Needs minimum 10 settled trades per sector to start adjusting
  - Max adjustment: ±30% from neutral (1.0) — prevents runaway weights
  - Adjustment step: 0.05 per cycle (gradual drift, not jumps)
  - Weight > 1.0 = sector signals are boosted
  - Weight < 1.0 = sector signals are dampened
"""

import json
import os
import logging
from datetime import datetime

log = logging.getLogger("WeightAdjuster")

_BASE         = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEIGHTS_FILE  = os.path.join(_BASE, "data", "learned_weights.json")
ACCURACY_FILE = os.path.join(_BASE, "data", "accuracy_stats.json")

MIN_TRADES_TO_ADJUST = 10   # need at least 10 outcomes before touching weights
MAX_WEIGHT           = 1.30  # 30% boost max
MIN_WEIGHT           = 0.70  # 30% dampen max
STEP                 = 0.05  # weight change per adjustment cycle
TARGET_WIN_RATE      = 0.60  # 60% = professional grade, worthy of neutral weight

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
        log.error("WeightAdjuster save failed: %s", e)

def adjust_weights():
    """
    Main function — reads accuracy stats and updates sector weights.
    Returns dict of {sector: new_weight, ...}
    """
    accuracy = _load(ACCURACY_FILE, {})
    weights  = _load(WEIGHTS_FILE,  {"sector_weights": {}, "stock_weights": {},
                                      "factor_weights": {}, "total_adjustments": 0})

    by_sector = accuracy.get("by_sector", {})
    if not by_sector:
        log.debug("WeightAdjuster: No accuracy data yet — weights unchanged")
        return weights

    adjustments_made = 0

    for sector, stats in by_sector.items():
        total    = stats.get("total", 0)
        win_rate = stats.get("win_rate", 0.0)

        # Need minimum data before adjusting
        if total < MIN_TRADES_TO_ADJUST:
            log.debug("WeightAdjuster: %s only %d trades — need %d",
                      sector, total, MIN_TRADES_TO_ADJUST)
            continue

        current_weight = weights["sector_weights"].get(sector, 1.0)

        # Decide direction
        if win_rate > TARGET_WIN_RATE + 0.10:
            # Sector is performing well (+10% above target) → boost
            new_weight = min(MAX_WEIGHT, current_weight + STEP)
            direction  = "↑ boosted"
        elif win_rate < TARGET_WIN_RATE - 0.10:
            # Sector underperforming (>10% below target) → dampen
            new_weight = max(MIN_WEIGHT, current_weight - STEP)
            direction  = "↓ dampened"
        else:
            # Within acceptable range → drift back toward neutral
            if current_weight > 1.0:
                new_weight = max(1.0, current_weight - STEP * 0.5)
                direction  = "→ normalizing"
            elif current_weight < 1.0:
                new_weight = min(1.0, current_weight + STEP * 0.5)
                direction  = "→ normalizing"
            else:
                continue  # already neutral

        if abs(new_weight - current_weight) > 0.001:
            weights["sector_weights"][sector] = round(new_weight, 3)
            adjustments_made += 1
            log.info("⚖️  Weight: %s %.2f→%.2f (win%.0f%% | %d trades) %s",
                     sector, current_weight, new_weight,
                     win_rate * 100, total, direction)

    # Stock-level adjustments (need 20+ trades per stock)
    by_stock = accuracy.get("by_stock", {})
    for stock, stats in by_stock.items():
        total    = stats.get("total", 0)
        win_rate = stats.get("win_rate", 0.0)

        if total < 20:
            continue

        current = weights["stock_weights"].get(stock, 1.0)

        if win_rate > 0.75:
            new_w = min(MAX_WEIGHT, current + STEP)
        elif win_rate < 0.45:
            new_w = max(MIN_WEIGHT, current - STEP)
        else:
            continue

        if abs(new_w - current) > 0.001:
            weights["stock_weights"][stock] = round(new_w, 3)
            adjustments_made += 1

    if adjustments_made > 0:
        weights["total_adjustments"] = weights.get("total_adjustments", 0) + adjustments_made
        weights["last_adjusted"]     = datetime.now().isoformat()
        _save(WEIGHTS_FILE, weights)
        log.info("✅ WeightAdjuster: %d adjustments made (total: %d)",
                 adjustments_made, weights["total_adjustments"])
    else:
        log.debug("WeightAdjuster: No adjustments needed this cycle")

    return weights

def get_weights():
    """Returns current learned weights."""
    return _load(WEIGHTS_FILE, {
        "sector_weights": {},
        "stock_weights":  {},
        "factor_weights": {"fundamental_pct": 0.40, "technical_pct": 0.30,
                           "momentum_pct": 0.20, "risk_pct": 0.10},
    })

def apply_sector_weight(base_score, sector):
    """Apply sector weight to a base score. Returns adjusted score."""
    weights = get_weights()
    w       = weights.get("sector_weights", {}).get(sector, 1.0)
    adjusted = round(base_score * w, 1)
    return min(100, max(0, adjusted))

def apply_stock_weight(base_score, stock_name):
    """Apply stock-specific weight to a base score."""
    weights = get_weights()
    w       = weights.get("stock_weights", {}).get(stock_name, 1.0)
    adjusted = round(base_score * w, 1)
    return min(100, max(0, adjusted))
