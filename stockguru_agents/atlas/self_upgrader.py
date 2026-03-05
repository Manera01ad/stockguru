# ══════════════════════════════════════════════════════════════════════════════
# ATLAS MODULE 6 — SELF-UPGRADE ENGINE
# ══════════════════════════════════════════════════════════════════════════════
# This is the nightly brain upgrade. While traders sleep, ATLAS:
#
#   1. SYNTHESIZES all closed trades into pattern correlations
#   2. REBUILDS options flow insights from PCR history
#   3. RECALCULATES news impact map from recorded events
#   4. UPDATES time pattern stats (which sessions/days win most)
#   5. REFRESHES volume spike stats by class
#   6. RUNS causal analysis on any uncaused closed trades
#   7. GENERATES new trading rules from GOLD/SILVER patterns
#   8. RETIRES rules that have been invalidated by new data
#   9. CALLS Claude (Haiku) to write natural language insights
#   10. WRITES everything back to the knowledge store
#
# Designed to run once per day (or on demand).
# Every morning StockGuru wakes up slightly smarter than yesterday.
#
# Schedule: Daily at 9:00 PM (after market close, before next open)
# Trigger:  /api/atlas/upgrade (manual) or app.py scheduler
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta

log = logging.getLogger("atlas.self_upgrader")

_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))

# Minimum trades required before generating rules
MIN_TRADES_FOR_RULES = 5
# Rule confidence thresholds
GOLD_CONFIDENCE    = 0.80
SILVER_CONFIDENCE  = 0.65
# Pattern win rate to generate a rule
RULE_WIN_RATE_MIN  = 0.65
RULE_SAMPLE_MIN    = 8


# ─────────────────────────────────────────────────────────────────────────────
# MAIN UPGRADE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def run_upgrade(shared_state: dict = None, use_llm: bool = True) -> dict:
    """
    Execute the full nightly self-upgrade cycle.
    Returns a summary dict of what was learned.
    """
    run_id  = f"ATLAS_UPGRADE_{datetime.now().strftime('%Y%m%d_%H%M')}"
    started = datetime.now()

    log.info("🧠 ATLAS Self-Upgrade: Starting run %s", run_id)

    from stockguru_agents.atlas.core import _get_conn, log_synthesis_run
    from stockguru_agents.atlas.options_flow_memory import rebuild_insights
    from stockguru_agents.atlas.news_impact_mapper import build_impact_map
    from stockguru_agents.atlas.regime_detector import build_time_pattern_stats
    from stockguru_agents.atlas.volume_classifier import build_volume_stats
    from stockguru_agents.atlas.causal_engine import (
        build_causal_stats, analyze_trade_cause
    )

    conn = _get_conn()
    results = {
        "run_id": run_id,
        "started": started.isoformat(),
        "steps": {},
    }

    # ── STEP 1: Get uncaused closed trades and run causal analysis ────────────
    try:
        uncaused = conn.execute("""
            SELECT * FROM knowledge_events
            WHERE outcome NOT IN ('OPEN','EXPIRED')
            AND primary_cause IS NULL
            LIMIT 50
        """).fetchall()

        causes_added = 0
        for row in uncaused:
            ev = dict(row)
            analysis = analyze_trade_cause(
                outcome          = ev.get("outcome"),
                pnl_pct          = ev.get("pnl_pct"),
                rsi              = ev.get("rsi"),
                macd_cross       = ev.get("macd_cross"),
                ema_position     = ev.get("ema_position"),
                volume_class     = ev.get("volume_class"),
                volume_ratio     = ev.get("volume_ratio"),
                regime           = ev.get("regime"),
                pcr_nifty        = ev.get("pcr_nifty"),
                options_signal   = ev.get("options_signal"),
                news_event_type  = ev.get("news_event_type"),
                news_impact      = ev.get("news_impact_magnitude"),
                fii_flow         = ev.get("fii_flow"),
                sector_momentum  = ev.get("sector_momentum"),
                week_type        = ev.get("week_type"),
                market_session   = ev.get("market_session"),
                hold_duration_hrs = ev.get("hold_duration_hrs"),
            )
            conn.execute("""
                UPDATE knowledge_events
                SET primary_cause=?, secondary_causes=?, failure_reason=?, lesson_extracted=?
                WHERE event_id=?
            """, (analysis["primary_cause"], json.dumps(analysis["secondary_causes"]),
                  analysis["failure_reason"], analysis["lesson"], ev["event_id"]))
            causes_added += 1

        conn.commit()
        results["steps"]["causal_analysis"] = {"events_processed": causes_added}
        log.info("✅ Step 1: Causal analysis — %d trades tagged", causes_added)
    except Exception as e:
        log.error("Step 1 causal error: %s", e)
        results["steps"]["causal_analysis"] = {"error": str(e)}

    # ── STEP 2: Rebuild all stat modules ─────────────────────────────────────
    try:
        signal_history = _load_signal_history()
        opts_insights  = rebuild_insights(signal_history)
        news_map       = build_impact_map()
        time_stats     = build_time_pattern_stats(signal_history)
        vol_stats      = build_volume_stats(conn)
        causal_stats   = build_causal_stats(conn)

        results["steps"]["stats_rebuilt"] = {
            "options_pcr_zones": len(opts_insights.get("pcr_outcome_map", {})),
            "news_event_types":  len(news_map.get("by_event_type", {})),
            "time_patterns":     len(time_stats),
            "volume_classes":    len(vol_stats),
            "causal_causes":     len(causal_stats.get("by_cause", {})),
        }
        log.info("✅ Step 2: All stats rebuilt")
    except Exception as e:
        log.error("Step 2 stats error: %s", e)
        results["steps"]["stats_rebuilt"] = {"error": str(e)}

    # ── STEP 3: Generate rules from GOLD patterns ─────────────────────────────
    try:
        rules_generated, rules_retired = _generate_rules_from_patterns(conn)
        results["steps"]["rules"] = {
            "generated": rules_generated,
            "retired":   rules_retired,
        }
        log.info("✅ Step 3: Rules — %d generated, %d retired",
                 rules_generated, rules_retired)
    except Exception as e:
        log.error("Step 3 rules error: %s", e)
        results["steps"]["rules"] = {"error": str(e)}

    # ── STEP 4: LLM synthesis (Claude Haiku generates narrative insights) ─────
    llm_insight = None
    if use_llm:
        try:
            llm_insight = _run_llm_synthesis(conn, results)
            results["steps"]["llm_synthesis"] = {"insight": llm_insight[:200] if llm_insight else None}
            log.info("✅ Step 4: LLM synthesis complete")
        except Exception as e:
            log.error("Step 4 LLM error: %s", e)
            results["steps"]["llm_synthesis"] = {"error": str(e)}

    # ── STEP 5: Write synthesis log ───────────────────────────────────────────
    try:
        total_events = conn.execute(
            "SELECT COUNT(*) FROM knowledge_events WHERE outcome NOT IN ('OPEN')"
        ).fetchone()[0]
        total_patterns = conn.execute(
            "SELECT COUNT(*) FROM pattern_correlations"
        ).fetchone()[0]
        total_rules = (results.get("steps", {}).get("rules", {}).get("generated", 0) or 0)
        retired = (results.get("steps", {}).get("rules", {}).get("retired", 0) or 0)

        log_synthesis_run(
            run_id          = run_id,
            events_analyzed = total_events,
            patterns_found  = total_patterns,
            rules_generated = total_rules,
            rules_retired   = retired,
            top_insight     = llm_insight[:300] if llm_insight else "Synthesis complete",
            summary         = json.dumps(results.get("steps", {})),
        )
    except Exception as e:
        log.error("Step 5 log error: %s", e)

    # ── Final summary ─────────────────────────────────────────────────────────
    duration = (datetime.now() - started).total_seconds()
    results["duration_secs"] = round(duration, 1)
    results["completed"]     = datetime.now().isoformat()
    results["top_insight"]   = llm_insight

    if shared_state is not None:
        shared_state["atlas_last_upgrade"] = results

    log.info("🧠 ATLAS Self-Upgrade: Complete in %.1fs | Run: %s", duration, run_id)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# RULE GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def _generate_rules_from_patterns(conn) -> tuple:
    """
    Read GOLD/SILVER patterns and generate trading rules.
    Returns (rules_generated, rules_retired).
    """
    from stockguru_agents.atlas.core import store_rule, get_active_rules

    patterns = conn.execute("""
        SELECT pattern_id, dimension_key, dimensions, win_count, loss_count,
               avg_win_pct, avg_loss_pct, avg_hold_hrs, quality
        FROM pattern_correlations
        WHERE quality IN ('GOLD','SILVER')
        AND (win_count + loss_count) >= ?
        ORDER BY CAST(win_count AS REAL)/(win_count+loss_count) DESC
        LIMIT 30
    """, (RULE_SAMPLE_MIN,)).fetchall()

    rules_generated = 0
    for row in patterns:
        p = dict(row)
        total    = p["win_count"] + p["loss_count"]
        win_rate = p["win_count"] / total if total > 0 else 0

        if win_rate < RULE_WIN_RATE_MIN:
            continue

        rule_text = _pattern_to_rule(p)
        if not rule_text:
            continue

        rule_id = f"RULE_{p['pattern_id']}"
        confidence = min(0.95, win_rate * (min(total, 30) / 30) * 1.1)
        rule_type  = _infer_rule_type(p["dimension_key"])

        stored = store_rule(
            rule_id            = rule_id,
            rule_text          = rule_text,
            rule_type          = rule_type,
            confidence         = round(confidence, 3),
            supporting_evidence = [p["pattern_id"]],
            win_rate_basis     = round(win_rate, 3),
            trade_count        = total,
        )
        if stored:
            rules_generated += 1

    # Retire rules with declining performance (win_rate now below 50% with new data)
    rules_retired = 0
    active_rules  = get_active_rules()
    for rule in active_rules:
        supporting = json.loads(rule.get("supporting_evidence") or "[]")
        for pat_id in supporting:
            row = conn.execute(
                "SELECT win_count, loss_count FROM pattern_correlations WHERE pattern_id=?",
                (pat_id,)
            ).fetchone()
            if row:
                total = row["win_count"] + row["loss_count"]
                wr = row["win_count"] / total if total > 0 else 0
                if wr < 0.45 and total >= 15:
                    conn.execute(
                        "UPDATE atlas_rules SET active=0 WHERE rule_id=?",
                        (rule["rule_id"],)
                    )
                    conn.commit()
                    rules_retired += 1
                    log.info("🗑️  Retired rule: %s (win rate dropped to %.0f%%)",
                             rule["rule_id"], wr * 100)

    return rules_generated, rules_retired


def _pattern_to_rule(pattern: dict) -> str:
    """Convert a pattern dict into a human-readable trading rule."""
    key      = pattern["dimension_key"]
    win_rate = pattern["win_count"] / max(pattern["win_count"] + pattern["loss_count"], 1)
    total    = pattern["win_count"] + pattern["loss_count"]
    avg_pnl  = pattern.get("avg_win_pct", 0) or 0

    # Parse the dimension key
    parts = {}
    for segment in key.split("|"):
        if ":" in segment:
            k, v = segment.split(":", 1)
            parts[k] = v

    conditions = []
    if "regime" in parts:
        conditions.append(f"Market regime = {parts['regime']}")
    if "pcr_zone" in parts:
        conditions.append(f"PCR zone = {parts['pcr_zone']}")
    if "vol_class" in parts:
        conditions.append(f"Volume = {parts['vol_class']}")
    if "sector" in parts:
        conditions.append(f"Sector = {parts['sector']}")
    if "news_type" in parts:
        conditions.append(f"News event = {parts['news_type']}")
    if "day" in parts:
        conditions.append(f"Day = {parts['day']}")
    if "session" in parts:
        conditions.append(f"Session = {parts['session']}")
    if "fii" in parts:
        conditions.append(f"FII = {parts['fii']}")

    if len(conditions) < 2:
        return None

    return (
        f"When {' AND '.join(conditions)}: "
        f"{win_rate*100:.0f}% win rate (avg gain {avg_pnl:+.1f}%, n={total}). "
        f"Quality: {pattern.get('quality','SILVER')}. "
        f"ACTION: {'INCREASE conviction/size' if win_rate >= 0.75 else 'Normal position size, high priority'}."
    )


def _infer_rule_type(dimension_key: str) -> str:
    if "session" in dimension_key or "day" in dimension_key:
        return "TIMING"
    if "regime" in dimension_key:
        return "ENTRY"
    if "vol_class" in dimension_key:
        return "ENTRY"
    if "pcr_zone" in dimension_key:
        return "ENTRY"
    if "sector" in dimension_key:
        return "ENTRY"
    return "ENTRY"


# ─────────────────────────────────────────────────────────────────────────────
# LLM SYNTHESIS
# ─────────────────────────────────────────────────────────────────────────────

def _run_llm_synthesis(conn, results: dict) -> str:
    """
    Call Claude Haiku to generate a natural language synthesis of recent learnings.
    Returns a paragraph of insights.
    """
    import anthropic
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("ATLAS LLM: No API key — skipping narrative synthesis")
        return "LLM synthesis skipped (no API key)"

    # Build context for LLM
    try:
        # Last 7 days of closed trades
        recent = conn.execute("""
            SELECT ticker, sector, outcome, pnl_pct, primary_cause,
                   failure_reason, volume_class, regime, pcr_nifty,
                   news_event_type, lesson_extracted
            FROM knowledge_events
            WHERE outcome NOT IN ('OPEN','EXPIRED')
            AND timestamp >= date('now','-7 days')
            ORDER BY timestamp DESC
            LIMIT 20
        """).fetchall()
        recent_list = [dict(r) for r in recent]

        # Top patterns
        gold_patterns = conn.execute("""
            SELECT dimension_key, win_count, loss_count,
                   CAST(win_count AS REAL)/(win_count+loss_count) as win_rate,
                   avg_win_pct
            FROM pattern_correlations
            WHERE quality='GOLD'
            LIMIT 5
        """).fetchall()
        gold_list = [dict(r) for r in gold_patterns]

        # Most common failure reasons
        failures = conn.execute("""
            SELECT failure_reason, COUNT(*) as cnt
            FROM knowledge_events
            WHERE outcome='SL_HIT' AND failure_reason IS NOT NULL
            AND timestamp >= date('now','-30 days')
            GROUP BY failure_reason
            ORDER BY cnt DESC LIMIT 5
        """).fetchall()
        fail_list = [dict(r) for r in failures]

    except Exception as e:
        return f"Context build failed: {e}"

    prompt = f"""You are ATLAS, the self-learning knowledge engine for StockGuru trading system.

RECENT TRADES (last 7 days):
{json.dumps(recent_list[:10], indent=2)}

TOP GOLD PATTERNS DISCOVERED:
{json.dumps(gold_list, indent=2)}

TOP FAILURE REASONS (last 30 days):
{json.dumps(fail_list, indent=2)}

Write a concise 3-4 sentence daily synthesis note for the trading agents.
Focus on:
1. The single most important pattern currently working
2. The most common mistake to avoid right now
3. One specific recommendation for tomorrow's trading

Be specific, use data from above, write as actionable intelligence.
Keep it under 200 words."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        insight = msg.content[0].text.strip()
        log.info("🧠 ATLAS LLM synthesis: %d chars generated", len(insight))
        return insight
    except Exception as e:
        log.error("ATLAS LLM call failed: %s", e)
        return f"LLM synthesis failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_signal_history() -> list:
    path = os.path.join(_BASE, "signal_history.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def get_upgrade_status() -> dict:
    """Returns status of last upgrade run for dashboard."""
    try:
        from stockguru_agents.atlas.core import _get_conn
        conn = _get_conn()
        row  = conn.execute(
            "SELECT * FROM synthesis_log ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
        if row:
            d = dict(row)
            return {
                "last_run":        d.get("run_at"),
                "events_analyzed": d.get("events_analyzed", 0),
                "patterns_found":  d.get("patterns_found", 0),
                "rules_generated": d.get("rules_generated", 0),
                "top_insight":     d.get("top_insight"),
            }
    except Exception:
        pass
    return {"last_run": None, "top_insight": "No upgrade run yet"}


def run_quick_context_refresh(shared_state: dict) -> dict:
    """
    Lightweight refresh called every 15 minutes.
    Updates shared_state with current ATLAS context without full rebuild.
    """
    try:
        from stockguru_agents.atlas.core import get_knowledge_stats, get_best_patterns, get_active_rules
        from stockguru_agents.atlas.regime_detector import detect_regime, get_time_context, get_time_win_rate
        from stockguru_agents.atlas.options_flow_memory import get_options_context

        # Get current options state from shared_state
        opts = shared_state.get("options_flow", {})
        pcr_nifty    = opts.get("nifty", {}).get("pcr") if isinstance(opts.get("nifty"), dict) else None
        pcr_bnf      = opts.get("banknifty", {}).get("pcr") if isinstance(opts.get("banknifty"), dict) else None
        iv_pct       = opts.get("nifty", {}).get("iv_percentile") if isinstance(opts.get("nifty"), dict) else None

        # Time context
        time_ctx = get_time_context()

        # Historical win rate for current conditions
        time_wr = get_time_win_rate(
            session  = time_ctx.get("session"),
            day      = time_ctx.get("day_of_week"),
            week_type = time_ctx.get("week_type"),
        )

        # Options context
        opts_ctx = get_options_context(pcr_nifty, pcr_bnf, iv_pct)

        # Knowledge stats
        stats = get_knowledge_stats()

        # Best patterns
        gold_patterns = get_best_patterns("GOLD", limit=5)

        # Active rules
        active_rules  = get_active_rules(rule_type="ENTRY")[:5]

        atlas_context = {
            "time":         time_ctx,
            "time_win_rate": time_wr,
            "options":      opts_ctx,
            "stats":        stats,
            "gold_patterns": gold_patterns,
            "active_rules": active_rules,
            "refreshed_at": datetime.now().isoformat(),
        }

        shared_state["atlas_context"] = atlas_context
        return atlas_context

    except Exception as e:
        log.error("ATLAS quick refresh error: %s", e)
        return {}
