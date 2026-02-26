"""
AGENT 4 — COMMODITY & CRYPTO AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Track Gold, Silver, Crude Oil, Nat Gas,
          BTC, ETH, SOL in real-time.
          Map commodity moves to stock impacts.
          Flag breakouts and key level breaks.
Runs    : Every 15 minutes
Reports : Telegram (on breakout) + Dashboard
"""

import requests
import logging
from datetime import datetime

log = logging.getLogger("CommodityCrypto")

# ── SYMBOLS ──────────────────────────────────────────────────────────────────
COMMODITIES = [
    {"name": "GOLD",      "symbol": "GC=F",    "unit": "/10g INR",  "icon": "🥇", "type": "commodity"},
    {"name": "SILVER",    "symbol": "SI=F",    "unit": "/kg INR",   "icon": "🥈", "type": "commodity"},
    {"name": "CRUDE OIL", "symbol": "CL=F",    "unit": "/bbl USD",  "icon": "🛢️", "type": "commodity"},
    {"name": "NAT GAS",   "symbol": "NG=F",    "unit": "/mmBtu",    "icon": "⛽",  "type": "commodity"},
    {"name": "COPPER",    "symbol": "HG=F",    "unit": "/lb USD",   "icon": "🔶", "type": "commodity"},
    {"name": "BTC/INR",   "symbol": "BTC-INR", "unit": "INR",       "icon": "₿",  "type": "crypto"},
    {"name": "ETH/INR",   "symbol": "ETH-INR", "unit": "INR",       "icon": "Ξ",  "type": "crypto"},
    {"name": "SOL/INR",   "symbol": "SOL-INR", "unit": "INR",       "icon": "◎",  "type": "crypto"},
    {"name": "USD/INR",   "symbol": "INR=X",   "unit": "INR",       "icon": "💱", "type": "forex"},
    {"name": "EUR/INR",   "symbol": "EURINR=X","unit": "INR",       "icon": "€",  "type": "forex"},
]

# ── STOCK IMPACT MAP ─────────────────────────────────────────────────────────
COMMODITY_STOCK_IMPACT = {
    "GOLD": {
        "positive": ["MUTHOOT", "MANAPPURAM", "IIFL FINANCE"],
        "negative": [],
        "logic": "Gold ▲ → Gold loan AUM rises → NBFCs benefit"
    },
    "CRUDE OIL": {
        "positive": ["ONGC", "OIL INDIA", "HPCL", "BPCL"],
        "negative": ["INDIGO", "ASIAN PAINTS", "MRF", "APOLLO TYRES"],
        "logic": "Crude ▲ → upstream wins, downstream loses; Crude ▼ = inverse"
    },
    "SILVER": {
        "positive": ["HINDUSTAN ZINC"],
        "negative": [],
        "logic": "Silver ▲ → industrial demand; EV/solar sector benefits"
    },
    "COPPER": {
        "positive": ["HINDUSTAN COPPER", "STERLITE"],
        "negative": [],
        "logic": "Copper ▲ = global growth signal; infra stocks benefit"
    },
    "USD/INR": {
        "positive": ["TCS", "INFOSYS", "WIPRO", "HCL TECH"],
        "negative": ["INDIGO", "TATA MOTORS", "BAJAJ AUTO"],
        "logic": "Weak INR → IT exporters win (USD revenues); importers lose"
    },
    "BTC/INR": {
        "positive": [],
        "negative": [],
        "logic": "Crypto rally = risk-on; correlates with Nifty IT 0.6"
    },
}

# ── KEY LEVELS (update monthly) ───────────────────────────────────────────────
KEY_LEVELS = {
    "GOLD":      {"support": 84000, "resistance": 90000, "trend": "BULLISH"},
    "CRUDE OIL": {"support": 65,    "resistance": 78,    "trend": "BEARISH"},
    "BTC/INR":   {"support": 7200000, "resistance": 9000000, "trend": "BULLISH"},
    "USD/INR":   {"support": 84.50,  "resistance": 87.50,  "trend": "NEUTRAL"},
}

def fetch_price(symbol):
    """Fetch price from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        r   = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
        d   = r.json()
        meta = d["chart"]["result"][0]["meta"]
        price    = meta.get("regularMarketPrice", 0)
        prev     = meta.get("chartPreviousClose", price) or price
        chg_pct  = round(((price - prev) / prev) * 100, 2) if prev else 0
        hi       = meta.get("regularMarketDayHigh", price)
        lo       = meta.get("regularMarketDayLow", price)
        return {"price": round(price, 4), "prev": round(prev, 4),
                "change_pct": chg_pct, "high": hi, "low": lo}
    except Exception as e:
        log.debug(f"Price fetch failed {symbol}: {e}")
        return None

def check_level_break(name, price, chg_pct):
    """Check if price is breaking key levels."""
    levels = KEY_LEVELS.get(name, {})
    alerts = []

    if levels:
        sup = levels.get("support", 0)
        res = levels.get("resistance", 0)

        if price > res * 0.995 and chg_pct > 0.5:
            alerts.append(f"🚨 BREAKOUT: {name} testing resistance {res} — watch for breakout!")
        elif price < sup * 1.005 and chg_pct < -0.5:
            alerts.append(f"⚠️ BREAKDOWN: {name} near support {sup} — be cautious!")

    if abs(chg_pct) >= 2.0:
        direction = "surging" if chg_pct > 0 else "falling"
        alerts.append(f"📊 MOVE: {name} {direction} {abs(chg_pct):.1f}% — check stock impacts")

    return alerts

def get_stock_impact(name, chg_pct):
    """Determine which stocks are impacted by commodity move."""
    impact_map = COMMODITY_STOCK_IMPACT.get(name, {})
    if not impact_map:
        return []

    impacts = []
    if chg_pct > 0.5:
        for stk in impact_map.get("positive", []):
            impacts.append({"stock": stk, "direction": "positive", "reason": impact_map["logic"]})
        for stk in impact_map.get("negative", []):
            impacts.append({"stock": stk, "direction": "negative", "reason": impact_map["logic"]})
    elif chg_pct < -0.5:
        for stk in impact_map.get("negative", []):
            impacts.append({"stock": stk, "direction": "positive", "reason": impact_map["logic"]+" (inverse)"})
        for stk in impact_map.get("positive", []):
            impacts.append({"stock": stk, "direction": "negative", "reason": impact_map["logic"]+" (inverse)"})

    return impacts

def get_signal(chg_pct, trend):
    """Simple directional signal."""
    if trend == "BULLISH" and chg_pct > 0:   return "BULLISH ▲"
    if trend == "BULLISH" and chg_pct < -1:  return "PULLBACK ▽"
    if trend == "BEARISH" and chg_pct < 0:   return "BEARISH ▼"
    if trend == "BEARISH" and chg_pct > 1:   return "BOUNCE △"
    return "NEUTRAL →"

def run(shared_state):
    """Main agent — fetch all commodities + crypto."""
    log.info("🥇 CommodityCrypto: Fetching %d instruments...", len(COMMODITIES))

    results  = []
    alerts   = []

    for item in COMMODITIES:
        data = fetch_price(item["symbol"])
        if data:
            levels = KEY_LEVELS.get(item["name"], {})
            trend  = levels.get("trend", "NEUTRAL")
            signal = get_signal(data["change_pct"], trend)
            lvl_alerts = check_level_break(item["name"], data["price"], data["change_pct"])
            stk_impacts = get_stock_impact(item["name"], data["change_pct"])
            alerts.extend(lvl_alerts)

            results.append({
                **item, **data,
                "trend":          trend,
                "signal":         signal,
                "support":        levels.get("support", "--"),
                "resistance":     levels.get("resistance", "--"),
                "stock_impacts":  stk_impacts,
                "updated":        datetime.now().strftime("%H:%M:%S"),
            })
            log.info("  %s %s: %s (%+.2f%%)", item["icon"], item["name"],
                     data["price"], data["change_pct"])

    # Compute commodity sentiment for macro context
    commodity_sentiment = "NEUTRAL"
    gold  = next((r for r in results if r["name"] == "GOLD"), None)
    crude = next((r for r in results if r["name"] == "CRUDE OIL"), None)
    btc   = next((r for r in results if r["name"] == "BTC/INR"), None)

    if gold and crude and btc:
        gold_bull  = gold["change_pct"] > 0
        crude_bear = crude["change_pct"] < 0
        btc_bull   = btc["change_pct"] > 1

        if gold_bull and crude_bear:
            commodity_sentiment = "MACRO BULLISH (Gold ▲ + Crude ▼ = India positive)"
        elif not gold_bull and crude["change_pct"] > 2:
            commodity_sentiment = "MACRO CAUTION (Crude surging — inflation risk)"
        elif btc_bull and gold_bull:
            commodity_sentiment = "RISK-ON (BTC + Gold both up — strong sentiment)"

    log.info("✅ CommodityCrypto: %d instruments fetched. %d alerts. Macro: %s",
             len(results), len(alerts), commodity_sentiment)

    shared_state["commodity_results"]     = results
    shared_state["commodity_alerts"]      = alerts
    shared_state["commodity_sentiment"]   = commodity_sentiment
    shared_state["commodity_last_run"]    = datetime.now().strftime("%d %b %H:%M:%S")
    return results
