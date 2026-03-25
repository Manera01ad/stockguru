"""
StockGuru Intelligence Connectors
══════════════════════════════════
High-impact pluggable intelligence connectors that upgrade the agent pipeline.
Each connector activates automatically when its conditions are met (no keys
needed for analysis connectors; Alpaca needs broker credentials).

Connectors:
  alpaca_execution  — Route paper trades through Alpaca paper account (real fills)
  pattern_detector  — Chart pattern recognition (flags, H&S, triangles, etc.)
  agent_router      — Confidence-based LLM routing (skip expensive calls when weak)
  risk_analytics    — Portfolio VaR (95/99%), correlation matrix, portfolio beta
"""
from .connector_manager import ConnectorManager

__all__ = ["ConnectorManager"]
