"""
Alpha Vantage Channel
══════════════════════
Free fundamentals, earnings, macro data.
Free tier: 25 API requests/day, 5 req/min.

Setup:
  1. Get free key at https://www.alphavantage.co/support/#api-key
  2. Add to .env: ALPHA_VANTAGE_KEY=your_key

Data available:
  • Company overview (P/E, EPS, revenue, market cap)
  • Earnings history + upcoming dates
  • Economic indicators (GDP, CPI, interest rates)
  • Global quote (real-time price for US stocks)
"""

import os
import logging
import requests
from datetime import datetime

log = logging.getLogger("AlphaVantage")

AV_KEY  = os.getenv("ALPHA_VANTAGE_KEY", "")
AV_BASE = "https://www.alphavantage.co/query"


class AlphaVantageChannel:
    """Alpha Vantage REST API wrapper."""

    def __init__(self):
        self.api_key = AV_KEY

    def _get(self, params: dict) -> dict:
        try:
            params["apikey"] = self.api_key
            r = requests.get(AV_BASE, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "Note" in data:  # rate limit hit
                    log.warning("Alpha Vantage rate limit hit (5 req/min)")
                return data
            return {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def get_overview(self, symbol: str) -> dict:
        """
        Company fundamentals: sector, P/E, EPS, revenue, profit margin, etc.
        Very useful for enriching our watchlist fundamental scores.
        """
        data = self._get({"function": "OVERVIEW", "symbol": symbol})
        if "Symbol" not in data:
            return {}
        return {
            "pe_ratio":       float(data.get("PERatio", 0) or 0),
            "eps":            float(data.get("EPS", 0) or 0),
            "revenue":        data.get("RevenueTTM", "N/A"),
            "profit_margin":  data.get("ProfitMargin", "N/A"),
            "roe":            data.get("ReturnOnEquityTTM", "N/A"),
            "debt_equity":    data.get("DebtToEquityRatio", "N/A"),
            "market_cap":     data.get("MarketCapitalization", "N/A"),
            "sector":         data.get("Sector", "N/A"),
            "analyst_target": float(data.get("AnalystTargetPrice", 0) or 0),
            "52w_high":       float(data.get("52WeekHigh", 0) or 0),
            "52w_low":        float(data.get("52WeekLow", 0) or 0),
        }

    def get_earnings(self, symbol: str) -> dict:
        """
        Earnings history — actual vs. estimated EPS beat/miss.
        Feeds into pattern_memory agent for earnings momentum patterns.
        """
        data = self._get({"function": "EARNINGS", "symbol": symbol})
        quarterly = data.get("quarterlyEarnings", [])[:8]
        processed = []
        for q in quarterly:
            try:
                reported  = float(q.get("reportedEPS", 0) or 0)
                estimated = float(q.get("estimatedEPS", 0) or 0)
                surprise  = float(q.get("surprisePercentage", 0) or 0)
                processed.append({
                    "date":        q.get("fiscalDateEnding"),
                    "reported":    reported,
                    "estimated":   estimated,
                    "surprise_pct": round(surprise, 2),
                    "beat":        reported > estimated,
                })
            except Exception:
                continue
        beat_count = sum(1 for q in processed if q.get("beat"))
        return {
            "symbol":      symbol,
            "quarters":    processed,
            "beat_rate":   round(beat_count / len(processed), 2) if processed else 0,
            "last_4_beats": beat_count,
        }

    def get_gdp(self) -> dict:
        """US GDP growth rate — macro context for global sentiment."""
        data = self._get({"function": "REAL_GDP", "interval": "quarterly"})
        series = data.get("data", [])[:4]
        return {"gdp_data": series}

    def status(self) -> dict:
        return {
            "channel":    "alpha_vantage",
            "configured": bool(self.api_key),
            "key_masked": self.api_key[:4] + "****" if self.api_key else "not set",
            "checked_at": datetime.now().strftime("%H:%M:%S"),
        }
