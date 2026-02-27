"""
AGENT 5 — INSTITUTIONAL FLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Track FII/DII daily flows, bulk deals, block deals.
          Institutional money direction is the strongest leading
          indicator in Indian markets — never fight FII flow.
Runs    : Every 15 minutes (data refreshes daily, cached within day)
Cost    : Zero — NSE public data + web scraping
Reports : Feeds claude_intelligence + trade_signal conviction gate R5/R22
"""

import requests
import re
import json
import logging
from datetime import datetime, date

log = logging.getLogger("InstitutionalFlow")

# ── NSE HEADERS (needed to avoid 401/403) ────────────────────────────────────
NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}

# Cache: FII/DII data is daily — cache within the same trading day
_cache          = {}
_cache_date     = None

# ── FII/DII FLOW ──────────────────────────────────────────────────────────────
def fetch_fii_dii():
    """Fetch today's FII and DII net flow in ₹ Crore."""
    global _cache, _cache_date
    today = date.today()

    if _cache_date == today and _cache.get("fii_net_crore") is not None:
        log.debug("InstitutionalFlow: Using cached FII/DII data")
        return _cache

    result = {"fii_net_crore": None, "dii_net_crore": None,
              "fii_buy": None, "fii_sell": None,
              "dii_buy": None, "dii_sell": None,
              "source": "unavailable"}

    # Method 1: NSE API
    try:
        session = requests.Session()
        # Establish session first
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
        r = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers=NSE_HEADERS, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            # Parse the response (NSE format varies)
            for item in data:
                cat = item.get("category", "").upper()
                if "FII" in cat or "FPI" in cat:
                    result["fii_buy"]  = float(str(item.get("buyCF", 0)).replace(",",""))
                    result["fii_sell"] = float(str(item.get("sellCF", 0)).replace(",",""))
                    result["fii_net_crore"] = round(result["fii_buy"] - result["fii_sell"], 2)
                elif "DII" in cat:
                    result["dii_buy"]  = float(str(item.get("buyCF", 0)).replace(",",""))
                    result["dii_sell"] = float(str(item.get("sellCF", 0)).replace(",",""))
                    result["dii_net_crore"] = round(result["dii_buy"] - result["dii_sell"], 2)
            if result["fii_net_crore"] is not None:
                result["source"] = "NSE"
                log.info("  FII/DII: FII ₹%.0f Cr | DII ₹%.0f Cr",
                         result["fii_net_crore"] or 0, result["dii_net_crore"] or 0)
    except Exception as e:
        log.debug("NSE FII/DII fetch failed: %s", e)

    # Method 2: Fallback — try Moneycontrol scrape for FII/DII summary
    if result["fii_net_crore"] is None:
        try:
            r = requests.get(
                "https://www.moneycontrol.com/stocks/fii_dii_activity/",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=8
            )
            text = r.text
            # Try to extract FII net value
            fii_match = re.search(r'FII.*?Net.*?([+-]?\d[\d,]*\.?\d*)', text, re.DOTALL)
            if fii_match:
                val = float(fii_match.group(1).replace(",", ""))
                result["fii_net_crore"] = val
                result["source"]        = "MC-estimate"
        except Exception:
            pass

    # If still no data → use neutral placeholder (system continues without it)
    if result["fii_net_crore"] is None:
        result["fii_net_crore"] = 0
        result["dii_net_crore"] = 0
        result["source"]        = "unavailable"
        log.warning("  InstitutionalFlow: FII/DII data unavailable today")

    _cache      = result
    _cache_date = today
    return result

# ── BULK & BLOCK DEALS ────────────────────────────────────────────────────────
def fetch_bulk_deals():
    """Fetch today's bulk and block deals from NSE."""
    deals = []
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)

        # Bulk deals
        r = session.get(
            "https://www.nseindia.com/api/bulk-deals",
            headers=NSE_HEADERS, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            for item in items[:10]:
                symbol = item.get("symbol", "")
                qty    = item.get("quantityTraded", 0)
                price  = item.get("tradePrice", 0)
                side   = "BUY" if "buy" in str(item.get("buySell","")).lower() else "SELL"
                deals.append({
                    "symbol": symbol,
                    "side":   side,
                    "qty":    qty,
                    "price":  price,
                    "type":   "BULK",
                    "client": item.get("clientName", ""),
                })
    except Exception as e:
        log.debug("Bulk deals fetch failed: %s", e)

    # Block deals (if available)
    try:
        session2 = requests.Session()
        session2.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
        r2 = session2.get(
            "https://www.nseindia.com/api/block-deal",
            headers=NSE_HEADERS, timeout=10
        )
        if r2.status_code == 200:
            data2 = r2.json()
            items2 = data2 if isinstance(data2, list) else data2.get("data", [])
            for item in items2[:5]:
                deals.append({
                    "symbol": item.get("symbol", ""),
                    "side":   "BUY" if "buy" in str(item.get("buySell","")).lower() else "SELL",
                    "qty":    item.get("quantityTraded", 0),
                    "price":  item.get("tradePrice", 0),
                    "type":   "BLOCK",
                    "client": item.get("clientName", ""),
                })
    except Exception:
        pass

    log.info("  Bulk/Block deals: %d found", len(deals))
    return deals

# ── DELIVERY % TRACKING ───────────────────────────────────────────────────────
def fetch_delivery_data(watchlist_symbols: list) -> dict:
    """
    Fetch delivery % for watchlist stocks from NSE.
    Delivery % > 60% on high volume = institutional accumulation.
    Delivery % < 25% on high volume = pure speculative/intraday play.

    Returns: {SYMBOL: {delivery_pct, delivery_qty, traded_qty, interpretation}}
    """
    delivery_map = {}
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)

        r = session.get(
            "https://www.nseindia.com/api/deliveryTradeDetails",
            headers=NSE_HEADERS, timeout=10
        )
        if r.status_code == 200:
            data  = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            for item in items:
                sym = item.get("symbol", "").upper()
                if not sym:
                    continue
                try:
                    delivery_qty = float(str(item.get("deliveryQuantity", 0)).replace(",", ""))
                    traded_qty   = float(str(item.get("tradedQuantity",   0)).replace(",", ""))
                    delivery_pct = round((delivery_qty / traded_qty) * 100, 1) if traded_qty else 0.0
                except (ValueError, ZeroDivisionError):
                    delivery_pct = 0.0
                    delivery_qty = 0
                    traded_qty   = 0

                if delivery_pct >= 60:
                    interpretation = "INSTITUTIONAL_ACCUMULATION"
                elif delivery_pct >= 45:
                    interpretation = "MIXED_HOLDING"
                elif delivery_pct >= 25:
                    interpretation = "MOSTLY_INTRADAY"
                else:
                    interpretation = "SPECULATIVE"

                delivery_map[sym] = {
                    "delivery_pct":    delivery_pct,
                    "delivery_qty":    int(delivery_qty),
                    "traded_qty":      int(traded_qty),
                    "interpretation":  interpretation,
                    "institutional":   delivery_pct >= 60,
                }

            log.info("  Delivery data: %d stocks fetched", len(delivery_map))
        else:
            log.debug("  Delivery API returned %d", r.status_code)
    except Exception as e:
        log.debug("Delivery fetch failed: %s", e)

    return delivery_map

# ── SECTOR FLOW INFERENCE ─────────────────────────────────────────────────────
def infer_sector_flow(fii_net, bulk_deals, sector_map):
    """
    Infer which sectors FIIs are buying/selling based on:
    1. Bulk/block deal patterns
    2. Overall FII flow direction + sector performance
    """
    sector_sentiment = {}

    for deal in bulk_deals:
        sym = deal["symbol"]
        sec = sector_map.get(sym, "Unknown")
        if sec not in sector_sentiment:
            sector_sentiment[sec] = {"buy_deals": 0, "sell_deals": 0}
        if deal["side"] == "BUY":
            sector_sentiment[sec]["buy_deals"] += 1
        else:
            sector_sentiment[sec]["sell_deals"] += 1

    # Infer bias
    for sec, data in sector_sentiment.items():
        total  = data["buy_deals"] + data["sell_deals"]
        if total > 0:
            buy_ratio = data["buy_deals"] / total
            data["bias"]     = "BUYING" if buy_ratio > 0.6 else "SELLING" if buy_ratio < 0.4 else "NEUTRAL"
            data["strength"] = round(buy_ratio, 2)

    return sector_sentiment

# ── MAIN AGENT ────────────────────────────────────────────────────────────────
def run(shared_state):
    """Main agent — fetch and analyze institutional flow."""
    log.info("🏦 InstitutionalFlow: Fetching FII/DII + deals...")

    fii_dii     = fetch_fii_dii()
    bulk_deals  = fetch_bulk_deals()

    # Build quick sector map from scanner
    sector_map = {}
    watchlist_syms = []
    for s in shared_state.get("full_scan", []):
        raw_sym = s.get("sym", "")
        clean   = raw_sym.replace(".NS", "").replace(".BO", "")
        sector_map[clean] = s.get("sector", "Unknown")
        watchlist_syms.append(clean)

    sector_flow   = infer_sector_flow(fii_dii.get("fii_net_crore", 0), bulk_deals, sector_map)
    delivery_data = fetch_delivery_data(watchlist_syms)

    # Identify institutional accumulation stocks (high delivery + scanner watchlist)
    inst_accumulation = {
        sym: d for sym, d in delivery_data.items()
        if d["institutional"] and sym in sector_map
    }

    # Overall FII signal (R22: >₹2000Cr buy = strong bullish)
    fii_net  = fii_dii.get("fii_net_crore", 0) or 0
    dii_net  = fii_dii.get("dii_net_crore", 0) or 0

    if fii_net > 2000:
        fii_signal = "STRONG_BUYING"
    elif fii_net > 500:
        fii_signal = "BUYING"
    elif fii_net < -2000:
        fii_signal = "STRONG_SELLING"
    elif fii_net < -500:
        fii_signal = "SELLING"
    else:
        fii_signal = "NEUTRAL"

    # Counter-balanced by DII (DIIs often absorb FII selling)
    net_combined = fii_net + dii_net
    market_flow  = "BULLISH" if net_combined > 0 else "BEARISH" if net_combined < 0 else "NEUTRAL"

    result = {
        "fii_net_crore":       fii_net,
        "dii_net_crore":       dii_net,
        "fii_buy":             fii_dii.get("fii_buy"),
        "fii_sell":            fii_dii.get("fii_sell"),
        "fii_signal":          fii_signal,
        "market_flow":         market_flow,
        "bulk_deals":          bulk_deals[:8],
        "sector_flow":         sector_flow,
        "delivery_data":       delivery_data,
        "inst_accumulation":   inst_accumulation,
        "data_source":         fii_dii.get("source", "unavailable"),
        "fii_gate_pass":       fii_net >= 0,  # Gate R5: FII not net selling
        "last_run":            datetime.now().strftime("%d %b %H:%M:%S"),
    }

    shared_state["institutional_flow"]      = result
    shared_state["institutional_last_run"]  = result["last_run"]
    shared_state["delivery_data"]           = delivery_data

    accum_names = list(inst_accumulation.keys())[:5]
    log.info("✅ InstitutionalFlow: FII ₹%.0f Cr | Signal: %s | Deals: %d | "
             "Delivery tracked: %d stocks | Accumulation: %s",
             fii_net, fii_signal, len(bulk_deals),
             len(delivery_data), accum_names or "none")
    return result
