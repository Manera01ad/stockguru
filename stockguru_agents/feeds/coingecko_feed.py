"""
CoinGecko Feed — For Crypto.
"""
import requests
import datetime
from .base import DataFeed

# Hardcoded map for UI symbols -> CoinGecko IDs
CG_MAP = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "BNB-USD": "binancecoin",
    "SOL-USD": "solana",
    "XRP-USD": "ripple",
    "DOGE-USD": "dogecoin",
    "ADA-USD": "cardano",
    "AVAX-USD": "avalanche-2",
    "BTC-INR": "bitcoin",
    "ETH-INR": "ethereum",
    "SOL-INR": "solana",
}

class CoinGeckoFeed(DataFeed):
    NAME        = "coingecko"
    LABEL       = "CoinGecko"
    REQUIRED_ENV = []
    LATENCY_MS  = 3000
    OB_LEVELS   = 0     # Simulated for now
    IS_REALTIME = False # Public API is cached

    def is_configured(self) -> bool:
        return True

    def get_quote(self, symbol: str) -> dict:
        cg_id = CG_MAP.get(symbol.upper(), "bitcoin")
        vs = "inr" if "-INR" in symbol.upper() else "usd"
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies={vs}&include_24hr_change=true&include_24hr_vol=true"
            r = requests.get(url, timeout=8).json()
            if cg_id in r:
                curr = r[cg_id][vs]
                vol  = r[cg_id].get(f"{vs}_24h_vol", 0)
                chg  = r[cg_id].get(f"{vs}_24h_change", 0)
                # Reverse engineer prev_close
                prev = curr / (1 + (chg / 100)) if chg else curr
                
                return {
                    "price":      round(curr, 4),
                    "prev_close": round(prev, 4),
                    "change_pct": round(chg, 2),
                    "day_high":   curr * 1.05, # mock
                    "day_low":    curr * 0.95, # mock
                    "volume":     int(vol),
                    "currency":   vs.upper(),
                    "name":       symbol,
                }
        except Exception as e:
            return {"price": 0, "error": str(e)}
        return {"price": 0, "error": "Not found"}

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        cg_id = CG_MAP.get(symbol.upper())
        if not cg_id:
            # Fallback to yahoo if not supported
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
            
        vs = "inr" if "-INR" in symbol.upper() else "usd"
        # CoinGecko OHLCV days logic
        # 1 day from current time = 30 min candles
        # 7 - 30 days = 4 hour candles
        days = {"1d": 1, "5d": 7, "1wk": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}.get(range_, 1)
        
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlcv?vs_currency={vs}&days={days}"
            data = requests.get(url, timeout=10).json()
            if isinstance(data, dict) and 'error' in data:
                 raise ValueError(data['error'])
                 
            candles = []
            for row in data:
                # row: [timestamp, open, high, low, close]
                ts = int(row[0] / 1000)
                candles.append({
                    "time": ts,
                    "open": round(row[1], 4),
                    "high": round(row[2], 4),
                    "low": round(row[3], 4),
                    "close": round(row[4], 4),
                    "volume": 0 # CoinGecko OHLCV doesn't include volume
                })
                
            q = self.get_quote(symbol)
            return {
                "candles": candles,
                "symbol": symbol,
                "name": symbol.upper(),
                "currency": vs.upper(),
                "price": q.get("price", 0),
                "prev_close": q.get("prev_close", 0),
                "change_pct": q.get("change_pct", 0),
                "day_high": q.get("day_high", 0),
                "day_low": q.get("day_low", 0),
                "volume": q.get("volume", 0),
                "interval": interval,
                "range": range_
            }
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)

    def get_orderbook(self, symbol: str, depth: int = 15) -> dict:
        from .yahoo_feed import YahooFeed
        return YahooFeed().get_orderbook(symbol, depth)
