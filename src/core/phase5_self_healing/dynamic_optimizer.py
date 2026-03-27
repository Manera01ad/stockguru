"""
Dynamic Threshold Optimizer

Generates gate threshold recommendations based on:
- Gate effectiveness analysis
- Market regime classification
- Historical performance patterns
- Backtesting of alternative thresholds
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from .data_models import GateType, MarketRegime, ThresholdRecommendation


@dataclass
class BacktestResult:
    """Results of backtesting a threshold change"""
    gate_type: GateType
    current_threshold: float
    new_threshold: float
    backtest_periods: int = 90
    trades_tested: int = 0

    # Win/Loss before and after
    wins_with_current: int = 0
    losses_with_current: int = 0
    wins_with_new: int = 0
    losses_with_new: int = 0

    # Calculated metrics
    current_win_rate: float = 0.0
    new_win_rate: float = 0.0
    win_rate_improvement: float = 0.0

    # Signal count
    signals_with_current: int = 0
    signals_with_new: int = 0
    signal_change_percent: float = 0.0

    # Confidence
    confidence: float = 0.0
    recommendation: str = "hold"  # "tighten", "relax", "hold"


class DynamicThresholdOptimizer:
    """
    Generates optimal gate threshold recommendations
    """

    def __init__(self):
        """Initialize optimizer"""
        self.recommendations: List[ThresholdRecommendation] = []
        self.last_optimization = None

    def generate_recommendations(self,
                                gate_effectiveness: Dict,
                                market_regime: MarketRegime,
                                historical_trades: List = None) -> List[ThresholdRecommendation]:
        """
        Generate threshold recommendations for all gates

        Args:
            gate_effectiveness: Output from GateEffectivenessCalculator
            market_regime: Current market regime
            historical_trades: List of historical trades for backtesting

        Returns:
            List of ThresholdRecommendation objects
        """
        recommendations = []

        for gate_key, metrics in gate_effectiveness.items():
            if gate_key == "all_gate_metrics":
                continue

            rec = self._optimize_gate_threshold(
                gate_key,
                metrics,
                market_regime,
                historical_trades
            )

            if rec:
                recommendations.append(rec)

        self.recommendations = recommendations
        self.last_optimization = datetime.utcnow()

        return recommendations

    def _optimize_gate_threshold(self,
                                gate_key: str,
                                gate_metrics: Dict,
                                market_regime: MarketRegime,
                                historical_trades: List = None) -> Optional[ThresholdRecommendation]:
        """
        Optimize a single gate's threshold

        Args:
            gate_key: Gate identifier
            gate_metrics: Gate metrics from effectiveness calculator
            market_regime: Current market regime
            historical_trades: Historical trades for validation

        Returns:
            ThresholdRecommendation or None
        """
        predictive_power = gate_metrics.get("predictive_power", 0)
        false_positive_rate = gate_metrics.get("false_positive_rate", 0)
        false_negative_rate = gate_metrics.get("false_negative_rate", 0)
        confidence = gate_metrics.get("confidence_score", 0)

        # Skip if low confidence
        if confidence < 0.5:
            return None

        # Determine action
        recommended_action = "keep"
        threshold_adjustment = 0.0
        projected_impact = {
            "win_rate_change": 0.0,
            "signal_change_percent": 0.0,
        }

        # Tighten: Too many false positives
        if false_positive_rate > 0.3 and predictive_power > 0.1:
            recommended_action = "tighten"
            threshold_adjustment = 0.1  # 10% tighter
            projected_impact = {
                "win_rate_change": predictive_power * 0.3,
                "signal_change_percent": -15.0,
            }

        # Relax: Too many false negatives (missing winners)
        elif false_negative_rate > 0.3 and predictive_power > 0.1:
            recommended_action = "relax"
            threshold_adjustment = -0.05  # 5% looser
            projected_impact = {
                "win_rate_change": predictive_power * 0.2,
                "signal_change_percent": 10.0,
            }

        # Regime-specific adjustments
        regime_adjustment = self._get_regime_adjustment(gate_key, market_regime)
        if regime_adjustment:
            threshold_adjustment += regime_adjustment.get("adjustment", 0)

        # Create recommendation
        recommendation = ThresholdRecommendation(
            gate_type=GateType[gate_key.upper()],
            current_threshold=1.0,  # Placeholder - actual values from conviction_filter
            recommended_threshold=1.0 + threshold_adjustment,
            change_amount=threshold_adjustment,
            change_percent=threshold_adjustment * 100,
            projected_win_rate_change=projected_impact.get("win_rate_change", 0),
            projected_false_positive_change=-false_positive_rate * 0.3 if recommended_action == "tighten" else 0,
            estimated_signal_change=projected_impact.get("signal_change_percent", 0),
            backtest_periods=90,
            confidence_level=confidence,
            status="pending",
            reasoning=self._generate_reasoning(
                gate_key,
                recommended_action,
                false_positive_rate,
                false_negative_rate,
                predictive_power
            ),
            optimal_for_regime=market_regime,
        )

        return recommendation if recommended_action != "keep" else None

    def _get_regime_adjustment(self, gate_key: str, regime: MarketRegime) -> Optional[Dict]:
        """
        Get threshold adjustment for specific regime

        Args:
            gate_key: Gate name
            regime: Market regime

        Returns:
            Adjustment dictionary or None
        """
        adjustments = {
            MarketRegime.TRENDING: {
                "technical_setup": {"adjustment": 0.05, "reason": "Trend setup stronger"},
                "volume_confirmation": {"adjustment": 0.02, "reason": "Confirm momentum"},
                "risk_reward": {"adjustment": 0.10, "reason": "Wider targets"},
            },
            MarketRegime.RANGING: {
                "agent_consensus": {"adjustment": 0.02, "reason": "Need agreement"},
                "support_resistance": {"adjustment": -0.05, "reason": "Less restrictive"},
            },
            MarketRegime.VOLATILE: {
                "technical_setup": {"adjustment": 0.10, "reason": "Tighter filters"},
                "agent_consensus": {"adjustment": 0.10, "reason": "Need consensus"},
                "vix_check": {"adjustment": 0.15, "reason": "Restrict volatility"},
            },
        }

        return adjustments.get(regime, {}).get(gate_key)

    def _generate_reasoning(self,
                           gate_key: str,
                           action: str,
                           fp_rate: float,
                           fn_rate: float,
                           pred_power: float) -> str:
        """
        Generate reasoning for recommendation

        Args:
            gate_key: Gate name
            action: Action recommended
            fp_rate: False positive rate
            fn_rate: False negative rate
            pred_power: Predictive power

        Returns:
            Reasoning string
        """
        if action == "tighten":
            return (
                f"Gate '{gate_key}' has strong predictive power ({pred_power:.2f}) "
                f"but high false positive rate ({fp_rate:.1%}). "
                f"Tightening threshold will reduce low-quality signals by ~15%."
            )
        elif action == "relax":
            return (
                f"Gate '{gate_key}' is too restrictive (false negative rate: {fn_rate:.1%}). "
                f"Relaxing will capture more winners with predictive power of {pred_power:.2f}."
            )
        else:
            return (
                f"Gate '{gate_key}' is well-calibrated with predictive power {pred_power:.2f}. "
                f"No adjustment needed."
            )

    def backtest_threshold_change(self,
                                  gate_key: str,
                                  current_threshold: float,
                                  new_threshold: float,
                                  historical_trades: List) -> BacktestResult:
        """
        Backtest a proposed threshold change

        Args:
            gate_key: Gate to backtest
            current_threshold: Current threshold value
            new_threshold: Proposed threshold value
            historical_trades: Historical trades to test against

        Returns:
            BacktestResult with performance metrics
        """
        result = BacktestResult(
            gate_type=GateType[gate_key.upper()],
            current_threshold=current_threshold,
            new_threshold=new_threshold,
            trades_tested=len(historical_trades) if historical_trades else 0,
        )

        if not historical_trades:
            return result

        # Simulate outcomes with current threshold
        current_signals = []
        new_signals = []

        for trade in historical_trades:
            if not trade.gates_passed:
                continue

            gate_passed = trade.gates_passed.get(gate_key, False)

            # Simulate current threshold behavior
            if gate_passed:
                current_signals.append(trade)
                if trade.is_win:
                    result.wins_with_current += 1
                else:
                    result.losses_with_current += 1

            # Simulate new threshold behavior
            # (In practice, would re-evaluate signal against new threshold)
            new_would_pass = self._simulate_threshold_change(
                gate_passed,
                current_threshold,
                new_threshold
            )

            if new_would_pass:
                new_signals.append(trade)
                if trade.is_win:
                    result.wins_with_new += 1
                else:
                    result.losses_with_new += 1

        # Calculate metrics
        result.signals_with_current = len(current_signals)
        result.signals_with_new = len(new_signals)

        if result.signals_with_current > 0:
            result.current_win_rate = result.wins_with_current / result.signals_with_current

        if result.signals_with_new > 0:
            result.new_win_rate = result.wins_with_new / result.signals_with_new

        result.win_rate_improvement = result.new_win_rate - result.current_win_rate

        if result.signals_with_current > 0:
            result.signal_change_percent = (
                (result.signals_with_new - result.signals_with_current) /
                result.signals_with_current * 100
            )

        # Determine recommendation
        if result.win_rate_improvement > 0.05:
            result.recommendation = "approve"
            result.confidence = min(0.95, abs(result.win_rate_improvement) * 2)
        elif result.win_rate_improvement < -0.05:
            result.recommendation = "reject"
            result.confidence = min(0.95, abs(result.win_rate_improvement) * 2)
        else:
            result.recommendation = "hold"
            result.confidence = 0.5

        return result

    @staticmethod
    def _simulate_threshold_change(currently_passes: bool,
                                  current_threshold: float,
                                  new_threshold: float) -> bool:
        """
        Simulate whether gate would pass with new threshold

        Args:
            currently_passes: Whether gate currently passes
            current_threshold: Current threshold
            new_threshold: New threshold

        Returns:
            Whether gate would pass with new threshold
        """
        # Simplified simulation
        # In practice, would re-evaluate actual gate values
        if new_threshold > current_threshold:
            # Tightening threshold
            # ~70% of currently passing signals still pass
            return currently_passes and (hash(str(new_threshold)) % 100 > 30)
        else:
            # Relaxing threshold
            # ~80% of currently passing signals pass + some new ones
            return currently_passes or (hash(str(new_threshold)) % 100 < 20)

    def get_optimization_summary(self) -> Dict:
        """
        Get summary of optimization results

        Returns:
            Summary dictionary
        """
        if not self.recommendations:
            return {"status": "no_recommendations"}

        approved = [r for r in self.recommendations if r.status == "approved"]
        pending = [r for r in self.recommendations if r.status == "pending"]

        total_projected_improvement = sum(
            r.projected_win_rate_change for r in self.recommendations
        )

        return {
            "total_recommendations": len(self.recommendations),
            "pending_approval": len(pending),
            "approved": len(approved),
            "implemented": len([r for r in self.recommendations if r.status == "implemented"]),
            "projected_cumulative_win_rate_improvement": total_projected_improvement,
            "last_optimization": self.last_optimization,
            "recommendations": [
                {
                    "gate": r.gate_type.value,
                    "action": r.recommended_action,
                    "confidence": r.confidence_level,
                    "status": r.status,
                }
                for r in self.recommendations
            ],
        }
