"""
Phase 5: Self-Healing Strategy Layer

This module provides auto-learning and dynamic optimization for StockGuru's
trading conviction filter. It analyzes historical trades, measures gate effectiveness,
detects market regimes, and generates threshold recommendations.

Components:
- HistoricalAnalyzer: Analyzes 90-day trade history
- GateEffectivenessCalculator: Measures predictive power of each gate
- MarketRegimeDetector: Classifies market conditions
- DynamicThresholdOptimizer: Generates gate threshold recommendations
- RiskParameterTuner: Optimizes position sizing and stop losses
- LearningEngine: Main orchestrator coordinating all analysis
- StatisticalUtils: Correlation, confidence scoring, distributions
"""

__version__ = "1.0.0"
__author__ = "StockGuru Development Team"

from phase5_self_healing.data_models import (
    GateEffectivenessRecord,
    MarketRegimeState,
    ThresholdRecommendation,
    RiskParameterProfile,
    OptimizationMetrics,
)
from phase5_self_healing.historical_analyzer import HistoricalAnalyzer
from phase5_self_healing.gate_effectiveness import GateEffectivenessCalculator
from phase5_self_healing.market_regime_detector import MarketRegimeDetector
from phase5_self_healing.dynamic_optimizer import DynamicThresholdOptimizer
from phase5_self_healing.risk_tuner import RiskParameterTuner
from phase5_self_healing.learning_engine import LearningEngine
from phase5_self_healing.statistical_utils import StatisticalUtils

__all__ = [
    "GateEffectivenessRecord",
    "MarketRegimeState",
    "ThresholdRecommendation",
    "RiskParameterProfile",
    "OptimizationMetrics",
    "HistoricalAnalyzer",
    "GateEffectivenessCalculator",
    "MarketRegimeDetector",
    "DynamicThresholdOptimizer",
    "RiskParameterTuner",
    "LearningEngine",
    "StatisticalUtils",
]
