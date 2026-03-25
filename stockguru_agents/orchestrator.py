"""
StockGuru Agent Orchestrator — Central Controller (Phase 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal:   Manages 14+ agents + sovereign layer with error recovery.
Status: Implementation of Phase 1 of the Agentic Ecosystem Plan.

Key Features:
- Centralized execution of agent cycles
- Error recovery & fallback chains
- Agent health monitoring (shared_state["agent_status"])
- Standardized logging to agent_reasoning_log
"""

import logging
import time
import os
import requests
from datetime import datetime

log = logging.getLogger("orchestrator")

class ErrorRecoveryPipeline:
    """Fallback chains for agent failures."""
    FALLBACK_CHAINS = {
        'claude_intelligence': ['technical_analysis', 'news_sentiment'],
        'news_sentiment': ['web_researcher'],
        'trade_signal': ['technical_analysis', 'pattern_memory'],
        'risk_manager': ['quant', 'risk_master'],
        'market_scanner': ['commodity_crypto'], # If scanner fails, macro might still work
        'paper_trader': ['morning_brief'], # Ensure report still goes out
    }

    @staticmethod
    def get_fallbacks(agent_name):
        return ErrorRecoveryPipeline.FALLBACK_CHAINS.get(agent_name, [])


class AgentOrchestrator:
    """Central controller managing all 14 agents + sovereign layer."""

    def __init__(self, shared_state):
        self.shared_state = shared_state
        self.agents = {}           # Loaded agent modules
        self.error_log = []        # Track failures
        self.health_results = {}   # Agent health status

    def register_agent(self, name, agent_module, required=False):
        """Register an agent module with its logic."""
        self.agents[name] = {
            "module": agent_module,
            "required": required,
            "status": "ready"
        }

    def _log_cycle(self, msg, level="info"):
        """Internal helper for cycle logging."""
        entry = {"t": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level}
        if "agent_cycle_log" not in self.shared_state:
            self.shared_state["agent_cycle_log"] = []
        self.shared_state["agent_cycle_log"].append(entry)
        if len(self.shared_state["agent_cycle_log"]) > 200:
            self.shared_state["agent_cycle_log"] = self.shared_state["agent_cycle_log"][-200:]

    def _update_status(self, agent_name, status):
        """Update agent status for UI/monitoring."""
        if "agent_status" not in self.shared_state:
            self.shared_state["agent_status"] = {}
        self.shared_state["agent_status"][agent_name] = status
        icon = "▶" if status == "running" else ("✅" if status == "done" else "❌")
        self._log_cycle(f"{icon} {agent_name.upper()} — {status}", level=status)

    def execute_agent(self, name, *args, **kwargs):
        """Execute agent with error handling & recovery."""
        if name not in self.agents:
            log.warning("Agent %s not registered", name)
            return False

        agent_info = self.agents[name]
        module = agent_info["module"]

        self._update_status(name, "running")
        start_time = time.time()

        try:
            # Most agents expect `shared_state` as first arg
            # Some might have different call signatures (like paper_trader)
            # We assume a standard .run(shared_state) unless otherwise noted
            if hasattr(module, "run"):
                module.run(self.shared_state, *args, **kwargs)
            else:
                log.error("Agent %s has no .run() method", name)
                raise AttributeError(f"Agent {name} has no .run() method")
            
            self._update_status(name, "done")
            duration = time.time() - start_time
            log.info("Agent %s completed in %.2fs", name, duration)
            return True

        except Exception as e:
            self._update_status(name, "failed")
            self.error_log.append({
                "timestamp": datetime.now().isoformat(),
                "agent": name,
                "error": str(e)
            })
            log.error("Agent %s failed: %s", name, e)

            # --- Trigger Recovery Pipeline ---
            fallbacks = ErrorRecoveryPipeline.get_fallbacks(name)
            if fallbacks:
                log.info("Triggering recovery for %s: checking fallbacks %s", name, fallbacks)
                for fallback_name in fallbacks:
                    if fallback_name in self.agents:
                        log.info("Attempting fallback agent: %s", fallback_name)
                        if self.execute_agent(fallback_name):
                            log.info("Recovery via %s successful", fallback_name)
                            return True
            
            # Escalate if required
            if agent_info.get("required"):
                self._send_telegram_alert(f"🚨 CRITICAL AGENT FAILURE: {name}\nError: {str(e)[:100]}")

            return False

    def _send_telegram_alert(self, message):
        """Send emergency alerts to Telegram."""
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=8)
        except Exception:
            pass

    def get_agent_status(self):
        """Get summary status of all registered agents."""
        return self.shared_state.get("agent_status", {})
