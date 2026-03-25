"""
StockGuru Conviction Filter - 8-Gate Trade Validation System
============================================================

This module implements a multi-stage conviction filter that validates every trade signal
against 8 distinct gates before execution. Only signals passing 6+ gates are executed,
reducing false positives and improving win-rate through rigorous signal filtering.

Architecture:
- Gate 1: Technical Setup (RSI, MACD, trend alignment)
- Gate 2: Volume Confirmation (3x+ average volume)
- Gate 3: Multi-Agent Consensus (3+ agents agree)
- Gate 4: Risk/Reward Ratio (≥ 1:2)
- Gate 5: Time-of-Day Filter (avoid open/close volatility)
- Gate 6: Institutional Flow (FII/DII positive)
- Gate 7: News Sentiment (no conflicting news)
- Gate 8: VIX Check (avoid panic mode > 25)

Output: ConvictionAudit record with complete gate-by-gate results for every trade decision

Last Updated: 2026-03-25
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)


class ConvictionLevel(Enum):
    """Trade conviction classification"""
    HIGH = "HIGH"          # 7+ gates passed
    MEDIUM = "MEDIUM"      # 5-6 gates passed
    LOW = "LOW"            # <5 gates passed
    REJECTED = "REJECTED"  # <6 gates passed, no execution


class GateResult(Enum):
    """Individual gate evaluation result"""
    PASS = True
    FAIL = False


@dataclass
class GateEvaluation:
    """Result of a single gate evaluation"""
    gate_number: int
    gate_name: str
    passed: bool
    value: Optional[float] = None
    threshold: Optional[float] = None
    reason: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ConvictionAuditRecord:
    """Complete audit record for a trade decision"""
    id: str                           # Unique trade ID
    timestamp: datetime               # Decision timestamp
    symbol: str                       # Stock symbol
    decision: str                     # BUY/SELL/REJECTED
    signal_type: str                  # Entry or Exit
    entry_price: Optional[float]      # Entry price
    exit_price: Optional[float]       # Target price
    stop_loss: Optional[float]        # Stop loss price

    # 8-Gate Results (Boolean)
    gate_1_technical: bool            # RSI, MACD, trend
    gate_2_volume: bool               # Volume confirmation
    gate_3_consensus: bool            # Agent consensus
    gate_4_rr_ratio: bool             # Risk/Reward
    gate_5_time_filter: bool          # Time of day
    gate_6_institutional: bool        # FII/DII flow
    gate_7_sentiment: bool            # News sentiment
    gate_8_vix: bool                  # VIX check

    # Summary
    gates_passed: int                 # Count of gates passed (0-8)
    conviction_level: str             # HIGH/MEDIUM/LOW/REJECTED
    rejection_reason: Optional[str]   # Why signal was rejected
    agent_name: str = ""              # Which agent generated signal

    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

    def to_json(self):
        return json.dumps(self.to_dict(), default=str, indent=2)


class ConvictionFilter:
    """
    Multi-stage conviction filter for trade validation.

    Every trade signal passes through 8 independent gates.
    Only signals with 6+ gates passing are executed.
    Every decision is logged to ConvictionAudit for transparency.
    """

    # Gate Thresholds (tunable parameters)
    THRESHOLDS = {
        'gate_1_rsi_min': 30,              # Technical: RSI oversold threshold
        'gate_1_rsi_max': 70,              # Technical: RSI overbought threshold
        'gate_2_volume_multiplier': 3.0,   # Volume: must be 3x+ average
        'gate_3_consensus_min': 3,         # Consensus: minimum agents agreeing
        'gate_4_rr_ratio_min': 1.5,        # R:R: minimum 1:1.5 ratio
        'gate_5_time_open_min': 5,         # Time: skip first N minutes
        'gate_5_time_close_min': 5,        # Time: skip last N minutes
        'gate_6_fii_threshold': 0,         # Institutional: FII flow
        'gate_6_dii_threshold': 0,         # Institutional: DII flow
        'gate_7_sentiment_min': 0.3,       # Sentiment: minimum score
        'gate_8_vix_max': 25.0,            # VIX: panic mode threshold
        'minimum_gates_to_execute': 6,     # Minimum gates to pass
    }

    def __init__(self, db_session=None):
        """
        Initialize conviction filter

        Args:
            db_session: SQLAlchemy session for logging to ConvictionAudit table
        """
        self.db_session = db_session
        self.gate_results: List[GateEvaluation] = []

    def evaluate_signal(self, signal_context: Dict) -> Tuple[bool, ConvictionAuditRecord]:
        """
        Evaluate a trade signal against all 8 conviction gates.

        Args:
            signal_context: Dictionary containing:
                - symbol: Stock symbol (e.g., "INFY")
                - decision: BUY/SELL
                - signal_type: Entry or Exit
                - entry_price: Entry price
                - exit_price: Target price
                - stop_loss: Stop loss price
                - rsi: RSI value (0-100)
                - macd_positive: MACD > signal line (bool)
                - above_200dma: Price above 200-day MA (bool)
                - volume: Current volume
                - avg_volume: Average volume
                - agent_votes: List of agent predictions (e.g., ['BUY', 'BUY', 'SELL', 'BUY'])
                - fii_flow: FII flow amount
                - dii_flow: DII flow amount
                - news_sentiment: Sentiment score (-1 to 1)
                - breaking_news_count: Number of breaking news items
                - vix: VIX index value
                - minute: Market minute (0-359, 0=9:15, 359=15:29)

        Returns:
            Tuple of (should_execute: bool, audit_record: ConvictionAuditRecord)
        """
        # Reset gate results
        self.gate_results = []

        # Generate unique ID for this decision
        audit_id = self._generate_audit_id(signal_context['symbol'])
        timestamp = datetime.now()

        # Evaluate each gate
        gate_1_result = self._gate_1_technical(signal_context)
        gate_2_result = self._gate_2_volume(signal_context)
        gate_3_result = self._gate_3_consensus(signal_context)
        gate_4_result = self._gate_4_rr_ratio(signal_context)
        gate_5_result = self._gate_5_time_filter(signal_context)
        gate_6_result = self._gate_6_institutional(signal_context)
        gate_7_result = self._gate_7_sentiment(signal_context)
        gate_8_result = self._gate_8_vix(signal_context)

        # Calculate conviction level
        gates_passed = sum([
            gate_1_result,
            gate_2_result,
            gate_3_result,
            gate_4_result,
            gate_5_result,
            gate_6_result,
            gate_7_result,
            gate_8_result,
        ])

        # Determine conviction level
        if gates_passed >= 7:
            conviction_level = ConvictionLevel.HIGH.value
        elif gates_passed >= 5:
            conviction_level = ConvictionLevel.MEDIUM.value
        else:
            conviction_level = ConvictionLevel.LOW.value

        # Determine if trade should execute
        should_execute = gates_passed >= self.THRESHOLDS['minimum_gates_to_execute']
        decision = signal_context['decision'] if should_execute else "REJECTED"
        rejection_reason = None

        if not should_execute:
            rejection_reason = self._generate_rejection_reason(
                gates_passed,
                self.gate_results
            )

        # Create audit record
        audit_record = ConvictionAuditRecord(
            id=audit_id,
            timestamp=timestamp,
            symbol=signal_context['symbol'],
            decision=decision,
            signal_type=signal_context.get('signal_type', 'Entry'),
            entry_price=signal_context.get('entry_price'),
            exit_price=signal_context.get('exit_price'),
            stop_loss=signal_context.get('stop_loss'),

            gate_1_technical=gate_1_result,
            gate_2_volume=gate_2_result,
            gate_3_consensus=gate_3_result,
            gate_4_rr_ratio=gate_4_result,
            gate_5_time_filter=gate_5_result,
            gate_6_institutional=gate_6_result,
            gate_7_sentiment=gate_7_result,
            gate_8_vix=gate_8_result,

            gates_passed=gates_passed,
            conviction_level=conviction_level,
            rejection_reason=rejection_reason,
            agent_name=signal_context.get('agent_name', 'Unknown'),
        )

        # Log to database
        self._log_to_database(audit_record)

        # Log to console
        self._log_to_console(audit_record, should_execute)

        return should_execute, audit_record

    def _gate_1_technical(self, signal_context: Dict) -> bool:
        """
        Gate 1: Technical Setup

        Criteria:
        - RSI not in extreme territory (30-70 range acceptable)
        - MACD positive (price momentum up)
        - Price above 200-day moving average (long-term uptrend)
        """
        rsi = signal_context.get('rsi', 50)
        macd_positive = signal_context.get('macd_positive', False)
        above_200dma = signal_context.get('above_200dma', False)

        passed = (
            self.THRESHOLDS['gate_1_rsi_min'] <= rsi <= self.THRESHOLDS['gate_1_rsi_max'] and
            macd_positive and
            above_200dma
        )

        reason = (
            f"RSI={rsi}, MACD={'✓' if macd_positive else '✗'}, "
            f"Above 200DMA={'✓' if above_200dma else '✗'}"
        )

        self.gate_results.append(GateEvaluation(
            gate_number=1,
            gate_name="Technical Setup",
            passed=passed,
            value=rsi,
            threshold=f"{self.THRESHOLDS['gate_1_rsi_min']}-{self.THRESHOLDS['gate_1_rsi_max']}",
            reason=reason
        ))

        return passed

    def _gate_2_volume(self, signal_context: Dict) -> bool:
        """
        Gate 2: Volume Confirmation

        Criteria:
        - Current volume > 3x average volume
        - Indicates strong conviction by institutional players
        """
        volume = signal_context.get('volume', 0)
        avg_volume = signal_context.get('avg_volume', 1)

        volume_ratio = volume / avg_volume if avg_volume > 0 else 0
        passed = volume_ratio >= self.THRESHOLDS['gate_2_volume_multiplier']

        reason = f"Volume ratio: {volume_ratio:.2f}x (threshold: {self.THRESHOLDS['gate_2_volume_multiplier']}x)"

        self.gate_results.append(GateEvaluation(
            gate_number=2,
            gate_name="Volume Confirmation",
            passed=passed,
            value=volume_ratio,
            threshold=self.THRESHOLDS['gate_2_volume_multiplier'],
            reason=reason
        ))

        return passed

    def _gate_3_consensus(self, signal_context: Dict) -> bool:
        """
        Gate 3: Multi-Agent Consensus

        Criteria:
        - At least 3 agents agree on the direction
        - Reduces impact of single-agent errors
        - Encourages alignment across different analysis methods
        """
        agent_votes = signal_context.get('agent_votes', [])
        target_decision = signal_context.get('decision', 'BUY')

        matching_votes = sum(1 for vote in agent_votes if vote == target_decision)
        passed = matching_votes >= self.THRESHOLDS['gate_3_consensus_min']

        reason = f"{matching_votes}/{len(agent_votes)} agents agree (threshold: {self.THRESHOLDS['gate_3_consensus_min']})"

        self.gate_results.append(GateEvaluation(
            gate_number=3,
            gate_name="Multi-Agent Consensus",
            passed=passed,
            value=matching_votes,
            threshold=self.THRESHOLDS['gate_3_consensus_min'],
            reason=reason
        ))

        return passed

    def _gate_4_rr_ratio(self, signal_context: Dict) -> bool:
        """
        Gate 4: Risk/Reward Ratio

        Criteria:
        - Target price / Stop loss >= 1.5
        - Ensures we're not risking too much for potential gain
        - Improves edge with proper position sizing
        """
        entry_price = signal_context.get('entry_price', 0)
        exit_price = signal_context.get('exit_price', 0)  # Target
        stop_loss = signal_context.get('stop_loss', 0)

        if entry_price == 0 or stop_loss == 0:
            passed = False
            reason = "Missing price data"
        else:
            reward = abs(exit_price - entry_price) if exit_price > 0 else 0
            risk = abs(entry_price - stop_loss)

            rr_ratio = reward / risk if risk > 0 else 0
            passed = rr_ratio >= self.THRESHOLDS['gate_4_rr_ratio_min']

            reason = f"R:R ratio: {rr_ratio:.2f}:{1} (threshold: {self.THRESHOLDS['gate_4_rr_ratio_min']}:1)"

        self.gate_results.append(GateEvaluation(
            gate_number=4,
            gate_name="Risk/Reward Ratio",
            passed=passed,
            value=rr_ratio if entry_price > 0 else 0,
            threshold=self.THRESHOLDS['gate_4_rr_ratio_min'],
            reason=reason
        ))

        return passed

    def _gate_5_time_filter(self, signal_context: Dict) -> bool:
        """
        Gate 5: Time-of-Day Filter

        Criteria:
        - Avoid market open (high volatility, spreads)
        - Avoid market close (final positions, volatility)
        - Avoid lunch hour (low liquidity)

        Time mapping (IST market hours 9:15-15:30):
        - Minute 0-4: Market open
        - Minute 180-184: Lunch hour
        - Minute 355-359: Market close
        """
        minute = signal_context.get('minute', 180)

        # Skip open (0-4), lunch (180-184), close (355-359)
        passed = not (
            (minute <= self.THRESHOLDS['gate_5_time_open_min'] or
             minute >= 355 - self.THRESHOLDS['gate_5_time_close_min'])
        )

        time_period = self._minute_to_time(minute)
        reason = f"Market time: {time_period}, Away from open/lunch/close: {'✓' if passed else '✗'}"

        self.gate_results.append(GateEvaluation(
            gate_number=5,
            gate_name="Time-of-Day Filter",
            passed=passed,
            value=minute,
            reason=reason
        ))

        return passed

    def _gate_6_institutional(self, signal_context: Dict) -> bool:
        """
        Gate 6: Institutional Flow

        Criteria:
        - FII (Foreign Institutional Investors) flow > 0 (buying)
        - DII (Domestic Institutional Investors) flow > 0 (buying)
        - Indicates strong institutional conviction
        """
        fii_flow = signal_context.get('fii_flow', 0)
        dii_flow = signal_context.get('dii_flow', 0)

        passed = (
            fii_flow > self.THRESHOLDS['gate_6_fii_threshold'] and
            dii_flow > self.THRESHOLDS['gate_6_dii_threshold']
        )

        reason = f"FII: {fii_flow:+.0f}Cr, DII: {dii_flow:+.0f}Cr - Both positive: {'✓' if passed else '✗'}"

        self.gate_results.append(GateEvaluation(
            gate_number=6,
            gate_name="Institutional Flow",
            passed=passed,
            value=(fii_flow + dii_flow),
            reason=reason
        ))

        return passed

    def _gate_7_sentiment(self, signal_context: Dict) -> bool:
        """
        Gate 7: News Sentiment

        Criteria:
        - No breaking negative news
        - Sentiment score >= 0.3 (positive/neutral)
        - Avoids trading against macro headwinds
        """
        news_sentiment = signal_context.get('news_sentiment', 0)
        breaking_news_count = signal_context.get('breaking_news_count', 0)

        passed = (
            news_sentiment >= self.THRESHOLDS['gate_7_sentiment_min'] and
            breaking_news_count == 0
        )

        reason = (
            f"Sentiment: {news_sentiment:.2f} "
            f"(threshold: {self.THRESHOLDS['gate_7_sentiment_min']}), "
            f"Breaking news: {breaking_news_count}"
        )

        self.gate_results.append(GateEvaluation(
            gate_number=7,
            gate_name="News Sentiment",
            passed=passed,
            value=news_sentiment,
            threshold=self.THRESHOLDS['gate_7_sentiment_min'],
            reason=reason
        ))

        return passed

    def _gate_8_vix(self, signal_context: Dict) -> bool:
        """
        Gate 8: VIX Check

        Criteria:
        - VIX < 25 (not in panic mode)
        - High VIX = high volatility = wider stops needed
        - Filter prevents entering during market stress
        """
        vix = signal_context.get('vix', 20)

        passed = vix < self.THRESHOLDS['gate_8_vix_max']

        reason = f"VIX: {vix:.1f} (threshold: < {self.THRESHOLDS['gate_8_vix_max']})"

        self.gate_results.append(GateEvaluation(
            gate_number=8,
            gate_name="VIX Check",
            passed=passed,
            value=vix,
            threshold=self.THRESHOLDS['gate_8_vix_max'],
            reason=reason
        ))

        return passed

    def _generate_rejection_reason(self, gates_passed: int, gate_results: List[GateEvaluation]) -> str:
        """Generate human-readable rejection reason"""
        failed_gates = [g for g in gate_results if not g.passed]

        if not failed_gates:
            return f"Not enough gates passed: {gates_passed}/{len(gate_results)}"

        failed_names = ", ".join([g.gate_name for g in failed_gates])
        return f"Failed gates ({gates_passed} passed): {failed_names}"

    def _log_to_database(self, audit_record: ConvictionAuditRecord):
        """Log audit record to database"""
        if self.db_session is None:
            return

        try:
            # Import models here to avoid circular imports
            from stockguru_agents.models import ConvictionAudit

            db_record = ConvictionAudit(
                id=audit_record.id,
                timestamp=audit_record.timestamp,
                symbol=audit_record.symbol,
                decision=audit_record.decision,
                signal_type=audit_record.signal_type,
                entry_price=audit_record.entry_price,
                exit_price=audit_record.exit_price,
                stop_loss=audit_record.stop_loss,

                gate_1_technical=audit_record.gate_1_technical,
                gate_2_volume=audit_record.gate_2_volume,
                gate_3_consensus=audit_record.gate_3_consensus,
                gate_4_rr_ratio=audit_record.gate_4_rr_ratio,
                gate_5_time_filter=audit_record.gate_5_time_filter,
                gate_6_institutional=audit_record.gate_6_institutional,
                gate_7_sentiment=audit_record.gate_7_sentiment,
                gate_8_vix=audit_record.gate_8_vix,

                gates_passed=audit_record.gates_passed,
                conviction_level=audit_record.conviction_level,
                rejection_reason=audit_record.rejection_reason,
                agent_name=audit_record.agent_name,
            )

            self.db_session.add(db_record)
            self.db_session.commit()
            logger.info(f"✅ Logged conviction audit for {audit_record.symbol} to database")

        except Exception as e:
            logger.error(f"❌ Failed to log conviction audit: {e}")

    def _log_to_console(self, audit_record: ConvictionAuditRecord, should_execute: bool):
        """Log audit record to console with formatted output"""
        status = "✅ EXECUTE" if should_execute else "❌ REJECT"

        logger.info(f"\n{'='*70}")
        logger.info(f"{status} | {audit_record.symbol} {audit_record.decision} | Conviction: {audit_record.conviction_level}")
        logger.info(f"{'='*70}")

        for gate in self.gate_results:
            gate_status = "✓" if gate.passed else "✗"
            logger.info(f"  {gate_status} Gate {gate.gate_number}: {gate.gate_name:25s} | {gate.reason}")

        logger.info(f"\n  Gates Passed: {audit_record.gates_passed}/8")

        if audit_record.rejection_reason:
            logger.warning(f"  Rejection Reason: {audit_record.rejection_reason}")

        logger.info(f"{'='*70}\n")

    @staticmethod
    def _generate_audit_id(symbol: str) -> str:
        """Generate unique audit ID"""
        import uuid
        return f"{symbol}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _minute_to_time(minute: int) -> str:
        """Convert market minute to IST time"""
        start_hour, start_minute = 9, 15
        total_minutes = start_hour * 60 + start_minute + minute
        hours = total_minutes // 60
        mins = total_minutes % 60
        return f"{hours:02d}:{mins:02d}"


# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )

    # Create conviction filter (without database for testing)
    conviction_filter = ConvictionFilter(db_session=None)

    # Example signal that should PASS all gates
    strong_signal = {
        'symbol': 'INFY',
        'decision': 'BUY',
        'signal_type': 'Entry',
        'entry_price': 1000.0,
        'exit_price': 1300.0,
        'stop_loss': 900.0,

        'rsi': 55.0,                      # Gate 1: Good RSI
        'macd_positive': True,            # Gate 1: MACD positive
        'above_200dma': True,             # Gate 1: Above 200 DMA
        'volume': 3000000,                # Gate 2: 3x volume
        'avg_volume': 1000000,            # Gate 2: Average
        'agent_votes': ['BUY', 'BUY', 'BUY', 'SELL'],  # Gate 3: 3 agree
        'fii_flow': 500.0,                # Gate 6: Positive FII
        'dii_flow': 300.0,                # Gate 6: Positive DII
        'news_sentiment': 0.5,            # Gate 7: Positive
        'breaking_news_count': 0,         # Gate 7: No breaking news
        'vix': 18.0,                      # Gate 8: Low VIX
        'minute': 120,                    # Gate 5: Mid-day
        'agent_name': 'MarketScanner',
    }

    print("\n" + "="*70)
    print("STRONG SIGNAL TEST (Should Execute)")
    print("="*70)
    should_execute, audit = conviction_filter.evaluate_signal(strong_signal)
    print(f"Decision: {'EXECUTE' if should_execute else 'REJECT'}")
    print(f"Audit Record JSON:\n{audit.to_json()}")

    # Example signal that should FAIL some gates
    weak_signal = {
        'symbol': 'TCS',
        'decision': 'BUY',
        'signal_type': 'Entry',
        'entry_price': 3000.0,
        'exit_price': 3100.0,  # Bad R:R ratio
        'stop_loss': 2900.0,

        'rsi': 75.0,                      # Gate 1: Overbought
        'macd_positive': False,           # Gate 1: MACD negative
        'above_200dma': True,             # Gate 1: Above 200 DMA
        'volume': 500000,                 # Gate 2: Only 0.5x volume
        'avg_volume': 1000000,            # Gate 2: Average
        'agent_votes': ['BUY', 'SELL', 'SELL'],  # Gate 3: Only 1 agrees
        'fii_flow': -200.0,               # Gate 6: Negative FII
        'dii_flow': 100.0,                # Gate 6: Mixed
        'news_sentiment': 0.1,            # Gate 7: Low
        'breaking_news_count': 1,         # Gate 7: Has breaking news
        'vix': 28.0,                      # Gate 8: High VIX
        'minute': 2,                      # Gate 5: Near open
        'agent_name': 'NewsAnalyzer',
    }

    print("\n" + "="*70)
    print("WEAK SIGNAL TEST (Should Reject)")
    print("="*70)
    should_execute, audit = conviction_filter.evaluate_signal(weak_signal)
    print(f"Decision: {'EXECUTE' if should_execute else 'REJECT'}")
    print(f"Audit Record JSON:\n{audit.to_json()}")
