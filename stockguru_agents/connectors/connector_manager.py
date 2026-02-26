"""
Connector Manager — orchestrates all intelligence connectors
════════════════════════════════════════════════════════════
Mirrors channels/channel_manager.py pattern.
Analysis connectors (pattern_detector, agent_router, risk_analytics) are always
"enabled" — they need no API keys. Alpaca execution requires credentials.
"""

import os
import logging
from datetime import datetime

log = logging.getLogger("ConnectorManager")


class ConnectorManager:
    """
    Central registry for all intelligence connectors.
    Connectors with no env_keys are always enabled.
    Connectors with env_keys follow the same connected/partial/not_configured logic.
    """

    CONNECTOR_DEFS = {
        "alpaca_execution": {
            "name":        "Alpaca Execution Bridge",
            "description": "Route paper trades through Alpaca paper account for real fills",
            "env_keys":    ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"],
            "type":        "execution",
            "icon":        "🦙",
        },
        "pattern_detector": {
            "name":        "Chart Pattern Detector",
            "description": "Detects flags, double tops/bottoms, H&S from OHLCV data",
            "env_keys":    [],
            "type":        "analysis",
            "icon":        "📐",
        },
        "agent_router": {
            "name":        "Agent Router",
            "description": "Confidence-based routing — skips LLM when Tier 1 signals are weak",
            "env_keys":    [],
            "type":        "orchestration",
            "icon":        "🔀",
        },
        "risk_analytics": {
            "name":        "Risk Analytics",
            "description": "Portfolio VaR (95/99%), correlation matrix, portfolio beta",
            "env_keys":    [],
            "type":        "risk",
            "icon":        "📊",
        },
    }

    def __init__(self):
        self._status_cache = {}

    def get_all_statuses(self) -> dict:
        """Return status of every connector."""
        statuses = {}
        for connector_id, defn in self.CONNECTOR_DEFS.items():
            if not defn["env_keys"]:
                # No keys required → always enabled
                status = "enabled"
                keys_present = 0
                keys_missing = []
            else:
                keys_present = [k for k in defn["env_keys"] if os.getenv(k)]
                keys_missing = [k for k in defn["env_keys"] if not os.getenv(k)]
                if len(keys_present) == len(defn["env_keys"]):
                    status = "connected"
                elif keys_present:
                    status = "partial"
                else:
                    status = "not_configured"
                keys_present = len(keys_present)

            statuses[connector_id] = {
                **defn,
                "status":        status,
                "keys_present":  keys_present,
                "keys_required": len(defn["env_keys"]),
                "missing_keys":  keys_missing,
                "checked_at":    datetime.now().strftime("%H:%M:%S"),
            }
        self._status_cache = statuses
        return statuses

    def is_enabled(self, connector_id: str) -> bool:
        """True if connector is enabled (no keys needed) or connected (keys present)."""
        if not self._status_cache:
            self.get_all_statuses()
        s = self._status_cache.get(connector_id, {}).get("status", "")
        return s in ("enabled", "connected")

    def get_alpaca_execution(self):
        """Return AlpacaExecutionConnector, or None if not configured."""
        if not self.is_enabled("alpaca_execution"):
            return None
        try:
            from .alpaca_execution import AlpacaExecutionConnector
            return AlpacaExecutionConnector()
        except Exception as e:
            log.warning(f"AlpacaExecution init failed: {e}")
            return None

    def get_pattern_detector(self):
        """Return PatternDetector (always available)."""
        try:
            from .pattern_detector import PatternDetector
            return PatternDetector()
        except Exception as e:
            log.warning(f"PatternDetector init failed: {e}")
            return None

    def get_agent_router(self):
        """Return AgentRouter (always available)."""
        try:
            from .agent_router import AgentRouter
            return AgentRouter()
        except Exception as e:
            log.warning(f"AgentRouter init failed: {e}")
            return None

    def get_risk_analytics(self):
        """Return RiskAnalytics (always available)."""
        try:
            from .risk_analytics import RiskAnalytics
            return RiskAnalytics()
        except Exception as e:
            log.warning(f"RiskAnalytics init failed: {e}")
            return None

    def summary(self) -> str:
        statuses = self.get_all_statuses()
        active = sum(1 for s in statuses.values() if s["status"] in ("enabled", "connected"))
        return f"{active}/{len(statuses)} connectors active"
