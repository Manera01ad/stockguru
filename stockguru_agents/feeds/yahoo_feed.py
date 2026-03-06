"""
Yahoo Finance Feed — always available, no credentials needed.
15-minute delayed data. Used as the universal fallback.
"""
import math
import random
import requests
from datetime import datetime
from .base import DataFeed


class YahooFeed(DataFeed):
    NAME        = "yahoo"
    LABEL       = "Yahoo Finance"
    REQUIRED_ENV = []          # no credentials needed
    LATENCY_MS  = 15000        # ~15 min delay
    OB_LEVELS   = 0            # simulated, not real
    IS_REALTIME = False

    _HEADERS = {"User-Agent": "Mozilla/5.0"}

    def is_configured(self) -> bool:
        return True            # always available

    # ── Quote ──────────────────────────────────────────────────────────────
    def get_quote(self, symbol: str) -> dict:
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                   f"?interval=1m&range=1d")
            r    = requests.get(url, headers=self._HEADERS, timeout=8)
            meta = r.json()["chart"]["result"][0]["meta"]
            curr = meta.get("regularMarketPrice", 0)
            prev = meta.get("chartPreviousClose", curr) or curr
            return {
                "price":      round(float(curr), 4),
                "prev_close": round(float(prev), 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   meta.get("regularMarketDayHigh", curr),
                "day_low":    meta.get("regularMarketDayLow",  curr),
                "volume":     meta.get("regularMarketVolume",  0),
                "currency":   meta.get("currency", "INR"),
                "name":       meta.get("longName", meta.get("shortName", symbol)),
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    # ── Candles ────────────────────────────────────────────────────────────
    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        # Enforce valid Yahoo interval/range combos
        valid = {
            "1m":  ["1d"],
            "2m":  ["1d","5d"],
            "5m":  ["1d","5d"],
            "15m": ["1d","5d","1mo"],
            "30m": ["1d","5d","1mo"],
            "60m": ["5d","1mo","3mo"],
            "1h":  ["5d","1mo","3mo"],
            "1d":  ["1mo","3mo","6mo","1y","2y","5y"],
            "1wk": ["3mo","6mo","1y","2y","5y"],
            "1mo": ["1y","2y","5y"],
        }
        allowed = valid.get(interval, ["1d","5d","1mo"])
        if range_ not in allowed:
            range_ = allowed[0]

        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                   f"?interval={interval}&range={range_}&includePrePost=false")
            r   = requests.get(url, headers=self._HEADERS, timeout=10)
            d   = r.json()
            res = d.get("chart", {}).get("result", [])
            if not res:
                return {"candles": [], "error": "No data"}

            res    = res[0]
            meta   = res.get("meta", {})
            ts_lst = res.get("timestamp", [])
            q      = res.get("indicators", {}).get("quote", [{}])[0]

            candles = []
            for i, ts in enumerate(ts_lst):
                o = q.get("open",   [None]*len(ts_lst))[i]
                h = q.get("high",   [None]*len(ts_lst))[i]
                l = q.get("low",    [None]*len(ts_lst))[i]
                c = q.get("close",  [None]*len(ts_lst))[i]
                v = q.get("volume", [0]*len(ts_lst))[i]
                if None in (o, h, l, c) or o != o:
                    continue
                candles.append({
                    "time":   int(ts),
                    "open":   round(float(o), 4),
                    "high":   round(float(h), 4),
                    "low":    round(float(l), 4),
                    "close":  round(float(c), 4),
                    "volume": int(v or 0),
                })

            curr = meta.get("regularMarketPrice", 0)
            prev = meta.get("chartPreviousClose", curr) or curr
            return {
                "candles":    candles,
                "symbol":     symbol,
                "name":       meta.get("longName", meta.get("shortName", symbol)),
                "currency":   meta.get("currency", "INR"),
                "price":      round(float(curr), 4),
                "prev_close": round(float(prev), 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   meta.get("regularMarketDayHigh", curr),
                "day_low":    meta.get("regularMarketDayLow",  curr),
                "volume":     meta.get("regularMarketVolume",  0),
                "interval":   interval,
                "range":      range_,
            }
        except Exception as e:
            return {"candles": [], "error": str(e)}

    # ── Order book (simulated) ─────────────────────────────────────────────
    def get_orderbook(self, symbol: str, depth: int = 15) -> dict:
        quote = self.get_quote(symbol)
        price = quote.get("price", 0)
        if not price:
            return {"bids": [], "asks": [], "spread": 0, "price": 0,
                    "note": "simulated"}

        # Tick size (Indian market rules)
        if "BTC" in symbol or "ETH" in symbol or "USD" in symbol:
            tick = round(price * 0.0001, 6)
        elif symbol in ("^NSEI", "^NSEBANK"):
            tick = 0.10
        elif price >= 50:
            tick = 0.05
        else:
            tick = 0.01

        best_bid = round(math.floor(price / tick) * tick, 4)
        best_ask = round(best_bid + tick, 4)
        spread   = round(best_ask - best_bid, 4)

        rnd = random.Random(int(price * 100) % 9999 + datetime.now().minute)

        def _qty(lvl):
            base = max(50, int(10_000 / max(price, 1)))
            return round(base * max(0.2, 1.5 - lvl * 0.08 + rnd.uniform(-0.3, 0.5)))

        asks, bids = [], []
        cum_a = cum_b = 0
        for i in range(depth):
            aq = _qty(i); cum_a += aq
            asks.append({"price": round(best_ask + i * tick, 4),
                         "qty": aq, "total": round(cum_a)})
            bq = _qty(i); cum_b += bq
            bids.append({"price": round(best_bid - i * tick, 4),
                         "qty": bq, "total": round(cum_b)})

        total = cum_a + cum_b
        return {
            "bids": bids, "asks": asks,
            "spread": spread,
            "best_bid": best_bid, "best_ask": best_ask,
            "buy_pct":  round(cum_b / total * 100) if total else 50,
            "sell_pct": round(cum_a / total * 100) if total else 50,
            "price": price,
            "note": "simulated",
        }
