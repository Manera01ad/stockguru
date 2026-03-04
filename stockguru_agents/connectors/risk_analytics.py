"""
Risk Analytics Connector
═════════════════════════
Portfolio-level risk metrics beyond per-trade R:R.

Computes:
  - Historical VaR (95% and 99%) — worst-case daily loss
  - Correlation matrix — pairwise Pearson r between open positions
  - Portfolio beta — weighted beta vs NIFTY 50 (^NSEI)

Data source: Yahoo Finance 60-day daily returns (no API key required).
Reads open positions from shared_state["paper_portfolio"]["positions"].

Falls back gracefully to zeros when portfolio is empty or data unavailable.
"""

import logging
import requests
from datetime import datetime, timedelta
from statistics import mean, stdev, correlation

log = logging.getLogger("RiskAnalytics")

NIFTY_SYMBOL = "^NSEI"
HISTORY_DAYS = 62   # ~3 trading months for robust statistics


def _fetch_returns(symbol: str, days: int = HISTORY_DAYS) -> list:
    """
    Fetch daily closing prices from Yahoo Finance and compute daily returns.
    Returns list of floats (decimal returns, e.g. 0.012 = +1.2%).
    """
    end   = datetime.now()
    start = end - timedelta(days=days)
    url   = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&period1={int(start.timestamp())}&period2={int(end.timestamp())}"
    )
    try:
        r      = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data   = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 10:
            return []
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
                   for i in range(1, len(closes))]
        return returns
    except Exception as e:
        log.debug(f"Returns fetch error for {symbol}: {e}")
        return []


def _percentile(data: list, pct: float) -> float:
    """Simple percentile calculation (no numpy needed)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    return sorted_data[max(0, min(idx, len(sorted_data) - 1))]


def _pearson(x: list, y: list) -> float:
    """Pearson correlation coefficient between two aligned return series."""
    n = min(len(x), len(y))
    if n < 5:
        return 0.0
    x, y = x[-n:], y[-n:]
    try:
        return round(correlation(x, y), 3)
    except Exception:
        return 0.0


class RiskAnalytics:
    """
    Computes portfolio-level risk metrics and writes to shared_state.
    Designed to run after paper_trader in the agent cycle.
    """

    def compute_var(self, positions: dict, capital: float) -> dict:
        """
        Historical VaR at 95% and 99% confidence.
        Uses equal-weighted daily portfolio return (simplified).

        positions: {name: {"shares": int, "entry_price": float, "symbol": str}}
        capital:   total portfolio value in INR
        """
        if not positions:
            return {"var_95_pct": 0.0, "var_99_pct": 0.0,
                    "var_95_inr": 0.0, "var_99_inr": 0.0}

        all_returns = []
        weights     = []

        for name, pos in positions.items():
            if pos.get("status") != "OPEN":
                continue
            symbol  = pos.get("symbol", name)
            returns = _fetch_returns(symbol)
            if not returns:
                continue
            pos_value = pos.get("shares", 1) * pos.get("entry_price", 0)
            all_returns.append(returns)
            weights.append(pos_value)

        if not all_returns:
            return {"var_95_pct": 0.0, "var_99_pct": 0.0,
                    "var_95_inr": 0.0, "var_99_inr": 0.0}

        total_w = sum(weights) or 1.0
        norm_w  = [w / total_w for w in weights]

        # Compute weighted portfolio daily returns
        min_len     = min(len(r) for r in all_returns)
        port_returns = []
        for i in range(min_len):
            pr = sum(all_returns[j][i] * norm_w[j] for j in range(len(all_returns)))
            port_returns.append(pr)

        # Historical VaR: worst nth percentile
        var_95_pct = round(abs(_percentile(port_returns, 5)) * 100, 2)
        var_99_pct = round(abs(_percentile(port_returns, 1)) * 100, 2)

        return {
            "var_95_pct": var_95_pct,
            "var_99_pct": var_99_pct,
            "var_95_inr": round(capital * var_95_pct / 100, 0),
            "var_99_inr": round(capital * var_99_pct / 100, 0),
        }

    def compute_correlation(self, positions: dict) -> dict:
        """
        Pairwise Pearson correlation between all open positions.
        Returns high_corr_pairs (|r| > 0.7) and max_correlation.
        """
        open_pos = {
            name: pos for name, pos in positions.items()
            if pos.get("status") == "OPEN"
        }
        if len(open_pos) < 2:
            return {"pairs": {}, "max_corr": 0.0, "high_corr_pairs": []}

        # Fetch returns for each position
        return_map = {}
        for name, pos in open_pos.items():
            symbol  = pos.get("symbol", name)
            returns = _fetch_returns(symbol, days=35)
            if returns:
                return_map[name] = returns

        names = list(return_map.keys())
        pairs = {}
        high_corr = []

        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                r = _pearson(return_map[a], return_map[b])
                pairs[f"{a}|{b}"] = r
                if abs(r) >= 0.70:
                    high_corr.append((a, b, r))

        max_corr = round(max((abs(v) for v in pairs.values()), default=0.0), 3)
        return {
            "pairs":           pairs,
            "max_corr":        max_corr,
            "high_corr_pairs": sorted(high_corr, key=lambda x: abs(x[2]), reverse=True),
        }

    def compute_beta(self, positions: dict) -> dict:
        """
        Weighted portfolio beta vs NIFTY 50.
        beta > 1.2 = AGGRESSIVE, 0.8-1.2 = NEUTRAL, < 0.8 = DEFENSIVE
        """
        open_pos = {
            name: pos for name, pos in positions.items()
            if pos.get("status") == "OPEN"
        }
        if not open_pos:
            return {"portfolio_beta": 1.0, "beta_status": "NEUTRAL"}

        nifty_returns = _fetch_returns(NIFTY_SYMBOL)
        if not nifty_returns:
            return {"portfolio_beta": 1.0, "beta_status": "NEUTRAL"}

        betas   = []
        weights = []

        for name, pos in open_pos.items():
            symbol  = pos.get("symbol", name)
            returns = _fetch_returns(symbol)
            if not returns:
                continue
            n = min(len(returns), len(nifty_returns))
            r, m = returns[-n:], nifty_returns[-n:]
            cov  = mean((r[i] - mean(r)) * (m[i] - mean(m)) for i in range(n))
            var_m = mean((x - mean(m)) ** 2 for x in m)
            beta = round(cov / var_m, 3) if var_m else 1.0
            pos_value = pos.get("shares", 1) * pos.get("entry_price", 0)
            betas.append(beta)
            weights.append(pos_value)

        if not betas:
            return {"portfolio_beta": 1.0, "beta_status": "NEUTRAL"}

        total_w  = sum(weights) or 1.0
        port_beta = round(sum(b * w / total_w for b, w in zip(betas, weights)), 3)

        if port_beta > 1.2:
            status = "AGGRESSIVE"
        elif port_beta < 0.8:
            status = "DEFENSIVE"
        else:
            status = "NEUTRAL"

        return {"portfolio_beta": port_beta, "beta_status": status}

    def run(self, shared_state: dict) -> dict:
        """
        Run all risk analytics and write to shared_state["risk_analytics"].
        Reads portfolio from shared_state["paper_portfolio"].
        """
        portfolio = shared_state.get("paper_portfolio", {})
        positions = portfolio.get("positions", {})
        capital   = float(portfolio.get("total_value", portfolio.get("available_cash", 500000)))

        var_result   = self.compute_var(positions, capital)
        corr_result  = self.compute_correlation(positions)
        beta_result  = self.compute_beta(positions)

        open_count = sum(1 for p in positions.values() if p.get("status") == "OPEN")

        result = {
            **var_result,
            **corr_result,
            **beta_result,
            "open_positions": open_count,
            "capital_inr":    capital,
            "computed_at":    datetime.now().strftime("%d %b %Y %H:%M"),
        }

        shared_state["risk_analytics"] = result
        log.info(
            f"RiskAnalytics: {open_count} open positions | "
            f"VaR95={var_result['var_95_pct']}% | "
            f"β={beta_result['portfolio_beta']} ({beta_result['beta_status']}) | "
            f"MaxCorr={corr_result['max_corr']}"
        )
        return result
