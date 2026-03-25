"""
Phase 5 Data Models

Dataclasses and SQLAlchemy ORM models for storing phase 5 analysis results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum


class MarketRegime(Enum):
    """Market regime classifications"""
    TRENDING = "trending"        # Strong directional movement
    RANGING = "ranging"          # Sideways consolidation
    VOLATILE = "volatile"        # High volatility, unclear direction


class GateType(Enum):
    """The 8 conviction gates"""
    TECHNICAL_SETUP = "technical_setup"
    VOLUME_CONFIRMATION = "volume_confirmation"
    AGENT_CONSENSUS = "agent_consensus"
    RISK_REWARD = "risk_reward"
    TIME_OF_DAY = "time_of_day"
    INSTITUTIONAL_FLOW = "institutional_flow"
    NEWS_SENTIMENT = "news_sentiment"
    VIX_CHECK = "vix_check"


@dataclass
class GateMetrics:
    """Effectiveness metrics for a single gate"""
    gate_type: GateType
    total_passed: int = 0
    total_rejected: int = 0
    wins_when_passed: int = 0
    wins_when_rejected: int = 0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    pass_rate: float = 0.0
    predictive_power: float = 0.0  # 0-1 correlation strength
    win_rate_when_passed: float = 0.0
    confidence_score: float = 0.0  # 0-1 reliability

    def calculate_effectiveness(self):
        """Calculate gate effectiveness metrics"""
        if (self.wins_when_passed + self.wins_when_rejected) == 0:
            return

        # Win rate when gate passes
        if self.total_passed > 0:
            self.win_rate_when_passed = self.wins_when_passed / self.total_passed

        # Pass rate
        total = self.total_passed + self.total_rejected
        if total > 0:
            self.pass_rate = self.total_passed / total

        # False positive rate (failed but trade won)
        if self.total_rejected > 0:
            self.false_positive_rate = self.wins_when_rejected / self.total_rejected

        # False negative rate (passed but trade lost)
        if self.total_passed > 0:
            self.false_negative_rate = (self.total_passed - self.wins_when_passed) / self.total_passed


@dataclass
class GateEffectivenessRecord:
    """Phase 5 database: Gate effectiveness analysis"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    gate_type: GateType = None
    analysis_period_days: int = 90

    # Metrics
    total_passed: int = 0
    total_rejected: int = 0
    wins_when_passed: int = 0
    wins_when_rejected: int = 0
    losses_when_passed: int = 0
    losses_when_rejected: int = 0

    # Calculated values
    pass_rate: float = 0.0
    win_rate_when_passed: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    predictive_power: float = 0.0
    confidence_score: float = 0.0

    # Recommendations
    recommended_threshold: float = None
    recommended_action: str = None  # "tighten", "relax", "keep"

    # Metadata
    symbol: Optional[str] = None
    market_regime: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MarketRegimeState:
    """Phase 5 database: Current market regime"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Current regime
    current_regime: MarketRegime = MarketRegime.RANGING
    regime_confidence: float = 0.5

    # Market indicators
    vix_level: float = 20.0
    vix_trend: str = "stable"  # "rising", "stable", "falling"
    volatility_percentile: float = 0.5

    # Directional analysis
    trend_direction: Optional[str] = None  # "up", "down", "neutral"
    trend_strength: float = 0.0  # 0-1

    # Performance in regime
    win_rate_in_regime: float = 0.0
    trades_in_regime: int = 0
    avg_profit_factor: float = 1.0

    # Metadata
    symbol: Optional[str] = None
    analysis_period: int = 20  # lookback periods


@dataclass
class ThresholdRecommendation:
    """Phase 5: Recommendation for gate threshold adjustment"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Which gate
    gate_type: GateType = None

    # Current vs recommended
    current_threshold: float = None
    recommended_threshold: float = None
    change_amount: float = 0.0
    change_percent: float = 0.0

    # Backtesting results
    projected_win_rate_change: float = 0.0
    projected_false_positive_change: float = 0.0
    estimated_signal_change: float = 0.0  # % more or fewer signals

    # Validation
    backtest_periods: int = 90
    backtest_trades: int = 0
    confidence_level: float = 0.0  # 0-1

    # Status
    status: str = "pending"  # "pending", "approved", "implemented", "rejected"
    reasoning: Optional[str] = None

    # Market context
    optimal_for_regime: Optional[MarketRegime] = None
    symbol: Optional[str] = None


@dataclass
class RiskParameterProfile:
    """Phase 5: Risk parameter optimization for market regime"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Regime this applies to
    market_regime: MarketRegime = MarketRegime.RANGING
    symbol: Optional[str] = None

    # Position sizing
    position_size_percent: float = 2.0  # % of account
    max_position_size: float = 0.0  # absolute if set

    # Stop loss
    stop_loss_atr_multiple: float = 2.0  # Stop = Entry - (ATR * multiple)
    min_stop_distance: float = 0.5
    max_stop_distance: float = 5.0

    # Targets
    target_rr_ratio: float = 2.0  # Risk:Reward ratio
    take_profit_atr_multiple: float = 4.0

    # Volatility adjustments
    volatility_adjusted: bool = True
    volatility_multiplier: float = 1.0

    # Performance metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.5
    profit_factor: float = 1.0

    # Status
    active: bool = True
    approved: bool = False


@dataclass
class OptimizationMetrics:
    """Overall optimization performance metrics"""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Period analyzed
    analysis_start_date: datetime = None
    analysis_end_date: datetime = None
    days_analyzed: int = 90

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # Gate effectiveness
    most_effective_gate: Optional[GateType] = None
    least_effective_gate: Optional[GateType] = None
    gate_effectiveness_scores: Dict[str, float] = field(default_factory=dict)

    # Market regimes
    regime_distribution: Dict[str, float] = field(default_factory=dict)
    win_rate_by_regime: Dict[str, float] = field(default_factory=dict)

    # Improvement potential
    recommended_changes: List[ThresholdRecommendation] = field(default_factory=list)
    projected_improvement: float = 0.0

    # Confidence
    analysis_confidence: float = 0.8
    recommendation_count: int = 0


@dataclass
class ThresholdOptimizationLog:
    """Audit trail of all threshold changes"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # What changed
    gate_type: GateType = None
    change_type: str = None  # "threshold_adjustment", "risk_tuning"

    # Before/after
    before_value: float = None
    after_value: float = None
    change_amount: float = 0.0

    # Context
    market_regime_at_change: Optional[str] = None
    vix_at_change: float = None

    # Approval
    approval_status: str = "pending"  # "pending", "approved", "rejected"
    approved_by: Optional[str] = None
    approval_timestamp: Optional[datetime] = None

    # Results
    result_status: str = "monitoring"  # "monitoring", "successful", "reverted"
    win_rate_before: float = None
    win_rate_after: float = None
    actual_improvement: float = None

    # Metadata
    symbol: Optional[str] = None
    notes: Optional[str] = None
    rollback_available: bool = True


@dataclass
class OptimizationRecommendation:
    """Pending recommendation waiting for user approval"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Recommendation details
    title: str = ""
    description: str = ""
    gate_type: Optional[GateType] = None

    # Analysis backing
    analysis_data: Dict = field(default_factory=dict)
    confidence: float = 0.0

    # Recommendation
    recommended_action: str = ""  # What to do
    parameters: Dict = field(default_factory=dict)  # Specific values

    # Impact projection
    projected_impact: Dict = field(default_factory=dict)  # {"win_rate": +0.05, "signals": -10}

    # Status tracking
    status: str = "pending"  # "pending", "approved", "implemented", "rejected"
    approved_at: Optional[datetime] = None
    implemented_at: Optional[datetime] = None

    # Metadata
    symbol: Optional[str] = None
    valid_for_regime: Optional[str] = None
    expiration_date: Optional[datetime] = None
