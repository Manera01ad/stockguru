"""
Phase 5 Integration: Update paper_trader.py

MODIFICATIONS TO paper_trader.py TO USE PHASE 5 RISK OPTIMIZATION

This integration allows the paper trading engine to dynamically adjust:
- Position sizing
- Stop loss distances
- Target profit ratios
Based on current market regime and Phase 5 analysis
"""

# ============================================================================
# PART 1: Add imports to paper_trader.py
# ============================================================================

"""
Add these imports at the top:

from phase5_self_healing.learning_engine import LearningEngine
from phase5_self_healing.market_regime_detector import MarketRegimeDetector
from phase5_self_healing.risk_tuner import RiskParameterTuner, RiskMetrics
from phase5_self_healing.data_models import MarketRegime
from datetime import datetime
"""


# ============================================================================
# PART 2: Add Phase 5 Risk Manager Class
# ============================================================================

"""
Add this class to paper_trader.py:
"""

class Phase5RiskManager:
    """
    Manages position sizing, stops, and targets using Phase 5 optimization
    """

    def __init__(self, db_connection=None, initial_account_equity=100000):
        """
        Initialize risk manager with Phase 5 components

        Args:
            db_connection: SQLAlchemy session
            initial_account_equity: Starting account size
        """
        self.db = db_connection
        self.account_equity = initial_account_equity
        self.peak_equity = initial_account_equity
        self.learning_engine = LearningEngine(db_connection=db_connection)
        self.regime_detector = MarketRegimeDetector()
        self.risk_tuner = RiskParameterTuner()

        # Cache of optimized risk parameters by regime
        self.risk_profiles = {}
        self.current_regime = MarketRegime.RANGING
        self.last_optimization_time = None

    def update_market_regime(self, vix: float, atr: float, trend_strength: float,
                            momentum: float):
        """
        Update current market regime detection

        Args:
            vix: Current VIX level
            atr: Average True Range
            trend_strength: Trend strength (0-1)
            momentum: Momentum indicator (-1 to 1)
        """
        regime, confidence = self.regime_detector.detect_regime(
            vix_level=vix,
            atr=atr,
            trend_strength=trend_strength,
            momentum=momentum
        )
        self.current_regime = regime

    def calculate_position_size(self, account_equity: float = None,
                               risk_amount: float = None,
                               entry_price: float = None,
                               stop_loss_price: float = None) -> float:
        """
        Calculate optimal position size using Phase 5 optimization

        Args:
            account_equity: Current account size (use self.account_equity if None)
            risk_amount: Max risk in currency (calculate from risk% if None)
            entry_price: Entry price
            stop_loss_price: Stop loss price

        Returns:
            Position quantity
        """
        if account_equity is None:
            account_equity = self.account_equity

        # Get Phase 5 optimized risk profile for current regime
        risk_profile = self.get_risk_profile(self.current_regime)

        # Calculate position size as % of account
        position_size_percent = risk_profile.position_size_percent

        # Get risk amount
        if risk_amount is None:
            risk_amount = account_equity * position_size_percent

        # Calculate position quantity
        if entry_price and stop_loss_price:
            risk_per_share = abs(entry_price - stop_loss_price)
            if risk_per_share > 0:
                quantity = int(risk_amount / risk_per_share)
                return max(1, quantity)

        # Fallback: use percentage directly
        return max(1, int(account_equity * position_size_percent / entry_price))

    def calculate_stop_loss(self, entry_price: float, atr: float,
                           direction: str = "long") -> float:
        """
        Calculate stop loss price using Phase 5 optimization

        Args:
            entry_price: Entry price
            atr: Average True Range
            direction: "long" or "short"

        Returns:
            Stop loss price
        """
        # Get Phase 5 optimized stop loss multiple
        risk_profile = self.get_risk_profile(self.current_regime)
        stop_multiple = risk_profile.stop_loss_atr_multiple

        # Calculate stop loss
        stop_distance = atr * stop_multiple

        if direction.lower() == "long":
            return entry_price - stop_distance
        else:  # short
            return entry_price + stop_distance

    def calculate_target_price(self, entry_price: float, stop_loss: float,
                              direction: str = "long") -> float:
        """
        Calculate profit target using Phase 5 R:R optimization

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            direction: "long" or "short"

        Returns:
            Target profit price
        """
        # Get Phase 5 optimized R:R ratio
        risk_profile = self.get_risk_profile(self.current_regime)
        target_rr = risk_profile.target_rr_ratio

        # Calculate risk distance
        risk_distance = abs(entry_price - stop_loss)

        # Calculate target distance (risk * R:R)
        target_distance = risk_distance * target_rr

        if direction.lower() == "long":
            return entry_price + target_distance
        else:  # short
            return entry_price - target_distance

    def get_risk_profile(self, regime: MarketRegime):
        """
        Get or create Phase 5 optimized risk profile for regime

        Args:
            regime: Market regime

        Returns:
            RiskParameterProfile object
        """
        # Check cache
        if regime in self.risk_profiles:
            return self.risk_profiles[regime]

        # Load from Phase 5
        try:
            # In production, query RiskOptimization table from Phase 5 schema
            if self.db:
                from stockguru_agents.models import RiskOptimization
                profile = self.db.query(RiskOptimization).filter(
                    RiskOptimization.market_regime == regime.value,
                    RiskOptimization.is_active == True
                ).first()

                if profile:
                    self.risk_profiles[regime] = profile
                    return profile

        except Exception as e:
            print(f"Error loading Phase 5 risk profile: {e}")

        # Fallback: Generate default profile using RiskTuner
        risk_metrics = RiskMetrics(
            win_rate=0.60,
            avg_win=1500,
            avg_loss=1000,
            market_regime=regime
        )

        default_profile = self.risk_tuner.optimize_for_regime(regime, risk_metrics)
        self.risk_profiles[regime] = default_profile
        return default_profile

    def adapt_position_size_to_drawdown(self, current_equity: float) -> float:
        """
        Scale position size based on current drawdown

        Args:
            current_equity: Current account equity

        Returns:
            Position size multiplier (e.g., 0.8 = 20% reduction)
        """
        drawdown = 1.0 - (current_equity / self.peak_equity)

        # Phase 5 recommended: reduce by 20% per 1% drawdown above historical max
        max_historical_drawdown = 0.15

        if drawdown > max_historical_drawdown:
            excess_drawdown = drawdown - max_historical_drawdown
            reduction = 1.0 - (excess_drawdown * 20)
            return max(0.5, reduction)  # Never reduce below 50%

        return 1.0

    def update_account_equity(self, new_equity: float):
        """
        Update account equity and track peak for drawdown calculation

        Args:
            new_equity: New account equity
        """
        self.account_equity = new_equity
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity

    def get_regime_recommendations(self) -> dict:
        """
        Get trading recommendations for current regime from Phase 5

        Returns:
            Dictionary of recommendations
        """
        risk_profile = self.get_risk_profile(self.current_regime)
        return self.risk_tuner.get_risk_recommendations(self.current_regime)

    def log_trade_to_phase5(self, trade_data: dict):
        """
        Log trade execution details for Phase 5 feedback

        Args:
            trade_data: Dictionary with trade details
                {
                    'symbol': 'RELIANCE',
                    'entry_time': datetime,
                    'entry_price': 2500,
                    'quantity': 10,
                    'stop_loss': 2450,
                    'target': 2600,
                    'market_regime': 'TRENDING',
                    'gates_passed': 6
                }
        """
        # In production, save to database for Phase 5 feedback
        try:
            if self.db:
                # Log to ConvictionAudit or Trade table
                # This allows Phase 5 to analyze how its recommendations performed
                pass
        except Exception as e:
            print(f"Error logging trade to Phase 5: {e}")


# ============================================================================
# PART 3: Update execute_trade() method
# ============================================================================

"""
In your existing PaperTradingEngine class, update trade execution:

Original code (simplified):
    def execute_trade(self, signal):
        entry_price = signal['price']
        position_size = HARDCODED_SIZE  # Fixed position size
        stop_loss = entry_price - 50     # Hardcoded stop distance
        target = entry_price + 100       # Hardcoded target
        ...

Updated with Phase 5:
    def execute_trade(self, signal):
        entry_price = signal['price']

        # Use Phase 5 risk management
        position_size = self.risk_manager.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=self.risk_manager.calculate_stop_loss(
                entry_price,
                signal['atr'],
                direction='long'
            )
        )

        stop_loss = self.risk_manager.calculate_stop_loss(
            entry_price,
            signal['atr'],
            direction='long'
        )

        target = self.risk_manager.calculate_target_price(
            entry_price,
            stop_loss,
            direction='long'
        )

        # Adapt for drawdown
        size_multiplier = self.risk_manager.adapt_position_size_to_drawdown(
            self.account_equity
        )
        position_size = int(position_size * size_multiplier)

        # Log for Phase 5 feedback
        self.risk_manager.log_trade_to_phase5({
            'symbol': signal['symbol'],
            'entry_time': datetime.utcnow(),
            'entry_price': entry_price,
            'quantity': position_size,
            'stop_loss': stop_loss,
            'target': target,
            'market_regime': self.risk_manager.current_regime.value,
            'gates_passed': signal.get('conviction_count', 0)
        })

        # Execute trade...
"""


# ============================================================================
# PART 4: Update market monitoring
# ============================================================================

"""
Add this to your main trading loop to continuously update regime:

    def market_monitoring_loop(self):
        while trading_active:
            current_data = get_market_data()

            # Update Phase 5 market regime
            self.risk_manager.update_market_regime(
                vix=current_data['vix'],
                atr=current_data['atr'],
                trend_strength=current_data['trend_strength'],
                momentum=current_data['momentum']
            )

            # Check if Phase 5 analysis should be rerun
            if self.risk_manager.learning_engine.should_rerun_analysis(min_hours=24):
                results = self.risk_manager.learning_engine.run_full_analysis()
                print(f"Phase 5 Analysis: {results['market_regime']['current']}")

            # Update equity
            self.risk_manager.update_account_equity(self.account_equity)

            time.sleep(60)  # Check every minute
"""


# ============================================================================
# PART 5: Usage example
# ============================================================================

"""
In your app initialization:

from paper_trader import PaperTradingEngine, Phase5RiskManager

# Initialize
engine = PaperTradingEngine()
risk_manager = Phase5RiskManager(
    db_connection=db.session,
    initial_account_equity=100000
)

# In trading loop:
for signal in trading_signals:
    # Update market regime
    risk_manager.update_market_regime(
        vix=signal['vix'],
        atr=signal['atr'],
        trend_strength=signal['trend_strength'],
        momentum=signal['momentum']
    )

    # Calculate position parameters using Phase 5
    stop = risk_manager.calculate_stop_loss(signal['price'], signal['atr'])
    target = risk_manager.calculate_target_price(signal['price'], stop)
    position_size = risk_manager.calculate_position_size(
        entry_price=signal['price'],
        stop_loss_price=stop
    )

    # Execute trade
    engine.execute_trade(
        symbol=signal['symbol'],
        entry_price=signal['price'],
        quantity=position_size,
        stop_loss=stop,
        target=target,
        regime=risk_manager.current_regime.value
    )

    # Log for Phase 5 feedback
    risk_manager.log_trade_to_phase5({
        'symbol': signal['symbol'],
        'entry_price': signal['price'],
        'entry_time': datetime.utcnow(),
        'quantity': position_size,
        'stop_loss': stop,
        'target': target,
        'market_regime': risk_manager.current_regime.value,
        'gates_passed': signal.get('conviction_count', 0)
    })
"""
