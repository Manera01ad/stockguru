"""
Upstox v2 Feed — WebSocket + REST
Requires: UPSTOX_ACCESS_TOKEN in .env
Token expires daily — regenerate from https://upstox.com/developer/api-documentation/
"""
import os
import math
import random
import requests
from datetime import datetime, timedelta
from .base import DataFeed


class UpstoxFeed(DataFeed):
    NAME        = "upstox"
    LABEL       = "Upstox v2"
    REQUIRED_ENV = ["UPSTOX_ACCESS_TOKEN"]
    LATENCY_MS  = 200
    OB_LEVELS   = 5
    IS_REALTIME = True

    BASE = "https://api.upstox.com/v2"

    # ── Instrument key mapping (Yahoo sym → Upstox instrument_key) ──────────
    # Upstox uses "NSE_EQ|{ISIN}" or "NSE_EQ|{symbol}" format
    # For simplicity we use the simpler symbol-based key which works for most NSE equities
    _SYM_MAP = {
        "^NSEI":    "NSE_INDEX|Nifty 50",
        "^NSEBANK": "NSE_INDEX|Nifty Bank",
        "BTC-USD":  "MCX_FO|BITCOINUSDT",
    }

    def _headers(self) -> dict:
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "")
        return {
            "Authorization": f"Bearer {token}",
            "Accept":        "application/json",
        }

    def _to_instrument_key(self, yahoo_sym: str) -> str:
        if yahoo_sym in self._SYM_MAP:
            return self._SYM_MAP[yahoo_sym]
        clean = self._strip_suffix(yahoo_sym)
        exchange = "BSE_EQ" if self._is_bse(yahoo_sym) else "NSE_EQ"
        return f"{exchange}|{clean}"

    def _to_historical_key(self, yahoo_sym: str) -> str:
        """URL-encode the instrument key for historical endpoints."""
        import urllib.parse
        return urllib.parse.quote(self._to_instrument_key(yahoo_sym), safe="")

    # ── Interval/period mapping ────────────────────────────────────────────
    _INTERVAL_MAP = {
        "1m": "1minute",  "2m": "2minute",  "5m": "5minute",
        "15m": "15minute","30m": "30minute","60m": "60minute",
        "1h": "60minute", "1d": "day",      "1wk": "week",  "1mo": "month",
    }

    # ── Quote ──────────────────────────────────────────────────────────────
    def get_quote(self, symbol: str) -> dict:
        try:
            import urllib.parse
            key = urllib.parse.quote(self._to_instrument_key(symbol), safe="")
            r   = requests.get(
                f"{self.BASE}/market-quote/quotes?symbol={key}",
                headers=self._headers(), timeout=6
            )
            data = r.json()
            if data.get("status") != "success":
                raise ValueError(data.get("message", "Upstox API error"))

            q = list(data["data"].values())[0]
            curr = q.get("last_price", 0)
            prev = q.get("close_price", curr) or curr
            return {
                "price":      round(float(curr), 4),
                "prev_close": round(float(prev), 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   q.get("ohlc", {}).get("high", curr),
                "day_low":    q.get("ohlc", {}).get("low",  curr),
                "volume":     q.get("volume", 0),
                "currency":   "INR",
                "name":       symbol,
                "bid":        q.get("depth", {}).get("buy",  [{}])[0].get("price", 0),
                "ask":        q.get("depth", {}).get("sell", [{}])[0].get("price", 0),
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    # ── Order book ─────────────────────────────────────────────────────────
    def get_orderbook(self, symbol: str, depth: int = 5) -> dict:
        try:
            import urllib.parse
            key = urllib.parse.quote(self._to_instrument_key(symbol), safe="")
            r   = requests.get(
                f"{self.BASE}/market-quote/quotes?symbol={key}",
                headers=self._headers(), timeout=6
            )
            data = r.json()
            if data.get("status") != "success":
                raise ValueError(data.get("message", "Upstox API error"))

            q     = list(data["data"].values())[0]
            price = q.get("last_price", 0)
            ob    = q.get("depth", {})

            raw_bids = ob.get("buy",  [])[:5]
            raw_asks = ob.get("sell", [])[:5]

            bids, asks = [], []
            cum_b = cum_a = 0
            for row in raw_bids:
                p, qty = row.get("price", 0), row.get("quantity", 0)
                cum_b += qty
                bids.append({"price": p, "qty": qty, "total": cum_b,
                             "orders": row.get("orders", 0)})
            for row in raw_asks:
                p, qty = row.get("price", 0), row.get("quantity", 0)
                cum_a += qty
                asks.append({"price": p, "qty": qty, "total": cum_a,
                             "orders": row.get("orders", 0)})

            best_bid = bids[0]["price"] if bids else 0
            best_ask = asks[0]["price"] if asks else 0
            spread   = round(best_ask - best_bid, 4) if (best_bid and best_ask) else 0
            total    = cum_b + cum_a

            return {
                "bids": bids, "asks": asks,
                "spread": spread,
                "best_bid": best_bid, "best_ask": best_ask,
                "buy_pct":  round(cum_b / total * 100) if total else 50,
                "sell_pct": round(cum_a / total * 100) if total else 50,
                "price": price,
                "note": "live",
            }
        except Exception as e:
            # Fallback to simulated on error
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_orderbook(symbol, depth)

    # ── Candles ────────────────────────────────────────────────────────────
    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        try:
            tf      = self._INTERVAL_MAP.get(interval, "15minute")
            key_enc = self._to_historical_key(symbol)
            to_dt   = datetime.now().strftime("%Y-%m-%d")
            days    = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90,
                       "6mo": 180, "1y": 365, "2y": 730}.get(range_, 5)
            from_dt = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            url = f"{self.BASE}/historical-candle/{key_enc}/{tf}/{to_dt}/{from_dt}"
            r   = requests.get(url, headers=self._headers(), timeout=10)
            data = r.json()

            if data.get("status") != "success":
                raise ValueError(data.get("message", "No data"))

            raw_candles = data.get("data", {}).get("candles", [])
            candles = []
            for row in raw_candles:
                # Upstox format: [timestamp, open, high, low, close, volume, oi]
                ts, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
                from datetime import timezone
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts = int(dt.timestamp())
                candles.append({
                    "time": int(ts), "open": round(o, 4), "high": round(h, 4),
                    "low": round(l, 4), "close": round(c, 4), "volume": int(v or 0),
                })

            # Sort ascending
            candles.sort(key=lambda x: x["time"])

            # Get current quote for price/stats
            q = self.get_quote(symbol)
            return {
                "candles":    candles,
                "symbol":     symbol,
                "name":       symbol,
                "currency":   "INR",
                "price":      q.get("price", 0),
                "prev_close": q.get("prev_close", 0),
                "change_pct": q.get("change_pct", 0),
                "day_high":   q.get("day_high", 0),
                "day_low":    q.get("day_low", 0),
                "volume":     q.get("volume", 0),
                "interval":   interval,
                "range":      range_,
            }
        except Exception as e:
            # Fallback to Yahoo for candles
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
