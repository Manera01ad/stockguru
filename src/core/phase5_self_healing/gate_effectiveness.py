"""
Gate Effectiveness Calculator

Measures the predictive power of each conviction gate by analyzing:
- Win rate when gate passes vs fails
- False positive rate (failed but won)
- False negative rate (passed but lost)
- Overall correlation strength
- Confidence scoring
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import statistics
from .data_models import GateEffectivenessRecord, GateType


@dataclass
class GatePerformance:
    """Performance metrics for a single gate"""
    gate_type: GateType
    total_passed: int = 0
    total_rejected: int = 0
    wins_when_passed: int = 0
    losses_when_passed: int = 0
    wins_when_rejected: int = 0
    losses_when_rejected: int = 0

    def get_metrics(self) -> Dict:
        """Calculate all performance metrics"""
        # Win rates
        win_rate_when_passed = (
            self.wins_when_passed / self.total_passed
            if self.total_passed > 0 else 0
        )
        win_rate_when_rejected = (
            self.wins_when_rejected / self.total_rejected
            if self.total_rejected > 0 else 0
        )

        # Error rates
        false_positive_rate = (
            self.wins_when_rejected / self.total_rejected
            if self.total_rejected > 0 else 0
        )
        false_negative_rate = (
            self.losses_when_passed / self.total_passed
            if self.total_passed > 0 else 0
        )

        # Predictive power: How much better is passing vs failing
        predictive_power = win_rate_when_passed - win_rate_when_rejected

        # Pass rate: How often does gate pass
        pass_rate = (
            self.total_passed / (self.total_passed + self.total_rejected)
            if (self.total_passed + self.total_rejected) > 0 else 0
        )

        # Confidence: Based on sample size and consistency
        sample_size = self.total_passed + self.total_rejected
        confidence = min(1.0, sample_size / 100)  # 100+ samples = 100% confidence

        return {
            "win_rate_when_passed": win_rate_when_passed,
            "win_rate_when_rejected": win_rate_when_rejected,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "predictive_power": predictive_power,
            "pass_rate": pass_rate,
            "confidence_score": confidence,
            "sample_size": sample_size,
        }


class GateEffectivenessCalculator:
    """
    Calculates effectiveness and predictive power of each conviction gate
    """

    def __init__(self, historical_trades: List):
        """
        Initialize with historical trades

        Args:
            historical_trades: List of TradeRecord objects from HistoricalAnalyzer
        """
        self.trades = historical_trades
        self.gate_performances: Dict[str, GatePerformance] = {}

    def calculate_all_gates(self) -> Dict[str, Dict]:
        """
        Calculate effectiveness for all gates

        Returns:
            {"gate_1": {metrics}, "gate_2": {metrics}, ...}
        """
        gates = [
            GateType.TECHNICAL_SETUP,
            GateType.VOLUME_CONFIRMATION,
            GateType.AGENT_CONSENSUS,
            GateType.RISK_REWARD,
            GateType.TIME_OF_DAY,
            GateType.INSTITUTIONAL_FLOW,
            GateType.NEWS_SENTIMENT,
            GateType.VIX_CHECK,
        ]

        results = {}

        for gate_type in gates:
            perf = self.calculate_gate_effectiveness(gate_type)
            results[gate_type.value] = perf

        return results

    def calculate_gate_effectiveness(self, gate_type: GateType) -> Dict:
        """
        Calculate effectiveness for a specific gate

        Args:
            gate_type: Which gate to analyze

        Returns:
            Dictionary of metrics
        """
        gate_key = gate_type.value

        # Initialize performance tracker
        perf = GatePerformance(gate_type=gate_type)

        # Analyze all trades
        for trade in self.trades:
            if not trade.gates_passed:
                continue

            gate_passed = trade.gates_passed.get(gate_key, False)

            if gate_passed:
                perf.total_passed += 1
                if trade.is_win:
                    perf.wins_when_passed += 1
                else:
                    perf.losses_when_passed += 1
            else:
                perf.total_rejected += 1
                if trade.is_win:
                    perf.wins_when_rejected += 1
                else:
                    perf.losses_when_rejected += 1

        # Store performance
        self.gate_performances[gate_key] = perf

        # Calculate metrics
        metrics = perf.get_metrics()

        return {
            "gate_type": gate_key,
            **metrics,
            "raw_data": {
                "total_passed": perf.total_passed,
                "total_rejected": perf.total_rejected,
                "wins_when_passed": perf.wins_when_passed,
                "losses_when_passed": perf.losses_when_passed,
                "wins_when_rejected": perf.wins_when_rejected,
                "losses_when_rejected": perf.losses_when_rejected,
            }
        }

    def get_most_effective_gates(self, top_n: int = 3) -> List[Tuple[str, float]]:
        """
        Get gates ranked by predictive power

        Args:
            top_n: How many gates to return

        Returns:
            List of (gate_name, predictive_power) tuples
        """
        rankings = []

        for gate_key, perf in self.gate_performances.items():
            metrics = perf.get_metrics()
            predictive_power = metrics["predictive_power"]
            rankings.append((gate_key, predictive_power))

        # Sort by predictive power (descending)
        rankings.sort(key=lambda x: x[1], reverse=True)

        return rankings[:top_n]

    def get_least_effective_gates(self, bottom_n: int = 3) -> List[Tuple[str, float]]:
        """
        Get gates ranked by weakest predictive power

        Args:
            bottom_n: How many gates to return

        Returns:
            List of (gate_name, predictive_power) tuples
        """
        rankings = []

        for gate_key, perf in self.gate_performances.items():
            metrics = perf.get_metrics()
            predictive_power = metrics["predictive_power"]
            rankings.append((gate_key, predictive_power))

        # Sort by predictive power (ascending)
        rankings.sort(key=lambda x: x[1])

        return rankings[:bottom_n]

    def get_gates_by_pass_rate(self, min_pass_rate: float = 0.0, max_pass_rate: float = 1.0) -> Dict[str, Dict]:
        """
        Get gates that pass at a certain rate

        Args:
            min_pass_rate: Minimum pass rate (0-1)
            max_pass_rate: Maximum pass rate (0-1)

        Returns:
            Filtered gate metrics
        """
        results = {}

        for gate_key, perf in self.gate_performances.items():
            metrics = perf.get_metrics()
            pass_rate = metrics["pass_rate"]

            if min_pass_rate <= pass_rate <= max_pass_rate:
                results[gate_key] = metrics

        return results

    def identify_gates_for_tightening(self, threshold_predictive_power: float = 0.1) -> List[str]:
        """
        Identify gates that should be tightened (high false positive rate)

        Args:
            threshold_predictive_power: Only consider gates with at least this much power

        Returns:
            List of gate names to tighten
        """
        candidates = []

        for gate_key, perf in self.gate_performances.items():
            metrics = perf.get_metrics()

            # Gate is good at filtering (high predictive power)
            # but too lenient (many false positives)
            if (metrics["predictive_power"] > threshold_predictive_power and
                metrics["false_positive_rate"] > 0.3):
                candidates.append(gate_key)

        return candidates

    def identify_gates_for_relaxing(self, threshold_predictive_power: float = 0.1) -> List[str]:
        """
        Identify gates that should be relaxed (high false negative rate)

        Args:
            threshold_predictive_power: Only consider gates with at least this much power

        Returns:
            List of gate names to relax
        """
        candidates = []

        for gate_key, perf in self.gate_performances.items():
            metrics = perf.get_metrics()

            # Gate is too strict (missing winners)
            # False negative rate is high
            if (metrics["predictive_power"] > threshold_predictive_power and
                metrics["false_negative_rate"] > 0.3):
                candidates.append(gate_key)

        return candidates

    def get_effectiveness_summary(self) -> Dict:
        """
        Get summary of all gate effectiveness

        Returns:
            Summary metrics
        """
        all_gates = self.calculate_all_gates()

        # Aggregate metrics
        avg_predictive_power = statistics.mean(
            [g["predictive_power"] for g in all_gates.values()]
        )

        most_effective = self.get_most_effective_gates(1)
        least_effective = self.get_least_effective_gates(1)

        return {
            "total_gates_analyzed": len(all_gates),
            "avg_predictive_power": avg_predictive_power,
            "most_effective_gate": most_effective[0] if most_effective else None,
            "least_effective_gate": least_effective[0] if least_effective else None,
            "gates_for_tightening": self.identify_gates_for_tightening(),
            "gates_for_relaxing": self.identify_gates_for_relaxing(),
            "all_gate_metrics": all_gates,
        }


class ThresholdOptimizationAnalyzer:
    """
    Suggests optimal threshold values for each gate based on effectiveness
    """

    def __init__(self, gate_effectiveness: Dict[str, Dict]):
        """
        Initialize with gate effectiveness metrics

        Args:
            gate_effectiveness: Output from GateEffectivenessCalculator
        """
        self.gate_effectiveness = gate_effectiveness

    def suggest_threshold_adjustments(self) -> Dict[str, Dict]:
        """
        Suggest threshold adjustments for each gate

        Returns:
            {"gate_name": {current: X, suggested: Y, action: "tighten"|"relax"}}
        """
        suggestions = {}

        for gate_key, metrics in self.gate_effectiveness.items():
            if gate_key == "all_gate_metrics":
                continue

            suggestion = self._analyze_gate_for_adjustment(gate_key, metrics)
            if suggestion:
                suggestions[gate_key] = suggestion

        return suggestions

    def _analyze_gate_for_adjustment(self, gate_key: str, metrics: Dict) -> Optional[Dict]:
        """
        Analyze a single gate for threshold adjustment

        Args:
            gate_key: Gate identifier
            metrics: Gate metrics

        Returns:
            Suggestion dict or None
        """
        predictive_power = metrics.get("predictive_power", 0)
        false_positive_rate = metrics.get("false_positive_rate", 0)
        false_negative_rate = metrics.get("false_negative_rate", 0)
        confidence = metrics.get("confidence_score", 0)

        # Skip if not confident
        if confidence < 0.5:
            return None

        # Tighten: gate is effective but too lenient
        if predictive_power > 0.1 and false_positive_rate > 0.3:
            return {
                "gate": gate_key,
                "action": "tighten",
                "reason": "High predictive power but accepting losers",
                "expected_impact": {
                    "win_rate_improvement": predictive_power * 0.5,
                    "signal_reduction": "10-20%",
                }
            }

        # Relax: gate is too strict, missing winners
        if predictive_power > 0.1 and false_negative_rate > 0.3:
            return {
                "gate": gate_key,
                "action": "relax",
                "reason": "Too strict, missing winners",
                "expected_impact": {
                    "win_rate_improvement": predictive_power * 0.3,
                    "signal_increase": "10-20%",
                }
            }

        # Keep as is
        if predictive_power > 0.05:
            return {
                "gate": gate_key,
                "action": "keep",
                "reason": "Well-calibrated",
                "expected_impact": {
                    "win_rate_improvement": 0,
                }
            }

        return None
