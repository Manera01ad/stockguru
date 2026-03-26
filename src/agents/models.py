
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, JSON, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class PaperTrade(Base):
    """Refined Table to track all trade history (TradeBook)."""
    __tablename__ = 'trade_book'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String, unique=True, index=True)
    order_id = Column(String, index=True)
    symbol = Column(String, index=True, nullable=False)
    exchange = Column(String, default="NSE")
    transaction_type = Column(String)  # BUY, SELL
    product_code = Column(String)     # CNC, MIS, NRML
    
    quantity = Column(Integer)
    price = Column(Float)
    value = Column(Float)
    
    # Cost Details
    brokerage = Column(Float, default=0.0)
    stt = Column(Float, default=0.0)
    exchange_charges = Column(Float, default=0.0)
    gst = Column(Float, default=0.0)
    total_costs = Column(Float, default=0.0)
    
    executed_at = Column(DateTime, default=datetime.utcnow)
    tag = Column(String)

class OrderBook(Base):
    """Tracks every order status change."""
    __tablename__ = 'order_book'
    
    order_id = Column(String, primary_key=True)
    symbol = Column(String, index=True)
    transaction = Column(String)
    order_type = Column(String)
    product = Column(String)
    status = Column(String, index=True)
    
    quantity = Column(Integer)
    price = Column(Float)
    trigger_price = Column(Float)
    filled_qty = Column(Integer, default=0)
    avg_price = Column(Float, default=0.0)
    
    placed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    rejection_reason = Column(String)
    tag = Column(String)

class PositionBook(Base):
    """Active portfolio positions."""
    __tablename__ = 'position_book'
    
    symbol = Column(String, primary_key=True)
    product = Column(String, primary_key=True) # Composite key: SYMBOL+PRODUCT
    quantity = Column(Integer, default=0)
    avg_price = Column(Float, default=0.0)
    last_price = Column(Float, default=0.0)
    
    realised_pnl = Column(Float, default=0.0)
    unrealised_pnl = Column(Float, default=0.0)
    
    # Conviction / Strategy
    target1 = Column(Float)
    target2 = Column(Float)
    stop_loss = Column(Float)
    trail_sl_high = Column(Float)
    t1_booked = Column(Integer, default=0) # 0=No, 1=Yes
    
    opened_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="OPEN")

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if isinstance(d.get("opened_at"), datetime):
            d["opened_at"] = d["opened_at"].isoformat()
        return d

class PortfolioState(Base):
    """Current account balance and global stats."""
    __tablename__ = 'portfolio_state'
    
    id = Column(Integer, primary_key=True) # Always 1
    capital = Column(Float)
    available_cash = Column(Float)
    realised_pnl = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

class ConvictionAudit(Base):
    """Detailed audit of all 8 conviction gates for trade attempts."""
    __tablename__ = 'conviction_audit'
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String, index=True)
    decision = Column(String)
    signal_type = Column(String)
    entry_price = Column(Float)
    exit_price = Column(Float)
    stop_loss = Column(Float)
    
    # 8 Gates
    gate_1_technical = Column(Integer)
    gate_2_volume = Column(Integer)
    gate_3_consensus = Column(Integer)
    gate_4_rr_ratio = Column(Integer)
    gate_5_time_filter = Column(Integer)
    gate_6_institutional = Column(Integer)
    gate_7_sentiment = Column(Integer)
    gate_8_vix = Column(Integer)
    
    gates_passed = Column(Integer)
    conviction_level = Column(String)
    rejection_reason = Column(Text)
    agent_name = Column(String)

class PortfolioHistory(Base):
    """Daily/hourly snapshots for the equity curve."""
    __tablename__ = 'portfolio_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    total_value = Column(Float)
    cash_balance = Column(Float)
    open_pnl = Column(Float)
    realised_pnl = Column(Float)

# ── PHASE 5: SELF-HEALING & ADAPTIVE STRATEGY ──────────────────────────────────

class SelfHealingSession(Base):
    """Logs each full optimization cycle run by the Learning Engine."""
    __tablename__ = 'learning_sessions'
    id                              = Column(Integer, primary_key=True, autoincrement=True)
    session_ts                      = Column(DateTime, default=datetime.utcnow, index=True)
    strategy                        = Column(String)
    trigger_type                    = Column(String, default="manual")   # manual | scheduled | anomaly
    analysis_period_days            = Column(Integer, default=90)
    total_trades_analyzed           = Column(Integer, default=0)
    winning_trades                  = Column(Integer, default=0)
    losing_trades                   = Column(Integer, default=0)
    win_rate_before                 = Column(Float)
    win_rate_after                  = Column(Float)                      # filled after post-cycle trades
    market_regime                   = Column(String)                     # TRENDING | RANGING | VOLATILE
    regime_confidence               = Column(Float)
    vix_level                       = Column(Float)
    recommendations_generated       = Column(Integer, default=0)
    recommendations_approved        = Column(Integer, default=0)
    recommendations_implemented     = Column(Integer, default=0)
    projected_win_rate_improvement  = Column(Float)
    full_analysis_data              = Column(JSON)
    adjustments_json                = Column(Text, default="{}")
    notes                           = Column(Text)
    completed                       = Column(Boolean, default=False)
    created_at                      = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SelfHealingSession {self.id} | regime={self.market_regime} | wr_before={self.win_rate_before}>"


class GatePerformance(Base):
    """Tracks effectiveness of each conviction gate over time (Phase 5)."""
    __tablename__ = 'gate_performance'

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    session_id            = Column(Integer, index=True)           # FK → learning_sessions.id
    gate_name             = Column(String(50), index=True)        # e.g. 'technical_setup'
    total_passed          = Column(Integer, default=0)
    total_rejected        = Column(Integer, default=0)
    wins_when_passed      = Column(Integer, default=0)
    losses_when_passed    = Column(Integer, default=0)
    wins_when_rejected    = Column(Integer, default=0)
    losses_when_rejected  = Column(Integer, default=0)
    pass_rate             = Column(Float)
    win_rate_when_passed  = Column(Float)
    win_rate_when_rejected= Column(Float)
    false_positive_rate   = Column(Float)
    false_negative_rate   = Column(Float)
    predictive_power      = Column(Float)                         # -1 to 1
    confidence_score      = Column(Float)                         # 0 to 1
    market_regime         = Column(String(50))                    # TRENDING | RANGING | VOLATILE | None
    symbol                = Column(String(20))
    recommended_action    = Column(String(50))                    # tighten | relax | keep
    action_rationale      = Column(Text)
    analysis_date         = Column(DateTime, default=datetime.utcnow, index=True)
    created_at            = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<GatePerformance {self.gate_name} | power={self.predictive_power:.2f}>"


class DynamicThreshold(Base):
    """AI-optimized gate thresholds per regime, with full version history (Phase 5)."""
    __tablename__ = 'dynamic_thresholds'

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    gate_name             = Column(String(50), index=True)
    market_regime         = Column(String(50), index=True)        # TRENDING | RANGING | VOLATILE | all
    symbol                = Column(String(20))
    current_value         = Column(Float)
    previous_value        = Column(Float)
    source                = Column(String(100), default="phase5_optimization")
    optimization_session_id = Column(Integer)
    expected_impact       = Column(JSON)                          # {"win_rate_change": 0.05, ...}
    actual_impact         = Column(JSON)                          # populated after N trades
    is_active             = Column(Boolean, default=True)
    approved              = Column(Boolean, default=False)
    approval_timestamp    = Column(DateTime)
    activated_at          = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at            = Column(DateTime)
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DynamicThreshold {self.gate_name} | {self.market_regime} | val={self.current_value}>"


class RiskOptimization(Base):
    """Regime-specific risk parameters optimized by Phase 5."""
    __tablename__ = 'risk_optimizations'

    id                       = Column(Integer, primary_key=True, autoincrement=True)
    session_id               = Column(Integer)
    market_regime            = Column(String(50), index=True)
    symbol                   = Column(String(20))
    position_size_percent    = Column(Float)
    max_position_size_currency = Column(Float)
    stop_loss_atr_multiple   = Column(Float)
    min_stop_distance        = Column(Float)
    max_stop_distance        = Column(Float)
    target_rr_ratio          = Column(Float)
    take_profit_atr_multiple = Column(Float)
    win_rate_in_regime       = Column(Float)
    avg_win_amount           = Column(Float)
    avg_loss_amount          = Column(Float)
    profit_factor            = Column(Float)
    trades_in_regime         = Column(Integer, default=0)
    expected_profit_factor   = Column(Float)
    expected_win_rate        = Column(Float)
    volatility_adjusted      = Column(Boolean, default=True)
    volatility_multiplier    = Column(Float, default=1.0)
    is_active                = Column(Boolean, default=True)
    approved                 = Column(Boolean, default=False)
    approval_timestamp       = Column(DateTime)
    activated_at             = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at               = Column(DateTime)
    created_at               = Column(DateTime, default=datetime.utcnow)
    updated_at               = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<RiskOptimization {self.market_regime} | pos_size={self.position_size_percent}>"


class RegimeHistory(Base):
    """Chronological record of detected market regimes (Phase 5)."""
    __tablename__ = 'regime_history'

    id                          = Column(Integer, primary_key=True, autoincrement=True)
    detected_at                 = Column(DateTime, default=datetime.utcnow, index=True)
    regime                      = Column(String(50), index=True)   # TRENDING | RANGING | VOLATILE
    confidence                  = Column(Float)
    vix_level                   = Column(Float)
    vix_trend                   = Column(String(20))               # rising | stable | falling
    volatility_percentile       = Column(Float)
    trend_direction             = Column(String(20))               # up | down | neutral
    trend_strength              = Column(Float)
    momentum                    = Column(Float)
    symbol                      = Column(String(20))
    expected_win_rate           = Column(Float)
    expected_profitable_strategy= Column(String(100))
    characteristics             = Column(JSON)
    recommended_actions         = Column(JSON)
    regime_start                = Column(DateTime)
    regime_end                  = Column(DateTime)
    created_at                  = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RegimeHistory {self.regime} @ {self.detected_at} | conf={self.confidence:.0%}>"


# ── Engine + SessionLocal ─────────────────────────────────────────────────────
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "stockguru.db")

engine       = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)
