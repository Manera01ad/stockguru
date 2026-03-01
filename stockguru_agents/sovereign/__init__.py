# ══════════════════════════════════════════════════════════════════════════════
# StockGuru — Sovereign Trader Layer  (Phase 1 + Phase 2)
# ══════════════════════════════════════════════════════════════════════════════
# Phase 1 meta-agents:
#   The Scryer     → source confidence + shock vs reality delta
#   The Quant      → overreaction engine + conviction tier routing
#   The Risk Master→ hard/soft VETO governance
#   The Post-Mortem→ LLM reflexion + SQLite memory + self-correction
#
# Phase 1 supporting systems:
#   debate_engine    → 3-round Bull/Bear/Resolution debate (LLM)
#   hitl_controller  → Telegram inline-button approval queue
#   memory_engine    → SQLite agent_memory.db (local → Qdrant-ready)
#
# Phase 2 agents:
#   observer           → NSE option chain + Screener.in scraper (every 4h)
#   synthetic_backtester → 3-scenario stress test (every 6h)
#   builder_agent      → Dashboard panel proposal + auto-patcher (daily)
# ══════════════════════════════════════════════════════════════════════════════

from . import scryer, quant, risk_master, debate_engine, hitl_controller, post_mortem, memory_engine
from . import observer, synthetic_backtester, builder_agent

__all__ = [
    "scryer", "quant", "risk_master",
    "debate_engine", "hitl_controller",
    "post_mortem", "memory_engine",
    "observer", "synthetic_backtester", "builder_agent",
]
