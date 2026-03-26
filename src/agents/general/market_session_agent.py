"""
Market Session Agent — StockGuru SAHI Integration
Tracks all 4 market segments (IST):
  - NSE Equity  : 09:15 – 15:30
  - NSE F&O     : 09:15 – 15:30
  - MCX Commodity: 09:00 – 23:30
  - NSE Currency : 09:00 – 17:00
Provides session state, open/close event hooks, and pre-open window detection.
"""

import datetime
import pytz
import logging
from typing import Dict, Callable, List, Optional

log = logging.getLogger("market_session_agent")

IST = pytz.timezone("Asia/Kolkata")

# ── Market Segment Definitions ──────────────────────────────────────────────
SEGMENTS = {
    "NSE_EQUITY": {
        "name":        "NSE Equity",
        "open":        datetime.time(9, 15),
        "close":       datetime.time(15, 30),
        "pre_open":    datetime.time(9, 0),   # pre-open session starts
        "post_close":  datetime.time(15, 35),
        "days":        {0, 1, 2, 3, 4},       # Mon–Fri
        "icon":        "📈",
        "color":       "#00E676",
    },
    "NSE_FNO": {
        "name":        "NSE F&O",
        "open":        datetime.time(9, 15),
        "close":       datetime.time(15, 30),
        "pre_open":    datetime.time(9, 0),
        "post_close":  datetime.time(15, 35),
        "days":        {0, 1, 2, 3, 4},
        "icon":        "📊",
        "color":       "#00C4CC",
    },
    "MCX": {
        "name":        "MCX Commodity",
        "open":        datetime.time(9, 0),
        "close":       datetime.time(23, 30),
        "pre_open":    datetime.time(8, 45),
        "post_close":  datetime.time(23, 45),
        "days":        {0, 1, 2, 3, 4},
        "icon":        "🥇",
        "color":       "#FFD700",
    },
    "NSE_CURRENCY": {
        "name":        "NSE Currency",
        "open":        datetime.time(9, 0),
        "close":       datetime.time(17, 0),
        "pre_open":    datetime.time(8, 45),
        "post_close":  datetime.time(17, 5),
        "days":        {0, 1, 2, 3, 4},
        "icon":        "💱",
        "color":       "#FF9800",
    },
}

# ── Holiday list (NSE/BSE/MCX) – add dates as needed ────────────────────────
NSE_HOLIDAYS_2025 = {
    datetime.date(2025, 1, 26),   # Republic Day
    datetime.date(2025, 3, 14),   # Holi
    datetime.date(2025, 4, 14),   # Dr. Ambedkar Jayanti / Good Friday
    datetime.date(2025, 4, 18),   # Good Friday (MCX variant)
    datetime.date(2025, 5, 1),    # Maharashtra Day
    datetime.date(2025, 8, 15),   # Independence Day
    datetime.date(2025, 10, 2),   # Gandhi Jayanti
    datetime.date(2025, 10, 24),  # Dussehra
    datetime.date(2025, 11, 5),   # Diwali Laxmi Pujan
    datetime.date(2025, 12, 25),  # Christmas
}
NSE_HOLIDAYS_2026 = {
    datetime.date(2026, 1, 26),   # Republic Day
    datetime.date(2026, 3, 20),   # Holi
    datetime.date(2026, 4, 3),    # Good Friday
    datetime.date(2026, 5, 1),    # Maharashtra Day
    datetime.date(2026, 8, 15),   # Independence Day
    datetime.date(2026, 10, 2),   # Gandhi Jayanti
    datetime.date(2026, 11, 11),  # Diwali Laxmi Pujan (tentative)
    datetime.date(2026, 12, 25),  # Christmas
}
MARKET_HOLIDAYS = NSE_HOLIDAYS_2025 | NSE_HOLIDAYS_2026


# ── Session State Constants ──────────────────────────────────────────────────
STATE_CLOSED    = "CLOSED"
STATE_PRE_OPEN  = "PRE_OPEN"
STATE_OPEN      = "OPEN"
STATE_CLOSING   = "CLOSING"   # last 5 minutes
STATE_POST      = "POST"


class MarketSessionAgent:
    """
    Singleton-style agent that tracks market session states and fires callbacks
    on open/close events. Call `tick()` periodically (every 30–60 seconds).
    """

    def __init__(self):
        # Last known state per segment
        self._last_state: Dict[str, str] = {seg: STATE_CLOSED for seg in SEGMENTS}
        # Registered callbacks: {event_type: [callable]}
        # event_type: "open_<SEG>", "close_<SEG>", "pre_open_<SEG>"
        self._callbacks: Dict[str, List[Callable]] = {}
        self._initialized = False

    # ── Public API ────────────────────────────────────────────────────────────

    def now_ist(self) -> datetime.datetime:
        return datetime.datetime.now(IST)

    def is_holiday(self, date: Optional[datetime.date] = None) -> bool:
        if date is None:
            date = self.now_ist().date()
        return date in MARKET_HOLIDAYS

    def get_session_state(self, segment: str) -> str:
        """Return current session state for the given segment key."""
        seg = SEGMENTS.get(segment)
        if not seg:
            return STATE_CLOSED
        now = self.now_ist()
        today = now.date()
        t = now.time()

        # Weekend or holiday check
        if now.weekday() not in seg["days"] or self.is_holiday(today):
            return STATE_CLOSED

        o  = seg["open"]
        c  = seg["close"]
        po = seg["pre_open"]
        pc = seg["post_close"]

        if t < po:
            return STATE_CLOSED
        if po <= t < o:
            return STATE_PRE_OPEN
        # Closing window: last 5 minutes
        closing_start = (datetime.datetime.combine(today, c) - datetime.timedelta(minutes=5)).time()
        if o <= t < closing_start:
            return STATE_OPEN
        if closing_start <= t <= c:
            return STATE_CLOSING
        if c < t <= pc:
            return STATE_POST
        return STATE_CLOSED

    def is_market_open(self, segment: str) -> bool:
        return self.get_session_state(segment) in (STATE_OPEN, STATE_CLOSING)

    def any_market_open(self) -> bool:
        return any(self.is_market_open(seg) for seg in SEGMENTS)

    def get_all_states(self) -> Dict[str, dict]:
        """Return dict of segment → state info for UI display."""
        result = {}
        for seg_key, seg_def in SEGMENTS.items():
            state = self.get_session_state(seg_key)
            now = self.now_ist()
            today = now.date()
            # Time to next event
            next_event = None
            next_event_label = ""
            if state == STATE_CLOSED:
                if now.weekday() in seg_def["days"] and not self.is_holiday(today):
                    # Opens today?
                    open_dt = IST.localize(datetime.datetime.combine(today, seg_def["pre_open"]))
                    if now < open_dt:
                        diff = open_dt - now
                        next_event = int(diff.total_seconds())
                        next_event_label = f"Pre-open in {_fmt_td(diff)}"
            elif state == STATE_PRE_OPEN:
                open_dt = IST.localize(datetime.datetime.combine(today, seg_def["open"]))
                diff = open_dt - now
                next_event = int(diff.total_seconds())
                next_event_label = f"Opens in {_fmt_td(diff)}"
            elif state in (STATE_OPEN, STATE_CLOSING):
                close_dt = IST.localize(datetime.datetime.combine(today, seg_def["close"]))
                diff = close_dt - now
                next_event = int(diff.total_seconds())
                next_event_label = f"Closes in {_fmt_td(diff)}"

            result[seg_key] = {
                "name":              seg_def["name"],
                "state":             state,
                "is_open":           self.is_market_open(seg_key),
                "icon":              seg_def["icon"],
                "color":             seg_def["color"],
                "open_time":         seg_def["open"].strftime("%H:%M"),
                "close_time":        seg_def["close"].strftime("%H:%M"),
                "next_event_secs":   next_event,
                "next_event_label":  next_event_label,
            }
        return result

    def get_active_segments(self) -> List[str]:
        """Return list of segment keys currently open."""
        return [seg for seg in SEGMENTS if self.is_market_open(seg)]

    # ── Callback Registration ─────────────────────────────────────────────────

    def on_open(self, segment: str, fn: Callable):
        """Register a callback fired when a segment opens."""
        key = f"open_{segment}"
        self._callbacks.setdefault(key, []).append(fn)

    def on_close(self, segment: str, fn: Callable):
        """Register a callback fired when a segment closes."""
        key = f"close_{segment}"
        self._callbacks.setdefault(key, []).append(fn)

    def on_pre_open(self, segment: str, fn: Callable):
        """Register a callback fired when pre-open session starts."""
        key = f"pre_open_{segment}"
        self._callbacks.setdefault(key, []).append(fn)

    # ── Tick (called by scheduler) ────────────────────────────────────────────

    def tick(self):
        """
        Call every 30–60 seconds from the Flask APScheduler.
        Detects state transitions and fires registered callbacks.
        """
        for seg_key in SEGMENTS:
            new_state = self.get_session_state(seg_key)
            old_state = self._last_state.get(seg_key, STATE_CLOSED)

            if self._initialized and new_state != old_state:
                self._fire_transition(seg_key, old_state, new_state)

            self._last_state[seg_key] = new_state

        if not self._initialized:
            self._initialized = True

    def _fire_transition(self, segment: str, old: str, new: str):
        seg_def = SEGMENTS[segment]
        log.info(f"[SessionAgent] {seg_def['name']}: {old} → {new}")

        if new == STATE_PRE_OPEN:
            self._emit(f"pre_open_{segment}", segment, seg_def)
        elif new == STATE_OPEN and old in (STATE_CLOSED, STATE_PRE_OPEN):
            self._emit(f"open_{segment}", segment, seg_def)
        elif new in (STATE_CLOSED, STATE_POST) and old in (STATE_OPEN, STATE_CLOSING):
            self._emit(f"close_{segment}", segment, seg_def)

    def _emit(self, event_key: str, segment: str, seg_def: dict):
        for fn in self._callbacks.get(event_key, []):
            try:
                fn(segment=segment, seg_def=seg_def, agent=self)
            except Exception as e:
                log.error(f"[SessionAgent] Callback error for {event_key}: {e}")

    # ── Status Summary ────────────────────────────────────────────────────────

    def status_summary(self) -> str:
        """One-line status string for logging / Telegram."""
        now = self.now_ist().strftime("%H:%M IST")
        parts = []
        for seg_key, seg_def in SEGMENTS.items():
            state = self.get_session_state(seg_key)
            icon = "🟢" if state == STATE_OPEN else "🟡" if state in (STATE_PRE_OPEN, STATE_CLOSING) else "🔴"
            parts.append(f"{icon} {seg_def['name']}: {state}")
        return f"[{now}] " + "  |  ".join(parts)


def _fmt_td(td: datetime.timedelta) -> str:
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ── Module-level singleton ────────────────────────────────────────────────────
session_agent = MarketSessionAgent()
