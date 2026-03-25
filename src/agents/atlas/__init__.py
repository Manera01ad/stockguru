# ══════════════════════════════════════════════════════════════════════════════
# ATLAS — Adaptive Trading & Learning Architecture System
# ══════════════════════════════════════════════════════════════════════════════
# The self-upgrading cognitive knowledge engine for StockGuru.
# Every trade, news event, option flow spike, volume pattern, and market regime
# is recorded, cross-referenced, and synthesized into growing intelligence.
#
# Modules:
#   core.py              — Central knowledge hub, SQLite + JSON store
#   options_flow_memory  — Historical PCR→outcome, unusual OI tracking
#   news_impact_mapper   — News type → price move causality
#   regime_detector      — Market regime (bull/bear/sideways) + time patterns
#   volume_classifier    — Volume spike taxonomy (accumulation/distribution/climax)
#   causal_engine        — Multi-dimensional WHY analysis
#   self_upgrader        — Nightly synthesis → auto-generated trading rules
# ══════════════════════════════════════════════════════════════════════════════

from .core import ATLASCore

__all__ = ["ATLASCore"]
