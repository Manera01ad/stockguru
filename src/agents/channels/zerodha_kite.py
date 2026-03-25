"""
Zerodha Kite Connect Channel
═════════════════════════════
India's most popular retail broker API.
Free to use with Zerodha account (₹0 brokerage on delivery).

Setup (one-time):
  1. Login at https://kite.trade/
  2. Create app → get API Key + API Secret
  3. Add to .env:
       KITE_API_KEY=your_api_key
       KITE_API_SECRET=your_api_secret
       KITE_ACCESS_TOKEN=  (generated fresh each trading day)

Capabilities:
  • Fetch live quotes for any NSE/BSE symbol
  • Place market / limit / SL orders (paper_trader.py controls the gate)
  • Fetch positions, holdings, order history
  • Real-time margins and account balance

LIVE_TRADING is controlled by paper_trader.py — this module
only provides the API bridge. The safety lock stays in paper_trader.
"""

import os
import logging
import requests
from datetime import datetime

log = logging.getLogger("ZerodhaKite")

KITE_API_KEY      = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET   = os.getenv("KITE_API_SECRET", "")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")

KITE_BASE = "https://api.kite.trade"


class ZerodhaKiteChannel:
    """
    Lightweight Zerodha Kite Connect wrapper.
    Uses requests directly — no kiteconnect library dependency.
    """

    def __init__(self):
        self.api_key      = KITE_API_KEY
        self.access_token = KITE_ACCESS_TOKEN
        self._headers = {
            "X-Kite-Version": "3",
            "Authorization":  f"token {self.api_key}:{self.access_token}",
        }

    @property
    def is_authenticated(self) -> bool:
        return bool(self.api_key and self.access_token)

    def get_quote(self, instruments: list) -> dict:
        """
        Fetch live quotes for a list of instruments.
        instruments: ["NSE:INFY", "NSE:HDFCBANK", ...]
        """
        if not self.is_authenticated:
            return {"error": "Not authenticated — set KITE_ACCESS_TOKEN"}
        try:
            params = {"i": instruments}
            r = requests.get(f"{KITE_BASE}/quote", headers=self._headers,
                             params=params, timeout=8)
            if r.status_code == 200:
                return r.json().get("data", {})
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> dict:
        """Fetch current open positions."""
        if not self.is_authenticated:
            return {"error": "Not authenticated"}
        try:
            r = requests.get(f"{KITE_BASE}/portfolio/positions",
                             headers=self._headers, timeout=8)
            return r.json() if r.status_code == 200 else {"error": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def get_holdings(self) -> dict:
        """Fetch long-term holdings."""
        if not self.is_authenticated:
            return {"error": "Not authenticated"}
        try:
            r = requests.get(f"{KITE_BASE}/portfolio/holdings",
                             headers=self._headers, timeout=8)
            return r.json() if r.status_code == 200 else {"error": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def get_margins(self) -> dict:
        """Fetch account margins/balance."""
        if not self.is_authenticated:
            return {"error": "Not authenticated"}
        try:
            r = requests.get(f"{KITE_BASE}/user/margins",
                             headers=self._headers, timeout=8)
            return r.json() if r.status_code == 200 else {"error": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def place_order(self, tradingsymbol: str, exchange: str, transaction_type: str,
                    quantity: int, order_type: str = "MARKET",
                    price: float = 0, trigger_price: float = 0) -> dict:
        """
        Place an order on Kite.
        ⚠️  Only called by paper_trader.py when LIVE_TRADING_ENABLED = True.
        """
        if not self.is_authenticated:
            return {"error": "Not authenticated"}
        payload = {
            "tradingsymbol":   tradingsymbol,
            "exchange":        exchange,
            "transaction_type": transaction_type,
            "quantity":        quantity,
            "order_type":      order_type,
            "product":         "CNC",  # delivery
            "validity":        "DAY",
        }
        if order_type in ("LIMIT", "SL"):
            payload["price"] = price
        if order_type == "SL":
            payload["trigger_price"] = trigger_price
        try:
            r = requests.post(f"{KITE_BASE}/orders/regular",
                              headers=self._headers, data=payload, timeout=10)
            return r.json() if r.status_code == 200 else {"error": r.text[:300]}
        except Exception as e:
            return {"error": str(e)}

    def status(self) -> dict:
        return {
            "channel":         "zerodha_kite",
            "authenticated":   self.is_authenticated,
            "api_key_masked":  self.api_key[:4] + "****" if self.api_key else "not set",
            "token_set":       bool(self.access_token),
            "checked_at":      datetime.now().strftime("%H:%M:%S"),
        }
