"""
Agent Orchestrator - Central Controller for StockGuru Agentic Ecosystem
========================================================================

This module provides:
1. Unified agent registration & execution
2. Error handling & fallback chains
3. Shared state management
4. Health monitoring
5. Report standardization

Status: Phase 1 Implementation Template
"""

import threading
import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Callable, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict

# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

class AgentStatus(Enum):
    """Agent health status"""
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"
    TIMEOUT = "timeout"
    DISABLED = "disabled"

class ExecutionPhase(Enum):
    """Execution stages in agent cycle"""
    PRE_MARKET = "pre_market"       # 8-9 AM IST
    MARKET_OPEN = "market_open"     # 9:15-15:30 IST
    MARKET_CLOSE = "market_close"   # 15:30-16:30 IST
    AFTER_HOURS = "after_hours"     # 16:30+ IST

@dataclass
class AgentMetrics:
    """Performance metrics for an agent"""
    name: str
    executions: int = 0
    successes: int = 0
    failures: int = 0
    avg_response_time: float = 0.0
    last_executed: Optional[datetime] = None
    last_error: Optional[str] = None
    win_rate: float = 0.0
    consecutive_failures: int = 0

    def get_status(self) -> AgentStatus:
        """Determine health status"""
        if self.consecutive_failures > 3:
            return AgentStatus.ERROR
        elif self.consecutive_failures > 1:
            return AgentStatus.DEGRADED
        elif self.last_executed and (datetime.now() - self.last_executed).seconds > 600:
            return AgentStatus.TIMEOUT
        else:
            return AgentStatus.OK

@dataclass
class AgentReportOutput:
    """Standardized agent output format"""
    timestamp: datetime
    agent_name: str
    symbol: str
    decision: str  # BUY, SELL, HOLD
    confidence: float  # 0-100
    reasoning: str
    data_points: Dict[str, Any]
    related_agents: List[str]
    educational_notes: str
    validation_status: str  # passed, needs_review, failed
    sovereign_approval: bool = False

    def to_dict(self):
        """Convert to JSON-serializable dict"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

# ──────────────────────────────────────────────────────────────────────────────
# Agent Registry
# ──────────────────────────────────────────────────────────────────────────────

class AgentRegistry:
    """Registry of all agents with dependencies & fallbacks"""

    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._logger = logging.getLogger(__name__)

    def register(self,
                 name: str,
                 execute_func: Callable,
                 required: bool = False,
                 timeout: int = 30,
                 fallbacks: Optional[List[str]] = None):
        """Register an agent with optional fallbacks"""
        self._agents[name] = {
            'func': execute_func,
            'required': required,
            'timeout': timeout,
            'fallbacks': fallbacks or [],
            'metrics': AgentMetrics(name=name),
            'enabled': True
        }
        self._logger.info(f"✅ Registered agent: {name}")

    def disable(self, name: str):
        """Disable an agent (e.g., if external API is down)"""
        if name in self._agents:
            self._agents[name]['enabled'] = False
            self._logger.warning(f"⚠️  Disabled agent: {name}")

    def enable(self, name: str):
        """Re-enable a disabled agent"""
        if name in self._agents:
            self._agents[name]['enabled'] = True
            self._logger.info(f"✅ Re-enabled agent: {name}")

    def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """Get agent config"""
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agents"""
        return list(self._agents.keys())

    def get_metrics(self, name: str) -> Optional[AgentMetrics]:
        """Get agent metrics"""
        agent = self._agents.get(name)
        return agent['metrics'] if agent else None

# ──────────────────────────────────────────────────────────────────────────────
# Shared State Manager
# ──────────────────────────────────────────────────────────────────────────────

class SharedStateManager:
    """Thread-safe in-memory state for all agents"""

    def __init__(self):
        self._lock = threading.RLock()
        self._state = {
            'agents': {},          # Agent outputs keyed by agent name
            'prices': {},          # Latest prices
            'signals': [],         # Generated buy/sell signals
            'errors': [],          # Recent agent errors
            'portfolio': {},       # Paper trading state
            'cycle_info': {},      # Current cycle metadata
            'alerts': []           # Active alerts
        }
        self._logger = logging.getLogger(__name__)
        self._websocket_callback = None

    def set_websocket_callback(self, callback: Callable):
        """Set callback for WebSocket broadcasting"""
        self._websocket_callback = callback

    def update_agent_output(self, agent_name: str, output: AgentReportOutput):
        """Store agent output (thread-safe)"""
        with self._lock:
            self._state['agents'][agent_name] = {
                'output': output.to_dict(),
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            }

        # Broadcast to WebSocket clients
        if self._websocket_callback:
            try:
                self._websocket_callback('agent_output', {
                    'agent': agent_name,
                    'output': output.to_dict()
                })
            except Exception as e:
                self._logger.error(f"WebSocket broadcast failed: {e}")

    def update_agent_error(self, agent_name: str, error: str, context: Dict):
        """Log agent error"""
        with self._lock:
            self._state['agents'][agent_name] = {
                'error': error,
                'context': context,
                'timestamp': datetime.now().isoformat(),
                'status': 'error'
            }

            # Keep error history limited
            self._state['errors'].append({
                'agent': agent_name,
                'error': error,
                'timestamp': datetime.now().isoformat()
            })
            if len(self._state['errors']) > 100:
                self._state['errors'] = self._state['errors'][-100:]

    def update_prices(self, prices: Dict[str, float]):
        """Update price cache"""
        with self._lock:
            self._state['prices'].update(prices)

    def add_signal(self, signal: Dict[str, Any]):
        """Add generated signal"""
        with self._lock:
            signal['timestamp'] = datetime.now().isoformat()
            self._state['signals'].append(signal)
            if len(self._state['signals']) > 500:
                self._state['signals'] = self._state['signals'][-500:]

    def get_state(self) -> Dict:
        """Get current state (snapshot)"""
        with self._lock:
            return json.loads(json.dumps(self._state, default=str))

    def get_agent_output(self, agent_name: str) -> Optional[Dict]:
        """Get specific agent output"""
        with self._lock:
            return self._state['agents'].get(agent_name)

    def get_recent_errors(self, limit: int = 20) -> List[Dict]:
        """Get recent errors"""
        with self._lock:
            return self._state['errors'][-limit:]

# ──────────────────────────────────────────────────────────────────────────────
# Error Recovery Pipeline
# ──────────────────────────────────────────────────────────────────────────────

class ErrorRecoveryPipeline:
    """Fallback chains for agent failures"""

    # Define fallback chains: if agent X fails, try these in order
    FALLBACK_CHAINS = {
        'news_sentiment': ['claude_intelligence', 'web_researcher'],
        'trade_signal': ['technical_analysis', 'pattern_memory'],
        'institutional_flow': ['sector_rotation', 'technical_analysis'],
        'commodity_crypto': ['web_researcher', 'claude_intelligence'],
        'technical_analysis': ['pattern_memory', 'institutional_flow'],
        'risk_manager': ['quant', 'risk_master'],
        'market_scanner': ['technical_analysis', 'pattern_memory'],
    }

    def __init__(self, registry: AgentRegistry, state: SharedStateManager, logger: logging.Logger):
        self.registry = registry
        self.state = state
        self.logger = logger

    def execute_with_recovery(self,
                             agent_name: str,
                             primary_func: Callable,
                             context: Dict[str, Any],
                             timeout: int = 30) -> Tuple[bool, Any]:
        """
        Execute agent with fallback chains

        Returns:
            (success: bool, result: Any)
        """
        # Try primary agent
        try:
            self.logger.info(f"▶️  Executing: {agent_name}")
            result = self._execute_with_timeout(primary_func, context, timeout)
            self.logger.info(f"✅ {agent_name} succeeded")
            return True, result
        except Exception as e:
            self.logger.error(f"❌ {agent_name} failed: {e}")
            self.state.update_agent_error(agent_name, str(e), {'context': context})

        # Try fallbacks
        fallbacks = self.FALLBACK_CHAINS.get(agent_name, [])
        for fallback_agent_name in fallbacks:
            try:
                fallback_agent = self.registry.get_agent(fallback_agent_name)
                if not fallback_agent or not fallback_agent['enabled']:
                    continue

                self.logger.warning(f"⚠️  Trying fallback: {fallback_agent_name}")
                result = self._execute_with_timeout(
                    fallback_agent['func'],
                    {**context, '_fallback_for': agent_name},
                    fallback_agent['timeout']
                )
                self.logger.info(f"✅ Fallback {fallback_agent_name} succeeded")
                return True, result
            except Exception as e:
                self.logger.warning(f"⚠️  Fallback {fallback_agent_name} also failed: {e}")
                continue

        # All failed
        self.logger.error(f"🔴 All agents failed: {agent_name}")
        return False, None

    @staticmethod
    def _execute_with_timeout(func: Callable, context: Dict, timeout: int) -> Any:
        """Execute function with timeout"""
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Agent execution exceeded {timeout}s")

        # Note: signal.alarm only works on Unix; for production use threading
        try:
            # Simple implementation - for production, use threading with proper cleanup
            result = func(context)
            return result
        except TimeoutError:
            raise

    def record_recovery_success(self, original_agent: str, fallback_agent: str):
        """Log successful recovery"""
        self.logger.info(f"📊 Recovery: {original_agent} → {fallback_agent}")

# ──────────────────────────────────────────────────────────────────────────────
# Central Orchestrator
# ──────────────────────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """Central controller for the agentic ecosystem"""

    def __init__(self):
        self.registry = AgentRegistry()
        self.state = SharedStateManager()
        self.recovery = ErrorRecoveryPipeline(self.registry, self.state, self._get_logger())
        self._logger = self._get_logger()
        self._cycle_lock = threading.Lock()
        self._is_running = False

    @staticmethod
    def _get_logger() -> logging.Logger:
        """Get or create logger"""
        logger = logging.getLogger('agent_orchestrator')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def register_agent(self,
                      name: str,
                      execute_func: Callable,
                      required: bool = False,
                      timeout: int = 30,
                      fallbacks: Optional[List[str]] = None):
        """Register an agent"""
        self.registry.register(name, execute_func, required, timeout, fallbacks)

    def execute_agent(self, agent_name: str, context: Dict[str, Any]) -> Tuple[bool, Any]:
        """Execute a single agent with recovery"""
        agent = self.registry.get_agent(agent_name)
        if not agent:
            self._logger.error(f"Unknown agent: {agent_name}")
            return False, None

        if not agent['enabled']:
            self._logger.warning(f"Agent disabled: {agent_name}")
            return False, None

        # Execute with recovery pipeline
        success, result = self.recovery.execute_with_recovery(
            agent_name,
            agent['func'],
            context,
            agent['timeout']
        )

        # Update metrics
        metrics = self.registry.get_metrics(agent_name)
        if metrics:
            metrics.executions += 1
            metrics.last_executed = datetime.now()
            if success:
                metrics.successes += 1
                metrics.consecutive_failures = 0
            else:
                metrics.failures += 1
                metrics.consecutive_failures += 1

        return success, result

    def run_cycle(self, context: Dict[str, Any], agent_order: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute full agent cycle in sequence

        Args:
            context: Global context for agents
            agent_order: Custom execution order (default: registered order)

        Returns:
            Results dict with all outputs and metrics
        """
        if not self._cycle_lock.acquire(blocking=False):
            self._logger.warning("⚠️  Previous cycle still running, skipping")
            return {'status': 'skipped', 'reason': 'previous_cycle_running'}

        try:
            self._logger.info("=" * 60)
            self._logger.info("🚀 Starting Agent Cycle")
            self._logger.info("=" * 60)

            cycle_start = datetime.now()
            results = {
                'status': 'running',
                'cycle_start': cycle_start.isoformat(),
                'agents': {},
                'metrics': {}
            }

            agents_to_run = agent_order or self.registry.list_agents()

            for agent_name in agents_to_run:
                success, result = self.execute_agent(agent_name, context)
                results['agents'][agent_name] = {
                    'success': success,
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                }

            # Compile metrics
            for agent_name in agents_to_run:
                metrics = self.registry.get_metrics(agent_name)
                if metrics:
                    results['metrics'][agent_name] = {
                        'executions': metrics.executions,
                        'successes': metrics.successes,
                        'failures': metrics.failures,
                        'win_rate': f"{metrics.win_rate:.1f}%" if metrics.win_rate > 0 else "N/A",
                        'status': metrics.get_status().value
                    }

            cycle_end = datetime.now()
            results['cycle_end'] = cycle_end.isoformat()
            results['duration_seconds'] = (cycle_end - cycle_start).total_seconds()
            results['status'] = 'completed'

            # Update global state
            self.state._state['cycle_info'] = results

            self._logger.info(f"✅ Cycle completed in {results['duration_seconds']:.1f}s")
            return results

        finally:
            self._cycle_lock.release()

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all agents"""
        status = {}
        for agent_name in self.registry.list_agents():
            metrics = self.registry.get_metrics(agent_name)
            if metrics:
                status[agent_name] = {
                    'health': metrics.get_status().value,
                    'executions': metrics.executions,
                    'success_rate': f"{(metrics.successes/metrics.executions*100 if metrics.executions > 0 else 0):.1f}%",
                    'last_executed': metrics.last_executed.isoformat() if metrics.last_executed else None,
                    'consecutive_failures': metrics.consecutive_failures
                }
        return status

# ──────────────────────────────────────────────────────────────────────────────
# Example Usage
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Create orchestrator
    orchestrator = AgentOrchestrator()

    # Define example agents
    def market_scanner_agent(context: Dict) -> AgentReportOutput:
        """Example: Market Scanner"""
        return AgentReportOutput(
            timestamp=datetime.now(),
            agent_name='market_scanner',
            symbol='INFY',
            decision='BUY',
            confidence=78,
            reasoning='Volume spike at resistance detected',
            data_points={'volume': '+250%', 'rsi': 68},
            related_agents=['technical_analysis'],
            educational_notes='High volume breakouts often lead to sustained trends',
            validation_status='passed'
        )

    def news_sentiment_agent(context: Dict) -> AgentReportOutput:
        """Example: News Sentiment"""
        return AgentReportOutput(
            timestamp=datetime.now(),
            agent_name='news_sentiment',
            symbol='INFY',
            decision='HOLD',
            confidence=55,
            reasoning='Mixed sentiment in recent news',
            data_points={'positive_articles': 3, 'negative_articles': 2},
            related_agents=['web_researcher'],
            educational_notes='Sentiment alone is not enough for conviction',
            validation_status='passed'
        )

    # Register agents
    orchestrator.register_agent('market_scanner', market_scanner_agent, required=True)
    orchestrator.register_agent('news_sentiment', news_sentiment_agent, fallbacks=['claude_intelligence'])

    # Run cycle
    results = orchestrator.run_cycle({'symbols': ['INFY', 'TCS', 'RELIANCE']})

    print("\n📊 Cycle Results:")
    print(json.dumps(results, indent=2, default=str))

    print("\n❤️  Health Status:")
    print(json.dumps(orchestrator.get_health_status(), indent=2, default=str))
