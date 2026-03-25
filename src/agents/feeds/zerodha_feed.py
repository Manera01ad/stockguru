"""
Zerodha KiteConnect Feed  [₹2,000/month]
Requires: KITE_API_KEY, KITE_ACCESS_TOKEN
pip install kiteconnect
Token expires daily — regenerate from Kite developer console.
Docs: https://kite.trade/docs/connect/v3/
"""
import os
from datetime import datetime, timedelta
from .base import DataFeed


class ZerodhaFeed(DataFeed):
    NAME         = "zerodha"
    LABEL        = "Zerodha KiteConnect"
    REQUIRED_ENV = ["KITE_API_KEY", "KITE_ACCESS_TOKEN"]
    LATENCY_MS   = 200
    OB_LEVELS    = 5
    IS_REALTIME  = True

    _SYM_MAP = {
        "^NSEI":    ("NSE", "NIFTY 50"),
        "^NSEBANK": ("NSE", "NIFTY BANK"),
        "BTC-USD":  ("CDS", "BTCUSDT"),
    }
    _TF_MAP = {
        "1m":"minute","3m":"3minute","5m":"5minute","10m":"10minute",
        "15m":"15minute","30m":"30minute","60m":"60minute","1h":"60minute",
        "1d":"day","1wk":"week","1mo":"month",
    }

    def _to_kite_sym(self, yahoo_sym):
        if yahoo_sym in self._SYM_MAP:
            return self._SYM_MAP[yahoo_sym]
        clean = self._strip_suffix(yahoo_sym)
        exch  = "BSE" if self._is_bse(yahoo_sym) else "NSE"
        return (exch, clean)

    def _get_kite(self):
        try:
            from kiteconnect import KiteConnect
            kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
            kite.set_access_token(os.getenv("KITE_ACCESS_TOKEN"))
            return kite
        except ImportError:
            raise ImportError("Run: pip install kiteconnect")

    def get_quote(self, symbol: str) -> dict:
        try:
            kite = self._get_kite()
            exch, sym = self._to_kite_sym(symbol)
            instrument = f"{exch}:{sym}"
            data = kite.quote([instrument])
            d    = data.get(instrument, {})
            curr = float(d.get("last_price", 0))
            ohlc = d.get("ohlc", {})
            prev = float(ohlc.get("close", curr) or curr)
            return {
                "price":      round(curr, 4),
                "prev_close": round(prev, 4),
                "change_pct": round(((curr-prev)/prev)*100, 2) if prev else 0,
                "day_high":   float(ohlc.get("high", curr)),
                "day_low":    float(ohlc.get("low",  curr)),
                "volume":     int(d.get("volume", 0)),
                "currency":   "INR",
                "name":       sym,
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    def get_orderbook(self, symbol: str, depth: int = 5) -> dict:
        try:
            kite = self._get_kite()
            exch, sym = self._to_kite_sym(symbol)
            instrument = f"{exch}:{sym}"
            data  = kite.quote([instrument])
            d     = data.get(instrument, {})
            price = float(d.get("last_price", 0))
            depth_data = d.get("depth", {})
            bids_raw = depth_data.get("buy",  [])[:5]
            asks_raw = depth_data.get("sell", [])[:5]
            bids, asks  = [], []
            cum_b = cum_a = 0
            for row in bids_raw:
                p, qty = float(row.get("price",0)), int(row.get("quantity",0))
                cum_b += qty; bids.append({"price":p,"qty":qty,"total":cum_b,"orders":row.get("orders",0)})
            for row in asks_raw:
                p, qty = float(row.get("price",0)), int(row.get("quantity",0))
                cum_a += qty; asks.append({"price":p,"qty":qty,"total":cum_a,"orders":row.get("orders",0)})
            best_bid = bids[0]["price"] if bids else 0
            best_ask = asks[0]["price"] if asks else 0
            total    = cum_b + cum_a
            return {"bids":bids,"asks":asks,
                    "spread":round(best_ask-best_bid,4) if best_bid and best_ask else 0,
                    "best_bid":best_bid,"best_ask":best_ask,
                    "buy_pct":round(cum_b/total*100) if total else 50,
                    "sell_pct":round(cum_a/total*100) if total else 50,
                    "price":price,"note":"live"}
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_orderbook(symbol, depth)

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        try:
            kite = self._get_kite()
            exch, sym = self._to_kite_sym(symbol)
            instrument = f"{exch}:{sym}"
            days    = {"1d":1,"5d":5,"1mo":30,"3mo":90,"6mo":180,"1y":365}.get(range_, 5)
            to_dt   = datetime.now()
            from_dt = to_dt - timedelta(days=days)
            data = kite.historical_data(
                kite.ltp([instrument])[instrument]["instrument_token"],
                from_dt.strftime("%Y-%m-%d %H:%M:%S"),
                to_dt.strftime("%Y-%m-%d %H:%M:%S"),
                self._TF_MAP.get(interval, "15minute"),
            )
            candles = []
            for row in data:
                ts = int(row["date"].timestamp()) if hasattr(row["date"],"timestamp") else int(row["date"])
                candles.append({"time":ts,"open":round(row["open"],4),"high":round(row["high"],4),
                                "low":round(row["low"],4),"close":round(row["close"],4),"volume":int(row["volume"])})
            candles.sort(key=lambda x: x["time"])
            q = self.get_quote(symbol)
            return {"candles":candles,"symbol":symbol,"name":symbol,"currency":"INR",
                    **{k:q.get(k,0) for k in ("price","prev_close","change_pct","day_high","day_low","volume")},
                    "interval":interval,"range":range_}
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
