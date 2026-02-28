"""Quick functional test for Phase 1 Sovereign modules."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'stockguru_agents', 'sovereign'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'stockguru_agents'))

from sovereign import scryer, quant, risk_master, memory_engine

# Minimal shared_state
ss = {
    'news_results': [],
    'stock_sentiment_map': {},
    'technical_data': {},
    '_price_cache': {},
    'index_prices': {'INDIA VIX': {'price': 14.5}},
    'paper_portfolio': {'capital': 100000, 'positions': {}, 'stats': {'daily_pnl_pct': 0}},
    'actionable_signals': [],
    'risk_reviewed_signals': [],
    'trade_signals': [],
    'claude_analysis': {},
    'accuracy_stats': {}
}

# Test Scryer
out = scryer.run(ss)
assert 'scryer_market_read' in out, "Scryer missing scryer_market_read"
print(f"[PASS] Scryer  | market_read={out['scryer_market_read']} | news_analyzed={out['news_analyzed']}")

# Test Quant
out = quant.run(ss)
assert 'auto_candidates' in out, "Quant missing auto_candidates"
print(f"[PASS] Quant   | auto={out['auto_candidates']} | hitl={out['hitl_candidates']} | debate={out['debate_candidates']}")

# Test Risk Master
out = risk_master.run(ss, None)
assert 'hard_veto_active' in out, "RiskMaster missing hard_veto_active"
print(f"[PASS] RiskMstr| hard_veto={out['hard_veto_active']} | vix={out['vix_level']} | losses={out['consecutive_losses']}")

# Test Memory Engine
mem = memory_engine.get_all_recent(5)
assert isinstance(mem, list), "Memory Engine get_all_recent must return list"
print(f"[PASS] MemEng  | records_in_db={len(mem)}")

# Test store + retrieve lesson
ok = memory_engine.store_lesson(
    trade_id='TEST_001', ticker='TESTCO', sector='TEST',
    outcome='FAILURE', metadata={'rsi': 70}, reflexion='Test lesson.', root_cause='TIMING'
)
assert ok, "store_lesson returned False"
lessons = memory_engine.get_recent_lessons('TESTCO', limit=1)
assert len(lessons) == 1 and lessons[0]['reflexion'] == 'Test lesson.', "get_recent_lessons failed"
print(f"[PASS] MemStore| store+retrieve OK: {lessons[0]['outcome']} / {lessons[0]['root_cause']}")

print()
print("=== ALL SOVEREIGN PHASE 1 TESTS PASSED ===")
