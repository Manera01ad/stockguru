"""
StockGuru Channel Connectors
════════════════════════════
Pluggable broker and data-source connectors.
Each channel can be enabled/disabled independently via .env keys.

Available channels:
  zerodha_kite   — Zerodha Kite Connect (Indian broker, live + paper)
  alpaca_broker  — Alpaca Markets (US stocks, commission-free)
  alpha_vantage  — Alpha Vantage (fundamentals + technicals, free tier)
"""
from .channel_manager import ChannelManager

__all__ = ["ChannelManager"]
