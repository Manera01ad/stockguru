# StockGuru — M3 Completion Report
**Date:** 2026-03-01
**Sprint:** M3 — Production Hardening + Intelligence Upgrade
**Test result:** 87/87 passing (0 failures, 0 xfail)

---

## M3 Task Summary

| Task | Description | Status |
|------|-------------|--------|
| M3-1 | Fix morning_brief telegram exception (xfail → passing) | ✅ Done |
| M3-2 | Railway production deployment (gunicorn + SocketIO) | ✅ Done |
| M3-3 | builder_agent auto-patch proposals wiring | ✅ Done |
| M3-4 | Trailing SL in `broker_connector.tick()` | ✅ Done |
| M3-5 | Post-mortem insights → Claude Intelligence context | ✅ Done |
| M3-6 | Full test suite + M3 completion report | ✅ Done |

---

## M3-1: morning_brief — Non-Fatal Telegram

**Problem:** `morning_brief.run()` propagated `Exception` from `send_telegram_fn()` and crashed the 15-minute agent cycle. Test was marked `@pytest.mark.xfail`.

**Fix (`stockguru_agents/agents/morning_brief.py`):**
- Wrapped all `send_telegram_fn()` calls in `try/except Exception`
- Wrapped all `send_n8n_fn()` calls in `try/except Exception`
- Added `shared_state["morning_brief_text"] = msg` for downstream access
- Log warnings on delivery failure; agent returns normally

**Test update (`tests/test_agents_unit.py::TestMorningBrief::test_telegram_failure`):**
- Removed `@pytest.mark.xfail`
- Added assertions that `last_morning_brief` key is set and result is non-None when Telegram raises

---

## M3-2: Railway Production Deployment

**Problem:** Procfile used `--threads 4` (incompatible with Flask-SocketIO gevent worker); no health-check endpoint wired into Railway config.

**New files:**

**`gunicorn.conf.py`** — production server config:
- `worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"` (required for SocketIO)
- `workers = 1` (in-memory shared_state cannot be forked)
- `timeout = 300` (covers 15-min agent cycles)
- `preload_app = False` (startup must run in worker context)
- `bind = f"0.0.0.0:{os.getenv('PORT', '5050')}"`

**`nixpacks.toml`** — Railway NIXPACKS build config:
- Pins Python 3.10 via `nixPkgs = ["python310", "python310Packages.pip"]`
- Runs `pip install -r requirements.txt --no-cache-dir`

**`runtime.txt`** — `python-3.10.12` (Heroku/Railway compatibility)

**Updated files:**
- `Procfile` → `web: gunicorn app:app --config gunicorn.conf.py`
- `railway.json` → `startCommand` + `healthcheckPath: /api/health` + 5-retry restart policy
- `.env.example` → 7-point Railway deployment checklist

**Critical note:** `eventlet` must NOT be in requirements.txt — it conflicts with system OpenSSL on Linux and breaks yfinance. gevent backend only.

---

## M3-3: Builder Agent Auto-Patch Proposals Wiring

**Problem:** Builder agent wrote `shared_state["builder_output"]` but the dashboard had no visual indicator when a new panel was proposed via Telegram inline-button flow.

**Changes (`app.py`):**
- Added `builder_output` and `observer_run_count` to `_ws_emit_agents()` WebSocket payload

**Changes (`static/index.html`):**
- Added `fetchBuilderProposals()` to the `agents_update` SocketIO handler
- Added `builder-badge` span on the Sovereign tab button
- Badge shows `NEW` in amber when `data.builder_output.status === 'proposed'`
- Badge clears on Sovereign tab click via `onclick`

---

## M3-4: Trailing Stop-Loss in `broker_connector.tick()`

**Problem:** After T1 booking, `pos.stop_loss` was only moved to `avg_price` (breakeven) and never updated again — exposing unrealised profit between T1 and T2.

**Constant added (`broker_connector.py`):**
```python
TRAILING_SL_PCT = 0.03   # 3% trail below highest LTP after T1
```

**Field added to `Position` dataclass:**
```python
trail_sl_high: float = 0.0   # Highest LTP seen after T1 (for trailing SL)
```

**`tick()` logic enhanced:**

_On T1 hit:_
```python
pos.trail_sl_high = ltp          # seed high at T1 price
pos.stop_loss = pos.avg_price    # floor at breakeven
```

_Every tick after T1 (ratchet mechanism):_
```python
if ltp > pos.trail_sl_high:
    pos.trail_sl_high = ltp
    new_sl = round(max(pos.avg_price, pos.trail_sl_high * (1 - TRAILING_SL_PCT)), 2)
    if new_sl > pos.stop_loss:
        pos.stop_loss = new_sl
```

**Guarantees:**
- SL never moves downward (ratchet-only)
- SL never drops below `avg_price` (breakeven floor)
- SL automatically follows price up by 3% — locks in profit between T1 and T2

**New test file:** `tests/test_m3_trailing_sl.py` — 12 tests covering:
- T1 seeds breakeven SL and trail_sl_high
- T1 books half quantity (5 of 10 shares)
- Trailing SL raises as price climbs
- Ratchet: SL never moves backward
- Floor: SL never below avg_price
- Multi-step accumulation
- SL exit triggered at trailed SL level
- No trail before T1 hits
- T2 exit after trailing SL was active
- Constant and dataclass field validation

---

## M3-5: Post-Mortem Insights → Claude Intelligence

**Problem:** `claude_intelligence.py` built its LLM prompt from trading skills + accuracy stats + patterns, but had no awareness of _what specific trades had failed and why_ — missing the reflexion loop from `post_mortem.py`.

**New function `_load_post_mortem_context(shared_state)` in `claude_intelligence.py`:**

Sources tapped (in priority):
1. `shared_state["post_mortem_llm_note"]` — LLM-generated global lesson from the last post-mortem LLM call
2. `shared_state["post_mortem_output"]` — latest cycle summary (failure count, tickers, adjustment count, root diagnosis)
3. `data/post_mortem_log.json` — last 3 failure reflexions (ticker, root cause, reflexion text, capped at 120 chars each)

**SYSTEM_PROMPT updated:** New section `RECENT POST-MORTEM INSIGHTS` between accuracy and patterns:
```
RECENT POST-MORTEM INSIGHTS (failures analyzed by the learning engine):
{post_mortem}
```

**`_call_claude()` updated:** Passes `post_mortem=_load_post_mortem_context(shared_state)` when formatting the system prompt.

**Result:** Every LLM call now carries the system's own learning — e.g. "Avoid IT after consecutive FII sell sessions; RSI divergence is a false positive in bear markets." This creates a true reflexion loop: post-mortem writes lessons → Claude reads them → makes better picks → fewer post-mortems.

**4 new tests added to `TestClaudeIntelligence`:**
- `test_post_mortem_context_in_prompt` — failure tickers and lessons appear in context
- `test_post_mortem_context_empty_state` — returns safe fallback string
- `test_system_prompt_has_post_mortem_placeholder` — `{post_mortem}` in SYSTEM_PROMPT
- `test_post_mortem_context_injected_in_api_call` — sentinel lesson appears verbatim in API system arg

---

## Test Suite Progression

| Milestone | Tests | Result |
|-----------|-------|--------|
| M1 baseline | 54 unit + 4 integration | 54 passed, 1 xfail |
| M2 (WebSocket, Observer, Backtester) | +16 tests | 70 passed, 1 xfail |
| M3-1 (xfail fix) | — | 71 passed, 0 xfail |
| M3-4 (Trailing SL) | +12 tests | 83 passed |
| M3-5 (Post-Mortem→Claude) | +4 tests | 87 passed |
| **M3 Final** | **87 tests** | **87/87 ✅** |

---

## Files Changed in M3

| File | Change |
|------|--------|
| `stockguru_agents/agents/morning_brief.py` | try/except on Telegram/n8n calls; write `morning_brief_text` |
| `stockguru_agents/agents/claude_intelligence.py` | `_load_post_mortem_context()` + `{post_mortem}` in SYSTEM_PROMPT |
| `stockguru_agents/broker_connector.py` | `TRAILING_SL_PCT` const, `trail_sl_high` field, trailing SL in `tick()` |
| `app.py` | `builder_output` + `observer_run_count` in `_ws_emit_agents()` |
| `static/index.html` | Builder badge on Sovereign tab; `fetchBuilderProposals` in SocketIO handler |
| `Procfile` | Updated to use `gunicorn.conf.py` |
| `railway.json` | `healthcheckPath`, `startCommand`, retry policy |
| `gunicorn.conf.py` | **NEW** — GeventWebSocketWorker production config |
| `nixpacks.toml` | **NEW** — Railway NIXPACKS build config |
| `runtime.txt` | **NEW** — Python 3.10.12 pinned |
| `.env.example` | Railway deployment checklist (7-point) |
| `tests/test_agents_unit.py` | xfail→passing; 4 new M3-5 tests |
| `tests/test_m3_trailing_sl.py` | **NEW** — 12 trailing SL tests |

---

## Architecture Impact

```
post_mortem.py
    ↓ (writes lessons to shared_state + data/post_mortem_log.json)
claude_intelligence.py
    ↓ (reads _load_post_mortem_context() into SYSTEM_PROMPT)
  Claude Haiku API
    ↓ (makes better conviction picks, avoids repeat failures)
paper_trader.py
    ↓ (executes picks via PaperBroker)
broker_connector.PaperBroker.tick()
    ↓ (trails SL upward after T1, locks in profit)
  Fewer SL_HITs → fewer post-mortems
    ↑_______________________________________↑   (reflexion loop closes)
```

---

## Ready for M4

The codebase is now production-ready on Railway with:
- Stable WebSocket push (gevent + SocketIO)
- Builder agent proposal UX (Telegram → Dashboard badge)
- Trailing stop-loss protecting paper trades
- Self-improving LLM prompt via post-mortem reflexion loop
- 87 tests covering all core paths

**M4 candidates:** LiveBroker adapter (Zerodha/Upstox), multi-position sizing (Kelly criterion), Telegram alert enrichment with voice/charts, Redis-backed shared_state for horizontal scaling.
