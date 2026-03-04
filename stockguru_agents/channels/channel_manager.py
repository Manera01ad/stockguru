"""
Channel Manager — orchestrates all broker/data connectors
════════════════════════════════════════════════════════════
Checks which channels are configured (via .env), reports their
status, and provides a unified interface for the rest of the system.
"""

import os
import logging
from datetime import datetime

log = logging.getLogger("ChannelManager")


class ChannelManager:
    """
    Central registry for all data/execution channels.
    Each channel is lazy-loaded only when its API keys are present.
    """

    CHANNEL_DEFS = {
        "zerodha_kite": {
            "name":        "Zerodha Kite",
            "description": "India's #1 broker — live trading, positions, orders",
            "env_keys":    ["KITE_API_KEY", "KITE_API_SECRET"],
            "region":      "India",
            "type":        "broker",
            "docs_url":    "https://kite.trade/docs/connect/v3/",
        },
        "alpaca": {
            "name":        "Alpaca Markets",
            "description": "Commission-free US stocks — paper & live trading",
            "env_keys":    ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"],
            "region":      "US",
            "type":        "broker",
            "docs_url":    "https://alpaca.markets/docs/",
        },
        "alpha_vantage": {
            "name":        "Alpha Vantage",
            "description": "Fundamentals, earnings, macro data (free tier: 25 req/day)",
            "env_keys":    ["ALPHA_VANTAGE_KEY"],
            "region":      "Global",
            "type":        "data",
            "docs_url":    "https://www.alphavantage.co/documentation/",
        },
        "newsapi": {
            "name":        "NewsAPI",
            "description": "Real-time global news headlines (free tier: 100 req/day)",
            "env_keys":    ["NEWS_API_KEY"],
            "region":      "Global",
            "type":        "data",
            "docs_url":    "https://newsapi.org/docs",
        },
        "telegram": {
            "name":        "Telegram Alerts",
            "description": "Push alerts to Telegram chat",
            "env_keys":    ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"],
            "region":      "Global",
            "type":        "notification",
            "docs_url":    "https://core.telegram.org/bots/api",
        },
    }

    def __init__(self):
        self._status_cache = {}
        self._last_check = None

    def get_all_statuses(self) -> dict:
        """Return status of every channel."""
        statuses = {}
        for channel_id, defn in self.CHANNEL_DEFS.items():
            keys_present = [k for k in defn["env_keys"] if os.getenv(k)]
            keys_missing = [k for k in defn["env_keys"] if not os.getenv(k)]

            if len(keys_present) == len(defn["env_keys"]):
                status = "connected"
            elif keys_present:
                status = "partial"
            else:
                status = "not_configured"

            statuses[channel_id] = {
                **defn,
                "status":        status,
                "keys_present":  len(keys_present),
                "keys_required": len(defn["env_keys"]),
                "missing_keys":  keys_missing,
                "checked_at":    datetime.now().strftime("%H:%M:%S"),
            }
        self._status_cache = statuses
        self._last_check   = datetime.now()
        return statuses

    def is_connected(self, channel_id: str) -> bool:
        status = self._status_cache.get(channel_id, {})
        if not status:
            self.get_all_statuses()
        return self._status_cache.get(channel_id, {}).get("status") == "connected"

    def get_zerodha_client(self):
        """Return a configured Zerodha Kite client, or None."""
        if not self.is_connected("zerodha_kite"):
            return None
        try:
            from .zerodha_kite import ZerodhaKiteChannel
            return ZerodhaKiteChannel()
        except Exception as e:
            log.warning(f"Zerodha init failed: {e}")
            return None

    def get_alpaca_client(self):
        """Return a configured Alpaca client, or None."""
        if not self.is_connected("alpaca"):
            return None
        try:
            from .alpaca_broker import AlpacaChannel
            return AlpacaChannel()
        except Exception as e:
            log.warning(f"Alpaca init failed: {e}")
            return None

    def get_alpha_vantage_client(self):
        """Return Alpha Vantage client, or None."""
        if not self.is_connected("alpha_vantage"):
            return None
        try:
            from .alpha_vantage import AlphaVantageChannel
            return AlphaVantageChannel()
        except Exception as e:
            log.warning(f"Alpha Vantage init failed: {e}")
            return None

    def summary(self) -> str:
        statuses = self.get_all_statuses()
        connected = sum(1 for s in statuses.values() if s["status"] == "connected")
        total     = len(statuses)
        return f"{connected}/{total} channels connected"
