"""
Verify Phase 2 routes are registered in the Flask app
without starting the HTTP server.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'stockguru_agents'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'stockguru_agents', 'sovereign'))

# Mock out the startup thread calls so they don't fire
import unittest.mock as mock
import threading
original_thread_start = threading.Thread.start
threading.Thread.start = lambda self: None  # suppress background threads

# Import the Flask app
import app as stockguru_app

# Restore threads
threading.Thread.start = original_thread_start

flask_app = stockguru_app.app

# Collect all registered route rules
rules = {str(r.rule) for r in flask_app.url_map.iter_rules()}

print("=== Phase 2 Route Verification ===")

phase2_routes = [
    "/api/observer-data",
    "/api/synthetic-backtest",
    "/api/builder-proposals",
    "/api/run-builder",
    "/api/run-observer",
]

phase1_routes = [
    "/api/sovereign-status",
    "/api/debate-log",
    "/api/hitl-queue",
    "/api/post-mortem",
    "/api/risk-master-status",
    "/api/agent-memory",
    "/api/sovereign-config",
    "/api/telegram-update",
    "/api/run-sovereign",
]

all_pass = True
for route in phase1_routes + phase2_routes:
    ok = route in rules
    status = "[PASS]" if ok else "[FAIL]"
    if not ok:
        all_pass = False
    tier = "Phase 1" if route in phase1_routes else "Phase 2"
    print(f"{status} {tier}: {route}")

# Check Phase 2 sovereign modules loaded
print()
print(f"SOVEREIGN_AVAILABLE:       {stockguru_app.SOVEREIGN_AVAILABLE}")
print(f"SOVEREIGN_PHASE2_AVAILABLE:{stockguru_app.SOVEREIGN_PHASE2_AVAILABLE}")

print()
if all_pass and stockguru_app.SOVEREIGN_PHASE2_AVAILABLE:
    print("=== ALL PHASE 2 ROUTES AND MODULES VERIFIED ===")
else:
    print("=== SOME CHECKS FAILED ===")
    sys.exit(1)
