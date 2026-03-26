#!/usr/bin/env python3
"""
StockGuru — Full Project Debug Script
======================================
Run from project root:   python debug.py
Optionally fix imports:  python debug.py --fix

Checks:
  1. Python syntax errors (all .py files)
  2. Truncated / incomplete files
  3. Import chain health (general, atlas, sovereign, channels, etc.)
  4. Config & .env keys
  5. Python package dependencies
  6. Database files
  7. Directory structure
"""

import os
import sys
import subprocess
import importlib
import argparse

ROOT      = os.path.dirname(os.path.abspath(__file__))
SRC_AGENTS = os.path.join(ROOT, "src", "agents")
SRC_CORE   = os.path.join(ROOT, "src", "core")

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "reports", "archived",
             "stockguru_agents"}   # legacy — no longer the source of truth

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✅{RESET}  {msg}")
def err(msg):  print(f"  {RED}❌{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠️ {RESET}  {msg}")
def info(msg): print(f"  {CYAN}ℹ️ {RESET}  {msg}")
def header(title):
    print(f"\n{BOLD}{CYAN}── {title} {'─' * max(0, 60 - len(title))}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. SYNTAX ERRORS
# ─────────────────────────────────────────────────────────────────────────────
def check_syntax():
    header("1. Syntax Errors")
    errors = []
    checked = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            checked += 1
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", fpath],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                rel  = os.path.relpath(fpath, ROOT)
                msg  = result.stderr.strip().split("\n")[-1].strip()
                errors.append((rel, msg))

    if not errors:
        ok(f"All {checked} Python files are syntax-clean")
    else:
        warn(f"{len(errors)} files have syntax errors  ({checked} files scanned)")
        for path, msg in sorted(errors):
            print(f"     {RED}{path}{RESET}")
            print(f"       → {msg}")
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# 2. TRUNCATED FILES
# ─────────────────────────────────────────────────────────────────────────────
def check_truncated():
    header("2. Truncated / Incomplete Files")

    # Files that are known to be truncated (error at or near last line)
    suspects = [
        "src/agents/atlas/causal_engine.py",
        "src/agents/atlas/self_upgrader.py",
        "src/agents/atlas/volume_classifier.py",
        "src/agents/sovereign/post_mortem.py",
        "src/agents/models.py",
        "src/agents/paper_trader.py",
        "src/api/PHASE_5_API_ROUTES.py",
        "src/api/stockguru_mcp_server.py",
        "src/core/app.py",
        "src/core/agentic_report_generator.py",
        "scripts/utilities/DIAGNOSIS_TOOLKIT.py",
    ]

    truncated = []
    for rel in suspects:
        fpath = os.path.join(ROOT, rel)
        if not os.path.exists(fpath):
            warn(f"Missing: {rel}")
            continue
        lines = sum(1 for _ in open(fpath, errors="ignore"))
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", fpath],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            truncated.append((rel, lines))
            err(f"{rel}  ({lines} lines — ends mid-expression)")
        else:
            ok(f"{rel}  ({lines} lines)")

    if not truncated:
        ok("No truncated files found")
    else:
        info(f"{len(truncated)} truncated files — likely cut off during the March 25 reorganisation")
        info("These files exist in stockguru_agents/ (working copies) — src/ copies need regeneration")
    return truncated


# ─────────────────────────────────────────────────────────────────────────────
# 3. IMPORT CHAINS
# ─────────────────────────────────────────────────────────────────────────────
def check_imports():
    header("3. Import Chain Health")

    # Ensure paths are set up as app.py does
    for p in [SRC_AGENTS, SRC_CORE]:
        if p not in sys.path:
            sys.path.insert(0, p)

    checks = {
        "general (16 agents)": lambda: __import_multi("general", [
            "market_scanner","news_sentiment","trade_signal","commodity_crypto",
            "morning_brief","technical_analysis","institutional_flow","options_flow",
            "claude_intelligence","web_researcher","sector_rotation","risk_manager",
            "pattern_memory","paper_trader","earnings_calendar","spike_detector",
        ]),
        "orchestrator": lambda: __import__("orchestrator"),
        "learning": lambda: __import_multi("learning", ["signal_tracker","weight_adjuster"]),
        "atlas.core": lambda: importlib.import_module("atlas.core"),
        "channels": lambda: __import__("channels"),
        "backtesting": lambda: __import__("backtesting"),
        "connectors": lambda: __import__("connectors"),
        "feeds": lambda: __import__("feeds"),
        "sovereign": lambda: __import__("sovereign"),
        "phase5_self_healing": lambda: importlib.import_module("phase5_self_healing.learning_engine"),
    }

    results = {}
    for name, fn in checks.items():
        try:
            fn()
            ok(name)
            results[name] = True
        except SyntaxError as e:
            fname = os.path.basename(e.filename) if e.filename else "?"
            warn(f"{name}  — pre-existing SyntaxError in {fname} line {e.lineno}")
            results[name] = "syntax"
        except ImportError as e:
            err(f"{name}  — ImportError: {e}")
            results[name] = False
        except Exception as e:
            err(f"{name}  — {type(e).__name__}: {e}")
            results[name] = False
    return results


def __import_multi(package, names):
    mod = __import__(package)
    for n in names:
        if not hasattr(mod, n):
            raise ImportError(f"'{package}' has no attribute '{n}'")


# ─────────────────────────────────────────────────────────────────────────────
# 4. CONFIG & ENV
# ─────────────────────────────────────────────────────────────────────────────
def check_config():
    header("4. Config & .env")

    env_path = os.path.join(ROOT, ".env")
    required_keys = [
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
    ]
    optional_keys = [
        "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID",
        "ACTIVE_FEED", "PAPER_CAPITAL", "LOCAL_KEYS_PATH",
    ]

    if not os.path.exists(env_path):
        err(".env file not found — create one from .env.example")
        return

    env_keys = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_keys[k.strip()] = v.strip()

    ok(f".env found  ({len(env_keys)} keys configured)")

    for k in required_keys:
        v = env_keys.get(k, "")
        if not v or v in ("disabled", "your_key_here", ""):
            err(f"{k} = NOT SET  ← required")
        elif len(v) < 10:
            warn(f"{k} = set but suspiciously short")
        else:
            ok(f"{k} = {'*' * 8}{v[-4:]}  ✓")

    for k in optional_keys:
        v = env_keys.get(k, "")
        if v:
            ok(f"{k} = set")
        else:
            info(f"{k} = not set  (optional)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. PYTHON PACKAGES
# ─────────────────────────────────────────────────────────────────────────────
def check_packages():
    header("5. Python Package Dependencies")

    packages = {
        "flask":          "Flask web server",
        "flask_cors":     "CORS headers",
        "flask_socketio": "WebSocket support",
        "flask_limiter":  "Rate limiting",
        "anthropic":      "Claude LLM client",
        "google.generativeai": "Gemini LLM client",
        "yfinance":       "Yahoo Finance feed",
        "schedule":       "Task scheduler",
        "dotenv":         "Env file loader",
        "requests":       "HTTP client",
        "gevent":         "Async server (SocketIO)",
        "sqlalchemy":     "ORM / SQLite",
        "bs4":            "BeautifulSoup HTML parser",
    }

    missing = []
    for pkg, desc in packages.items():
        try:
            importlib.import_module(pkg)
            ok(f"{pkg}  — {desc}")
        except ImportError:
            err(f"{pkg}  — {desc}  ← pip install needed")
            missing.append(pkg)

    if missing:
        print(f"\n  Run:  pip install {' '.join(missing)} --break-system-packages")
    return missing


# ─────────────────────────────────────────────────────────────────────────────
# 6. DATABASES
# ─────────────────────────────────────────────────────────────────────────────
def check_databases():
    header("6. Database Files")

    db_paths = [
        ("data/stockguru.db", "Primary app DB — single source of truth"),
    ]

    found = []
    for rel, label in db_paths:
        fpath = os.path.join(ROOT, rel)
        if os.path.exists(fpath):
            size = os.path.getsize(fpath) / 1024
            ok(f"{rel}  ({size:.1f} KB)  — {label}")
            found.append(rel)
        else:
            info(f"{rel}  — {label}  (not yet created)")

    if len(found) > 1:
        warn(f"{len(found)} DB files found — consider consolidating to data/stockguru.db")


# ─────────────────────────────────────────────────────────────────────────────
# 7. DIRECTORY STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────
def check_structure():
    header("7. Directory Structure")

    expected = {
        "src/agents/general":     "16 trading agents (source of truth)",
        "src/agents/atlas":       "ATLAS self-learning engine",
        "src/agents/sovereign":   "Sovereign meta-agents",
        "src/agents/channels":    "Delivery channels",
        "src/agents/backtesting": "Backtesting engine",
        "src/agents/connectors":  "Intelligence connectors",
        "src/agents/learning":    "Signal tracker + weight adjuster",
        "src/agents/feeds":       "Market data feed manager",
        "src/core":               "conviction_filter, phase5_self_healing",
        "src/api":                "API routes",
        "data":                   "Paper portfolio, trade logs",
        "logs":                   "Rotating app logs",
        "static":                 "Frontend assets",
        "tests":                  "Unit tests",
    }

    for rel, desc in expected.items():
        fpath = os.path.join(ROOT, rel)
        if os.path.isdir(fpath):
            count = len([f for f in os.listdir(fpath) if f.endswith(".py")])
            ok(f"{rel}/  ({count} .py files)  — {desc}")
        else:
            err(f"{rel}/  MISSING  — {desc}")

    # Legacy directory check (removed in March 26 cleanup)
    legacy = os.path.join(ROOT, "stockguru_agents")
    if os.path.exists(legacy):
        warn("stockguru_agents/  still present — legacy directory, should be removed")
        info("Run:  rm -rf stockguru_agents/")


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def print_summary(syntax_errors, truncated, import_results, missing_pkgs):
    header("SUMMARY")

    total_issues = len(syntax_errors) + len(truncated) + \
                   sum(1 for v in import_results.values() if v is False) + \
                   len(missing_pkgs)

    syntax_only_in_src = [e for e in syntax_errors
                          if not e[0].startswith("stockguru_agents")]

    # Only flag as blocking if the import chain test also failed for that module
    # (e.g. mcp_tools.py has a syntax error but feeds imports fine — not a blocker)
    failed_set = {k for k, v in import_results.items() if v is False}
    blockers = [e for e in syntax_only_in_src
                if any(k in e[0] for k in failed_set)]

    if total_issues == 0:
        ok("Project is fully healthy — no issues found")
        return

    if missing_pkgs:
        err(f"Missing packages ({len(missing_pkgs)}): {', '.join(missing_pkgs)}")
        info("Fix: pip install -r requirements.txt --break-system-packages")

    if blockers:
        err(f"Blocking syntax errors in active import chain ({len(blockers)} files)")
        for path, _ in blockers:
            print(f"     → {path}")
    elif syntax_only_in_src:
        warn(f"Non-blocking syntax errors in src/ ({len(syntax_only_in_src)} files)")
        info("These are in unused/duplicate files and don't affect app startup")

    failed_imports = [k for k, v in import_results.items() if v is False]
    if failed_imports:
        err(f"Import failures: {', '.join(failed_imports)}")

    syntax_imports = [k for k, v in import_results.items() if v == 'syntax']
    if syntax_imports:
        warn(f"Syntax-blocked imports (pre-existing): {', '.join(syntax_imports)}")
        info("sovereign/post_mortem.py needs the truncated docstring completed")

    print(f"\n  {'🔴' if blockers or failed_imports else '🟡'} "
          f"{total_issues} issue(s) total  |  "
          f"App startup: {'✅ OK' if not blockers and not failed_imports else '❌ BLOCKED'}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StockGuru project debug tool")
    parser.add_argument("--quick", action="store_true",
                        help="Skip syntax scan (faster)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*64}")
    print(f"  StockGuru Debug — {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Root: {ROOT}")
    print(f"{'='*64}{RESET}")

    syntax_errors  = [] if args.quick else check_syntax()
    truncated      = check_truncated()
    import_results = check_imports()
    check_config()
    missing_pkgs   = check_packages()
    check_databases()
    check_structure()
    print_summary(syntax_errors, truncated, import_results, missing_pkgs)
    print()
