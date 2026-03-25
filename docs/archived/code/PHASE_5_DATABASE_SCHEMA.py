"""
Phase 5 Database Schema Extensions

Add these 5 SQLAlchemy models to stockguru_agents/models.py

This schema stores all Phase 5 self-healing analysis results and recommendations.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class LearningSession(Base):
    """
    Logs each Phase 5 optimization cycle
    - When analysis ran
    - What triggered it
    - What metrics were generated
    - What recommendations were made
    """
    __tablename__ = 'learning_sessions'

    id = Column(Integer, primary_key=True)
    session_timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    analysis_period_days = Column(Integer, default=90)

    # What triggered this analysis
    trigger_type = Column(String(50))  # "manual", "scheduled", "anomaly"
    triggered_by = Column(String(100))  # User or system identifier

    # Input metrics
    total_trades_analyzed = Column(Integer)
    winning_trades = Column(Integer)
    losing_trades = Column(Integer)
    win_rate_at_analysis = Column(Float)

    # Market context at time of analysis
    market_regime = Column(String(50))  # "TRENDING", "RANGING", "VOLATILE"
    regime_confidence = Column(Float)
    vix_level = Column(Float)

    # Output: What was recommended
    recommendations_generated = Column(Integer)
    recommendations_approved = Column(Integer)
    recommendations_implemented = Column(Integer)

    # Projected impact
    projected_win_rate_improvement = Column(Float)
    projected_false_positive_reduction = Column(Float)

    # Full analysis data (JSON for flexibility)
    full_analysis_data = Column(JSON)

    # Results after implementation
    actual_improvement = Column(Float)  # Will be filled in after trades run
    completed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<LearningSession {self.id} - {self.market_regime} - WR:{self.win_rate_at_analysis:.1%}>"


class GatePerformance(Base):
    """
    Tracks effectiveness of each conviction gate over time
    - Which gate (1-8)
    - How often it passes/fails
    - Win rate when it passes vs fails
    - Predictive power (correlation with wins)
    """
    __tablename__ = 'gate_performance'

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, index=True)  # Foreign key to LearningSession
    gate_name = Column(String(50), index=True)  # "technical_setup", "volume_confirmation", etc.

    # Sample sizes
    total_passed = Column(Integer, default=0)
    total_rejected = Column(Integer, default=0)

    # Win/Loss breakdown
    wins_when_passed = Column(Integer, default=0)
    losses_when_passed = Column(Integer, default=0)
    wins_when_rejected = Column(Integer, default=0)
    losses_when_rejected = Column(Integer, default=0)

    # Calculated metrics
    pass_rate = Column(Float)  # % of trades passing this gate
    win_rate_when_passed = Column(Float)  # Win rate if gate passes
    win_rate_when_rejected = Column(Float)  # Win rate if gate fails
    false_positive_rate = Column(Float)  # Rejected but won
    false_negative_rate = Column(Float)  # Passed but lost

    # Key metric: How much does this gate correlate with winning?
    predictive_power = Column(Float)  # -1 to 1 (negative = gate inversely correlated)
    confidence_score = Column(Float)  # 0-1 (how confident are we in this measurement?)

    # Market regime this applies to
    market_regime = Column(String(50))  # TRENDING, RANGING, VOLATILE (or None for overall)
    symbol = Column(String(20))  # Specific symbol or None for all

    # Recommendation based on this analysis
    recommended_action = Column(String(50))  # "tighten", "relax", "keep"
    action_rationale = Column(Text)

    analysis_date = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<GatePerformance {self.gate_name} - Power:{self.predictive_power:.2f}>"


class DynamicThreshold(Base):
    """
    Stores AI-optimized thresholds for each gate
    - Different thresholds per market regime
    - Version history for rollback
    - When it was activated
    """
    __tablename__ = 'dynamic_thresholds'

    id = Column(Integer, primary_key=True)
    gate_name = Column(String(50), index=True)
    market_regime = Column(String(50), index=True)  # TRENDING, RANGING, VOLATILE, or "all"
    symbol = Column(String(20))  # Specific symbol or None for all symbols

    # The actual threshold values
    current_value = Column(Float)  # Current threshold being used
    previous_value = Column(Float)  # Previous threshold (for rollback)

    # How was this determined?
    source = Column(String(100))  # "phase5_optimization", "manual_adjustment", "default"
    optimization_session_id = Column(Integer)  # Reference to LearningSession

    # Impact tracking
    expected_impact = Column(JSON)  # {"win_rate_change": 0.05, "signal_reduction": 0.1}
    actual_impact = Column(JSON)  # Populated after N trades

    # Status
    is_active = Column(Boolean, default=True)
    approved = Column(Boolean, default=False)
    approval_timestamp = Column(DateTime)

    # Timeline
    activated_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime)  # Optional expiration for A/B testing

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DynamicThreshold {self.gate_name} - {self.market_regime} - {self.current_value}>"


class RiskOptimization(Base):
    """
    Stores regime-specific risk parameters
    - Position sizing per regime
    - Stop loss distances
    - Target R:R ratios
    - Performance in each regime
    """
    __tablename__ = 'risk_optimizations'

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer)  # Which optimization cycle created this
    market_regime = Column(String(50), index=True)  # TRENDING, RANGING, VOLATILE
    symbol = Column(String(20))  # Specific symbol or all symbols

    # Position sizing
    position_size_percent = Column(Float)  # % of account per trade
    max_position_size_currency = Column(Float)  # Cap in absolute currency

    # Stop loss
    stop_loss_atr_multiple = Column(Float)  # Stop = Entry - (ATR * multiple)
    min_stop_distance = Column(Float)
    max_stop_distance = Column(Float)

    # Profit targets
    target_rr_ratio = Column(Float)  # Risk:Reward ratio (1:2, 1:2.5, etc)
    take_profit_atr_multiple = Column(Float)

    # Historical performance in this regime
    win_rate_in_regime = Column(Float)
    avg_win_amount = Column(Float)
    avg_loss_amount = Column(Float)
    profit_factor = Column(Float)
    trades_in_regime = Column(Integer)

    # Expected performance with these params
    expected_profit_factor = Column(Float)
    expected_win_rate = Column(Float)

    # Volatility adjustment
    volatility_adjusted = Column(Boolean, default=True)
    volatility_multiplier = Column(Float)  # Adjust position size by volatility

    # Status
    is_active = Column(Boolean, default=True)
    approved = Column(Boolean, default=False)
    approval_timestamp = Column(DateTime)

    # Timeline
    activated_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<RiskOptimization {self.market_regime} - PosSize:{self.position_size_percent:.1%}>"


class RegimeHistory(Base):
    """
    Chronological record of detected market regimes
    - Timestamp of detection
    - Which regime was detected
    - Confidence level
    - Key metrics that led to classification
    """
    __tablename__ = 'regime_history'

    id = Column(Integer, primary_key=True)
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Detected regime
    regime = Column(String(50), index=True)  # TRENDING, RANGING, VOLATILE
    confidence = Column(Float)  # 0-1, how confident are we?

    # Key metrics at time of detection
    vix_level = Column(Float)
    vix_trend = Column(String(20))  # "rising", "stable", "falling"
    volatility_percentile = Column(Float)

    # Trend analysis
    trend_direction = Column(String(20))  # "up", "down", "neutral"
    trend_strength = Column(Float)  # 0-1
    momentum = Column(Float)  # -1 to 1

    # Market context
    symbol = Column(String(20))  # Which symbol(s) this applies to
    market_cap_weighted = Column(Boolean, default=True)  # Or symbol-specific?

    # Performance expectations in this regime
    expected_win_rate = Column(Float)
    expected_profitable_strategy = Column(String(100))  # "trend_following", "mean_reversion"

    # Characteristics and recommendations
    characteristics = Column(JSON)  # Store regime characteristics
    recommended_actions = Column(JSON)  # Recommended strategies

    # Duration
    regime_start = Column(DateTime)  # When this regime started
    regime_end = Column(DateTime)  # When it ended (populated when regime changes)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RegimeHistory {self.regime} @ {self.detected_at} - Confidence:{self.confidence:.0%}>"


"""
INTEGRATION INSTRUCTIONS FOR models.py:

1. Import these models:
   from phase5_self_healing.models import (
       LearningSession, GatePerformance, DynamicThreshold,
       RiskOptimization, RegimeHistory
   )

2. Add to Base.metadata.create_all() in your database initialization:
   Base.metadata.create_all(bind=engine)

3. Add indexes for performance:
   - CREATE INDEX idx_learning_sessions_timestamp ON learning_sessions(session_timestamp)
   - CREATE INDEX idx_gate_performance_session ON gate_performance(session_id)
   - CREATE INDEX idx_dynamic_thresholds_gate ON dynamic_thresholds(gate_name, market_regime)
   - CREATE INDEX idx_risk_optimizations_regime ON risk_optimizations(market_regime)
   - CREATE INDEX idx_regime_history_timestamp ON regime_history(detected_at)

4. Update your ConvictionAudit table to reference learning_sessions:
   learning_session_id = Column(Integer, ForeignKey('learning_sessions.id'))

5. Update your Trade table to reference dynamic_thresholds:
   threshold_version_id = Column(Integer, ForeignKey('dynamic_thresholds.id'))
   risk_optimization_id = Column(Integer, ForeignKey('risk_optimizations.id'))
"""
