import sys
import os
import unittest
from datetime import datetime, timedelta

# Add project root to sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

# Import Phase 5 components
from phase5_self_healing.learning_engine import LearningEngine
from phase5_self_healing.data_models import MarketRegime
from conviction_filter import ConvictionFilter

class TestPhase5SelfHealing(unittest.TestCase):
    def setUp(self):
        self.engine = LearningEngine()
        self.shared_state = {
            "trade_signals": [],
            "paper_portfolio": {"capital": 500000},
            "active_gate_thresholds": {}
        }

    def test_run_analysis_dry(self):
        """Test that the engine runs without crashing on empty data."""
        results = self.engine.run_full_analysis(days=7)
        self.assertIn("status", results)
        if results.get("status") == "success":
            self.assertIn("optimization_metrics", results)
            self.assertIn("threshold_recommendations", results)
        else:
            self.assertIn("no_trades", results.get("status"))
        print(f"✅ Analysis run completed. Mode: {results.get('market_regime', {}).get('current', 'N/A')}")

    def test_threshold_overrides(self):
        """Test that ConvictionFilter correctly picks up overrides."""
        self.shared_state["active_gate_thresholds"] = {
            "gate_8_vix_max": 35.0  # Volatility-adjusted threshold
        }
        
        # Initialize filter with state
        cf = ConvictionFilter(shared_state=self.shared_state)
        
        # Check if override was applied
        self.assertEqual(cf.active_thresholds["gate_8_vix_max"], 35.0)
        # Check that defaults are still there
        self.assertEqual(cf.active_thresholds["minimum_gates_to_execute"], 6)
        print("✅ Threshold override verified successfully!")

    def test_regime_detection_logic(self):
        """Test the regime detector independently."""
        from phase5_self_healing.market_regime_detector import MarketRegimeDetector
        detector = MarketRegimeDetector()
        
        # Pseudo-data
        vix = 12.0
        atr = 1.0
        trend_strength = 0.8
        momentum = 0.5
        regime, conf = detector.detect_regime(vix, atr, trend_strength, momentum)
        self.assertIsInstance(regime, MarketRegime)
        print(f"✅ Regime detection test: {regime} (confidence: {conf})")

if __name__ == "__main__":
    unittest.main()
