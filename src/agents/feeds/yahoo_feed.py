"""
Yahoo Finance Feed — always available, no credentials needed.
15-minute delayed data. Used as the universal fallback.
Uses yfinance library (handles cookies/crumb automatically).
"""
import math
import random
from datetime import datetime
from .base import DataFeed


class YahooFeed(DataFeed):
    NAME        = "yahoo"
    LABEL       = "Yahoo Finance"
    REQUIRED_ENV = []          # no credentials needed
    LATENCY_MS  = 15000        # ~15 min delay
    OB_LEVELS   = 0            # simulated, not real
    IS_REALTIME = False

    def is_configured(self) -> bool:
        return True            # always available

    # ── Quote ──────────────────────────────────────────────────────────────
    def get_quote(self, symbol: str) -> dict:
        try:
            import yfinance as yf
            tk   = yf.Ticker(symbol)
            info = tk.fast_info
            curr = float(getattr(info, "last_price", 0) or getattr(info, "regularMarketPrice", 0) or 0)
            prev = float(getattr(info, "previous_close", curr) or curr)
            return {
                "price":      round(curr, 4),
                "prev_close": round(prev, 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   float(getattr(info, "day_high", curr) or curr),
                "day_low":    float(getattr(info, "day_low",  curr) or curr),
                "volume":     int(getattr(info, "three_month_average_volume", 0) or 0),
                "currency":   getattr(info, "currency", "INR"),
                "name":       symbol,
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    # ── Candles ────────────────────────────────────────────────────────────
    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        # Map range strings to yfinance period
        period_map = {
            "1d": "1d", "5d": "5d", "1mo": "1mo",
            "3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y",
        }
        # Enforce valid yfinance interval/period combos
        valid = {
            "1m":  ["1d"],
            "2m":  ["1d", "5d"],
            "5m":  ["1d", "5d"],
            "15m": ["1d", "5d", "1mo"],
            "30m": ["1d", "5d", "1mo"],
            "60m": ["5d", "1mo", "3mo"],
            "1h":  ["5d", "1mo", "3mo"],
            "1d":  ["1mo", "3mo", "6mo", "1y", "2y"],
            "1wk": ["3mo", "6mo", "1y", "2y"],
        }
        allowed = valid.get(interval, ["5d", "1mo"])
        if range_ not in allowed:
            range_ = allowed[0]
        period = period_map.get(range_, range_)

        try:
            import yfinance as yf
            tk   = yf.Ticker(symbol)
            hist = tk.history(period=period, interval=interval, auto_adjust=True)

            candles = []
            for idx, row in hist.iterrows():
                try:
                    # idx is a pandas Timestamp
                    ts = int(idx.timestamp())
                    o  = float(row["Open"])
                    h  = float(row["High"])
                    l  = float(row["Low"])
                    c  = float(row["Close"])
                    v  = int(row.get("Volume", 0) or 0)
                    if o != o or c != c:  # NaN check
                        continue
                    candles.append({
                        "time":   ts,
                        "open":   round(o, 4),
                        "high":   round(h, 4),
                        "low":    round(l, 4),
                        "close":  round(c, 4),
                        "volume": v,
                    })
                except Exception:
                    continue

            # Get current price metadata
            fast = tk.fast_info
            curr = float(getattr(fast, "last_price", 0) or 0)
            prev = float(getattr(fast, "previous_close", curr) or curr)
            if not curr and candles:
                curr = candles[-1]["close"]
                prev = curr

            return {
                "candles":    candles,
                "symbol":     symbol,
                "name":       symbol,
                "currency":   getattr(fast, "currency", "INR"),
                "price":      round(curr, 4),
                "prev_close": round(prev, 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   float(getattr(fast, "day_high", curr) or curr),
                "day_low":    float(getattr(fast, "day_low",  curr) or curr),
                "volume":     int(getattr(fast, "three_month_average_volume", 0) or 0),
                "interval":   interval,
                "range":      range_,
            }
        except Exception as e:
            return {"candles": [], "error": str(e), "symbol": symbol,
                    "price": 0, "interval": interval, "range": range_}

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
