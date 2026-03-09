"""
Base DataFeed interface — all connectors implement this.
"""
import os
from abc import ABC, abstractmethod
from typing import List, Dict


class DataFeed(ABC):
    NAME        = "base"
    LABEL       = "Base"
    REQUIRED_ENV: List[str] = []   # env var names that must be set
    LATENCY_MS  = 0
    OB_LEVELS   = 0
    IS_REALTIME = False

    # ── Configuration check ────────────────────────────────────────────────
    def is_configured(self) -> bool:
        """Return True if all required env vars are present and non-empty."""
        return all(os.getenv(k, "").strip() for k in self.REQUIRED_ENV)

    def is_enabled(self) -> bool:
        """Return True unless explicitly disabled via {NAME}_ENABLED=0 in env."""
        return os.getenv(f"{self.NAME.upper()}_ENABLED", "1").strip() != "0"

    # ── Core interface ─────────────────────────────────────────────────────
    @abstractmethod
    def get_quote(self, symbol: str) -> Dict:
        """
        Return current quote for a symbol.
        Expected keys: price, prev_close, change_pct, day_high, day_low,
                       volume, currency, name
        """

    @abstractmethod
    def get_orderbook(self, symbol: str, depth: int = 5) -> Dict:
        """
        Return live order book.
        Expected keys: bids[], asks[], spread, best_bid, best_ask
        Each bid/ask: { price, qty, total }
        """

    @abstractmethod
    def get_candles(self, symbol: str, interval: str, range_: str) -> Dict:
        """
        Return OHLCV candle data.
        Expected keys: candles[], price, change_pct, day_high, day_low,
                       volume, currency, name
        Each candle: { time (unix), open, high, low, close, volume }
        """

    # ── Status ─────────────────────────────────────────────────────────────
    def status(self) -> Dict:
        return {
            "name":        self.NAME,
            "label":       self.LABEL,
            "configured":  self.is_configured(),
            "realtime":    self.IS_REALTIME,
            "latency_ms":  self.LATENCY_MS,
            "ob_levels":   self.OB_LEVELS,
        }

    # ── Symbol helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _strip_suffix(sym: str) -> str:
        """RELIANCE.NS → RELIANCE"""
        return sym.replace(".NS", "").replace(".BO", "").replace("^", "")

    @staticmethod
    def _is_bse(sym: str) -> bool:
        return ".BO" in sym
