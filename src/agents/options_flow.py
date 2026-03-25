"""
AGENT 6 — OPTIONS FLOW
━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Analyze NSE option chain for Nifty + BankNifty.
          Compute PCR, Max Pain, IV percentile, unusual OI.
          These are the best leading indicators for market direction.
Runs    : Every 15 minutes during market hours
Cost    : Zero — NSE public data
Reports : Feeds claude_intelligence conviction gates (R8, R24)

KEY METRICS:
  PCR < 0.6  = Extreme greed (market likely to fall soon)
  PCR 0.6-0.8 = Bullish bias
  PCR 0.8-1.1 = Neutral
  PCR 1.1-1.3 = Bearish bias
  PCR > 1.3  = Extreme fear (contrarian buy signal)

  Max Pain = Strike where total option seller losses are minimized
             (Market tends to gravitate toward max pain at expiry)
"""

import requests
import logging
import math
import json
import os
from datetime import datetime, date

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IV_HISTORY_PATH     = os.path.join(_BASE, "data", "iv_history.json")
ROLLOVER_HIST_PATH  = os.path.join(_BASE, "data", "rollover_history.json")

log = logging.getLogger("OptionsFlow")

NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}

def fetch_option_chain(symbol="NIFTY"):
    """Fetch NSE option chain for NIFTY or BANKNIFTY."""
    try:
        session = requests.Session()
        # Establish session/cookies first
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
        session.get("https://www.nseindia.com/option-chain", headers=NSE_HEADERS, timeout=8)

        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        r   = session.get(url, headers=NSE_HEADERS, timeout=12)

        if r.status_code != 200:
            log.debug("Option chain HTTP %d for %s", r.status_code, symbol)
            return None

        data = r.json()
        records = data.get("records", {})
        return records
    except Exception as e:
        log.debug("Option chain fetch failed for %s: %s", symbol, e)
        return None

def compute_pcr(records):
    """Compute Put-Call Ratio from option chain records."""
    if not records:
        return None

    total_put_oi  = 0
    total_call_oi = 0
    data          = records.get("data", [])

    for item in data:
        ce = item.get("CE", {})
        pe = item.get("PE", {})
        total_call_oi += ce.get("openInterest", 0) if ce else 0
        total_put_oi  += pe.get("openInterest", 0) if pe else 0

    if total_call_oi == 0:
        return None

    pcr = round(total_put_oi / total_call_oi, 3)
    return pcr, total_put_oi, total_call_oi

def compute_max_pain(records):
    """
    Max Pain = strike price where total option buyer loss is maximum.
    = the price where combined P&L of all option buyers is most negative.
    Market makers benefit when market expires at max pain.
    """
    if not records:
        return None

    data     = records.get("data", [])
    strikes  = []
    oi_map   = {}

    for item in data:
        strike = item.get("strikePrice")
        if not strike:
            continue
        ce_oi = item.get("CE", {}).get("openInterest", 0) if item.get("CE") else 0
        pe_oi = item.get("PE", {}).get("openInterest", 0) if item.get("PE") else 0
        if ce_oi > 0 or pe_oi > 0:
            strikes.append(strike)
            oi_map[strike] = {"call_oi": ce_oi, "put_oi": pe_oi}

    if not strikes:
        return None

    # For each strike, compute total option value at expiry
    min_pain   = float("inf")
    max_pain_s = strikes[len(strikes) // 2]  # fallback: ATM

    for test_strike in strikes:
        total_pain = 0
        for strike, ois in oi_map.items():
            # Call holders lose if market expires below strike
            if test_strike < strike:
                total_pain += (strike - test_strike) * ois["call_oi"]
            # Put holders lose if market expires above strike
            if test_strike > strike:
                total_pain += (test_strike - strike) * ois["put_oi"]
        if total_pain < min_pain:
            min_pain   = total_pain
            max_pain_s = test_strike

    return max_pain_s

def compute_iv_expected_move(records, current_price):
    """
    IIFL IV Expected Move formula:
      Expected Movement = Current Price × IV × √(Days to Expiry / 365)

    Gets ATM option IV from the option chain, extracts nearest expiry date,
    then calculates the expected ±range by end of expiry.

    Returns dict with: iv, dte, expected_move, upper_range, lower_range
    """
    if not records or not current_price:
        return None
    try:
        data        = records.get("data", [])
        expiry_dates = records.get("expiryDates", [])
        if not expiry_dates:
            return None

        # Use the nearest expiry
        nearest_expiry = expiry_dates[0]
        # Parse "27-Feb-2026" format
        try:
            exp_date = datetime.strptime(nearest_expiry, "%d-%b-%Y").date()
        except Exception:
            return None
        dte = (exp_date - date.today()).days
        if dte <= 0:
            dte = 1  # same-day expiry

        # Find ATM strike (closest to current price)
        atm_strike = None
        atm_iv     = None
        min_diff   = float("inf")

        for item in data:
            strike = item.get("strikePrice")
            if not strike:
                continue
            diff = abs(strike - current_price)
            ce   = item.get("CE", {})
            pe   = item.get("PE", {})
            # Average CE+PE IV for ATM (more stable)
            ce_iv = ce.get("impliedVolatility", 0) if ce else 0
            pe_iv = pe.get("impliedVolatility", 0) if pe else 0
            iv    = (ce_iv + pe_iv) / 2 if (ce_iv and pe_iv) else (ce_iv or pe_iv)
            if diff < min_diff and iv and iv > 0:
                min_diff   = diff
                atm_strike = strike
                atm_iv     = iv

        if not atm_iv or atm_iv <= 0:
            return None

        # NSE gives IV as percentage (e.g. 14.5 = 14.5%), convert to decimal
        iv_decimal     = atm_iv / 100.0
        expected_move  = round(current_price * iv_decimal * math.sqrt(dte / 365), 2)
        upper_range    = round(current_price + expected_move, 2)
        lower_range    = round(current_price - expected_move, 2)
        expected_pct   = round((expected_move / current_price) * 100, 2)

        return {
            "atm_strike":     atm_strike,
            "atm_iv":         round(atm_iv, 2),
            "dte":            dte,
            "expiry":         nearest_expiry,
            "expected_move":  expected_move,
            "expected_pct":   expected_pct,
            "upper_range":    upper_range,
            "lower_range":    lower_range,
        }
    except Exception as e:
        log.debug("IV expected move calc failed: %s", e)
        return None

def find_unusual_oi(records, threshold=1.5):
    """
    Find strikes with unusually high OI buildup (institutional positioning).
    Returns top 8 walls enriched with vs_avg_pct and gamma_risk flag.
    """
    if not records:
        return []

    data      = records.get("data", [])
    call_ois  = []
    put_ois   = []
    items_map = {}

    for item in data:
        strike = item.get("strikePrice")
        if not strike:
            continue
        ce_oi = item.get("CE", {}).get("openInterest", 0) if item.get("CE") else 0
        pe_oi = item.get("PE", {}).get("openInterest", 0) if item.get("PE") else 0
        ce_iv = item.get("CE", {}).get("impliedVolatility", 0) if item.get("CE") else 0
        pe_iv = item.get("PE", {}).get("impliedVolatility", 0) if item.get("PE") else 0
        call_ois.append(ce_oi)
        put_ois.append(pe_oi)
        items_map[strike] = {
            "call_oi": ce_oi, "put_oi": pe_oi,
            "call_iv": ce_iv, "put_iv": pe_iv,
        }

    avg_call_oi = sum(call_ois) / len(call_ois) if call_ois else 1
    avg_put_oi  = sum(put_ois)  / len(put_ois)  if put_ois  else 1

    unusual = []
    for strike, ois in items_map.items():
        if ois["call_oi"] > avg_call_oi * threshold * 2:
            vs_avg = round((ois["call_oi"] / avg_call_oi - 1) * 100)
            unusual.append({
                "strike":     strike,
                "type":       "CALL",
                "oi":         ois["call_oi"],
                "iv":         ois["call_iv"],
                "vs_avg_pct": vs_avg,
                "signal":     "🔴 RESISTANCE",
                "note":       f"Major call wall at {strike:,} ({vs_avg}% above avg OI)",
                "gamma_risk": vs_avg > 300,   # extreme = gamma squeeze risk
            })
        if ois["put_oi"] > avg_put_oi * threshold * 2:
            vs_avg = round((ois["put_oi"] / avg_put_oi - 1) * 100)
            unusual.append({
                "strike":     strike,
                "type":       "PUT",
                "oi":         ois["put_oi"],
                "iv":         ois["put_iv"],
                "vs_avg_pct": vs_avg,
                "signal":     "🟢 SUPPORT",
                "note":       f"Major put wall at {strike:,} ({vs_avg}% above avg OI)",
                "gamma_risk": vs_avg > 300,
            })

    unusual.sort(key=lambda x: -x["oi"])
    return unusual[:8]


def check_oi_wall_approach(unusual_oi: list, current_price: float,
                           approach_pct: float = 0.5) -> list:
    """
    Returns walls that LTP is approaching within `approach_pct`% distance.
    Used to fire early Telegram alerts before a gamma squeeze develops.
    """
    if not unusual_oi or not current_price:
        return []
    alerts = []
    for wall in unusual_oi:
        strike = wall["strike"]
        dist_pct = abs(current_price - strike) / current_price * 100
        if dist_pct <= approach_pct:
            alerts.append({
                **wall,
                "current_price": current_price,
                "dist_pct":      round(dist_pct, 2),
                "approach_msg":  (
                    f"⚠️ LTP ₹{current_price:,.0f} approaching "
                    f"{wall['type']} wall @ {strike:,} "
                    f"(OI={wall['oi']:,}, {dist_pct:.1f}% away) — "
                    f"{'GAMMA SQUEEZE RISK 🔥' if wall.get('gamma_risk') else 'Monitor closely'}"
                ),
            })
    return alerts

def interpret_vix(vix_level):
    """Classify India VIX into regime + alert."""
    if vix_level is None:
        return "UNKNOWN", "VIX data unavailable", False
    if vix_level < 12:
        return "GREED",    "VIX extremely low — complacency risk, market priced for perfection", False
    elif vix_level < 15:
        return "CALM",     "VIX calm — healthy low volatility, trend-following favored", False
    elif vix_level < 20:
        return "CAUTIOUS", "VIX elevated — reduce size, tighten stops", True
    elif vix_level < 25:
        return "FEARFUL",  "VIX high — hedges needed, no aggressive longs (R22)", True
    else:
        return "PANIC",    "VIX extreme — markets panicking, avoid new positions", True


def compute_iv_rank(nifty_iv, banknifty_iv=None):
    """
    IV Rank (IVR) = how high current IV is vs 90-day range.
    Reads/writes data/iv_history.json.
    Returns: {nifty_ivr, nifty_iv_pct, banknifty_ivr, iv_regime, strategy_bias}
    """
    today_str = date.today().isoformat()
    # Load history
    try:
        with open(IV_HISTORY_PATH) as f:
            history = json.load(f)
    except Exception:
        history = {}

    # Store today's snapshot
    if nifty_iv and nifty_iv > 0:
        history[today_str] = {"nifty_iv": nifty_iv, "banknifty_iv": banknifty_iv}

    # Prune to 90-day rolling window
    dates = sorted(history.keys())[-90:]
    history = {d: history[d] for d in dates}

    # Save back
    try:
        os.makedirs(os.path.dirname(IV_HISTORY_PATH), exist_ok=True)
        with open(IV_HISTORY_PATH, "w") as f:
            json.dump(history, f)
    except Exception:
        pass

    # Compute IVR
    nifty_ivs = [v["nifty_iv"] for v in history.values() if v.get("nifty_iv")]
    result = {"nifty_ivr": None, "nifty_iv_pct": None, "banknifty_ivr": None,
              "iv_regime": "NORMAL", "strategy_bias": "BALANCED"}

    if len(nifty_ivs) >= 5:
        low, high = min(nifty_ivs), max(nifty_ivs)
        if high > low and nifty_iv:
            ivr = round((nifty_iv - low) / (high - low) * 100, 1)
            result["nifty_ivr"]     = ivr
            result["nifty_iv_pct"]  = round(nifty_iv, 2)
            result["iv_90d_low"]    = round(low, 2)
            result["iv_90d_high"]   = round(high, 2)
            if ivr < 20:
                result["iv_regime"]     = "LOW_IV"
                result["strategy_bias"] = "BUY_OPTIONS (cheap premium)"
            elif ivr < 40:
                result["iv_regime"]     = "BELOW_NORMAL"
                result["strategy_bias"] = "SLIGHT_BUY_OPTIONS"
            elif ivr < 60:
                result["iv_regime"]     = "NORMAL"
                result["strategy_bias"] = "BALANCED"
            elif ivr < 80:
                result["iv_regime"]     = "ELEVATED"
                result["strategy_bias"] = "SLIGHT_SELL_OPTIONS"
            else:
                result["iv_regime"]     = "HIGH_IV"
                result["strategy_bias"] = "SELL_OPTIONS (rich premium)"

    if banknifty_iv:
        bn_ivs = [v["banknifty_iv"] for v in history.values() if v.get("banknifty_iv")]
        if len(bn_ivs) >= 5:
            low_bn, high_bn = min(bn_ivs), max(bn_ivs)
            if high_bn > low_bn:
                result["banknifty_ivr"] = round((banknifty_iv - low_bn) / (high_bn - low_bn) * 100, 1)

    return result


def fetch_rollover(session):
    """
    Fetch Nifty futures OI for current + next expiry to compute rollover %.
    Rollover% = next_month_OI / (current_OI + next_OI) × 100
    Higher rollover = positions being carried forward (conviction trade).
    """
    try:
        url = "https://www.nseindia.com/api/quote-derivative?symbol=NIFTY"
        r   = session.get(url, headers=NSE_HEADERS, timeout=12)
        if r.status_code != 200:
            return None
        data     = r.json()
        fut_data = [
            x for x in data.get("stocks", [])
            if x.get("metadata", {}).get("instrumentType") == "Index Futures"
        ]
        if len(fut_data) < 2:
            return None

        # Sort by expiry date
        def parse_expiry(x):
            try:
                return datetime.strptime(x["metadata"]["expiryDate"], "%d-%b-%Y")
            except Exception:
                return datetime.max

        fut_data.sort(key=parse_expiry)
        curr = fut_data[0].get("marketDeptOrderBook", {}).get("tradeInfo", {})
        nxt  = fut_data[1].get("marketDeptOrderBook", {}).get("tradeInfo", {}) if len(fut_data) > 1 else {}

        curr_oi = curr.get("openInterest", 0) or 0
        next_oi = nxt.get("openInterest",  0) or 0
        total_oi = curr_oi + next_oi

        if total_oi == 0:
            return None

        rollover_pct = round(next_oi / total_oi * 100, 1)

        # Load/update rollover history for comparison
        today_str = date.today().isoformat()
        try:
            with open(ROLLOVER_HIST_PATH) as f:
                rh = json.load(f)
        except Exception:
            rh = {}

        rh[today_str] = rollover_pct
        rh = {d: rh[d] for d in sorted(rh.keys())[-30:]}   # 30-day rolling
        try:
            os.makedirs(os.path.dirname(ROLLOVER_HIST_PATH), exist_ok=True)
            with open(ROLLOVER_HIST_PATH, "w") as f:
                json.dump(rh, f)
        except Exception:
            pass

        # Compare vs 30-day average
        hist_vals = list(rh.values())
        avg_rollover = round(sum(hist_vals) / len(hist_vals), 1) if hist_vals else 65.0
        diff = round(rollover_pct - avg_rollover, 1)

        if diff > 5:
            interpretation = f"HIGH rollover ({rollover_pct}% vs avg {avg_rollover}%) — strong carry-forward, bulls confident"
            strength = "STRONG"
        elif diff < -5:
            interpretation = f"LOW rollover ({rollover_pct}% vs avg {avg_rollover}%) — positions squaring, caution"
            strength = "WEAK"
        else:
            interpretation = f"NORMAL rollover ({rollover_pct}% vs avg {avg_rollover}%) — orderly transition"
            strength = "NORMAL"

        curr_expiry = fut_data[0].get("metadata", {}).get("expiryDate", "")
        next_expiry = fut_data[1].get("metadata", {}).get("expiryDate", "") if len(fut_data) > 1 else ""

        return {
            "nifty_rollover_pct":  rollover_pct,
            "current_oi":          curr_oi,
            "next_oi":             next_oi,
            "avg_rollover_30d":    avg_rollover,
            "diff_vs_avg":         diff,
            "interpretation":      interpretation,
            "strength":            strength,
            "curr_expiry":         curr_expiry,
            "next_expiry":         next_expiry,
        }
    except Exception as e:
        log.debug("Rollover fetch failed: %s", e)
        return None


def interpret_pcr(pcr):
    """Map PCR value to market bias."""
    if pcr is None:
        return "NEUTRAL", "PCR data unavailable"
    if pcr < 0.5:
        return "DANGER_OVERBOUGHT", "Extreme greed — correction likely soon"
    elif pcr < 0.65:
        return "BULLISH_CAUTION",   "Bullish but overbought — use tight stops"
    elif pcr < 0.80:
        return "BULLISH",           "Healthy bullish sentiment — favor longs"
    elif pcr < 1.0:
        return "NEUTRAL_BULLISH",   "Slightly bullish — selective longs OK"
    elif pcr < 1.15:
        return "NEUTRAL",           "Balanced market — wait for direction"
    elif pcr < 1.30:
        return "BEARISH",           "Bearish sentiment building — be cautious"
    else:
        return "FEAR_BUY_DIPS",     "Extreme fear — contrarian buy dips (not breakouts)"

def run(shared_state):
    """Main agent — compute PCR, max pain, unusual OI, VIX regime, IV rank, rollover."""
    log.info("📈 OptionsFlow: Fetching Nifty + BankNifty option chains...")

    result = {
        "nifty_pcr":         None,
        "banknifty_pcr":     None,
        "nifty_max_pain":    None,
        "banknifty_max_pain": None,
        "nifty_unusual_oi":     [],
        "banknifty_unusual_oi": [],
        "market_bias":          "NEUTRAL",
        "bias_reason":          "Options data unavailable",
        "options_gate":         True,  # default pass if no data
        "last_run":             datetime.now().strftime("%d %b %H:%M:%S"),
    }

    # ── SHARED SESSION (reused for all NSE calls incl. rollover) ─────────────
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
        session.get("https://www.nseindia.com/option-chain", headers=NSE_HEADERS, timeout=8)
    except Exception:
        pass

    # ── INDIA VIX ────────────────────────────────────────────────────────────
    vix_data = shared_state.get("price_cache", {}).get("INDIA VIX", {})
    vix_level = vix_data.get("price") if vix_data else None
    vix_chg   = vix_data.get("change_pct") if vix_data else None
    vix_regime, vix_alert_msg, vix_alert = interpret_vix(vix_level)
    india_vix = {
        "level":      vix_level,
        "change_pct": vix_chg,
        "regime":     vix_regime,
        "alert":      vix_alert_msg,
        "is_alert":   vix_alert,
    }
    shared_state["india_vix"] = india_vix
    log.info("  India VIX: %.1f → %s", vix_level or 0, vix_regime)

    # ── NIFTY OPTION CHAIN ────────────────────────────────────────────────────
    try:
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        r   = session.get(url, headers=NSE_HEADERS, timeout=12)
        nifty_records = r.json().get("records", {}) if r.status_code == 200 else None
    except Exception:
        nifty_records = None

    nifty_ltp    = nifty_records.get("underlyingValue") if nifty_records else None
    nifty_atm_iv = None
    if nifty_records:
        pcr_result = compute_pcr(nifty_records)
        if pcr_result:
            pcr, put_oi, call_oi         = pcr_result
            result["nifty_pcr"]          = pcr
            result["nifty_total_put_oi"] = put_oi
            result["nifty_total_call_oi"]= call_oi

        result["nifty_max_pain"]    = compute_max_pain(nifty_records)
        result["nifty_unusual_oi"]  = find_unusual_oi(nifty_records)

        bias, reason               = interpret_pcr(result["nifty_pcr"])
        result["market_bias"]      = bias
        result["bias_reason"]      = reason

        # Gate R8: PCR between 0.6-1.1 = ok for new longs
        pcr_val = result["nifty_pcr"]
        result["options_gate"] = pcr_val is None or (0.60 <= pcr_val <= 1.15)

        atm_approx  = result["nifty_max_pain"]
        iv_move = compute_iv_expected_move(nifty_records, atm_approx)
        if iv_move:
            result["nifty_iv_expected_move"] = iv_move
            nifty_atm_iv = iv_move.get("atm_iv")
            log.info("  Nifty IV Move: ±%.0f (%.1f%%) | ATM IV=%.1f%% | DTE=%d",
                     iv_move["expected_move"], iv_move["expected_pct"],
                     iv_move["atm_iv"], iv_move["dte"])

        log.info("  Nifty PCR: %.3f → %s | Max Pain: %s",
                 result["nifty_pcr"] or 0, bias, result["nifty_max_pain"])

    # ── BANKNIFTY OPTION CHAIN ────────────────────────────────────────────────
    try:
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY"
        r   = session.get(url, headers=NSE_HEADERS, timeout=12)
        bn_records = r.json().get("records", {}) if r.status_code == 200 else None
    except Exception:
        bn_records = None

    bn_ltp    = bn_records.get("underlyingValue") if bn_records else None
    bn_atm_iv = None
    if bn_records:
        pcr_bn = compute_pcr(bn_records)
        if pcr_bn:
            result["banknifty_pcr"]       = pcr_bn[0]
        result["banknifty_max_pain"]      = compute_max_pain(bn_records)
        result["banknifty_unusual_oi"]    = find_unusual_oi(bn_records)

        bn_atm   = result["banknifty_max_pain"]
        bn_iv_move = compute_iv_expected_move(bn_records, bn_atm)
        if bn_iv_move:
            result["banknifty_iv_expected_move"] = bn_iv_move
            bn_atm_iv = bn_iv_move.get("atm_iv")
            log.info("  BankNifty IV Move: ±%.0f (%.1f%%) | ATM IV=%.1f%%",
                     bn_iv_move["expected_move"], bn_iv_move["expected_pct"],
                     bn_iv_move["atm_iv"])

        log.info("  BankNifty PCR: %.3f | Max Pain: %s",
                 result["banknifty_pcr"] or 0, result["banknifty_max_pain"])

    # ── IV RANK (IVR) ─────────────────────────────────────────────────────────
    if nifty_atm_iv:
        iv_rank = compute_iv_rank(nifty_atm_iv, bn_atm_iv)
        shared_state["iv_rank"] = iv_rank
        log.info("  Nifty IVR: %s%% → %s | Strategy: %s",
                 iv_rank.get("nifty_ivr", "N/A"),
                 iv_rank.get("iv_regime", ""),
                 iv_rank.get("strategy_bias", ""))

    # ── ROLLOVER ANALYSIS ─────────────────────────────────────────────────────
    rollover = fetch_rollover(session)
    if rollover:
        shared_state["rollover_data"] = rollover
        log.info("  Rollover: %.1f%% (avg %.1f%%) → %s",
                 rollover["nifty_rollover_pct"],
                 rollover["avg_rollover_30d"],
                 rollover["strength"])

    # ── OI WALL APPROACH DETECTION ────────────────────────────────────────────
    wall_alerts = []
    if nifty_ltp and result["nifty_unusual_oi"]:
        alerts = check_oi_wall_approach(result["nifty_unusual_oi"], nifty_ltp)
        for a in alerts:
            a["index"] = "NIFTY"
            wall_alerts.append(a)
            log.warning("⚠️ NIFTY OI WALL APPROACH: %s", a["approach_msg"])
    if bn_ltp and result["banknifty_unusual_oi"]:
        alerts = check_oi_wall_approach(result["banknifty_unusual_oi"], bn_ltp)
        for a in alerts:
            a["index"] = "BANKNIFTY"
            wall_alerts.append(a)
            log.warning("⚠️ BANKNIFTY OI WALL APPROACH: %s", a["approach_msg"])
    shared_state["oi_wall_alerts"] = wall_alerts

    shared_state["options_flow"]      = result
    shared_state["options_last_run"]  = result["last_run"]
    log.info("✅ OptionsFlow: Nifty PCR=%.3f | Gate=%s | Bias=%s | VIX=%.1f(%s) | Walls=%d approach",
             result["nifty_pcr"] or 0,
             "PASS" if result["options_gate"] else "FAIL",
             result["market_bias"],
             vix_level or 0, vix_regime,
             len(wall_alerts))
    return result
