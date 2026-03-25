# ══════════════════════════════════════════════════════════════════════════════
# StockGuru — Observer Swarm (Phase 2)
# Lightweight scraper: NSE option chain + Screener.in + NSE bulk deals
# No Playwright. Uses requests.Session() to seed NSE cookies.
# Runs every 4 hours via scheduler.
# Writes: shared_state["observer_output"] + data/observer_log.json
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import logging
import time
from datetime import datetime

log = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
_LOG_FILE = os.path.join(_DATA_DIR, "observer_log.json")
_LOG_MAX  = 50

_NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
    "Accept":          "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}

_WATCHLIST_SCREENER = {
    "AIRTEL":    "BHARTIARTL",
    "HDFC BANK": "HDFCBANK",
    "ICICI BANK": "ICICIBANK",
    "BAJAJ FIN": "BAJFINANCE",
    "BEL":       "BEL",
    "MUTHOOT":   "MUTHOOTFIN",
    "ZOMATO":    "ZOMATO",
    "INDIGO":    "INDIGO",
}


# ─── Public entry point ────────────────────────────────────────────────────────

def run(shared_state: dict) -> dict:
    """
    Main entry point called by scheduler every 4 hours.
    Returns observer_output dict and writes to shared_state.
    Fails gracefully — never raises.
    """
    if not _DEPS_OK:
        log.warning("Observer: requests/beautifulsoup4 not available")
        return {}

    log.info("Observer Swarm: starting scan")
    out = {
        "oi_heatmap":         {},
        "promoter_holdings":  {},
        "block_deals_today":  [],
        "52w_breakouts":      [],
        "last_run":           datetime.now().strftime("%d %b %H:%M:%S"),
        "run_count":          shared_state.get("observer_output", {}).get("run_count", 0) + 1,
        "errors":             [],
    }

    session = _create_nse_session()

    # 1. NSE option chain (OI heatmap, max pain, PCR)
    try:
        oi_data = _fetch_nse_option_chain(session)
        out["oi_heatmap"] = oi_data
        log.info(f"Observer: OI heatmap OK — max_pain={oi_data.get('max_pain')}, pcr={oi_data.get('pcr')}")
    except Exception as e:
        log.warning(f"Observer: option chain failed: {e}")
        out["errors"].append(f"option_chain: {str(e)[:80]}")

    # 2. NSE bulk deals
    try:
        deals = _fetch_block_deals(session)
        out["block_deals_today"] = deals
        log.info(f"Observer: block deals OK — {len(deals)} deals found")
    except Exception as e:
        log.warning(f"Observer: block deals failed: {e}")
        out["errors"].append(f"block_deals: {str(e)[:80]}")

    # 3. Screener.in fundamentals (throttled, 1s between requests)
    holdings = {}
    for name, sym in _WATCHLIST_SCREENER.items():
        try:
            h = _fetch_screener_fundamentals(sym)
            if h:
                holdings[name] = h
            time.sleep(1.2)  # polite rate limit
        except Exception as e:
            log.warning(f"Observer: Screener.in {sym} failed: {e}")
            out["errors"].append(f"screener_{sym}: {str(e)[:60]}")
    out["promoter_holdings"] = holdings
    log.info(f"Observer: promoter holdings OK — {len(holdings)} stocks")

    # 4. 52-week breakouts from NSE Nifty50 index
    try:
        breakouts = _fetch_52w_breakouts(session)
        out["52w_breakouts"] = breakouts
        log.info(f"Observer: 52w breakouts OK — {breakouts}")
    except Exception as e:
        log.warning(f"Observer: 52w breakouts failed: {e}")
        out["errors"].append(f"52w_breakouts: {str(e)[:80]}")

    # Save to shared_state and log
    shared_state["observer_output"] = out
    _save_observer_log(out)
    log.info(f"Observer Swarm: complete — {len(out['errors'])} errors")
    return out


# ─── NSE Session ──────────────────────────────────────────────────────────────

def _create_nse_session() -> "requests.Session":
    """Seed NSE session cookies by hitting the main page first."""
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.5)
    except Exception as e:
        log.warning(f"Observer: NSE session seed failed: {e}")
    return s


# ─── NSE Option Chain ─────────────────────────────────────────────────────────

def _fetch_nse_option_chain(session) -> dict:
    """
    Fetch NIFTY option chain from NSE API.
    Returns OI heatmap (top CE resistance / PE support), max pain, PCR.
    """
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    r = session.get(url, timeout=12)
    r.raise_for_status()
    data = r.json()

    records = data.get("records", {}).get("data", [])
    if not records:
        return {}

    atm_strike = data.get("records", {}).get("underlyingValue", 0)

    # Aggregate OI by strike
    ce_oi = {}
    pe_oi = {}
    for rec in records:
        strike = rec.get("strikePrice", 0)
        if "CE" in rec and rec["CE"].get("openInterest"):
            ce_oi[strike] = ce_oi.get(strike, 0) + rec["CE"]["openInterest"]
        if "PE" in rec and rec["PE"].get("openInterest"):
            pe_oi[strike] = pe_oi.get(strike, 0) + rec["PE"]["openInterest"]

    # Top CE (resistance) and PE (support) by OI
    top_ce = sorted(ce_oi.items(), key=lambda x: x[1], reverse=True)[:5]
    top_pe = sorted(pe_oi.items(), key=lambda x: x[1], reverse=True)[:5]

    # Max pain: strike where sum of CE+PE OI at expiry is maximum loss to buyers
    max_pain = _compute_max_pain(ce_oi, pe_oi)

    # PCR
    total_pe = sum(pe_oi.values())
    total_ce = sum(ce_oi.values())
    pcr = round(total_pe / total_ce, 3) if total_ce else 0.0

    return {
        "top_ce_resistance": [{"strike": int(s), "oi": int(o)} for s, o in top_ce],
        "top_pe_support":    [{"strike": int(s), "oi": int(o)} for s, o in top_pe],
        "max_pain":          max_pain,
        "pcr":               pcr,
        "atm_strike":        atm_strike,
        "total_ce_oi":       int(total_ce),
        "total_pe_oi":       int(total_pe),
    }


def _compute_max_pain(ce_oi: dict, pe_oi: dict) -> float:
    """
    Max pain = strike where total OI value (CE+PE) is maximized at expiry.
    At each strike K, sum (K - K_i) * OI for all lower CE strikes
    + sum (K_i - K) * OI for all higher PE strikes.
    Returns the strike with minimum pain to option writers (max pain to buyers).
    """
    all_strikes = sorted(set(list(ce_oi.keys()) + list(pe_oi.keys())))
    if not all_strikes:
        return 0.0

    min_pain = float("inf")
    max_pain_strike = all_strikes[len(all_strikes) // 2]

    for K in all_strikes:
        pain = 0
        for s, oi in ce_oi.items():
            pain += max(0, K - s) * oi
        for s, oi in pe_oi.items():
            pain += max(0, s - K) * oi
        if pain < min_pain:
            min_pain = pain
            max_pain_strike = K

    return float(max_pain_strike)


# ─── NSE Bulk Deals ───────────────────────────────────────────────────────────

def _fetch_block_deals(session) -> list:
    """Fetch today's bulk deal archive from NSE."""
    today = datetime.now().strftime("%d-%m-%Y")
    url = f"https://www.nseindia.com/api/bulk-deal-archives?optionType=bulk_deals&year={datetime.now().year}&fromDate={today}&toDate={today}"
    r = session.get(url, timeout=10)
    if r.status_code != 200:
        return []
    data = r.json()
    deals = data.get("data", [])
    result = []
    for d in deals[:10]:
        result.append({
            "stock":    d.get("symbol", ""),
            "client":   d.get("client_name", ""),
            "qty":      int(d.get("quantity_traded", 0)),
            "price":    float(d.get("trade_price", 0)),
            "buy_sell": d.get("buy_sell", ""),
        })
    return result


# ─── Screener.in Fundamentals ─────────────────────────────────────────────────

def _fetch_screener_fundamentals(symbol: str) -> dict:
    """
    Scrape Screener.in for promoter holding % and key fundamentals.
    Returns dict or empty dict on failure.
    """
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=12)
    if r.status_code != 200:
        return {}

    soup = BeautifulSoup(r.text, "lxml")
    result = {}

    # Promoter holding from shareholding section
    try:
        sh_section = soup.find("section", {"id": "shareholding"})
        if sh_section:
            rows = sh_section.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    if "promoter" in label:
                        # Last cell is most recent quarter
                        val_text = cells[-1].get_text(strip=True).replace("%", "").strip()
                        try:
                            result["promoter_pct"] = float(val_text)
                        except ValueError:
                            pass
                        # Compare last two quarters for trend
                        if len(cells) >= 3:
                            try:
                                prev = float(cells[-2].get_text(strip=True).replace("%", "").strip())
                                result["change_qtr"] = round(result.get("promoter_pct", 0) - prev, 2)
                            except ValueError:
                                pass
                        break
    except Exception:
        pass

    # DII holding
    try:
        if sh_section:
            for row in sh_section.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2 and "dii" in cells[0].get_text(strip=True).lower():
                    val_text = cells[-1].get_text(strip=True).replace("%", "").strip()
                    try:
                        result["dii_pct"] = float(val_text)
                    except ValueError:
                        pass
                    break
    except Exception:
        pass

    # P/E ratio from key ratios
    try:
        ratios_section = soup.find("section", {"id": "top-ratios"})
        if ratios_section:
            for li in ratios_section.find_all("li"):
                label = li.find("span", {"class": "name"})
                value = li.find("span", {"class": "value"})
                if label and value and "p/e" in label.get_text(strip=True).lower():
                    try:
                        result["pe"] = float(value.get_text(strip=True).replace(",", ""))
                    except ValueError:
                        pass
                    break
    except Exception:
        pass

    return result


# ─── 52-Week Breakouts ────────────────────────────────────────────────────────

def _fetch_52w_breakouts(session) -> list:
    """
    Check which NIFTY 50 stocks are near/at 52-week highs.
    Uses NSE equity index API.
    """
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
    r = session.get(url, timeout=12)
    if r.status_code != 200:
        return []
    data = r.json()
    stocks = data.get("data", [])
    breakouts = []
    for s in stocks:
        try:
            high_52w = float(s.get("yearHigh", 0) or 0)
            curr = float(s.get("lastPrice", 0) or 0)
            if high_52w > 0 and curr > 0:
                pct_from_high = (curr - high_52w) / high_52w * 100
                # Within 1.5% of 52-week high = breakout zone
                if pct_from_high >= -1.5:
                    breakouts.append(s.get("symbol", ""))
        except (TypeError, ValueError):
            pass
    return breakouts[:10]  # cap at 10


# ─── Log Persistence ──────────────────────────────────────────────────────────

def _save_observer_log(finding: dict) -> None:
    """Append observer run summary to rolling log (max 50 entries)."""
    try:
        log_entry = {
            "timestamp":      datetime.now().isoformat(),
            "last_run":       finding.get("last_run"),
            "run_count":      finding.get("run_count"),
            "pcr":            finding.get("oi_heatmap", {}).get("pcr"),
            "max_pain":       finding.get("oi_heatmap", {}).get("max_pain"),
            "block_deals":    len(finding.get("block_deals_today", [])),
            "promoters_scraped": len(finding.get("promoter_holdings", {})),
            "52w_breakouts":  finding.get("52w_breakouts", []),
            "errors":         finding.get("errors", []),
        }
        if os.path.exists(_LOG_FILE):
            with open(_LOG_FILE, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        else:
            log_data = []
        log_data.append(log_entry)
        if len(log_data) > _LOG_MAX:
            log_data = log_data[-_LOG_MAX:]
        with open(_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, default=str)
    except Exception as e:
        log.error(f"Observer: failed to save log: {e}")
