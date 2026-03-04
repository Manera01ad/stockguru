"""
Alpaca Execution Connector
════════════════════════════
Routes paper trades through Alpaca's paper trading API for real broker fills
instead of pure internal simulation.

Requires: ALPACA_API_KEY + ALPACA_SECRET_KEY in .env
Uses ALPACA_BASE_URL from env (defaults to paper endpoint).

When paper_trader.py generates a trade, this connector can optionally
place the same order on Alpaca paper account — getting real NBBO fills,
actual slippage, and a proper broker paper P&L record.

Safety: Only ever calls paper API endpoint. Live endpoint requires explicit
ALPACA_BASE_URL override to https://api.alpaca.markets.
"""

import os
import logging
import requests
from datetime import datetime

log = logging.getLogger("AlpacaExecution")

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")


class AlpacaExecutionConnector:
    """
    Bridge between StockGuru paper_trader and Alpaca paper account.
    Reuses channels/alpaca_broker.py for the actual HTTP calls.
    """

    def __init__(self):
        self.api_key    = ALPACA_API_KEY
        self.secret_key = ALPACA_SECRET_KEY
        self.base_url   = ALPACA_BASE_URL
        self._headers   = {
            "APCA-API-KEY-ID":     self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type":        "application/json",
        }

    @property
    def is_paper(self) -> bool:
        return "paper" in self.base_url

    def place_paper_order(self, symbol: str, qty: int, side: str,
                          order_type: str = "market",
                          limit_price: float = 0.0) -> dict:
        """
        Submit an order to Alpaca paper account.

        Args:
            symbol:      e.g. "INFY" (NSE) or "AAPL" (US)
            qty:         number of shares
            side:        "buy" or "sell"
            order_type:  "market" or "limit"
            limit_price: required if order_type == "limit"

        Returns: Alpaca order dict or {"error": ...}
        """
        if not (self.api_key and self.secret_key):
            return {"error": "Alpaca credentials not configured"}

        payload = {
            "symbol":        symbol,
            "qty":           str(qty),
            "side":          side.lower(),
            "type":          order_type.lower(),
            "time_in_force": "day",
        }
        if order_type.lower() == "limit" and limit_price:
            payload["limit_price"] = str(round(limit_price, 2))

        try:
            r = requests.post(
                f"{self.base_url}/v2/orders",
                headers=self._headers,
                json=payload,
                timeout=10,
            )
            if r.status_code in (200, 201):
                data = r.json()
                log.info(
                    f"Alpaca order placed: {side.upper()} {qty} {symbol} "
                    f"@ {order_type} | id={data.get('id','?')[:8]}"
                )
                return data
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def get_order_status(self, order_id: str) -> dict:
        """Check fill status of a placed order."""
        if not (self.api_key and self.secret_key):
            return {"error": "Not configured"}
        try:
            r = requests.get(
                f"{self.base_url}/v2/orders/{order_id}",
                headers=self._headers,
                timeout=8,
            )
            return r.json() if r.status_code == 200 else {"error": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def get_paper_positions(self) -> list:
        """Fetch all open positions from Alpaca paper account."""
        if not (self.api_key and self.secret_key):
            return []
        try:
            r = requests.get(
                f"{self.base_url}/v2/positions",
                headers=self._headers,
                timeout=8,
            )
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []

    def sync_fills(self, shared_state: dict) -> dict:
        """
        Fetch recent filled orders from Alpaca and write to shared_state["alpaca_fills"].
        Called after each agent cycle to sync actual fill prices.
        """
        if not (self.api_key and self.secret_key):
            return {}
        try:
            r = requests.get(
                f"{self.base_url}/v2/orders",
                headers=self._headers,
                params={"status": "filled", "limit": 20},
                timeout=8,
            )
            if r.status_code != 200:
                return {}
            orders = r.json()
            fills = {}
            for o in orders:
                fills[o["id"]] = {
                    "symbol":       o.get("symbol"),
                    "side":         o.get("side"),
                    "qty":          o.get("filled_qty"),
                    "filled_price": o.get("filled_avg_price"),
                    "status":       o.get("status"),
                    "filled_at":    o.get("filled_at", "")[:19],
                }
            shared_state["alpaca_fills"] = fills
            return fills
        except Exception as e:
            log.debug(f"sync_fills error: {e}")
            return {}

    def status(self) -> dict:
        return {
            "connector":     "alpaca_execution",
            "authenticated": bool(self.api_key and self.secret_key),
            "base_url":      self.base_url,
            "is_paper":      self.is_paper,
            "checked_at":    datetime.now().strftime("%H:%M:%S"),
        }
