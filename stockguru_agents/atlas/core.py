# ══════════════════════════════════════════════════════════════════════════════
# ATLAS CORE — Central Knowledge Hub
# ══════════════════════════════════════════════════════════════════════════════
# The brain of the self-learning system. Every agent reads from and writes to
# this central store. Think of it as the market's long-term memory.
#
# What it stores:
#   • Every trade entry with FULL multi-dimensional context snapshot
#   • Options flow state at time of entry
#   • News sentiment score at time of entry
#   • Market regime at time of entry
#   • Volume classification at time of entry
#   • Causal analysis of why it worked/failed
#   • Self-generated trading rules from synthesis
#
# What it enables:
#   • "What happened the last 10 times PCR was this low + volume spiked?"
#   • "Which news keywords caused >3% moves in Banking sector?"
#   • "What regime were we in during the best 20% of our trades?"
#   • "What volume pattern precedes our biggest winners?"
# ══════════════════════════════════════════════════════════════════════════════

import sqlite3
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("atlas.core")

# DB lives in /tmp (fast, no filesystem restrictions) and exports JSON snapshots to data/
# for persistence across sessions. On restart, data is reloaded from JSON snapshot.
_MNT_BASE     = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
DB_PATH       = "/tmp/stockguru_atlas.db"        # fast, no NTFS journal restriction
SNAPSHOT_PATH = os.path.join(_MNT_BASE, "atlas_snapshot.json")   # persistent export
RULES_PATH    = os.path.join(_MNT_BASE, "atlas_rules.json")
_BASE         = _MNT_BASE

_conn = None  # singleton


# ─────────────────────────────────────────────────────────────────────────────
# DB SETUP
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn():
    global _conn
    if _conn is None:
        os.makedirs(_MNT_BASE, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _create_tables(_conn)
        # Restore from JSON snapshot if /tmp DB is empty (e.g. after restart)
        count = _conn.execute("SELECT COUNT(*) FROM knowledge_events").fetchone()[0]
        if count == 0 and os.path.exists(SNAPSHOT_PATH):
            _restore_from_snapshot(_conn)
        log.info("✅ ATLAS Core: Knowledge DB at %s (%d events)", DB_PATH, count)
    return _conn


def _restore_from_snapshot(conn) -> int:
    """Reload knowledge events from JSON snapshot into /tmp DB after restart."""
    try:
        with open(SNAPSHOT_PATH) as f:
            snap = json.load(f)
        events = snap.get("events", [])
        restored = 0
        for ev in events:
            try:
                cols = ", ".join(ev.keys())
                placeholders = ", ".join(["?"] * len(ev))
                conn.execute(
                    f"INSERT OR IGNORE INTO knowledge_events ({cols}) VALUES ({placeholders})",
                    list(ev.values())
                )
                restored += 1
            except Exception:
                pass
        conn.commit()
        log.info("🔄 ATLAS: Restored %d events from snapshot", restored)
        return restored
    except Exception as e:
        log.warning("ATLAS snapshot restore failed: %s", e)
        return 0


def _export_snapshot() -> bool:
    """Export current knowledge_events to JSON snapshot for persistence."""
    try:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM knowledge_events ORDER BY timestamp DESC LIMIT 500").fetchall()
        events = [dict(r) for r in rows]
        snap = {
            "events":       events,
            "exported_at":  datetime.now().isoformat(),
            "count":        len(events),
        }
        os.makedirs(_MNT_BASE, exist_ok=True)
        with open(SNAPSHOT_PATH, "w") as f:
            json.dump(snap, f, indent=2, default=str)
        log.debug("💾 ATLAS: Snapshot exported (%d events)", len(events))
        return True
    except Exception as e:
        log.warning("ATLAS snapshot export failed: %s", e)
        return False


def _create_tables(conn):
    conn.executescript("""
    -- ── MASTER KNOWLEDGE EVENTS ──────────────────────────────────────────────
    -- Every trade captured with full multi-dimensional context snapshot
    CREATE TABLE IF NOT EXISTS knowledge_events (
        event_id        TEXT PRIMARY KEY,
        ticker          TEXT NOT NULL,
        sector          TEXT,
        instrument_type TEXT DEFAULT 'EQUITY',  -- EQUITY / CE / PE / FUTURES
        timestamp       TEXT NOT NULL,

        -- Entry context
        entry_price     REAL,
        signal_type     TEXT,                   -- STRONG BUY / BUY / SELL
        entry_score     REAL,
        gates_passed    INTEGER,

        -- Technical snapshot at entry
        rsi             REAL,
        macd_cross      TEXT,                   -- BULL / BEAR / NONE
        ema_position    TEXT,                   -- ABOVE_50 / ABOVE_200 / BELOW_50 / BELOW_200
        trend_strength  TEXT,                   -- STRONG / MODERATE / WEAK

        -- Options flow snapshot at entry
        pcr_nifty       REAL,
        pcr_banknifty   REAL,
        max_pain_nifty  REAL,
        iv_percentile   REAL,
        unusual_oi      INTEGER DEFAULT 0,       -- 1 if unusual OI spike detected
        options_signal  TEXT,                   -- BULLISH / BEARISH / NEUTRAL

        -- News context at entry
        news_sentiment_score   REAL,            -- -1.0 to +1.0
        news_event_type        TEXT,            -- EARNINGS / RBI / MACRO / SECTOR / STOCK / NONE
        news_impact_magnitude  TEXT,            -- HIGH / MEDIUM / LOW / NONE
        news_keywords          TEXT,            -- JSON array of top keywords

        -- Volume classification
        volume_class    TEXT,                   -- ACCUMULATION / DISTRIBUTION / CLIMAX / BREAKOUT / DRY_UP / NORMAL
        volume_ratio    REAL,                   -- current vol / 20-day avg
        volume_signal   TEXT,                   -- STRONG_BUY / BUY / CAUTION / SELL

        -- Market regime at entry
        regime          TEXT,                   -- BULL_TREND / BEAR_TREND / SIDEWAYS / VOLATILE
        regime_strength REAL,                   -- 0.0 to 1.0
        market_session  TEXT,                   -- PRE_OPEN / FIRST_HOUR / MID / LAST_HOUR / POST
        day_of_week     TEXT,                   -- MON / TUE / WED / THU / FRI
        week_type       TEXT,                   -- EXPIRY / BUDGET / EARNINGS / NORMAL
        time_hour       INTEGER,                -- 9-15

        -- Fundamental snapshot
        sector_momentum TEXT,                   -- STRONG / NEUTRAL / WEAK
        fii_flow        TEXT,                   -- BUYING / SELLING / NEUTRAL
        dii_flow        TEXT,

        -- Outcome (updated later)
        outcome         TEXT DEFAULT 'OPEN',    -- T2_HIT / T1_HIT / SL_HIT / EXPIRED / OPEN
        exit_price      REAL,
        exit_at         TEXT,
        pnl_pct         REAL,
        max_favorable_move  REAL,               -- best price seen before exit
        max_adverse_move    REAL,               -- worst price seen before exit
        hold_duration_hrs   REAL,

        -- Causal analysis (filled by causal_engine post-trade)
        primary_cause       TEXT,               -- what ACTUALLY drove the move
        secondary_causes    TEXT,               -- JSON array of contributing factors
        failure_reason      TEXT,               -- if SL_HIT: why it failed
        lesson_extracted    TEXT,               -- one-line lesson for the agent

        created_at      TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_ke_ticker    ON knowledge_events(ticker);
    CREATE INDEX IF NOT EXISTS idx_ke_sector    ON knowledge_events(sector);
    CREATE INDEX IF NOT EXISTS idx_ke_outcome   ON knowledge_events(outcome);
    CREATE INDEX IF NOT EXISTS idx_ke_regime    ON knowledge_events(regime);
    CREATE INDEX IF NOT EXISTS idx_ke_vol_class ON knowledge_events(volume_class);
    CREATE INDEX IF NOT EXISTS idx_ke_timestamp ON knowledge_events(timestamp);

    -- ── PATTERN CORRELATIONS ──────────────────────────────────────────────────
    -- Cross-dimensional patterns: which combos of conditions produce wins
    CREATE TABLE IF NOT EXISTS pattern_correlations (
        pattern_id      TEXT PRIMARY KEY,
        dimensions      TEXT NOT NULL,          -- JSON: {pcr_zone, volume_class, regime, news_type...}
        dimension_key   TEXT NOT NULL,          -- human-readable combo key for indexing
        win_count       INTEGER DEFAULT 0,
        loss_count      INTEGER DEFAULT 0,
        avg_win_pct     REAL DEFAULT 0.0,
        avg_loss_pct    REAL DEFAULT 0.0,
        avg_hold_hrs    REAL DEFAULT 0.0,
        quality         TEXT DEFAULT 'LEARNING', -- GOLD / SILVER / LEARNING
        last_seen_at    TEXT,
        first_seen_at   TEXT,
        updated_at      TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_pc_dim_key ON pattern_correlations(dimension_key);
    CREATE INDEX IF NOT EXISTS idx_pc_quality ON pattern_correlations(quality);

    -- ── ATLAS RULES ───────────────────────────────────────────────────────────
    -- Auto-generated trading rules from the self-upgrader
    CREATE TABLE IF NOT EXISTS atlas_rules (
        rule_id         TEXT PRIMARY KEY,
        rule_text       TEXT NOT NULL,          -- the actual rule in plain English
        rule_type       TEXT,                   -- ENTRY / EXIT / AVOID / SIZING / TIMING
        confidence      REAL DEFAULT 0.5,       -- 0.0 to 1.0
        supporting_evidence TEXT,               -- JSON: pattern_ids that support this rule
        win_rate_basis  REAL,                   -- win rate of trades following this rule
        trade_count     INTEGER DEFAULT 0,
        active          INTEGER DEFAULT 1,
        created_at      TEXT,
        last_validated  TEXT
    );

    -- ── KNOWLEDGE SYNTHESIS LOG ───────────────────────────────────────────────
    -- Record of every nightly synthesis run
    CREATE TABLE IF NOT EXISTS synthesis_log (
        run_id          TEXT PRIMARY KEY,
        run_at          TEXT NOT NULL,
        events_analyzed INTEGER DEFAULT 0,
        patterns_found  INTEGER DEFAULT 0,
        rules_generated INTEGER DEFAULT 0,
        rules_retired   INTEGER DEFAULT 0,
        top_insight     TEXT,
        summary         TEXT
    );
    """)
    conn.commit()
    log.debug("ATLAS: All tables created/verified")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: LOG TRADE ENTRY
# ─────────────────────────────────────────────────────────────────────────────

def log_trade_entry(
    event_id: str,
    ticker: str,
    sector: str,
    entry_price: float,
    signal_type: str,
    entry_score: float,
    gates_passed: int,
    # Technical
    rsi: float = None,
    macd_cross: str = None,
    ema_position: str = None,
    trend_strength: str = None,
    # Options
    pcr_nifty: float = None,
    pcr_banknifty: float = None,
    max_pain_nifty: float = None,
    iv_percentile: float = None,
    unusual_oi: bool = False,
    options_signal: str = None,
    # News
    news_sentiment_score: float = None,
    news_event_type: str = None,
    news_impact_magnitude: str = None,
    news_keywords: list = None,
    # Volume
    volume_class: str = None,
    volume_ratio: float = None,
    volume_signal: str = None,
    # Regime
    regime: str = None,
    regime_strength: float = None,
    market_session: str = None,
    day_of_week: str = None,
    week_type: str = None,
    # Fundamental
    sector_momentum: str = None,
    fii_flow: str = None,
    dii_flow: str = None,
    # Instrument
    instrument_type: str = "EQUITY",
) -> bool:
    """
    Called by paper_trader immediately when a trade is entered.
    Captures a full multi-dimensional snapshot of market conditions.
    """
    try:
        now = datetime.now()
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO knowledge_events (
                event_id, ticker, sector, instrument_type, timestamp,
                entry_price, signal_type, entry_score, gates_passed,
                rsi, macd_cross, ema_position, trend_strength,
                pcr_nifty, pcr_banknifty, max_pain_nifty, iv_percentile,
                unusual_oi, options_signal,
                news_sentiment_score, news_event_type, news_impact_magnitude, news_keywords,
                volume_class, volume_ratio, volume_signal,
                regime, regime_strength, market_session, day_of_week, week_type, time_hour,
                sector_momentum, fii_flow, dii_flow,
                outcome, created_at
            ) VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?,?,?, ?,?,?, ?, ?)
        """, (
            event_id, ticker.upper(), sector, instrument_type, now.isoformat(),
            entry_price, signal_type, entry_score, gates_passed,
            rsi, macd_cross, ema_position, trend_strength,
            pcr_nifty, pcr_banknifty, max_pain_nifty, iv_percentile,
            1 if unusual_oi else 0, options_signal,
            news_sentiment_score, news_event_type, news_impact_magnitude,
            json.dumps(news_keywords or []),
            volume_class, volume_ratio, volume_signal,
            regime, regime_strength, market_session,
            now.strftime("%A")[:3].upper(),  # MON/TUE/...
            week_type or "NORMAL",
            now.hour,
            sector_momentum, fii_flow, dii_flow,
            "OPEN", now.isoformat()
        ))
        conn.commit()
        log.info("🧠 ATLAS: Logged entry for %s [%s] score=%.0f pcr=%.2f vol=%s regime=%s",
                 ticker, signal_type, entry_score or 0,
                 pcr_nifty or 0, volume_class or "?", regime or "?")
        _export_snapshot()   # persist to mnt JSON
        return True
    except Exception as e:
        log.error("ATLAS log_trade_entry error: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: UPDATE TRADE OUTCOME
# ─────────────────────────────────────────────────────────────────────────────

def update_trade_outcome(
    event_id: str,
    outcome: str,
    exit_price: float,
    pnl_pct: float,
    max_favorable_move: float = None,
    max_adverse_move: float = None,
    hold_duration_hrs: float = None,
) -> bool:
    """
    Called when a trade closes (T1/T2/SL/EXPIRED).
    Triggers pattern correlation update.
    """
    try:
        conn = _get_conn()
        conn.execute("""
            UPDATE knowledge_events
            SET outcome=?, exit_price=?, exit_at=?, pnl_pct=?,
                max_favorable_move=?, max_adverse_move=?, hold_duration_hrs=?
            WHERE event_id=?
        """, (outcome, exit_price, datetime.now().isoformat(), pnl_pct,
              max_favorable_move, max_adverse_move, hold_duration_hrs, event_id))
        conn.commit()

        # Fetch full event and update pattern correlations
        row = conn.execute(
            "SELECT * FROM knowledge_events WHERE event_id=?", (event_id,)
        ).fetchone()
        if row:
            _update_pattern_correlations(dict(row))

        log.info("🧠 ATLAS: Outcome updated %s → %s (P&L: %+.1f%%)",
                 event_id, outcome, pnl_pct or 0)
        return True
    except Exception as e:
        log.error("ATLAS update_outcome error: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: UPDATE CAUSAL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def update_causal_analysis(
    event_id: str,
    primary_cause: str,
    secondary_causes: list,
    failure_reason: str = None,
    lesson_extracted: str = None,
) -> bool:
    """Called by causal_engine after analyzing a closed trade."""
    try:
        conn = _get_conn()
        conn.execute("""
            UPDATE knowledge_events
            SET primary_cause=?, secondary_causes=?, failure_reason=?, lesson_extracted=?
            WHERE event_id=?
        """, (primary_cause, json.dumps(secondary_causes or []),
              failure_reason, lesson_extracted, event_id))
        conn.commit()
        return True
    except Exception as e:
        log.error("ATLAS update_causal error: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL: PATTERN CORRELATION TRACKING
# ─────────────────────────────────────────────────────────────────────────────

def _update_pattern_correlations(event: dict):
    """
    Build and update multi-dimensional pattern correlations from a closed event.
    Creates combinations of all relevant dimensions.
    """
    try:
        conn     = _get_conn()
        is_win   = event.get("outcome") in ("T1_HIT", "T2_HIT")
        pnl      = event.get("pnl_pct") or 0.0
        hold_hrs = event.get("hold_duration_hrs") or 0.0

        # Build dimension buckets
        dims = {
            "sector":     event.get("sector", "Unknown"),
            "regime":     event.get("regime", "UNKNOWN"),
            "vol_class":  event.get("volume_class", "UNKNOWN"),
            "pcr_zone":   _pcr_zone(event.get("pcr_nifty")),
            "news_type":  event.get("news_event_type", "NONE"),
            "day":        event.get("day_of_week", "UNK"),
            "session":    event.get("market_session", "UNKNOWN"),
            "week_type":  event.get("week_type", "NORMAL"),
            "fii":        event.get("fii_flow", "NEUTRAL"),
            "iv_zone":    _iv_zone(event.get("iv_percentile")),
        }

        # Generate combos (2-dim, 3-dim)
        combos = _generate_combos(dims)

        for combo_key, combo_dims in combos:
            pattern_id = f"PAT_{hash(combo_key) & 0xFFFFFFFF:08x}"
            existing = conn.execute(
                "SELECT * FROM pattern_correlations WHERE pattern_id=?", (pattern_id,)
            ).fetchone()

            if existing:
                e = dict(existing)
                new_wins   = e["win_count"] + (1 if is_win else 0)
                new_losses = e["loss_count"] + (0 if is_win else 1)
                total      = new_wins + new_losses
                new_avg_win  = (e["avg_win_pct"] * e["win_count"] + (pnl if is_win else 0)) / max(new_wins, 1)
                new_avg_loss = (e["avg_loss_pct"] * e["loss_count"] + (pnl if not is_win else 0)) / max(new_losses, 1)
                new_avg_hold = (e["avg_hold_hrs"] * (total-1) + hold_hrs) / total
                quality = _calc_quality(new_wins / total if total > 0 else 0, total)

                conn.execute("""
                    UPDATE pattern_correlations
                    SET win_count=?, loss_count=?, avg_win_pct=?, avg_loss_pct=?,
                        avg_hold_hrs=?, quality=?, last_seen_at=?, updated_at=?
                    WHERE pattern_id=?
                """, (new_wins, new_losses, round(new_avg_win, 2), round(new_avg_loss, 2),
                      round(new_avg_hold, 1), quality,
                      datetime.now().isoformat(), datetime.now().isoformat(), pattern_id))
            else:
                conn.execute("""
                    INSERT INTO pattern_correlations
                    (pattern_id, dimensions, dimension_key, win_count, loss_count,
                     avg_win_pct, avg_loss_pct, avg_hold_hrs, quality,
                     last_seen_at, first_seen_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (pattern_id, json.dumps(combo_dims), combo_key,
                      1 if is_win else 0, 0 if is_win else 1,
                      pnl if is_win else 0.0, 0.0 if is_win else pnl,
                      hold_hrs, "LEARNING",
                      datetime.now().isoformat(), datetime.now().isoformat(),
                      datetime.now().isoformat()))

        conn.commit()
    except Exception as e:
        log.error("ATLAS pattern correlation error: %s", e)


def _generate_combos(dims: dict) -> list:
    """Generate 2-D and 3-D dimension combos for pattern tracking."""
    combos = []
    keys = list(dims.keys())
    vals = list(dims.values())

    # 2-dim combos
    for i in range(len(keys)):
        for j in range(i+1, len(keys)):
            k = f"{keys[i]}:{vals[i]}|{keys[j]}:{vals[j]}"
            combos.append((k, {keys[i]: vals[i], keys[j]: vals[j]}))

    # 3-dim combos (prioritized combinations)
    priority_triples = [
        ("regime", "vol_class", "pcr_zone"),
        ("sector", "regime", "vol_class"),
        ("sector", "news_type", "fii"),
        ("regime", "pcr_zone", "news_type"),
        ("session", "vol_class", "regime"),
        ("week_type", "pcr_zone", "vol_class"),
    ]
    for k1, k2, k3 in priority_triples:
        if all(k in dims for k in [k1, k2, k3]):
            key = f"{k1}:{dims[k1]}|{k2}:{dims[k2]}|{k3}:{dims[k3]}"
            combos.append((key, {k1: dims[k1], k2: dims[k2], k3: dims[k3]}))

    return combos


def _pcr_zone(pcr: float) -> str:
    if pcr is None:  return "PCR_UNKNOWN"
    if pcr < 0.6:    return "PCR_EUPHORIA"
    if pcr < 0.8:    return "PCR_BULLISH"
    if pcr < 1.1:    return "PCR_NEUTRAL"
    if pcr < 1.3:    return "PCR_BEARISH"
    return "PCR_EXTREME_FEAR"


def _iv_zone(iv_pct: float) -> str:
    if iv_pct is None: return "IV_UNKNOWN"
    if iv_pct < 20:    return "IV_VERY_LOW"
    if iv_pct < 40:    return "IV_LOW"
    if iv_pct < 60:    return "IV_NORMAL"
    if iv_pct < 80:    return "IV_HIGH"
    return "IV_EXTREME"


def _calc_quality(win_rate: float, count: int) -> str:
    if win_rate >= 0.70 and count >= 10: return "GOLD"
    if win_rate >= 0.60 and count >= 5:  return "SILVER"
    return "LEARNING"


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: QUERY INTERFACE (agents call these before trading)
# ─────────────────────────────────────────────────────────────────────────────

def query_similar_conditions(
    regime: str = None,
    pcr_zone: str = None,
    volume_class: str = None,
    sector: str = None,
    news_type: str = None,
    limit: int = 10,
) -> list:
    """
    Find historical events with similar conditions.
    Returns list of events with their outcomes.
    Used by agents before entering trades: "what happened last time conditions were like this?"
    """
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if regime:       conditions.append("regime=?");       params.append(regime)
        if pcr_zone:
            # Convert pcr_zone back to pcr range
            pcr_ranges = {
                "PCR_EUPHORIA": (0.0, 0.6), "PCR_BULLISH": (0.6, 0.8),
                "PCR_NEUTRAL": (0.8, 1.1), "PCR_BEARISH": (1.1, 1.3),
                "PCR_EXTREME_FEAR": (1.3, 9.9),
            }
            r = pcr_ranges.get(pcr_zone)
            if r:
                conditions.append("pcr_nifty BETWEEN ? AND ?")
                params.extend(r)
        if volume_class: conditions.append("volume_class=?");  params.append(volume_class)
        if sector:       conditions.append("sector=?");        params.append(sector)
        if news_type:    conditions.append("news_event_type=?"); params.append(news_type)

        where = " AND ".join(conditions) if conditions else "1=1"
        where += " AND outcome != 'OPEN'"
        params.append(limit)

        rows = conn.execute(f"""
            SELECT ticker, sector, outcome, pnl_pct, regime, volume_class, pcr_nifty,
                   news_event_type, day_of_week, market_session, lesson_extracted,
                   entry_score, timestamp
            FROM knowledge_events
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("ATLAS query_similar error: %s", e)
        return []


def get_best_patterns(quality: str = "GOLD", limit: int = 15) -> list:
    """Returns top-performing patterns for agent context."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT dimension_key, win_count, loss_count,
                   CAST(win_count AS REAL)/(win_count+loss_count) as win_rate,
                   avg_win_pct, avg_loss_pct, avg_hold_hrs, quality
            FROM pattern_correlations
            WHERE quality=? AND (win_count + loss_count) >= 3
            ORDER BY win_rate DESC, win_count DESC
            LIMIT ?
        """, (quality, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("ATLAS get_best_patterns error: %s", e)
        return []


def get_active_rules(rule_type: str = None) -> list:
    """Returns currently active auto-generated trading rules."""
    try:
        conn = _get_conn()
        if rule_type:
            rows = conn.execute(
                "SELECT * FROM atlas_rules WHERE active=1 AND rule_type=? ORDER BY confidence DESC",
                (rule_type,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM atlas_rules WHERE active=1 ORDER BY confidence DESC LIMIT 20"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("ATLAS get_active_rules error: %s", e)
        return []


def store_rule(rule_id: str, rule_text: str, rule_type: str,
               confidence: float, supporting_evidence: list,
               win_rate_basis: float, trade_count: int) -> bool:
    """Store or update an auto-generated rule from the self-upgrader."""
    try:
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO atlas_rules
            (rule_id, rule_text, rule_type, confidence, supporting_evidence,
             win_rate_basis, trade_count, active, created_at, last_validated)
            VALUES (?,?,?,?,?,?,?,1,?,?)
        """, (rule_id, rule_text, rule_type, confidence,
              json.dumps(supporting_evidence), win_rate_basis, trade_count,
              datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        log.error("ATLAS store_rule error: %s", e)
        return False


def get_knowledge_stats() -> dict:
    """Dashboard stats for ATLAS panel."""
    try:
        conn = _get_conn()
        total_events = conn.execute(
            "SELECT COUNT(*) FROM knowledge_events"
        ).fetchone()[0]
        closed_events = conn.execute(
            "SELECT COUNT(*) FROM knowledge_events WHERE outcome != 'OPEN'"
        ).fetchone()[0]
        gold_patterns = conn.execute(
            "SELECT COUNT(*) FROM pattern_correlations WHERE quality='GOLD'"
        ).fetchone()[0]
        silver_patterns = conn.execute(
            "SELECT COUNT(*) FROM pattern_correlations WHERE quality='SILVER'"
        ).fetchone()[0]
        active_rules = conn.execute(
            "SELECT COUNT(*) FROM atlas_rules WHERE active=1"
        ).fetchone()[0]
        win_rate_row = conn.execute("""
            SELECT AVG(CASE WHEN outcome IN ('T1_HIT','T2_HIT') THEN 1.0 ELSE 0.0 END)
            FROM knowledge_events WHERE outcome != 'OPEN'
        """).fetchone()[0]
        last_synthesis = conn.execute(
            "SELECT run_at, top_insight FROM synthesis_log ORDER BY run_at DESC LIMIT 1"
        ).fetchone()

        return {
            "total_events":    total_events,
            "closed_events":   closed_events,
            "open_events":     total_events - closed_events,
            "gold_patterns":   gold_patterns,
            "silver_patterns": silver_patterns,
            "active_rules":    active_rules,
            "overall_win_rate": round(win_rate_row or 0, 3),
            "last_synthesis":  dict(last_synthesis) if last_synthesis else None,
        }
    except Exception as e:
        log.error("ATLAS get_knowledge_stats error: %s", e)
        return {}


def get_recent_lessons_atlas(ticker: str = None, limit: int = 5) -> list:
    """Get recent lessons from ATLAS (richer than memory_engine)."""
    try:
        conn = _get_conn()
        where = "WHERE outcome != 'OPEN' AND lesson_extracted IS NOT NULL"
        params = [limit]
        if ticker:
            where += " AND ticker=?"
            params = [ticker.upper(), limit]
        rows = conn.execute(f"""
            SELECT ticker, sector, outcome, pnl_pct, lesson_extracted,
                   primary_cause, failure_reason, timestamp
            FROM knowledge_events {where}
            ORDER BY timestamp DESC LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("ATLAS get_recent_lessons error: %s", e)
        return []


def log_synthesis_run(run_id: str, events_analyzed: int, patterns_found: int,
                      rules_generated: int, rules_retired: int,
                      top_insight: str, summary: str) -> bool:
    """Record a synthesis run in the log."""
    try:
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO synthesis_log
            (run_id, run_at, events_analyzed, patterns_found,
             rules_generated, rules_retired, top_insight, summary)
            VALUES (?,?,?,?,?,?,?,?)
        """, (run_id, datetime.now().isoformat(), events_analyzed, patterns_found,
              rules_generated, rules_retired, top_insight, summary))
        conn.commit()
        return True
    except Exception as e:
        log.error("ATLAS log_synthesis_run error: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ATLAS CORE SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

class ATLASCore:
    """
    Facade class — provides a single import point for all ATLAS core functions.
    Agents import `from stockguru_agents.atlas import ATLASCore` and call methods.
    """

    @staticmethod
    def log_entry(**kwargs):       return log_trade_entry(**kwargs)
    @staticmethod
    def update_outcome(**kwargs):  return update_trade_outcome(**kwargs)
    @staticmethod
    def update_causal(**kwargs):   return update_causal_analysis(**kwargs)
    @staticmethod
    def query(**kwargs):           return query_similar_conditions(**kwargs)
    @staticmethod
    def best_patterns(**kwargs):   return get_best_patterns(**kwargs)
    @staticmethod
    def active_rules(**kwargs):    return get_active_rules(**kwargs)
    @staticmethod
    def store_rule(**kwargs):      return store_rule(**kwargs)
    @staticmethod
    def stats():                   return get_knowledge_stats()
    @staticmethod
    def recent_lessons(**kwargs):  return get_recent_lessons_atlas(**kwargs)
    @staticmethod
    def log_synthesis(**kwargs):   return log_synthesis_run(**kwargs)
