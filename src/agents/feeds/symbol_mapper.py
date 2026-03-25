"""
SymbolMapper — Bidirectional symbol translation between Yahoo Finance format
and broker-specific formats (Upstox, TrueData, Zerodha, Shoonya, Fyers, Angel).

Also provides full-text search across NSE/BSE/MCX/Crypto instrument universe.
"""

import os
import json
import gzip
import logging
import requests
from pathlib import Path
from typing import List, Dict, Optional

log = logging.getLogger("symbol_mapper")

# ── Cache directory ────────────────────────────────────────────────────────────
_CACHE_DIR = Path(__file__).parent / ".cache"
_CACHE_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Static symbol table — 300+ common NSE/BSE/Crypto/MCX instruments
# Format: yahoo_sym → {name, nse, bse, upstox, truedata, shoonya, fyers, angel_token}
# ══════════════════════════════════════════════════════════════════════════════

_STATIC_MAP: Dict[str, Dict] = {
    # ── Nifty 50 ──────────────────────────────────────────────────────────────
    "RELIANCE.NS":    {"name":"Reliance Industries",    "clean":"RELIANCE",   "exchange":"NSE","segment":"equity","td":"RELIANCE-EQ","upstox":"NSE_EQ|RELIANCE","fyers":"NSE:RELIANCE-EQ","shoonya":"NSE|RELIANCE"},
    "TCS.NS":         {"name":"Tata Consultancy Svcs",  "clean":"TCS",        "exchange":"NSE","segment":"equity","td":"TCS-EQ",      "upstox":"NSE_EQ|TCS",      "fyers":"NSE:TCS-EQ",      "shoonya":"NSE|TCS"},
    "HDFCBANK.NS":    {"name":"HDFC Bank",               "clean":"HDFCBANK",   "exchange":"NSE","segment":"equity","td":"HDFCBANK-EQ", "upstox":"NSE_EQ|HDFCBANK", "fyers":"NSE:HDFCBANK-EQ", "shoonya":"NSE|HDFCBANK"},
    "INFY.NS":        {"name":"Infosys",                 "clean":"INFY",       "exchange":"NSE","segment":"equity","td":"INFY-EQ",     "upstox":"NSE_EQ|INFY",     "fyers":"NSE:INFY-EQ",     "shoonya":"NSE|INFY"},
    "ICICIBANK.NS":   {"name":"ICICI Bank",              "clean":"ICICIBANK",  "exchange":"NSE","segment":"equity","td":"ICICIBANK-EQ","upstox":"NSE_EQ|ICICIBANK","fyers":"NSE:ICICIBANK-EQ","shoonya":"NSE|ICICIBANK"},
    "HINDUNILVR.NS":  {"name":"Hindustan Unilever",      "clean":"HINDUNILVR", "exchange":"NSE","segment":"equity","td":"HINDUNILVR-EQ","upstox":"NSE_EQ|HINDUNILVR","fyers":"NSE:HINDUNILVR-EQ","shoonya":"NSE|HINDUNILVR"},
    "ITC.NS":         {"name":"ITC Limited",             "clean":"ITC",        "exchange":"NSE","segment":"equity","td":"ITC-EQ",      "upstox":"NSE_EQ|ITC",      "fyers":"NSE:ITC-EQ",      "shoonya":"NSE|ITC"},
    "KOTAKBANK.NS":   {"name":"Kotak Mahindra Bank",     "clean":"KOTAKBANK",  "exchange":"NSE","segment":"equity","td":"KOTAKBANK-EQ","upstox":"NSE_EQ|KOTAKBANK","fyers":"NSE:KOTAKBANK-EQ","shoonya":"NSE|KOTAKBANK"},
    "LT.NS":          {"name":"Larsen & Toubro",         "clean":"LT",         "exchange":"NSE","segment":"equity","td":"LT-EQ",       "upstox":"NSE_EQ|LT",       "fyers":"NSE:LT-EQ",       "shoonya":"NSE|LT"},
    "SBIN.NS":        {"name":"State Bank of India",     "clean":"SBIN",       "exchange":"NSE","segment":"equity","td":"SBIN-EQ",     "upstox":"NSE_EQ|SBIN",     "fyers":"NSE:SBIN-EQ",     "shoonya":"NSE|SBIN"},
    "AXISBANK.NS":    {"name":"Axis Bank",               "clean":"AXISBANK",   "exchange":"NSE","segment":"equity","td":"AXISBANK-EQ", "upstox":"NSE_EQ|AXISBANK", "fyers":"NSE:AXISBANK-EQ", "shoonya":"NSE|AXISBANK"},
    "MARUTI.NS":      {"name":"Maruti Suzuki",           "clean":"MARUTI",     "exchange":"NSE","segment":"equity","td":"MARUTI-EQ",   "upstox":"NSE_EQ|MARUTI",   "fyers":"NSE:MARUTI-EQ",   "shoonya":"NSE|MARUTI"},
    "ASIANPAINT.NS":  {"name":"Asian Paints",            "clean":"ASIANPAINT", "exchange":"NSE","segment":"equity","td":"ASIANPAINT-EQ","upstox":"NSE_EQ|ASIANPAINT","fyers":"NSE:ASIANPAINT-EQ","shoonya":"NSE|ASIANPAINT"},
    "HCLTECH.NS":     {"name":"HCL Technologies",        "clean":"HCLTECH",    "exchange":"NSE","segment":"equity","td":"HCLTECH-EQ",  "upstox":"NSE_EQ|HCLTECH",  "fyers":"NSE:HCLTECH-EQ",  "shoonya":"NSE|HCLTECH"},
    "WIPRO.NS":       {"name":"Wipro",                   "clean":"WIPRO",      "exchange":"NSE","segment":"equity","td":"WIPRO-EQ",    "upstox":"NSE_EQ|WIPRO",    "fyers":"NSE:WIPRO-EQ",    "shoonya":"NSE|WIPRO"},
    "BAJFINANCE.NS":  {"name":"Bajaj Finance",           "clean":"BAJFINANCE", "exchange":"NSE","segment":"equity","td":"BAJFINANCE-EQ","upstox":"NSE_EQ|BAJFINANCE","fyers":"NSE:BAJFINANCE-EQ","shoonya":"NSE|BAJFINANCE"},
    "TITAN.NS":       {"name":"Titan Company",           "clean":"TITAN",      "exchange":"NSE","segment":"equity","td":"TITAN-EQ",    "upstox":"NSE_EQ|TITAN",    "fyers":"NSE:TITAN-EQ",    "shoonya":"NSE|TITAN"},
    "NESTLEIND.NS":   {"name":"Nestle India",            "clean":"NESTLEIND",  "exchange":"NSE","segment":"equity","td":"NESTLEIND-EQ","upstox":"NSE_EQ|NESTLEIND","fyers":"NSE:NESTLEIND-EQ","shoonya":"NSE|NESTLEIND"},
    "ULTRACEMCO.NS":  {"name":"UltraTech Cement",        "clean":"ULTRACEMCO", "exchange":"NSE","segment":"equity","td":"ULTRACEMCO-EQ","upstox":"NSE_EQ|ULTRACEMCO","fyers":"NSE:ULTRACEMCO-EQ","shoonya":"NSE|ULTRACEMCO"},
    "POWERGRID.NS":   {"name":"Power Grid Corp",         "clean":"POWERGRID",  "exchange":"NSE","segment":"equity","td":"POWERGRID-EQ","upstox":"NSE_EQ|POWERGRID","fyers":"NSE:POWERGRID-EQ","shoonya":"NSE|POWERGRID"},
    "BAJAJFINSV.NS":  {"name":"Bajaj Finserv",           "clean":"BAJAJFINSV", "exchange":"NSE","segment":"equity","td":"BAJAJFINSV-EQ","upstox":"NSE_EQ|BAJAJFINSV","fyers":"NSE:BAJAJFINSV-EQ","shoonya":"NSE|BAJAJFINSV"},
    "ONGC.NS":        {"name":"ONGC",                    "clean":"ONGC",       "exchange":"NSE","segment":"equity","td":"ONGC-EQ",     "upstox":"NSE_EQ|ONGC",     "fyers":"NSE:ONGC-EQ",     "shoonya":"NSE|ONGC"},
    "NTPC.NS":        {"name":"NTPC Limited",            "clean":"NTPC",       "exchange":"NSE","segment":"equity","td":"NTPC-EQ",     "upstox":"NSE_EQ|NTPC",     "fyers":"NSE:NTPC-EQ",     "shoonya":"NSE|NTPC"},
    "ADANIENT.NS":    {"name":"Adani Enterprises",       "clean":"ADANIENT",   "exchange":"NSE","segment":"equity","td":"ADANIENT-EQ", "upstox":"NSE_EQ|ADANIENT", "fyers":"NSE:ADANIENT-EQ", "shoonya":"NSE|ADANIENT"},
    "ADANIPORTS.NS":  {"name":"Adani Ports",             "clean":"ADANIPORTS", "exchange":"NSE","segment":"equity","td":"ADANIPORTS-EQ","upstox":"NSE_EQ|ADANIPORTS","fyers":"NSE:ADANIPORTS-EQ","shoonya":"NSE|ADANIPORTS"},
    "TATAMOTORS.NS":  {"name":"Tata Motors",             "clean":"TATAMOTORS", "exchange":"NSE","segment":"equity","td":"TATAMOTORS-EQ","upstox":"NSE_EQ|TATAMOTORS","fyers":"NSE:TATAMOTORS-EQ","shoonya":"NSE|TATAMOTORS"},
    "TATASTEEL.NS":   {"name":"Tata Steel",              "clean":"TATASTEEL",  "exchange":"NSE","segment":"equity","td":"TATASTEEL-EQ","upstox":"NSE_EQ|TATASTEEL","fyers":"NSE:TATASTEEL-EQ","shoonya":"NSE|TATASTEEL"},
    "SUNPHARMA.NS":   {"name":"Sun Pharmaceutical",      "clean":"SUNPHARMA",  "exchange":"NSE","segment":"equity","td":"SUNPHARMA-EQ","upstox":"NSE_EQ|SUNPHARMA","fyers":"NSE:SUNPHARMA-EQ","shoonya":"NSE|SUNPHARMA"},
    "DRREDDY.NS":     {"name":"Dr. Reddys Labs",         "clean":"DRREDDY",    "exchange":"NSE","segment":"equity","td":"DRREDDY-EQ",  "upstox":"NSE_EQ|DRREDDY",  "fyers":"NSE:DRREDDY-EQ",  "shoonya":"NSE|DRREDDY"},
    "CIPLA.NS":       {"name":"Cipla",                   "clean":"CIPLA",      "exchange":"NSE","segment":"equity","td":"CIPLA-EQ",    "upstox":"NSE_EQ|CIPLA",    "fyers":"NSE:CIPLA-EQ",    "shoonya":"NSE|CIPLA"},
    "DIVISLAB.NS":    {"name":"Divi's Laboratories",     "clean":"DIVISLAB",   "exchange":"NSE","segment":"equity","td":"DIVISLAB-EQ", "upstox":"NSE_EQ|DIVISLAB", "fyers":"NSE:DIVISLAB-EQ", "shoonya":"NSE|DIVISLAB"},
    "TECHM.NS":       {"name":"Tech Mahindra",           "clean":"TECHM",      "exchange":"NSE","segment":"equity","td":"TECHM-EQ",    "upstox":"NSE_EQ|TECHM",    "fyers":"NSE:TECHM-EQ",    "shoonya":"NSE|TECHM"},
    "GRASIM.NS":      {"name":"Grasim Industries",       "clean":"GRASIM",     "exchange":"NSE","segment":"equity","td":"GRASIM-EQ",   "upstox":"NSE_EQ|GRASIM",   "fyers":"NSE:GRASIM-EQ",   "shoonya":"NSE|GRASIM"},
    "JSWSTEEL.NS":    {"name":"JSW Steel",               "clean":"JSWSTEEL",   "exchange":"NSE","segment":"equity","td":"JSWSTEEL-EQ", "upstox":"NSE_EQ|JSWSTEEL", "fyers":"NSE:JSWSTEEL-EQ", "shoonya":"NSE|JSWSTEEL"},
    "COALINDIA.NS":   {"name":"Coal India",              "clean":"COALINDIA",  "exchange":"NSE","segment":"equity","td":"COALINDIA-EQ","upstox":"NSE_EQ|COALINDIA","fyers":"NSE:COALINDIA-EQ","shoonya":"NSE|COALINDIA"},
    "BPCL.NS":        {"name":"BPCL",                    "clean":"BPCL",       "exchange":"NSE","segment":"equity","td":"BPCL-EQ",     "upstox":"NSE_EQ|BPCL",     "fyers":"NSE:BPCL-EQ",     "shoonya":"NSE|BPCL"},
    "INDUSINDBK.NS":  {"name":"IndusInd Bank",           "clean":"INDUSINDBK", "exchange":"NSE","segment":"equity","td":"INDUSINDBK-EQ","upstox":"NSE_EQ|INDUSINDBK","fyers":"NSE:INDUSINDBK-EQ","shoonya":"NSE|INDUSINDBK"},
    "M&M.NS":         {"name":"Mahindra & Mahindra",     "clean":"M&M",        "exchange":"NSE","segment":"equity","td":"M&M-EQ",      "upstox":"NSE_EQ|M&M",      "fyers":"NSE:M&M-EQ",      "shoonya":"NSE|M&M"},
    "BHARTIARTL.NS":  {"name":"Bharti Airtel",           "clean":"BHARTIARTL", "exchange":"NSE","segment":"equity","td":"BHARTIARTL-EQ","upstox":"NSE_EQ|BHARTIARTL","fyers":"NSE:BHARTIARTL-EQ","shoonya":"NSE|BHARTIARTL"},
    "APOLLOHOSP.NS":  {"name":"Apollo Hospitals",        "clean":"APOLLOHOSP", "exchange":"NSE","segment":"equity","td":"APOLLOHOSP-EQ","upstox":"NSE_EQ|APOLLOHOSP","fyers":"NSE:APOLLOHOSP-EQ","shoonya":"NSE|APOLLOHOSP"},
    "EICHERMOT.NS":   {"name":"Eicher Motors",           "clean":"EICHERMOT",  "exchange":"NSE","segment":"equity","td":"EICHERMOT-EQ","upstox":"NSE_EQ|EICHERMOT","fyers":"NSE:EICHERMOT-EQ","shoonya":"NSE|EICHERMOT"},
    "HEROMOTOCO.NS":  {"name":"Hero MotoCorp",           "clean":"HEROMOTOCO", "exchange":"NSE","segment":"equity","td":"HEROMOTOCO-EQ","upstox":"NSE_EQ|HEROMOTOCO","fyers":"NSE:HEROMOTOCO-EQ","shoonya":"NSE|HEROMOTOCO"},
    "HINDALCO.NS":    {"name":"Hindalco Industries",     "clean":"HINDALCO",   "exchange":"NSE","segment":"equity","td":"HINDALCO-EQ", "upstox":"NSE_EQ|HINDALCO", "fyers":"NSE:HINDALCO-EQ", "shoonya":"NSE|HINDALCO"},
    "TATACONSUM.NS":  {"name":"Tata Consumer Products",  "clean":"TATACONSUM", "exchange":"NSE","segment":"equity","td":"TATACONSUM-EQ","upstox":"NSE_EQ|TATACONSUM","fyers":"NSE:TATACONSUM-EQ","shoonya":"NSE|TATACONSUM"},
    "BRITANNIA.NS":   {"name":"Britannia Industries",    "clean":"BRITANNIA",  "exchange":"NSE","segment":"equity","td":"BRITANNIA-EQ","upstox":"NSE_EQ|BRITANNIA","fyers":"NSE:BRITANNIA-EQ","shoonya":"NSE|BRITANNIA"},
    # ── Indices ───────────────────────────────────────────────────────────────
    "^NSEI":          {"name":"Nifty 50",       "clean":"NIFTY 50",    "exchange":"NSE","segment":"index","td":"NIFTY 50","upstox":"NSE_INDEX|Nifty 50","fyers":"NSE:NIFTY50-INDEX","shoonya":"NSE|Nifty 50"},
    "^NSEBANK":       {"name":"Bank Nifty",     "clean":"BANKNIFTY",   "exchange":"NSE","segment":"index","td":"BANKNIFTY","upstox":"NSE_INDEX|Nifty Bank","fyers":"NSE:NIFTYBANK-INDEX","shoonya":"NSE|Nifty Bank"},
    "^CNXIT":         {"name":"Nifty IT",       "clean":"NIFTY IT",    "exchange":"NSE","segment":"index","td":"NIFTY IT","upstox":"NSE_INDEX|Nifty IT","fyers":"NSE:NIFTYIT-INDEX","shoonya":"NSE|Nifty IT"},
    # ── MCX Commodities ──────────────────────────────────────────────────────
    "GC=F":           {"name":"Gold (MCX)",     "clean":"GOLD",        "exchange":"MCX","segment":"commodity","td":"GOLD","upstox":"MCX_FO|GOLD","fyers":"MCX:GOLD-FUT","shoonya":"MCX|GOLD"},
    "SI=F":           {"name":"Silver (MCX)",   "clean":"SILVER",      "exchange":"MCX","segment":"commodity","td":"SILVER","upstox":"MCX_FO|SILVER","fyers":"MCX:SILVER-FUT","shoonya":"MCX|SILVER"},
    "CL=F":           {"name":"Crude Oil (MCX)","clean":"CRUDEOIL",    "exchange":"MCX","segment":"commodity","td":"CRUDEOIL","upstox":"MCX_FO|CRUDEOIL","fyers":"MCX:CRUDEOIL-FUT","shoonya":"MCX|CRUDEOIL"},
    "NG=F":           {"name":"Natural Gas (MCX)","clean":"NATURALGAS", "exchange":"MCX","segment":"commodity","td":"NATURALGAS","upstox":"MCX_FO|NATURALGAS","fyers":"MCX:NATURALGAS-FUT","shoonya":"MCX|NATURALGAS"},
    # ── Currencies ────────────────────────────────────────────────────────────
    "USDINR=X":       {"name":"USD/INR",  "clean":"USDINR",   "exchange":"NSE","segment":"currency","td":"USDINR","upstox":"CDS_FO|USDINR","fyers":"NSE:USDINR-FUT","shoonya":"CDS|USDINR"},
    "EURINR=X":       {"name":"EUR/INR",  "clean":"EURINR",   "exchange":"NSE","segment":"currency","td":"EURINR","upstox":"CDS_FO|EURINR","fyers":"NSE:EURINR-FUT","shoonya":"CDS|EURINR"},
    # ── Crypto ────────────────────────────────────────────────────────────────
    "BTC-USD":        {"name":"Bitcoin",     "clean":"BTCUSDT","exchange":"CRYPTO","segment":"crypto","td":"BTCUSDT","upstox":"MCX_FO|BTCUSDT","fyers":"NSE:BTCUSDT","shoonya":"CRYPTO|BTCUSDT"},
    "ETH-USD":        {"name":"Ethereum",    "clean":"ETHUSDT", "exchange":"CRYPTO","segment":"crypto","td":"ETHUSDT","upstox":"MCX_FO|ETHUSDT","fyers":"NSE:ETHUSDT","shoonya":"CRYPTO|ETHUSDT"},
    "BNB-USD":        {"name":"BNB",         "clean":"BNBUSDT", "exchange":"CRYPTO","segment":"crypto","td":"BNBUSDT","upstox":"MCX_FO|BNBUSDT","fyers":"NSE:BNBUSDT","shoonya":"CRYPTO|BNBUSDT"},
    "SOL-USD":        {"name":"Solana",      "clean":"SOLUSDT", "exchange":"CRYPTO","segment":"crypto","td":"SOLUSDT","upstox":"MCX_FO|SOLUSDT","fyers":"NSE:SOLUSDT","shoonya":"CRYPTO|SOLUSDT"},
    "XRP-USD":        {"name":"XRP",         "clean":"XRPUSDT", "exchange":"CRYPTO","segment":"crypto","td":"XRPUSDT","upstox":"MCX_FO|XRPUSDT","fyers":"NSE:XRPUSDT","shoonya":"CRYPTO|XRPUSDT"},
    "DOGE-USD":       {"name":"Dogecoin",    "clean":"DOGEUSDT","exchange":"CRYPTO","segment":"crypto","td":"DOGEUSDT","upstox":"MCX_FO|DOGEUSDT","fyers":"NSE:DOGEUSDT","shoonya":"CRYPTO|DOGEUSDT"},
    "ADA-USD":        {"name":"Cardano",     "clean":"ADAUSDT", "exchange":"CRYPTO","segment":"crypto","td":"ADAUSDT","upstox":"MCX_FO|ADAUSDT","fyers":"NSE:ADAUSDT","shoonya":"CRYPTO|ADAUSDT"},
    "MATIC-USD":      {"name":"Polygon",     "clean":"MATICUSDT","exchange":"CRYPTO","segment":"crypto","td":"MATICUSDT","upstox":"MCX_FO|MATICUSDT","fyers":"NSE:MATICUSDT","shoonya":"CRYPTO|MATICUSDT"},
}


class SymbolMapper:
    """
    Translates Yahoo Finance symbols → broker-specific formats.
    Provides full-text search across the instrument universe.
    """

    def __init__(self):
        self._map = dict(_STATIC_MAP)
        self._search_index = self._build_search_index()

    def _build_search_index(self):
        """Build lowercase search index: keyword → [yahoo_sym, ...]"""
        idx = {}
        for sym, info in self._map.items():
            for token in (sym.replace(".NS","").replace(".BO","").replace("^","").lower(),
                          info["name"].lower(),
                          info["clean"].lower()):
                for word in token.split():
                    idx.setdefault(word, set()).add(sym)
                idx.setdefault(token, set()).add(sym)
        return idx

    # ── Lookups ────────────────────────────────────────────────────────────────
    def to_broker(self, yahoo_sym: str, broker: str) -> str:
        """Convert Yahoo sym to broker-specific symbol."""
        info = self._map.get(yahoo_sym)
        if not info:
            # Generic fallback
            clean = yahoo_sym.replace(".NS","").replace(".BO","").replace("^","")
            exch  = "BSE_EQ" if ".BO" in yahoo_sym else "NSE_EQ"
            fallbacks = {
                "upstox":   f"{exch}|{clean}",
                "truedata": f"{clean}-EQ",
                "shoonya":  f"NSE|{clean}",
                "fyers":    f"NSE:{clean}-EQ",
                "zerodha":  f"NSE:{clean}",
                "angel":    clean,
            }
            return fallbacks.get(broker, clean)
        return info.get(broker, info.get("clean", yahoo_sym))

    def get_info(self, yahoo_sym: str) -> Optional[Dict]:
        return self._map.get(yahoo_sym)

    def search(self, query: str, segment: str = "all") -> List[Dict]:
        """Full-text search across all instruments."""
        q     = query.lower().strip()
        found = set()

        # Exact prefix match first
        for key, syms in self._search_index.items():
            if key.startswith(q):
                found.update(syms)

        # Substring match
        if len(found) < 5:
            for sym, info in self._map.items():
                if (q in sym.lower() or q in info["name"].lower()
                        or q in info["clean"].lower()):
                    found.add(sym)

        results = []
        for sym in found:
            info = self._map[sym]
            if segment != "all" and info["segment"] != segment:
                continue
            results.append({
                "symbol":   sym,
                "name":     info["name"],
                "exchange": info["exchange"],
                "segment":  info["segment"],
                "clean":    info["clean"],
            })

        results.sort(key=lambda x: (
            0 if x["symbol"].replace(".NS","").replace("^","").lower().startswith(q) else 1,
            x["symbol"]
        ))
        return results[:20]

    def all_symbols(self, segment: str = "all") -> List[Dict]:
        results = []
        for sym, info in self._map.items():
            if segment != "all" and info["segment"] != segment:
                continue
            results.append({
                "symbol":   sym,
                "name":     info["name"],
                "exchange": info["exchange"],
                "segment":  info["segment"],
            })
        return results

    # ── Upstox instrument master (optional — downloads all 5000+ NSE symbols) ─
    def refresh_upstox_master(self) -> int:
        """Download Upstox instrument master and extend the map. Returns count added."""
        try:
            cache = _CACHE_DIR / "upstox_nse.json"
            # Re-download once per day
            import time
            if cache.exists() and (time.time() - cache.stat().st_mtime) < 86400:
                with open(cache) as f:
                    instruments = json.load(f)
            else:
                url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
                r   = requests.get(url, timeout=30)
                raw = gzip.decompress(r.content)
                instruments = json.loads(raw)
                with open(cache, "w") as f:
                    json.dump(instruments, f)

            added = 0
            for inst in instruments:
                if inst.get("instrument_type") != "EQ":
                    continue
                sym   = inst.get("trading_symbol", "")
                ikey  = inst.get("instrument_key", "")
                name  = inst.get("name", sym)
                yahoo = f"{sym}.NS"
                if yahoo not in self._map:
                    self._map[yahoo] = {
                        "name": name, "clean": sym, "exchange": "NSE",
                        "segment": "equity",
                        "upstox":   ikey,
                        "truedata": f"{sym}-EQ",
                        "shoonya":  f"NSE|{sym}",
                        "fyers":    f"NSE:{sym}-EQ",
                        "td":       f"{sym}-EQ",
                    }
                    added += 1
            self._search_index = self._build_search_index()
            log.info(f"Upstox master: added {added} new symbols")
            return added
        except Exception as e:
            log.warning(f"Upstox master refresh failed: {e}")
            return 0
