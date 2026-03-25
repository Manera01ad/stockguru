"""
Frankfurter Feed — For FOREX pairs (Currency).
Free API for ECB foreign exchange rates.
"""
import requests
from .base import DataFeed

# Map Yahoo ticker -> Frankfurter from/to
FX_MAP = {
    "USDINR=X": ("USD", "INR"),
    "EURINR=X": ("EUR", "INR"),
    "GBPINR=X": ("GBP", "INR"),
    "JPYINR=X": ("JPY", "INR"),
    "EURUSD=X": ("EUR", "USD"),
    "GBPUSD=X": ("GBP", "USD"),
    "INR=X":    ("USD", "INR"),
}

class FrankfurterFeed(DataFeed):
    NAME        = "frankfurter"
    LABEL       = "Frankfurter (ECB)"
    REQUIRED_ENV = []
    LATENCY_MS  = 60000     # hourly/daily updates
    OB_LEVELS   = 0         # simulated
    IS_REALTIME = False

    def is_configured(self) -> bool:
        return True

    def get_quote(self, symbol: str) -> dict:
        pair = FX_MAP.get(symbol.upper())
        if not pair:
            return {"price": 0, "error": "unsupported pair"}
        
        base, target = pair
        try:
            # Latest
            url = f"https://api.frankfurter.app/latest?from={base}&to={target}"
            r = requests.get(url, timeout=5).json()
            curr = r.get("rates", {}).get(target, 0)
            
            # For prev close we'd need historical, mock it
            # since ECB changes daily anyway
            return {
                "price":      round(curr, 4),
                "prev_close": round(curr, 4),
                "change_pct": 0,
                "day_high":   curr,
                "day_low":    curr,
                "volume":     0,
                "currency":   target,
                "name":       f"{base}/{target}",
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        # Frankfurter doesn't provide intraday OHLCV!
        # Fall back to Yahoo Finance seamlessly for Forex charting
        from .yahoo_feed import YahooFeed
        return YahooFeed().get_candles(symbol, interval, range_)

    def get_orderbook(self, symbol: str, depth: int = 15) -> dict:
        from .yahoo_feed import YahooFeed
        return YahooFeed().get_orderbook(symbol, depth)
