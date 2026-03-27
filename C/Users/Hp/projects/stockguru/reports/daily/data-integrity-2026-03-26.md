# StockGuru Data Integrity Report
**Date:** 2026-03-26 **Time:** 10:28:57

**Status:** ⚠️ NEEDS ATTENTION — 3 CORRUPTED FILES DETECTED

---

## 📋 File Status Summary

| File | Status | Size | Notes |
|------|--------|------|-------|
| paper_portfolio.json | 🔴 **CORRUPTED** | 948 B | JSON parse error at line 38 — missing closing bracket |
| paper_trades.json | 🟡 **EMPTY** | 2 B | Placeholder only — no trade data |
| accuracy_stats.json | ✅ VALID | 384 B | Good |
| signal_history.json | 🔴 **CORRUPTED** | ? B | JSON parse error — invalid structure |
| learned_weights.json | ✅ VALID | 799 B | Good |
| sovereign_config.json | ✅ VALID | 2.2 KB | Good |
| pattern_library.json | 🟡 **EMPTY** | 3 B | No pattern data |
| post_mortem_log.json | 🟡 **EMPTY** | 3 B | No post-mortems recorded |
| builder_proposals.json | 🔴 **CORRUPTED** | 2.7 KB | JSON parse error at line 28 |

**Other Critical Files:**
| File | Status | Size | Purpose |
|------|--------|------|---------|
| agent_memory.db | ✅ HEALTHY | 36 KB | 3 tables, 1 row in memories |
| stockguru.db | ✅ HEALTHY | 100 KB | 11 tables (new), 0 rows total |
| All_Trades_Consolidated.csv | ✅ VALID | 6.3 KB | Historical trade data |

---

## 📊 Paper Portfolio Snapshot

**⚠️ UNABLE TO PARSE** — File is corrupted

Partial data before corruption:
```
- Capital: ₹500,000.00
- Available Cash: ₹222,333.94
- Invested: ₹277,130.34
- Unrealized PnL: -₹138.74
- Open Positions: MUTHOOT (20 shares @ ₹3,321.86)
```

**Issue**: File truncated or malformed JSON at position 948 bytes. Last entry (MUTHOOT position) is incomplete.

---

## 🗄️ SQLite Databases

### agent_memory.db ✅ **HEALTHY**
- **Size:** 36 KB
- **Tables:** 3 (memories, config_history, sqlite_sequence)
- **Status:** Operational
- **Row count:** memories=1, config_history=0

### stockguru.db ✅ **HEALTHY**
- **Size:** 100 KB
- **Tables:** 11 (trade_book, order_book, position_book, portfolio_state, conviction_audit, portfolio_history, learning_sessions, gate_performance, dynamic_thresholds, risk_optimizations, regime_history)
- **Status:** Operational but empty (new database)
- **Row count:** All tables empty (0 total rows)

---

## 🔴 CRITICAL ISSUES

### 1. **paper_portfolio.json — CORRUPTED**
- **Impact:** HIGH — Blocks paper trading engine
- **Error:** JSON decode error: line 38, missing/invalid closing bracket
- **File size:** 948 bytes (incomplete)
- **Cause:** File write interrupted or manual edit error
- **Fix:** Restore from backup or reconstruct from CSV (All_Trades_Consolidated.csv)

### 2. **signal_history.json — CORRUPTED**
- **Impact:** MEDIUM — Loses historical signal data
- **Error:** JSON parse error at line 2
- **Cause:** Empty or invalid structure
- **Fix:** Reinitialize if not critical for backtesting

### 3. **builder_proposals.json — CORRUPTED**
- **Impact:** MEDIUM — Loses proposal history
- **Error:** JSON parse error at line 28
- **Cause:** Incomplete write or truncation
- **Fix:** Restore from backup or reinitialize

---

## 🟡 WARNINGS

### Empty Files (Data Loss / Initialization)
- **paper_trades.json** — Should contain trade execution log
- **pattern_library.json** — Should contain learned patterns
- **post_mortem_log.json** — Should contain trade reviews

**Recommendation:** These files should be populated by trading runs. If no trades have been executed, this is expected.

---

## ✅ What's Working

- **SQLite databases:** Both databases are healthy and accessible
- **Valid JSON configs:** sovereign_config.json, learned_weights.json, accuracy_stats.json
- **CSV archive:** All_Trades_Consolidated.csv contains historical trades
- **Supporting databases:** Multiple backup databases (atlas_brain.db, atlas_knowledge.db) available
- **Cache directory:** Exists and appears operational

---

## 🛠️ Recommended Actions

### IMMEDIATE (Priority 1)
1. **Restore paper_portfolio.json** from recent backup
   - Check if backup exists in `.git` history
   - Alternative: Reconstruct from `All_Trades_Consolidated.csv`
2. **Fix signal_history.json**
   - Clear and reinitialize, or restore from backup
3. **Restore builder_proposals.json**
   - Restore from git history or reinitialize

### SHORT-TERM (Priority 2)
4. Implement automated backup for all JSON files
5. Add JSON validation to all write operations
6. Set up data corruption detection alerts

### MONITORING
7. Monitor paper_portfolio.json for future corruption
8. Populate empty trade files from next trading run
9. Run integrity check daily (this script)

---

## 📝 Session Info
- **Check Time:** 2026-03-26 10:28:57
- **Project Path:** `/sessions/sleepy-tender-bell/mnt/stockguru`
- **Next Check:** Automatic (scheduled daily)

---

**Next Action:** Restore corrupted JSON files from git backup before resuming paper trading.
