"""
Fyers API v3 Feed  [FREE for Fyers customers]
Requires: FYERS_CLIENT_ID, FYERS_ACCESS_TOKEN
pip install fyers-apiv3
Docs: https://myapi.fyers.in/docs
"""
import os
from datetime import datetime, timedelta
from .base import DataFeed


class FyersFeed(DataFeed):
    NAME         = "fyers"
    LABEL        = "Fyers API v3"
    REQUIRED_ENV = ["FYERS_CLIENT_ID", "FYERS_ACCESS_TOKEN"]
    LATENCY_MS   = 300
    OB_LEVELS    = 5
    IS_REALTIME  = True

    _SYM_MAP = {
        "^NSEI":    "NSE:NIFTY50-INDEX",
        "^NSEBANK": "NSE:NIFTYBANK-INDEX",
        "BTC-USD":  "MCX:BITCOINUSDT-FUT",
    }
    _TF_MAP = {
        "1m":"1","2m":"2","3m":"3","5m":"5","10m":"10","15m":"15",
        "20m":"20","30m":"30","60m":"60","1h":"60",
        "1d":"D","1wk":"W","1mo":"M",
    }

    def _to_fyers_sym(self, yahoo_sym: str) -> str:
        if yahoo_sym in self._SYM_MAP:
            return self._SYM_MAP[yahoo_sym]
        clean = self._strip_suffix(yahoo_sym)
        if self._is_bse(yahoo_sym):
            return f"BSE:{clean}-A"
        return f"NSE:{clean}-EQ"

    def _get_api(self):
        try:
            from fyers_apiv3 import fyersModel
            api = fyersModel.FyersModel(
                client_id=os.getenv("FYERS_CLIENT_ID"),
                token=os.getenv("FYERS_ACCESS_TOKEN"),
                is_async=False, log_path="",
            )
            return api
        except ImportError:
            raise ImportError("Run: pip install fyers-apiv3")

    def get_quote(self, symbol: str) -> dict:
        try:
            api = self._get_api()
            fyers_sym = self._to_fyers_sym(symbol)
            data = api.quotes({"symbols": fyers_sym})
            if data.get("s") != "ok":
                raise ValueError(data.get("message", "Fyers quote error"))
            d    = data["d"][0]["v"]
            curr = float(d.get("lp", 0))
            prev = float(d.get("prev_close_price", curr) or curr)
            return {
                "price":      round(curr, 4),
                "prev_close": round(prev, 4),
                "change_pct": round(((curr-prev)/prev)*100, 2) if prev else 0,
                "day_high":   float(d.get("high_price", curr)),
                "day_low":    float(d.get("low_price",  curr)),
                "volume":     int(d.get("volume", 0)),
                "currency":   "INR",
                "name":       d.get("description", symbol),
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    def get_orderbook(self, symbol: str, depth: int = 5) -> dict:
        try:
            api = self._get_api()
            fyers_sym = self._to_fyers_sym(symbol)
            data = api.depth({"symbol": fyers_sym, "ohlcv_flag": 1})
            if data.get("s") != "ok":
                raise ValueError(data.get("message", ""))
            d     = data["d"]
            price = float(d.get("ltp", 0))
            bids_raw = d.get("bids", [])[:5]
            asks_raw = d.get("ask",  [])[:5]
            bids, asks  = [], []
            cum_b = cum_a = 0
            for row in bids_raw:
                p, qty = float(row.get("price",0)), int(row.get("volume",0))
                cum_b += qty; bids.append({"price":p,"qty":qty,"total":cum_b})
            for row in asks_raw:
                p, qty = float(row.get("price",0)), int(row.get("volume",0))
                cum_a += qty; asks.append({"price":p,"qty":qty,"total":cum_a})
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
            api = self._get_api()
            fyers_sym = self._to_fyers_sym(symbol)
            days    = {"1d":1,"5d":5,"1mo":30,"3mo":90,"6mo":180,"1y":365}.get(range_, 5)
            to_ts   = int(datetime.now().timestamp())
            from_ts = int((datetime.now()-timedelta(days=days)).timestamp())
            data = api.history({
                "symbol": fyers_sym,
                "resolution": self._TF_MAP.get(interval, "15"),
                "date_format": "0",
                "range_from": str(from_ts),
                "range_to":   str(to_ts),
                "cont_flag":  "1",
            })
            if data.get("s") != "ok":
                raise ValueError(data.get("message",""))
            candles = []
            for row in data.get("candles", []):
                candles.append({"time":int(row[0]),"open":round(row[1],4),"high":round(row[2],4),
                                "low":round(row[3],4),"close":round(row[4],4),"volume":int(row[5])})
            candles.sort(key=lambda x: x["time"])
            q = self.get_quote(symbol)
            return {"candles":candles,"symbol":symbol,"name":symbol,"currency":"INR",
                    **{k:q.get(k,0) for k in ("price","prev_close","change_pct","day_high","day_low","volume")},
                    "interval":interval,"range":range_}
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
