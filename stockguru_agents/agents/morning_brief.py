"""
AGENT 5 — MORNING BRIEF AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : At 8:00 AM every day, compile a complete
          pre-market intelligence brief and send to
          Telegram + WhatsApp (via n8n).
          
          Brief includes:
          - Global cues (US markets, SGX Nifty)
          - Key levels for the day
          - Top 3 stock picks with entry/target/SL
          - Commodity snapshot
          - Events calendar for the day
          - Sentiment score
Runs    : 8:00 AM daily (+ on-demand)
Reports : Telegram + n8n WhatsApp
"""

import requests
import logging
from datetime import datetime, date

log = logging.getLogger("MorningBrief")

# ── WEEKLY EVENTS CALENDAR (manually updated) ─────────────────────────────────
def get_todays_events():
    """Return today's key market events."""
    today = datetime.now()
    day   = today.weekday()   # 0=Mon … 6=Sun
    hour  = today.hour

    # Recurring weekly events
    weekly = {
        0: ["📊 RBI Weekly Data Release", "💹 FII/DII flow data"],
        1: ["📈 US Consumer Confidence (overnight)", "🏭 India Manufacturing PMI"],
        2: ["🇺🇸 US ADP Jobs data (overnight)", "📊 India Services PMI"],
        3: ["⚡ Nifty/BankNifty Weekly EXPIRY — HIGH VOLATILITY", "🇺🇸 US Jobless Claims"],
        4: ["🇺🇸 US Non-Farm Payrolls (overnight)", "📊 India GDP (if month-end)"],
    }

    events = weekly.get(day, ["📅 No major events scheduled"])

    # Earnings season flag (Jan, Apr, Jul, Oct)
    month = today.month
    if month in [1, 4, 7, 10] and today.day <= 25:
        events.append("📋 Q3/Q4 RESULTS SEASON — watch for earnings surprises")

    # Month-end effects
    if today.day >= 28:
        events.append("📆 Month-end rebalancing — institutional flows may be volatile")

    return events

def format_price(val, prefix=""):
    """Format price for Telegram message."""
    if not val or val == "--":
        return "--"
    try:
        f = float(val)
        if f > 100000:
            return f"{prefix}₹{f/100000:.2f}L"
        if f > 1000:
            return f"{prefix}₹{f:,.0f}"
        return f"{prefix}₹{f:.2f}"
    except Exception:
        return str(val)

def build_brief(shared_state):
    """Build the complete morning brief message."""
    now = datetime.now()

    # ── COLLECT DATA FROM SHARED STATE ────────────────────────────────────────
    comm      = {r["name"]: r for r in shared_state.get("commodity_results", [])}
    scanner   = shared_state.get("scanner_results", [])
    signals   = shared_state.get("actionable_signals", shared_state.get("trade_signals", []))
    news      = shared_state.get("news_high_impact", [])
    mood_s    = shared_state.get("market_sentiment_score", 0)
    comm_sent = shared_state.get("commodity_sentiment", "NEUTRAL")
    indices   = shared_state.get("index_prices", {})

    # ── INDEX DATA ─────────────────────────────────────────────────────────────
    nifty  = indices.get("NIFTY 50",   {})
    sensex = indices.get("SENSEX",     {})
    bn     = indices.get("BANK NIFTY", {})
    vix    = indices.get("INDIA VIX",  {})

    def idx_line(name, data):
        if not data:
            return f"  {name}: --"
        p   = data.get("price", "--")
        chg = data.get("change_pct", 0)
        arr = "▲" if chg >= 0 else "▼"
        return f"  {name}: {p:,} ({arr} {abs(chg):.2f}%)"

    # ── MOOD LABEL ─────────────────────────────────────────────────────────────
    if mood_s >= 2:     mood_lbl = "🤑 GREED — Cautious"
    elif mood_s >= 0.5: mood_lbl = "😊 MILDLY BULLISH"
    elif mood_s >= -0.5:mood_lbl = "😐 NEUTRAL"
    elif mood_s >= -2:  mood_lbl = "😰 FEAR — Be Careful"
    else:               mood_lbl = "😨 EXTREME FEAR — Opportunities?"

    # ── TOP PICKS ──────────────────────────────────────────────────────────────
    top3 = signals[:3] if signals else scanner[:3]

    def pick_line(s):
        name  = s.get("name", "--")
        cmp   = s.get("cmp", s.get("price", "--"))
        sig   = s.get("signal", "--")
        score = s.get("score", "--")
        t1    = s.get("target1", s.get("target", "--"))
        sl    = s.get("stop_loss", s.get("sl", "--"))
        emoji = "🟢" if "BUY" in str(sig) else "🟡"
        return f"  {emoji} *{name}* | CMP ₹{cmp} | {sig} | Score {score}\n     T1: ₹{t1} | SL: ₹{sl}"

    # ── NEWS BULLETS ───────────────────────────────────────────────────────────
    news_lines = []
    for n in news[:4]:
        e = n.get("emoji", "📰")
        news_lines.append(f"  {e} {n['headline'][:70]}")

    # ── EVENTS ─────────────────────────────────────────────────────────────────
    events = get_todays_events()

    # ── COMMODITY SNAPSHOT ────────────────────────────────────────────────────
    gold   = comm.get("GOLD",      {})
    crude  = comm.get("CRUDE OIL", {})
    usd    = comm.get("USD/INR",   {})
    btc    = comm.get("BTC/INR",   {})

    def comm_line(name, data):
        if not data:
            return f"  {name}: --"
        p   = data.get("price", "--")
        chg = data.get("change_pct", 0)
        arr = "▲" if chg >= 0 else "▼"
        return f"  {name}: {p} ({arr} {abs(chg):.2f}%)"

    # ── ASSEMBLE MESSAGE ───────────────────────────────────────────────────────
    lines = [
        f"🌅 *STOCKGURU MORNING BRIEF*",
        f"📅 {now.strftime('%A, %d %b %Y')} | {now.strftime('%I:%M %p')} IST",
        f"",
        f"📊 *MARKET INDICES*",
        idx_line("Nifty 50 ", nifty),
        idx_line("Sensex   ", sensex),
        idx_line("BankNifty", bn),
        idx_line("India VIX", vix),
        f"",
        f"🧠 *MARKET MOOD: {mood_lbl}*",
        f"  Sentiment Score: {mood_s:+.2f} | Macro: {comm_sent[:40]}",
        f"",
        f"🥇 *COMMODITIES*",
        comm_line("Gold  ", gold),
        comm_line("Crude ", crude),
        comm_line("USD/INR", usd),
        comm_line("BTC   ", btc),
        f"",
        f"🏆 *TOP 3 PICKS FOR TODAY*",
    ]

    if top3:
        for s in top3:
            lines.append(pick_line(s))
    else:
        lines.append("  ⏳ Scanning in progress...")

    lines += [
        f"",
        f"📰 *HIGH-IMPACT NEWS*",
    ]

    if news_lines:
        lines.extend(news_lines)
    else:
        lines.append("  No major news alerts")

    lines += [
        f"",
        f"📅 *TODAY'S EVENTS*",
    ]
    for ev in events:
        lines.append(f"  {ev}")

    lines += [
        f"",
        f"─────────────────────────",
        f"⚠️ _Paper trade mode. Not SEBI advice._",
        f"🔄 _Next update in 15 minutes_",
    ]

    return "\n".join(lines)

def build_intraday_alert(shared_state):
    """Build a compact 15-minute update message."""
    signals   = shared_state.get("actionable_signals", [])
    comm_alts = shared_state.get("commodity_alerts", [])
    news_hi   = shared_state.get("news_high_impact", [])

    if not signals and not comm_alts and not news_hi:
        return None   # nothing to report

    now   = datetime.now()
    lines = [f"⚡ *StockGuru Update* — {now.strftime('%H:%M')} IST"]

    if signals:
        lines.append(f"\n🏆 *Active Signals:*")
        for s in signals[:3]:
            arr = "🟢" if "BUY" in s["signal"] else "🟡"
            lines.append(
                f"  {arr} *{s['name']}* ₹{s['cmp']} | {s['signal']} | "
                f"Score {s['score']} | T1 ₹{s['target1']} | SL ₹{s['stop_loss']}"
            )

    if comm_alts:
        lines.append(f"\n📊 *Commodity Alerts:*")
        for a in comm_alts[:2]:
            lines.append(f"  {a}")

    if news_hi:
        lines.append(f"\n📰 *News:*")
        for n in news_hi[:2]:
            lines.append(f"  {n['emoji']} {n['headline'][:60]}")

    lines.append(f"\n_⚠️ Paper trade only._")
    return "\n".join(lines)

def run(shared_state, send_telegram_fn, send_n8n_fn=None, force=False):
    """Main agent — send morning brief at 8 AM or on demand."""
    now  = datetime.now()
    hour = now.hour

    if force or hour == 8:
        log.info("🌅 MorningBrief: Compiling full brief...")
        msg = build_brief(shared_state)
        try:
            send_telegram_fn(msg)
            log.info("✅ MorningBrief: Telegram sent.")
        except Exception as _te:
            log.warning("⚠️  MorningBrief: Telegram delivery failed (non-fatal): %s", _te)
        if send_n8n_fn:
            try:
                send_n8n_fn(msg, "morning_brief")
            except Exception as _ne:
                log.warning("⚠️  MorningBrief: n8n delivery failed (non-fatal): %s", _ne)
        shared_state["last_morning_brief"] = now.strftime("%d %b %H:%M")
        shared_state["morning_brief_text"] = msg
        log.info("✅ MorningBrief: Complete.")
        return msg

    # Intraday update (every 15 min during market hours 9:15 to 15:30)
    elif 9 <= hour <= 15:
        msg = build_intraday_alert(shared_state)
        if msg:
            log.info("⚡ MorningBrief: Sending intraday alert...")
            try:
                send_telegram_fn(msg)
            except Exception as _te:
                log.warning("⚠️  MorningBrief: Intraday alert Telegram failed (non-fatal): %s", _te)
            if send_n8n_fn:
                try:
                    send_n8n_fn(msg, "intraday_alert")
                except Exception as _ne:
                    log.warning("⚠️  MorningBrief: Intraday n8n failed (non-fatal): %s", _ne)
            return msg

    return None
