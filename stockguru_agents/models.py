
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, JSON, Text
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
    """Logs each optimization cycle run by the Learning Engine."""
    __tablename__ = 'learning_sessions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    trades_analyzed = Column(Integer)
    regime_detected = Column(String)  # TRENDING, RANGING, VOLATILE
    avg_win_rate = Column(Float)
    expected_improvement = Column(Float)
    status = Column(String) # COMPLETED, ERROR

class GatePerformance(Base):
    """Statistically derived effectiveness of each conviction gate."""
    __tablename__ = 'gate_performance'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, index=True)
    gate_name = Column(String) # gate_1_technical, etc.
    true_positive_rate = Column(Float) # Gate passed + Trade Won
    false_positive_rate = Column(Float) # Gate passed + Trade Lost
    predictive_power = Column(Float) # Weighted score 0.0 - 1.0
    last_updated = Column(DateTime, default=datetime.utcnow)

class DynamicThreshold(Base):
    """Current 'Self-Healed' optimal threshold values for the core engine."""
    __tablename__ = 'dynamic_thresholds'
    id = Column(Integer, primary_key=True, autoincrement=True)
    param_name = Column(String, unique=True) # MIN_RR, MIN_VOLUME_Z, etc.
    current_value = Column(Float)
    previous_value = Column(Float)
    confidence_score = Column(Float) # 0.0 - 1.0 based on sample size
    applied_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Integer, default=1)

class RiskOptimization(Base):
    """Suggested risk-parameter deviations based on recent performance."""
    __tablename__ = 'risk_optimizations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    market_regime = Column(String)
    suggested_sl_mult = Column(Float) # e.g. 1.2x usual ATR
    suggested_tp_mult = Column(Float)
    max_drawdown_limit = Column(Float)
    notes = Column(Text)

class MarketRegimeHistory(Base):
    """Historical record of changing market conditions."""
    __tablename__ = 'regime_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    regime = Column(String)
    vix_level = Column(Float)
    breadth_ratio = Column(Float)
    dominance = Column(String) # BULLS, BEARS, TUG_OF_WAR

# Database Engine Setup
DB_PATH = "sqlite:///stockguru.db"
engine = create_engine(DB_PATH, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ StockGuru Database & Schema Initialized!")

if __name__ == "__main__":
    init_db()
