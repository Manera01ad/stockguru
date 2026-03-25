"""
Risk Parameter Tuner

Optimizes position sizing, stop loss distances, and target R:R ratios
based on:
- Market regime (trending/ranging/volatile)
- Volatility levels (VIX, ATR)
- Account equity curve
- Historical performance in current conditions
"""

from typing import Dict, Optional
from dataclasses import dataclass
from phase5_self_healing.data_models import MarketRegime, RiskParameterProfile


@dataclass
class RiskMetrics:
    """Risk metrics for current conditions"""
    win_rate: float = 0.5
    avg_win: float = 1.0
    avg_loss: float = 1.0
    largest_winning_streak: int = 1
    largest_losing_streak: int = 1
    max_drawdown: float = 0.1
    account_equity: float = 100000.0
    volatility_percentile: float = 0.5
    market_regime: MarketRegime = MarketRegime.RANGING


class RiskParameterTuner:
    """
    Optimizes risk parameters for current market conditions
    """

    def __init__(self):
        """Initialize tuner"""
        self.current_profile = None
        self.regime_profiles: Dict[MarketRegime, RiskParameterProfile] = {}

    def calculate_optimal_position_size(self,
                                       account_equity: float,
                                       win_rate: float,
                                       risk_per_trade: float = 0.02) -> float:
        """
        Calculate optimal position size using Kelly Criterion variant

        Args:
            account_equity: Account size
            win_rate: Expected win rate (0-1)
            risk_per_trade: Risk per trade as % of account (default 2%)

        Returns:
            Position size as % of account
        """
        if win_rate < 0.4 or win_rate > 0.6:
            # Outside normal range, reduce position size
            risk_per_trade *= 0.5

        # Adjusted Kelly Criterion: f = (2p - 1) / 2
        # where p = win_rate
        # Using fraction of Kelly (0.25x Kelly for safety)
        kelly_fraction = 0.25

        if win_rate > 0.5:
            kelly_sizing = kelly_fraction * (2 * win_rate - 1)
            return min(kelly_sizing, risk_per_trade * 5)  # Cap at 5x the risk allocation
        else:
            # Below 50% win rate, use fixed risk allocation
            return risk_per_trade

    def calculate_stop_loss_distance(self,
                                    atr: float,
                                    market_regime: MarketRegime,
                                    volatility_percentile: float = 0.5) -> float:
        """
        Calculate stop loss distance based on volatility and regime

        Args:
            atr: Average True Range (volatility measure)
            market_regime: Current market regime
            volatility_percentile: Where volatility ranks (0-1)

        Returns:
            Stop loss distance (in price units)
        """
        # Base stop loss: 2x ATR
        base_stop = 2.0 * atr

        # Regime adjustments
        regime_multipliers = {
            MarketRegime.TRENDING: 1.5,    # Tighter stops in trends
            MarketRegime.RANGING: 1.0,     # Normal stops in ranges
            MarketRegime.VOLATILE: 2.0,    # Wider stops in volatility
        }

        multiplier = regime_multipliers.get(market_regime, 1.0)

        # Volatility adjustment
        if volatility_percentile > 0.75:
            multiplier *= 1.2  # Wider in high volatility

        stop_distance = base_stop * multiplier

        # Ensure reasonable bounds
        return max(0.5, min(5.0, stop_distance))

    def calculate_target_rr_ratio(self,
                                 market_regime: MarketRegime,
                                 win_rate: float) -> float:
        """
        Calculate target Risk:Reward ratio for current regime

        Args:
            market_regime: Current market regime
            win_rate: Current win rate

        Returns:
            Target R:R ratio (e.g., 2.0 = 1:2 risk to reward)
        """
        # Base R:R by regime
        regime_ratios = {
            MarketRegime.TRENDING: 2.5,    # Higher targets in trends
            MarketRegime.RANGING: 2.0,     # Normal targets in ranges
            MarketRegime.VOLATILE: 1.5,    # Lower targets in volatility
        }

        base_ratio = regime_ratios.get(market_regime, 2.0)

        # Adjust for win rate
        if win_rate > 0.60:
            # High win rate = can use lower R:R
            base_ratio *= 0.8
        elif win_rate < 0.50:
            # Low win rate = need higher R:R
            base_ratio *= 1.2

        # Ensure minimum of 1.5:1
        return max(1.5, base_ratio)

    def optimize_for_regime(self,
                           regime: MarketRegime,
                           risk_metrics: RiskMetrics) -> RiskParameterProfile:
        """
        Optimize risk parameters for specific regime

        Args:
            regime: Market regime
            risk_metrics: Current risk metrics

        Returns:
            RiskParameterProfile with optimized parameters
        """
        profile = RiskParameterProfile(
            market_regime=regime,
        )

        # Position sizing
        profile.position_size_percent = self.calculate_optimal_position_size(
            risk_metrics.account_equity,
            risk_metrics.win_rate,
        )

        # Stop loss
        stop_distance = self.calculate_stop_loss_distance(
            1.0,  # ATR = 1.0 (normalized)
            regime,
            risk_metrics.volatility_percentile,
        )
        profile.stop_loss_atr_multiple = max(1.5, min(4.0, stop_distance))

        # Risk:Reward target
        profile.target_rr_ratio = self.calculate_target_rr_ratio(
            regime,
            risk_metrics.win_rate,
        )

        # Win rate metrics
        profile.win_rate = risk_metrics.win_rate
        profile.avg_win = risk_metrics.avg_win
        profile.avg_loss = risk_metrics.avg_loss
        profile.profit_factor = (
            risk_metrics.avg_win / risk_metrics.avg_loss
            if risk_metrics.avg_loss > 0 else 1.0
        )

        # Volatility adjustment
        profile.volatility_adjusted = True
        profile.volatility_multiplier = 1.0 + (risk_metrics.volatility_percentile - 0.5)

        self.regime_profiles[regime] = profile
        return profile

    def get_adaptive_position_size(self,
                                  base_position_size: float,
                                  current_drawdown: float,
                                  max_historical_drawdown: float = 0.2) -> float:
        """
        Adjust position size based on current drawdown

        Args:
            base_position_size: Base position size from optimization
            current_drawdown: Current equity drawdown (0-1)
            max_historical_drawdown: Maximum historical drawdown

        Returns:
            Adjusted position size
        """
        # During drawdown, reduce position size
        if current_drawdown > max_historical_drawdown:
            # Reduce by 20% per 1% drawdown above max
            excess_drawdown = current_drawdown - max_historical_drawdown
            reduction_factor = 1.0 - (excess_drawdown * 20)
            return base_position_size * max(0.5, reduction_factor)

        # During equity highs, can size up slightly
        if current_drawdown < max_historical_drawdown * 0.5:
            return base_position_size * 1.1

        return base_position_size

    def get_scaling_based_on_streak(self,
                                   wins_in_row: int,
                                   losses_in_row: int,
                                   base_position_size: float) -> float:
        """
        Adjust position size based on winning/losing streak

        Args:
            wins_in_row: Current winning streak
            losses_in_row: Current losing streak
            base_position_size: Base position size

        Returns:
            Scaled position size
        """
        # Scale up on winning streaks (confidence)
        if wins_in_row >= 3:
            return base_position_size * min(1.5, 1.0 + (wins_in_row * 0.1))

        # Scale down on losing streaks (protection)
        if losses_in_row >= 3:
            return base_position_size * max(0.5, 1.0 - (losses_in_row * 0.15))

        return base_position_size

    def get_risk_recommendations(self, regime: MarketRegime) -> Dict[str, str]:
        """
        Get risk management recommendations for regime

        Args:
            regime: Market regime

        Returns:
            Dictionary of recommendations
        """
        recommendations = {
            MarketRegime.TRENDING: {
                "position_sizing": "Moderate to aggressive (50-100% of base)",
                "stop_loss": "Place below recent swing lows",
                "profit_taking": "Let winners run with trailing stops",
                "scaling": "Add to winning positions in direction of trend",
                "key_rule": "Cut losers quick, let winners run",
            },
            MarketRegime.RANGING: {
                "position_sizing": "Conservative to moderate (50-75% of base)",
                "stop_loss": "Place just outside support/resistance",
                "profit_taking": "Take partial profits at midline",
                "scaling": "Scale in at support, scale out at resistance",
                "key_rule": "Quick profits, tight stops",
            },
            MarketRegime.VOLATILE: {
                "position_sizing": "Conservative (25-50% of base)",
                "stop_loss": "Place wider than normal (3-4x ATR)",
                "profit_taking": "Take all profits quickly",
                "scaling": "Avoid scaling, single entry only",
                "key_rule": "Small positions, quick exits",
            },
        }

        return recommendations.get(regime, recommendations[MarketRegime.RANGING])

    def calculate_expected_value(self,
                                win_rate: float,
                                avg_win: float,
                                avg_loss: float) -> float:
        """
        Calculate expected value per trade

        Args:
            win_rate: Win rate (0-1)
            avg_win: Average winning trade size
            avg_loss: Average losing trade size

        Returns:
            Expected value per trade
        """
        if avg_loss == 0:
            return avg_win * win_rate

        ev = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        return ev

    def calculate_kelly_percentage(self,
                                  win_rate: float,
                                  win_loss_ratio: float) -> float:
        """
        Calculate Kelly Criterion percentage

        Args:
            win_rate: Win rate (0-1)
            win_loss_ratio: Avg win / avg loss ratio

        Returns:
            Kelly percentage (fraction of bankroll to risk)
        """
        if win_loss_ratio == 0 or win_rate <= 0.5:
            return 0.0

        # Kelly Formula: f = (bp - q) / b
        # where p = win prob, q = loss prob, b = win/loss ratio
        b = win_loss_ratio
        p = win_rate
        q = 1 - win_rate

        kelly = (b * p - q) / b

        # Use fraction of Kelly for safety (usually 0.25x)
        kelly_fraction = kelly * 0.25

        return max(0.0, min(0.1, kelly_fraction))  # Cap at 10% risk

    def get_regime_profile_summary(self) -> Dict:
        """
        Get summary of all regime profiles

        Returns:
            Dictionary of regime profiles
        """
        summary = {}

        for regime, profile in self.regime_profiles.items():
            summary[regime.value] = {
                "position_size_percent": profile.position_size_percent,
                "stop_loss_atr_multiple": profile.stop_loss_atr_multiple,
                "target_rr_ratio": profile.target_rr_ratio,
                "win_rate": profile.win_rate,
                "profit_factor": profile.profit_factor,
                "active": profile.active,
                "approved": profile.approved,
            }

        return summary
