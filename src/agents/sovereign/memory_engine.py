# ══════════════════════════════════════════════════════════════════════════════
# StockGuru Sovereign — Memory Engine
# SQLite-backed persistent trade memory. Local now → Qdrant-ready later.
# ══════════════════════════════════════════════════════════════════════════════
import sqlite3, json, logging, os
from datetime import datetime

log = logging.getLogger("sovereign.memory")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "agent_memory.db")
DB_PATH = os.path.normpath(DB_PATH)

_conn = None  # module-level singleton connection

# ─────────────────────────────────────────────────────────────────────────────
def _get_conn():
    """Return (or create) the SQLite connection — thread-safe check_same_thread=False."""
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _create_tables(_conn)
        log.info("✅ Memory Engine: SQLite opened at %s", DB_PATH)
    return _conn


def _create_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS memories (
        trade_id   TEXT PRIMARY KEY,
        ticker     TEXT NOT NULL,
        sector     TEXT,
        timestamp  TEXT NOT NULL,
        outcome    TEXT NOT NULL,
        metadata   TEXT,
        reflexion  TEXT,
        root_cause TEXT,
        applied    INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_ticker    ON memories(ticker);
    CREATE INDEX IF NOT EXISTS idx_sector    ON memories(sector);
    CREATE INDEX IF NOT EXISTS idx_outcome   ON memories(outcome);
    CREATE INDEX IF NOT EXISTS idx_timestamp ON memories(timestamp);

    CREATE TABLE IF NOT EXISTS config_history (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        agent     TEXT NOT NULL,
        key_path  TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        reason    TEXT
    );
    """)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC WRITE
# ─────────────────────────────────────────────────────────────────────────────

def store_lesson(trade_id: str, ticker: str, sector: str, outcome: str,
                 metadata: dict, reflexion: str, root_cause: str = None) -> bool:
    """
    Store (or update) a trade lesson.
    outcome: 'SUCCESS' | 'FAILURE' | 'PARTIAL'
    root_cause: 'TIMING' | 'SECTOR' | 'MACRO' | 'OVEREXTENDED' | 'FAKE_OUT' | None
    """
    try:
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO memories
            (trade_id, ticker, sector, timestamp, outcome, metadata, reflexion, root_cause, applied)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            trade_id, ticker.upper(), sector,
            datetime.now().isoformat(),
            outcome, json.dumps(metadata or {}),
            reflexion, root_cause
        ))
        conn.commit()
        log.info("💾 Memory stored: %s [%s] %s", ticker, outcome, root_cause or "")
        return True
    except Exception as e:
        log.error("Memory store error: %s", e)
        return False


def log_config_change(agent: str, key_path: str, old_val, new_val, reason: str):
    """Track every sovereign_config.json modification for audit trail."""
    try:
        conn = _get_conn()
        conn.execute("""
            INSERT INTO config_history (timestamp, agent, key_path, old_value, new_value, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), agent, key_path,
              str(old_val), str(new_val), reason))
        conn.commit()
    except Exception as e:
        log.error("Config history log error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC READ
# ─────────────────────────────────────────────────────────────────────────────

def get_recent_lessons(ticker: str, limit: int = 3) -> list:
    """
    Returns list of plain-English reflexion strings for a ticker.
    Called by HITL Controller to show memory context in Telegram message.
    """
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT outcome, reflexion, root_cause, timestamp
            FROM memories
            WHERE ticker = ? AND reflexion IS NOT NULL
            ORDER BY timestamp DESC LIMIT ?
        """, (ticker.upper(), limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_recent_lessons error: %s", e)
        return []


def get_sector_lessons(sector: str, outcome: str = "FAILURE", limit: int = 5) -> list:
    """Returns failure patterns for a sector. Used by Post-Mortem and Debate Bear."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT ticker, reflexion, root_cause, metadata, timestamp
            FROM memories
            WHERE sector = ? AND outcome = ? AND reflexion IS NOT NULL
            ORDER BY timestamp DESC LIMIT ?
        """, (sector, outcome, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_sector_lessons error: %s", e)
        return []


def get_recent_failures(limit: int = 10) -> list:
    """All recent failures across all tickers — for Post-Mortem analysis."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT trade_id, ticker, sector, outcome, metadata, reflexion, root_cause, timestamp
            FROM memories
            WHERE outcome = 'FAILURE'
            ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            result.append(d)
        return result
    except Exception as e:
        log.error("get_recent_failures error: %s", e)
        return []


def get_all_recent(limit: int = 20) -> list:
    """All recent memories — for the Sovereign dashboard panel."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT trade_id, ticker, sector, outcome, reflexion, root_cause, timestamp
            FROM memories
            ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_all_recent error: %s", e)
        return []


def get_ticker_stats(ticker: str) -> dict:
    """Win/loss record and common root causes for a ticker."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT outcome, root_cause, COUNT(*) as cnt
            FROM memories
            WHERE ticker = ?
            GROUP BY outcome, root_cause
        """, (ticker.upper(),)).fetchall()
        stats = {"ticker": ticker, "SUCCESS": 0, "FAILURE": 0, "PARTIAL": 0, "root_causes": {}}
        for r in rows:
            stats[r["outcome"]] = stats.get(r["outcome"], 0) + r["cnt"]
            if r["root_cause"]:
                stats["root_causes"][r["root_cause"]] = r["cnt"]
        total = stats["SUCCESS"] + stats["FAILURE"] + stats["PARTIAL"]
        stats["total"] = total
        stats["win_rate"] = round(stats["SUCCESS"] / total, 3) if total > 0 else None
        return stats
    except Exception as e:
        log.error("get_ticker_stats error: %s", e)
        return {}


def format_memory_context(ticker: str) -> str:
    """
    Returns a 1-line summary of memory for a ticker.
    Used in HITL Telegram message under 💭 Memory:
    """
    lessons = get_recent_lessons(ticker, limit=3)
    if not lessons:
        return f"No prior memory on {ticker}"
    last = lessons[0]
    outcome_emoji = "✅" if last["outcome"] == "SUCCESS" else ("⚠️" if last["outcome"] == "PARTIAL" else "❌")
    rc = last.get("root_cause") or "unknown"
    refl = (last.get("reflexion") or "")[:80]
    return f"{outcome_emoji} Last {last['outcome']}: {rc} — {refl}"


def get_config_history(limit: int = 20) -> list:
    """Returns recent sovereign_config.json changes."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT * FROM config_history ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_config_history error: %s", e)
        return []
