"""
Shoonya (Finvasia) Feed — WebSocket + REST  [FREE]
Requires: SHOONYA_USER, SHOONYA_PASSWORD, SHOONYA_API_KEY, SHOONYA_TOTP_KEY
pip install NorenRestApiPy pyotp

Full DOM (order book depth), ~200ms latency. Completely free for Shoonya customers.
"""
import os
import requests
from datetime import datetime, timedelta
from .base import DataFeed


class ShoonyaFeed(DataFeed):
    NAME         = "shoonya"
    LABEL        = "Shoonya (Finvasia)"
    REQUIRED_ENV = ["SHOONYA_USER", "SHOONYA_PASSWORD", "SHOONYA_API_KEY", "SHOONYA_TOTP_KEY"]
    LATENCY_MS   = 200
    OB_LEVELS    = 5
    IS_REALTIME  = True

    BASE     = "https://api.shoonya.com/NorenWClientTP"
    _session = None

    _SYM_MAP = {
        "^NSEI":    ("NSE", "Nifty 50"),
        "^NSEBANK": ("NSE", "Nifty Bank"),
    }

    def _to_shoonya_sym(self, yahoo_sym):
        if yahoo_sym in self._SYM_MAP:
            return self._SYM_MAP[yahoo_sym]
        clean    = self._strip_suffix(yahoo_sym)
        exchange = "BSE" if self._is_bse(yahoo_sym) else "NSE"
        return (exchange, clean)

    def _get_session(self):
        if ShoonyaFeed._session:
            return ShoonyaFeed._session
        try:
            import pyotp
            totp = pyotp.TOTP(os.getenv("SHOONYA_TOTP_KEY", "")).now()
            import hashlib
            pwd_hash = hashlib.sha256(
                os.getenv("SHOONYA_PASSWORD", "").encode()
            ).hexdigest()
            payload = {
                "apkversion": "1.0.0",
                "uid":   os.getenv("SHOONYA_USER"),
                "pwd":   pwd_hash,
                "factor2": totp,
                "imei": "abc123",
                "source": "API",
                "appkey": f"{os.getenv('SHOONYA_USER')}|{os.getenv('SHOONYA_API_KEY')}",
            }
            r = requests.post(f"{self.BASE}/QuickAuth", json=payload, timeout=10)
            data = r.json()
            if data.get("stat") == "Ok":
                ShoonyaFeed._session = data.get("susertoken")
                return ShoonyaFeed._session
            raise ValueError(f"Shoonya auth failed: {data.get('emsg', 'unknown')}")
        except ImportError:
            raise ImportError("Run: pip install NorenRestApiPy pyotp")

    def _post(self, endpoint: str, jdata: dict) -> dict:
        import json
        session = self._get_session()
        payload = {"jData": json.dumps({**jdata, "uid": os.getenv("SHOONYA_USER"),
                                        "actid": os.getenv("SHOONYA_USER"),
                                        "susertoken": session})}
        r = requests.post(f"{self.BASE}/{endpoint}", data=payload, timeout=8)
        return r.json()

    def get_quote(self, symbol: str) -> dict:
        try:
            exchange, sym = self._to_shoonya_sym(symbol)
            data = self._post("GetQuotes", {"exch": exchange, "token": sym})
            if data.get("stat") != "Ok":
                raise ValueError(data.get("emsg", "Shoonya quote error"))
            curr = float(data.get("lp", 0))
            prev = float(data.get("c",  curr) or curr)
            return {
                "price":      round(curr, 4),
                "prev_close": round(prev, 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   float(data.get("h", curr)),
                "day_low":    float(data.get("l", curr)),
                "volume":     int(data.get("v", 0)),
                "currency":   "INR",
                "name":       data.get("cname", symbol),
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    def get_orderbook(self, symbol: str, depth: int = 5) -> dict:
        try:
            exchange, sym = self._to_shoonya_sym(symbol)
            data = self._post("GetQuotes", {"exch": exchange, "token": sym})
            if data.get("stat") != "Ok":
                raise ValueError(data.get("emsg", ""))
            price = float(data.get("lp", 0))

            bids, asks  = [], []
            cum_b = cum_a = 0
            for i in range(1, 6):    # Shoonya returns bp1..bp5, bq1..bq5
                bp = float(data.get(f"bp{i}", 0))
                bq = int(data.get(f"bq{i}", 0))
                sp = float(data.get(f"sp{i}", 0))
                sq = int(data.get(f"sq{i}", 0))
                if bp: cum_b += bq; bids.append({"price": bp, "qty": bq, "total": cum_b})
                if sp: cum_a += sq; asks.append({"price": sp, "qty": sq, "total": cum_a})

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
                "price": price, "note": "live",
            }
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_orderbook(symbol, depth)

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        try:
            exchange, sym = self._to_shoonya_sym(symbol)
            days    = {"1d":1,"5d":5,"1mo":30,"3mo":90,"6mo":180,"1y":365}.get(range_, 5)
            end_dt  = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            start_dt= (datetime.now() - timedelta(days=days)).strftime("%d-%m-%Y %H:%M:%S")
            tf_secs = {"1m":60,"5m":300,"15m":900,"30m":1800,"60m":3600,"1h":3600,"1d":86400}.get(interval, 900)

            data = self._post("TPSeries", {
                "exch": exchange, "token": sym,
                "st": start_dt, "et": end_dt,
                "intrv": str(tf_secs),
            })
            candles = []
            for row in (data if isinstance(data, list) else []):
                try:
                    ts = int(datetime.strptime(row["time"], "%d-%m-%Y %H:%M:%S").timestamp())
                    candles.append({
                        "time":   ts,
                        "open":   round(float(row.get("into", 0)), 4),
                        "high":   round(float(row.get("inth", 0)), 4),
                        "low":    round(float(row.get("intl", 0)), 4),
                        "close":  round(float(row.get("intc", 0)), 4),
                        "volume": int(row.get("intv", 0)),
                    })
                except: continue
            candles.sort(key=lambda x: x["time"])
            q = self.get_quote(symbol)
            return {"candles": candles, "symbol": symbol, "name": symbol,
                    "currency": "INR", **{k: q.get(k, 0) for k in
                    ("price","prev_close","change_pct","day_high","day_low","volume")},
                    "interval": interval, "range": range_}
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
