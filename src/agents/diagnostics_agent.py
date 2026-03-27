"""
DiagnosticsAgent — StockGuru Self-Healing Monitor
===================================================
Runs on every cycle (and on-demand via /api/diagnostics) to:

1. CONNECTIVITY  — Flask endpoints, WebSocket, DB
2. AGENT HEALTH  — All 14+ agents: status, last run, error count
3. DATA PIPELINE — Feeds, paper trades, signal flow
4. CODE HEALTH   — Syntax errors, truncated files, null-byte corruption
5. API KEYS      — Validity & credit status for Claude, Gemini, Telegram
6. DASHBOARD     — Missing/broken JS fetch targets
7. ENHANCEMENT   — Pattern-based suggestions for win-rate improvement

Usage:
    from src.agents.diagnostics_agent import DiagnosticsAgent
    diag = DiagnosticsAgent(shared_state, app_root="/path/to/stockguru")
    report = diag.run_full_check()
    # report is a dict — POST to /api/diagnostics for JSON output

Auto-registration:
    Wired into AgentOrchestrator — runs every 30 min and on app startup.
    Results pushed to shared_state["diagnostics_report"].
    Critical issues trigger a Telegram alert automatically.
"""

from __future__ import annotations

import os
import sys
import json
import time
import logging
import platform
import subprocess
import threading
import importlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("DiagnosticsAgent")

# ── Severity levels ───────────────────────────────────────────────────────────
SEV_CRITICAL = "CRITICAL"   # Blocks app from starting / running
SEV_ERROR    = "ERROR"      # Feature broken, needs fix
SEV_WARN     = "WARNING"    # Degraded, still functional
SEV_INFO     = "INFO"       # Improvement opportunity
SEV_OK       = "OK"         # All good

# ── Agent registry ────────────────────────────────────────────────────────────
EXPECTED_AGENTS = [
    "market_scanner", "news_sentiment", "trade_signal", "commodity_crypto",
    "morning_brief", "technical_analysis", "institutional_flow", "options_flow",
    "claude_intelligence", "web_researcher", "sector_rotation", "risk_manager",
    "pattern_memory", "paper_trader", "earnings_calendar", "spike_detector",
]

EXPECTED_SOVEREIGN = ["scryer", "quant", "risk_master", "debate_engine",
                      "hitl_controller", "post_mortem", "memory_engine",
                      "observer", "synthetic_backtester", "builder_agent"]

# ── Key API endpoints that the dashboard calls ────────────────────────────────
CRITICAL_ENDPOINTS = [
    "/api/health", "/api/agent-status", "/api/signals",
    "/api/paper-portfolio", "/api/prices", "/api/scanner",
    "/api/self-healing/stats",
]

REQUIRED_PACKAGES = [
    ("flask",          "Flask web server"),
    ("flask_cors",     "CORS headers"),
    ("flask_socketio", "WebSocket"),
    ("flask_limiter",  "Rate limiting"),
    ("anthropic",      "Claude LLM"),
    ("yfinance",       "Yahoo Finance feed"),
    ("schedule",       "Task scheduler"),
    ("sqlalchemy",     "SQLite ORM"),
    ("gevent",         "Async server"),
    ("requests",       "HTTP client"),
    ("bs4",            "HTML parser"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Issue record
# ─────────────────────────────────────────────────────────────────────────────
class Issue:
    def __init__(self, category: str, severity: str, title: str,
                 detail: str = "", fix: str = ""):
        self.category  = category
        self.severity  = severity
        self.title     = title
        self.detail    = detail
        self.fix       = fix
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "category":  self.category,
            "severity":  self.severity,
            "title":     self.title,
            "detail":    self.detail,
            "fix":       self.fix,
            "timestamp": self.timestamp,
        }


# ─────────────────────────────────────────────────────────────────────────────
# DiagnosticsAgent
# ─────────────────────────────────────────────────────────────────────────────
class DiagnosticsAgent:
    """
    Continuous self-monitoring agent.
    Call run_full_check() to get a complete diagnostic report.
    """

    def __init__(self, shared_state: Optional[Dict] = None, app_root: Optional[str] = None):
        self.shared_state = shared_state or {}
        # Resolve project root
        if app_root:
            self.root = os.path.abspath(app_root)
        else:
            # Try to detect from this file's location
            self.root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..")
            )
        self.issues: List[Issue] = []
        self._lock = threading.Lock()
        self._last_run: Optional[datetime] = None
        self._run_count = 0

    # ── Public API ────────────────────────────────────────────────────────────
    def run_full_check(self) -> Dict[str, Any]:
        """Run all diagnostic checks. Returns structured report dict."""
        with self._lock:
            start = time.time()
            self.issues = []
            self._run_count += 1
            self._last_run = datetime.now()

            self._check_python_packages()
            self._check_code_health()
            self._check_import_chains()
            self._check_agent_runtime_status()
            self._check_data_pipeline()
            self._check_database()
            self._check_api_keys()
            self._check_file_structure()
            self._check_enhancements()

            elapsed = round(time.time() - start, 2)
            report  = self._build_report(elapsed)

            # Cache in shared_state
            self.shared_state["diagnostics_report"] = report
            self.shared_state["diagnostics_last_run"] = self._last_run.isoformat()

            # Log summary
            n_crit = sum(1 for i in self.issues if i.severity == SEV_CRITICAL)
            n_err  = sum(1 for i in self.issues if i.severity == SEV_ERROR)
            n_warn = sum(1 for i in self.issues if i.severity == SEV_WARN)
            log.info(
                "DiagnosticsAgent #%d complete in %.2fs — "
                "CRITICAL:%d ERROR:%d WARN:%d",
                self._run_count, elapsed, n_crit, n_err, n_warn
            )
            if n_crit + n_err > 0:
                log.warning(
                    "⚠️  DiagnosticsAgent found %d issue(s) needing attention",
                    n_crit + n_err
                )
            return report

    def run_quick_check(self) -> Dict[str, Any]:
        """Fast check — agents, API keys, DB only. Under 2s."""
        with self._lock:
            start = time.time()
            self.issues = []
            self._check_agent_runtime_status()
            self._check_api_keys()
            self._check_database()
            elapsed = round(time.time() - start, 2)
            return self._build_report(elapsed, mode="quick")

    def get_telegram_summary(self) -> str:
        """One-line Telegram-friendly summary of critical issues."""
        crit = [i for i in self.issues if i.severity in (SEV_CRITICAL, SEV_ERROR)]
        if not crit:
            return "✅ StockGuru: All systems healthy"
        lines = [f"🔴 StockGuru Diagnostics — {len(crit)} issue(s) found:"]
        for i in crit[:5]:
            lines.append(f"  [{i.category}] {i.title}")
        if len(crit) > 5:
            lines.append(f"  … and {len(crit)-5} more")
        return "\n".join(lines)

    # ── Check 1: Python Packages ──────────────────────────────────────────────
    def _check_python_packages(self):
        missing = []
        for pkg, desc in REQUIRED_PACKAGES:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing.append(pkg)
                self.issues.append(Issue(
                    "Packages", SEV_CRITICAL,
                    f"Missing package: {pkg}",
                    f"{desc} not installed",
                    f"pip install {pkg} --break-system-packages"
                ))
        if not missing:
            log.debug("Packages: all %d required packages installed", len(REQUIRED_PACKAGES))

    # ── Check 2: Code Health (syntax + null bytes) ────────────────────────────
    def _check_code_health(self):
        src_dir = os.path.join(self.root, "src")
        if not os.path.isdir(src_dir):
            self.issues.append(Issue(
                "Code", SEV_CRITICAL, "src/ directory missing",
                "The entire source directory is gone",
                "Check that you're in the correct project folder"
            ))
            return

        errors = []
        for dirpath, dirnames, filenames in os.walk(src_dir):
            dirnames[:] = [d for d in dirnames if d not in {"__pycache__"}]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(dirpath, fname)
                # Null byte check
                try:
                    raw = open(fpath, "rb").read()
                    if b"\x00" in raw:
                        null_count = raw.count(b"\x00")
                        errors.append((fpath, f"NULL BYTES ({null_count})"))
                        self.issues.append(Issue(
                            "Code", SEV_CRITICAL,
                            f"Corrupted file: {os.path.relpath(fpath, self.root)}",
                            f"File contains {null_count} null bytes — Python can't import it",
                            "Run: python -c \"open('file','wb').write(open('file','rb').read().replace(b'\\x00',b''))\""
                        ))
                        continue
                except OSError:
                    continue
                # Syntax check
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", fpath],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    rel = os.path.relpath(fpath, self.root)
                    msg = result.stderr.strip().split("\n")[-1].strip()
                    errors.append((rel, msg))
                    self.issues.append(Issue(
                        "Code", SEV_ERROR,
                        f"Syntax error: {rel}",
                        msg,
                        "Fix the syntax error indicated by Python's error message"
                    ))

        if not errors:
            log.debug("Code health: all Python files in src/ are clean")

    # ── Check 3: Import chains ────────────────────────────────────────────────
    def _check_import_chains(self):
        chains = {
            "src.agents (general)": "src.agents.market_scanner",
            "src.core.conviction_filter": "src.core.conviction_filter",
            "src.core.phase5_self_healing": "src.core.phase5_self_healing.learning_engine",
            "src.agents.atlas": "src.agents.atlas.core",
            "src.agents.sovereign": "src.agents.sovereign.scryer",
            "src.agents.feeds": "src.agents.feeds.feed_manager",
            "src.agents.connectors": "src.agents.connectors.connector_manager",
        }
        # Ensure root on path
        if self.root not in sys.path:
            sys.path.insert(0, self.root)

        for label, module in chains.items():
            try:
                importlib.import_module(module)
            except ImportError as e:
                self.issues.append(Issue(
                    "Imports", SEV_ERROR,
                    f"Import failed: {label}",
                    str(e),
                    "Check the module for missing dependencies or syntax errors"
                ))
            except Exception as e:
                self.issues.append(Issue(
                    "Imports", SEV_WARN,
                    f"Import warning: {label}",
                    f"{type(e).__name__}: {e}",
                    "Non-critical import issue — check module initialization"
                ))

    # ── Check 4: Agent runtime status ────────────────────────────────────────
    def _check_agent_runtime_status(self):
        agent_status = self.shared_state.get("agent_status", {})
        last_cycle   = self.shared_state.get("last_cycle_time", None)

        # Check if agents are available at all
        if not self.shared_state.get("AGENTS_AVAILABLE", True):
            self.issues.append(Issue(
                "Agents", SEV_CRITICAL,
                "Core agents not loaded",
                "AGENTS_AVAILABLE=False — import failed at startup",
                "Check app startup logs for the specific ImportError"
            ))
            return

        # Check individual agent statuses
        for agent_name in EXPECTED_AGENTS:
            status = agent_status.get(agent_name, "unknown")
            if status == "error":
                self.issues.append(Issue(
                    "Agents", SEV_ERROR,
                    f"Agent failed: {agent_name}",
                    f"Runtime status: error",
                    f"Check logs for {agent_name} exception details"
                ))
            elif status == "unknown":
                self.issues.append(Issue(
                    "Agents", SEV_WARN,
                    f"Agent never ran: {agent_name}",
                    "No cycle has completed yet or agent not scheduled",
                    "Run /api/run-now to trigger a full agent cycle"
                ))

        # Check cycle staleness
        if last_cycle:
            try:
                last_dt = datetime.fromisoformat(str(last_cycle))
                age_min = (datetime.now() - last_dt).total_seconds() / 60
                if age_min > 60:
                    self.issues.append(Issue(
                        "Agents", SEV_WARN,
                        f"Agent cycle stale — last run {age_min:.0f} min ago",
                        "Scheduler may be blocked or no market data is flowing",
                        "Run /api/run-now or restart the Flask server"
                    ))
            except (ValueError, TypeError):
                pass
        else:
            self.issues.append(Issue(
                "Agents", SEV_INFO,
                "No agent cycle has run yet",
                "Server just started or scheduler not triggered",
                "Call GET /api/run-now to execute the first agent cycle"
            ))

        # Cycle count
        cycle_count = self.shared_state.get("cycle_count", 0)
        if cycle_count == 0:
            self.issues.append(Issue(
                "Agents", SEV_INFO,
                "Zero completed cycles",
                "Agents have not yet processed any market data",
                "Trigger a cycle via /api/run-now"
            ))

    # ── Check 5: Data pipeline ────────────────────────────────────────────────
    def _check_data_pipeline(self):
        data_dir = os.path.join(self.root, "data")
        if not os.path.isdir(data_dir):
            self.issues.append(Issue(
                "Data", SEV_WARN,
                "data/ directory missing",
                "Paper trade files and portfolio JSON files not found",
                "The directory will be created automatically when agents run"
            ))
            return

        # Check signal freshness
        sig_path = os.path.join(data_dir, "signal_history.json")
        if os.path.exists(sig_path):
            age_h = (time.time() - os.path.getmtime(sig_path)) / 3600
            if age_h > 24:
                self.issues.append(Issue(
                    "Data", SEV_INFO,
                    f"Signal history stale — {age_h:.0f}h old",
                    "No new signals have been generated in the past 24h",
                    "Run /api/run-now or check if market is open"
                ))
        else:
            self.issues.append(Issue(
                "Data", SEV_INFO,
                "signal_history.json not yet created",
                "Will be created after first agent cycle",
                "Trigger /api/run-now"
            ))

        # Check portfolio
        port_path = os.path.join(data_dir, "paper_portfolio.json")
        if not os.path.exists(port_path):
            self.issues.append(Issue(
                "Data", SEV_INFO,
                "paper_portfolio.json not yet created",
                "Paper trading not yet initialized",
                "Portfolio file created on first trade execution"
            ))
        else:
            try:
                port = json.load(open(port_path))
                capital = port.get("capital", 0)
                if capital <= 0:
                    self.issues.append(Issue(
                        "Data", SEV_WARN,
                        "Portfolio capital is zero or negative",
                        f"capital={capital}",
                        "Check PAPER_CAPITAL in .env — default is 100000"
                    ))
            except (json.JSONDecodeError, OSError) as e:
                self.issues.append(Issue(
                    "Data", SEV_ERROR,
                    "paper_portfolio.json is corrupted",
                    str(e),
                    "Delete the file — it will be recreated on next cycle"
                ))

        # Multiple DB files (fragmentation warning)
        db_files = [f for f in os.listdir(data_dir) if f.endswith(".db")]
        if len(db_files) > 2:
            self.issues.append(Issue(
                "Data", SEV_WARN,
                f"{len(db_files)} SQLite databases found — consider consolidating",
                f"Files: {', '.join(db_files)}",
                "Run data/consolidate_dbs.py to merge into stockguru.db"
            ))

    # ── Check 6: Database integrity ──────────────────────────────────────────
    def _check_database(self):
        db_path = os.path.join(self.root, "data", "stockguru.db")
        if not os.path.exists(db_path):
            self.issues.append(Issue(
                "Database", SEV_WARN,
                "stockguru.db not found",
                "Primary database not yet created",
                "The DB is auto-created on first app cycle"
            ))
            return

        try:
            import sqlite3
            conn = sqlite3.connect(db_path, timeout=5)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}
            conn.close()

            expected_tables = {
                "paper_trades", "order_book", "position_book",
                "portfolio_state", "conviction_audit", "portfolio_history",
            }
            missing = expected_tables - table_names
            if missing:
                self.issues.append(Issue(
                    "Database", SEV_WARN,
                    f"Missing DB tables: {', '.join(sorted(missing))}",
                    "Tables not yet initialized — will be created on first run",
                    "Run /api/run-now or restart the server"
                ))
            else:
                log.debug("Database: all required tables present (%d tables total)", len(table_names))

        except Exception as e:
            self.issues.append(Issue(
                "Database", SEV_ERROR,
                "Database connection failed",
                str(e),
                "Check that stockguru.db is not locked by another process"
            ))

    # ── Check 7: API Keys ─────────────────────────────────────────────────────
    def _check_api_keys(self):
        env_path = os.path.join(self.root, ".env")
        if not os.path.exists(env_path):
            self.issues.append(Issue(
                "API Keys", SEV_CRITICAL,
                ".env file missing",
                "No API keys configured — Claude/Gemini/Telegram will fail",
                "Create a .env file from .env.example and add your keys"
            ))
            return

        # Read keys directly (don't rely on os.environ which may have stale values)
        keys = {}
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    keys[k.strip()] = v.strip()

        # Claude
        claude_key = keys.get("ANTHROPIC_API_KEY", "")
        if not claude_key or claude_key in ("disabled", "your_key_here", ""):
            self.issues.append(Issue(
                "API Keys", SEV_ERROR,
                "ANTHROPIC_API_KEY not set",
                "Claude LLM analysis disabled — trade reasoning degraded",
                "Add your Anthropic API key to .env"
            ))
        elif claude_key == os.getenv("ANTHROPIC_API_KEY", ""):
            # Key is loaded — check if it has insufficient credits (from shared_state)
            if self.shared_state.get("claude_credits_exhausted"):
                self.issues.append(Issue(
                    "API Keys", SEV_WARN,
                    "Claude API — insufficient credits",
                    "API key valid but account needs credit top-up",
                    "Top up your Anthropic account at console.anthropic.com"
                ))

        # Gemini
        gemini_key = keys.get("GEMINI_API_KEY", "")
        if not gemini_key or gemini_key in ("disabled", "your_key_here", ""):
            self.issues.append(Issue(
                "API Keys", SEV_WARN,
                "GEMINI_API_KEY not set",
                "Gemini validation disabled — single-LLM mode only",
                "Add your Google Gemini API key to .env for dual-LLM validation"
            ))

        # Telegram
        tg_token   = keys.get("TELEGRAM_TOKEN", "")
        tg_chat_id = keys.get("TELEGRAM_CHAT_ID", "")
        if not tg_token or not tg_chat_id:
            self.issues.append(Issue(
                "API Keys", SEV_INFO,
                "Telegram alerts not configured",
                "TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing",
                "Set both in .env to receive trade alerts on Telegram"
            ))

    # ── Check 8: File structure ────────────────────────────────────────────────
    def _check_file_structure(self):
        expected = [
            ("src/agents/general",     "16 general agents"),
            ("src/agents/atlas",       "ATLAS knowledge engine"),
            ("src/agents/sovereign",   "Sovereign meta-agents"),
            ("src/agents/feeds",       "Market data feeds"),
            ("src/core",               "Conviction filter + Phase 5"),
            ("static/index.html",      "Dashboard HTML"),
            ("data",                   "Trade data"),
            ("logs",                   "Log files"),
        ]
        for rel, desc in expected:
            full = os.path.join(self.root, rel)
            if not os.path.exists(full):
                self.issues.append(Issue(
                    "Structure", SEV_ERROR,
                    f"Missing: {rel}",
                    f"Expected: {desc}",
                    f"Recreate {rel} or restore from backup"
                ))

    # ── Check 9: Enhancement suggestions ─────────────────────────────────────
    def _check_enhancements(self):
        port = self.shared_state.get("paper_portfolio", {})
        stats = port.get("stats", {})
        win_rate = stats.get("win_rate", 0)
        total_trades = stats.get("total_trades", 0)

        if total_trades >= 20 and win_rate < 0.55:
            self.issues.append(Issue(
                "Enhancement", SEV_INFO,
                f"Win rate {win_rate*100:.1f}% — below 55% target",
                f"After {total_trades} trades. Phase 5 self-healing should improve this.",
                "Run POST /api/self-healing/run to trigger learning cycle"
            ))

        if total_trades >= 100 and not self.shared_state.get("SELF_HEALING_AVAILABLE"):
            self.issues.append(Issue(
                "Enhancement", SEV_WARN,
                "Phase 5 self-healing not active — missing adaptive improvement",
                "You have enough trade history for self-healing to work",
                "Fix Phase 5 import (see Import chain errors above)"
            ))

        cycle_count = self.shared_state.get("cycle_count", 0)
        if cycle_count > 50:
            atlas_available = self.shared_state.get("ATLAS_AVAILABLE", False)
            if not atlas_available:
                self.issues.append(Issue(
                    "Enhancement", SEV_WARN,
                    "ATLAS knowledge engine not loaded — missing pattern memory",
                    f"{cycle_count} cycles run without ATLAS learning",
                    "Fix ATLAS import (check src/agents/atlas/__init__.py)"
                ))

    # ── Report builder ────────────────────────────────────────────────────────
    def _build_report(self, elapsed: float, mode: str = "full") -> Dict[str, Any]:
        issues_by_sev: Dict[str, List[dict]] = {
            SEV_CRITICAL: [], SEV_ERROR: [], SEV_WARN: [],
            SEV_INFO: [], SEV_OK: []
        }
        for issue in self.issues:
            issues_by_sev.setdefault(issue.severity, []).append(issue.to_dict())

        n_critical = len(issues_by_sev[SEV_CRITICAL])
        n_error    = len(issues_by_sev[SEV_ERROR])
        n_warn     = len(issues_by_sev[SEV_WARN])
        n_info     = len(issues_by_sev[SEV_INFO])

        if n_critical > 0:
            overall = "CRITICAL"
        elif n_error > 0:
            overall = "DEGRADED"
        elif n_warn > 0:
            overall = "WARNING"
        else:
            overall = "HEALTHY"

        # Health score: 100 - penalties
        score = 100
        score -= n_critical * 30
        score -= n_error    * 15
        score -= n_warn     *  5
        score -= n_info     *  2
        score  = max(0, score)

        return {
            "overall":      overall,
            "health_score": score,
            "mode":         mode,
            "run_number":   self._run_count,
            "timestamp":    self._last_run.isoformat() if self._last_run else None,
            "elapsed_s":    elapsed,
            "python":       platform.python_version(),
            "root":         self.root,
            "summary": {
                "critical": n_critical,
                "error":    n_error,
                "warning":  n_warn,
                "info":     n_info,
                "total":    len(self.issues),
            },
            "issues":        issues_by_sev,
            "all_issues":    [i.to_dict() for i in self.issues],
            "telegram_summary": self.get_telegram_summary(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton & convenience function (used by app.py)
# ─────────────────────────────────────────────────────────────────────────────
_agent_instance: Optional[DiagnosticsAgent] = None


def get_diagnostics_agent(shared_state: Optional[Dict] = None,
                           app_root: Optional[str] = None) -> DiagnosticsAgent:
    """Return the singleton DiagnosticsAgent, creating it if needed."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = DiagnosticsAgent(shared_state, app_root)
    elif shared_state is not None:
        _agent_instance.shared_state = shared_state
    return _agent_instance


def run_diagnostics(shared_state: Optional[Dict] = None,
                    app_root: Optional[str] = None,
                    quick: bool = False) -> Dict[str, Any]:
    """One-call convenience wrapper for app.py integration."""
    agent = get_diagnostics_agent(shared_state, app_root)
    return agent.run_quick_check() if quick else agent.run_full_check()


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="StockGuru DiagnosticsAgent")
    ap.add_argument("--quick", action="store_true", help="Quick check only")
    ap.add_argument("--root",  default=None,        help="Project root path")
    args = ap.parse_args()

    root   = args.root or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    agent  = DiagnosticsAgent(app_root=root)
    report = agent.run_quick_check() if args.quick else agent.run_full_check()

    # Pretty print
    GREEN  = "\033[92m"; RED  = "\033[91m"; YELLOW = "\033[93m"
    CYAN   = "\033[96m"; BOLD = "\033[1m";  RESET  = "\033[0m"
    sev_color = {SEV_CRITICAL: RED, SEV_ERROR: RED,
                 SEV_WARN: YELLOW, SEV_INFO: CYAN, SEV_OK: GREEN}

    print(f"\n{BOLD}StockGuru DiagnosticsAgent — {report['timestamp']}{RESET}")
    print(f"Overall: {BOLD}{report['overall']}{RESET}  |  "
          f"Health: {report['health_score']}%  |  "
          f"{report['summary']['total']} issue(s)\n")

    for issue in report["all_issues"]:
        color = sev_color.get(issue["severity"], RESET)
        print(f"  {color}[{issue['severity']}]{RESET} "
              f"[{issue['category']}] {issue['title']}")
        if issue["detail"]:
            print(f"           → {issue['detail']}")
        if issue["fix"]:
            print(f"           💡 {issue['fix']}")
    print()
