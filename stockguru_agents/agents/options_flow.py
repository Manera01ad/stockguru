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
from datetime import datetime, date

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
    """Find strikes with unusually high OI buildup (institutional positioning)."""
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
        call_ois.append(ce_oi)
        put_ois.append(pe_oi)
        items_map[strike] = {"call_oi": ce_oi, "put_oi": pe_oi}

    avg_call_oi = sum(call_ois) / len(call_ois) if call_ois else 0
    avg_put_oi  = sum(put_ois)  / len(put_ois)  if put_ois  else 0

    unusual = []
    for strike, ois in items_map.items():
        if ois["call_oi"] > avg_call_oi * threshold * 2:
            unusual.append({"strike": strike, "type": "CALL", "oi": ois["call_oi"],
                            "note": f"Major call resistance at {strike}"})
        if ois["put_oi"] > avg_put_oi * threshold * 2:
            unusual.append({"strike": strike, "type": "PUT", "oi": ois["put_oi"],
                            "note": f"Major put support at {strike}"})

    unusual.sort(key=lambda x: -x["oi"])
    return unusual[:5]

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
    """Main agent — compute PCR, max pain, unusual OI for Nifty + BankNifty."""
    log.info("📈 OptionsFlow: Fetching Nifty + BankNifty option chains...")

    result = {
        "nifty_pcr":         None,
        "banknifty_pcr":     None,
        "nifty_max_pain":    None,
        "banknifty_max_pain": None,
        "nifty_unusual_oi":  [],
        "market_bias":       "NEUTRAL",
        "bias_reason":       "Options data unavailable",
        "options_gate":      True,  # default pass if no data
        "last_run":          datetime.now().strftime("%d %b %H:%M:%S"),
    }

    # ── NIFTY ────────────────────────────────────────────────────────────────
    nifty_records = fetch_option_chain("NIFTY")
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

        # ── NEW: IV Expected Move for Nifty ──────────────────────────────
        nifty_price = result.get("nifty_price")  # set below if available
        # Estimate Nifty price from ATM strike
        atm_approx  = result["nifty_max_pain"]
        iv_move = compute_iv_expected_move(nifty_records, atm_approx)
        if iv_move:
            result["nifty_iv_expected_move"] = iv_move
            log.info("  Nifty IV Move: ±%.0f (%.1f%%) | IV=%.1f%% | DTE=%d",
                     iv_move["expected_move"], iv_move["expected_pct"],
                     iv_move["atm_iv"], iv_move["dte"])

        log.info("  Nifty PCR: %.3f → %s | Max Pain: %s",
                 result["nifty_pcr"] or 0, bias, result["nifty_max_pain"])

    # ── BANKNIFTY ─────────────────────────────────────────────────────────────
    bn_records = fetch_option_chain("BANKNIFTY")
    if bn_records:
        pcr_bn = compute_pcr(bn_records)
        if pcr_bn:
            result["banknifty_pcr"]  = pcr_bn[0]
        result["banknifty_max_pain"] = compute_max_pain(bn_records)

        # ── NEW: IV Expected Move for BankNifty ──────────────────────────
        bn_atm   = result["banknifty_max_pain"]
        bn_iv_move = compute_iv_expected_move(bn_records, bn_atm)
        if bn_iv_move:
            result["banknifty_iv_expected_move"] = bn_iv_move
            log.info("  BankNifty IV Move: ±%.0f (%.1f%%) | IV=%.1f%%",
                     bn_iv_move["expected_move"], bn_iv_move["expected_pct"],
                     bn_iv_move["atm_iv"])

        log.info("  BankNifty PCR: %.3f | Max Pain: %s",
                 result["banknifty_pcr"] or 0, result["banknifty_max_pain"])

    shared_state["options_flow"]      = result
    shared_state["options_last_run"]  = result["last_run"]
    log.info("✅ OptionsFlow: Nifty PCR=%.3f | Gate=%s | Bias=%s",
             result["nifty_pcr"] or 0,
             "PASS" if result["options_gate"] else "FAIL",
             result["market_bias"])
    return result
