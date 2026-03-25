# 🚀 PHASE 5 DEPLOYMENT CHECKLIST
**StockGuru "Self-Healing" Strategy Layer**

This checklist ensures a smooth transition to the autonomous, self-optimizing version of StockGuru. Follow these steps in order.

---

## 📂 1. Directory Structure Setup
- [x] Create directory `phase5_self_healing/`
- [x] Ensure `__init__.py` exists in all subdirectories.
- [x] Verify presence of core modules:
    - `historical_analyzer.py`
    - `gate_effectiveness.py`
    - `market_regime_detector.py`
    - `dynamic_optimizer.py`
    - `risk_tuner.py`
    - `learning_engine.py`

## 🗄️ 2. Database Migration
- [x] Update `stockguru_agents/models.py` with 5 new tables:
    - `learning_sessions`
    - `gate_performance`
    - `dynamic_thresholds`
    - `risk_optimizations`
    - `regime_history`
- [x] Run `python stockguru_agents/models.py` to initialize tables.
- [x] Create database indexes on `symbol` and `timestamp` fields.

## 🔌 3. API Integration
- [x] Add Phase 5 imports to `app.py`.
- [x] Register the 5 mission-critical endpoints:
    - `POST /api/self-healing/run`
    - `GET /api/self-healing/stats`
    - `GET /api/self-healing/recommendations`
    - `POST /api/self-healing/apply`
    - `GET /api/self-healing/history`
- [x] Update `shared_state` to support optimization caches.

## 🧠 4. Core Logic Integration
- [x] Update `conviction_filter.py` to use `active_thresholds` instead of static defaults.
- [x] Modify `paper_trader.py` to pass `shared_state` to the conviction engine.
- [x] Link Risk Manager to the `ActiveRiskParams` provided by Phase 5.

## 🧪 5. Testing & Verification
- [x] Run `tests/test_phase5_healing.py`.
- [x] Verify regime detection with mock VIX data.
- [x] Verify API responses via Postman or Curl.
- [x] Confirm that "REJECTED" signals in paper trader cite dynamic reasons.

## 🚢 6. Final Deployment
- [x] Perform a full system restart (`python app.py`).
- [x] Monitor logs for "Phase 5 Self-Healing Layer loaded" message.
- [x] Execute first "Healing Run" via the dashboard.
- [x] Commit all changes to Git.

---
**Deployment Verified By**: StockGuru AI Autopilot
**Status**: PRODUCTION READY 🚀
