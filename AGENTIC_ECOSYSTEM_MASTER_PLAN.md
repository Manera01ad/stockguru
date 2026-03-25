# StockGuru: Unified Agentic Ecosystem Master Plan
**v1.0** | Created: 2026-03-25 | Status: Architecture & Implementation Guide

---

## 🎯 Executive Summary

You're building a **14+ Agent Intelligence Network** for retail investor education. Currently, agents run in parallel with varying reliability. This plan unifies them into a **Self-Healing, Educational Agentic Ecosystem** that:

- ✅ **Detects & fixes agent failures** automatically
- ✅ **Generates real-time agentic reports** explaining every trade decision
- ✅ **Creates educational narratives** teaching *why* trades succeed/fail
- ✅ **Handles market scenarios** (Black Swan, liquidity crisis, earnings shock)
- ✅ **Integrates with n8n** for orchestration + Python for reasoning

---

## 📊 Current State Analysis

### ✅ What's Working
```
✓ Flask API routes with 15+ endpoints
✓ 14 Core Agents (Market Scanner, News Sentiment, Trade Signals, etc.)
✓ Sovereign Trader Layer (Meta-agents: Scryer, Quant, Risk Master, Debate Engine)
✓ n8n workflow with Telegram alerts
✓ Paper trading simulation
✓ Market session awareness (IST market hours)
✓ Learning system (signal tracking, weight adjustment)
✓ Daily report generation
✓ Data persistence (JSON files)
```

### ⚠️ Issues to Fix
```
1. **Agent Isolation**: Agents don't share reasoning/learnings in real-time
2. **Report Generation**: Reports exist but lack educational depth
3. **Error Recovery**: Failed agents don't trigger fallback mechanisms
4. **WebSocket Integration**: Incomplete (Flask-SocketIO imported but may not emit consistently)
5. **Paper Trading DB**: Uses JSON, not persistent database (SQLite/PostgreSQL)
6. **Agentic Reporting**: No structured output template for agent decisions
7. **Skill System**: Mentioned in ARCHITECTURE.md but not implemented
8. **Performance Metrics**: Limited tracking of agent accuracy/win-rate
```

### 🔍 Missing Components
```
- [ ] Central Orchestration Controller (Agent State Manager)
- [ ] Unified Report Schema & Generator
- [ ] Agent Health Monitor + Recovery System
- [ ] Real-time WebSocket Publisher (Price Updates, Agent Status)
- [ ] Educational Narrative Generator (Why did this trade fail?)
- [ ] Performance Dashboard (Win-rate, Sharpe Ratio, Agent Leaderboard)
- [ ] Agentic Skill Executor (Dynamic Prompt System)
- [ ] Scenario Simulator (Black Swan Tester)
- [ ] Knowledge Base for Pattern Learning
- [ ] Multi-Agent Debate Resolution Engine (partially exists, needs polish)
```

---

## 🏗️ Unified Agentic Ecosystem Architecture

### Layer 1: Data Ingestion (External → System)
```
Market Data (Yahoo, NSE, Crypto APIs)
    ↓
n8n Orchestration Layer
    ├─ Health Checks (Server Status)
    ├─ Trigger Agent Cycle (every 15 min)
    └─ Telegram Alerts (Black Swan, Signals)
    ↓
Flask API Gateway (Port 5050)
    ├─ Rate Limiting & Auth
    ├─ Cache Management (In-Memory Shared State)
    └─ WebSocket Broadcaster
```

### Layer 2: Agent Intelligence (14 Agents + Sovereign Meta-Layer)
```
┌─────────────────────────────────────────────┐
│       Central Orchestration Controller        │
│  (New: Manages state, error recovery, deps) │
└────────────────┬────────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ↓            ↓            ↓
┌─────────┐  ┌─────────┐  ┌──────────┐
│ Agents  │  │Sovereign│  │ Learning │
│ Layer   │  │ Layer   │  │ System   │
└─────────┘  └─────────┘  └──────────┘

Agents (14):
  ├─ Market Scanner          (Technical patterns)
  ├─ News Sentiment         (NLP + market impact)
  ├─ Trade Signal Generator (Buy/Sell points)
  ├─ Commodity/Crypto       (Alternative assets)
  ├─ Morning Brief          (EOD summary)
  ├─ Technical Analysis     (Indicators)
  ├─ Institutional Flow     (FII/DII)
  ├─ Options Flow           (IV, OI walls)
  ├─ Claude Intelligence    (LLM reasoning)
  ├─ Web Researcher         (News scraping)
  ├─ Sector Rotation        (Money flows)
  ├─ Risk Manager           (Portfolio risk)
  ├─ Pattern Memory         (Historical patterns)
  ├─ Paper Trader           (Execution + P&L)
  ├─ Earnings Calendar      (Upcoming events)
  └─ Spike Detector         (Anomalies)

Sovereign Layer (Meta-Agents):
  ├─ Scryer                 (Probability weighting)
  ├─ Quant                  (Statistical validation)
  ├─ Risk Master            (VaR, Black Swan)
  ├─ Debate Engine          (Multi-model consensus)
  ├─ HITL Controller        (Human-in-Loop queue)
  ├─ Post-Mortem Engine     (Trade review & learning)
  ├─ Memory Engine          (Pattern library)
  ├─ Observer               (Market state tracking)
  ├─ Synthetic Backtester   (Scenario testing)
  └─ Builder Agent          (Portfolio construction)

Learning System:
  ├─ Signal Tracker         (Track signal accuracy)
  └─ Weight Adjuster        (Auto-tune agent weights)
```

### Layer 3: Reporting & Educational Output
```
┌──────────────────────────────────┐
│  Agentic Report Generator        │
│  (New: Unified Report Engine)    │
└──────────────┬───────────────────┘
               │
   ┌───────────┼───────────┐
   ↓           ↓           ↓
Daily Report  Trade Report Educational
 Generator     Generator    Narrative Gen
   │           │            │
   └───────────┴────────────┘
           ↓
┌─────────────────────────────┐
│ Report Output (Multi-Format)│
│ ├─ HTML Dashboard          │
│ ├─ JSON API                │
│ ├─ Markdown (Archive)      │
│ ├─ Telegram Alert          │
│ └─ PDF Export              │
└─────────────────────────────┘
```

### Layer 4: Storage & Persistence
```
In-Memory Cache         ← Real-time agent state
    ↓
File System (JSON)      ← Paper trades, signals, patterns
    ↓
SQLite Database         ← (To be added) Portfolio P&L, audit trail
    ↓
Telegram/External       ← Push notifications
```

---

## 🛠️ Orchestration Strategy: n8n vs Python

### **RECOMMENDATION: Hybrid Approach**

| Component | Tool | Reason |
|-----------|------|--------|
| **Data Fetching** | n8n | HTTP requests, caching, retry logic |
| **Trigger Scheduling** | n8n | Cron expressions, IST timezone awareness |
| **Health Checks** | n8n | Monitoring, Telegram alerts |
| **Agent Execution** | Python | Complex logic, LLM calls, state mgmt |
| **Report Generation** | Python | Educational narrative creation |
| **Error Recovery** | Python | Fallback chains, debate resolution |
| **WebSocket Broadcasting** | Python (Flask) | Real-time updates |

### Why Not 100% n8n?
- n8n excels at orchestration, not reasoning
- Complex agent debates, learning adjustments need Python
- LLM calls (Claude, Gemini) better handled in Python with SDKs
- Educational narrative generation is LLM-intensive

### Why Not 100% Python?
- n8n handles operational reliability (retries, monitoring)
- Telegram alerts are simpler in n8n
- Separates data pipeline from reasoning logic
- n8n provides visual workflow debugging

---

## 📋 Implementation Roadmap (Priority Order)

### **Phase 1: Agent Unification & Error Handling** (Week 1-2)
```python
# 1. Build Central Orchestration Controller
class AgentOrchestrator:
    """Central controller managing all 14 agents + sovereign layer"""

    def __init__(self):
        self.agents = {}           # Loaded agents
        self.state = {}            # Shared state
        self.error_log = []        # Track failures
        self.health_checks = {}    # Agent health status

    def register_agent(self, name, agent_instance, required=False, fallback=None):
        """Register agent with fallback"""
        pass

    def execute_agent(self, agent_name, context):
        """Execute with error handling & recovery"""
        # Try primary agent
        # On failure → try fallback
        # On all failure → log & alert
        pass

    def get_agent_status(self):
        """Real-time health dashboard"""
        pass

    def run_cycle(self):
        """Execute all agents in sequence with dependencies"""
        pass

# 2. Implement Error Recovery
class ErrorRecoveryPipeline:
    """Fallback chains for agent failures"""

    FALLBACK_CHAINS = {
        'news_sentiment': ['claude_intelligence', 'web_researcher'],
        'trade_signal': ['technical_analysis', 'pattern_memory'],
        'risk_manager': ['quant', 'risk_master'],
    }

    def execute_with_recovery(self, agent_name, primary_func):
        """Try primary, fallback, escalate if all fail"""
        pass
```

### **Phase 2: Unified Reporting System** (Week 2-3)
```python
# 1. Agentic Report Schema
class AgenticReportSchema:
    """Structured output for every agent decision"""

    def __init__(self):
        self.timestamp = None
        self.agent_name = str()
        self.symbol = str()
        self.decision = str()      # BUY/SELL/HOLD
        self.confidence = float()  # 0-100
        self.reasoning = str()     # WHY this decision?
        self.data_points = dict()  # Supporting data
        self.related_agents = []   # Cross-references
        self.educational_notes = str()  # What does this teach?

    def to_json(self):
        pass

    def to_narrative(self):
        """Convert to educational explanation"""
        # "Market Scanner detected 3x volume spike at ₹500 resistance.
        #  This teaches us: breakouts on volume are stronger..."
        pass

# 2. Report Generator
class AgenticReportGenerator:
    """Generate multi-format reports from agent outputs"""

    def generate_daily_report(self, date, agent_outputs):
        """HTML + JSON + Markdown"""
        pass

    def generate_trade_report(self, trade_id):
        """Analysis of specific trade: why entered, why exited"""
        pass

    def generate_educational_narrative(self, symbol, time_period):
        """Teach user what agents learned about this stock"""
        pass
```

### **Phase 3: WebSocket Real-Time Updates** (Week 3)
```python
# Fix Flask-SocketIO integration
from flask_socketio import SocketIO, emit

@socketio.on('connect')
def handle_connect():
    """User connects to real-time updates"""
    emit('response', {'status': 'Connected to live feeds'})

# Emit agent updates
def broadcast_agent_update(agent_name, symbol, signal, confidence):
    """Push agent decision to all connected clients"""
    socketio.emit('agent_update', {
        'agent': agent_name,
        'symbol': symbol,
        'signal': signal,
        'confidence': confidence,
        'timestamp': datetime.now().isoformat()
    }, broadcast=True)

# WebSocket events for real-time price & reports
socketio.on_event('subscribe_symbol', handle_subscribe)
socketio.on_event('request_agent_analysis', handle_analysis_request)
```

### **Phase 4: Paper Trading Database** (Week 4)
```python
# Migrate from JSON to SQLite
from sqlalchemy import create_engine, Column, String, Float, DateTime

class PaperTrade(Base):
    """Persistent paper trade record"""
    __tablename__ = 'paper_trades'

    id = Column(String, primary_key=True)
    symbol = Column(String, index=True)
    entry_price = Column(Float)
    entry_time = Column(DateTime)
    exit_price = Column(Float)
    exit_time = Column(DateTime)
    pl_amount = Column(Float)
    pl_percent = Column(Float)
    agent_name = Column(String)
    reasoning = Column(String)  # Why did agents choose this?

    def calculate_metrics(self):
        """Win-rate, Sharpe, max_drawdown"""
        pass

# Portfolio P&L calculation
class Portfolio:
    def get_daily_pnl(self, date):
        """P&L breakdown by agent"""
        pass

    def get_agent_leaderboard(self):
        """Which agents are winning?"""
        pass
```

### **Phase 5: Agent Skill System** (Week 5)
```python
# Dynamic prompting system
class AgentSkill:
    """Skill = {agent + specific prompt + context}"""

    def __init__(self, agent, skill_name, system_prompt, required_context):
        self.agent = agent
        self.skill_name = skill_name
        self.system_prompt = system_prompt
        self.required_context = required_context

    def execute(self, context):
        """Run agent with custom prompt"""
        pass

# Example: "News Agent, explain this 5% drop"
explain_drops_skill = AgentSkill(
    agent=news_sentiment,
    skill_name='explain_price_movement',
    system_prompt='You are a news sentiment analyst. Explain what caused the price change.',
    required_context=['symbol', 'price_change_pct', 'news_headlines']
)

# Execute on-demand from UI
response = explain_drops_skill.execute({
    'symbol': 'INFY',
    'price_change_pct': -5.2,
    'news_headlines': [...]
})
```

### **Phase 6: Educational Narrative Generation** (Week 5-6)
```python
class EducationalNarrativeGenerator:
    """Transform raw agent decisions into learning experiences"""

    def generate_trade_lesson(self, trade_record):
        """
        Trade: BUY INFY at ₹1500
        Entry Reason: Market Scanner + Institutional Flow agreed
        Exit: Sold at ₹1520 (+1.3%)

        Lesson:
        When multiple agents converge on the same symbol, probability
        of success increases. This trade teaches us about consensus
        weighting in the Debate Engine.
        """
        pass

    def generate_failure_analysis(self, losing_trade):
        """Why did this trade lose? What to learn?"""
        pass

    def generate_market_lesson(self, symbol, time_period):
        """History of all trades in a stock: patterns over time"""
        pass
```

### **Phase 7: Scenario Simulation** (Week 6-7)
```python
class BlackSwanScenarioTester:
    """Test agent behavior in extreme conditions"""

    def simulate_vix_spike(self, vix_level):
        """If VIX goes to 80, how do agents react?"""
        pass

    def simulate_liquidity_crisis(self, symbol):
        """If bid-ask spread widens 10x, are stops valid?"""
        pass

    def simulate_earnings_shock(self, symbol, shock_pct):
        """If stock gaps down 15% on earnings, recovery strategy?"""
        pass
```

---

## 🔧 Detailed Fixes Needed

### Fix 1: WebSocket Consistency
**Status**: Incomplete initialization
**Solution**:
```python
# app.py: Fix WebSocket initialization
if _SIO_AVAILABLE:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

    @socketio.on('connect')
    def handle_connect():
        print(f"Client {request.sid} connected")
        emit('connection_response', {'data': 'Connected to StockGuru Live'})

    # Schedule regular price broadcasts
    def broadcast_loop():
        while True:
            prices = fetch_all_prices()
            socketio.emit('price_update', prices, broadcast=True)
            time.sleep(5)

    # Run in background thread
    socketio_thread = threading.Thread(target=broadcast_loop, daemon=True)
    socketio_thread.start()
else:
    socketio = None
    app.logger.warning("⚠️ WebSocket disabled - install flask-socketio")
```

### Fix 2: Agent State Management
**Status**: No central state coordinator
**Solution**:
```python
class SharedState:
    """In-memory state manager for all agents"""

    def __init__(self):
        self._lock = threading.RLock()
        self._state = {
            'agents': {},          # Agent outputs
            'prices': {},          # Latest prices
            'signals': [],         # Generated signals
            'errors': [],          # Agent errors
            'portfolio': {},       # Paper trading
        }

    def update_agent_output(self, agent_name, output):
        with self._lock:
            self._state['agents'][agent_name] = {
                'output': output,
                'timestamp': datetime.now(),
                'status': 'success'
            }

    def get_agent_output(self, agent_name):
        with self._lock:
            return self._state['agents'].get(agent_name)

    def broadcast_to_websocket(self):
        """Send state changes to connected clients"""
        if socketio:
            socketio.emit('state_update', self._state, broadcast=True)

# Global instance
shared_state = SharedState()
```

### Fix 3: Error Logging & Recovery
**Status**: Minimal error tracking
**Solution**:
```python
class AgentErrorHandler:
    """Centralized error tracking & recovery"""

    def __init__(self):
        self.error_history = []
        self.recovery_actions = {}

    def log_agent_failure(self, agent_name, error, context):
        """Log with full context"""
        record = {
            'timestamp': datetime.now(),
            'agent': agent_name,
            'error': str(error),
            'context': context,
            'recovery_attempted': False
        }
        self.error_history.append(record)

        # Alert via Telegram
        send_telegram(f"⚠️ Agent {agent_name} failed: {str(error)}")

    def trigger_recovery(self, agent_name):
        """Execute recovery chain"""
        fallback_chain = FALLBACK_CHAINS.get(agent_name, [])
        for fallback_agent in fallback_chain:
            try:
                result = execute_agent(fallback_agent)
                record_recovery_success(agent_name, fallback_agent)
                return result
            except Exception as e:
                continue

        # All failed - escalate
        escalate_to_human(agent_name)
```

### Fix 4: Report Schema Consistency
**Status**: Inconsistent report formats
**Solution**:
```python
# Define standard report template
AGENT_REPORT_TEMPLATE = {
    "timestamp": "ISO8601",
    "agent_name": "string",
    "decision": "BUY|SELL|HOLD",
    "symbol": "string",
    "confidence": "0-100",
    "reasoning": {
        "primary_factors": ["list of key reasons"],
        "secondary_factors": ["supporting factors"],
        "conviction_level": "high|medium|low"
    },
    "data_points": {
        "technical": {"RSI": 65, "MACD": "positive"},
        "sentiment": {"news_tone": "positive", "score": 0.78},
        "institutional": {"FII_flow": "+1200 Cr", "trend": "buying"}
    },
    "related_signals": ["other agents that agree"],
    "educational_value": "What does this teach users?",
    "validation_status": "passed|needs_review",
    "sovereign_approval": True|False
}

def standardize_agent_output(agent_output):
    """Convert agent output to standard format"""
    return {
        **AGENT_REPORT_TEMPLATE,
        **agent_output  # Merge with defaults
    }
```

---

## 📊 Monitoring & Dashboards

### Agent Health Dashboard (Real-Time)
```
Agent Name          │ Status  │ Last Run │ Win Rate │ Avg Response Time
────────────────────┼─────────┼──────────┼──────────┼──────────────────
Market Scanner      │ ✅ OK   │ 2m ago   │  64%     │ 1.2s
News Sentiment      │ ✅ OK   │ 3m ago   │  58%     │ 2.1s
Trade Signal Gen    │ ⚠️  SLOW│ 1m ago   │  71%     │ 3.4s
Commodity/Crypto    │ ❌ ERR  │ 12m ago  │  45%     │ —
Risk Manager        │ ✅ OK   │ 1m ago   │  82%     │ 0.9s
Debate Engine       │ ✅ OK   │ 1m ago   │  75%     │ 1.8s
```

### Performance Metrics (Weekly)
```
Agent              │ Trades │ Wins │ Win % │ Avg Gain │ Max Loss
───────────────────┼────────┼──────┼───────┼──────────┼──────────
Market Scanner     │  42    │  27  │ 64%   │ +1.2%    │ -2.3%
Institutional Flow │  38    │  24  │ 63%   │ +0.9%    │ -1.8%
Technical Analysis │  51    │  38  │ 75%   │ +1.5%    │ -1.1%
Consensus Picks    │  18    │  15  │ 83%   │ +2.1%    │ -0.7%
```

---

## 🚀 Deployment Architecture

### Local Development (Docker)
```yaml
version: '3.8'
services:
  stockguru:
    build: .
    ports:
      - "5050:5050"
    environment:
      - FLASK_ENV=development
      - DATABASE_URL=sqlite:///stockguru.db
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports

  n8n:
    image: n8n
    ports:
      - "5678:5678"
    environment:
      - WEBHOOK_URL=http://stockguru:5050
```

### Production (Railway/Cloud)
```
┌─────────────────┐
│ GitHub (Source) │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Railway Deploy  │
└────────┬────────┘
         ↓
┌──────────────────────────────┐
│ Production StockGuru Server  │
│ (Flask + Gunicorn + Gevent)  │
└──────────────────────────────┘
         ↓
┌──────────────────────────────┐
│ Database (PostgreSQL)        │
│ Reports (S3/Cloud Storage)   │
│ Cache (Redis)                │
└──────────────────────────────┘
```

---

## 🎯 Success Metrics

By end of implementation:
- [ ] **Zero single-point failures**: All agents have fallbacks
- [ ] **Real-time updates**: WebSocket latency < 500ms
- [ ] **Educational output**: Every trade has explanation
- [ ] **Agent accuracy tracking**: Win-rate dashboard live
- [ ] **Autonomous error recovery**: 95% of failures self-heal
- [ ] **Scenario simulation**: Black Swan tester operational
- [ ] **Performance**: Agent cycle completes in < 2 minutes
- [ ] **Reliability**: 99.5% uptime during market hours

---

## 📚 Next Steps

1. **Start Phase 1**: Build `AgentOrchestrator` class
2. **Review existing agents**: Identify which ones need fixes
3. **Set up SQLite database**: Paper trading persistence
4. **Test WebSocket**: Verify real-time broadcasting
5. **Document agent contracts**: What inputs/outputs each agent expects
6. **Build monitoring dashboard**: Real-time agent health

---

## 📞 Questions to Answer Before Phase 1

1. **Existing issues**: Which agents are currently failing?
2. **Data location**: Is price data always available? Fallback if not?
3. **LLM integration**: Using Claude + Gemini? Which is primary?
4. **Telegram token**: Is `TELEGRAM_CHAT_ID` configured?
5. **Database**: Ready to migrate from JSON to SQLite?
6. **n8n access**: Is n8n running locally or cloud?

