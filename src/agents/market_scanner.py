"""
AGENT 1 — MARKET SCANNER
━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Scan Nifty 500 universe, score every stock,
          return top 10 ranked by composite score.
Runs    : Every 15 minutes during market hours
Reports : Telegram + Dashboard
"""

import requests
import time
import logging
from datetime import datetime

log = logging.getLogger("MarketScanner")

# ── NIFTY 500 UNIVERSE (top 60 liquid stocks for scanning) ──────────────────
UNIVERSE = [
    # Banking & Finance
    {"name":"HDFC BANK",    "sym":"HDFCBANK.NS",   "sector":"Banking",    "pe_avg":20, "roe_base":17},
    {"name":"ICICI BANK",   "sym":"ICICIBANK.NS",  "sector":"Banking",    "pe_avg":18, "roe_base":18},
    {"name":"KOTAK BANK",   "sym":"KOTAKBANK.NS",  "sector":"Banking",    "pe_avg":22, "roe_base":14},
    {"name":"AXIS BANK",    "sym":"AXISBANK.NS",   "sector":"Banking",    "pe_avg":14, "roe_base":16},
    {"name":"SBI",          "sym":"SBIN.NS",       "sector":"Banking",    "pe_avg":9,  "roe_base":18},
    {"name":"BAJAJ FIN",    "sym":"BAJFINANCE.NS", "sector":"NBFC",       "pe_avg":28, "roe_base":24},
    {"name":"MUTHOOT",      "sym":"MUTHOOTFIN.NS", "sector":"Gold Loan",  "pe_avg":16, "roe_base":27},
    {"name":"CHOLA FIN",    "sym":"CHOLAFIN.NS",   "sector":"NBFC",       "pe_avg":24, "roe_base":19},
    # Telecom
    {"name":"AIRTEL",       "sym":"BHARTIARTL.NS", "sector":"Telecom",    "pe_avg":28, "roe_base":18},
    {"name":"AIRTEL HEX",   "sym":"BHARTIHEXA.NS", "sector":"Telecom",    "pe_avg":40, "roe_base":12},
    # IT
    {"name":"TCS",          "sym":"TCS.NS",        "sector":"IT",         "pe_avg":28, "roe_base":48},
    {"name":"INFOSYS",      "sym":"INFY.NS",       "sector":"IT",         "pe_avg":24, "roe_base":32},
    {"name":"HCL TECH",     "sym":"HCLTECH.NS",    "sector":"IT",         "pe_avg":22, "roe_base":24},
    {"name":"WIPRO",        "sym":"WIPRO.NS",      "sector":"IT",         "pe_avg":20, "roe_base":16},
    # Defence
    {"name":"BEL",          "sym":"BEL.NS",        "sector":"Defence",    "pe_avg":38, "roe_base":23},
    {"name":"HAL",          "sym":"HAL.NS",        "sector":"Defence",    "pe_avg":32, "roe_base":28},
    {"name":"MAZAGON",      "sym":"MAZDOCK.NS",    "sector":"Defence",    "pe_avg":36, "roe_base":22},
    # Auto
    {"name":"MARUTI",       "sym":"MARUTI.NS",     "sector":"Auto",       "pe_avg":28, "roe_base":17},
    {"name":"TATA MOTORS",  "sym":"TATAMOTORS.NS", "sector":"Auto",       "pe_avg":8,  "roe_base":22},
    {"name":"HERO MOTO",    "sym":"HEROMOTOCO.NS", "sector":"Auto",       "pe_avg":18, "roe_base":26},
    {"name":"TVS MOTOR",    "sym":"TVSMOTOR.NS",   "sector":"Auto",       "pe_avg":42, "roe_base":28},
    {"name":"EICHER",       "sym":"EICHERMOT.NS",  "sector":"Auto",       "pe_avg":30, "roe_base":24},
    {"name":"ASHOK LEY",    "sym":"ASHOKLEY.NS",   "sector":"Auto",       "pe_avg":22, "roe_base":21},
    # Pharma
    {"name":"SUN PHARMA",   "sym":"SUNPHARMA.NS",  "sector":"Pharma",     "pe_avg":34, "roe_base":20},
    {"name":"DIVIS LAB",    "sym":"DIVISLAB.NS",   "sector":"Pharma",     "pe_avg":38, "roe_base":22},
    {"name":"TORRENT PH",   "sym":"TORNTPHARM.NS", "sector":"Pharma",     "pe_avg":44, "roe_base":19},
    {"name":"DR REDDY",     "sym":"DRREDDY.NS",    "sector":"Pharma",     "pe_avg":20, "roe_base":17},
    # FMCG
    {"name":"HINDUSTAN UNI","sym":"HINDUNILVR.NS", "sector":"FMCG",       "pe_avg":55, "roe_base":22},
    {"name":"ITC",          "sym":"ITC.NS",        "sector":"FMCG",       "pe_avg":26, "roe_base":28},
    {"name":"NESTLE",       "sym":"NESTLEIND.NS",  "sector":"FMCG",       "pe_avg":70, "roe_base":100},
    # Energy
    {"name":"RELIANCE",     "sym":"RELIANCE.NS",   "sector":"Energy",     "pe_avg":24, "roe_base":12},
    {"name":"ONGC",         "sym":"ONGC.NS",       "sector":"Energy",     "pe_avg":8,  "roe_base":14},
    {"name":"COAL INDIA",   "sym":"COALINDIA.NS",  "sector":"Energy",     "pe_avg":8,  "roe_base":42},
    # Food Tech / New Age
    {"name":"ZOMATO",       "sym":"ZOMATO.NS",     "sector":"Food Tech",  "pe_avg":90, "roe_base":4},
    {"name":"PAYTM",        "sym":"PAYTM.NS",      "sector":"Fintech",    "pe_avg":0,  "roe_base":-8},
    # Aviation
    {"name":"INDIGO",       "sym":"INDIGO.NS",     "sector":"Aviation",   "pe_avg":14, "roe_base":82},
    # Infra / Power
    {"name":"L&T",          "sym":"LT.NS",         "sector":"Infra",      "pe_avg":26, "roe_base":14},
    {"name":"ADANI PORTS",  "sym":"ADANIPORTS.NS", "sector":"Infra",      "pe_avg":24, "roe_base":16},
    {"name":"NTPC",         "sym":"NTPC.NS",       "sector":"Power",      "pe_avg":16, "roe_base":12},
    {"name":"POWER GRID",   "sym":"POWERGRID.NS",  "sector":"Power",      "pe_avg":18, "roe_base":20},
    # Insurance
    {"name":"SBI LIFE",     "sym":"SBILIFE.NS",    "sector":"Insurance",  "pe_avg":62, "roe_base":16},
    {"name":"HDFC LIFE",    "sym":"HDFCLIFE.NS",   "sector":"Insurance",  "pe_avg":78, "roe_base":12},
    # Cement
    {"name":"ULTRATECH",    "sym":"ULTRACEMCO.NS", "sector":"Cement",     "pe_avg":36, "roe_base":14},
    {"name":"SHREE CEM",    "sym":"SHREECEM.NS",   "sector":"Cement",     "pe_avg":40, "roe_base":12},
    # Metals
    {"name":"TATA STEEL",   "sym":"TATASTEEL.NS",  "sector":"Metals",     "pe_avg":12, "roe_base":8},
    {"name":"HINDALCO",     "sym":"HINDALCO.NS",   "sector":"Metals",     "pe_avg":12, "roe_base":10},
    {"name":"JSW STEEL",    "sym":"JSWSTEEL.NS",   "sector":"Metals",     "pe_avg":14, "roe_base":14},
    # Real Estate
    {"name":"DLF",          "sym":"DLF.NS",        "sector":"Realty",     "pe_avg":50, "roe_base":8},
    {"name":"GODREJ PROP",  "sym":"GODREJPROP.NS", "sector":"Realty",     "pe_avg":60, "roe_base":10},
    # Healthcare
    {"name":"MAX HEALTH",   "sym":"MAXHEALTH.NS",  "sector":"Healthcare", "pe_avg":60, "roe_base":14},
    {"name":"APOLLO HOSP",  "sym":"APOLLOHOSP.NS", "sector":"Healthcare", "pe_avg":72, "roe_base":16},
]

def fetch_price(symbol):
    """Fetch live price + momentum from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        r   = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
        d   = r.json()
        meta = d["chart"]["result"][0]["meta"]
        price     = meta.get("regularMarketPrice", 0)
        prev      = meta.get("chartPreviousClose", price) or price
        hi        = meta.get("regularMarketDayHigh", price)
        lo        = meta.get("regularMarketDayLow", price)
        vol       = meta.get("regularMarketVolume", 0)
        avg_vol   = meta.get("averageDailyVolume10Day", vol) or vol
        chg_pct   = round(((price - prev) / prev) * 100, 2) if prev else 0
        vol_surge = round((vol / avg_vol), 2) if avg_vol else 1
        rng_pos   = round(((price - lo) / (hi - lo)) * 100, 1) if (hi - lo) > 0 else 50
        return {
            "price": round(price, 2), "prev": round(prev, 2),
            "change_pct": chg_pct, "vol_surge": vol_surge,
            "range_pos": rng_pos, "high": hi, "low": lo, "volume": vol
        }
    except Exception as e:
        log.debug(f"Price fetch failed {symbol}: {e}")
        return None

def score_stock(stock, price_data):
    """
    Composite scoring: 40% Fundamental + 30% Technical + 20% Momentum + 10% Risk
    Returns score 0-100
    """
    if not price_data:
        return 50, "WATCH"

    chg     = price_data["change_pct"]
    vol_s   = price_data["vol_surge"]
    rng_p   = price_data["range_pos"]
    roe     = stock["roe_base"]

    # ── FUNDAMENTAL SCORE (40 pts) ──────────────────
    f_score = 0
    if roe > 25:        f_score += 20
    elif roe > 15:      f_score += 15
    elif roe > 8:       f_score += 8
    elif roe > 0:       f_score += 4

    pe_ratio = stock["pe_avg"]
    if 0 < pe_ratio < 20:   f_score += 20
    elif pe_ratio < 35:     f_score += 14
    elif pe_ratio < 55:     f_score += 8
    else:                   f_score += 3

    # ── TECHNICAL SCORE (30 pts) ────────────────────
    t_score = 0
    if 40 <= rng_p <= 70:   t_score += 15   # sweet spot RSI proxy
    elif rng_p < 30:        t_score += 10   # oversold bounce
    elif rng_p > 80:        t_score += 5    # overbought — careful

    if chg > 1.5:           t_score += 15
    elif chg > 0.5:         t_score += 12
    elif chg > 0:           t_score += 8
    elif chg > -1:          t_score += 4
    else:                   t_score += 0

    # ── MOMENTUM SCORE (20 pts) ─────────────────────
    m_score = 0
    if vol_s > 2.0:         m_score += 20   # massive volume surge
    elif vol_s > 1.5:       m_score += 15
    elif vol_s > 1.2:       m_score += 10
    elif vol_s > 1.0:       m_score += 6
    else:                   m_score += 2

    # ── DELIVERY BONUS (up to +8 pts from institutional accumulation) ──
    delivery_pct = stock.get("delivery_pct", 0)
    if delivery_pct >= 60 and vol_s >= 1.5:
        m_score = min(20, m_score + 8)   # institutional accumulation: high delivery + high vol
    elif delivery_pct >= 45 and vol_s >= 1.2:
        m_score = min(20, m_score + 4)   # moderate institutional interest
    elif delivery_pct > 0 and delivery_pct < 25 and vol_s > 2.0:
        m_score = max(0, m_score - 4)    # high vol but speculative — penalise

    # ── RISK SCORE (10 pts) ─────────────────────────
    r_score = 10 if chg > -2 else 5 if chg > -4 else 2

    total = min(100, f_score + t_score + m_score + r_score)

    # Signal
    if total >= 88:   sig = "STRONG BUY"
    elif total >= 78: sig = "BUY"
    elif total >= 65: sig = "WATCH"
    elif total >= 50: sig = "HOLD"
    else:             sig = "AVOID"

    return total, sig

def fetch_advance_decline():
    """
    Fetch Advance-Decline breadth from NSE allIndices API.
    Returns: {advances, declines, unchanged, ad_ratio, total, breadth_signal}
    """
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com",
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}, timeout=6)
        r = session.get(
            "https://www.nseindia.com/api/allIndices",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                     "Referer": "https://www.nseindia.com/"},
            timeout=10
        )
        if r.status_code != 200:
            return None
        data = r.json().get("data", [])
        # Find NIFTY 50 index entry which has advances/declines
        for idx in data:
            if idx.get("index") in ("NIFTY 50", "Nifty 50"):
                adv = idx.get("advances",  0) or 0
                dec = idx.get("declines",  0) or 0
                unc = idx.get("unchanged", 0) or 0
                total = adv + dec + unc or 1
                ad_ratio = round(adv / (adv + dec), 3) if (adv + dec) > 0 else 0.5

                if ad_ratio > 0.65:
                    signal = "BROAD_RALLY"
                elif ad_ratio > 0.50:
                    signal = "MODERATE_BUYING"
                elif ad_ratio > 0.35:
                    signal = "MIXED"
                else:
                    signal = "BROAD_SELLING"

                return {
                    "advances":       adv,
                    "declines":       dec,
                    "unchanged":      unc,
                    "total":          total,
                    "ad_ratio":       ad_ratio,
                    "breadth_signal": signal,
                    "breadth_pct":    round(adv / total * 100, 1),
                }
        return None
    except Exception as e:
        log.debug("Advance-Decline fetch failed: %s", e)
        return None


def run(shared_state):
    """Main agent function — scans universe, returns top 10."""
    log.info("🔍 MarketScanner: Starting scan of %d stocks...", len(UNIVERSE))
    start   = time.time()
    results = []

    # Pull delivery data written by institutional_flow (may be empty on first cycle)
    delivery_map = shared_state.get("delivery_data", {})

    for i, stock in enumerate(UNIVERSE):
        pdata = fetch_price(stock["sym"])

        # Enrich stock with delivery % before scoring
        clean_sym = stock["sym"].replace(".NS", "").replace(".BO", "")
        del_info  = delivery_map.get(clean_sym, {})
        stock_enriched = {
            **stock,
            "delivery_pct":   del_info.get("delivery_pct", 0),
            "institutional":  del_info.get("institutional", False),
        }

        score, sig = score_stock(stock_enriched, pdata)
        if pdata:
            target = round(pdata["price"] * 1.20, 1)
            sl     = round(pdata["price"] * 0.92, 1)
            results.append({
                **stock_enriched, **pdata,
                "score": score, "signal": sig,
                "target": target, "sl": sl,
                "scanned_at": datetime.now().strftime("%H:%M:%S")
            })
        time.sleep(0.25)   # polite rate limiting

        if (i + 1) % 10 == 0:
            log.info("  Scanned %d/%d...", i+1, len(UNIVERSE))

    results.sort(key=lambda x: -x["score"])
    top10 = results[:10]

    elapsed = round(time.time() - start, 1)
    log.info("✅ MarketScanner: Done in %ss. Top pick: %s (Score %d)",
             elapsed, top10[0]["name"] if top10 else "—", top10[0]["score"] if top10 else 0)

    # ── ADVANCE-DECLINE BREADTH ───────────────────────────────────────────────
    ad_data = fetch_advance_decline()
    if ad_data:
        shared_state["advance_decline"] = ad_data
        log.info("  A/D: %d↑ %d↓ | Ratio=%.2f | %s",
                 ad_data["advances"], ad_data["declines"],
                 ad_data["ad_ratio"], ad_data["breadth_signal"])
    else:
        # Fallback: estimate from scan results
        adv = sum(1 for s in results if s.get("change_pct", 0) > 0)
        dec = len(results) - adv
        ad_r = round(adv / (adv + dec), 3) if (adv + dec) > 0 else 0.5
        shared_state["advance_decline"] = {
            "advances": adv, "declines": dec, "unchanged": 0,
            "total": len(results), "ad_ratio": ad_r,
            "breadth_signal": "BROAD_RALLY" if ad_r > 0.65 else "MIXED",
            "breadth_pct": round(adv / len(results) * 100, 1) if results else 50,
            "source": "scan_estimate",
        }

    # Write to shared state
    shared_state["scanner_results"]  = top10
    shared_state["full_scan"]        = results
    shared_state["scanner_last_run"] = datetime.now().strftime("%d %b %H:%M:%S")
    shared_state["scanner_elapsed"]  = elapsed
    return top10
