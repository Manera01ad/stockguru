"""
AGENT 4 — TECHNICAL ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Compute RSI(14), MACD(12,26,9), Bollinger Bands(20,2),
          EMA(20/50/200), ATR(14), Pivot Points (Classic),
          Swing Low detection — IIFL-style entry/exit zones.
Runs    : Every 15 minutes (after market_scanner)
Cost    : Zero — pure math on Yahoo Finance OHLCV data
Reports : Feeds claude_intelligence + trade_signal + paper_trader
"""

import requests
import time
import logging
from datetime import datetime

log = logging.getLogger("TechnicalAnalysis")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def _ema(prices, period):
    if len(prices) < period:
        return None
    k   = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 2)

def _sma(prices, period):
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)

def _rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs  = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def _macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return None, None, None
    ema_fast, ema_slow = [], []
    k_fast = 2 / (fast + 1)
    k_slow = 2 / (slow + 1)
    ef = sum(prices[:fast]) / fast
    es = sum(prices[:slow]) / slow
    for p in prices[fast:slow]:
        ef = p * k_fast + ef * (1 - k_fast)
    for p in prices[slow:]:
        ef = p * k_fast + ef * (1 - k_fast)
        es = p * k_slow + es * (1 - k_slow)
        ema_fast.append(ef)
        ema_slow.append(es)
    macd_line = [round(f - s, 4) for f, s in zip(ema_fast, ema_slow)]
    if len(macd_line) < signal:
        return None, None, None
    k_sig   = 2 / (signal + 1)
    sig_ema = sum(macd_line[:signal]) / signal
    for m in macd_line[signal:]:
        sig_ema = m * k_sig + sig_ema * (1 - k_sig)
    hist = round(macd_line[-1] - sig_ema, 4)
    return round(macd_line[-1], 4), round(sig_ema, 4), hist

def _bollinger(prices, period=20, std_mult=2):
    if len(prices) < period:
        return None, None, None
    window = prices[-period:]
    mid    = sum(window) / period
    std    = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
    upper  = round(mid + std_mult * std, 2)
    lower  = round(mid - std_mult * std, 2)
    return upper, round(mid, 2), lower

def _atr(highs, lows, closes, period=14):
    """Average True Range — Wilder smoothing. Measures daily volatility."""
    if len(closes) < period + 1 or len(highs) < period + 1:
        return None
    # Align arrays to same length
    n = min(len(highs), len(lows), len(closes))
    highs, lows, closes = highs[-n:], lows[-n:], closes[-n:]
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1])
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 2)

def _pivot_points(prev_high, prev_low, prev_close):
    """
    Classic Pivot Points using PREVIOUS day's H/L/C.
    PP  = (H + L + C) / 3
    R1  = 2*PP - L   ← first resistance (IIFL T1 target zone)
    R2  = PP + (H-L) ← second resistance (IIFL T2 target zone)
    S1  = 2*PP - H   ← first support (IIFL entry zone lower)
    S2  = PP - (H-L) ← second support (strong support)
    """
    pp = round((prev_high + prev_low + prev_close) / 3, 2)
    r1 = round(2 * pp - prev_low,  2)
    r2 = round(pp + (prev_high - prev_low), 2)
    s1 = round(2 * pp - prev_high, 2)
    s2 = round(pp - (prev_high - prev_low), 2)
    return {"pp": pp, "r1": r1, "r2": r2, "s1": s1, "s2": s2}

def _swing_low(lows, lookback=10):
    """
    Most recent swing low = lowest low in last N candles.
    IIFL places SL just below this level.
    """
    if not lows or len(lows) < lookback:
        return None
    recent = [l for l in lows[-lookback:] if l is not None]
    if not recent:
        return None
    return round(min(recent), 2)

def _swing_high(highs, lookback=10):
    """Most recent swing high = highest high in last N candles."""
    if not highs or len(highs) < lookback:
        return None
    recent = [h for h in highs[-lookback:] if h is not None]
    if not recent:
        return None
    return round(max(recent), 2)

def _iifl_entry_zone(pivot_pp, price):
    """
    IIFL 5-7% Rule:
    Ideal entry = within 5-7% ABOVE the pivot breakout.
    If price is already above pivot by >7%, it's 'chasing' — avoid.
    Entry zone: [pivot, pivot * 1.07]
    """
    entry_low  = round(pivot_pp, 2)
    entry_high = round(pivot_pp * 1.07, 2)
    pct_above  = round(((price - pivot_pp) / pivot_pp) * 100, 1) if pivot_pp else 0
    chasing    = pct_above > 7.0
    return entry_low, entry_high, pct_above, chasing

# ── PRICE HISTORY FETCH ───────────────────────────────────────────────────────
def fetch_ohlcv(symbol, days=60):
    """Fetch daily OHLCV from Yahoo Finance (60 days for all indicators)."""
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
               f"?interval=1d&range=3mo")
        r   = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        d   = r.json()
        res = d["chart"]["result"][0]
        q   = res["indicators"]["quote"][0]
        closes  = [c for c in q.get("close",  []) if c is not None]
        highs   = [h for h in q.get("high",   []) if h is not None]
        lows    = [l for l in q.get("low",    []) if l is not None]
        volumes = [v for v in q.get("volume", []) if v is not None]
        return closes, highs, lows, volumes
    except Exception as e:
        log.debug("OHLCV fetch failed %s: %s", symbol, e)
        return [], [], [], []

# ── INTERPRET INDICATORS ──────────────────────────────────────────────────────
def _interpret(rsi, macd_line, macd_sig, macd_hist, price, bb_upper, bb_lower, bb_mid,
               ema20, ema50, ema200):
    signals     = []
    gates       = {}

    if rsi is not None:
        gates["rsi_gate"] = 35 <= rsi <= 68
        if rsi < 30:    signals.append("OVERSOLD BOUNCE")
        elif rsi < 42:  signals.append("RSI-dip entry")
        elif rsi > 72:  signals.append("OVERBOUGHT-avoid")
    else:
        gates["rsi_gate"] = None

    if macd_line is not None and macd_sig is not None:
        bullish_macd       = macd_line > macd_sig
        gates["macd_gate"] = bullish_macd
        if bullish_macd and macd_hist and macd_hist > 0:
            signals.append("MACD-bullish")
        elif not bullish_macd:
            signals.append("MACD-bearish")
    else:
        gates["macd_gate"] = None

    if ema50 and price:
        gates["trend_gate"] = price > ema50
        if price > ema50:   signals.append("above-EMA50")
        else:               signals.append("below-EMA50-caution")
    else:
        gates["trend_gate"] = None

    if ema50 and ema200:
        if ema50 > ema200:  signals.append("GOLDEN-CROSS")
        else:               signals.append("death-cross")

    if bb_upper and bb_lower and price:
        bb_width = round(((bb_upper - bb_lower) / bb_mid) * 100, 1) if bb_mid else None
        if price >= bb_upper * 0.99:    signals.append("BB-upper-resistance")
        elif price <= bb_lower * 1.01:  signals.append("BB-lower-support")
        if bb_width and bb_width < 3:   signals.append("BB-squeeze-brewing")
    return signals, gates

# ── MAIN AGENT ────────────────────────────────────────────────────────────────
def run(shared_state):
    """Compute technical indicators + IIFL-style levels for top scanner stocks."""
    scanner = shared_state.get("scanner_results", [])
    if not scanner:
        log.warning("TechnicalAnalysis: No scanner results — skipping")
        shared_state["technical_data"] = {}
        return {}

    stocks_to_analyze = scanner[:12]
    log.info("📊 TechnicalAnalysis: Analyzing %d stocks (incl. ATR + Pivots)...", len(stocks_to_analyze))

    technical_data = {}

    for stock in stocks_to_analyze:
        name = stock["name"]
        sym  = stock.get("sym", stock.get("symbol", ""))
        if not sym:
            continue

        closes, highs, lows, volumes = fetch_ohlcv(sym)
        if len(closes) < 30:
            log.debug("  %s: insufficient history (%d days)", name, len(closes))
            continue

        price = closes[-1]

        # ── Core indicators ──────────────────────────────────────────────────
        rsi_val          = _rsi(closes)
        macd_l, macd_s, macd_h = _macd(closes)
        bb_u, bb_m, bb_l = _bollinger(closes)
        ema20_v  = _ema(closes, 20)
        ema50_v  = _ema(closes, 50)
        ema200_v = _ema(closes, 200) if len(closes) >= 200 else None

        # ── NEW: ATR, Pivot Points, Swing Low ─────────────────────────────
        atr_val    = _atr(highs, lows, closes, period=14)
        swing_low  = _swing_low(lows,  lookback=10)
        swing_high = _swing_high(highs, lookback=10)

        # Pivot uses PREVIOUS day's data (index -2)
        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            pivots = _pivot_points(highs[-2], lows[-2], closes[-2])
        else:
            pivots = None

        # ── IIFL Entry Zone (pivot-based) ────────────────────────────────
        if pivots:
            entry_low_iifl, entry_high_iifl, pct_above_pivot, chasing = \
                _iifl_entry_zone(pivots["pp"], price)
        else:
            entry_low_iifl  = round(price * 0.98, 2)
            entry_high_iifl = round(price * 1.02, 2)
            pct_above_pivot = 0
            chasing         = False

        # ── Stop Loss: swing low preferred, else ATR-based, else 8% ─────
        if swing_low and swing_low < price:
            sl_iifl      = round(swing_low * 0.995, 2)  # just below swing low
            sl_method    = "Swing Low"
        elif atr_val:
            sl_iifl      = round(price - 1.5 * atr_val, 2)
            sl_method    = "1.5×ATR"
        else:
            sl_iifl      = round(price * 0.92, 2)
            sl_method    = "8% Fixed"

        # ── Targets: R1 and R2 from pivot, else ATR-projected ────────────
        if pivots and pivots["r1"] > price:
            t1_iifl   = pivots["r1"]
            t2_iifl   = pivots["r2"]
            t_method  = "Pivot R1/R2"
        elif atr_val:
            t1_iifl   = round(price + 3 * atr_val, 2)
            t2_iifl   = round(price + 5 * atr_val, 2)
            t_method  = "3×/5×ATR"
        else:
            t1_iifl   = round(price * 1.12, 2)
            t2_iifl   = round(price * 1.22, 2)
            t_method  = "Fixed %"

        # ── Risk/Reward ──────────────────────────────────────────────────
        risk   = abs(price - sl_iifl)
        rr_t1  = round(abs(t1_iifl - price) / risk, 2) if risk > 0 else 0
        rr_t2  = round(abs(t2_iifl - price) / risk, 2) if risk > 0 else 0

        # ── ATR as % of price (volatility indicator) ─────────────────────
        atr_pct = round((atr_val / price) * 100, 2) if atr_val and price else None

        signals_list, gate_results = _interpret(
            rsi_val, macd_l, macd_s, macd_h,
            price, bb_u, bb_l, bb_m,
            ema20_v, ema50_v, ema200_v
        )

        tech_score = 50
        if gate_results.get("rsi_gate"):    tech_score += 10
        if gate_results.get("macd_gate"):   tech_score += 15
        if gate_results.get("trend_gate"):  tech_score += 15
        if rsi_val and 40 <= rsi_val <= 60: tech_score += 10
        if ema50_v and ema200_v and ema50_v > ema200_v: tech_score += 10
        tech_score = min(100, tech_score)

        technical_data[name] = {
            # ── Identity ───────────────────────────────────────────────
            "symbol":        sym,
            "price":         price,
            # ── Core indicators ────────────────────────────────────────
            "rsi":           rsi_val,
            "macd_line":     macd_l,
            "macd_signal":   macd_s,
            "macd_hist":     macd_h,
            "macd_bullish":  (macd_l or 0) > (macd_s or 0),
            "bb_upper":      bb_u,
            "bb_mid":        bb_m,
            "bb_lower":      bb_l,
            "ema20":         ema20_v,
            "ema50":         ema50_v,
            "ema200":        ema200_v,
            "above_ema20":   bool(ema20_v  and price > ema20_v),
            "above_ema50":   bool(ema50_v  and price > ema50_v),
            "above_ema200":  bool(ema200_v and price > ema200_v),
            "golden_cross":  bool(ema50_v and ema200_v and ema50_v > ema200_v),
            # ── NEW: ATR ───────────────────────────────────────────────
            "atr":           atr_val,
            "atr_pct":       atr_pct,
            # ── NEW: Pivot Points ──────────────────────────────────────
            "pivot_pp":      pivots["pp"]  if pivots else None,
            "pivot_r1":      pivots["r1"]  if pivots else None,
            "pivot_r2":      pivots["r2"]  if pivots else None,
            "pivot_s1":      pivots["s1"]  if pivots else None,
            "pivot_s2":      pivots["s2"]  if pivots else None,
            # ── NEW: Swing levels ──────────────────────────────────────
            "swing_low":     swing_low,
            "swing_high":    swing_high,
            # ── NEW: IIFL-style entry/exit zones ──────────────────────
            "entry_low":     entry_low_iifl,
            "entry_high":    entry_high_iifl,
            "pct_above_pivot": pct_above_pivot,
            "chasing":       chasing,
            "stop_loss":     sl_iifl,
            "sl_method":     sl_method,
            "target1":       t1_iifl,
            "target2":       t2_iifl,
            "target_method": t_method,
            "rr_t1":         rr_t1,
            "rr_t2":         rr_t2,
            # ── Score & signals ────────────────────────────────────────
            "tech_score":    tech_score,
            "signals":       signals_list,
            "gates":         gate_results,
            "analyzed_at":   datetime.now().strftime("%H:%M:%S"),
        }

        log.info("  ✅ %s | RSI=%.1f | ATR=%.2f(%.1f%%) | Pivot=%.1f | Entry=%.1f-%.1f | T1=%.1f | SL=%.1f [%s]",
                 name,
                 rsi_val or 0,
                 atr_val or 0, atr_pct or 0,
                 pivots["pp"] if pivots else 0,
                 entry_low_iifl, entry_high_iifl,
                 t1_iifl,
                 sl_iifl, sl_method)

        time.sleep(0.3)

    shared_state["technical_data"]     = technical_data
    shared_state["technical_last_run"] = datetime.now().strftime("%d %b %H:%M:%S")
    log.info("✅ TechnicalAnalysis: %d stocks analyzed with IIFL-style levels", len(technical_data))
    return technical_data
