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

from .data_models import (
    GateEffectivenessRecord,
    MarketRegimeState,
    ThresholdRecommendation,
    RiskParameterProfile,
    OptimizationMetrics,
)
from .historical_analyzer import HistoricalAnalyzer
from .gate_effectiveness import GateEffectivenessCalculator
from .market_regime_detector import MarketRegimeDetector
from .dynamic_optimizer import DynamicThresholdOptimizer
from .risk_tuner import RiskParameterTuner
from .learning_engine import LearningEngine
from .statistical_utils import StatisticalUtils

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
