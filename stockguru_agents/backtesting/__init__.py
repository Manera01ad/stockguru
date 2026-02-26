"""
StockGuru Backtesting Module
═════════════════════════════
Replay historical signals against Yahoo Finance 1-year data.
Computes: win rate, Sharpe ratio, max drawdown, avg R:R.
"""
from .engine import BacktestEngine

__all__ = ["BacktestEngine"]
