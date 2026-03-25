# Phase 2.5 Integration Guide - How to Wire Conviction Filter into Paper Trader

**Purpose**: Step-by-step instructions for integrating `conviction_filter.py` with existing `paper_trader.py` and database

**Duration**: 30-60 minutes (with testing)

---

## ✅ Prerequisites

Before starting integration, verify:

- [ ] `conviction_filter.py` is in project root
- [ ] `paper_trader.py` exists and works
- [ ] SQLite database initialized with ConvictionAudit table (from Phase 2)
- [ ] `stockguru_agents/models.py` has ConvictionAudit class
- [ ] Dependencies installed: `sqlalchemy`, `sqlite3`

**Verify setup**:
```bash
# Check files exist
ls conviction_filter.py paper_trader.py stockguru_agents/models.py

# Test database
python -c "from stockguru_agents.models import ConvictionAudit; print('✅ Models OK')"
```

---

## 📋 Integration Checklist

### Phase 1: Modify Paper Trader (15 min)

- [ ] Add conviction_filter import
- [ ] Create conviction_filter instance with db_session
- [ ] Add build_signal_context() helper method
- [ ] Add conviction check to execute_trade() method
- [ ] Update return types to include audit_record

### Phase 2: Wire Agent Orchestrator (10 min)

- [ ] Import and initialize ConvictionFilter
- [ ] Update AgentOrchestrator.execute_trade() to pass signal_context
- [ ] Handle rejection responses gracefully

### Phase 3: Test Integration (15 min)

- [ ] Unit test strong signal (should execute)
- [ ] Unit test weak signal (should reject)
- [ ] Verify database logging
- [ ] Check console output

### Phase 4: Production Deployment (10 min)

- [ ] Enable ConvictionFilter in main app.py
- [ ] Monitor rejection rate (should be 20-30%)
- [ ] Verify win-rate improvement
- [ ] Update status in CLAUDE.md

---

## 🔧 INTEGRATION CODE

### **Step 1: Modify paper_trader.py**

Add this to the top of your `paper_trader.py`:

```python
# =============================================================================
# PHASE 2.5 ADDITION: Conviction Filter Integration
# =============================================================================

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from conviction_filter import ConvictionFilter

logger = logging.getLogger(__name__)

class PaperTradingEngine:
    """
    Enhanced paper trading engine with conviction-based filtering.

    Every trade signal is validated through 8-gate conviction filter
    before execution. Only high-conviction trades are executed.
    """

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.conviction_filter = ConvictionFilter(db_session=db_session)
        self.trades = []
        self.portfolio_state = {}

    def execute_trade_with_conviction(self, signal_context: dict) -> dict:
        """
        Execute trade only if it passes conviction filter.

        Args:
            signal_context: Dict with:
                - symbol: Stock symbol
                - decision: BUY/SELL
                - signal_type: Entry or Exit
                - entry_price: Entry price
                - exit_price: Target price
                - stop_loss: Stop loss price
                - rsi: RSI value
                - macd_positive: Bool
                - above_200dma: Bool
                - volume: Current volume
                - avg_volume: Average volume
                - agent_votes: List of agent votes
                - fii_flow: FII flow amount
                - dii_flow: DII flow amount
                - news_sentiment: Sentiment score
                - breaking_news_count: Count
                - vix: VIX index value
                - minute: Market minute (0-359)
                - agent_name: Which agent generated signal

        Returns:
            {
                'status': 'EXECUTED' | 'REJECTED' | 'ERROR',
                'trade_id': str,
                'reason': str,
                'audit_record': ConvictionAuditRecord,
                'conviction_level': str
            }
        """

        logger.info(f"Processing signal: {signal_context['symbol']} {signal_context['decision']}")

        try:
            # Step 1: Evaluate signal through conviction filter
            should_execute, audit_record = self.conviction_filter.evaluate_signal(signal_context)

            # Step 2: Check conviction result
            if not should_execute:
                logger.info(
                    f"❌ Signal rejected: {audit_record.rejection_reason} "
                    f"({audit_record.gates_passed}/8 gates passed)"
                )

                return {
                    'status': 'REJECTED',
                    'symbol': signal_context['symbol'],
                    'reason': audit_record.rejection_reason,
                    'gates_passed': audit_record.gates_passed,
                    'conviction_level': audit_record.conviction_level,
                    'audit_record': audit_record,
                }

            # Step 3: Execute trade (high conviction)
            logger.info(
                f"✅ Signal ACCEPTED: {audit_record.conviction_level} conviction "
                f"({audit_record.gates_passed}/8 gates passed)"
            )

            trade_result = self._execute_trade_atomic(
                symbol=signal_context['symbol'],
                direction=signal_context['decision'],
                entry_price=signal_context['entry_price'],
                exit_price=signal_context['exit_price'],
                stop_loss=signal_context['stop_loss'],
                reasoning=f"Conviction: {audit_record.conviction_level}, Gates: {audit_record.gates_passed}/8",
                agent_name=signal_context.get('agent_name', 'Unknown'),
            )

            return {
                'status': 'EXECUTED',
                'trade_id': trade_result.get('trade_id'),
                'symbol': signal_context['symbol'],
                'conviction_level': audit_record.conviction_level,
                'gates_passed': audit_record.gates_passed,
                'audit_record': audit_record,
                'trade_result': trade_result,
            }

        except Exception as e:
            logger.error(f"❌ Error processing signal: {e}", exc_info=True)
            return {
                'status': 'ERROR',
                'symbol': signal_context['symbol'],
                'reason': str(e),
                'error': e,
            }

    def _execute_trade_atomic(self, symbol: str, direction: str, entry_price: float,
                              exit_price: float, stop_loss: float, reasoning: str,
                              agent_name: str) -> dict:
        """
        Actually execute the trade with atomic database transaction.

        This is your existing execute_trade() method, now called only after
        conviction filter passes.
        """

        # YOUR EXISTING TRADE EXECUTION CODE GOES HERE
        # This should:
        # 1. Create PaperTrade record with all details
        # 2. Update portfolio state
        # 3. Store in database atomically
        # 4. Return trade result

        from stockguru_agents.models import PaperTrade

        try:
            trade = PaperTrade(
                id=self._generate_trade_id(symbol),
                timestamp=datetime.now(),
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                stop_loss=stop_loss,
                pl_amount=0.0,  # Will be updated on exit
                agent_name=agent_name,
                reasoning=reasoning,
                status='OPEN',
            )

            self.db_session.add(trade)
            self.db_session.commit()

            logger.info(f"✅ Trade executed: {symbol} {direction} @ {entry_price}")

            return {
                'trade_id': trade.id,
                'status': 'OPEN',
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
            }

        except Exception as e:
            self.db_session.rollback()
            logger.error(f"❌ Trade execution failed: {e}")
            raise

    @staticmethod
    def _generate_trade_id(symbol: str) -> str:
        """Generate unique trade ID"""
        import uuid
        return f"TRADE_{symbol}_{uuid.uuid4().hex[:8]}"


# =============================================================================
# END PHASE 2.5 ADDITION
# =============================================================================
```

---

### **Step 2: Modify Agent Orchestrator**

Update your `agent_orchestrator.py` to use the new execution method:

```python
# In AgentOrchestrator class, update execute_signal() method:

def execute_signal(self, agent_name: str, signal_context: dict):
    """
    Execute trade signal with conviction filtering.

    Args:
        agent_name: Name of agent generating signal
        signal_context: Trade signal with all context

    Returns:
        Execution result (executed, rejected, or error)
    """

    logger.info(f"Agent '{agent_name}' generated signal: {signal_context['symbol']}")

    # Add agent name to context
    signal_context['agent_name'] = agent_name

    # Execute with conviction filter
    result = self.paper_trader.execute_trade_with_conviction(signal_context)

    # Log result
    if result['status'] == 'EXECUTED':
        logger.info(f"✅ Signal executed: {result['symbol']} ({result['conviction_level']} conviction)")

        # Update shared state
        self.shared_state.record_executed_trade(
            signal_context['symbol'],
            signal_context['decision'],
            result['gates_passed'],
            result['conviction_level']
        )

    elif result['status'] == 'REJECTED':
        logger.info(f"❌ Signal rejected: {result['reason']}")

        # Update shared state
        self.shared_state.record_rejected_signal(
            signal_context['symbol'],
            result['reason'],
            result['gates_passed']
        )

    return result
```

---

### **Step 3: Add Helper Method**

Add this helper to build signal context from agent output:

```python
@staticmethod
def build_signal_context_from_agent(agent_output: dict) -> dict:
    """
    Convert agent output to conviction filter signal context.

    Maps agent-specific fields to standardized signal context format.
    """

    return {
        'symbol': agent_output.get('symbol'),
        'decision': agent_output.get('decision', 'BUY'),
        'signal_type': agent_output.get('type', 'Entry'),
        'entry_price': agent_output.get('entry_price'),
        'exit_price': agent_output.get('target_price'),
        'stop_loss': agent_output.get('stop_loss'),

        # Technical
        'rsi': agent_output.get('rsi', 50),
        'macd_positive': agent_output.get('macd_signal', False),
        'above_200dma': agent_output.get('above_200dma', False),

        # Volume
        'volume': agent_output.get('volume', 0),
        'avg_volume': agent_output.get('avg_volume', 1),

        # Consensus
        'agent_votes': agent_output.get('agent_consensus', []),

        # Institutional
        'fii_flow': agent_output.get('fii_flow', 0),
        'dii_flow': agent_output.get('dii_flow', 0),

        # Sentiment
        'news_sentiment': agent_output.get('sentiment_score', 0),
        'breaking_news_count': agent_output.get('breaking_news_count', 0),

        # Market
        'vix': agent_output.get('vix', 20),
        'minute': agent_output.get('market_minute', 180),
    }
```

---

### **Step 4: Initialize in Main App**

Update `app.py` to initialize conviction filter:

```python
# In Flask app initialization

from conviction_filter import ConvictionFilter
from paper_trader import PaperTradingEngine

def init_trading_system(app, db_session):
    """Initialize trading system with conviction filter"""

    # Create paper trader with conviction filtering
    paper_trader = PaperTradingEngine(db_session=db_session)

    # Verify conviction filter working
    try:
        test_filter = ConvictionFilter(db_session=db_session)
        logger.info("✅ Conviction filter initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize conviction filter: {e}")
        raise

    return paper_trader

# In app startup:
paper_trader = init_trading_system(app, db_session)
```

---

## 🧪 TESTING

### Test 1: Strong Signal (Should Execute)

```python
# Test that strong signals pass all gates

from conviction_filter import ConvictionFilter

conviction_filter = ConvictionFilter(db_session=None)

strong_signal = {
    'symbol': 'INFY',
    'decision': 'BUY',
    'signal_type': 'Entry',
    'entry_price': 1000.0,
    'exit_price': 1300.0,
    'stop_loss': 900.0,
    'rsi': 55.0,
    'macd_positive': True,
    'above_200dma': True,
    'volume': 3000000,
    'avg_volume': 1000000,
    'agent_votes': ['BUY', 'BUY', 'BUY', 'SELL'],
    'fii_flow': 500.0,
    'dii_flow': 300.0,
    'news_sentiment': 0.5,
    'breaking_news_count': 0,
    'vix': 18.0,
    'minute': 120,
    'agent_name': 'TestAgent',
}

should_execute, audit_record = conviction_filter.evaluate_signal(strong_signal)

assert should_execute == True, "Strong signal should execute"
assert audit_record.gates_passed >= 6, "Should pass minimum gates"
assert audit_record.conviction_level in ['HIGH', 'MEDIUM'], "Should be HIGH or MEDIUM"

print("✅ Test 1 passed: Strong signal executes")
```

### Test 2: Weak Signal (Should Reject)

```python
weak_signal = {
    'symbol': 'TCS',
    'decision': 'BUY',
    'signal_type': 'Entry',
    'entry_price': 3000.0,
    'exit_price': 3100.0,  # Bad R:R
    'stop_loss': 2900.0,
    'rsi': 75.0,           # Overbought
    'macd_positive': False,
    'above_200dma': True,
    'volume': 500000,      # Low volume
    'avg_volume': 1000000,
    'agent_votes': ['BUY', 'SELL', 'SELL'],  # Low consensus
    'fii_flow': -200.0,    # Negative flow
    'dii_flow': 100.0,
    'news_sentiment': 0.1,
    'breaking_news_count': 1,  # Breaking news
    'vix': 28.0,           # High VIX
    'minute': 2,           # Near open
    'agent_name': 'TestAgent',
}

should_execute, audit_record = conviction_filter.evaluate_signal(weak_signal)

assert should_execute == False, "Weak signal should be rejected"
assert audit_record.gates_passed < 6, "Should fail minimum gates"
assert audit_record.conviction_level == 'LOW', "Should be LOW conviction"
assert audit_record.rejection_reason is not None, "Should have rejection reason"

print("✅ Test 2 passed: Weak signal rejected")
```

### Test 3: Database Logging

```python
# Verify records are written to database

from stockguru_agents.models import ConvictionAudit

# Check that audit records exist
audit_count = db_session.query(ConvictionAudit).count()
assert audit_count > 0, "Should have audit records in database"

# Check record details
latest_audit = db_session.query(ConvictionAudit).order_by(
    ConvictionAudit.timestamp.desc()
).first()

assert latest_audit is not None, "Should have at least one audit record"
assert latest_audit.gates_passed <= 8, "Gates passed should be 0-8"
assert latest_audit.conviction_level in ['HIGH', 'MEDIUM', 'LOW'], "Valid conviction level"

print(f"✅ Test 3 passed: {audit_count} audit records logged to database")
```

### Run All Tests

```bash
# Create test file
cat > test_conviction_integration.py << 'EOF'
import logging
logging.basicConfig(level=logging.INFO)

# Test 1
print("\n" + "="*70)
print("TEST 1: Strong signal execution")
print("="*70)
exec(open('test_strong_signal.py').read())

# Test 2
print("\n" + "="*70)
print("TEST 2: Weak signal rejection")
print("="*70)
exec(open('test_weak_signal.py').read())

# Test 3
print("\n" + "="*70)
print("TEST 3: Database logging")
print("="*70)
exec(open('test_database_logging.py').read())

print("\n" + "="*70)
print("✅ ALL TESTS PASSED")
print("="*70)
EOF

python test_conviction_integration.py
```

---

## 📊 MONITORING

### Check Conviction Statistics

```sql
-- View conviction distribution
SELECT
    conviction_level,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM conviction_audit), 1) as percentage
FROM conviction_audit
GROUP BY conviction_level
ORDER BY count DESC;

-- Expected:
-- HIGH    | 45 |  30%
-- MEDIUM  | 78 |  52%
-- LOW     | 27 |  18%
-- REJECTED| 0  |  0%   (these should have decision='REJECTED')
```

### Check Win-Rate by Conviction Level

```sql
-- Win-rate by conviction level
SELECT
    ca.conviction_level,
    COUNT(*) as trade_count,
    ROUND(AVG(CASE WHEN pt.pl_amount > 0 THEN 1 ELSE 0 END) * 100, 1) as win_rate_percent
FROM conviction_audit ca
LEFT JOIN paper_trades pt ON ca.symbol = pt.symbol
WHERE ca.decision != 'REJECTED'
GROUP BY ca.conviction_level
ORDER BY win_rate_percent DESC;

-- Expected:
-- HIGH    | 30 | 78%  (high conviction = good trades)
-- MEDIUM  | 60 | 62%  (medium = decent trades)
-- LOW     | 20 | 42%  (low = worst trades, mostly filtered out)
```

### Most Effective Gates

```sql
-- Which gates reject most signals?
SELECT
    'Gate 1: Technical' as gate_name,
    COUNT(*) as rejection_count
FROM conviction_audit
WHERE gate_1_technical = 0 AND decision = 'REJECTED'

UNION ALL

SELECT 'Gate 2: Volume', COUNT(*)
FROM conviction_audit WHERE gate_2_volume = 0 AND decision = 'REJECTED'

-- ... repeat for all 8 gates
ORDER BY rejection_count DESC;

-- Most effective gates at top (reject most low-quality signals)
```

---

## 🚀 DEPLOYMENT CHECKLIST

Before going live with conviction filter:

- [ ] `conviction_filter.py` tested independently
- [ ] `PaperTradingEngine` integrated with conviction check
- [ ] Strong signal test passes (executes)
- [ ] Weak signal test passes (rejects)
- [ ] Database logging verified
- [ ] Rejection rate monitored (should be 20-30%)
- [ ] Win-rate improvement verified (should increase 10-20%)
- [ ] Console output shows conviction levels
- [ ] No exceptions in logs
- [ ] CLAUDE.md updated with Phase 2.5 completion

---

## ⚠️ TROUBLESHOOTING

### Issue: "ModuleNotFoundError: No module named 'conviction_filter'"

**Fix**: Ensure `conviction_filter.py` is in the same directory as `paper_trader.py` or in Python path

```python
import sys
sys.path.insert(0, '/path/to/stockguru')
from conviction_filter import ConvictionFilter
```

### Issue: "ConvictionAudit table doesn't exist"

**Fix**: Run database migrations from Phase 2

```python
from stockguru_agents.models import Base, engine
Base.metadata.create_all(engine)
```

### Issue: "Gates always pass (win-rate not improving)"

**Fix**: Thresholds may be too loose. Tighten them:

```python
# In conviction_filter.py, increase strictness:
ConvictionFilter.THRESHOLDS['minimum_gates_to_execute'] = 7  # was 6
ConvictionFilter.THRESHOLDS['gate_2_volume_multiplier'] = 4.0  # was 3.0
```

### Issue: "Too many rejections (no trades executing)"

**Fix**: Thresholds too tight. Relax them:

```python
ConvictionFilter.THRESHOLDS['minimum_gates_to_execute'] = 5  # was 6
ConvictionFilter.THRESHOLDS['gate_4_rr_ratio_min'] = 1.2  # was 1.5
```

---

## 📞 SUPPORT

If integration issues arise:

1. Check conviction_filter.py test output: `python conviction_filter.py`
2. Review database schema: ConvictionAudit table must exist
3. Check logs for gate evaluation details
4. Compare your signal_context to example signals
5. Verify agent_votes format matches expected list

---

**Status**: Ready for Integration
**Estimated Time**: 30-60 minutes
**Difficulty**: Medium (mostly copy-paste with small modifications)

**Next**: Run tests, monitor metrics, proceed to Phase 3 WebSocket enrichment.
