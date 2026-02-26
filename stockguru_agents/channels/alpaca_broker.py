"""
Alpaca Markets Channel
═══════════════════════
Commission-free US stock trading API.
Paper trading is completely free — no live account needed to start.

Setup:
  1. Sign up at https://alpaca.markets/
  2. Generate API Key + Secret (paper or live)
  3. Add to .env:
       ALPACA_API_KEY=your_key
       ALPACA_SECRET_KEY=your_secret
       ALPACA_BASE_URL=https://paper-api.alpaca.markets   (paper)
       # OR
       ALPACA_BASE_URL=https://api.alpaca.markets         (live)

Capabilities:
  • US stock quotes and bars (free data)
  • Paper + live order execution
  • Portfolio positions and account balance
"""

import os
import logging
import requests
from datetime import datetime

log = logging.getLogger("AlpacaBroker")

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_URL   = "https://data.alpaca.markets"


class AlpacaChannel:
    """Alpaca Markets REST API wrapper."""

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

    def get_account(self) -> dict:
        """Fetch account details (balance, buying power, etc.)."""
        try:
            r = requests.get(f"{self.base_url}/v2/account",
                             headers=self._headers, timeout=8)
            return r.json() if r.status_code == 200 else {"error": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> list:
        """Fetch open positions."""
        try:
            r = requests.get(f"{self.base_url}/v2/positions",
                             headers=self._headers, timeout=8)
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            log.debug(f"Alpaca positions error: {e}")
            return []

    def get_quote(self, symbol: str) -> dict:
        """Fetch latest quote for a US stock symbol."""
        try:
            r = requests.get(
                f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/quotes/latest",
                headers=self._headers, timeout=8
            )
            return r.json() if r.status_code == 200 else {"error": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def place_order(self, symbol: str, qty: int, side: str,
                    order_type: str = "market", limit_price: float = None) -> dict:
        """
        Place an order on Alpaca.
        ⚠️  Only called when LIVE_TRADING_ENABLED = True in paper_trader.py.
        """
        payload = {
            "symbol":        symbol,
            "qty":           qty,
            "side":          side,       # "buy" | "sell"
            "type":          order_type, # "market" | "limit"
            "time_in_force": "day",
        }
        if order_type == "limit" and limit_price:
            payload["limit_price"] = str(limit_price)
        try:
            r = requests.post(f"{self.base_url}/v2/orders",
                              headers=self._headers, json=payload, timeout=10)
            return r.json() if r.status_code in (200, 201) else {"error": r.text[:300]}
        except Exception as e:
            return {"error": str(e)}

    def status(self) -> dict:
        acct = self.get_account()
        return {
            "channel":       "alpaca",
            "mode":          "paper" if self.is_paper else "live",
            "buying_power":  acct.get("buying_power", "N/A"),
            "portfolio_val": acct.get("portfolio_value", "N/A"),
            "authenticated": "error" not in acct,
            "checked_at":    datetime.now().strftime("%H:%M:%S"),
        }
