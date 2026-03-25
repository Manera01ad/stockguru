"""
Market Regime Detector

Classifies current market conditions into:
- TRENDING: Strong directional movement (high momentum)
- RANGING: Sideways consolidation (mean reversion environment)
- VOLATILE: High volatility with unclear direction

Uses VIX, ATR, trend strength, and momentum indicators.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from phase5_self_healing.data_models import MarketRegime


@dataclass
class RegimeMetrics:
    """Metrics for regime detection"""
    vix_level: float = 20.0
    atr: float = 1.0  # Average True Range
    trend_strength: float = 0.0  # 0-1, strength of directional movement
    momentum: float = 0.0  # -1 to 1, direction and strength
    volatility_percentile: float = 0.5
    range_expansion: float = 0.0  # % above/below moving averages
    volume_trend: float = 0.0  # Is volume increasing or decreasing


class MarketRegimeDetector:
    """
    Detects and classifies current market regime
    """

    def __init__(self):
        """Initialize detector"""
        self.current_regime = MarketRegime.RANGING
        self.regime_confidence = 0.5
        self.last_update = None

    def detect_regime(self,
                     vix_level: float,
                     atr: float,
                     trend_strength: float,
                     momentum: float,
                     volatility_percentile: float = 0.5) -> Tuple[MarketRegime, float]:
        """
        Detect current market regime

        Args:
            vix_level: Current VIX level (typically 10-40)
            atr: Average True Range (volatility measure)
            trend_strength: Strength of trend (0-1)
            momentum: Momentum indicator (-1 to 1)
            volatility_percentile: Where current volatility ranks (0-1)

        Returns:
            (regime, confidence_score)
        """
        metrics = RegimeMetrics(
            vix_level=vix_level,
            atr=atr,
            trend_strength=trend_strength,
            momentum=momentum,
            volatility_percentile=volatility_percentile,
        )

        return self._classify_regime(metrics)

    def _classify_regime(self, metrics: RegimeMetrics) -> Tuple[MarketRegime, float]:
        """
        Classify regime based on metrics

        Args:
            metrics: RegimeMetrics object

        Returns:
            (regime, confidence)
        """
        # Volatility check first
        if metrics.vix_level > 25 or metrics.volatility_percentile > 0.75:
            # Market is volatile
            self.current_regime = MarketRegime.VOLATILE
            self.regime_confidence = 0.9
            self.last_update = datetime.utcnow()
            return MarketRegime.VOLATILE, 0.9

        # Trending vs Ranging check
        # Trending: Strong trend + Good momentum
        # Ranging: Weak trend + Mean-reverting momentum
        if metrics.trend_strength > 0.6 and abs(metrics.momentum) > 0.5:
            # Strong directional move = TRENDING
            self.current_regime = MarketRegime.TRENDING
            self.regime_confidence = min(0.95, metrics.trend_strength)
            self.last_update = datetime.utcnow()
            return MarketRegime.TRENDING, self.regime_confidence

        # Weak trend or opposite momentum = RANGING
        self.current_regime = MarketRegime.RANGING
        self.regime_confidence = 0.7
        self.last_update = datetime.utcnow()
        return MarketRegime.RANGING, 0.7

    def get_regime_summary(self) -> Dict:
        """
        Get summary of current regime

        Returns:
            Dictionary with regime info
        """
        return {
            "current_regime": self.current_regime.value,
            "confidence": self.regime_confidence,
            "last_update": self.last_update,
            "characteristics": self.get_regime_characteristics(),
        }

    def get_regime_characteristics(self) -> Dict[str, str]:
        """
        Get trading characteristics for current regime

        Returns:
            Dictionary of regime characteristics
        """
        characteristics = {
            MarketRegime.TRENDING: {
                "best_strategy": "Trend following",
                "entry_type": "Breakout entries",
                "exit_type": "Trail stops",
                "expected_holding_time": "Hours to days",
                "suitable_gates": ["technical_setup", "volume_confirmation", "trend_filters"],
                "adjust_stops": "Trail higher on wins",
                "typical_win_rate": "55-65%",
            },
            MarketRegime.RANGING: {
                "best_strategy": "Mean reversion",
                "entry_type": "Support/resistance bounces",
                "exit_type": "Quick profits at midline",
                "expected_holding_time": "Minutes to hours",
                "suitable_gates": ["overbought_oversold", "support_resistance"],
                "adjust_stops": "Tight stops near entry",
                "typical_win_rate": "60-70%",
            },
            MarketRegime.VOLATILE: {
                "best_strategy": "High caution or mean reversion",
                "entry_type": "Conservative entries only",
                "exit_type": "Quick partial profits",
                "expected_holding_time": "Minutes only",
                "suitable_gates": ["vix_check", "volume_confirmation", "news_sentiment"],
                "adjust_stops": "Widen stops for volatility",
                "typical_win_rate": "45-55% (harder)",
            },
        }

        return characteristics.get(
            self.current_regime,
            characteristics[MarketRegime.RANGING]  # Default
        )

    def get_regime_recommendations(self) -> Dict[str, str]:
        """
        Get trading recommendations for current regime

        Returns:
            Dictionary of recommendations
        """
        if self.current_regime == MarketRegime.TRENDING:
            return {
                "position_sizing": "Normal to aggressive (markets reward trend following)",
                "entry_bias": "In direction of trend (breakouts preferred)",
                "stop_placement": "Below swing lows",
                "profit_taking": "Trail stops or breakeven after profit target",
                "risk_management": "Let winners run, cut losers quickly",
            }

        elif self.current_regime == MarketRegime.RANGING:
            return {
                "position_sizing": "Normal (safe for mean reversion)",
                "entry_bias": "At support/resistance levels",
                "stop_placement": "Just outside support/resistance",
                "profit_taking": "Target midline or resistance/support",
                "risk_management": "Tight stops, quick exits on breakouts",
            }

        else:  # VOLATILE
            return {
                "position_sizing": "Conservative (reduce size in volatility)",
                "entry_bias": "Very selective, consider skipping",
                "stop_placement": "Wider than normal due to volatility",
                "profit_taking": "Take small profits quickly",
                "risk_management": "Avoid if possible, extreme caution if trading",
            }

    def calculate_regime_probability(self,
                                    trending_score: float,
                                    ranging_score: float,
                                    volatile_score: float) -> Dict[str, float]:
        """
        Calculate probability of each regime

        Args:
            trending_score: Score for trending regime (0-1)
            ranging_score: Score for ranging regime (0-1)
            volatile_score: Score for volatile regime (0-1)

        Returns:
            {"trending": X, "ranging": Y, "volatile": Z}
        """
        total = trending_score + ranging_score + volatile_score

        if total == 0:
            return {
                "trending": 0.33,
                "ranging": 0.34,
                "volatile": 0.33,
            }

        return {
            "trending": trending_score / total,
            "ranging": ranging_score / total,
            "volatile": volatile_score / total,
        }

    def get_optimal_thresholds_for_regime(self) -> Dict[str, Dict]:
        """
        Get recommended threshold adjustments for current regime

        Returns:
            {"gate_name": {current: X, recommended: Y}}
        """
        adjustments = {
            MarketRegime.TRENDING: {
                "technical_setup": {"adjustment": "+10%", "reason": "Trend setup stronger"},
                "volume_confirmation": {"adjustment": "+5%", "reason": "Validate momentum"},
                "agent_consensus": {"adjustment": "keep", "reason": "Consensus still valuable"},
                "risk_reward": {"adjustment": "+15%", "reason": "Wider targets in trends"},
                "time_of_day": {"adjustment": "keep", "reason": "Trends work all day"},
                "institutional_flow": {"adjustment": "+10%", "reason": "Institutions trend-follow"},
                "news_sentiment": {"adjustment": "-5%", "reason": "Less restrictive"},
                "vix_check": {"adjustment": "-10%", "reason": "Higher VIX tolerable"},
            },
            MarketRegime.RANGING: {
                "technical_setup": {"adjustment": "-10%", "reason": "Setup less critical"},
                "volume_confirmation": {"adjustment": "keep", "reason": "Volume still important"},
                "agent_consensus": {"adjustment": "+5%", "reason": "Consensus helps filter"},
                "risk_reward": {"adjustment": "-10%", "reason": "Tighter targets"},
                "time_of_day": {"adjustment": "+10%", "reason": "Time-of-day effects strong"},
                "institutional_flow": {"adjustment": "-5%", "reason": "Retail-driven ranges"},
                "news_sentiment": {"adjustment": "keep", "reason": "Important for ranges"},
                "vix_check": {"adjustment": "keep", "reason": "Normal VIX checking"},
            },
            MarketRegime.VOLATILE: {
                "technical_setup": {"adjustment": "+15%", "reason": "Tighten technical filters"},
                "volume_confirmation": {"adjustment": "+10%", "reason": "Validate volume spikes"},
                "agent_consensus": {"adjustment": "+15%", "reason": "Need high agreement"},
                "risk_reward": {"adjustment": "-20%", "reason": "Accept smaller ratios"},
                "time_of_day": {"adjustment": "+20%", "reason": "Time-of-day very critical"},
                "institutional_flow": {"adjustment": "+10%", "reason": "Follow smart money"},
                "news_sentiment": {"adjustment": "+20%", "reason": "Check for news-driven moves"},
                "vix_check": {"adjustment": "+25%", "reason": "Very restrictive VIX check"},
            },
        }

        return adjustments.get(self.current_regime, adjustments[MarketRegime.RANGING])


class VIXRegimeAnalyzer:
    """
    Analyzes VIX levels to determine market fear/complacency
    """

    @staticmethod
    def classify_vix_regime(vix_level: float) -> Tuple[str, str]:
        """
        Classify VIX level

        Args:
            vix_level: Current VIX level

        Returns:
            (regime_name, description)
        """
        if vix_level < 12:
            return "COMPLACENT", "Very low volatility, potential calm before storm"
        elif vix_level < 16:
            return "LOW", "Low volatility, normal conditions"
        elif vix_level < 20:
            return "MODERATE", "Moderate volatility, balanced conditions"
        elif vix_level < 25:
            return "ELEVATED", "Elevated volatility, mild stress"
        elif vix_level < 30:
            return "HIGH", "High volatility, significant fear"
        else:
            return "EXTREME", "Extreme volatility, panic conditions"

    @staticmethod
    def get_vix_trading_implications(vix_level: float) -> Dict[str, str]:
        """
        Get trading implications of VIX level

        Args:
            vix_level: Current VIX level

        Returns:
            Dictionary of trading implications
        """
        regime, description = VIXRegimeAnalyzer.classify_vix_regime(vix_level)

        implications = {
            "COMPLACENT": {
                "market_condition": "Calm, trending sideways or up slowly",
                "typical_behavior": "Low volume, range-bound",
                "recommendation": "Look for breakout setups above resistance",
                "caution": "Sudden spikes possible",
            },
            "LOW": {
                "market_condition": "Normal market conditions",
                "typical_behavior": "Balanced momentum, clear trends possible",
                "recommendation": "All strategies can work",
                "caution": "Watch for complacency spikes",
            },
            "MODERATE": {
                "market_condition": "Active but not panicked",
                "typical_behavior": "Good momentum, clear directional moves",
                "recommendation": "Trend following works well",
                "caution": "Prepare for volatility increases",
            },
            "ELEVATED": {
                "market_condition": "Increased uncertainty",
                "typical_behavior": "Wider swings, trending with pullbacks",
                "recommendation": "Use tighter stops, smaller positions",
                "caution": "More whipsaws, less predictable",
            },
            "HIGH": {
                "market_condition": "Significant selling/fear",
                "typical_behavior": "Wide swings, volatile moves",
                "recommendation": "Conservative approach, mean reversion",
                "caution": "Very unpredictable, many false signals",
            },
            "EXTREME": {
                "market_condition": "Panic conditions",
                "typical_behavior": "Extreme moves, panic selling",
                "recommendation": "Consider avoiding entirely or very small position",
                "caution": "Market dislocations, extreme risk",
            },
        }

        return implications.get(regime, implications["MODERATE"])
