"""
AGENT 14 — PAPER TRADING ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

╔══════════════════════════════════════════════════════════════════╗
║  🔒 SAFETY GUARANTEE — READ FIRST                               ║
║                                                                  ║
║  This agent has ZERO connection to any real broker API.          ║
║  It ONLY simulates trades using Yahoo Finance prices.            ║
║  No real money is ever at risk.                                  ║
║                                                                  ║
║  LIVE_TRADING_ENABLED = False  ←  hardcoded, never changes       ║
║  PAPER_TRADING_ONLY   = True   ←  always True in this version    ║
║                                                                  ║
║  To even consider live trading:                                  ║
║    1. Paper win rate must be >= 65% over 50+ trades              ║
║    2. User must explicitly configure and confirm separately      ║
║    3. A completely separate broker_connector.py must be built    ║
║    4. User gives explicit permission per session                 ║
╚══════════════════════════════════════════════════════════════════╝

CONVICTION GATE SYSTEM (8 gates — need 6+ to execute):
  Gate 1: Score gate     — agent score >= 88
  Gate 2: RSI gate       — RSI between 35-68 (not overbought)
  Gate 3: Volume gate    — volume surge >= 1.3x
  Gate 4: Trend gate     — price above 50-EMA
  Gate 5: MACD gate      — MACD bullish (line > signal)
  Gate 6: News gate      — no negative news impact
  Gate 7: FII gate       — FII not net selling
  Gate 8: Options gate   — PCR between 0.6-1.15

TRADE MANAGEMENT:
  Entry   : Next 5-min price fetch after signal (simulates real delay)
  Costs   : Slippage(0.05%) + Brokerage(₹20) + STT(0.1% both sides) +
            Exchange(0.00297%) + SEBI(0.0001%) + Stamp(0.015% buy) + DP(₹15.93 sell) + GST(18%)
  Booking : 50% at T1 (trail SL to breakeven), 50% run to T2
  Exit    : Monitored every 5 minutes (when price_cache updates)
"""

import os
import json
import logging
from datetime import datetime, date

log = logging.getLogger("PaperTrader")

# ══════════════════════════════════════════════════════════════════════════════
# 🔒 SAFETY LOCKS — These are permanent. NEVER remove or bypass these.
# ══════════════════════════════════════════════════════════════════════════════
LIVE_TRADING_ENABLED    = False   # HARDCODED — never change this
PAPER_TRADING_ONLY      = True    # HARDCODED — this is always a simulation
BROKER_CONNECTOR_EXISTS = True    # broker_connector.py now available (paper mode only)
# ══════════════════════════════════════════════════════════════════════════════

# ── Broker Connector Import ───────────────────────────────────────────────────
# Import the broker interface so paper_trader uses proper terminal-grade structures.
# broker_connector.LIVE_TRADING_ENABLED is also False — double lock.
try:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from broker_connector import (
        get_broker, OrderBuilder, PaperBroker,
        OrderType, ProductCode, TransactionType, Exchange, Validity,
        OrderStatus, compute_costs,
    )
    _BROKER_AVAILABLE = True
except ImportError as _e:
    log.warning("broker_connector not found (%s) — falling back to legacy engine", _e)
    _BROKER_AVAILABLE = False
# ─────────────────────────────────────────────────────────────────────────────

_BASE           = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO_FILE  = os.path.join(_BASE, "data", "paper_portfolio.json")
TRADES_FILE     = os.path.join(_BASE, "data", "paper_trades.json")

DEFAULT_CAPITAL = float(os.getenv("PAPER_CAPITAL", "500000"))  # ₹5L default

# ── REALISTIC COST MODEL (Indian Equity Delivery) ────────────────────────────
# Matches Zerodha/Upstox/Angel One discount broker structure
SLIPPAGE_PCT      = 0.0005    # 0.05% slippage (realistic for mid-cap)

# ── AUTO TRAILING STOP LOSS ────────────────────────────────────────────────────
# When TSL is enabled on a position, every time price moves up by TSL_STEP_PCT
# the stop-loss is ratcheted up by the same amount (locks in profit).
TSL_STEP_PCT      = 0.005    # 0.5% step — ratchet SL up every 0.5% price gain
TSL_MIN_GAIN_PCT  = 0.01     # Only start trailing after price is 1% above entry
BROKERAGE_FLAT    = 20.0      # ₹20 flat per order (discount broker model)
STT_PCT           = 0.001     # 0.1% STT — on BOTH buy & sell for delivery equity
STT_INTRADAY_PCT  = 0.00025   # 0.025% STT — sell side only for intraday (not used here)
EXCHANGE_PCT      = 0.0000297 # 0.00297% NSE transaction charge
SEBI_PCT          = 0.000001  # 0.0001% SEBI turnover fee
STAMP_DUTY_PCT    = 0.00015   # 0.015% stamp duty on BUY only (state tax)
DP_CHARGES        = 15.93     # ₹15.93 CDSL/NSDL depository charge per SELL (delivery)

def _compute_costs(price, shares, side="BUY"):
    """
    Complete Indian equity delivery cost model:
      BUY  side: Brokerage + STT(0.1%) + Exchange + SEBI + Stamp(0.015%) + GST + Slippage
      SELL side: Brokerage + STT(0.1%) + Exchange + SEBI + DP(₹15.93) + GST + Slippage
    """
    value         = price * shares
    slippage      = value * SLIPPAGE_PCT
    brokerage     = min(BROKERAGE_FLAT, value * 0.0003)  # ₹20 or 0.03% whichever lower
    stt           = value * STT_PCT                       # 0.1% on both sides delivery
    exchange_fees = value * EXCHANGE_PCT
    sebi_fee      = value * SEBI_PCT
    stamp         = value * STAMP_DUTY_PCT if side == "BUY" else 0
    dp            = DP_CHARGES if side == "SELL" else 0
    gst           = (brokerage + exchange_fees + sebi_fee) * 0.18
    total_cost    = slippage + brokerage + stt + exchange_fees + sebi_fee + stamp + dp + gst
    return round(total_cost, 2)

def _cost_breakdown(price, shares, side="BUY"):
    """Return itemised cost breakdown for display in P&L reports."""
    value = price * shares
    b = min(BROKERAGE_FLAT, value * 0.0003)
    s = value * STT_PCT
    e = value * EXCHANGE_PCT
    sebi = value * SEBI_PCT
    stamp = value * STAMP_DUTY_PCT if side == "BUY" else 0
    dp = DP_CHARGES if side == "SELL" else 0
    gst = (b + e + sebi) * 0.18
    slip = value * SLIPPAGE_PCT
    return {
        "brokerage": round(b, 2), "stt": round(s, 2),
        "exchange":  round(e + sebi, 2), "stamp": round(stamp, 2),
        "dp_charges": round(dp, 2), "gst": round(gst, 2),
        "slippage":  round(slip, 2),
        "total":     round(slip + b + s + e + sebi + stamp + dp + gst, 2),
    }

# ── PORTFOLIO PERSISTENCE ─────────────────────────────────────────────────────
def _load_portfolio():
    try:
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "capital":          DEFAULT_CAPITAL,
            "available_cash":   DEFAULT_CAPITAL,
            "invested":         0.0,
            "unrealized_pnl":   0.0,
            "realized_pnl":     0.0,
            "total_pnl":        0.0,
            "total_return_pct": 0.0,
            "positions":        {},
            "daily_pnl":        {},        # {date_str: pnl_pct}
            "daily_pnl_pct":    0.0,       # today's P&L %
            "stats": {
                "total_trades":  0,
                "wins":          0,
                "losses":        0,
                "win_rate":      0.0,
                "avg_win_pct":   0.0,
                "avg_loss_pct":  0.0,
                "best_trade":    None,
                "worst_trade":   None,
                "max_drawdown":  0.0,
                "sharpe_approx": 0.0,
            },
            "safety": {
                "live_trading":  False,  # ALWAYS False
                "paper_only":    True,   # ALWAYS True
                "mode":          "SIMULATION",
            },
            "created_at":       datetime.now().isoformat(),
            "last_updated":     datetime.now().isoformat(),
        }

def _save_portfolio(portfolio):
    portfolio["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2, default=str)

def _load_trades():
    try:
        with open(TRADES_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def _save_trades(trades):
    os.makedirs(os.path.dirname(TRADES_FILE), exist_ok=True)
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)

# ── CONVICTION GATE CHECKER ───────────────────────────────────────────────────
def _check_gates(signal, shared_state):
    """
    Check all 8 conviction gates for a signal.
    Returns (gates_passed, gate_detail, reasons)
    """
    name   = signal.get("name", "")
    score  = signal.get("score", 0)
    tech   = shared_state.get("technical_data", {}).get(name, {})
    inst   = shared_state.get("institutional_flow", {})
    opts   = shared_state.get("options_flow", {})
    news_m = shared_state.get("stock_sentiment_map", {})
    web    = shared_state.get("web_research", {}).get(name, {})

    gates  = {}
    passed = 0
    reasons = []

    # Gate 1: Score gate — agent score >= 88
    g1 = score >= 88
    gates["score_gate"] = g1
    if g1: passed += 1
    else:  reasons.append(f"Score {score} < 88")

    # Gate 2: RSI gate — not overbought (35-68)
    rsi    = tech.get("rsi")
    g2     = tech.get("gates", {}).get("rsi_gate") if tech else None
    if g2 is None:
        g2 = (35 <= rsi <= 68) if rsi is not None else True  # pass if unknown
    gates["rsi_gate"] = bool(g2)
    if g2: passed += 1
    else:  reasons.append(f"RSI {rsi:.1f} outside 35-68" if rsi else "RSI unavailable")

    # Gate 3: Volume gate — vol_surge >= 1.3x
    vol    = signal.get("vol_surge", 1.0)
    g3     = vol >= 1.3
    gates["volume_gate"] = g3
    if g3: passed += 1
    else:  reasons.append(f"Volume {vol:.1f}x < 1.3x avg")

    # Gate 4: Trend gate — above 50-EMA
    g4 = tech.get("above_ema50") if tech else None
    if g4 is None: g4 = True  # pass if unknown (no data yet)
    gates["trend_gate"] = bool(g4)
    if g4: passed += 1
    else:  reasons.append("Price below 50-EMA (R3)")

    # Gate 5: MACD gate — bullish
    g5 = tech.get("macd_bullish") if tech else None
    if g5 is None: g5 = True  # pass if unknown
    gates["macd_gate"] = bool(g5)
    if g5: passed += 1
    else:  reasons.append("MACD bearish (R7)")

    # Gate 6: News gate — no strongly negative news
    news_score = news_m.get(name, {}).get("score", 0)
    web_safe   = web.get("safe_to_trade", True)
    g6 = news_score >= -1.5 and web_safe
    gates["news_gate"] = g6
    if g6: passed += 1
    else:
        if not web_safe:
            reasons.append(f"Web research: {web.get('key_finding','negative news')}")
        else:
            reasons.append(f"Negative news score {news_score:.1f}")

    # Gate 7: FII gate — FII not strongly selling (R5)
    g7 = inst.get("fii_gate_pass", True)
    gates["fii_gate"] = bool(g7)
    if g7: passed += 1
    else:  reasons.append(f"FII selling {inst.get('fii_net_crore',0):.0f}Cr (R22)")

    # Gate 8: Options gate — PCR in acceptable range (R8)
    g8 = opts.get("options_gate", True)
    gates["options_gate"] = bool(g8)
    if g8: passed += 1
    else:  reasons.append(f"PCR {opts.get('nifty_pcr','?')} outside range (R8)")

    return passed, gates, reasons

# ── POSITION ENTRY ────────────────────────────────────────────────────────────
def _enter_position(signal, gates_passed, gate_detail, portfolio, price_cache, shared_state):
    """Execute a paper trade entry. Returns trade record or None."""
    name    = signal.get("name", "")
    sector  = signal.get("sector", "")
    score   = signal.get("claude_score", signal.get("score", 0))
    t1      = signal.get("target1", signal.get("target", 0))
    t2      = signal.get("target2", 0)
    sl_orig = signal.get("stop_loss", signal.get("sl", 0))

    # Get current market price
    cached = price_cache.get(name, {})
    price  = cached.get("price", 0)
    if not price:
        log.warning("PaperTrader: No price for %s — cannot enter", name)
        return None

    # Apply slippage (buy slightly above current price = realistic)
    entry_price = round(price * (1 + SLIPPAGE_PCT), 2)

    # Get risk-approved position size
    risk_data = signal.get("risk", {})
    shares    = risk_data.get("position_size", 0)
    if shares <= 0:
        # Fallback sizing if risk_manager didn't run
        risk_amount = portfolio["available_cash"] * 0.02
        sl_risk     = abs(entry_price - sl_orig) if sl_orig else entry_price * 0.08
        shares      = max(1, int(risk_amount / sl_risk)) if sl_risk > 0 else 1

    # Check available cash
    entry_cost    = round(entry_price * shares, 2)
    trade_costs   = _compute_costs(entry_price, shares, "BUY")
    total_outlay  = entry_cost + trade_costs

    if total_outlay > portfolio["available_cash"]:
        # Reduce shares to fit available cash
        max_shares = int((portfolio["available_cash"] * 0.95) / (entry_price + entry_price * SLIPPAGE_PCT))
        if max_shares <= 0:
            log.warning("PaperTrader: Insufficient cash for %s (need ₹%.0f, have ₹%.0f)",
                        name, total_outlay, portfolio["available_cash"])
            return None
        shares     = max_shares
        entry_cost = round(entry_price * shares, 2)
        trade_costs = _compute_costs(entry_price, shares, "BUY")

    # Record the position
    position = {
        "name":             name,
        "sector":           sector,
        "score":            score,
        "signal_type":      signal.get("signal", "BUY"),
        "shares":           shares,
        "entry_price":      entry_price,
        "entry_cost":       entry_cost,
        "buy_costs":        trade_costs,
        "target1":          t1,
        "target2":          t2,
        "stop_loss":        sl_orig,
        "trailing_sl":      sl_orig,    # moves up after T1 hit / TSL
        "tsl_enabled":      True,       # Auto Trailing SL — on by default
        "tsl_high_water":   entry_price,# highest price seen since entry
        "t1_booked":        False,      # has T1 partial booking happened?
        "shares_remaining": shares,
        "status":           "OPEN",
        "gates_passed":     gates_passed,
        "gate_detail":      gate_detail,
        "entry_time":       datetime.now().isoformat(),
        "paper_only":       True,       # safety marker
        "live_trade":       False,      # safety marker — always False
    }

    # Deduct from portfolio
    portfolio["available_cash"] = round(portfolio["available_cash"] - total_outlay, 2)
    portfolio["invested"]       = round(portfolio["invested"] + entry_cost, 2)
    portfolio["positions"][name] = position

    log.info("📗 PAPER BUY: %s | %d shares @ ₹%.2f | Cost ₹%.0f | Gates %d/8 | T1=₹%.1f SL=₹%.1f",
             name, shares, entry_price, total_outlay, gates_passed, t1, sl_orig)

    # Record in signal_tracker
    try:
        import sys
        sys.path.insert(0, os.path.join(_BASE, "stockguru_agents"))
        from learning import signal_tracker
        signal_tracker.record_signal(
            name=name, sector=sector,
            signal_type=signal.get("signal", "BUY"),
            entry_price=entry_price,
            target1=t1, target2=t2,
            stop_loss=sl_orig, score=score,
            confidence=signal.get("confidence", "MEDIUM"),
            gates_passed=gates_passed,
        )
    except Exception as e:
        log.debug("signal_tracker record failed: %s", e)

    # ── ATLAS: Log full multi-dimensional entry context ──────────────────────
    try:
        from atlas.core import log_trade_entry
        from atlas.volume_classifier import classify_volume
        from atlas.regime_detector import get_time_context
        from atlas.news_impact_mapper import classify_news_event

        # Extract signal metadata
        meta      = signal.get("meta", {}) or {}
        opts_data = shared_state.get("options_flow", {}) if shared_state else {}
        nifty_opts = opts_data.get("nifty", {}) if isinstance(opts_data.get("nifty"), dict) else {}
        bnf_opts   = opts_data.get("banknifty", {}) if isinstance(opts_data.get("banknifty"), dict) else {}
        fii_data  = shared_state.get("institutional_flow", {}) if shared_state else {}
        news_data = shared_state.get("news_sentiment", {}) if shared_state else {}
        ta_data   = signal.get("technical", {}) or {}

        # Volume classification
        vol_data   = meta.get("volume_data", {}) or {}
        vol_result = classify_volume(
            ticker                  = name,
            current_volume          = vol_data.get("current_volume", 0),
            avg_volume_20d          = vol_data.get("avg_volume", 1),
            price_change_pct        = vol_data.get("price_change_pct", 0),
            price_vs_high_52w       = meta.get("price_vs_52w_high", 100),
            price_vs_resistance     = meta.get("vs_resistance_pct", 0),
            is_near_corporate_event = meta.get("near_earnings", False),
        ) if vol_data.get("current_volume") else {"volume_class": None, "volume_ratio": None, "signal": None}

        # Time context
        time_ctx = get_time_context()

        # ATLAS entry log
        atlas_event_id = f"ATLAS_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        log_trade_entry(
            event_id     = atlas_event_id,
            ticker       = name,
            sector       = sector,
            entry_price  = entry_price,
            signal_type  = signal.get("signal", "BUY"),
            entry_score  = score,
            gates_passed = gates_passed,
            # Technical
            rsi          = ta_data.get("rsi") or meta.get("rsi"),
            macd_cross   = "BULL" if ta_data.get("macd_bullish") else ("BEAR" if ta_data.get("macd_bullish") is False else None),
            ema_position = meta.get("ema_position"),
            trend_strength = meta.get("trend_strength"),
            # Options
            pcr_nifty    = nifty_opts.get("pcr"),
            pcr_banknifty = bnf_opts.get("pcr"),
            max_pain_nifty = nifty_opts.get("max_pain"),
            iv_percentile = nifty_opts.get("iv_percentile"),
            options_signal = nifty_opts.get("signal"),
            # News
            news_sentiment_score  = news_data.get("overall_score"),
            news_event_type       = news_data.get("top_event_type"),
            news_impact_magnitude = news_data.get("impact_magnitude"),
            # Volume
            volume_class   = vol_result.get("volume_class"),
            volume_ratio   = vol_result.get("volume_ratio"),
            volume_signal  = vol_result.get("signal"),
            # Regime / Time
            regime         = shared_state.get("market_regime", {}).get("regime") if shared_state else None,
            regime_strength = shared_state.get("market_regime", {}).get("strength") if shared_state else None,
            market_session = time_ctx.get("session"),
            day_of_week    = time_ctx.get("day_of_week"),
            week_type      = time_ctx.get("week_type"),
            # Fundamental
            fii_flow       = fii_data.get("fii_flow"),
            dii_flow       = fii_data.get("dii_flow"),
            sector_momentum = shared_state.get("sector_momentum", {}).get(sector) if shared_state else None,
        )
        # Store ATLAS event_id on position for outcome tracking later
        position["atlas_event_id"] = atlas_event_id
        log.debug("🧠 ATLAS: Entry logged for %s [%s]", name, atlas_event_id)
    except Exception as e:
        log.debug("ATLAS entry log failed: %s", e)

    return position

# ── POSITION MONITOR & EXIT ───────────────────────────────────────────────────
def _monitor_positions(portfolio, price_cache):
    """
    Check all open positions against current prices.
    Execute partial T1 booking, trailing SL updates, full T2/SL exits.
    Called every 5 minutes when price_cache updates.
    """
    trades    = _load_trades()
    closed    = []
    today_str = date.today().isoformat()

    for name, pos in list(portfolio["positions"].items()):
        if pos.get("status") != "OPEN":
            continue

        cached = price_cache.get(name, {})
        price  = cached.get("price")
        if not price:
            continue

        shares_rem = pos["shares_remaining"]
        entry      = pos["entry_price"]
        t1         = pos["target1"]
        t2         = pos["target2"]
        trail_sl   = pos["trailing_sl"]
        t1_booked  = pos["t1_booked"]

        # ── AUTO TRAILING SL (TSL) ────────────────────────────────────────────
        # If TSL is enabled: ratchet SL up whenever price makes a new high
        # (by at least TSL_STEP_PCT above last recorded high water mark)
        if pos.get("tsl_enabled", False):
            hw = pos.get("tsl_high_water", entry)
            if price > hw * (1 + TSL_STEP_PCT):
                # How many TSL_STEP_PCT steps above entry?
                gain_pct   = (price - entry) / entry
                steps      = int(gain_pct / TSL_STEP_PCT)
                # Only start trailing after TSL_MIN_GAIN_PCT above entry
                if gain_pct >= TSL_MIN_GAIN_PCT and steps > 0:
                    # New SL = entry + (steps-1) * TSL_STEP_PCT  (keep one step below current)
                    new_sl = round(entry * (1 + (steps - 1) * TSL_STEP_PCT), 2)
                    if new_sl > trail_sl:
                        pos["trailing_sl"]    = new_sl
                        pos["tsl_high_water"] = price
                        trail_sl              = new_sl
                        log.info("📈 TSL UPDATE: %s | new SL=₹%.2f (price=₹%.2f, gain=%.1f%%)",
                                 name, new_sl, price, gain_pct * 100)

        # ── T2 HIT (remaining shares → full exit at T2)
        if price >= t2 and t1_booked and t2 > 0:
            sell_costs = _compute_costs(price, shares_rem, "SELL")
            pnl_trade  = round(((price * (1 - SLIPPAGE_PCT)) - entry) * shares_rem - sell_costs, 2)
            pnl_pct    = round(((price - entry) / entry) * 100, 2)
            _close_position(portfolio, name, "T2_HIT", price, shares_rem, pnl_trade, pnl_pct, trades)
            closed.append(name)
            log.info("🎯 PAPER T2 EXIT: %s @ ₹%.2f | P&L: +₹%.0f (+%.1f%%)",
                     name, price, pnl_trade, pnl_pct)

        # ── T1 HIT (first partial booking — 50%)
        elif price >= t1 and not t1_booked:
            shares_book = max(1, shares_rem // 2)
            sell_costs  = _compute_costs(t1, shares_book, "SELL")
            pnl_partial = round(((t1 * (1 - SLIPPAGE_PCT)) - entry) * shares_book - sell_costs, 2)
            proceeds    = round(t1 * shares_book, 2)

            portfolio["available_cash"] += proceeds - sell_costs
            portfolio["realized_pnl"]   += pnl_partial

            # Trail SL to breakeven on remaining shares
            pos["t1_booked"]        = True
            pos["shares_remaining"] = shares_rem - shares_book
            pos["trailing_sl"]      = max(trail_sl, entry * 1.002)  # SL to breakeven+0.2%

            pnl_pct = round(((t1 - entry) / entry) * 100, 2)
            log.info("🎯 PAPER T1 BOOK: %s | Sold %d @ ₹%.2f | P&L: +₹%.0f (+%.1f%%) | Remaining: %d shares (SL→breakeven)",
                     name, shares_book, t1, pnl_partial, pnl_pct, pos["shares_remaining"])

            # Update trade record
            trades.append({
                "name": name, "type": "PARTIAL_T1",
                "shares": shares_book, "price": t1,
                "pnl": pnl_partial, "pnl_pct": pnl_pct,
                "time": datetime.now().isoformat(), "paper_only": True,
            })

        # ── TRAILING SL HIT
        elif price <= trail_sl and trail_sl > 0:
            sell_costs = _compute_costs(price, shares_rem, "SELL")
            pnl_trade  = round(((price * (1 - SLIPPAGE_PCT)) - entry) * shares_rem - sell_costs, 2)
            pnl_pct    = round(((price - entry) / entry) * 100, 2)
            outcome    = "SL_HIT" if not t1_booked else "SL_AFTER_T1"
            _close_position(portfolio, name, outcome, price, shares_rem, pnl_trade, pnl_pct, trades)
            closed.append(name)
            emoji = "⛔" if pnl_trade < 0 else "✅"
            log.info("%s PAPER SL EXIT: %s @ ₹%.2f | P&L: ₹%.0f (%.1f%%)",
                     emoji, name, price, pnl_trade, pnl_pct)

    # Remove closed positions
    for name in closed:
        portfolio["positions"].pop(name, None)

    if closed:
        _rebuild_stats(portfolio)
        _update_daily_pnl(portfolio)

    _save_trades(trades)
    return closed

def _close_position(portfolio, name, outcome, exit_price, shares, pnl, pnl_pct, trades):
    """Close a position, update portfolio cash and stats."""
    pos         = portfolio["positions"].get(name, {})
    proceeds    = round(exit_price * shares, 2)
    sell_costs  = _compute_costs(exit_price, shares, "SELL")

    portfolio["available_cash"] = round(portfolio["available_cash"] + proceeds - sell_costs, 2)
    portfolio["invested"]       = max(0, round(portfolio["invested"] - pos.get("entry_cost", 0), 2))
    portfolio["realized_pnl"]   = round(portfolio["realized_pnl"] + pnl, 2)

    pos["status"]     = "CLOSED"
    pos["exit_price"] = exit_price
    pos["exit_time"]  = datetime.now().isoformat()
    pos["outcome"]    = outcome
    pos["final_pnl"]  = pnl
    pos["final_pnl_pct"] = pnl_pct

    # ── ATLAS: Record trade outcome for knowledge learning ───────────────────
    atlas_event_id = pos.get("atlas_event_id")
    if atlas_event_id:
        try:
            from atlas.core import update_trade_outcome
            entry_time = pos.get("entry_time")
            hold_hrs   = None
            if entry_time:
                try:
                    delta = datetime.now() - datetime.fromisoformat(entry_time)
                    hold_hrs = round(delta.total_seconds() / 3600, 1)
                except Exception:
                    pass
            update_trade_outcome(
                event_id          = atlas_event_id,
                outcome           = outcome,
                exit_price        = exit_price,
                pnl_pct           = pnl_pct,
                hold_duration_hrs = hold_hrs,
            )
            log.debug("🧠 ATLAS: Outcome logged %s → %s %.1f%%", atlas_event_id, outcome, pnl_pct)
        except Exception as e:
            log.debug("ATLAS outcome log failed: %s", e)

    trades.append({
        "name":      name,
        "sector":    pos.get("sector", ""),
        "type":      "CLOSE",
        "outcome":   outcome,
        "shares":    shares,
        "entry":     pos.get("entry_price", 0),
        "exit":      exit_price,
        "pnl":       pnl,
        "pnl_pct":   pnl_pct,
        "gates":     pos.get("gates_passed", 0),
        "time":      datetime.now().isoformat(),
        "paper_only": True,
    })

def _rebuild_stats(portfolio):
    """Recalculate win rate, avg win/loss from trade history."""
    trades = _load_trades()
    closes = [t for t in trades if t.get("type") == "CLOSE"]
    if not closes:
        return

    wins   = [t for t in closes if t.get("outcome") in ("T1_HIT", "T2_HIT")]
    losses = [t for t in closes if t.get("outcome") in ("SL_HIT", "SL_AFTER_T1")]

    portfolio["stats"]["total_trades"]  = len(closes)
    portfolio["stats"]["wins"]          = len(wins)
    portfolio["stats"]["losses"]        = len(losses)
    portfolio["stats"]["win_rate"]      = round(len(wins) / len(closes), 3) if closes else 0
    portfolio["stats"]["avg_win_pct"]   = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    portfolio["stats"]["avg_loss_pct"]  = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0

    if wins:
        best = max(wins, key=lambda x: x["pnl_pct"])
        portfolio["stats"]["best_trade"] = f"{best['name']} +{best['pnl_pct']:.1f}%"
    if losses:
        worst = min(losses, key=lambda x: x["pnl_pct"])
        portfolio["stats"]["worst_trade"] = f"{worst['name']} {worst['pnl_pct']:.1f}%"

def _update_daily_pnl(portfolio):
    """Track today's P&L %."""
    capital     = portfolio.get("capital", DEFAULT_CAPITAL)
    today       = date.today().isoformat()
    start_val   = portfolio.get("daily_start_value", capital)
    current_val = capital + portfolio.get("realized_pnl", 0) + portfolio.get("unrealized_pnl", 0)
    daily_pnl_pct = round(((current_val - start_val) / start_val) * 100, 2) if start_val else 0

    portfolio["daily_pnl_pct"]         = daily_pnl_pct
    portfolio["daily_pnl"][today]      = daily_pnl_pct
    portfolio["total_pnl"]             = round(portfolio.get("realized_pnl", 0), 2)
    portfolio["total_return_pct"]      = round((portfolio["total_pnl"] / capital) * 100, 2)

# ── BROKER-INTEGRATED EXECUTION ──────────────────────────────────────────────
def execute_signal_via_broker(broker: "PaperBroker", signal: dict,
                               shared_state: dict) -> dict:
    """
    Convert a StockGuru trade signal into a broker terminal order.
    Uses OrderBuilder for clean signal→order mapping.
    Returns the Order as a dict (JSON-serialisable) or None if rejected.

    Signal expected keys:
      symbol, action (BUY/SELL), entry, target1, target2, stop_loss,
      confidence, gates_passed, gates_total
    """
    if not _BROKER_AVAILABLE:
        return None

    portfolio_info = broker.get_margins()
    available_cash = portfolio_info["available_cash"]
    entry_price    = float(signal.get("entry", 0))

    if entry_price <= 0:
        log.warning("execute_signal_via_broker: no entry price for %s", signal.get("symbol"))
        return None

    # Position sizing: 10% of available capital (capped by MAX_SINGLE_TRADE_PCT)
    alloc_pct = min(0.10, broker.MAX_SINGLE_TRADE_PCT)
    alloc     = available_cash * alloc_pct
    qty       = max(1, int(alloc / entry_price))

    try:
        order = (
            OrderBuilder(broker)
            .from_signal(signal)
            .with_quantity_from_capital(available_cash, entry_price, alloc_pct)
            .with_product(ProductCode.CNC)      # delivery (change to MIS for intraday)
            .with_order_type(OrderType.MARKET)  # market entry (LIMIT in M2 upgrade)
            .with_validity(Validity.DAY)
            .build()
        )

        if order.status == OrderStatus.REJECTED:
            log.warning("execute_signal_via_broker: rejected %s — %s",
                        signal.get("symbol"), order.rejection_reason)
            return None

        log.info("🏦 BrokerOrder | %s %s×%s [%s] | T1=₹%.0f T2=₹%.0f SL=₹%.0f",
                 order.transaction.value if hasattr(order.transaction, 'value')
                 else order.transaction,
                 order.quantity, signal.get("symbol", ""),
                 order.order_id,
                 signal.get("target1", 0), signal.get("target2", 0),
                 signal.get("stop_loss", 0))

        return order.to_dict()

    except Exception as e:
        log.error("execute_signal_via_broker error for %s: %s", signal.get("symbol"), e)
        return None


def get_broker_instance() -> "PaperBroker":
    """Return the singleton PaperBroker for this process."""
    if not _BROKER_AVAILABLE:
        return None
    return get_broker(portfolio_file=PORTFOLIO_FILE, trades_file=TRADES_FILE)


# ── PUBLIC SAHI-STYLE API HELPERS ─────────────────────────────────────────────

def set_tsl_enabled(symbol: str, enabled: bool) -> dict:
    """Toggle Auto Trailing SL on an open position. Called from SAHI UI toggle."""
    portfolio = _load_portfolio()
    pos = portfolio["positions"].get(symbol)
    if not pos:
        return {"ok": False, "error": f"{symbol} not found in open positions"}
    pos["tsl_enabled"] = bool(enabled)
    _save_portfolio(portfolio)
    state = "ON" if enabled else "OFF"
    log.info("TSL %s for %s", state, symbol)
    return {"ok": True, "symbol": symbol, "tsl_enabled": enabled}


def quick_enter(symbol: str, action: str, entry_price: float,
                sl_pct: float = 2.0, target_pct: float = 4.0,
                alloc_pct: float = 5.0) -> dict:
    """
    SAHI-style 1-click paper trade entry.
    symbol     : e.g. "RELIANCE.NS"
    action     : "BUY" or "SELL"
    entry_price: CMP from price_cache
    sl_pct     : stop-loss distance % from entry (default 2%)
    target_pct : target % above entry for T1 (default 4%)
    alloc_pct  : % of available cash to deploy (default 5%)
    Returns position dict or error dict.
    """
    if LIVE_TRADING_ENABLED:
        return {"ok": False, "error": "Live trading is disabled"}

    portfolio = _load_portfolio()
    if symbol in portfolio["positions"]:
        return {"ok": False, "error": f"Position already open for {symbol}"}

    avail = portfolio["available_cash"]
    alloc = avail * (alloc_pct / 100.0)
    shares = max(1, int(alloc / entry_price))

    sl     = round(entry_price * (1 - sl_pct / 100), 2)
    t1     = round(entry_price * (1 + target_pct / 100), 2)
    t2     = round(entry_price * (1 + target_pct * 2 / 100), 2)

    signal = {
        "name":       symbol,
        "signal":     action,
        "price":      entry_price,
        "entry":      entry_price,
        "target1":    t1,
        "target2":    t2,
        "stop_loss":  sl,
        "score":      88,         # quick trade gets pass-through score
        "sector":     "Manual",
        "vol_surge":  1.5,
        "confidence": "MEDIUM",
    }

    # Minimal gate pass (override gates for manual quick-trade)
    pos = _enter_position(signal, gates_passed=6,
                          gate_detail={"manual_quick_trade": True},
                          portfolio=portfolio, price_cache={}, shared_state={})

    if pos:
        _save_portfolio(portfolio)
        log.info("🟢 QUICK ENTER: %s %s @ ₹%.2f | SL=₹%.2f T1=₹%.2f T2=₹%.2f",
                 action, symbol, entry_price, sl, t1, t2)
        return {"ok": True, "position": pos}
    return {"ok": False, "error": "Entry failed — check cash or duplicate position"}


def get_live_positions(price_cache: dict = None) -> list:
    """
    Return all open positions with live P&L calculated against price_cache.
    Used by the SAHI panel's live P&L table (refreshed every 30s).
    """
    portfolio = _load_portfolio()
    pc = price_cache or {}
    result = []
    for name, pos in portfolio["positions"].items():
        if pos.get("status") != "OPEN":
            continue
        cached = pc.get(name, {})
        cmp    = cached.get("price", 0)
        entry  = pos.get("entry_price", 0)
        shares = pos.get("shares_remaining", pos.get("shares", 0))
        unreal_pnl     = round((cmp - entry) * shares, 2) if cmp and entry else 0
        unreal_pnl_pct = round(((cmp - entry) / entry) * 100, 2) if cmp and entry else 0
        result.append({
            "symbol":       name,
            "shares":       shares,
            "entry_price":  entry,
            "cmp":          cmp,
            "target1":      pos.get("target1", 0),
            "target2":      pos.get("target2", 0),
            "stop_loss":    pos.get("stop_loss", 0),
            "trailing_sl":  pos.get("trailing_sl", 0),
            "tsl_enabled":  pos.get("tsl_enabled", True),
            "t1_booked":    pos.get("t1_booked", False),
            "unreal_pnl":   unreal_pnl,
            "unreal_pnl_pct": unreal_pnl_pct,
            "gates_passed": pos.get("gates_passed", 0),
            "entry_time":   pos.get("entry_time", ""),
            "signal_type":  pos.get("signal_type", "BUY"),
        })
    result.sort(key=lambda x: abs(x["unreal_pnl_pct"]), reverse=True)
    return result


def close_position_manual(symbol: str, price_cache: dict = None) -> dict:
    """Manually close an open position at current market price (SAHI exit button)."""
    portfolio = _load_portfolio()
    pos = portfolio["positions"].get(symbol)
    if not pos or pos.get("status") != "OPEN":
        return {"ok": False, "error": f"{symbol} not found in open positions"}
    pc    = price_cache or {}
    price = pc.get(symbol, {}).get("price") or pos.get("entry_price", 0)
    shares = pos.get("shares_remaining", pos.get("shares", 0))
    trades = _load_trades()
    sell_costs = _compute_costs(price, shares, "SELL")
    pnl     = round(((price * (1 - SLIPPAGE_PCT)) - pos["entry_price"]) * shares - sell_costs, 2)
    pnl_pct = round(((price - pos["entry_price"]) / pos["entry_price"]) * 100, 2) if pos["entry_price"] else 0
    _close_position(portfolio, symbol, "MANUAL_EXIT", price, shares, pnl, pnl_pct, trades)
    portfolio["positions"].pop(symbol, None)
    _rebuild_stats(portfolio)
    _update_daily_pnl(portfolio)
    _save_portfolio(portfolio)
    _save_trades(trades)
    log.info("🔴 MANUAL EXIT: %s @ ₹%.2f | P&L: ₹%.0f (%.1f%%)", symbol, price, pnl, pnl_pct)
    return {"ok": True, "symbol": symbol, "exit_price": price, "pnl": pnl, "pnl_pct": pnl_pct}


# ── MAIN AGENT ────────────────────────────────────────────────────────────────
def run(shared_state, price_cache=None):
    """
    Main paper trading cycle:
    1. Monitor existing positions (T1/T2/SL checks)
    2. Evaluate new signals for entry (8-gate filter)
    3. Execute entries for approved signals
    """
    # Double-check safety (paranoid but necessary)
    if LIVE_TRADING_ENABLED:
        log.critical("SAFETY VIOLATION: LIVE_TRADING_ENABLED was modified! Aborting.")
        return
    if not PAPER_TRADING_ONLY:
        log.critical("SAFETY VIOLATION: PAPER_TRADING_ONLY was modified! Aborting.")
        return

    portfolio = _load_portfolio()
    pc        = price_cache or shared_state.get("_price_cache", {})

    # ── STEP 1: Monitor existing positions ─────────────────────────────────────
    if pc:
        closed = _monitor_positions(portfolio, pc)
        if closed:
            log.info("PaperTrader: Closed %d positions", len(closed))

    # ── STEP 2: Update unrealized P&L ─────────────────────────────────────────
    unrealized = 0.0
    for name, pos in portfolio["positions"].items():
        if pos.get("status") != "OPEN":
            continue
        cached = pc.get(name, {})
        price  = cached.get("price", pos.get("entry_price", 0))
        unrealized += (price - pos["entry_price"]) * pos.get("shares_remaining", 0)
    portfolio["unrealized_pnl"] = round(unrealized, 2)
    _update_daily_pnl(portfolio)

    # ── STEP 3: Daily loss circuit breaker (R15) ───────────────────────────────
    if portfolio["daily_pnl_pct"] <= -3.0:
        log.warning("⛔ PaperTrader: DAILY LOSS CIRCUIT (-%.1f%%) — No new entries today",
                    abs(portfolio["daily_pnl_pct"]))
        _save_portfolio(portfolio)
        shared_state["paper_portfolio"] = portfolio
        return portfolio

    # ── STEP 4: Check VIX (R14) ────────────────────────────────────────────────
    vix_data   = shared_state.get("index_prices", {}).get("INDIA VIX", {})
    vix_price  = vix_data.get("price") if vix_data else None
    if vix_price and vix_price > 25:
        log.warning("⛔ PaperTrader: VIX=%.1f > 25 — No new entries (R14)", vix_price)
        _save_portfolio(portfolio)
        shared_state["paper_portfolio"] = portfolio
        return portfolio

    # ── STEP 5: Check max simultaneous positions (R13) ─────────────────────────
    open_count = len([p for p in portfolio["positions"].values() if p.get("status") == "OPEN"])
    if open_count >= 5:
        log.info("PaperTrader: Max positions reached (%d/5) — no new entries", open_count)
        _save_portfolio(portfolio)
        shared_state["paper_portfolio"] = portfolio
        return portfolio

    # ── STEP 6: Evaluate new signals ──────────────────────────────────────────
    # Priority: use risk_reviewed_signals (have been through risk_manager)
    candidate_signals = shared_state.get("risk_reviewed_signals", [])
    if not candidate_signals:
        candidate_signals = shared_state.get("actionable_signals", [])

    # Also respect Claude's execute_paper_trade flag
    claude_analysis = shared_state.get("claude_analysis", {})
    claude_picks    = {p["name"]: p for p in claude_analysis.get("conviction_picks", [])}

    new_entries = 0
    for sig in candidate_signals:
        name = sig.get("name", "")

        # Skip if already in portfolio
        if name in portfolio["positions"] and portfolio["positions"][name].get("status") == "OPEN":
            continue

        # Must have price data
        if not pc.get(name, {}).get("price"):
            continue

        # Check risk_manager approval
        risk     = sig.get("risk", {})
        approved = risk.get("approved", False)

        # Check Claude's conviction flag (if Claude ran)
        claude_pick  = claude_picks.get(name, {})
        claude_says  = claude_pick.get("execute_paper_trade", None)

        # If Claude explicitly says NO — skip (override risk_manager)
        if claude_says is False:
            log.info("PaperTrader: %s skipped — Claude says no execute", name)
            continue

        # If risk_manager rejected AND Claude didn't explicitly approve — skip
        if not approved and claude_says is not True:
            continue

        # ── Run 8-gate conviction check ────────────────────────────────────
        gates_passed, gate_detail, rejection_reasons = _check_gates(sig, shared_state)

        if gates_passed < 6:
            log.info("PaperTrader: %s REJECTED (gates %d/8) — %s",
                     name, gates_passed, "; ".join(rejection_reasons[:2]))
            continue

        # ── CHECK MARKET HOURS (only enter during market hours) ────────────
        now_hour = datetime.now().hour
        now_min  = datetime.now().minute
        market_open  = (now_hour > 9 or (now_hour == 9 and now_min >= 15))
        market_close = (now_hour < 15 or (now_hour == 15 and now_min <= 25))

        if not (market_open and market_close):
            log.info("PaperTrader: %s — outside market hours, queuing for next session", name)
            continue

        # ── EXECUTE PAPER ENTRY ────────────────────────────────────────────
        pos = _enter_position(sig, gates_passed, gate_detail, portfolio, pc, shared_state)
        if pos:
            new_entries += 1
            open_count  += 1
            if open_count >= 5:
                break  # max positions reached

    # ── SAVE STATE ────────────────────────────────────────────────────────────
    _save_portfolio(portfolio)
    shared_state["paper_portfolio"] = portfolio

    # ── BROKER CONNECTOR TICK (process SL/T1/T2 via terminal-grade engine) ───
    if _BROKER_AVAILABLE and pc:
        try:
            broker = get_broker_instance()
            changed_orders = broker.tick(pc)
            if changed_orders:
                # Merge broker's portfolio snapshot into shared_state
                broker_snap = broker.portfolio_snapshot()
                shared_state["paper_portfolio"].update({
                    "broker_order_count": len(broker.get_order_book()),
                    "broker_open_orders": broker_snap.get("open_orders", 0),
                    "broker_realised_pnl": broker_snap.get("realised_pnl", 0),
                })
            shared_state["broker_order_book"] = [
                o.to_dict() for o in broker.get_order_book()[-20:]  # last 20
            ]
        except Exception as _be:
            log.warning("Broker tick failed (non-fatal): %s", _be)

    total_val = (portfolio["capital"] + portfolio["realized_pnl"] + portfolio["unrealized_pnl"])
    log.info(
        "✅ PaperTrader: [SIMULATION ONLY] Positions=%d | New entries=%d | "
        "Portfolio ₹%.0f | Realized P&L ₹%+.0f | Unrealized ₹%+.0f | "
        "Win rate %.0f%%",
        len([p for p in portfolio["positions"].values() if p.get("status") == "OPEN"]),
        new_entries,
        total_val,
        portfolio["realized_pnl"],
        portfolio["unrealized_pnl"],
        portfolio["stats"].get("win_rate", 0) * 100,
    )
    return portfolio
