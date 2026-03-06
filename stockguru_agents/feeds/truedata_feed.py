"""
TrueData Feed — WebSocket + REST
Requires: TRUEDATA_USERNAME, TRUEDATA_PASSWORD in .env
Subscription: https://truedata.in  (~₹800/month)
20-level live order book, ~100ms latency, all segments (NSE/BSE/MCX/NCDEX).
"""
import os
import requests
from datetime import datetime, timedelta
from .base import DataFeed


class TrueDataFeed(DataFeed):
    NAME         = "truedata"
    LABEL        = "TrueData"
    REQUIRED_ENV = ["TRUEDATA_USERNAME", "TRUEDATA_PASSWORD"]
    LATENCY_MS   = 100
    OB_LEVELS    = 20
    IS_REALTIME  = True

    REST_URL = "https://api.truedata.in"
    _token   = None
    _token_expiry = None

    # ── Symbol mapping ─────────────────────────────────────────────────────
    # TrueData uses "RELIANCE-EQ", "NIFTY 50", "USDINR" etc.
    _SYM_MAP = {
        "^NSEI":    "NIFTY 50",
        "^NSEBANK": "BANKNIFTY",
        "BTC-USD":  "BITCOINUSDT",
        "ETH-USD":  "ETHUSD",
    }

    def _to_td_symbol(self, yahoo_sym: str) -> str:
        if yahoo_sym in self._SYM_MAP:
            return self._SYM_MAP[yahoo_sym]
        clean = self._strip_suffix(yahoo_sym)
        suffix = "-BE" if self._is_bse(yahoo_sym) else "-EQ"
        return f"{clean}{suffix}"

    # ── Auth ───────────────────────────────────────────────────────────────
    def _get_token(self) -> str:
        now = datetime.now()
        if self._token and self._token_expiry and now < self._token_expiry:
            return self._token
        r = requests.post(
            f"{self.REST_URL}/users/login",
            json={
                "user_id":  os.getenv("TRUEDATA_USERNAME"),
                "password": os.getenv("TRUEDATA_PASSWORD"),
            },
            timeout=10,
        )
        data = r.json()
        if not data.get("Authorization"):
            raise ValueError(f"TrueData login failed: {data.get('message', 'unknown')}")
        TrueDataFeed._token        = data["Authorization"]
        TrueDataFeed._token_expiry = now + timedelta(hours=23)
        return TrueDataFeed._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type":  "application/json",
        }

    # ── Quote ──────────────────────────────────────────────────────────────
    def get_quote(self, symbol: str) -> dict:
        try:
            td_sym = self._to_td_symbol(symbol)
            r = requests.get(
                f"{self.REST_URL}/marketdata/ltp",
                params={"symbollist": td_sym},
                headers=self._headers(),
                timeout=6,
            )
            data = r.json()
            records = data.get("Records", [])
            if not records:
                raise ValueError("No records returned")
            rec  = records[0]
            curr = float(rec.get("LTP", 0))
            prev = float(rec.get("PrevClose", curr) or curr)
            return {
                "price":      round(curr, 4),
                "prev_close": round(prev, 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   float(rec.get("High", curr)),
                "day_low":    float(rec.get("Low",  curr)),
                "volume":     int(rec.get("Volume", 0)),
                "currency":   "INR",
                "name":       rec.get("Symbol", symbol),
                "bid":        float(rec.get("BidPrice", 0)),
                "ask":        float(rec.get("AskPrice", 0)),
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    # ── Order book ─────────────────────────────────────────────────────────
    def get_orderbook(self, symbol: str, depth: int = 20) -> dict:
        try:
            td_sym = self._to_td_symbol(symbol)
            r = requests.get(
                f"{self.REST_URL}/marketdata/marketdepth",
                params={"symbollist": td_sym, "depth": min(depth, 20)},
                headers=self._headers(),
                timeout=6,
            )
            data    = r.json()
            records = data.get("Records", [])
            if not records:
                raise ValueError("No order book data")

            rec      = records[0]
            price    = float(rec.get("LTP", 0))
            raw_bids = rec.get("Bids", [])
            raw_asks = rec.get("Asks", [])

            bids, asks  = [], []
            cum_b = cum_a = 0
            for row in raw_bids[:depth]:
                p, qty = float(row.get("Price", 0)), int(row.get("Quantity", 0))
                cum_b += qty
                bids.append({"price": p, "qty": qty, "total": cum_b,
                             "orders": row.get("NumberOfOrders", 0)})
            for row in raw_asks[:depth]:
                p, qty = float(row.get("Price", 0)), int(row.get("Quantity", 0))
                cum_a += qty
                asks.append({"price": p, "qty": qty, "total": cum_a,
                             "orders": row.get("NumberOfOrders", 0)})

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
            from .yahoo_feed import YahooFeed
            result = YahooFeed().get_orderbook(symbol, depth)
            result["note"] = f"simulated (TrueData err: {e})"
            return result

    # ── Candles ────────────────────────────────────────────────────────────
    _TF_MAP = {
        "1m": "1", "2m": "2", "3m": "3", "5m": "5",
        "10m": "10", "15m": "15", "30m": "30", "60m": "60",
        "1h": "60", "1d": "eod", "1wk": "eod", "1mo": "eod",
    }
    _DAYS_MAP = {
        "1d": 1, "5d": 5, "1mo": 30, "3mo": 90,
        "6mo": 180, "1y": 365, "2y": 730,
    }

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        try:
            td_sym  = self._to_td_symbol(symbol)
            tf      = self._TF_MAP.get(interval, "5")
            days    = self._DAYS_MAP.get(range_, 5)
            end_dt  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            start_dt= (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

            endpoint = "eoddata" if tf == "eod" else "barsdata"
            r = requests.get(
                f"{self.REST_URL}/marketdata/{endpoint}",
                params={
                    "symbollist": td_sym,
                    "duration":   tf,
                    "bidask":     "false",
                    "from":       start_dt,
                    "to":         end_dt,
                },
                headers=self._headers(),
                timeout=15,
            )
            data = r.json()
            raw  = data.get("Records", [])

            candles = []
            for rec in raw:
                # TrueData candle fields
                ts_str = rec.get("Timestamp") or rec.get("Date", "")
                try:
                    dt = datetime.fromisoformat(str(ts_str).replace("Z", ""))
                    ts = int(dt.timestamp())
                except:
                    continue
                candles.append({
                    "time":   ts,
                    "open":   round(float(rec.get("Open",  0)), 4),
                    "high":   round(float(rec.get("High",  0)), 4),
                    "low":    round(float(rec.get("Low",   0)), 4),
                    "close":  round(float(rec.get("Close", 0)), 4),
                    "volume": int(rec.get("Volume", 0)),
                })

            candles.sort(key=lambda x: x["time"])
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
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
