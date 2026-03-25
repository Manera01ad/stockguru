"""
Historical Analyzer

Analyzes 90-day rolling window of historical trades to understand:
- Trade outcomes (win/loss, profit/loss)
- Gate performance (which gates passed/failed)
- Market conditions (regime, VIX levels)
- Pattern recognition (what conditions preceded winners/losers)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import statistics


@dataclass
class TradeRecord:
    """Analyzed historical trade record"""
    trade_id: int
    symbol: str
    entry_datetime: datetime
    exit_datetime: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    quantity: int
    status: str  # "open", "closed", "cancelled"

    # Outcome
    profit_loss: float = 0.0
    profit_loss_percent: float = 0.0
    is_win: bool = False

    # Gates (which passed/failed)
    gates_passed: Dict[str, bool] = None
    conviction_level: str = "LOW"
    conviction_count: int = 0

    # Market context
    vix_at_entry: float = 20.0
    market_regime: str = "RANGING"
    time_of_day: str = "normal"

    # Risk metrics
    intended_risk_amount: float = 0.0
    actual_risk_taken: float = 0.0
    rr_ratio: float = 0.0


class HistoricalAnalyzer:
    """
    Analyzes historical trade data to understand:
    - Which gates are most effective
    - Performance in different market regimes
    - Seasonal patterns and optimal trading windows
    """

    def __init__(self, db_connection=None):
        """
        Initialize analyzer with database connection

        Args:
            db_connection: SQLAlchemy session or connection
        """
        self.db = db_connection
        self.analysis_period_days = 90
        self.trades: List[TradeRecord] = []
        self.metadata = {}

    def fetch_historical_trades(self, symbol: str = None, limit_days: int = 90) -> List[TradeRecord]:
        """
        Fetch last N days of closed trades from database

        Args:
            symbol: Specific symbol or None for all
            limit_days: How far back to look

        Returns:
            List of TradeRecord objects
        """
        if not self.db:
            return self._generate_mock_trades(limit_days)

        cutoff_date = datetime.utcnow() - timedelta(days=limit_days)
        trades = []

        try:
            # Query from stockguru database
            # This assumes trades are stored with ConvictionAudit records
            # Actual query depends on your schema

            query = self.db.query(Trade).filter(
                Trade.exit_datetime >= cutoff_date,
                Trade.status == "closed"
            )

            if symbol:
                query = query.filter(Trade.symbol == symbol)

            for db_trade in query.all():
                trade = TradeRecord(
                    trade_id=db_trade.id,
                    symbol=db_trade.symbol,
                    entry_datetime=db_trade.entry_datetime,
                    exit_datetime=db_trade.exit_datetime,
                    entry_price=db_trade.entry_price,
                    exit_price=db_trade.exit_price,
                    quantity=db_trade.quantity,
                    status=db_trade.status,
                    profit_loss=db_trade.profit_loss,
                    is_win=db_trade.profit_loss > 0,
                    conviction_count=db_trade.conviction_audit.gates_passed if hasattr(db_trade, 'conviction_audit') else 0,
                    vix_at_entry=db_trade.vix_at_entry if hasattr(db_trade, 'vix_at_entry') else 20.0,
                    market_regime=db_trade.market_regime if hasattr(db_trade, 'market_regime') else "RANGING",
                )
                trades.append(trade)

        except Exception as e:
            print(f"Error fetching trades: {e}. Using mock data.")
            trades = self._generate_mock_trades(limit_days)

        self.trades = trades
        self.analysis_period_days = limit_days
        return trades

    def analyze_trade_outcomes(self) -> Dict:
        """
        Calculate overall trading statistics

        Returns:
            Dictionary with win rate, profit factor, etc.
        """
        if not self.trades:
            return {}

        wins = [t for t in self.trades if t.is_win]
        losses = [t for t in self.trades if not t.is_win]

        if not wins and not losses:
            return {}

        win_rate = len(wins) / len(self.trades) if self.trades else 0
        avg_win = statistics.mean([t.profit_loss for t in wins]) if wins else 0
        avg_loss = statistics.mean([t.profit_loss for t in losses]) if losses else 0

        total_profit = sum(t.profit_loss for t in wins)
        total_loss = abs(sum(t.profit_loss for t in losses)) if losses else 0

        profit_factor = total_profit / total_loss if total_loss > 0 else 1.0

        return {
            "total_trades": len(self.trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "total_profit": total_profit,
            "total_loss": total_loss,
        }

    def analyze_by_market_regime(self) -> Dict[str, Dict]:
        """
        Analyze performance in different market regimes

        Returns:
            {"TRENDING": {stats}, "RANGING": {stats}, "VOLATILE": {stats}}
        """
        regimes = defaultdict(list)

        for trade in self.trades:
            regime = trade.market_regime or "RANGING"
            regimes[regime].append(trade)

        results = {}
        for regime, trades in regimes.items():
            if trades:
                wins = len([t for t in trades if t.is_win])
                results[regime] = {
                    "total_trades": len(trades),
                    "winning_trades": wins,
                    "win_rate": wins / len(trades),
                    "avg_profit": statistics.mean([t.profit_loss for t in trades]),
                }
            else:
                results[regime] = {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "win_rate": 0.0,
                    "avg_profit": 0.0,
                }

        return results

    def analyze_by_time_of_day(self) -> Dict[str, Dict]:
        """
        Analyze performance by time of day (market phases)

        Returns:
            Statistics for different market phases
        """
        time_buckets = defaultdict(list)

        for trade in self.trades:
            hour = trade.entry_datetime.hour if trade.entry_datetime else 9
            if 9 <= hour < 10:
                phase = "market_open"
            elif 10 <= hour < 14:
                phase = "mid_day"
            elif 14 <= hour < 15:
                phase = "afternoon"
            else:
                phase = "after_hours"

            time_buckets[phase].append(trade)

        results = {}
        for phase, trades in time_buckets.items():
            if trades:
                wins = len([t for t in trades if t.is_win])
                results[phase] = {
                    "total_trades": len(trades),
                    "winning_trades": wins,
                    "win_rate": wins / len(trades),
                    "avg_profit": statistics.mean([t.profit_loss for t in trades]),
                }

        return results

    def analyze_gate_effectiveness(self) -> Dict[str, Dict]:
        """
        Analyze effectiveness of each conviction gate

        Returns:
            {"gate_1": {metrics}, "gate_2": {metrics}, ...}
        """
        gate_stats = defaultdict(lambda: {
            "passed": [],
            "failed": [],
            "wins_when_passed": 0,
            "wins_when_failed": 0,
        })

        # Collect gate data from all trades
        for trade in self.trades:
            if not trade.gates_passed:
                continue

            for gate_name, gate_passed in trade.gates_passed.items():
                if gate_passed:
                    gate_stats[gate_name]["passed"].append(trade)
                    if trade.is_win:
                        gate_stats[gate_name]["wins_when_passed"] += 1
                else:
                    gate_stats[gate_name]["failed"].append(trade)
                    if trade.is_win:
                        gate_stats[gate_name]["wins_when_failed"] += 1

        # Calculate metrics
        results = {}
        for gate_name, stats in gate_stats.items():
            passed_count = len(stats["passed"])
            failed_count = len(stats["failed"])

            passed_win_rate = (
                stats["wins_when_passed"] / passed_count
                if passed_count > 0 else 0
            )
            failed_win_rate = (
                stats["wins_when_failed"] / failed_count
                if failed_count > 0 else 0
            )

            # Predictive power: how much better/worse when gate passes
            predictive_power = passed_win_rate - failed_win_rate

            results[gate_name] = {
                "total_passed": passed_count,
                "total_failed": failed_count,
                "pass_rate": passed_count / (passed_count + failed_count) if (passed_count + failed_count) > 0 else 0,
                "wins_when_passed": stats["wins_when_passed"],
                "wins_when_failed": stats["wins_when_failed"],
                "win_rate_when_passed": passed_win_rate,
                "win_rate_when_failed": failed_win_rate,
                "predictive_power": predictive_power,  # How much gate correlates with wins
            }

        return results

    def get_summary(self) -> Dict:
        """
        Get complete analysis summary

        Returns:
            Comprehensive analysis of all metrics
        """
        return {
            "period_days": self.analysis_period_days,
            "analysis_date": datetime.utcnow().isoformat(),
            "trade_outcomes": self.analyze_trade_outcomes(),
            "by_market_regime": self.analyze_by_market_regime(),
            "by_time_of_day": self.analyze_by_time_of_day(),
            "gate_effectiveness": self.analyze_gate_effectiveness(),
        }

    def _generate_mock_trades(self, limit_days: int = 90) -> List[TradeRecord]:
        """
        Generate mock trade data for testing (when database unavailable)

        Args:
            limit_days: How many days back to generate

        Returns:
            List of mock trades
        """
        import random

        trades = []
        start_date = datetime.utcnow() - timedelta(days=limit_days)

        for i in range(50):  # 50 mock trades
            entry_date = start_date + timedelta(
                days=random.randint(0, limit_days),
                hours=random.randint(9, 14)
            )

            is_win = random.random() < 0.65  # 65% win rate in mock
            profit_loss = random.uniform(1000, 5000) if is_win else random.uniform(-2000, -500)

            trade = TradeRecord(
                trade_id=i,
                symbol=random.choice(["RELIANCE", "TCS", "INFY", "HDFC"]),
                entry_datetime=entry_date,
                exit_datetime=entry_date + timedelta(hours=2),
                entry_price=random.uniform(1500, 3000),
                exit_price=random.uniform(1500, 3000),
                quantity=10,
                status="closed",
                profit_loss=profit_loss,
                is_win=is_win,
                conviction_count=random.randint(5, 8),
                vix_at_entry=random.uniform(15, 25),
                market_regime=random.choice(["TRENDING", "RANGING", "VOLATILE"]),
                gates_passed={
                    "technical_setup": random.random() > 0.2,
                    "volume_confirmation": random.random() > 0.15,
                    "agent_consensus": random.random() > 0.1,
                    "risk_reward": random.random() > 0.2,
                    "time_of_day": random.random() > 0.1,
                    "institutional_flow": random.random() > 0.25,
                    "news_sentiment": random.random() > 0.3,
                    "vix_check": random.random() > 0.05,
                }
            )
            trades.append(trade)

        return trades
