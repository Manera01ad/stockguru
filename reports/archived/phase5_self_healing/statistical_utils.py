"""
Statistical Utilities

Provides statistical functions for:
- Correlation calculations
- Confidence scoring
- Distribution analysis
- Significance testing
- Standard deviation and variance
"""

from typing import List, Dict, Tuple, Optional
import statistics
import math


class StatisticalUtils:
    """
    Statistical utilities for Phase 5 analysis
    """

    @staticmethod
    def calculate_correlation(x_values: List[float], y_values: List[float]) -> float:
        """
        Calculate Pearson correlation between two series

        Args:
            x_values: First data series
            y_values: Second data series (same length)

        Returns:
            Correlation coefficient (-1 to 1)
        """
        if len(x_values) != len(y_values) or len(x_values) < 2:
            return 0.0

        try:
            mean_x = statistics.mean(x_values)
            mean_y = statistics.mean(y_values)

            numerator = sum(
                (x - mean_x) * (y - mean_y)
                for x, y in zip(x_values, y_values)
            )

            std_x = statistics.stdev(x_values) if len(x_values) > 1 else 1
            std_y = statistics.stdev(y_values) if len(y_values) > 1 else 1

            denominator = std_x * std_y * len(x_values)

            if denominator == 0:
                return 0.0

            correlation = numerator / denominator
            return max(-1.0, min(1.0, correlation))  # Clamp to [-1, 1]

        except Exception:
            return 0.0

    @staticmethod
    def calculate_win_loss_correlation(gates_passed_list: List[Dict[str, bool]],
                                       outcomes_list: List[bool]) -> Dict[str, float]:
        """
        Calculate correlation between each gate passing and trade winning

        Args:
            gates_passed_list: List of gate dictionaries {gate_name: bool}
            outcomes_list: List of trade outcomes (True = win, False = loss)

        Returns:
            {gate_name: correlation}
        """
        if not gates_passed_list or not outcomes_list:
            return {}

        if len(gates_passed_list) != len(outcomes_list):
            return {}

        correlations = {}

        # Get all gate names from first record
        if not gates_passed_list[0]:
            return {}

        for gate_name in gates_passed_list[0].keys():
            gate_values = [
                1.0 if gates.get(gate_name, False) else 0.0
                for gates in gates_passed_list
            ]
            outcome_values = [1.0 if o else 0.0 for o in outcomes_list]

            correlation = StatisticalUtils.calculate_correlation(
                gate_values,
                outcome_values
            )
            correlations[gate_name] = correlation

        return correlations

    @staticmethod
    def calculate_confidence_score(sample_size: int,
                                   consistency: float,
                                   predictive_power: float) -> float:
        """
        Calculate confidence score for a metric (0-1)

        Args:
            sample_size: Number of samples analyzed
            consistency: Standard deviation normalized (0-1, lower is better)
            predictive_power: Strength of prediction (0-1)

        Returns:
            Confidence score (0-1)
        """
        # Sample size factor: 100+ samples = 100% confidence
        sample_confidence = min(1.0, sample_size / 100.0)

        # Consistency factor: lower std dev = higher confidence
        consistency_confidence = 1.0 - consistency

        # Predictive power factor: stronger prediction = higher confidence
        power_confidence = abs(predictive_power)

        # Weighted average
        confidence = (
            sample_confidence * 0.4 +
            consistency_confidence * 0.3 +
            power_confidence * 0.3
        )

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def calculate_zscore(value: float, mean: float, std_dev: float) -> float:
        """
        Calculate Z-score (standard deviations from mean)

        Args:
            value: The value to score
            mean: Mean of distribution
            std_dev: Standard deviation

        Returns:
            Z-score
        """
        if std_dev == 0:
            return 0.0
        return (value - mean) / std_dev

    @staticmethod
    def calculate_percentile(value: float, distribution: List[float]) -> float:
        """
        Calculate percentile of a value in a distribution

        Args:
            value: Value to rank
            distribution: Distribution to rank against

        Returns:
            Percentile (0-100)
        """
        if not distribution:
            return 50.0

        sorted_dist = sorted(distribution)
        rank = sum(1 for v in sorted_dist if v < value)
        percentile = (rank / len(sorted_dist)) * 100
        return percentile

    @staticmethod
    def calculate_std_deviation(values: List[float]) -> float:
        """
        Calculate standard deviation

        Args:
            values: List of values

        Returns:
            Standard deviation
        """
        if len(values) < 2:
            return 0.0
        try:
            return statistics.stdev(values)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_variance(values: List[float]) -> float:
        """
        Calculate variance

        Args:
            values: List of values

        Returns:
            Variance
        """
        std_dev = StatisticalUtils.calculate_std_deviation(values)
        return std_dev ** 2

    @staticmethod
    def is_statistically_significant(sample_size: int,
                                      effect_size: float,
                                      confidence_level: float = 0.95) -> bool:
        """
        Determine if result is statistically significant

        Args:
            sample_size: Number of samples
            effect_size: Size of effect (0-1)
            confidence_level: Confidence level (default 95%)

        Returns:
            True if significant
        """
        # Simple heuristic: need enough samples and effect size
        min_samples = {
            0.95: 100,  # 95% confidence = 100 samples
            0.90: 64,   # 90% confidence = 64 samples
            0.85: 36,   # 85% confidence = 36 samples
        }

        required_samples = min_samples.get(confidence_level, 100)

        # Need sufficient sample size and effect size
        return sample_size >= required_samples and effect_size > 0.05

    @staticmethod
    def calculate_confidence_interval(mean: float,
                                      std_dev: float,
                                      sample_size: int,
                                      confidence: float = 0.95) -> Tuple[float, float]:
        """
        Calculate confidence interval for a mean

        Args:
            mean: Sample mean
            std_dev: Sample standard deviation
            sample_size: Number of samples
            confidence: Confidence level (default 95%)

        Returns:
            (lower_bound, upper_bound)
        """
        if sample_size < 2 or std_dev == 0:
            return (mean, mean)

        # Z-score for 95% confidence (approximate)
        z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z_score = z_scores.get(confidence, 1.96)

        margin_of_error = z_score * (std_dev / math.sqrt(sample_size))

        return (mean - margin_of_error, mean + margin_of_error)

    @staticmethod
    def calculate_effect_size(group1: List[float], group2: List[float]) -> float:
        """
        Calculate Cohen's d effect size between two groups

        Args:
            group1: First group of values
            group2: Second group of values

        Returns:
            Effect size (Cohen's d)
        """
        if not group1 or not group2:
            return 0.0

        mean1 = statistics.mean(group1)
        mean2 = statistics.mean(group2)

        std1 = StatisticalUtils.calculate_std_deviation(group1)
        std2 = StatisticalUtils.calculate_std_deviation(group2)

        # Pooled standard deviation
        n1, n2 = len(group1), len(group2)
        pooled_std = math.sqrt(
            ((n1 - 1) * std1**2 + (n2 - 1) * std2**2) / (n1 + n2 - 2)
        ) if (n1 + n2 - 2) > 0 else 1.0

        if pooled_std == 0:
            return 0.0

        cohen_d = (mean1 - mean2) / pooled_std
        return cohen_d

    @staticmethod
    def normalize_score(value: float, min_value: float, max_value: float) -> float:
        """
        Normalize value to 0-1 range

        Args:
            value: Value to normalize
            min_value: Minimum possible value
            max_value: Maximum possible value

        Returns:
            Normalized value (0-1)
        """
        if max_value == min_value:
            return 0.5

        normalized = (value - min_value) / (max_value - min_value)
        return max(0.0, min(1.0, normalized))

    @staticmethod
    def calculate_moving_average(values: List[float], window: int = 5) -> List[float]:
        """
        Calculate moving average

        Args:
            values: List of values
            window: Window size

        Returns:
            Moving averages
        """
        if len(values) < window:
            return values

        averages = []
        for i in range(len(values) - window + 1):
            avg = statistics.mean(values[i:i + window])
            averages.append(avg)

        return averages

    @staticmethod
    def detect_outliers(values: List[float], threshold: float = 2.0) -> List[Tuple[int, float]]:
        """
        Detect outliers using Z-score method

        Args:
            values: List of values
            threshold: Z-score threshold (2.0 = 95% confidence)

        Returns:
            List of (index, value) tuples for outliers
        """
        if len(values) < 2:
            return []

        mean = statistics.mean(values)
        std_dev = StatisticalUtils.calculate_std_deviation(values)

        outliers = []
        for i, value in enumerate(values):
            z_score = StatisticalUtils.calculate_zscore(value, mean, std_dev)
            if abs(z_score) > threshold:
                outliers.append((i, value))

        return outliers

    @staticmethod
    def calculate_optimal_threshold(true_positives: int,
                                     false_positives: int,
                                     true_negatives: int,
                                     false_negatives: int) -> Dict[str, float]:
        """
        Calculate optimal threshold using various metrics

        Args:
            true_positives: Correct positive predictions
            false_positives: Incorrect positive predictions
            true_negatives: Correct negative predictions
            false_negatives: Incorrect negative predictions

        Returns:
            Dictionary of metrics and optimal threshold
        """
        total = true_positives + false_positives + true_negatives + false_negatives

        if total == 0:
            return {}

        # Metrics
        accuracy = (true_positives + true_negatives) / total
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "true_positive_rate": recall,
            "false_positive_rate": false_positives / (false_positives + true_negatives) if (false_positives + true_negatives) > 0 else 0,
        }
