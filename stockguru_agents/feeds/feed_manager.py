"""
FeedManager — Auto-selects the best configured data feed.

Priority (best → fallback):
  TrueData → Zerodha → Upstox → Fyers → Shoonya → Angel One → Yahoo Finance

Just add credentials to .env — the correct feed activates automatically.
No code changes needed when switching providers.
"""
import logging
from typing import List, Dict

log = logging.getLogger("feed_manager")


class FeedManager:
    """
    Singleton that routes all market data calls to the best available feed.
    Import as: from stockguru_agents.feeds import feed_manager
    """

    # Priority order: highest quality / fastest first, Yahoo always last
    FEED_PRIORITY = [
        "truedata",   # 100ms, 20-level OB, ₹800/mo
        "zerodha",    # 200ms, 5-level OB, ₹2k/mo
        "upstox",     # 200ms, 5-level OB, free
        "fyers",      # 300ms, 5-level OB, free
        "shoonya",    # 200ms, 5-level OB, free
        "angel",      # 400ms, 5-level OB, free
        "yahoo",      # 15min delay, simulated OB, free (always available)
    ]

    def __init__(self):
        self._feeds: Dict = {}
        self._active_name: str = "yahoo"
        self._load_all_feeds()
        self._select_active()

    # ── Feed loading ───────────────────────────────────────────────────────
    def _load_all_feeds(self):
        """Instantiate all feed classes, catch import errors gracefully."""
        feed_classes = {}

        try:
            from .truedata_feed import TrueDataFeed
            feed_classes["truedata"] = TrueDataFeed
        except Exception as e:
            log.debug(f"TrueData feed unavailable: {e}")

        try:
            from .zerodha_feed import ZerodhaFeed
            feed_classes["zerodha"] = ZerodhaFeed
        except Exception as e:
            log.debug(f"Zerodha feed unavailable: {e}")

        try:
            from .upstox_feed import UpstoxFeed
            feed_classes["upstox"] = UpstoxFeed
        except Exception as e:
            log.debug(f"Upstox feed unavailable: {e}")

        try:
            from .fyers_feed import FyersFeed
            feed_classes["fyers"] = FyersFeed
        except Exception as e:
            log.debug(f"Fyers feed unavailable: {e}")

        try:
            from .shoonya_feed import ShoonyaFeed
            feed_classes["shoonya"] = ShoonyaFeed
        except Exception as e:
            log.debug(f"Shoonya feed unavailable: {e}")

        try:
            from .angel_feed import AngelFeed
            feed_classes["angel"] = AngelFeed
        except Exception as e:
            log.debug(f"Angel feed unavailable: {e}")

        try:
            from .coingecko_feed import CoinGeckoFeed
            feed_classes["coingecko"] = CoinGeckoFeed
        except Exception as e:
            log.debug(f"CoinGecko feed unavailable: {e}")

        try:
            from .frankfurter_feed import FrankfurterFeed
            feed_classes["frankfurter"] = FrankfurterFeed
        except Exception as e:
            log.debug(f"Frankfurter feed unavailable: {e}")

        try:
            from .yahoo_feed import YahooFeed
            feed_classes["yahoo"] = YahooFeed
        except Exception as e:
            log.error(f"Yahoo feed unavailable: {e}")

        # Instantiate each class
        for name, cls in feed_classes.items():
            try:
                self._feeds[name] = cls()
            except Exception as e:
                log.warning(f"Could not instantiate {name}: {e}")

    # ── Feed selection ─────────────────────────────────────────────────────
    def _select_active(self):
        """Pick the highest-priority configured and enabled feed, respecting ACTIVE_FEED override."""
        import os
        forced = os.getenv("ACTIVE_FEED")
        
        # 1. First respect manually forced override from the UI (Active Feed Switch)
        if forced:
            forced = forced.lower().strip()
            if forced == "yahoo":
                self._active_name = "yahoo"
                log.info("📡 Active data feed: Yahoo Finance (forced via ACTIVE_FEED)")
                return
            elif forced in self._feeds:
                feed = self._feeds[forced]
                if feed.is_configured() and feed.is_enabled():
                    self._active_name = forced
                    log.info(f"✅ Active data feed: {feed.LABEL} ({forced}) [FORCED]")
                    return
                else:
                    log.warning(f"⚠️ Forced ACTIVE_FEED '{forced}' is not fully configured. Falling back to priority.")

        # 2. Otherwise fall through to priority-based selection
        for name in self.FEED_PRIORITY:
            feed = self._feeds.get(name)
            if feed and feed.is_configured() and feed.is_enabled():
                self._active_name = name
                log.info(f"✅ Active data feed: {feed.LABEL} ({name})")
                return
        # Fallback
        self._active_name = "yahoo"
        log.info("📡 Active data feed: Yahoo Finance (fallback)")

    def reload(self):
        """Force re-detection (call after .env changes at runtime)."""
        self._select_active()

    # ── Active feed accessors ──────────────────────────────────────────────
    @property
    def active(self):
        return self._feeds.get(self._active_name) or self._feeds.get("yahoo")

    @property
    def active_name(self) -> str:
        return self._active_name

    @property
    def active_label(self) -> str:
        f = self.active
        return f.LABEL if f else "Unknown"

    # ── Public API (delegates to active feed) ─────────────────────────────
    def _route_symbol(self, symbol: str):
        sym = symbol.upper()
        if "-USD" in sym or "-INR" in sym:
            return self._feeds.get("coingecko") or self.active
        if "=X" in sym:
            return self._feeds.get("frankfurter") or self.active
        return self.active

    def get_quote(self, symbol: str) -> dict:
        feed = self._route_symbol(symbol)
        try:
            return feed.get_quote(symbol)
        except Exception as e:
            log.error(f"get_quote failed ({feed.NAME}): {e}")
            return self._feeds["yahoo"].get_quote(symbol)

    def get_orderbook(self, symbol: str, depth: int = 15) -> dict:
        feed = self._route_symbol(symbol)
        try:
            return feed.get_orderbook(symbol, depth)
        except Exception as e:
            log.error(f"get_orderbook failed ({feed.NAME}): {e}")
            return self._feeds["yahoo"].get_orderbook(symbol, depth)

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        feed = self._route_symbol(symbol)
        try:
            return feed.get_candles(symbol, interval, range_)
        except Exception as e:
            log.error(f"get_candles failed ({feed.NAME}): {e}")
            return self._feeds["yahoo"].get_candles(symbol, interval, range_)

    # ── Status (for /api/feed-status endpoint) ─────────────────────────────
    def status(self) -> dict:
        all_feeds = []
        for name in self.FEED_PRIORITY + ["coingecko", "frankfurter"]:
            feed = self._feeds.get(name)
            if feed:
                s = feed.status()
                s["active"]   = (name == self._active_name)
                s["enabled"]  = feed.is_enabled()
                all_feeds.append(s)
        return {
            "active_feed":  self._active_name,
            "active_label": self.active_label,
            "is_realtime":  self.active.IS_REALTIME if self.active else False,
            "latency_ms":   self.active.LATENCY_MS  if self.active else 0,
            "ob_levels":    self.active.OB_LEVELS    if self.active else 0,
            "feeds":        all_feeds,
        }
