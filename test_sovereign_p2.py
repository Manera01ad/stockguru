"""Phase 2 Sovereign modules functional test."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'stockguru_agents', 'sovereign'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'stockguru_agents'))

from sovereign import observer, synthetic_backtester, builder_agent

print("--- Phase 2 import check ---")
assert hasattr(observer,              'run'),                 "observer.run missing"
assert hasattr(synthetic_backtester,  'run'),                 "synthetic_backtester.run missing"
assert hasattr(synthetic_backtester,  '_classify_probability'), "backtester._classify_probability missing"
assert hasattr(builder_agent,         'run'),                 "builder_agent.run missing"
assert hasattr(builder_agent,         'process_callback'),    "builder_agent.process_callback missing"
assert hasattr(builder_agent,         'get_proposals_for_api'), "builder_agent.get_proposals_for_api missing"
print("[PASS] All Phase 2 module attributes verified")

# Test synthetic_backtester with no positions
ss = {
    "paper_portfolio": {"capital": 100000, "positions": {}, "stats": {}},
    "synthetic_backtest": {},
}
result = synthetic_backtester.run(ss)
assert result.get("black_swan_probability") == "LOW", "Empty portfolio should be LOW"
assert "scenarios" in result, "Missing scenarios"
assert result["portfolio_snapshot"]["positions_count"] == 0
print(f"[PASS] Backtester (no positions): prob={result['black_swan_probability']}, run_id={result['run_id']}")

# Test synthetic_backtester with mock positions
ss2 = {
    "paper_portfolio": {
        "capital": 100000,
        "positions": {
            "AIRTEL": {"entry_price": 1800.0, "qty": 10, "stop_loss": 1710.0, "sector": "Telecom"},
            "HDFC BANK": {"entry_price": 1650.0, "qty": 15, "stop_loss": 1567.5, "sector": "Banking"},
        },
        "stats": {}
    },
    "synthetic_backtest": {},
}
result2 = synthetic_backtester.run(ss2)
assert "FLASH_CRASH" in result2["scenarios"], "Missing FLASH_CRASH"
assert "BLACK_SWAN" in result2["scenarios"], "Missing BLACK_SWAN"
assert result2["portfolio_snapshot"]["positions_count"] == 2
fc_dd = result2["scenarios"]["FLASH_CRASH"]["drawdown_pct"]
bs_dd = result2["scenarios"]["BLACK_SWAN"]["drawdown_pct"]
print(f"[PASS] Backtester (2 positions): FLASH_CRASH={fc_dd}%, BLACK_SWAN={bs_dd}%, prob={result2['black_swan_probability']}")

# Test probability classification
assert synthetic_backtester._classify_probability({"A": {"drawdown_pct": -10}}) == "HIGH"
assert synthetic_backtester._classify_probability({"A": {"drawdown_pct": -5}})  == "MEDIUM"
assert synthetic_backtester._classify_probability({"A": {"drawdown_pct": -2}})  == "LOW"
print("[PASS] Probability classification: HIGH/MEDIUM/LOW logic correct")

# Test builder_agent proposals API (empty state)
proposals = builder_agent.get_proposals_for_api()
assert isinstance(proposals, list), "get_proposals_for_api must return list"
print(f"[PASS] Builder proposals API: {len(proposals)} existing proposals")

# Test observer graceful fail (NSE will be unreachable in test env)
ss3 = {"observer_output": {}}
result3 = observer.run(ss3)
assert isinstance(result3, dict), "observer.run must return dict"
assert "last_run" in result3, "observer_output missing last_run"
assert "errors" in result3, "observer_output missing errors key"
print(f"[PASS] Observer graceful run: errors={len(result3.get('errors',[]))}, last_run={result3.get('last_run')}")

# Test observer backtest file was written
backtest_path = os.path.join(os.path.dirname(__file__), "data", "backtest_scenarios.json")
assert os.path.exists(backtest_path), "backtest_scenarios.json not created"
import json
with open(backtest_path) as f:
    scenarios_hist = json.load(f)
assert isinstance(scenarios_hist, list), "backtest_scenarios.json should be a list"
assert len(scenarios_hist) >= 1, "backtest_scenarios.json should have at least 1 entry"
print(f"[PASS] backtest_scenarios.json: {len(scenarios_hist)} entries")

print()
print("=== ALL SOVEREIGN PHASE 2 TESTS PASSED ===")
