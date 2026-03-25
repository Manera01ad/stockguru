# 🔌 PHASE 5 API REFERENCE
**StockGuru Autonomous Strategy Adaptation Interface**

## 🌐 Endpoints Overview
The Phase 5 'Self-Healing' system adds 5 mission-critical endpoints to the existing StockGuru API.

---

### 1. `POST /api/self-healing/run`
**Description**: Triggers a complete self-healing cycle, analyzing historical trades and the current market regime.

- **Parameters**: 
    - `days` (int, default=90): Number of days back to analyze.
- **Returns**: 
    - `status`: "success" or "error"
    - `analysis_period`: Start/End dates and trades analyzed.
    - `market_regime`: Detected regime (TRENDING/RANGING/VOLATILE).
    - `threshold_recommendations`: List of suggested gate changes.
    - `risk_optimization`: Calculated position sizing and ATR multiples.

---

### 2. `GET /api/self-healing/stats`
**Description**: Retrieves the statistical health of the conviction gates.

- **Returns**: 
    - `gate_effectiveness`: Individual win-rate contribution for all 8 gates (0.0 to 1.0).
    - `predictive_power`: Combined confidence score for the current gate set.

---

### 3. `GET /api/self-healing/recommendations`
**Description**: Shows the currently pending (unapplied) strategy optimizations.

- **Returns**: 
    - `thresholds`: Dictionary of proposed gate values (e.g., `gate_2_volume_multiplier: 4.5`).
    - `risk`: Proposed risk changes (e.g., `position_size_percent: 2.0`).

---

### 4. `POST /api/self-healing/apply`
**Description**: Commits and activates the recommended strategy changes across the live scanner and paper trader.

- **Returns**: 
    - `status`: "SUCCESS"
    - `applied`: Full dictionary of the new parameters now in effect.

---

### 5. `GET /api/self-healing/history`
**Description**: Provides an audit trail of every past optimization session.

- **Returns**: 
    - `history`: List of past learning sessions (timestamps, regimes, improvements).
    - `count`: Total sessions run.

---
**Authentication**: Standard project API token required (if enabled).  
**Headers**: `Content-Type: application/json`
