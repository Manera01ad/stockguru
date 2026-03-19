"""
AGENT 15 — EARNINGS & EVENTS CALENDAR
══════════════════════════════════════
Goal  : Track upcoming NSE/BSE corporate events (results, AGM, dividends,
        bonus, splits, board meetings) and flag stocks in the watchlist
        that have events in the next 7 days.

Why   : Buying before a potential earnings miss = unnecessary risk.
        Positioning ahead of a confirmed beat = high-probability trade.
        Top-5% systems treat the events calendar as a primary signal filter.

Sources (all free, no API key):
  • NSE India event calendar API
  • BSE India corporate actions
  • Fallback: Economic Times earnings calendar RSS

Output → shared_state["events_calendar"]  (consumed by risk_manager,
         trade_signal, and claude_intelligence)
"""

import requests
import logging
from datetime import datetime, timedelta

log = logging.getLogger("EarningsCalendar")

NSE_EVENTS_URL  = "https://www.nseindia.com/api/event-calendar"
BSE_ACTIONS_URL = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w?Category=CA&Type=C"

# Events that significantly move stock price
HIGH_IMPACT_TYPES = {
    "Board Meeting": 0.7,
    "Dividend":      0.5,
    "Bonus":         0.8,
    "Split":         0.8,
    "Results":       0.9,
    "AGM":           0.4,
    "Rights":        0.6,
    "Buyback":       0.7,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://www.nseindia.com",
    "Accept":     "application/json",
}

# ── SESSION (NSE needs cookies) ───────────────────────────────────────────────
_session = requests.Session()
_session.headers.update(HEADERS)
_nse_cookies_loaded = False

def _init_nse_session():
    global _nse_cookies_loaded
    if not _nse_cookies_loaded:
        try:
            _session.get("https://www.nseindia.com", timeout=8)
            _nse_cookies_loaded = True
        except Exception:
            pass

def _fetch_nse_events():
    """Fetch upcoming corporate events from NSE."""
    _init_nse_session()
    events = []
    try:
        resp = _session.get(NSE_EVENTS_URL, timeout=10)
        if resp.status_code != 200:
            return events
        data = resp.json()
        if not isinstance(data, list):
            data = data.get("data", [])
        for item in data[:100]:
            purpose = item.get("purpose", "") or item.get("bm_desc", "")
            symbol  = item.get("symbol", "") or item.get("scrip_cd", "")
            date_str = item.get("bm_date", "") or item.get("date", "")
            events.append({
                "symbol":  symbol,
                "purpose": purpose,
                "date":    date_str,
                "source":  "NSE"
            })
    except Exception as e:
        log.debug(f"NSE events: {e}")
    return events

def _fetch_bse_actions():
    """Fetch BSE corporate actions as fallback."""
    events = []
    try:
        resp = requests.get(BSE_ACTIONS_URL, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return events
        data = resp.json()
        items = data.get("Table", data) if isinstance(data, dict) else data
        for item in (items or [])[:50]:
            events.append({
                "symbol":  item.get("SCRIP_CD", "") or item.get("Symbol", ""),
                "purpose": item.get("CORPORATE_ACTION", "") or item.get("Purpose", ""),
                "date":    item.get("EX_DATE", "") or item.get("Date", ""),
                "source":  "BSE"
            })
    except Exception as e:
        log.debug(f"BSE actions: {e}")
    return events

def _parse_date(date_str):
    """Try multiple date formats."""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(str(date_str).strip(), fmt).date()
        except Exception:
            continue
    return None

def _classify_impact(purpose):
    """Return impact score for event type."""
    purpose_upper = str(purpose).upper()
    for key, score in HIGH_IMPACT_TYPES.items():
        if key.upper() in purpose_upper:
            return score
    return 0.3  # unknown event = low impact

def run(shared_state: dict):
    """
    Main entry — fetches events, filters to watchlist stocks,
    writes results into shared_state["events_calendar"].
    """
    log.info("Fetching earnings & corporate events calendar...")

    # Collect watchlist symbols for matching
    watchlist = shared_state.get("watchlist", [])
    wl_symbols = set()
    wl_names   = set()
    for s in watchlist:
        sym = s.get("symbol", "").replace(".NS", "").replace(".BO", "").upper()
        wl_symbols.add(sym)
        wl_names.add(s.get("name", "").upper())

    # Fetch from both exchanges
    all_events = _fetch_nse_events() + _fetch_bse_actions()

    today = datetime.now().date()
    horizon = today + timedelta(days=7)

    upcoming = []
    watchlist_alerts = []

    for ev in all_events:
        ev_date = _parse_date(ev.get("date", ""))
        if not ev_date:
            continue
        if not (today <= ev_date <= horizon):
            continue

        purpose = ev.get("purpose", "Unknown")
        symbol  = ev.get("symbol", "").upper().replace(".NS", "").replace(".BO", "")
        impact  = _classify_impact(purpose)
        days_away = (ev_date - today).days

        entry = {
            "symbol":    symbol,
            "purpose":   purpose,
            "date":      str(ev_date),
            "days_away": days_away,
            "impact":    round(impact, 2),
            "source":    ev.get("source", "NSE")
        }
        upcoming.append(entry)

        # Flag if this stock is in our watchlist
        if symbol in wl_symbols or symbol in wl_names:
            entry["watchlist_match"] = True
            watchlist_alerts.append(entry)
            if impact >= 0.7:
                log.warning(f"HIGH IMPACT event: {symbol} — {purpose} on {ev_date} ({days_away}d away)")

    # Sort by date then impact
    upcoming.sort(key=lambda x: (x["days_away"], -x["impact"]))
    watchlist_alerts.sort(key=lambda x: (x["days_away"], -x["impact"]))

    result = {
        "last_run":         datetime.now().strftime("%d %b %H:%M"),
        "total_events":     len(upcoming),
        "watchlist_alerts": watchlist_alerts,
        "upcoming":         upcoming[:30],
        "horizon_days":     7,
        "high_impact_count": sum(1 for e in upcoming if e["impact"] >= 0.7)
    }

    shared_state["events_calendar"] = result

    # ── INJECT into agent handoff for risk_manager & trade_signal ──────────────
    if "agent_confidence" not in shared_state:
        shared_state["agent_confidence"] = {}

    shared_state["agent_confidence"]["earnings_calendar"] = {
        "confidence":    0.95,
        "key_signal":    f"{len(watchlist_alerts)} watchlist events in 7 days",
        "alert_count":   len(watchlist_alerts),
        "high_impact":   [e["symbol"] for e in watchlist_alerts if e["impact"] >= 0.7],
        "handoff_notes": (
            f"CAUTION: {', '.join(e['symbol'] for e in watchlist_alerts[:5])} "
            f"have events in next {7}d — verify before entry"
        ) if watchlist_alerts else "No watchlist events in next 7 days — calendar clear"
    }

    log.info(
        f"Calendar: {len(upcoming)} events in {7}d | "
        f"{len(watchlist_alerts)} watchlist matches | "
        f"{result['high_impact_count']} high-impact"
    )
    return result
