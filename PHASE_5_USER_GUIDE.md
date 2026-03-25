# 📖 PHASE 5: USER GUIDE - "The Self-Healing Intelligence"
**StockGuru Autonomous Evolution Engine v5.0**

## 🌟 Overview
Phase 5 introduces the "Self-Healing" layer, transforming StockGuru from a fixed-parameter scanner into a dynamic, learning organism. The platform now analyzes its own performance history to identify which of the 8 conviction gates are working and which need adjustment.

## 🛠️ Core Components

### 1. The Learning Loop
The system runs a deep-learning analysis every 24 hours (or on command) that:
1.  **Audits**: Scrutinizes the last 90 days of paper trades.
2.  **Correlates**: Matches trade outcomes with the specific gate values at the time of entry.
3.  **Detects Mode**: Classifies the current "Market Regime" (Trending, Ranging, Volatile).
4.  **Recommends**: Generates new threshold values for all 8 conviction gates.

### 2. Market Regime Detection
The bot adapts its behavior based on the current regime:
- **TRENDING**: Higher conviction needed for volume; wider targets; trailing stops active.
- **RANGING**: Momentum filters loosened; tighter targets (mean reversion); support/resistance gates prioritized.
- **VOLATILE**: Extremely strict conviction filters (+25% requirement); reduced position sizing (conservative mode).

## 🚦 How to Use the Dashboard
1.  **Trigger Analysis**: Click the "Run Healing Cycle" button on the terminal.
2.  **Review Recommendations**: Check the "Self-Healing Insights" panel for pending optimizations.
3.  **Manual Approval**: Review the "Projected Win-Rate Improvement" (e.g., +8.5%). Click **APPLY** to commit these changes to the live scanner.

## 📈 Performance Tracking
The Phase 5 system manages the "Consensus Health" of the bot. If a specific gate (e.g., Gate 2: Volume) starts failing frequently in a certain regime, the system will automatically recommend increasing the volume multiplier to filter out low-quality "pre-market noise."

---
**Tip**: A regime change from Trending to Volatile will automatically trigger a "Risk Lockdown" mode, reducing your default position size to protect capital.
