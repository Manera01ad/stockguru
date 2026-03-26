"""
StockGuru MCP Server — Market Data as Model Context Protocol tools.

Exposes live Indian + crypto market data to any MCP-compatible client:
  • Claude Desktop  → add to claude_desktop_config.json
  • Claude Code     → add to .claude.json
  • Any MCP client  → connect via stdio or SSE

Usage:
  python stockguru_mcp_server.py            # stdio (Claude Desktop)
  python stockguru_mcp_server.py --sse      # SSE HTTP server on :8765

Requirements:
  pip install mcp

Tools exposed:
  get_quote(symbol)                   → live price, OHLC, volume
  get_orderbook(symbol, depth)        → bid/ask ladder
  get_candles(symbol, interval, range)→ OHLCV history
  get_feed_status()                   → active connector + all feeds
  search_symbol(query)                → find NSE/BSE/crypto symbols
  get_market_status()                 → NSE/BSE/MCX open/closed
  get_top_movers(segment, limit)      → gainers & losers
  run_pre_spike_scan()                → StockGuru pre-spike detector output
"""

import sys
import os
import json
import logging
from datetime import datetime
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_root = Path(__file__).parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "stockguru_agents"))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("stockguru_mcp")

# ── Feed manager ───────────────────────────────────────────────────────────────
try:
    from src.agents.feeds import feed_manager
    _FEED_OK = True
except Exception as e:
    log.error(f"FeedManager failed: {e}")
    feed_manager = None
    _FEED_OK = False

# ── Symbol mapper ──────────────────────────────────────────────────────────────
try:
    from src.agents.feeds.symbol_mapper import SymbolMapper
    _sym_mapper = SymbolMapper()
except Exception:
    _sym_mapper = None

# ── Market hours (IST) ────────────────────────────────────────────────────────
_NSE_OPEN  = (9, 15)
_NSE_CLOSE = (15, 30)
_MCX_OPEN  = (9, 0)
_MCX_CLOSE = (23, 30)

def _market_status() -> dict:
    from datetime import timezone, timedelta
    IST   = timezone(timedelta(hours=5, minutes=30))
    now   = datetime.now(IST)
    wd    = now.weekday()   # 0=Mon … 6=Sun
    h, m  = now.hour, now.minute
    t     = h * 60 + m
    week  = wd < 5
    nse   = week and _NSE_OPEN[0]*60+_NSE_OPEN[1] <= t <= _NSE_CLOSE[0]*60+_NSE_CLOSE[1]
    mcx   = week and _MCX_OPEN[0]*60+_MCX_OPEN[1] <= t <= _MCX_CLOSE[0]*60+_MCX_CLOSE[1]
    return {
        "NSE":  {"open": nse,  "status": "OPEN" if nse  else "CLOSED"},
        "BSE":  {"open": nse,  "status": "OPEN" if nse  else "CLOSED"},
        "MCX":  {"open": mcx,  "status": "OPEN" if mcx  else "CLOSED"},
        "time_IST": now.strftime("%H:%M:%S %Z"),
        "day":  now.strftime("%A"),
    }

# ── Top movers ─────────────────────────────────────────────────────────────────
_NIFTY50 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","ITC.NS","KOTAKBANK.NS","LT.NS","SBIN.NS",
    "AXISBANK.NS","MARUTI.NS","ASIANPAINT.NS","HCLTECH.NS","WIPRO.NS",
    "BAJFINANCE.NS","TITAN.NS","NESTLEIND.NS","ULTRACEMCO.NS","POWERGRID.NS",
]
_CRYPTO = ["BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD"]


# ══════════════════════════════════════════════════════════════════════════════
# MCP Server setup
# ══════════════════════════════════════════════════════════════════════════════

try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    print("⚠️  mcp package not installed. Run: pip install mcp", file=sys.stderr)
    print("   Running in HTTP fallback mode instead.", file=sys.stderr)


if _MCP_AVAILABLE:
    mcp = FastMCP(
        name="StockGuru Market Data",
        instructions=(
            "Real-time Indian stock market data server for StockGuru. "
            "Use get_quote() for live prices, get_orderbook() for order book depth, "
            "get_candles() for historical OHLCV, search_symbol() to find instrument keys. "
            "All prices are in INR unless noted. Symbols use Yahoo Finance format: "
            "RELIANCE.NS (NSE), RELIANCE.BO (BSE), BTC-USD (crypto), ^NSEI (Nifty 50)."
        ),
    )

    # ── Tool 1: get_quote ─────────────────────────────────────────────────────
    @mcp.tool()
    def get_quote(symbol: str) -> str:
        """
        Get real-time quote for a stock, index, or crypto symbol.

        Args:
            symbol: Yahoo Finance symbol. Examples:
                    RELIANCE.NS  → Reliance Industries (NSE)
                    HDFCBANK.NS  → HDFC Bank (NSE)
                    ^NSEI        → Nifty 50 index
                    ^NSEBANK     → Bank Nifty index
                    BTC-USD      → Bitcoin/USD
                    GOLD.MCX     → MCX Gold

        Returns JSON with: price, change_pct, day_high, day_low, volume,
                           prev_close, currency, name, feed (data source)
        """
        if not _FEED_OK or not feed_manager:
            return json.dumps({"error": "Feed manager not available"})
        result = feed_manager.get_quote(symbol)
        result["feed"] = feed_manager.active_name
        result["symbol"] = symbol
        result["timestamp"] = datetime.now().isoformat()
        return json.dumps(result, default=str)

    # ── Tool 2: get_orderbook ─────────────────────────────────────────────────
    @mcp.tool()
    def get_orderbook(symbol: str, depth: int = 5) -> str:
        """
        Get live order book (bid/ask ladder) for a symbol.

        Args:
            symbol: Yahoo Finance symbol (e.g. RELIANCE.NS, ^NSEI, BTC-USD)
            depth:  Number of price levels each side (1-20, default 5).
                    Note: max depth depends on active feed
                    (Yahoo=simulated, Upstox=5, TrueData=20)

        Returns JSON with:
            bids[]: [{price, qty, total, orders}]  — buy side
            asks[]: [{price, qty, total, orders}]  — sell side
            spread, best_bid, best_ask, buy_pct, sell_pct,
            note: "live" | "simulated"
        """
        if not _FEED_OK or not feed_manager:
            return json.dumps({"error": "Feed manager not available"})
        result = feed_manager.get_orderbook(symbol, min(depth, 20))
        result["feed"]   = feed_manager.active_name
        result["symbol"] = symbol
        return json.dumps(result, default=str)

    # ── Tool 3: get_candles ────────────────────────────────────────────────────
    @mcp.tool()
    def get_candles(symbol: str, interval: str = "15m", range_: str = "5d") -> str:
        """
        Get OHLCV candlestick data for a symbol.

        Args:
            symbol:   Yahoo Finance symbol (e.g. RELIANCE.NS)
            interval: Candle timeframe. Options:
                      1m, 2m, 5m, 15m, 30m, 60m, 1h, 1d, 1wk, 1mo
            range_:   Data range. Options:
                      1d, 5d, 1mo, 3mo, 6mo, 1y, 2y
                      Note: short intervals require short ranges
                      (e.g. 1m only works with 1d range)

        Returns JSON with:
            candles[]: [{time (unix ts), open, high, low, close, volume}]
            price, change_pct, day_high, day_low, volume, currency
        """
        if not _FEED_OK or not feed_manager:
            return json.dumps({"error": "Feed manager not available"})
        result = feed_manager.get_candles(symbol, interval, range_)
        result["feed"] = feed_manager.active_name
        # Limit candles in response to avoid token overflow
        if len(result.get("candles", [])) > 200:
            result["candles"] = result["candles"][-200:]
            result["note"] = "Truncated to last 200 candles"
        return json.dumps(result, default=str)

    # ── Tool 4: get_feed_status ────────────────────────────────────────────────
    @mcp.tool()
    def get_feed_status() -> str:
        """
        Get the status of all data feed connectors.

        Returns which feed is currently active, latency, order book depth,
        and configuration status of all 7 connectors:
        TrueData, Zerodha, Upstox, Fyers, Shoonya, Angel One, Yahoo Finance.

        Use this to understand data quality and suggest upgrades.
        """
        if not _FEED_OK or not feed_manager:
            return json.dumps({"active_feed": "none", "error": "Feed manager not available"})
        return json.dumps(feed_manager.status(), default=str)

    # ── Tool 5: search_symbol ─────────────────────────────────────────────────
    @mcp.tool()
    def search_symbol(query: str, segment: str = "all") -> str:
        """
        Search for stock/index/crypto symbols by name or ticker.

        Args:
            query:   Company name or partial ticker (e.g. "Reliance", "HDFC", "bitcoin")
            segment: Filter by segment: "nse", "bse", "crypto", "index", "all"

        Returns JSON list of matches:
            [{symbol, name, exchange, segment}]

        Common patterns:
            "Reliance"  → RELIANCE.NS
            "Nifty"     → ^NSEI, ^NSEBANK etc.
            "Bitcoin"   → BTC-USD
            "Gold"      → GOLD.MCX or GLD
        """
        if _sym_mapper:
            results = _sym_mapper.search(query, segment)
        else:
            # Basic fallback
            q = query.upper()
            results = [
                s for s in _get_all_symbols()
                if q in s["symbol"].upper() or q in s["name"].upper()
            ]
        return json.dumps(results[:20], default=str)

    # ── Tool 6: get_market_status ──────────────────────────────────────────────
    @mcp.tool()
    def get_market_status() -> str:
        """
        Check if NSE, BSE, and MCX markets are currently open or closed.

        Returns open/closed status for each exchange,
        current time in IST, and day of week.
        Market hours: NSE/BSE 09:15–15:30 IST (Mon–Fri)
                      MCX      09:00–23:30 IST (Mon–Fri)
        """
        return json.dumps(_market_status(), default=str)

    # ── Tool 7: get_top_movers ────────────────────────────────────────────────
    @mcp.tool()
    def get_top_movers(segment: str = "nifty50", limit: int = 5) -> str:
        """
        Get top gainers and losers for a market segment.

        Args:
            segment: "nifty50" | "banknifty" | "crypto" | "fno"
            limit:   Number of top/bottom movers (1-10, default 5)

        Returns JSON with:
            gainers[]: [{symbol, name, price, change_pct}]
            losers[]:  [{symbol, name, price, change_pct}]
            as_of: timestamp
        """
        limit = min(limit, 10)
        syms  = _CRYPTO if segment == "crypto" else _NIFTY50
        data  = []
        for sym in syms[:15]:
            try:
                q = feed_manager.get_quote(sym) if (_FEED_OK and feed_manager) else {}
                if q.get("price"):
                    data.append({
                        "symbol": sym, "name": q.get("name", sym),
                        "price": q.get("price", 0),
                        "change_pct": q.get("change_pct", 0),
                    })
            except Exception:
                pass

        data.sort(key=lambda x: x["change_pct"])
        return json.dumps({
            "segment": segment,
            "gainers": sorted(data, key=lambda x: -x["change_pct"])[:limit],
            "losers":  data[:limit],
            "as_of":   datetime.now().isoformat(),
            "feed":    feed_manager.active_name if (_FEED_OK and feed_manager) else "none",
        }, default=str)

    # ── Tool 8: run_pre_spike_scan ────────────────────────────────────────────
    @mcp.tool()
    def run_pre_spike_scan(symbols: str = "") -> str:
        """
        Run StockGuru's Pre-Spike Detector on a list of symbols.

        Analyzes 6 forensic signals: OI velocity, volume surge, IV percentile,
        PCR delta, EMA reclaim, bid-ask compression. Returns score 0-100.
        Score ≥ 75 = high probability pre-spike detected.

        Args:
            symbols: Comma-separated list of Yahoo symbols.
                     Leave empty for default watchlist.
                     Example: "RELIANCE.NS,HDFCBANK.NS,TCS.NS"

        Returns JSON with top candidates sorted by pre-spike score.
        """
        try:
            sys.path.insert(0, str(_root / "stockguru_agents" / "agents"))
            from spike_detector import compute_pre_spike_score

            sym_list = [s.strip() for s in symbols.split(",")] if symbols else _NIFTY50[:10]
            results  = []
            for sym in sym_list:
                try:
                    r = compute_pre_spike_score(sym, {})
                    results.append({
                        "symbol":   sym,
                        "score":    r.get("score", 0),
                        "signals":  r.get("signals", []),
                        "reason":   r.get("reason", ""),
                        "alert":    r.get("score", 0) >= 75,
                    })
                except Exception:
                    pass
            results.sort(key=lambda x: -x["score"])
            return json.dumps({
                "scan_time": datetime.now().isoformat(),
                "results": results,
                "trigger_threshold": 75,
            }, default=str)
        except ImportError as e:
            return json.dumps({"error": f"spike_detector unavailable: {e}"})


# ── Helper ─────────────────────────────────────────────────────────────────────
def _get_all_symbols():
    """Basic symbol list for search fallback."""
    nse = [
        ("RELIANCE.NS","Reliance Industries","NSE","equity"),
        ("TCS.NS","Tata Consultancy Services","NSE","equity"),
        ("HDFCBANK.NS","HDFC Bank","NSE","equity"),
        ("INFY.NS","Infosys","NSE","equity"),
        ("ICICIBANK.NS","ICICI Bank","NSE","equity"),
        ("SBIN.NS","State Bank of India","NSE","equity"),
        ("AXISBANK.NS","Axis Bank","NSE","equity"),
        ("KOTAKBANK.NS","Kotak Mahindra Bank","NSE","equity"),
        ("HINDUNILVR.NS","Hindustan Unilever","NSE","equity"),
        ("ITC.NS","ITC Limited","NSE","equity"),
        ("LT.NS","Larsen & Toubro","NSE","equity"),
        ("MARUTI.NS","Maruti Suzuki","NSE","equity"),
        ("ASIANPAINT.NS","Asian Paints","NSE","equity"),
        ("HCLTECH.NS","HCL Technologies","NSE","equity"),
        ("WIPRO.NS","Wipro","NSE","equity"),
        ("BAJFINANCE.NS","Bajaj Finance","NSE","equity"),
        ("TITAN.NS","Titan Company","NSE","equity"),
        ("NESTLEIND.NS","Nestle India","NSE","equity"),
        ("ULTRACEMCO.NS","UltraTech Cement","NSE","equity"),
        ("POWERGRID.NS","Power Grid Corp","NSE","equity"),
        ("^NSEI","Nifty 50","NSE","index"),
        ("^NSEBANK","Bank Nifty","NSE","index"),
    ]
    crypto = [
        ("BTC-USD","Bitcoin","CRYPTO","crypto"),
        ("ETH-USD","Ethereum","CRYPTO","crypto"),
        ("BNB-USD","BNB","CRYPTO","crypto"),
        ("SOL-USD","Solana","CRYPTO","crypto"),
        ("XRP-USD","XRP","CRYPTO","crypto"),
    ]
    return [{"symbol":s,"name":n,"exchange":e,"segment":seg} for s,n,e,seg in nse+crypto]


# ══════════════════════════════════════════════════════════════════════════════
# HTTP fallback server (when mcp package not installed)
# ══════════════════════════════════════════════════════════════════════════════

def _run_http_fallback(port: int = 8765):
    """Simple JSON-RPC-style HTTP server as MCP fallback."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            path   = parsed.path

            routes = {
                "/quote":        lambda: feed_manager.get_quote(params.get("symbol","^NSEI")),
                "/orderbook":    lambda: feed_manager.get_orderbook(params.get("symbol","^NSEI"), int(params.get("depth",5))),
                "/candles":      lambda: feed_manager.get_candles(params.get("symbol","^NSEI"), params.get("interval","15m"), params.get("range","5d")),
                "/feed-status":  lambda: feed_manager.status(),
                "/market-status":lambda: _market_status(),
                "/health":       lambda: {"status":"ok","feed": feed_manager.active_name if feed_manager else "none"},
            }
            fn = routes.get(path)
            if fn:
                try:
                    result = fn()
                    body   = json.dumps(result, default=str).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_response(404)
                self.end_headers()

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"📡 StockGuru MCP HTTP fallback running on http://localhost:{port}")
    print(f"   Endpoints: /quote  /orderbook  /candles  /feed-status  /market-status")
    server.serve_forever()


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="StockGuru MCP Market Data Server")
    parser.add_argument("--sse",  action="store_true", help="Run as SSE HTTP server")
    parser.add_argument("--http", action="store_true", help="Run as plain HTTP fallback")
    parser.add_argument("--port", type=int, default=8765, help="Port for HTTP/SSE mode")
    args = parser.parse_args()

    if not _FEED_OK:
        print("⚠️  Feed manager not loaded — data will be unavailable", file=sys.stderr)

    if args.sse:
        run_sse_server(port=args.port)
    elif args.http:
        run_http_server(port=args.port)
    else:
        run_stdio_server()
