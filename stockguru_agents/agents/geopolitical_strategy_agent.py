"""
AGENT — GEOPOLITICAL STRATEGY ANALYSER
═══════════════════════════════════════════════════════════════════════════════
Goal    : Analyse 8 trading strategies across 4 categories in the context of
          high-volatility geopolitical markets (e.g., Iran-US conflict, 2026).
          Returns per-strategy signals (ACTIVE / WATCH / AVOID / NEUTRAL) with
          plain-English reasoning and a summary narrative.

Categories:
  1. Directional  — Bull Call/Bear Put Spread, Momentum Breakout
  2. Non-Directional (Volatility) — Long Straddle, 9:20 Short Straddle
  3. Hedging — Protective Put, Zero-Cost Collar
  4. Statistical — Mean Reversion (BB), Cash-Futures Arbitrage

Input   : shared_state (from previous agents) OR standalone HTTP call
Output  : dict with 'signals', 'analysis', 'top_picks', 'market_context'
═══════════════════════════════════════════════════════════════════════════════
"""

import logging
import math
from datetime import datetime

log = logging.getLogger("GeopoliticalStrategyAgent")

# ── STATUS CONSTANTS ──────────────────────────────────────────────────────────
ACTIVE  = "ACTIVE"   # ✅ Good conditions — consider this strategy NOW
WATCH   = "WATCH"    # ⚠️  Conditions partially met — monitor, not yet trade
AVOID   = "AVOID"    # ❌ Conditions wrong — high chance of loss
NEUTRAL = "NEUTRAL"  # ○  No clear signal in either direction


# ═════════════════════════════════════════════════════════════════════════════
# CATEGORY 1: DIRECTIONAL STRATEGIES
# ═════════════════════════════════════════════════════════════════════════════

def _analyse_bull_call_spread(tech_data: dict, vix: float, trend: str) -> dict:
    """
    Bull Call Spread: Buy ATM Call + Sell OTM Call
    Best when: mild recovery expected, VIX cooling, clear uptrend forming.
    Worst when: VIX very high (premiums expensive) or strong downtrend.
    """
    reasons = []
    score = 0

    # VIX check — high VIX makes options expensive (bad for buying spreads)
    if vix is None:
        vix = 18.0  # assume elevated if unknown
    if vix < 15:
        score += 2; reasons.append(f"VIX {vix:.1f} is low — options are cheap ✅")
    elif vix < 20:
        score += 1; reasons.append(f"VIX {vix:.1f} is moderate — spread viable ⚠️")
    else:
        score -= 1; reasons.append(f"VIX {vix:.1f} is high — premiums expensive, spread costly ⚠️")

    # Trend check
    ema50  = tech_data.get("ema50")
    ema200 = tech_data.get("ema200")
    price  = tech_data.get("price")
    if ema50 and ema200 and price:
        if ema50 > ema200:
            score += 2; reasons.append("Golden Cross active (EMA50 > EMA200) — bullish trend ✅")
        elif price > ema50:
            score += 1; reasons.append("Price above EMA50 — short-term bullish ⚠️")
        else:
            score -= 1; reasons.append("Price below EMA50 — downtrend, wait for recovery ❌")

    # RSI check
    rsi = tech_data.get("rsi")
    if rsi:
        if 45 < rsi < 65:
            score += 1; reasons.append(f"RSI {rsi:.1f} in healthy range (45-65) ✅")
        elif rsi > 70:
            score -= 1; reasons.append(f"RSI {rsi:.1f} overbought — don't buy calls now ❌")
        elif rsi < 35:
            score += 1; reasons.append(f"RSI {rsi:.1f} oversold — potential bounce for bull spread ⚠️")

    if score >= 3:
        status = ACTIVE
        advice = "Buy ATM CE + Sell OTM+200 CE. Risk = net debit paid. Target = OTM strike."
    elif score >= 1:
        status = WATCH
        advice = "Wait for VIX to cool below 18 and EMA50 to cross above EMA200."
    else:
        status = AVOID
        advice = "High VIX + downtrend = expensive spreads with low win probability."

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


def _analyse_momentum_breakout(tech_data: dict, vix: float) -> dict:
    """
    Momentum Breakout: Buy Nifty/BankNifty Future if it breaks the first
    15-minute candle HIGH with volume > 1.5× 5-day average.
    Best for: War rebound days, gap-up openings, news-driven surges.
    """
    reasons = []
    score = 0

    # High VIX = bigger moves = better for breakout strategies
    if vix and vix > 18:
        score += 2; reasons.append(f"VIX {vix:.1f} elevated — large intraday moves expected ✅")
    elif vix and vix > 14:
        score += 1; reasons.append(f"VIX {vix:.1f} moderate — some intraday volatility ⚠️")

    # Volume spike check
    vol_ratio = tech_data.get("volume_ratio", 1.0)  # current vol / 5-day avg
    if vol_ratio >= 1.5:
        score += 3; reasons.append(f"Volume {vol_ratio:.1f}× avg — strong breakout signal ✅")
    elif vol_ratio >= 1.2:
        score += 1; reasons.append(f"Volume {vol_ratio:.1f}× avg — moderate participation ⚠️")
    else:
        score -= 1; reasons.append(f"Volume only {vol_ratio:.1f}× avg — breakout may be weak ❌")

    # Check if price is near recent high (potential breakout zone)
    price = tech_data.get("price", 0)
    day_high = tech_data.get("day_high", 0)
    if price and day_high and day_high > 0:
        pct_from_high = ((day_high - price) / day_high) * 100
        if pct_from_high < 0.3:
            score += 2; reasons.append(f"Price within 0.3% of day high — breakout imminent ✅")
        elif pct_from_high < 1.0:
            score += 1; reasons.append(f"Price {pct_from_high:.1f}% from day high — watch for break ⚠️")

    if score >= 4:
        status = ACTIVE
        advice = "Buy Future on 15-min high breakout. SL = 15-min candle low. Target = 2× range."
    elif score >= 2:
        status = WATCH
        advice = "Monitor 9:30 AM volume spike. Set alert at 15-min candle high."
    else:
        status = NEUTRAL
        advice = "No breakout setup visible. Skip today."

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


# ═════════════════════════════════════════════════════════════════════════════
# CATEGORY 2: NON-DIRECTIONAL (VOLATILITY) STRATEGIES
# ═════════════════════════════════════════════════════════════════════════════

def _analyse_long_straddle(tech_data: dict, vix: float, geopolitical_risk: float) -> dict:
    """
    Long Straddle: Buy ATM Call + ATM Put simultaneously.
    Profits from ANY large move. Perfect for war-news events.
    Risk: time decay (theta) kills the trade if market stays sideways.
    """
    reasons = []
    score = 0

    # VIX is the key indicator — but counter-intuitive:
    # HIGH VIX = options expensive (pays off only with VERY large moves)
    # MODERATE VIX (15-22) = sweet spot for straddles
    if vix:
        if 15 <= vix <= 22:
            score += 3; reasons.append(f"VIX {vix:.1f} in sweet spot (15-22) for straddle ✅")
        elif vix > 22:
            score += 1; reasons.append(f"VIX {vix:.1f} very high — straddle expensive, needs massive move ⚠️")
        else:
            score -= 1; reasons.append(f"VIX {vix:.1f} too low — market calm, straddle loses theta ❌")

    # Geopolitical risk multiplier (0 = low, 1 = extreme)
    if geopolitical_risk > 0.7:
        score += 3; reasons.append(f"Geopolitical risk EXTREME ({geopolitical_risk:.0%}) — straddle ideal ✅")
    elif geopolitical_risk > 0.4:
        score += 2; reasons.append(f"Geopolitical risk HIGH ({geopolitical_risk:.0%}) — big moves likely ✅")
    elif geopolitical_risk > 0.2:
        score += 1; reasons.append(f"Geopolitical risk moderate ({geopolitical_risk:.0%}) ⚠️")

    # Bollinger Band width (wide bands = volatile = good for straddle)
    bb_width = tech_data.get("bb_width_pct", 2.0)
    if bb_width > 4.0:
        score += 2; reasons.append(f"BB width {bb_width:.1f}% — volatility expanding ✅")
    elif bb_width > 2.5:
        score += 1; reasons.append(f"BB width {bb_width:.1f}% — moderate expansion ⚠️")

    if score >= 5:
        status = ACTIVE
        advice = ("Buy ATM CE + ATM PE before next major news event. "
                  "Target: 1.5× debit paid. Exit on large candle — don't hold overnight.")
    elif score >= 3:
        status = WATCH
        advice = "Wait for confirmed VIX spike above 18 or an upcoming news catalyst."
    elif score >= 1:
        status = NEUTRAL
        advice = "Marginal setup — consider a cheaper Strangle instead."
    else:
        status = AVOID
        advice = "Low volatility market — straddle will lose to time decay."

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


def _analyse_short_straddle_9_20(tech_data: dict, vix: float, geopolitical_risk: float) -> dict:
    """
    9:20 Short Straddle: Sell ATM Call + ATM Put at 9:20 AM.
    Captures theta decay. EXTREMELY DANGEROUS in war/high-VIX markets.
    Auto-exit rule: if price moves 0.5% in first 5 minutes → exit immediately.
    """
    reasons = []
    score = 0

    # THIS STRATEGY IS A SELL STRATEGY — high VIX = bad (option seller loses)
    if vix:
        if vix < 12:
            score += 4; reasons.append(f"VIX {vix:.1f} very low — excellent for short straddle ✅")
        elif vix < 14:
            score += 2; reasons.append(f"VIX {vix:.1f} low — good theta capture environment ✅")
        elif vix < 18:
            score += 0; reasons.append(f"VIX {vix:.1f} moderate — marginal short straddle conditions ⚠️")
        else:
            score -= 4; reasons.append(f"VIX {vix:.1f} HIGH — NEVER sell straddles in war market ❌")

    # Geopolitical risk is a DISQUALIFIER for this strategy
    if geopolitical_risk > 0.5:
        score -= 4; reasons.append(f"Geopolitical risk {geopolitical_risk:.0%} — overnight gaps WILL blow straddle ❌")
    elif geopolitical_risk > 0.2:
        score -= 2; reasons.append(f"Elevated geopolitical risk — short straddle risky ⚠️")

    # Recent gap check — large gap = dangerous for sellers
    gap_pct = tech_data.get("gap_pct", 0)
    if abs(gap_pct) > 1.5:
        score -= 3; reasons.append(f"Today's gap was {gap_pct:+.1f}% — market is gapping, avoid selling ❌")
    elif abs(gap_pct) > 0.5:
        score -= 1; reasons.append(f"Gap of {gap_pct:+.1f}% at open — caution for option sellers ⚠️")
    else:
        score += 1; reasons.append(f"Flat open (gap {gap_pct:+.1f}%) — good for 9:20 straddle ✅")

    if score >= 4:
        status = ACTIVE
        advice = ("Sell ATM CE + ATM PE at 9:20 AM. "
                  "MANDATORY AUTO-EXIT: if price moves >0.5% in 5 min, exit immediately.")
    elif score >= 2:
        status = WATCH
        advice = "Conditions borderline. Only trade if no news events scheduled today."
    else:
        status = AVOID
        advice = ("⚠️ WAR MARKET — DO NOT SELL OPTIONS. "
                  "Overnight gap risk will destroy short straddle positions instantly.")

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


# ═════════════════════════════════════════════════════════════════════════════
# CATEGORY 3: HEDGING STRATEGIES
# ═════════════════════════════════════════════════════════════════════════════

def _analyse_protective_put(tech_data: dict, vix: float, geopolitical_risk: float,
                             has_open_positions: bool) -> dict:
    """
    Protective Put: Long Future + Buy OTM/ATM Put Option.
    Acts as portfolio insurance. ALWAYS relevant in geopolitical markets.
    """
    reasons = []
    score = 0

    # If geopolitical risk is elevated, this is ALWAYS worth considering
    if geopolitical_risk > 0.6:
        score += 4; reasons.append(f"⚠️ EXTREME geopolitical risk — protect all long positions NOW ✅")
    elif geopolitical_risk > 0.3:
        score += 3; reasons.append(f"High geopolitical risk — protective put recommended ✅")
    elif geopolitical_risk > 0.1:
        score += 1; reasons.append(f"Moderate geopolitical risk — consider protection ⚠️")

    # Open positions — protective put is only relevant if holding positions
    if has_open_positions:
        score += 2; reasons.append("Open positions detected — insurance is critical ✅")
    else:
        score -= 1; reasons.append("No open long positions — protective put not needed ○")

    # VIX check — higher VIX = puts are expensive, but the protection is NEEDED MORE
    if vix and vix > 20:
        score += 1; reasons.append(f"VIX {vix:.1f} high — expensive puts, but downside risk justifies cost ⚠️")
    elif vix and vix < 14:
        score -= 1; reasons.append(f"VIX {vix:.1f} low — puts are cheap, good time to buy insurance ✅")

    if score >= 4:
        status = ACTIVE
        advice = ("Buy ATM or 1% OTM Put for your holding period. "
                  "Cost = premium paid. Downside = capped at strike price.")
    elif score >= 2:
        status = WATCH
        advice = "Consider buying a Put if you're holding overnight in a news-heavy week."
    else:
        status = NEUTRAL
        advice = "Low geopolitical risk — full protective put may not be cost-effective."

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


def _analyse_collar(tech_data: dict, vix: float, geopolitical_risk: float,
                    has_open_positions: bool) -> dict:
    """
    Zero-Cost Collar: Long Future + Buy OTM Put (downside protection)
                     + Sell OTM Call (funds the put premium).
    Creates a profit bracket at near-zero net cost.
    """
    reasons = []
    score = 0

    if has_open_positions:
        score += 2; reasons.append("Existing long position — collar provides zero-cost protection ✅")

    if geopolitical_risk > 0.4:
        score += 3; reasons.append(f"High geopolitical risk {geopolitical_risk:.0%} — collar locks in profit bracket ✅")

    # VIX check — higher VIX = better call premium received (funds the put cheaply)
    if vix and vix > 18:
        score += 2; reasons.append(f"VIX {vix:.1f} — call premium high, puts are cheap to buy ✅")
    elif vix and vix > 14:
        score += 1; reasons.append(f"VIX {vix:.1f} — reasonable premium on both sides ⚠️")

    # Price trend — collar makes sense if you're in profit and want to protect gains
    price  = tech_data.get("price", 0)
    ema50  = tech_data.get("ema50", 0)
    if price and ema50 and price > ema50 * 1.02:
        score += 1; reasons.append("Price 2%+ above EMA50 — good time to lock in gains with collar ✅")

    if score >= 5:
        status = ACTIVE
        advice = ("Buy OTM-2% Put + Sell OTM+3% Call. Net premium ≈ ₹0. "
                  "Your max gain = +3%, max loss = -2% from current price.")
    elif score >= 3:
        status = WATCH
        advice = "Good strategy if you want to protect an existing profitable long position."
    else:
        status = NEUTRAL
        advice = "No open positions to protect. Not applicable currently."

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


# ═════════════════════════════════════════════════════════════════════════════
# CATEGORY 4: MEAN REVERSION & ARBITRAGE
# ═════════════════════════════════════════════════════════════════════════════

def _analyse_mean_reversion(tech_data: dict, vix: float) -> dict:
    """
    Mean Reversion (Bollinger Bands): Buy when price is ≥2 SD below mean.
    "Market crashed too hard, too fast — expect a bounce."
    """
    reasons = []
    score = 0

    price  = tech_data.get("price", 0)
    bb_lower = tech_data.get("bb_lower", 0)
    bb_upper = tech_data.get("bb_upper", 0)
    bb_mid   = tech_data.get("bb_mid", 0)
    rsi    = tech_data.get("rsi", 50)

    # BB position check
    if price and bb_lower and price < bb_lower:
        score += 4; reasons.append(f"Price ₹{price:.0f} BELOW lower BB (₹{bb_lower:.0f}) — oversold, bounce setup ✅")
    elif price and bb_lower and price < bb_lower * 1.005:
        score += 2; reasons.append(f"Price near lower BB — watch for bounce ⚠️")
    elif price and bb_mid and price < bb_mid:
        score += 0; reasons.append(f"Price below BB midline — mild bearish bias ○")

    # RSI confirmation
    if rsi and rsi < 30:
        score += 3; reasons.append(f"RSI {rsi:.1f} deeply oversold — strong mean reversion signal ✅")
    elif rsi and rsi < 40:
        score += 1; reasons.append(f"RSI {rsi:.1f} oversold — potential bounce ⚠️")
    elif rsi and rsi > 70:
        score -= 2; reasons.append(f"RSI {rsi:.1f} overbought — do NOT buy here ❌")

    # VIX context — high VIX = violent overshoots = better mean reversion opportunities
    if vix and vix > 20:
        score += 1; reasons.append(f"High VIX {vix:.1f} — war-induced overshoots create BB bounce opportunities ✅")

    if score >= 5:
        status = ACTIVE
        advice = ("BUY at lower BB level. SL = 2% below entry. Target = BB midline. "
                  "Use small position size (max 30% of normal) — bounces can fail in war markets.")
    elif score >= 3:
        status = WATCH
        advice = "Price approaching lower BB. Wait for RSI < 35 confirmation before entry."
    elif score >= 1:
        status = NEUTRAL
        advice = "Partial setup — wait for price to reach lower BB band."
    else:
        status = AVOID
        advice = "No mean reversion opportunity. Price not near BB extremes."

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


def _analyse_cash_futures_arb(tech_data: dict) -> dict:
    """
    Cash-Futures Arbitrage: Buy cash market + Sell futures when spread > fair value.
    Near risk-free if held to expiry. Best near expiry dates.
    """
    reasons = []
    score = 0

    # Futures premium (annualised spread above spot)
    futures_premium_pct = tech_data.get("futures_premium_pct", 0.3)
    days_to_expiry = tech_data.get("days_to_expiry", 15)

    # Calculate annualised premium
    if days_to_expiry > 0 and futures_premium_pct > 0:
        annualised = (futures_premium_pct / 100) * (365 / days_to_expiry) * 100
        if annualised > 15:
            score += 4; reasons.append(f"Annualised arb yield {annualised:.1f}% — excellent spread ✅")
        elif annualised > 10:
            score += 2; reasons.append(f"Annualised yield {annualised:.1f}% — decent arb opportunity ⚠️")
        elif annualised > 6:
            score += 1; reasons.append(f"Annualised yield {annualised:.1f}% — marginal (borrowing cost ~6%) ⚠️")
        else:
            score -= 1; reasons.append(f"Annualised yield {annualised:.1f}% — below cost of funds ❌")
    else:
        reasons.append("Futures premium data not available — check manually ○")

    # Near expiry = better (faster convergence)
    if days_to_expiry <= 7:
        score += 2; reasons.append(f"Only {days_to_expiry} days to expiry — fast convergence ✅")
    elif days_to_expiry <= 14:
        score += 1; reasons.append(f"{days_to_expiry} days to expiry — reasonable time horizon ⚠️")

    # Geopolitical context — high VIX widens spreads (more arb opportunities)
    vix = tech_data.get("vix", 16)
    if vix and vix > 18:
        score += 1; reasons.append("High VIX widens F&O spreads — more arb opportunities ✅")

    if score >= 5:
        status = ACTIVE
        advice = ("Buy in CASH market + Sell FUTURES simultaneously. "
                  "Hold until expiry for risk-free convergence profit.")
    elif score >= 3:
        status = WATCH
        advice = "Check the futures premium against your broker's cost of funds before executing."
    else:
        status = NEUTRAL
        advice = "Spread too small or expiry too far — arb profit less than transaction costs."

    return {"status": status, "score": score,
            "reason": "; ".join(reasons[:2]),
            "advice": advice, "reasons": reasons}


# ═════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═════════════════════════════════════════════════════════════════════════════

def run(shared_state: dict, request_params: dict = None) -> dict:
    """
    Main entry point. Can be called:
      a) From the agent pipeline (shared_state populated by other agents)
      b) Directly via /api/strategy-analysis (request_params from HTTP POST)
    """
    params = request_params or {}
    market   = params.get("market", "NIFTY")
    category = params.get("category", "all")

    log.info("⚔️  GeopoliticalStrategyAgent: market=%s category=%s", market, category)

    # ── Extract data from shared_state (populated by earlier agents) ──────────
    tech_raw  = shared_state.get("technical_data", {})
    # Use first available symbol's data as proxy, or empty dict
    tech_data = {}
    if tech_raw:
        first_key = next(iter(tech_raw), None)
        if first_key:
            tech_data = tech_raw.get(first_key, {})

    # Override with request params if provided (from direct API call)
    vix = params.get("vix") or shared_state.get("india_vix") or 18.0

    # Geopolitical risk score (0–1):
    # Hardcoded high for Iran-US 2026 scenario; can be wired to news sentiment agent
    sentiment_data = shared_state.get("news_sentiment", {})
    geo_risk = sentiment_data.get("geopolitical_risk_score", 0.75)  # Iran-US = high

    # Open positions from paper portfolio
    paper_portfolio = shared_state.get("paper_portfolio", {})
    has_positions = bool(paper_portfolio.get("open_positions", []))

    # Build clean tech_data dict for strategy functions
    td = {
        "price":       tech_data.get("price",       22500),
        "ema50":       tech_data.get("ema50"),
        "ema200":      tech_data.get("ema200"),
        "rsi":         tech_data.get("rsi",         45),
        "bb_upper":    tech_data.get("bb_upper"),
        "bb_mid":      tech_data.get("bb_mid"),
        "bb_lower":    tech_data.get("bb_lower"),
        "bb_width_pct":tech_data.get("bb_width_pct", 2.5),
        "volume_ratio":tech_data.get("volume_ratio", 1.0),
        "day_high":    tech_data.get("day_high"),
        "gap_pct":     tech_data.get("gap_pct", 0.0),
        "futures_premium_pct": params.get("futures_premium_pct", 0.35),
        "days_to_expiry":      params.get("days_to_expiry", 12),
        "vix":         vix,
    }

    # Determine overall trend
    if td["ema50"] and td["ema200"]:
        trend = "bullish" if td["ema50"] > td["ema200"] else "bearish"
    else:
        trend = "neutral"

    # ── Run all 8 strategy analyses ───────────────────────────────────────────
    signals = {
        "bull_call_spread":     _analyse_bull_call_spread(td, vix, trend),
        "momentum_breakout":    _analyse_momentum_breakout(td, vix),
        "long_straddle":        _analyse_long_straddle(td, vix, geo_risk),
        "short_straddle_9_20":  _analyse_short_straddle_9_20(td, vix, geo_risk),
        "protective_put":       _analyse_protective_put(td, vix, geo_risk, has_positions),
        "collar":               _analyse_collar(td, vix, geo_risk, has_positions),
        "mean_reversion":       _analyse_mean_reversion(td, vix),
        "cash_futures_arb":     _analyse_cash_futures_arb(td),
    }

    # ── Filter by category ────────────────────────────────────────────────────
    category_map = {
        "directional":  ["bull_call_spread", "momentum_breakout"],
        "volatility":   ["long_straddle", "short_straddle_9_20"],
        "hedging":      ["protective_put", "collar"],
        "arbitrage":    ["mean_reversion", "cash_futures_arb"],
    }
    if category != "all":
        keys = category_map.get(category, [])
        signals = {k: v for k, v in signals.items() if k in keys}

    # ── Rank and pick top 3 ───────────────────────────────────────────────────
    active   = [(k, v) for k, v in signals.items() if v["status"] == ACTIVE]
    watching = [(k, v) for k, v in signals.items() if v["status"] == WATCH]

    active.sort(key=lambda x: x[1]["score"], reverse=True)
    top_picks = [k for k, v in active[:3]]
    if len(top_picks) < 3:
        top_picks += [k for k, v in watching[:3 - len(top_picks)]]

    # ── Build narrative analysis text ─────────────────────────────────────────
    now = datetime.now().strftime("%d %b %Y %H:%M IST")
    lines = [
        f"⚔️  GEOPOLITICAL STRATEGY ANALYSIS — {market}",
        f"{'═'*60}",
        f"Time: {now}  |  Market: {market}  |  VIX: {vix:.1f}  |  Trend: {trend.upper()}",
        f"Geopolitical Risk: {'HIGH ⚠️' if geo_risk > 0.5 else 'MODERATE' if geo_risk > 0.2 else 'LOW'}  "
        f"({geo_risk:.0%}) — Iran-US Conflict Scenario",
        "",
    ]

    name_map = {
        "bull_call_spread": "📈 BULL CALL SPREAD",
        "momentum_breakout": "🌅 MOMENTUM BREAKOUT",
        "long_straddle": "🌪️  LONG STRADDLE",
        "short_straddle_9_20": "⏰  9:20 SHORT STRADDLE",
        "protective_put": "🛡️  PROTECTIVE PUT",
        "collar": "🔄 ZERO-COST COLLAR",
        "mean_reversion": "📉 MEAN REVERSION (BB)",
        "cash_futures_arb": "⚖️  CASH-FUTURES ARB",
    }

    status_icon = {ACTIVE: "✅", WATCH: "⚠️ ", AVOID: "❌", NEUTRAL: "○ "}

    for key, sig in signals.items():
        icon = status_icon.get(sig["status"], "○")
        lines.append(f"{icon} {name_map.get(key, key)} — {sig['status']}")
        if sig.get("reason"):
            lines.append(f"   Signal: {sig['reason']}")
        if sig.get("advice"):
            lines.append(f"   Action: {sig['advice']}")
        lines.append("")

    lines.append(f"{'─'*60}")
    lines.append("🏆 TOP PICKS FOR THIS SESSION:")
    for i, k in enumerate(top_picks, 1):
        sig = signals.get(k, {})
        lines.append(f"  {i}. {name_map.get(k, k)} — {sig.get('advice','')[:80]}")

    lines.append("")
    lines.append("⚠️  All recommendations are for paper trading / educational purposes only.")
    lines.append("   Consult a SEBI-registered advisor before investing real money.")

    analysis_text = "\n".join(lines)

    result = {
        "status": "ok",
        "market": market,
        "vix": vix,
        "geopolitical_risk": geo_risk,
        "trend": trend,
        "signals": signals,
        "top_picks": top_picks,
        "analysis": analysis_text,
        "summary": f"Analysis complete. {len(active)} strategies ACTIVE, {len(watching)} on WATCH.",
        "timestamp": now,
    }

    # Write back to shared_state for downstream agents
    shared_state["strategy_analysis"] = result
    log.info("⚔️  Strategy analysis complete: %d ACTIVE, %d WATCH",
             len(active), len(watching))

    return result
