# ══════════════════════════════════════════════════════════════════════════════
# StockGuru — Sovereign Trader Layer  (Phase 1)
# ══════════════════════════════════════════════════════════════════════════════
# Four meta-agents that supervise the existing 14-agent pipeline:
#   The Scryer     → source confidence + shock vs reality delta
#   The Quant      → overreaction engine + conviction tier routing
#   The Risk Master→ hard/soft VETO governance
#   The Post-Mortem→ LLM reflexion + SQLite memory + self-correction
#
# Plus supporting systems:
#   debate_engine    → 3-round Bull/Bear/Resolution debate (LLM)
#   hitl_controller  → Telegram inline-button approval queue
#   memory_engine    → SQLite agent_memory.db (local → Qdrant-ready)
# ══════════════════════════════════════════════════════════════════════════════

from . import scryer, quant, risk_master, debate_engine, hitl_controller, post_mortem, memory_engine

__all__ = [
    "scryer", "quant", "risk_master",
    "debate_engine", "hitl_controller",
    "post_mortem", "memory_engine"
]
