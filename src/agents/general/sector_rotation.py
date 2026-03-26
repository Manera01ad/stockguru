"""
AGENT 10 — SECTOR ROTATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Identify which sectors are gaining/losing momentum.
          Professional traders only go long in leading sectors (R1, R27).
          Validates every trade signal against sector trend.
Runs    : Every 15 minutes
Cost    : Zero — Yahoo Finance sector indices
Reports : Feeds claude_intelligence + risk_manager + paper_trader gate R1
"""

import requests
import time
import logging
from datetime import datetime

log = logging.getLogger("SectorRotation")

# ── SECTOR INDEX SYMBOLS ──────────────────────────────────────────────────────
# These are Nifty sector indices available on Yahoo Finance
SECTOR_INDICES = [
    {"name": "NIFTY BANK",     "symbol": "^NSEBANK",    "stocks": ["Banking", "NBFC"]},
    {"name": "NIFTY IT",       "symbol": "^CNXIT",       "stocks": ["IT"]},
    {"name": "NIFTY PHARMA",   "symbol": "^CNXPHARMA",  "stocks": ["Pharma", "Healthcare"]},
    {"name": "NIFTY AUTO",     "symbol": "^CNXAUTO",    "stocks": ["Auto"]},
    {"name": "NIFTY FMCG",     "symbol": "^CNXFMCG",    "stocks": ["FMCG"]},
    {"name": "NIFTY METAL",    "symbol": "^CNXMETAL",   "stocks": ["Metals"]},
    {"name": "NIFTY ENERGY",   "symbol": "^CNXENERGY",  "stocks": ["Energy", "Power"]},
    {"name": "NIFTY INFRA",    "symbol": "^CNXINFRA",   "stocks": ["Infra"]},
    {"name": "NIFTY REALTY",   "symbol": "^CNXREALTY",  "stocks": ["Realty"]},
    {"name": "NIFTY MEDIA",    "symbol": "^CNXMEDIA",   "stocks": ["Media"]},
]

# ── PRICE FETCH ───────────────────────────────────────────────────────────────
def fetch_sector_price(symbol):
    """Fetch sector index price and momentum."""
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
               f"?interval=1d&range=5d")
        r   = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        d   = r.json()
        res = d["chart"]["result"][0]
        meta      = res["meta"]
        price     = meta.get("regularMarketPrice", 0)
        prev      = meta.get("chartPreviousClose", price) or price
        chg_pct   = round(((price - prev) / prev) * 100, 2) if prev else 0
        closes    = res["indicators"]["quote"][0].get("close", [])
        closes    = [c for c in closes if c is not None]
        # 5-day momentum
        mom5d     = round(((closes[-1] - closes[0]) / closes[0]) * 100, 2) if len(closes) >= 2 else 0
        return {"price": round(price, 2), "change_pct": chg_pct, "momentum_5d": mom5d}
    except Exception as e:
        log.debug("Sector fetch failed %s: %s", symbol, e)
        return None

# ── CLASSIFY MOMENTUM ─────────────────────────────────────────────────────────
def classify_momentum(chg_pct, mom5d):
    """Return sector momentum classification."""
    score = (chg_pct * 0.5) + (mom5d * 0.5)  # blend 1-day + 5-day

    if score > 1.5:    return "STRONG_UP",   score
    elif score > 0.5:  return "UP",          score
    elif score > -0.5: return "NEUTRAL",     score
    elif score > -1.5: return "DOWN",        score
    else:              return "STRONG_DOWN", score

# ── MAIN AGENT ────────────────────────────────────────────────────────────────
def run(shared_state):
    """Fetch all sector indices, rank by momentum, flag leaders vs laggards."""
    log.info("🔄 SectorRotation: Fetching %d sector indices...", len(SECTOR_INDICES))

    sector_data  = []
    sector_scores = {}

    for sec in SECTOR_INDICES:
        data = fetch_sector_price(sec["symbol"])
        if data:
            momentum, score = classify_momentum(data["change_pct"], data["momentum_5d"])
            entry = {
                **sec, **data,
                "momentum":       momentum,
                "rotation_score": round(score, 2),
            }
            sector_data.append(entry)

            # Map to stock sectors for gate checking
            for stock_sector in sec["stocks"]:
                sector_scores[stock_sector] = {
                    "momentum":   momentum,
                    "score":      score,
                    "gate_pass":  momentum in ("STRONG_UP", "UP"),  # R1 gate
                    "sector_idx": sec["name"],
                }
            log.info("  %s: %+.2f%% (5d: %+.2f%%) → %s",
                     sec["name"], data["change_pct"], data["momentum_5d"], momentum)
        time.sleep(0.2)

    # Sort by rotation score
    sector_data.sort(key=lambda x: -x["rotation_score"])

    top_sectors  = [s["name"] for s in sector_data[:3]]
    weak_sectors = [s["name"] for s in sector_data[-3:]]

    # Overall rotation signal
    bullish_count = sum(1 for s in sector_data if "UP" in s["momentum"])
    total_count   = len(sector_data)
    breadth       = round(bullish_count / total_count, 2) if total_count else 0.5
    market_breadth = "BROAD_RALLY" if breadth > 0.70 else \
                     "SELECTIVE"   if breadth > 0.50 else \
                     "DEFENSIVE"   if breadth > 0.30 else "BROAD_WEAKNESS"

    result = {
        "sectors":        sector_data,
        "sector_scores":  sector_scores,  # used by paper_trader for R1 gate
        "top_sectors":    top_sectors,
        "weak_sectors":   weak_sectors,
        "breadth":        breadth,
        "market_breadth": market_breadth,
        "last_run":       datetime.now().strftime("%d %b %H:%M:%S"),
    }

    shared_state["sector_rotation"]      = result
    shared_state["sector_rotation_last"] = result["last_run"]

    log.info("✅ SectorRotation: Leaders=%s | Laggards=%s | Breadth=%s (%.0f%%)",
             top_sectors[:2], weak_sectors[:2], market_breadth, breadth * 100)
    return result
