"""
AGENT 3 — TRADE SIGNAL AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Take scanner results + news sentiment,
          generate precise trade signals with:
          - Entry zone (buy range)
          - Target 1 (short term 10-15%)
          - Target 2 (medium term 20-25%)
          - Stop Loss (8% below entry)
          - Risk/Reward ratio
          - Confidence level
          - Rationale (3 bullet points)
Runs    : Every 15 minutes (after scanner + news)
Reports : Telegram (Score ≥ 82) + Dashboard (all)
"""

import logging
from datetime import datetime

log = logging.getLogger("TradeSignal")

# ── SECTOR TAILWINDS (macro context, updated manually monthly) ───────────────
SECTOR_TAILWINDS = {
    "Banking":    {"score": +2, "reason": "RBI rate pivot expected Apr 2026; NIM expansion"},
    "Telecom":    {"score": +2, "reason": "5G subscriber growth; ARPU rising 15-18% YoY"},
    "Defence":    {"score": +2, "reason": "PLI scheme; ₹6L Cr order pipeline; atmanirbhar"},
    "NBFC":       {"score": +1, "reason": "Credit growth 18% YoY; gold price tailwind"},
    "Gold Loan":  {"score": +2, "reason": "Gold at ATH; AUM growth accelerating"},
    "Pharma":     {"score": +1, "reason": "USFDA approvals; chronic segment growth"},
    "Auto":       {"score": +1, "reason": "EV transition + rural recovery; CV cycle up"},
    "IT":         {"score": -1, "reason": "US macro uncertainty; deal ramp-up slow"},
    "Metals":     {"score": -1, "reason": "China demand weak; global oversupply"},
    "FMCG":       {"score":  0, "reason": "Rural recovery offset by urban slowdown"},
    "Energy":     {"score": +1, "reason": "Crude easing benefits downstream"},
    "Infra":      {"score": +1, "reason": "Capex budget ₹11.1L Cr; order flows strong"},
    "Power":      {"score": +1, "reason": "Renewable energy push; capacity additions"},
    "Food Tech":  {"score": +1, "reason": "Profitability inflection; Blinkit hypergrowth"},
    "Healthcare": {"score": +1, "reason": "Premiumisation; NABH capacity expansion"},
    "Aviation":   {"score": +1, "reason": "Crude -12% YoY; pax numbers +18%"},
    "Insurance":  {"score": +1, "reason": "Protection gap; rising penetration"},
    "Realty":     {"score":  0, "reason": "Premium segment strong; affordable slow"},
    "Fintech":    {"score":  0, "reason": "Regulatory clarity awaited"},
}

def calculate_entry_zone(price, signal_strength, tech=None):
    """
    Entry zone — IIFL pivot-based if available, else signal-strength fallback.
    IIFL rule: buy within 5-7% above pivot breakout.
    """
    if tech and tech.get("pivot_pp") and not tech.get("chasing"):
        # Use pre-computed IIFL entry zone from technical agent
        return tech["entry_low"], tech["entry_high"]
    # Fallback: signal-strength based
    if signal_strength == "STRONG BUY":
        low  = round(price * 0.995, 1)
        high = round(price * 1.005, 1)
    elif signal_strength == "BUY":
        low  = round(price * 0.98, 1)
        high = round(price * 1.002, 1)
    else:
        low  = round(price * 0.96, 1)
        high = round(price * 0.99, 1)
    return low, high

def calculate_targets(price, sector, score, tech=None):
    """
    Targets — IIFL uses Pivot R1/R2 (historical resistance).
    Falls back to sector-adjusted percentage if pivot not available.
    """
    if tech and tech.get("pivot_r1") and tech["pivot_r1"] > price:
        t1 = tech["pivot_r1"]
        t2 = tech["pivot_r2"] if tech.get("pivot_r2") and tech["pivot_r2"] > t1 else round(price * 1.22, 1)
        return t1, t2
    # Fallback: sector-score based
    sector_boost = SECTOR_TAILWINDS.get(sector, {}).get("score", 0)
    base_t1 = 0.12 + (sector_boost * 0.02) + ((score - 70) * 0.001)
    base_t2 = 0.22 + (sector_boost * 0.03) + ((score - 70) * 0.002)
    t1 = round(price * (1 + max(0.08, min(0.20, base_t1))), 1)
    t2 = round(price * (1 + max(0.15, min(0.35, base_t2))), 1)
    return t1, t2

def calculate_rr(entry, target, sl):
    """Calculate Risk/Reward ratio."""
    risk   = abs(entry - sl)
    reward = abs(target - entry)
    if risk == 0:
        return 0
    return round(reward / risk, 2)

def build_rationale(stock, price_data, news_sentiment_map):
    """Build 3-point rationale for the trade."""
    points = []
    sector = stock.get("sector", "")
    score  = stock.get("score", 0)
    chg    = price_data.get("change_pct", 0) if price_data else 0
    vol_s  = price_data.get("vol_surge", 1) if price_data else 1

    # Point 1: Fundamental
    roe = stock.get("roe_base", 0)
    if roe > 20:
        points.append(f"Strong ROE {roe}% — capital efficient business with wide moat")
    elif roe > 10:
        points.append(f"Healthy ROE {roe}% — improving profitability trajectory")
    else:
        points.append(f"Turnaround story — watch next quarter for ROE recovery")

    # Point 2: Technical / Momentum
    if chg > 1.5 and vol_s > 1.5:
        points.append(f"Volume surge {vol_s}x avg + price up {chg:.1f}% → institutional accumulation signal")
    elif chg > 0.5:
        points.append(f"Positive price action +{chg:.1f}% today; above 200DMA — bullish structure intact")
    elif vol_s > 1.8:
        points.append(f"Unusual volume {vol_s}x avg — smart money entering at current levels")
    else:
        points.append(f"Consolidation phase; accumulate in buy zone for swing trade setup")

    # Point 3: Sector tailwind
    tw = SECTOR_TAILWINDS.get(sector, {})
    if tw:
        points.append(f"Sector: {tw.get('reason', 'Sector in focus')}")

    # Point 4: News boost (if available)
    stock_name = stock.get("name", "")
    if stock_name in news_sentiment_map:
        ns = news_sentiment_map[stock_name]
        if ns["score"] > 0:
            points.append(f"Positive news flow: {ns['headlines'][0][:60]}...")
        elif ns["score"] < 0:
            points[0] = f"⚠️ Negative news: {ns['headlines'][0][:60]}... — trade with caution"

    return points[:3]

def generate_signal(stock, news_sentiment_map, technical_map=None):
    """Generate a complete trade signal for one stock."""
    price_data = {
        "price":      stock.get("price", 0),
        "change_pct": stock.get("change_pct", 0),
        "vol_surge":  stock.get("vol_surge", 1),
    }

    price  = price_data["price"]
    signal = stock.get("signal", "WATCH")
    score  = stock.get("score", 50)
    sector = stock.get("sector", "")
    name   = stock.get("name", "")

    if not price or price == "--":
        return None

    # Pull IIFL-style levels from technical agent if available
    tech = (technical_map or {}).get(name)

    entry_low, entry_high = calculate_entry_zone(price, signal, tech)
    t1, t2 = calculate_targets(price, sector, score, tech)

    # Stop loss: prefer swing low from technical agent
    if tech and tech.get("stop_loss") and tech["stop_loss"] < price:
        sl        = tech["stop_loss"]
        sl_method = tech.get("sl_method", "Technical")
    else:
        sl        = round(price * 0.92, 1)
        sl_method = "8% Fixed"

    rr1 = calculate_rr(price, t1, sl)
    rr2 = calculate_rr(price, t2, sl)
    rationale = build_rationale(stock, price_data, news_sentiment_map)

    # Confidence
    if score >= 88 and rr1 >= 1.5:   confidence = "HIGH"
    elif score >= 75 and rr1 >= 1.2: confidence = "MEDIUM"
    else:                             confidence = "LOW"

    sector_tw = SECTOR_TAILWINDS.get(sector, {})

    return {
        "name":         stock["name"],
        "sector":       sector,
        "score":        score,
        "signal":       signal,
        "cmp":          price,
        "change_pct":   price_data["change_pct"],
        "entry_low":    entry_low,
        "entry_high":   entry_high,
        "target1":      t1,
        "target2":      t2,
        "stop_loss":    sl,
        "sl_method":    sl_method,
        "rr_t1":        rr1,
        "rr_t2":        rr2,
        "confidence":   confidence,
        "rationale":    rationale,
        "sector_view":  sector_tw.get("reason", ""),
        "sector_score": sector_tw.get("score", 0),
        "hold_period":  "2-4 weeks" if signal == "BUY" else "1-2 weeks" if signal == "STRONG BUY" else "Monitor",
        # IIFL technical extras (if available)
        "pivot_pp":     tech.get("pivot_pp")  if tech else None,
        "pivot_r1":     tech.get("pivot_r1")  if tech else None,
        "pivot_r2":     tech.get("pivot_r2")  if tech else None,
        "pivot_s1":     tech.get("pivot_s1")  if tech else None,
        "atr":          tech.get("atr")       if tech else None,
        "atr_pct":      tech.get("atr_pct")   if tech else None,
        "swing_low":    tech.get("swing_low") if tech else None,
        "chasing":      tech.get("chasing", False) if tech else False,
        "rsi":          tech.get("rsi")       if tech else None,
        "generated_at": datetime.now().strftime("%d %b %H:%M"),
    }

def run(shared_state):
    """Main agent — generates trade signals from scanner results."""
    scanner_results = shared_state.get("scanner_results", [])
    news_sentiment  = shared_state.get("stock_sentiment_map", {})
    technical_map   = shared_state.get("technical_data", {})   # NEW

    if not scanner_results:
        log.warning("TradeSignal: No scanner results available yet")
        shared_state["trade_signals"]     = []
        shared_state["signals_last_run"]  = datetime.now().strftime("%d %b %H:%M:%S")
        return []

    has_tech = len(technical_map) > 0
    log.info("⚡ TradeSignal: Generating signals for %d stocks (IIFL tech=%s)...",
             len(scanner_results), "✅" if has_tech else "⏳")

    signals = []
    for stock in scanner_results:
        sig = generate_signal(stock, news_sentiment, technical_map)   # NEW
        if sig and sig["signal"] in ("STRONG BUY", "BUY", "WATCH"):
            signals.append(sig)

    # Sort by score
    signals.sort(key=lambda x: -x["score"])

    # Flag actionable ones (RR ≥ 1.2 and score ≥ 78)
    actionable = [s for s in signals if s["rr_t1"] >= 1.2 and s["score"] >= 78]

    log.info("✅ TradeSignal: %d signals generated, %d actionable", len(signals), len(actionable))

    shared_state["trade_signals"]      = signals
    shared_state["actionable_signals"] = actionable
    shared_state["signals_last_run"]   = datetime.now().strftime("%d %b %H:%M:%S")
    return signals
