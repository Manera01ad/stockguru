"""
Phase 5 Integration: Update conviction_filter.py

MODIFICATIONS TO conviction_filter.py TO USE PHASE 5 DYNAMIC THRESHOLDS

This integration allows the 8-gate conviction filter to dynamically adjust
its thresholds based on Phase 5 analysis and current market regime.
"""

# ============================================================================
# PART 1: Add imports at top of conviction_filter.py
# ============================================================================

"""
Add these imports:

from phase5_self_healing.learning_engine import LearningEngine
from phase5_self_healing.market_regime_detector import MarketRegimeDetector
from phase5_self_healing.data_models import MarketRegime
from datetime import datetime, timedelta
"""


# ============================================================================
# PART 2: Add Phase 5 Integration Class
# ============================================================================

"""
Add this class to conviction_filter.py:
"""

class Phase5ConvictionFilter:
    """
    Extends ConvictionFilter with Phase 5 dynamic threshold capability
    """

    def __init__(self, db_connection=None, shared_state=None):
        """
        Initialize with Phase 5 learning engine

        Args:
            db_connection: SQLAlchemy session
            shared_state: Shared state dict for app (for live threshold updates)
        """
        self.db = db_connection
        self.shared_state = shared_state or {}
        self.learning_engine = LearningEngine(db_connection=db_connection)
        self.regime_detector = MarketRegimeDetector()

        # Cache of dynamic thresholds by regime
        self.dynamic_thresholds = {}
        self.last_threshold_update = None
        self.threshold_cache_ttl = 3600  # 1 hour

    def get_current_market_regime(self) -> MarketRegime:
        """
        Detect current market regime for threshold selection

        Returns:
            MarketRegime enum
        """
        # In production, fetch real VIX, ATR, trend data
        # For now, use detector with dummy data
        vix = self.get_vix_level()  # Your VIX fetching logic
        trend_strength = self.get_trend_strength()
        momentum = self.get_momentum()

        regime, confidence = self.regime_detector.detect_regime(
            vix_level=vix,
            atr=1.0,
            trend_strength=trend_strength,
            momentum=momentum
        )

        return regime

    def load_dynamic_thresholds(self, force_refresh=False) -> dict:
        """
        Load Phase 5 optimized thresholds from database

        Args:
            force_refresh: Force reload even if cached

        Returns:
            Dictionary of gate thresholds by regime
        """
        # Check cache
        if (self.dynamic_thresholds and
            self.last_threshold_update and
            (datetime.utcnow() - self.last_threshold_update).seconds < self.threshold_cache_ttl
            and not force_refresh):
            return self.dynamic_thresholds

        # Load from database
        thresholds = {}
        try:
            # Query DynamicThreshold table (added in Phase 5 schema)
            if self.db:
                from stockguru_agents.models import DynamicThreshold
                query = self.db.query(DynamicThreshold).filter(
                    DynamicThreshold.is_active == True
                )

                for threshold in query.all():
                    key = f"{threshold.gate_name}_{threshold.market_regime}"
                    thresholds[key] = threshold.current_value

            self.dynamic_thresholds = thresholds
            self.last_threshold_update = datetime.utcnow()

        except Exception as e:
            print(f"Error loading Phase 5 thresholds: {e}")
            # Fall back to hardcoded defaults

        return thresholds

    def get_gate_threshold(self, gate_name: str, market_regime: MarketRegime = None) -> float:
        """
        Get threshold for specific gate, adjusted for regime

        Args:
            gate_name: Name of gate (e.g., "technical_setup")
            market_regime: Current market regime (auto-detect if None)

        Returns:
            Threshold value
        """
        if market_regime is None:
            market_regime = self.get_current_market_regime()

        # Load Phase 5 thresholds
        thresholds = self.load_dynamic_thresholds()

        # Try regime-specific threshold first
        regime_key = f"{gate_name}_{market_regime.value}"
        if regime_key in thresholds:
            return thresholds[regime_key]

        # Fall back to general threshold
        general_key = f"{gate_name}_all"
        if general_key in thresholds:
            return thresholds[general_key]

        # Fall back to hardcoded defaults
        return self._get_default_threshold(gate_name)

    def evaluate_gate_with_phase5(self, gate_name: str, gate_score: float,
                                  market_regime: MarketRegime = None) -> bool:
        """
        Evaluate gate using Phase 5 optimized threshold

        Args:
            gate_name: Name of gate
            gate_score: Score to compare against threshold (0-1)
            market_regime: Current regime (auto-detect if None)

        Returns:
            True if gate passes, False otherwise
        """
        threshold = self.get_gate_threshold(gate_name, market_regime)

        # Apply threshold
        passes = gate_score >= threshold

        # Log to shared state for real-time monitoring
        if self.shared_state is not None:
            if 'gate_evaluations' not in self.shared_state:
                self.shared_state['gate_evaluations'] = {}

            self.shared_state['gate_evaluations'][gate_name] = {
                'passes': passes,
                'score': gate_score,
                'threshold': threshold,
                'regime': market_regime.value if market_regime else 'unknown',
                'timestamp': datetime.utcnow().isoformat()
            }

        return passes

    def evaluate_conviction_with_phase5(self, signals: dict, shared_state: dict = None) -> dict:
        """
        Evaluate all 8 gates with Phase 5 optimization

        Args:
            signals: Dictionary of gate signal values
            shared_state: Shared state for live updates

        Returns:
            {
                'passes_all_gates': bool,
                'gates_passed': int,
                'conviction_level': str,
                'market_regime': str,
                'gate_results': {gate: passed},
                'recommended_action': str
            }
        """
        # Detect current regime
        market_regime = self.get_current_market_regime()

        # Evaluate all 8 gates
        gate_results = {}
        gates_passed = 0

        for gate_name, gate_score in signals.items():
            passes = self.evaluate_gate_with_phase5(gate_name, gate_score, market_regime)
            gate_results[gate_name] = passes
            if passes:
                gates_passed += 1

        # Determine conviction level
        if gates_passed >= 6:
            conviction = "HIGH"
        elif gates_passed >= 5:
            conviction = "MEDIUM"
        elif gates_passed >= 4:
            conviction = "LOW"
        else:
            conviction = "REJECT"

        # Regime-specific recommendation
        regime_actions = {
            MarketRegime.TRENDING: "Follow trend entries only",
            MarketRegime.RANGING: "Mean reversion entries preferred",
            MarketRegime.VOLATILE: "Very restrictive, wait for clarity"
        }

        return {
            'passes_all_gates': gates_passed >= 6,
            'gates_passed': gates_passed,
            'conviction_level': conviction,
            'market_regime': market_regime.value,
            'gate_results': gate_results,
            'threshold_source': 'phase5_optimized',
            'recommended_action': regime_actions.get(market_regime, "Proceed with caution"),
        }

    # ========================================================================
    # Helper methods to integrate with your existing code
    # ========================================================================

    def _get_default_threshold(self, gate_name: str) -> float:
        """
        Get hardcoded default threshold (fallback)

        Args:
            gate_name: Gate identifier

        Returns:
            Default threshold value
        """
        defaults = {
            'technical_setup': 0.70,
            'volume_confirmation': 0.75,
            'agent_consensus': 0.60,
            'risk_reward': 0.65,
            'time_of_day': 0.80,
            'institutional_flow': 0.70,
            'news_sentiment': 0.75,
            'vix_check': 0.85,
        }
        return defaults.get(gate_name, 0.70)

    def get_vix_level(self) -> float:
        """
        Fetch current VIX level

        In production, integrate with your VIX data source
        """
        # Placeholder - implement with your data source
        return 20.0

    def get_trend_strength(self) -> float:
        """
        Calculate trend strength (0-1)

        In production, implement with your technical analysis
        """
        # Placeholder
        return 0.5

    def get_momentum(self) -> float:
        """
        Calculate momentum (-1 to 1)

        In production, implement with your technical analysis
        """
        # Placeholder
        return 0.2


# ============================================================================
# PART 3: Update evaluate_conviction() method
# ============================================================================

"""
In your existing ConvictionFilter class, update the evaluate_conviction() method:

Original:
    def evaluate_conviction(self, signals):
        gates_passed = 0
        for gate in self.GATES:
            if signals[gate] > self.thresholds[gate]:  # Hardcoded threshold
                gates_passed += 1
        ...

Updated to use Phase 5:
    def evaluate_conviction(self, signals):
        # Use Phase 5 optimization instead
        phase5_result = self.phase5_filter.evaluate_conviction_with_phase5(
            signals,
            shared_state=self.shared_state
        )

        return {
            'conviction_count': phase5_result['gates_passed'],
            'conviction_level': phase5_result['conviction_level'],
            'should_trade': phase5_result['passes_all_gates'],
            'market_regime': phase5_result['market_regime'],
            'gate_details': phase5_result['gate_results'],
        }
"""


# ============================================================================
# PART 4: Usage example
# ============================================================================

"""
In your app initialization or trading loop:

from conviction_filter import Phase5ConvictionFilter

# Initialize with database connection
phase5_filter = Phase5ConvictionFilter(
    db_connection=db.session,
    shared_state=shared_state  # For live updates
)

# In your trade entry logic:
gate_signals = {
    'technical_setup': calculate_technical_score(),
    'volume_confirmation': calculate_volume_score(),
    'agent_consensus': calculate_consensus_score(),
    # ... etc for all 8 gates
}

result = phase5_filter.evaluate_conviction_with_phase5(gate_signals)

if result['passes_all_gates']:
    # Enter trade with Phase 5 optimized parameters
    print(f"Trading in {result['market_regime']} regime")
    print(f"Gate details: {result['gate_results']}")
    # ... execute trade logic
else:
    print(f"Rejected: Only {result['gates_passed']}/8 gates passed")
    print(f"Reason: {result['recommended_action']}")
"""
