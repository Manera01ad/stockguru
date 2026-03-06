"""
Angel One SmartAPI Feed  [FREE for Angel customers]
Requires: ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_KEY
pip install smartapi-python pyotp
"""
import os
from datetime import datetime, timedelta
from .base import DataFeed


class AngelFeed(DataFeed):
    NAME         = "angel"
    LABEL        = "Angel One SmartAPI"
    REQUIRED_ENV = ["ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PASSWORD", "ANGEL_TOTP_KEY"]
    LATENCY_MS   = 400
    OB_LEVELS    = 5
    IS_REALTIME  = True

    _smart_api = None

    _SYM_TOKEN_MAP = {
        # Yahoo sym → (exchange, symboltoken)
        "^NSEI":    ("NSE", "99926000"),
        "^NSEBANK": ("NSE", "99926009"),
        "RELIANCE.NS": ("NSE", "2885"),
        "TCS.NS":      ("NSE", "11536"),
        "INFY.NS":     ("NSE", "1594"),
        "HDFCBANK.NS": ("NSE", "1333"),
        "WIPRO.NS":    ("NSE", "3787"),
    }

    def _get_api(self):
        if AngelFeed._smart_api:
            return AngelFeed._smart_api
        try:
            from SmartApi import SmartConnect
            import pyotp
            api = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
            totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_KEY", "")).now()
            data = api.generateSession(
                os.getenv("ANGEL_CLIENT_ID"),
                os.getenv("ANGEL_PASSWORD"),
                totp,
            )
            if data.get("status"):
                AngelFeed._smart_api = api
                return api
            raise ValueError(f"Angel login failed: {data.get('message','unknown')}")
        except ImportError:
            raise ImportError("Run: pip install smartapi-python pyotp")

    def _get_token(self, yahoo_sym: str):
        if yahoo_sym in self._SYM_TOKEN_MAP:
            return self._SYM_TOKEN_MAP[yahoo_sym]
        clean = self._strip_suffix(yahoo_sym)
        exch  = "BSE" if self._is_bse(yahoo_sym) else "NSE"
        # Angel needs symboltoken — for unknown symbols fall back to quote by tradingsymbol
        return (exch, clean)

    def get_quote(self, symbol: str) -> dict:
        try:
            api = self._get_api()
            exch, token = self._get_token(symbol)
            data = api.ltpData(exch, self._strip_suffix(symbol), token)
            if not data.get("status"):
                raise ValueError(data.get("message", "Angel quote error"))
            d    = data["data"]
            curr = float(d.get("ltp", 0))
            return {
                "price":      round(curr, 4),
                "prev_close": 0,
                "change_pct": 0,
                "day_high":   0,
                "day_low":    0,
                "volume":     0,
                "currency":   "INR",
                "name":       symbol,
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    def get_orderbook(self, symbol: str, depth: int = 5) -> dict:
        # Angel SmartAPI returns 5-level depth via marketData
        try:
            api = self._get_api()
            exch, token = self._get_token(symbol)
            data = api.marketData("FULL", [{"exchange": exch, "symboltoken": token,
                                            "tradingsymbol": self._strip_suffix(symbol)}])
            if not data.get("status"):
                raise ValueError(data.get("message", ""))
            rec   = data["data"]["fetched"][0]
            price = float(rec.get("ltp", 0))
            bids_raw = rec.get("depth", {}).get("buy",  [])
            asks_raw = rec.get("depth", {}).get("sell", [])
            bids, asks  = [], []
            cum_b = cum_a = 0
            for row in bids_raw[:5]:
                p, qty = float(row.get("price",0)), int(row.get("quantity",0))
                cum_b += qty; bids.append({"price":p,"qty":qty,"total":cum_b})
            for row in asks_raw[:5]:
                p, qty = float(row.get("price",0)), int(row.get("quantity",0))
                cum_a += qty; asks.append({"price":p,"qty":qty,"total":cum_a})
            best_bid = bids[0]["price"] if bids else 0
            best_ask = asks[0]["price"] if asks else 0
            total    = cum_b + cum_a
            return {"bids":bids,"asks":asks,
                    "spread": round(best_ask-best_bid,4) if best_bid and best_ask else 0,
                    "best_bid":best_bid,"best_ask":best_ask,
                    "buy_pct": round(cum_b/total*100) if total else 50,
                    "sell_pct":round(cum_a/total*100) if total else 50,
                    "price":price,"note":"live"}
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_orderbook(symbol, depth)

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        try:
            api = self._get_api()
            exch, token = self._get_token(symbol)
            tf_map = {"1m":"ONE_MINUTE","5m":"FIVE_MINUTE","15m":"FIFTEEN_MINUTE",
                      "30m":"THIRTY_MINUTE","60m":"ONE_HOUR","1h":"ONE_HOUR",
                      "1d":"ONE_DAY","1wk":"ONE_WEEK","1mo":"ONE_MONTH"}
            days = {"1d":1,"5d":5,"1mo":30,"3mo":90,"6mo":180,"1y":365}.get(range_, 5)
            from_dt = (datetime.now()-timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
            to_dt   = datetime.now().strftime("%Y-%m-%d %H:%M")
            data = api.getCandleData({
                "exchange": exch, "symboltoken": token,
                "interval": tf_map.get(interval, "FIFTEEN_MINUTE"),
                "fromdate": from_dt, "todate": to_dt,
            })
            if not data.get("status"):
                raise ValueError(data.get("message",""))
            candles = []
            for row in data["data"]:
                try:
                    ts = int(datetime.fromisoformat(row[0]).timestamp())
                    candles.append({"time":ts,"open":round(row[1],4),"high":round(row[2],4),
                                    "low":round(row[3],4),"close":round(row[4],4),"volume":int(row[5])})
                except: continue
            candles.sort(key=lambda x: x["time"])
            q = self.get_quote(symbol)
            return {"candles":candles,"symbol":symbol,"name":symbol,"currency":"INR",
                    **{k:q.get(k,0) for k in ("price","prev_close","change_pct","day_high","day_low","volume")},
                    "interval":interval,"range":range_}
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
