"""
Chart Pattern Detector
═══════════════════════
Detects 7 classic chart patterns from 60-bar OHLCV data.
Runs after technical_analysis in the agent cycle, enriching
shared_state["chart_patterns"] with detected setups.

Patterns:
  BULL_FLAG        — Strong up-move + tight bearish consolidation
  BEAR_FLAG        — Strong down-move + tight bullish consolidation
  DOUBLE_BOTTOM    — W pattern (bullish reversal)
  DOUBLE_TOP       — M pattern (bearish reversal)
  ASC_TRIANGLE     — Flat resistance + rising lows (bullish)
  HEAD_SHOULDERS   — Three peaks, middle highest (bearish)
  INV_HEAD_SHLDRS  — Three troughs, middle lowest (bullish)

Each detected pattern returns:
  {pattern, direction, confidence (0-1), breakout_level, target, stop, bars_ago}
"""

import logging
import requests
from datetime import datetime, timedelta
from statistics import mean, stdev

log = logging.getLogger("PatternDetector")

PATTERN_LABELS = {
    "BULL_FLAG":       "Bull Flag",
    "BEAR_FLAG":       "Bear Flag",
    "DOUBLE_BOTTOM":   "Double Bottom",
    "DOUBLE_TOP":      "Double Top",
    "ASC_TRIANGLE":    "Asc. Triangle",
    "HEAD_SHOULDERS":  "Head & Shoulders",
    "INV_HEAD_SHLDRS": "Inv. H&S",
}


def _fetch_bars(symbol: str, days: int = 70) -> list:
    """Fetch OHLCV bars from Yahoo Finance. Returns list of bar dicts."""
    end   = datetime.now()
    start = end - timedelta(days=days)
    url   = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&period1={int(start.timestamp())}&period2={int(end.timestamp())}"
    )
    try:
        r    = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = r.json()
        res  = data["chart"]["result"][0]
        ts   = res["timestamp"]
        q    = res["indicators"]["quote"][0]
        bars = []
        for i, t in enumerate(ts):
            if q["close"][i] is None:
                continue
            bars.append({
                "date":   datetime.fromtimestamp(t).strftime("%Y-%m-%d"),
                "open":   round(q["open"][i]   or 0, 2),
                "high":   round(q["high"][i]   or 0, 2),
                "low":    round(q["low"][i]    or 0, 2),
                "close":  round(q["close"][i]  or 0, 2),
                "volume": int(q["volume"][i]   or 0),
            })
        return bars
    except Exception as e:
        log.debug(f"Pattern fetch error for {symbol}: {e}")
        return []


def _slope(values: list) -> float:
    """Simple linear slope of a value series."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


def detect_bull_flag(bars: list) -> dict | None:
    """Strong up-move (pole) followed by tight bearish consolidation (flag)."""
    if len(bars) < 20:
        return None
    pole  = bars[-20:-10]
    flag  = bars[-10:]
    closes_pole = [b["close"] for b in pole]
    closes_flag = [b["close"] for b in flag]
    pole_gain   = (closes_pole[-1] - closes_pole[0]) / closes_pole[0] if closes_pole[0] else 0
    flag_slope  = _slope(closes_flag)
    flag_range  = (max(closes_flag) - min(closes_flag)) / mean(closes_flag) if closes_flag else 1

    if pole_gain >= 0.06 and flag_slope < 0 and flag_range < 0.05:
        confidence  = min(1.0, pole_gain * 5 + (0.05 - flag_range) * 10)
        current     = bars[-1]["close"]
        breakout    = round(max(b["high"] for b in flag) * 1.002, 2)
        target      = round(current + (closes_pole[-1] - closes_pole[0]), 2)
        stop        = round(min(b["low"] for b in flag) * 0.998, 2)
        return {
            "pattern":        "BULL_FLAG",
            "label":          "Bull Flag",
            "direction":      "BULLISH",
            "confidence":     round(confidence, 2),
            "breakout_level": breakout,
            "target":         target,
            "stop":           stop,
            "bars_ago":       0,
        }
    return None


def detect_bear_flag(bars: list) -> dict | None:
    """Strong down-move (pole) followed by tight bullish consolidation."""
    if len(bars) < 20:
        return None
    pole  = bars[-20:-10]
    flag  = bars[-10:]
    closes_pole = [b["close"] for b in pole]
    closes_flag = [b["close"] for b in flag]
    pole_drop   = (closes_pole[0] - closes_pole[-1]) / closes_pole[0] if closes_pole[0] else 0
    flag_slope  = _slope(closes_flag)
    flag_range  = (max(closes_flag) - min(closes_flag)) / mean(closes_flag) if closes_flag else 1

    if pole_drop >= 0.06 and flag_slope > 0 and flag_range < 0.05:
        confidence  = min(1.0, pole_drop * 5 + (0.05 - flag_range) * 10)
        current     = bars[-1]["close"]
        breakdown   = round(min(b["low"] for b in flag) * 0.998, 2)
        target      = round(current - (closes_pole[0] - closes_pole[-1]), 2)
        stop        = round(max(b["high"] for b in flag) * 1.002, 2)
        return {
            "pattern":        "BEAR_FLAG",
            "label":          "Bear Flag",
            "direction":      "BEARISH",
            "confidence":     round(confidence, 2),
            "breakout_level": breakdown,
            "target":         target,
            "stop":           stop,
            "bars_ago":       0,
        }
    return None


def detect_double_bottom(bars: list) -> dict | None:
    """W pattern: two lows within 2% of each other, with a neckline above."""
    if len(bars) < 30:
        return None
    lows    = [b["low"] for b in bars[-30:]]
    closes  = [b["close"] for b in bars[-30:]]
    n = len(lows)

    # Find two local minima
    min1_idx = min(range(5, n // 2), key=lambda i: lows[i])
    min2_idx = min(range(n // 2, n - 3), key=lambda i: lows[i])

    low1, low2 = lows[min1_idx], lows[min2_idx]
    if low1 == 0 or low2 == 0:
        return None

    diff_pct = abs(low1 - low2) / ((low1 + low2) / 2)
    if diff_pct > 0.025:
        return None

    neckline   = max(closes[min1_idx:min2_idx + 1])
    current    = closes[-1]
    if current < neckline * 0.995:
        return None

    confidence = round(max(0.5, 0.9 - diff_pct * 20), 2)
    target     = round(neckline + (neckline - min(low1, low2)), 2)
    stop       = round(min(low1, low2) * 0.995, 2)
    return {
        "pattern":        "DOUBLE_BOTTOM",
        "label":          "Double Bottom",
        "direction":      "BULLISH",
        "confidence":     confidence,
        "breakout_level": round(neckline, 2),
        "target":         target,
        "stop":           stop,
        "bars_ago":       n - min2_idx - 1,
    }


def detect_double_top(bars: list) -> dict | None:
    """M pattern: two highs within 2% of each other, with a neckline below."""
    if len(bars) < 30:
        return None
    highs   = [b["high"] for b in bars[-30:]]
    closes  = [b["close"] for b in bars[-30:]]
    n = len(highs)

    top1_idx = max(range(5, n // 2), key=lambda i: highs[i])
    top2_idx = max(range(n // 2, n - 3), key=lambda i: highs[i])

    high1, high2 = highs[top1_idx], highs[top2_idx]
    if high1 == 0 or high2 == 0:
        return None

    diff_pct = abs(high1 - high2) / ((high1 + high2) / 2)
    if diff_pct > 0.025:
        return None

    neckline = min(closes[top1_idx:top2_idx + 1])
    current  = closes[-1]
    if current > neckline * 1.005:
        return None

    confidence = round(max(0.5, 0.9 - diff_pct * 20), 2)
    target     = round(neckline - (max(high1, high2) - neckline), 2)
    stop       = round(max(high1, high2) * 1.005, 2)
    return {
        "pattern":        "DOUBLE_TOP",
        "label":          "Double Top",
        "direction":      "BEARISH",
        "confidence":     confidence,
        "breakout_level": round(neckline, 2),
        "target":         target,
        "stop":           stop,
        "bars_ago":       n - top2_idx - 1,
    }


def detect_asc_triangle(bars: list) -> dict | None:
    """Flat resistance + ascending lows — bullish breakout setup."""
    if len(bars) < 25:
        return None
    recent = bars[-25:]
    highs  = [b["high"] for b in recent]
    lows   = [b["low"]  for b in recent]

    resistance = max(highs[-15:])
    near_res   = [h for h in highs[-15:] if h >= resistance * 0.992]
    if len(near_res) < 2:
        return None

    low_slope = _slope(lows[-15:])
    if low_slope <= 0:
        return None

    current    = bars[-1]["close"]
    confidence = round(min(0.85, 0.5 + low_slope / current * 500 + len(near_res) * 0.05), 2)
    target     = round(resistance + (resistance - lows[-15]), 2)
    stop       = round(lows[-1] * 0.997, 2)
    return {
        "pattern":        "ASC_TRIANGLE",
        "label":          "Asc. Triangle",
        "direction":      "BULLISH",
        "confidence":     confidence,
        "breakout_level": round(resistance * 1.003, 2),
        "target":         target,
        "stop":           stop,
        "bars_ago":       0,
    }


def detect_head_shoulders(bars: list) -> dict | None:
    """Three-peak pattern with middle peak highest — bearish reversal."""
    if len(bars) < 35:
        return None
    highs  = [b["high"]  for b in bars[-35:]]
    closes = [b["close"] for b in bars[-35:]]
    n = len(highs)

    # Left shoulder, head, right shoulder — roughly 3 equal-spaced peaks
    seg = n // 3
    ls_idx = max(range(0,    seg),     key=lambda i: highs[i])
    hd_idx = max(range(seg,  2 * seg), key=lambda i: highs[i])
    rs_idx = max(range(2 * seg, n),    key=lambda i: highs[i])

    ls, hd, rs = highs[ls_idx], highs[hd_idx], highs[rs_idx]
    if not (hd > ls and hd > rs):
        return None
    if abs(ls - rs) / max(ls, rs) > 0.04:
        return None

    neckline   = min(closes[ls_idx:rs_idx])
    current    = closes[-1]
    if current > neckline * 1.01:
        return None

    confidence = round(min(0.88, 0.65 + (hd - max(ls, rs)) / hd * 2), 2)
    target     = round(neckline - (hd - neckline), 2)
    stop       = round(highs[rs_idx] * 1.005, 2)
    return {
        "pattern":        "HEAD_SHOULDERS",
        "label":          "Head & Shoulders",
        "direction":      "BEARISH",
        "confidence":     confidence,
        "breakout_level": round(neckline * 0.997, 2),
        "target":         target,
        "stop":           stop,
        "bars_ago":       n - rs_idx - 1,
    }


def detect_inv_head_shoulders(bars: list) -> dict | None:
    """Three-trough pattern with middle trough lowest — bullish reversal."""
    if len(bars) < 35:
        return None
    lows   = [b["low"]   for b in bars[-35:]]
    closes = [b["close"] for b in bars[-35:]]
    n = len(lows)

    seg = n // 3
    ls_idx = min(range(0,    seg),     key=lambda i: lows[i])
    hd_idx = min(range(seg,  2 * seg), key=lambda i: lows[i])
    rs_idx = min(range(2 * seg, n),    key=lambda i: lows[i])

    ls, hd, rs = lows[ls_idx], lows[hd_idx], lows[rs_idx]
    if not (hd < ls and hd < rs):
        return None
    if abs(ls - rs) / min(ls, rs) > 0.04:
        return None

    neckline = max(closes[ls_idx:rs_idx])
    current  = closes[-1]
    if current < neckline * 0.99:
        return None

    confidence = round(min(0.88, 0.65 + (min(ls, rs) - hd) / min(ls, rs) * 2), 2)
    target     = round(neckline + (neckline - hd), 2)
    stop       = round(lows[rs_idx] * 0.995, 2)
    return {
        "pattern":        "INV_HEAD_SHLDRS",
        "label":          "Inv. H&S",
        "direction":      "BULLISH",
        "confidence":     confidence,
        "breakout_level": round(neckline * 1.003, 2),
        "target":         target,
        "stop":           stop,
        "bars_ago":       n - rs_idx - 1,
    }


DETECTORS = [
    detect_bull_flag,
    detect_bear_flag,
    detect_double_bottom,
    detect_double_top,
    detect_asc_triangle,
    detect_head_shoulders,
    detect_inv_head_shoulders,
]


class PatternDetector:
    """
    Runs all pattern detectors against each stock in technical_data.
    Fetches fresh 70-day OHLCV for each symbol.
    """

    def detect(self, symbol: str, bars: list) -> list:
        """Run all detectors on given bars. Returns list of detected patterns."""
        found = []
        for detector in DETECTORS:
            try:
                result = detector(bars)
                if result:
                    result["symbol"] = symbol
                    found.append(result)
            except Exception as e:
                log.debug(f"Detector {detector.__name__} error on {symbol}: {e}")
        return found

    def run(self, shared_state: dict) -> dict:
        """
        Scan all stocks in technical_data, detect patterns, write to shared_state.
        Returns the chart_patterns dict.
        """
        technical_data = shared_state.get("technical_data", {})
        if not technical_data:
            log.debug("PatternDetector: no technical_data yet — skipping")
            shared_state["chart_patterns"] = {}
            return {}

        results   = {}
        total_pat = 0

        for name, td in technical_data.items():
            symbol = td.get("symbol", name)
            bars   = _fetch_bars(symbol, days=70)
            if len(bars) < 20:
                continue

            patterns = self.detect(symbol, bars)
            if patterns:
                results[name] = patterns
                total_pat += len(patterns)
                log.debug(
                    f"PatternDetector: {name} — "
                    + ", ".join(p["label"] for p in patterns)
                )

        shared_state["chart_patterns"] = results
        log.info(
            f"PatternDetector: {len(technical_data)} stocks scanned | "
            f"{len(results)} with patterns | {total_pat} total patterns"
        )
        return results
