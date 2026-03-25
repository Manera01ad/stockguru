"""
Learning Engine

Main orchestrator for Phase 5 Self-Healing Strategy Layer.

Coordinates all analysis components to:
1. Fetch and analyze historical trades (90 days)
2. Calculate gate effectiveness
3. Detect current market regime
4. Generate threshold recommendations
5. Optimize risk parameters
6. Provide actionable insights for traders

This is the brain of Phase 5 - everything flows through here.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from dataclasses import asdict

from phase5_self_healing.historical_analyzer import HistoricalAnalyzer
from phase5_self_healing.gate_effectiveness import GateEffectivenessCalculator
from phase5_self_healing.market_regime_detector import MarketRegimeDetector, VIXRegimeAnalyzer
from phase5_self_healing.dynamic_optimizer import DynamicThresholdOptimizer
from phase5_self_healing.risk_tuner import RiskParameterTuner, RiskMetrics
from phase5_self_healing.statistical_utils import StatisticalUtils
from phase5_self_healing.data_models import (
    MarketRegime,
    OptimizationMetrics,
    ThresholdOptimizationLog,
)


class LearningEngine:
    """
    Phase 5 Learning Engine - Orchestrates all auto-learning and optimization
    """

    def __init__(self, db_connection=None):
        """
        Initialize Learning Engine

        Args:
            db_connection: SQLAlchemy database connection
        """
        self.db = db_connection
        self.last_analysis = None
        self.analysis_history: List[OptimizationMetrics] = []

        # Component instances
        self.historical_analyzer = HistoricalAnalyzer(db_connection)
        self.gate_effectiveness_calc = None
        self.regime_detector = MarketRegimeDetector()
        self.threshold_optimizer = DynamicThresholdOptimizer()
        self.risk_tuner = RiskParameterTuner()
        self.stat_utils = StatisticalUtils()

    def run_full_analysis(self, symbol: str = None, days: int = 90) -> Dict:
        """
        Run complete Phase 5 analysis pipeline

        Args:
            symbol: Specific symbol or None for all
            days: How many days back to analyze

        Returns:
            Complete analysis results with recommendations
        """
        print(f"🔄 Phase 5 Learning Engine - Starting full analysis ({days} days)...")

        try:
            # Stage 1: Fetch and analyze historical trades
            print("  📊 Stage 1: Analyzing historical trades...")
            trades = self.historical_analyzer.fetch_historical_trades(symbol, days)

            if not trades:
                return {"status": "no_trades", "message": "No historical trades found"}

            trade_outcomes = self.historical_analyzer.analyze_trade_outcomes()
            print(f"    ✓ Analyzed {trade_outcomes.get('total_trades', 0)} trades")

            # Stage 2: Calculate gate effectiveness
            print("  🎯 Stage 2: Calculating gate effectiveness...")
            self.gate_effectiveness_calc = GateEffectivenessCalculator(trades)
            gate_effectiveness = self.gate_effectiveness_calc.calculate_all_gates()
            effectiveness_summary = self.gate_effectiveness_calc.get_effectiveness_summary()
            print(f"    ✓ Analyzed {len(gate_effectiveness)} gates")

            # Stage 3: Detect market regime
            print("  🌍 Stage 3: Detecting market regime...")
            regime, regime_conf = self._detect_current_regime(trades)
            print(f"    ✓ Current regime: {regime.value} (confidence: {regime_conf:.1%})")

            # Stage 4: Generate threshold recommendations
            print("  💡 Stage 4: Generating threshold recommendations...")
            recommendations = self.threshold_optimizer.generate_recommendations(
                gate_effectiveness,
                regime,
                trades
            )
            print(f"    ✓ Generated {len(recommendations)} recommendations")

            # Stage 5: Optimize risk parameters
            print("  ⚠️  Stage 5: Optimizing risk parameters...")
            regime_analysis = self.historical_analyzer.analyze_by_market_regime()
            risk_metrics = self._calculate_risk_metrics(trades, regime_analysis, regime)
            risk_profile = self.risk_tuner.optimize_for_regime(regime, risk_metrics)
            print(f"    ✓ Optimized position sizing: {risk_profile.position_size_percent:.1%}")

            # Stage 6: Generate overall metrics
            print("  📈 Stage 6: Generating overall metrics...")
            metrics = self._generate_optimization_metrics(
                trades,
                gate_effectiveness,
                regime,
                recommendations
            )

            # Compile final results
            analysis_result = {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "analysis_period": {
                    "days": days,
                    "trades_analyzed": trade_outcomes.get("total_trades", 0),
                    "start_date": (datetime.utcnow() - timedelta(days=days)).isoformat(),
                    "end_date": datetime.utcnow().isoformat(),
                },
                "trade_outcomes": trade_outcomes,
                "gate_effectiveness": effectiveness_summary,
                "market_regime": {
                    "current": regime.value,
                    "confidence": regime_conf,
                    "characteristics": self.regime_detector.get_regime_characteristics(),
                    "recommendations": self.regime_detector.get_regime_recommendations(),
                },
                "threshold_recommendations": [
                    {
                        "gate": r.gate_type.value,
                        "current_threshold": r.current_threshold,
                        "recommended_threshold": r.recommended_threshold,
                        "change_percent": r.change_percent,
                        "projected_impact": {
                            "win_rate_change": r.projected_win_rate_change,
                            "signal_change_percent": r.estimated_signal_change,
                        },
                        "confidence": r.confidence_level,
                        "reasoning": r.reasoning,
                        "status": r.status,
                    }
                    for r in recommendations
                ],
                "risk_optimization": {
                    "position_size_percent": risk_profile.position_size_percent,
                    "stop_loss_atr_multiple": risk_profile.stop_loss_atr_multiple,
                    "target_rr_ratio": risk_profile.target_rr_ratio,
                    "recommendations": self.risk_tuner.get_risk_recommendations(regime),
                    "win_rate": risk_profile.win_rate,
                    "profit_factor": risk_profile.profit_factor,
                },
                "optimization_metrics": asdict(metrics),
                "next_actions": self._generate_next_actions(recommendations, metrics),
            }

            self.last_analysis = analysis_result
            self.analysis_history.append(metrics)

            print("✅ Analysis Complete!")
            return analysis_result

        except Exception as e:
            print(f"❌ Error in Learning Engine: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def _detect_current_regime(self, trades: List) -> tuple:
        """
        Detect current market regime from trades

        Args:
            trades: List of historical trades

        Returns:
            (MarketRegime, confidence)
        """
        if not trades:
            return MarketRegime.RANGING, 0.5

        # Calculate metrics from recent trades
        recent_trades = trades[-20:] if len(trades) > 20 else trades

        vix_levels = [t.vix_at_entry for t in recent_trades if t.vix_at_entry]
        avg_vix = sum(vix_levels) / len(vix_levels) if vix_levels else 20.0

        # Estimate trend strength from winning trades in one direction
        up_moves = len([t for t in recent_trades if t.is_win and t.profit_loss > 0])
        down_moves = len([t for t in recent_trades if t.is_win and t.profit_loss < 0])
        trend_strength = max(up_moves, down_moves) / len(recent_trades) if recent_trades else 0.3

        momentum = (up_moves - down_moves) / len(recent_trades) if recent_trades else 0.0

        return self.regime_detector.detect_regime(
            vix_level=avg_vix,
            atr=1.0,
            trend_strength=trend_strength,
            momentum=momentum,
        )

    def _calculate_risk_metrics(self, trades: List, regime_analysis: Dict, regime: MarketRegime) -> RiskMetrics:
        """
        Calculate risk metrics for optimization

        Args:
            trades: Historical trades
            regime_analysis: Regime-based analysis
            regime: Current market regime

        Returns:
            RiskMetrics object
        """
        if not trades:
            return RiskMetrics()

        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if not t.is_win]

        win_rate = len(wins) / len(trades) if trades else 0.5
        avg_win = sum(t.profit_loss for t in wins) / len(wins) if wins else 1000
        avg_loss = abs(sum(t.profit_loss for t in losses)) / len(losses) if losses else 500

        # Find longest streaks
        win_streak, loss_streak = 1, 1
        current_streak = 1
        for i, trade in enumerate(trades):
            if i > 0 and trades[i].is_win == trades[i-1].is_win:
                current_streak += 1
            else:
                if trades[i].is_win:
                    win_streak = max(win_streak, current_streak)
                else:
                    loss_streak = max(loss_streak, current_streak)
                current_streak = 1

        return RiskMetrics(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_winning_streak=win_streak,
            largest_losing_streak=loss_streak,
            max_drawdown=0.15,  # Placeholder
            market_regime=regime,
        )

    def _generate_optimization_metrics(self,
                                      trades: List,
                                      gate_effectiveness: Dict,
                                      regime: MarketRegime,
                                      recommendations: List) -> OptimizationMetrics:
        """
        Generate overall optimization metrics

        Args:
            trades: Historical trades
            gate_effectiveness: Gate effectiveness analysis
            regime: Current regime
            recommendations: Generated recommendations

        Returns:
            OptimizationMetrics
        """
        if not trades:
            return OptimizationMetrics()

        wins = [t for t in trades if t.is_win]

        # Find most/least effective gates
        gate_powers = {}
        for gate_key, metrics in gate_effectiveness.items():
            if gate_key == "all_gate_metrics":
                continue
            gate_powers[gate_key] = metrics.get("predictive_power", 0)

        sorted_gates = sorted(gate_powers.items(), key=lambda x: x[1], reverse=True)
        most_effective = sorted_gates[0][0] if sorted_gates else None
        least_effective = sorted_gates[-1][0] if sorted_gates else None

        # Regime distribution
        regime_counts = {}
        for trade in trades:
            regime_type = trade.market_regime or "RANGING"
            regime_counts[regime_type] = regime_counts.get(regime_type, 0) + 1

        regime_distribution = {
            k: v / len(trades) for k, v in regime_counts.items()
        } if trades else {}

        # Projected improvement
        projected_improvement = sum(
            r.projected_win_rate_change for r in recommendations
        ) if recommendations else 0.0

        return OptimizationMetrics(
            timestamp=datetime.utcnow(),
            analysis_start_date=datetime.utcnow() - timedelta(days=90),
            analysis_end_date=datetime.utcnow(),
            days_analyzed=90,
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(trades) - len(wins),
            win_rate=len(wins) / len(trades) if trades else 0,
            most_effective_gate=most_effective,
            least_effective_gate=least_effective,
            gate_effectiveness_scores=gate_powers,
            regime_distribution=regime_distribution,
            recommended_changes=recommendations,
            projected_improvement=projected_improvement,
            recommendation_count=len(recommendations),
        )

    def _generate_next_actions(self, recommendations: List, metrics: OptimizationMetrics) -> List[Dict]:
        """
        Generate actionable next steps for trader

        Args:
            recommendations: Threshold recommendations
            metrics: Optimization metrics

        Returns:
            List of next actions
        """
        actions = []

        # Action 1: Review pending recommendations
        if recommendations:
            actions.append({
                "priority": "HIGH",
                "action": "Review pending gate threshold recommendations",
                "details": f"{len(recommendations)} recommendations awaiting approval",
                "expected_impact": f"+{metrics.projected_improvement:.1%} win-rate improvement if approved",
                "timeline": "Within 24 hours",
            })

        # Action 2: Monitor risk parameters
        actions.append({
            "priority": "MEDIUM",
            "action": "Review risk parameter recommendations for current regime",
            "details": f"Optimized for {metrics.analysis_end_date.strftime('%Y-%m-%d')}",
            "expected_impact": "Better risk management for current market conditions",
            "timeline": "Before next trading session",
        })

        # Action 3: Track effectiveness
        actions.append({
            "priority": "MEDIUM",
            "action": "Track effectiveness of implemented recommendations",
            "details": "Monitor win-rate improvements over next 20-30 trades",
            "expected_impact": "Validate projections and adjust as needed",
            "timeline": "Ongoing",
        })

        return actions

    def get_analysis_history(self, limit: int = 10) -> List[OptimizationMetrics]:
        """
        Get recent analysis history

        Args:
            limit: Max number of analyses to return

        Returns:
            List of OptimizationMetrics
        """
        return self.analysis_history[-limit:]

    def get_latest_analysis(self) -> Optional[Dict]:
        """
        Get most recent analysis results

        Returns:
            Latest analysis dictionary or None
        """
        return self.last_analysis

    def should_rerun_analysis(self, min_hours: float = 24.0) -> bool:
        """
        Check if analysis should be rerun

        Args:
            min_hours: Minimum hours since last analysis

        Returns:
            True if should rerun
        """
        if not self.last_analysis:
            return True

        last_run = datetime.fromisoformat(self.last_analysis["timestamp"])
        hours_elapsed = (datetime.utcnow() - last_run).total_seconds() / 3600

        return hours_elapsed >= min_hours

    def export_analysis_to_json(self, filepath: str):
        """
        Export latest analysis to JSON file

        Args:
            filepath: Path to save JSON file
        """
        if not self.last_analysis:
            print("No analysis to export")
            return

        try:
            with open(filepath, 'w') as f:
                json.dump(self.last_analysis, f, indent=2, default=str)
            print(f"✓ Analysis exported to {filepath}")
        except Exception as e:
            print(f"✗ Error exporting analysis: {e}")

    def get_summary_report(self) -> Dict:
        """
        Get human-readable summary report

        Returns:
            Summary dictionary for display/logging
        """
        if not self.last_analysis:
            return {"status": "no_analysis"}

        analysis = self.last_analysis
        metrics = analysis.get("optimization_metrics", {})

        return {
            "period": f"{analysis['analysis_period']['days']} days",
            "trades_analyzed": analysis['analysis_period']['trades_analyzed'],
            "current_win_rate": f"{metrics.get('win_rate', 0):.1%}",
            "current_regime": analysis['market_regime']['current'],
            "pending_recommendations": len(analysis['threshold_recommendations']),
            "projected_improvement": f"+{metrics.get('projected_improvement', 0):.1%}",
            "most_effective_gate": metrics.get('most_effective_gate'),
            "least_effective_gate": metrics.get('least_effective_gate'),
            "next_actions": len(analysis.get('next_actions', [])),
            "timestamp": analysis['timestamp'],
        }
