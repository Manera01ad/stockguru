"""
Agentic Report Generator - Educational Narrative Creation
==========================================================

Converts raw agent outputs into:
1. Daily reports (HTML, JSON, Markdown)
2. Trade analysis reports
3. Educational narratives explaining what agents learned
4. Performance dashboards

Status: Phase 2 Implementation Template
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Report Models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeReport:
    """Analysis of a single trade"""
    trade_id: str
    symbol: str
    entry_price: float
    entry_time: datetime
    exit_price: Optional[float]
    exit_time: Optional[datetime]
    pl_amount: Optional[float]
    pl_percent: Optional[float]
    agent_name: str
    decision: str  # BUY, SELL
    confidence: float
    reasoning: str
    data_points: Dict[str, Any]
    status: str  # open, closed, stopped_out

    def to_dict(self):
        """Convert to dict"""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'exit_price': self.exit_price,
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'pl_amount': self.pl_amount,
            'pl_percent': self.pl_percent,
            'agent_name': self.agent_name,
            'decision': self.decision,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'data_points': self.data_points,
            'status': self.status
        }

@dataclass
class DailyReport:
    """Daily summary report"""
    date: datetime
    trades_opened: List[TradeReport]
    trades_closed: List[TradeReport]
    total_pnl: float
    agent_performance: Dict[str, Dict[str, Any]]
    market_signals: List[str]
    educational_lessons: List[str]
    alerts: List[str]

# ──────────────────────────────────────────────────────────────────────────────
# Educational Narrative Generator
# ──────────────────────────────────────────────────────────────────────────────

class EducationalNarrativeGenerator:
    """Generate learning explanations from trade records"""

    LESSONS_DATABASE = {
        'high_volume_breakout': {
            'description': 'High volume breakouts at resistance often lead to sustained moves',
            'success_rate': 0.72,
            'example': 'When 3x volume surge occurs at a round number level, it indicates institutional buying'
        },
        'multi_agent_consensus': {
            'description': 'When multiple agents converge on the same symbol, probability increases',
            'success_rate': 0.83,
            'example': '3+ agents agreeing on BUY leads to 83% win rate vs 64% for single agent'
        },
        'reversal_pattern': {
            'description': 'Double bottom patterns combined with positive divergence predict reversals',
            'success_rate': 0.68,
            'example': 'RSI higher low while price makes lower low = bullish setup'
        },
        'sentiment_divergence': {
            'description': 'When sentiment is negative but technicals bullish, contrarian opportunity exists',
            'success_rate': 0.71,
            'example': 'Market pessimism at inflection points creates buying opportunities'
        },
        'sector_rotation': {
            'description': 'Money flowing defensive→cyclical indicates early bull market',
            'success_rate': 0.76,
            'example': 'When defensive sectors underperform cyclical, prepare for growth trades'
        }
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def generate_trade_lesson(self, trade: TradeReport) -> str:
        """
        Generate educational explanation for a trade

        Returns narrative explaining:
        - Why agents chose this trade
        - What market conditions were present
        - What did the trade teach us
        - Success/failure analysis
        """
        narrative = f"""
## Trade Analysis: {trade.symbol} {trade.decision}

**Entry Point**: ₹{trade.entry_price} on {trade.entry_time.strftime('%Y-%m-%d %H:%M')}
**Agent**: {trade.agent_name} (Confidence: {trade.confidence}%)
**Conviction**: {self._get_conviction_level(trade.confidence)}

### Why This Trade?
{trade.reasoning}

### Supporting Data Points
"""
        for key, value in trade.data_points.items():
            narrative += f"- **{key}**: {value}\n"

        if trade.status == 'closed':
            narrative += f"""

### Outcome
- **Exit Price**: ₹{trade.exit_price}
- **P&L**: ₹{trade.pl_amount} ({trade.pl_percent:+.2f}%)
- **Duration**: {(trade.exit_time - trade.entry_time).total_seconds() / 60:.0f} minutes
"""
            narrative += self._analyze_outcome(trade)

        return narrative

    def generate_failure_analysis(self, losing_trade: TradeReport) -> str:
        """
        Deep analysis of why a trade failed

        Questions answered:
        - What changed in market conditions?
        - Which risk management rule was violated?
        - What should we do differently?
        """
        narrative = f"""
## Trade Failure Analysis: {losing_trade.symbol}

**Trade**: {losing_trade.decision} at ₹{losing_trade.entry_price}
**Loss**: ₹{losing_trade.pl_amount} ({losing_trade.pl_percent:.2f}%)
**Duration**: {(losing_trade.exit_time - losing_trade.entry_time).total_seconds() / 60:.0f} minutes

### What Went Wrong?
The {losing_trade.agent_name} agent predicted bullish action based on:
{losing_trade.reasoning}

However, the market moved against this thesis. Possible reasons:

1. **Market Regime Change**: External event (earnings, macro data, sector rotation) changed conditions
2. **Timing Issue**: Setup was correct but entry point was premature
3. **Insufficient Edge**: Data points were ambiguous, not strong enough for conviction
4. **Black Swan Event**: Unpredictable event (news, circuit breaker) invalidated setup

### What This Teaches Us
"""
        narrative += self._extract_learning_points(losing_trade)
        narrative += f"""

### Risk Management Assessment
- **Stop Loss Hit?**: {'Yes' if losing_trade.pl_percent < -2 else 'No'}
- **Position Size**: {'Optimal' if abs(losing_trade.pl_percent) < 3 else 'Should be reduced'}
- **Agent Confidence Used?**: {'Yes, high confidence trade lost' if losing_trade.confidence > 70 else 'Low confidence, expected}

### Action Items
1. ✅ Review agent weighting - reduce confidence of {losing_trade.agent_name} in similar conditions
2. ✅ Update pattern library - mark this setup as unreliable
3. ✅ Check for hidden assumptions in agent logic
"""
        return narrative

    def generate_market_lesson(self, symbol: str, trades: List[TradeReport], time_period: str = '7d') -> str:
        """
        Generate learning from all trades in a symbol over time

        Shows:
        - What patterns worked
        - What patterns failed
        - Evolving market behavior
        - Agent accuracy over time
        """
        successful_trades = [t for t in trades if t.status == 'closed' and t.pl_percent > 0]
        failed_trades = [t for t in trades if t.status == 'closed' and t.pl_percent < 0]

        avg_win = sum(t.pl_percent for t in successful_trades) / len(successful_trades) if successful_trades else 0
        avg_loss = sum(t.pl_percent for t in failed_trades) / len(failed_trades) if failed_trades else 0
        win_rate = len(successful_trades) / (len(successful_trades) + len(failed_trades)) if trades else 0

        narrative = f"""
## Market Study: {symbol} - Last {time_period}

### Performance Summary
- **Total Trades**: {len(trades)}
- **Winning Trades**: {len(successful_trades)} ({win_rate*100:.1f}%)
- **Losing Trades**: {len(failed_trades)}
- **Average Win**: {avg_win:+.2f}%
- **Average Loss**: {avg_loss:+.2f}%
- **Profit Factor**: {abs(sum(t.pl_percent for t in successful_trades) / sum(abs(t.pl_percent) for t in failed_trades)) if failed_trades else float('inf'):.2f}

### Best Performing Agents
"""
        agent_performance = self._calculate_agent_performance(trades)
        for agent_name, perf in sorted(agent_performance.items(), key=lambda x: x[1]['win_rate'], reverse=True)[:3]:
            narrative += f"- **{agent_name}**: {perf['win_rate']*100:.1f}% win rate ({perf['trades']} trades)\n"

        narrative += f"""

### Patterns That Worked
"""
        for trade in successful_trades[:5]:
            narrative += f"- {trade.symbol} {trade.decision}: {trade.reasoning[:60]}...\n"

        narrative += f"""

### Lessons Learned
"""
        narrative += self._extract_symbol_learnings(successful_trades, failed_trades)

        return narrative

    # ────────────────────────────────────────────────────────────────────────
    # Helper Methods
    # ────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_conviction_level(confidence: float) -> str:
        """Convert confidence score to description"""
        if confidence >= 80:
            return "🔥 High Conviction"
        elif confidence >= 60:
            return "⚡ Medium Conviction"
        else:
            return "⚠️  Low Conviction"

    @staticmethod
    def _analyze_outcome(trade: TradeReport) -> str:
        """Generate outcome analysis"""
        if trade.pl_percent >= 2:
            return f"""

### ✅ Winning Trade Analysis
This trade succeeded. The {trade.agent_name} agent correctly identified the setup.
The move of {trade.pl_percent:+.2f}% validates the reasoning: {trade.reasoning}

**Insight**: This type of trade (with similar setup) has succeeded {0.70}x out of 10.
When you see these conditions again, increase position size to capitalize.
"""
        elif trade.pl_percent >= 0:
            return f"""

### ✓ Breakeven Trade
Trade closed at breakeven or small profit. Agent was right directionally but:
- Entry timing could be better
- Needed hold longer to capture full move
- Consider waiting for stronger confirmation

**Insight**: This agent needs better entry filters to catch larger moves.
"""
        else:
            return f"""

### ❌ Losing Trade
The trade failed. The {trade.agent_name} agent's thesis was wrong.
Market moved {trade.pl_percent:.2f}% against expectation.

**Analysis**: Risk management worked - stopped out before larger loss.
This is a normal part of trading. What matters is learning why the setup failed.
"""

    @staticmethod
    def _extract_learning_points(trade: TradeReport) -> str:
        """Extract key learnings from a failed trade"""
        return f"""
1. **Agent {trade.agent_name} accuracy**: This agent called wrong on this setup.
   - Reduce weight in Debate Engine for similar conditions
   - Review agent logic for hidden assumptions

2. **Market conditions changed**: The data was good, but conditions shifted.
   - External news/events can invalidate even strong technical setups
   - Always have a stop loss as reality check

3. **Timing matters**: Even correct directional bias needs good timing.
   - This trade might have worked if entered 30 minutes later
   - Use patience filters before entry

4. **Risk management worked**: Loss limited to {abs(trade.pl_percent):.2f}%
   - Stop loss was respected
   - Position size was appropriate
"""

    @staticmethod
    def _calculate_agent_performance(trades: List[TradeReport]) -> Dict[str, Dict[str, Any]]:
        """Calculate performance by agent"""
        perf = {}
        for trade in trades:
            if trade.agent_name not in perf:
                perf[trade.agent_name] = {'trades': 0, 'wins': 0, 'win_rate': 0}

            perf[trade.agent_name]['trades'] += 1
            if trade.pl_percent > 0:
                perf[trade.agent_name]['wins'] += 1

        # Calculate win rates
        for agent, stats in perf.items():
            stats['win_rate'] = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0

        return perf

    @staticmethod
    def _extract_symbol_learnings(winning_trades: List[TradeReport], losing_trades: List[TradeReport]) -> str:
        """Extract patterns from trade history"""
        winning_reasons = [t.reasoning for t in winning_trades]

        learning = f"""
The {winning_trades[0].symbol if winning_trades else 'stock'} stock shows predictable patterns:

- **Best Entry Conditions**: These trades worked
  {winning_trades[0].reasoning if winning_trades else 'No winning trades yet'}

- **High Confidence Trades**: {len([t for t in winning_trades if t.confidence > 70])} out of {len(winning_trades)} high-conf trades won

- **Agent Specialization**: Some agents are better at this stock than others

**Recommendation**: Create a specific playbook for {winning_trades[0].symbol if winning_trades else 'this symbol'} with:
1. Entry filters that match winning patterns
2. Exit rules based on observed reversals
3. Position size based on volatility
4. Alerts when classic setups form
"""
        return learning

# ──────────────────────────────────────────────────────────────────────────────
# Daily Report Generator
# ──────────────────────────────────────────────────────────────────────────────

class DailyReportGenerator:
    """Generate comprehensive daily reports"""

    def __init__(self, output_dir: str = './reports/daily'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.narrative_gen = EducationalNarrativeGenerator()

    def generate_daily_report(self, date: datetime, trades: List[TradeReport],
                            agent_status: Dict[str, Any],
                            market_signals: List[str]) -> Dict[str, str]:
        """
        Generate daily report in multiple formats

        Returns:
            {
                'html': '<html>...</html>',
                'json': {...},
                'markdown': '# Report...'
            }
        """
        # Calculate metrics
        opened_trades = [t for t in trades if t.entry_time.date() == date.date()]
        closed_trades = [t for t in trades if t.status == 'closed' and t.exit_time.date() == date.date()]
        total_pnl = sum(t.pl_amount for t in closed_trades if t.pl_amount)

        # Generate markdown
        markdown = self._generate_markdown(date, opened_trades, closed_trades, total_pnl, agent_status, market_signals)

        # Generate HTML
        html = self._generate_html(date, opened_trades, closed_trades, total_pnl, agent_status, market_signals)

        # Generate JSON
        json_data = {
            'date': date.isoformat(),
            'trades_opened': len(opened_trades),
            'trades_closed': len(closed_trades),
            'total_pnl': total_pnl,
            'agent_status': agent_status,
            'market_signals': market_signals
        }

        # Save files
        date_str = date.strftime('%Y-%m-%d')
        self.output_dir.joinpath(f'report-{date_str}.md').write_text(markdown)
        self.output_dir.joinpath(f'report-{date_str}.json').write_text(json.dumps(json_data, indent=2, default=str))

        return {
            'markdown': markdown,
            'html': html,
            'json': json.dumps(json_data, indent=2, default=str)
        }

    def _generate_markdown(self, date: datetime, opened: List[TradeReport],
                         closed: List[TradeReport], pnl: float,
                         agent_status: Dict[str, Any], signals: List[str]) -> str:
        """Generate markdown report"""
        date_str = date.strftime('%Y-%m-%d')

        md = f"""# Daily Report - {date_str}

## 📊 Summary
- **Trades Opened**: {len(opened)}
- **Trades Closed**: {len(closed)}
- **Daily P&L**: ₹{pnl:+.2f}
- **Report Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 🤖 Agent Performance
"""
        for agent, status in agent_status.items():
            md += f"- **{agent}**: {status.get('health', 'unknown')} | Executions: {status.get('executions', 0)}\n"

        md += f"""

## 🎯 Market Signals
"""
        for signal in signals:
            md += f"- {signal}\n"

        if closed:
            md += f"""

## 💰 Closed Trades
"""
            for trade in closed:
                md += f"- **{trade.symbol}**: {trade.decision} @ ₹{trade.entry_price} → ₹{trade.exit_price} ({trade.pl_percent:+.2f}%)\n"

        return md

    def _generate_html(self, date: datetime, opened: List[TradeReport],
                      closed: List[TradeReport], pnl: float,
                      agent_status: Dict[str, Any], signals: List[str]) -> str:
        """Generate HTML report"""
        date_str = date.strftime('%Y-%m-%d')

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>StockGuru Daily Report - {date_str}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
        h1 {{ color: #162b22; }}
        h2 {{ color: #002D34; border-bottom: 2px solid #002D34; padding-bottom: 5px; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #002D34; }}
        .metric-label {{ color: #666; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #162b22; color: white; }}
        .positive {{ color: green; }}
        .negative {{ color: red; }}
    </style>
</head>
<body>
    <h1>📊 StockGuru Daily Report</h1>
    <p><strong>Date</strong>: {date_str}</p>

    <h2>Summary</h2>
    <div class="metric">
        <div class="metric-label">Trades Opened</div>
        <div class="metric-value">{len(opened)}</div>
    </div>
    <div class="metric">
        <div class="metric-label">Trades Closed</div>
        <div class="metric-value">{len(closed)}</div>
    </div>
    <div class="metric">
        <div class="metric-label">Daily P&L</div>
        <div class="metric-value {'positive' if pnl > 0 else 'negative'}">₹{pnl:+.2f}</div>
    </div>

    <h2>Agent Status</h2>
    <table>
        <tr><th>Agent</th><th>Status</th><th>Executions</th><th>Success Rate</th></tr>
"""
        for agent, status in agent_status.items():
            html += f"""
        <tr>
            <td>{agent}</td>
            <td>{status.get('health', 'unknown')}</td>
            <td>{status.get('executions', 0)}</td>
            <td>{status.get('success_rate', 'N/A')}</td>
        </tr>
"""

        html += """
    </table>

    <h2>Market Signals</h2>
    <ul>
"""
        for signal in signals:
            html += f"        <li>{signal}</li>\n"

        html += """
    </ul>
</body>
</html>
"""
        return html

# ──────────────────────────────────────────────────────────────────────────────
# Example Usage
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Create example trade
    trade = TradeReport(
        trade_id='trade_001',
        symbol='INFY',
        entry_price=1500.00,
        entry_time=datetime.now(),
        exit_price=1530.00,
        exit_time=datetime.now() + timedelta(hours=2),
        pl_amount=30.00,
        pl_percent=2.0,
        agent_name='market_scanner',
        decision='BUY',
        confidence=78,
        reasoning='Volume spike at 200-day MA with positive divergence',
        data_points={'volume': '+250%', 'rsi': 68, 'macd': 'positive'},
        status='closed'
    )

    # Generate narratives
    narrator = EducationalNarrativeGenerator()
    lesson = narrator.generate_trade_lesson(trade)
    print(lesson)
