"""Verify app.py can import all sovereign modules correctly (mirrors app.py startup)."""
import sys, os
_sovereign_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockguru_agents", "sovereign")
if _sovereign_dir not in sys.path:
    sys.path.insert(0, _sovereign_dir)
_sovereign_parent = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockguru_agents")
if _sovereign_parent not in sys.path:
    sys.path.insert(0, _sovereign_parent)

try:
    from sovereign import scryer, quant, risk_master, debate_engine, hitl_controller, post_mortem, memory_engine
    SOVEREIGN_AVAILABLE = True
except ImportError as _se:
    SOVEREIGN_AVAILABLE = False
    print(f"[FAIL] ImportError: {_se}")

print(f"SOVEREIGN_AVAILABLE = {SOVEREIGN_AVAILABLE}")
assert SOVEREIGN_AVAILABLE, "Sovereign import FAILED"

# Verify all 9 route handler dependencies
assert hasattr(scryer,          'run'),                     "scryer.run missing"
assert hasattr(quant,           'run'),                     "quant.run missing"
assert hasattr(risk_master,     'run'),                     "risk_master.run missing"
assert hasattr(debate_engine,   'run_debate'),              "debate_engine.run_debate missing"
assert hasattr(hitl_controller, 'dispatch_hitl_request'),   "hitl_controller.dispatch_hitl_request missing"
assert hasattr(hitl_controller, 'process_telegram_update'), "hitl_controller.process_telegram_update missing"
assert hasattr(hitl_controller, 'check_queue_expiry'),      "hitl_controller.check_queue_expiry missing"
assert hasattr(hitl_controller, 'get_queue_for_api'),       "hitl_controller.get_queue_for_api missing"
assert hasattr(post_mortem,     'run'),                     "post_mortem.run missing"
assert hasattr(memory_engine,   'get_all_recent'),          "memory_engine.get_all_recent missing"
assert hasattr(memory_engine,   'get_config_history'),      "memory_engine.get_config_history missing"

print("[PASS] All route dependencies verified")
print("[PASS] app.py startup simulation: SUCCESS")
