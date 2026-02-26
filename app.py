"""
StockGuru Real-Time Intelligence App — v2.0
============================================
14-Agent self-learning system with LLM intelligence.
Claude Haiku (primary) + Gemini Flash (parallel) review every cycle.
Paper trading simulation — ZERO broker connectivity.
"""

from flask import Flask, jsonify, render_template_string, send_from_directory, request
from flask_cors import CORS
import requests
import json
import os
import sys
import threading
import time
import schedule
from datetime import datetime
from dotenv import load_dotenv
import logging

# ── AGENT IMPORTS ─────────────────────────────────────────────────────────────
_agents_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockguru_agents")
if _agents_dir not in sys.path:
    sys.path.insert(0, _agents_dir)

try:
    from agents import (
        market_scanner, news_sentiment, trade_signal, commodity_crypto, morning_brief,
        technical_analysis, institutional_flow, options_flow,
        claude_intelligence, web_researcher,
        sector_rotation, risk_manager,
        pattern_memory, paper_trader,
    )
    AGENTS_AVAILABLE = True
except ImportError as _e:
    AGENTS_AVAILABLE = False
    logging.warning(f"Agents not loaded: {_e}")

# ── LEARNING IMPORTS ──────────────────────────────────────────────────────────
try:
    from learning import signal_tracker, weight_adjuster
    LEARNING_AVAILABLE = True
except ImportError:
    LEARNING_AVAILABLE = False

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
CORS(app)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY= os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")

YAHOO_SYMBOLS = {
    "NIFTY 50":    "^NSEI",
    "SENSEX":      "^BSESN",
    "BANK NIFTY":  "^NSEBANK",
    "INDIA VIX":   "^INDIAVIX",
    "AIRTEL":      "BHARTIARTL.NS",
    "HDFC BANK":   "HDFCBANK.NS",
    "ICICI BANK":  "ICICIBANK.NS",
    "BAJAJ FIN":   "BAJFINANCE.NS",
    "BEL":         "BEL.NS",
    "MUTHOOT":     "MUTHOOTFIN.NS",
    "ZOMATO":      "ZOMATO.NS",
    "INDIGO":      "INDIGO.NS",
    "GOLD MCX":    "GC=F",
    "SILVER MCX":  "SI=F",
    "CRUDE OIL":   "CL=F",
    "NAT GAS":     "NG=F",
    "USD/INR":     "INR=X",
    "BTC/INR":     "BTC-INR",
    "ETH/INR":     "ETH-INR",
    "SOL/INR":     "SOL-INR",
}

WATCHLIST = [
    {"name":"AIRTEL",    "symbol":"BHARTIARTL.NS", "sector":"Telecom",   "pe":24, "roe":18, "de":0.8, "base_score":93},
    {"name":"HDFC BANK", "symbol":"HDFCBANK.NS",   "sector":"Banking",   "pe":18, "roe":17, "de":0.1, "base_score":91},
    {"name":"ICICI BANK","symbol":"ICICIBANK.NS",  "sector":"Banking",   "pe":17, "roe":18, "de":0.1, "base_score":90},
    {"name":"BAJAJ FIN", "symbol":"BAJFINANCE.NS", "sector":"NBFC",      "pe":28, "roe":24, "de":0.3, "base_score":88},
    {"name":"BEL",       "symbol":"BEL.NS",        "sector":"Defence",   "pe":38, "roe":23, "de":0.0, "base_score":87},
    {"name":"MUTHOOT",   "symbol":"MUTHOOTFIN.NS", "sector":"Gold Loan", "pe":16, "roe":27, "de":0.4, "base_score":86},
    {"name":"ZOMATO",    "symbol":"ZOMATO.NS",     "sector":"Food Tech", "pe":90, "roe":4,  "de":0.0, "base_score":85},
    {"name":"INDIGO",    "symbol":"INDIGO.NS",     "sector":"Aviation",  "pe":14, "roe":82, "de":1.2, "base_score":84},
]

price_cache  = {}
alert_log    = []
last_update  = None
shared_state = {
    # Original state
    "scanner_results": [], "full_scan": [], "news_results": [],
    "news_high_impact": [], "trade_signals": [], "actionable_signals": [],
    "commodity_results": [], "commodity_alerts": [],
    "market_sentiment_score": 0, "commodity_sentiment": "NEUTRAL",
    "stock_sentiment_map": {}, "index_prices": {},
    "agent_status": {}, "cycle_count": 0, "last_full_cycle": None,
    "alert_log": [], "agent_cycle_log": [],
    "scanner_last_run": None, "news_last_run": None,
    "signals_last_run": None, "commodity_last_run": None,
    "last_morning_brief": None,
    # New state — intelligent agents
    "technical_data": {}, "technical_last_run": None,
    "institutional_flow": {}, "institutional_last_run": None,
    "options_flow": {}, "options_last_run": None,
    "sector_rotation": {}, "sector_rotation_last": None,
    "risk_reviewed_signals": [], "risk_summary": {},
    "claude_analysis": {}, "web_research": {},
    "pattern_library": [], "accuracy_stats": {},
    # Paper trading
    "paper_portfolio": {}, "paper_trades": [],
    "_price_cache": {},
}
agent_is_running = False

# ── PRICE FETCHER ─────────────────────────────────────────────────────────────
def fetch_yahoo_price(symbol):
    try:
        url     = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r       = requests.get(url, headers=headers, timeout=8)
        data    = r.json()
        meta    = data["chart"]["result"][0]["meta"]
        price       = meta.get("regularMarketPrice", 0)
        prev        = meta.get("chartPreviousClose", price)
        change      = round(price - prev, 2)
        change_pct  = round((change / prev) * 100, 2) if prev else 0
        return {"price": round(price, 2), "change": change, "change_pct": change_pct, "prev": round(prev, 2)}
    except Exception as e:
        log.warning(f"Yahoo fetch failed for {symbol}: {e}")
        return None

def fetch_all_prices():
    global last_update
    log.info("🔄 Fetching live prices...")
    for name, symbol in YAHOO_SYMBOLS.items():
        data = fetch_yahoo_price(symbol)
        if data:
            price_cache[name] = {**data, "symbol": symbol, "updated": datetime.now().strftime("%H:%M:%S")}
            if name in ("NIFTY 50", "SENSEX", "BANK NIFTY", "INDIA VIX"):
                shared_state["index_prices"][name] = data
        time.sleep(0.3)
    last_update              = datetime.now().strftime("%d %b %Y %H:%M:%S IST")
    shared_state["_price_cache"] = price_cache
    log.info(f"✅ Price cache updated at {last_update}")

    # Check signal outcomes every price cycle
    if LEARNING_AVAILABLE:
        try:
            signal_tracker.check_outcomes(price_cache, shared_state)
        except Exception as e:
            log.debug("signal_tracker check failed: %s", e)

    # Monitor paper positions every 5 min
    if AGENTS_AVAILABLE:
        try:
            paper_trader.run(shared_state, price_cache)
        except Exception as e:
            log.debug("paper_trader monitor failed: %s", e)

# ── SCORING ENGINE ────────────────────────────────────────────────────────────
def calculate_score(stock):
    base   = stock["base_score"]
    name   = stock["name"]
    cached = price_cache.get(name)
    if not cached:
        return base, "WATCH", 0, 0
    price      = cached["price"]
    change_pct = cached["change_pct"]
    tech_adj   = +3 if change_pct > 2 else +2 if change_pct > 1 else +1 if change_pct > 0 else -3 if change_pct < -2 else -2 if change_pct < -1 else -1
    score      = min(100, max(0, base + tech_adj))

    if LEARNING_AVAILABLE:
        try:
            score = weight_adjuster.apply_sector_weight(score, stock.get("sector", ""))
            score = weight_adjuster.apply_stock_weight(score, name)
        except Exception:
            pass

    if score >= 88:   signal = "STRONG BUY"
    elif score >= 82: signal = "BUY"
    elif score >= 72: signal = "WATCH"
    elif score >= 60: signal = "HOLD"
    else:             signal = "AVOID"
    target = round(price * 1.20, 1)
    sl     = round(price * 0.92, 1)
    return score, signal, target, sl

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured — skipping alert")
        return False
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        r    = requests.post(url, data=data, timeout=8)
        ok   = r.status_code == 200
        if ok:
            log.info(f"📲 Telegram sent: {message[:60]}...")
            alert_log.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": message})
        return ok
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False

def check_alerts():
    log.info("🔔 Checking alerts...")
    buy_signals = []
    for stock in WATCHLIST:
        score, signal, target, sl = calculate_score(stock)
        cached = price_cache.get(stock["name"])
        if cached and signal in ("STRONG BUY", "BUY"):
            buy_signals.append({"name": stock["name"], "score": score, "signal": signal,
                                "price": cached["price"], "change_pct": cached["change_pct"],
                                "target": target, "sl": sl, "sector": stock["sector"]})
    if buy_signals:
        lines = ["🚨 *StockGuru Alert* — " + datetime.now().strftime("%d %b %H:%M") + " IST\n"]
        for s in buy_signals:
            arrow = "🟢" if s["change_pct"] >= 0 else "🔴"
            lines.append(f"{arrow} *{s['name']}* ({s['sector']})\n"
                         f"   Score: {s['score']}/100 | Signal: {s['signal']}\n"
                         f"   CMP: ₹{s['price']} ({s['change_pct']:+.2f}%)\n"
                         f"   Target: ₹{s['target']} | SL: ₹{s['sl']}\n")
        lines.append("_⚠️ Paper simulation only. Not SEBI advice._")
        send_telegram("\n".join(lines))

def send_morning_brief():
    nifty  = price_cache.get("NIFTY 50",  {})
    sensex = price_cache.get("SENSEX",    {})
    gold   = price_cache.get("GOLD MCX",  {})
    crude  = price_cache.get("CRUDE OIL", {})
    btc    = price_cache.get("BTC/INR",   {})
    usd    = price_cache.get("USD/INR",   {})
    claude = shared_state.get("claude_analysis", {})

    msg = f"""🌅 *StockGuru Morning Brief*
📅 {datetime.now().strftime('%A, %d %b %Y')}

📊 *INDICES*
• Nifty 50:  {nifty.get('price','--')} ({nifty.get('change_pct',0):+.2f}%)
• Sensex:    {sensex.get('price','--')} ({sensex.get('change_pct',0):+.2f}%)

🧠 *AI MARKET VIEW: {claude.get('market_condition','NEUTRAL')}*
{claude.get('market_narrative','Analysis pending...')[:150]}

🥇 *COMMODITIES*
• Gold MCX:  {gold.get('price','--')} ({gold.get('change_pct',0):+.2f}%)
• Crude Oil: {crude.get('price','--')} ({crude.get('change_pct',0):+.2f}%)

💱 *FOREX & CRYPTO*
• USD/INR:   {usd.get('price','--')}
• BTC/INR:   {btc.get('price','--')} ({btc.get('change_pct',0):+.2f}%)

🏆 *TOP AI PICKS TODAY*"""

    for pick in claude.get("conviction_picks", [])[:3]:
        gate = pick.get("gates_passed", 0)
        msg += f"\n🟢 *{pick['name']}* | Gates {gate}/8 | {pick.get('entry_thesis','')[:50]}"

    msg += f"\n\n_Updated: {last_update}_\n_⚠️ Paper simulation only. Not SEBI advice._"
    send_telegram(msg)

def send_evening_debrief():
    portfolio = shared_state.get("paper_portfolio", {})
    stats     = portfolio.get("stats", {})
    lines     = [f"🌙 *StockGuru Evening Debrief*\n📅 {datetime.now().strftime('%d %b %Y')}\n"]
    gainers, losers = [], []
    for stock in WATCHLIST:
        cached = price_cache.get(stock["name"])
        if cached:
            if cached["change_pct"] > 0: gainers.append((stock["name"], cached["change_pct"]))
            else:                        losers.append((stock["name"], cached["change_pct"]))
    gainers.sort(key=lambda x: -x[1])
    losers.sort(key=lambda x: x[1])
    lines.append("📈 *Gainers:*")
    for name, chg in gainers[:3]:
        lines.append(f"  🟢 {name}: {chg:+.2f}%")
    lines.append("\n📉 *Laggards:*")
    for name, chg in losers[:3]:
        lines.append(f"  🔴 {name}: {chg:+.2f}%")
    if stats.get("total_trades", 0) > 0:
        lines.append(f"\n📊 *Paper Portfolio:*")
        lines.append(f"  Win rate: {stats.get('win_rate',0)*100:.0f}% | Trades: {stats.get('total_trades',0)}")
        lines.append(f"  P&L today: {portfolio.get('daily_pnl_pct',0):+.2f}%")
    lines.append(f"\n_⚠️ Paper simulation only. Not SEBI advice._")
    send_telegram("\n".join(lines))

# ── 14-AGENT CYCLE ────────────────────────────────────────────────────────────
def run_all_agents():
    global agent_is_running
    if not AGENTS_AVAILABLE:
        log.warning("Agents not available — skipping cycle")
        return
    if agent_is_running:
        log.info("Previous agent cycle still running — skipping")
        return
    agent_is_running = True
    shared_state["cycle_count"] += 1
    cycle = shared_state["cycle_count"]
    log.info("=" * 65)
    log.info("🤖 STOCKGURU 14-AGENT CYCLE #%d STARTING", cycle)
    log.info("=" * 65)

    def _log(msg, level="info"):
        entry = {"t": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level}
        shared_state["agent_cycle_log"].append(entry)
        if len(shared_state["agent_cycle_log"]) > 200:
            shared_state["agent_cycle_log"] = shared_state["agent_cycle_log"][-200:]
    def _st(agent, status):
        shared_state["agent_status"][agent] = status
        icon = "▶" if status == "running" else ("✅" if status == "done" else "❌")
        _log(f"{icon} {agent.upper()} — {status}", level=status)
    def _send_tg(msg): return send_telegram(msg)
    def _send_n8n(msg, evt="alert"):
        n8n = os.getenv("N8N_WEBHOOK_URL", "")
        if not n8n: return False
        try:
            requests.post(n8n, json={"event": evt, "message": msg,
                          "timestamp": datetime.now().isoformat()}, timeout=10)
            return True
        except Exception: return False

    try:
        _log(f"🚀 CYCLE #{cycle} STARTED — 14 agents launching", "start")
        # ── TIER 1: DATA AGENTS ───────────────────────────────────────────────
        log.info("─── TIER 1: Data Collection ──────────────────────────────────")
        _log("── TIER 1: Data Collection ──────────────────────────")
        _st("commodity",  "running"); commodity_crypto.run(shared_state);       _st("commodity",  "done")
        _log(f"   Gold={shared_state.get('commodity_results',[{}])[0].get('price','?')} | Crude={shared_state.get('commodity_results',[{},{}])[1].get('price','?') if len(shared_state.get('commodity_results',[]))>1 else '?'}")
        _st("news",       "running"); news_sentiment.run(shared_state);          _st("news",       "done")
        _log(f"   News sentiment: {shared_state.get('market_sentiment_score',0):+.0f} | {len(shared_state.get('news_results',[]))} headlines")
        _st("scanner",    "running"); market_scanner.run(shared_state);          _st("scanner",    "done")
        _log(f"   Scanner: {len(shared_state.get('scanner_results',[]))} stocks ranked")

        for agent_name, agent_mod in [("technical",  technical_analysis),
                                       ("inst_flow",  institutional_flow),
                                       ("options",    options_flow),
                                       ("sector_rot", sector_rotation)]:
            _st(agent_name, "running")
            try:    agent_mod.run(shared_state); _st(agent_name, "done")
            except Exception as e:
                log.error("%s failed: %s", agent_name, e); _st(agent_name, "error")

        # ── TIER 2: LLM BRAIN ─────────────────────────────────────────────────
        log.info("─── TIER 2: LLM Intelligence ─────────────────────────────────")
        _log("── TIER 2: LLM Brain ────────────────────────────────")
        _st("claude", "running")
        try:
            claude_intelligence.run(shared_state); _st("claude", "done")
            ca = shared_state.get("claude_analysis", {})
            _log(f"   Market: {ca.get('market_condition','?')} | Stance: {ca.get('market_stance','?')} | Picks: {len(ca.get('conviction_picks',[]))}")
        except Exception as e: log.error("claude_intelligence: %s", e); _st("claude", "error"); _log(f"   ⚠ Claude error: {e}", "error")

        # ── TIER 3: STRATEGY ──────────────────────────────────────────────────
        log.info("─── TIER 3: Strategy & Risk ──────────────────────────────────")
        _log("── TIER 3: Strategy & Risk ──────────────────────────")
        _st("signals", "running"); trade_signal.run(shared_state); _st("signals", "done")
        _log(f"   Signals: {len(shared_state.get('actionable_signals',[]))} actionable")

        for agent_name, agent_mod in [("risk",         risk_manager),
                                       ("web_research", web_researcher)]:
            _st(agent_name, "running")
            try:    agent_mod.run(shared_state); _st(agent_name, "done")
            except Exception as e:
                log.error("%s failed: %s", agent_name, e); _st(agent_name, "error")

        # ── TIER 4: PAPER TRADING + LEARNING ─────────────────────────────────
        log.info("─── TIER 4: Paper Trading & Learning ────────────────────────")
        _log("── TIER 4: Paper Trading & Learning ─────────────────")
        _st("paper_trader", "running")
        try:
            paper_trader.run(shared_state, price_cache); _st("paper_trader", "done")
            port = shared_state.get("paper_portfolio", {})
            open_pos = len([p for p in port.get("positions",{}).values() if p.get("status")=="OPEN"])
            _log(f"   Paper: {open_pos} open positions | Win rate: {port.get('stats',{}).get('win_rate',0)*100:.0f}%")
        except Exception as e: log.error("paper_trader: %s", e); _st("paper_trader", "error"); _log(f"   ⚠ Paper trader error: {e}", "error")

        _st("patterns", "running")
        try:    pattern_memory.run(shared_state); _st("patterns", "done")
        except Exception as e: log.error("pattern_memory: %s", e); _st("patterns", "error")

        if LEARNING_AVAILABLE:
            try: weight_adjuster.adjust_weights()
            except Exception as e: log.debug("weight_adjuster: %s", e)

        _st("brief", "running"); morning_brief.run(shared_state, _send_tg, _send_n8n); _st("brief", "done")

        # Alert on high-conviction AI picks
        claude_a  = shared_state.get("claude_analysis", {})
        top_picks = [p for p in claude_a.get("conviction_picks", [])
                     if p.get("execute_paper_trade") and p.get("gates_passed", 0) >= 7]
        if top_picks:
            lines = [f"🚨 *StockGuru AI PICK*\n⏰ {datetime.now().strftime('%d %b %H:%M')} IST\n"]
            for p in top_picks[:2]:
                lines.append(f"🟢 *{p['name']}* | Gates {p['gates_passed']}/8\n"
                             f"   {p.get('entry_thesis','')[:70]}\n")
            lines.append(f"_Stance: {claude_a.get('market_stance','?')} | ⚠️ Simulation only_")
            _send_tg("\n".join(lines))

        shared_state["last_full_cycle"] = datetime.now().strftime("%d %b %H:%M:%S")
        _log(f"✅ CYCLE #{cycle} COMPLETE — next in 15 min", "done")
        portfolio = shared_state.get("paper_portfolio", {})
        log.info("✅ CYCLE #%d DONE | Scanner=%d | Signals=%d | Paper positions=%d | Win rate=%.0f%%",
                 cycle, len(shared_state.get("scanner_results", [])),
                 len(shared_state.get("actionable_signals", [])),
                 len([p for p in portfolio.get("positions", {}).values() if p.get("status") == "OPEN"]),
                 portfolio.get("stats", {}).get("win_rate", 0) * 100)

    except Exception as e:
        log.error("❌ Agent cycle failed: %s", e, exc_info=True)
        for k in shared_state["agent_status"]:
            if shared_state["agent_status"][k] == "running":
                shared_state["agent_status"][k] = "error"
    finally:
        agent_is_running = False

# ── API ROUTES ────────────────────────────────────────────────────────────────
@app.route("/api/scanner")
def api_scanner():
    return jsonify({"top10": shared_state.get("scanner_results", []),
                    "last_run": shared_state.get("scanner_last_run"),
                    "total_scanned": len(shared_state.get("full_scan", []))})

@app.route("/api/signals")
def api_signals():
    return jsonify({"signals": shared_state.get("trade_signals", []),
                    "actionable": shared_state.get("actionable_signals", []),
                    "risk_reviewed": shared_state.get("risk_reviewed_signals", []),
                    "last_run": shared_state.get("signals_last_run")})

@app.route("/api/news")
def api_news():
    return jsonify({"news": shared_state.get("news_results", []),
                    "high_impact": shared_state.get("news_high_impact", []),
                    "sentiment": shared_state.get("market_sentiment_score", 0),
                    "last_run": shared_state.get("news_last_run")})

@app.route("/api/commodities")
def api_commodities():
    return jsonify({"commodities": shared_state.get("commodity_results", []),
                    "alerts": shared_state.get("commodity_alerts", []),
                    "sentiment": shared_state.get("commodity_sentiment", "NEUTRAL"),
                    "last_run": shared_state.get("commodity_last_run")})

@app.route("/api/indices")
def api_indices():
    return jsonify(shared_state.get("index_prices", {}))

@app.route("/api/run-now", methods=["GET","POST"])
def api_run_now():
    threading.Thread(target=run_all_agents, daemon=True).start()
    return jsonify({"status": "14-agent cycle triggered", "agents_available": AGENTS_AVAILABLE})

@app.route("/api/agent-status")
def api_agent_status():
    portfolio = shared_state.get("paper_portfolio", {})
    return jsonify({
        "agents_available":   AGENTS_AVAILABLE,
        "learning_available": LEARNING_AVAILABLE,
        "cycle_count":        shared_state["cycle_count"],
        "last_full_cycle":    shared_state["last_full_cycle"],
        "is_running":         agent_is_running,
        "agent_status":       shared_state["agent_status"],
        "scanner_count":      len(shared_state.get("scanner_results", [])),
        "signals_count":      len(shared_state.get("actionable_signals", [])),
        "news_count":         len(shared_state.get("news_results", [])),
        "paper_positions":    len([p for p in portfolio.get("positions", {}).values() if p.get("status") == "OPEN"]),
        "paper_win_rate":     portfolio.get("stats", {}).get("win_rate", 0),
        "claude_available":   bool(ANTHROPIC_API_KEY),
        "gemini_available":   bool(GEMINI_API_KEY),
    })

@app.route("/api/agent-log")
def api_agent_log():
    return jsonify({"log": shared_state.get("agent_cycle_log", [])[-100:]})

@app.route("/api/claude-analysis")
def api_claude_analysis():
    return jsonify(shared_state.get("claude_analysis", {}))

@app.route("/api/technical")
def api_technical():
    return jsonify({"data": shared_state.get("technical_data", {}),
                    "last_run": shared_state.get("technical_last_run")})

@app.route("/api/institutional-flow")
def api_institutional_flow():
    return jsonify(shared_state.get("institutional_flow", {}))

@app.route("/api/options-flow")
def api_options_flow():
    return jsonify(shared_state.get("options_flow", {}))

@app.route("/api/sector-rotation")
def api_sector_rotation():
    return jsonify(shared_state.get("sector_rotation", {}))

@app.route("/api/risk-summary")
def api_risk_summary():
    return jsonify(shared_state.get("risk_summary", {}))

@app.route("/api/web-research")
def api_web_research():
    return jsonify(shared_state.get("web_research", {}))

@app.route("/api/paper-portfolio")
def api_paper_portfolio():
    return jsonify(shared_state.get("paper_portfolio", {}))

@app.route("/api/paper-trades")
def api_paper_trades():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "paper_trades.json")
        with open(path) as f: trades = json.load(f)
        return jsonify({"trades": trades[-50:], "total": len(trades)})
    except Exception:
        return jsonify({"trades": [], "total": 0})

@app.route("/api/paper-stats")
def api_paper_stats():
    portfolio = shared_state.get("paper_portfolio", {})
    capital   = portfolio.get("capital", 500000)
    return jsonify({
        "capital":          capital,
        "available_cash":   portfolio.get("available_cash", capital),
        "invested":         portfolio.get("invested", 0),
        "realized_pnl":     portfolio.get("realized_pnl", 0),
        "unrealized_pnl":   portfolio.get("unrealized_pnl", 0),
        "total_return_pct": portfolio.get("total_return_pct", 0),
        "daily_pnl_pct":    portfolio.get("daily_pnl_pct", 0),
        "stats":            portfolio.get("stats", {}),
        "open_positions":   [{"name": k, **v}
                             for k, v in portfolio.get("positions", {}).items()
                             if v.get("status") == "OPEN"],
        "safety": {"live_trading": False, "paper_only": True, "mode": "SIMULATION"},
    })

@app.route("/api/learning-stats")
def api_learning_stats():
    try:
        _base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(_base, "data", "accuracy_stats.json"))  as f: stats   = json.load(f)
        with open(os.path.join(_base, "data", "learned_weights.json")) as f: weights = json.load(f)
        return jsonify({"accuracy": stats, "weights": weights})
    except Exception:
        return jsonify({"accuracy": {}, "weights": {}})

@app.route("/api/patterns")
def api_patterns():
    return jsonify({"patterns": shared_state.get("pattern_library", []),
                    "count": len(shared_state.get("pattern_library", []))})

@app.route("/api/signal-history")
def api_signal_history():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "signal_history.json")
        with open(path) as f: history = json.load(f)
        open_s  = [r for r in history if r.get("outcome") == "OPEN"]
        settled = [r for r in history if r.get("outcome") not in ("OPEN",)]
        return jsonify({"total": len(history), "open": len(open_s), "settled": len(settled),
                        "recent": sorted(settled, key=lambda x: x.get("exit_at",""), reverse=True)[:20]})
    except Exception:
        return jsonify({"total": 0, "open": 0, "settled": 0, "recent": []})

@app.route("/api/morning-brief")
def api_morning_brief():
    if not AGENTS_AVAILABLE:
        return jsonify({"status": "agents not available"})
    msg = morning_brief.build_brief(shared_state)
    send_telegram(msg)
    return jsonify({"status": "sent", "preview": msg[:200]})

@app.route("/api/prices")
def api_prices():
    return jsonify({"prices": price_cache, "last_update": last_update})

@app.route("/api/watchlist")
def api_watchlist():
    result = []
    for stock in WATCHLIST:
        cached = price_cache.get(stock["name"], {})
        score, signal, target, sl = calculate_score(stock)
        result.append({**stock, "price": cached.get("price", "--"),
                       "change": cached.get("change", 0), "change_pct": cached.get("change_pct", 0),
                       "score": score, "signal": signal, "target": target, "sl": sl,
                       "updated": cached.get("updated", "--")})
    result.sort(key=lambda x: -x["score"])
    return jsonify(result)

@app.route("/api/market-mood")
def api_market_mood():
    nifty = price_cache.get("NIFTY 50", {})
    vix   = price_cache.get("INDIA VIX", {})
    chg   = nifty.get("change_pct", 0)
    vix_v = vix.get("price", 15)
    mood  = max(0, min(100, 50 + (chg * 5) - max(0, (vix_v - 15) * 1.5)))
    label = "EXTREME GREED" if mood >= 75 else "GREED" if mood >= 60 else "NEUTRAL" if mood >= 45 else "FEAR" if mood >= 30 else "EXTREME FEAR"
    return jsonify({"score": round(mood, 1), "label": label})

@app.route("/api/alerts")
def api_alerts():
    return jsonify(alert_log[-20:])

@app.route("/api/refresh")
def api_refresh():
    threading.Thread(target=fetch_all_prices, daemon=True).start()
    return jsonify({"status": "Refresh triggered"})

@app.route("/api/test-telegram")
def api_test_telegram():
    ok = send_telegram("✅ *StockGuru v2.0* connected! 14-Agent AI system active. 🤖🚀")
    return jsonify({"status": "sent" if ok else "failed"})

@app.route("/api/update-keys", methods=["POST"])
def api_update_keys():
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    global ANTHROPIC_API_KEY, GEMINI_API_KEY
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data received"}), 400
        # If value contains **** it's a masked display value — keep existing key instead
        def resolve(field, existing):
            v = data.get(field, '').strip()
            return existing if '****' in v else v
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        new_anthropic = resolve('anthropic_api_key', ANTHROPIC_API_KEY)
        new_gemini    = resolve('gemini_api_key',    GEMINI_API_KEY)
        new_tg_token  = resolve('telegram_token',    TELEGRAM_TOKEN)
        new_tg_chat   = data.get('telegram_chat_id', TELEGRAM_CHAT_ID).strip()
        lines = [
            "# StockGuru v2.0 Configuration\n",
            f"TELEGRAM_TOKEN={new_tg_token}\n",
            f"TELEGRAM_CHAT_ID={new_tg_chat}\n",
            f"ANTHROPIC_API_KEY={new_anthropic}\n",
            f"GEMINI_API_KEY={new_gemini}\n",
            f"PAPER_CAPITAL={data.get('paper_capital', '500000')}\n",
            f"FLASK_PORT={data.get('flask_port', '5000')}\n",
            f"PRICE_REFRESH_MINUTES={data.get('price_refresh', '5')}\n",
            "ALERT_CHECK_MINUTES=15\n",
        ]
        with open(env_path, "w") as f:
            f.writelines(lines)
        TELEGRAM_TOKEN    = new_tg_token
        TELEGRAM_CHAT_ID  = new_tg_chat
        ANTHROPIC_API_KEY = new_anthropic
        GEMINI_API_KEY    = new_gemini
        os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
        os.environ["GEMINI_API_KEY"]    = GEMINI_API_KEY
        log.info("🔑 API keys updated (Anthropic + Gemini)")
        return jsonify({"status": "ok", "message": "Keys saved successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/get-keys")
def api_get_keys():
    def mask(val):
        if not val: return ""
        if len(val) <= 8: return "*" * len(val)
        return val[:4] + "*" * (len(val) - 8) + val[-4:]
    return jsonify({
        "telegram_token": mask(TELEGRAM_TOKEN), "telegram_chat_id": TELEGRAM_CHAT_ID,
        "anthropic_api_key": mask(ANTHROPIC_API_KEY), "gemini_api_key": mask(GEMINI_API_KEY),
        "flask_port": os.getenv("FLASK_PORT", "5000"),
        "price_refresh": os.getenv("PRICE_REFRESH_MINUTES", "5"),
        "paper_capital": os.getenv("PAPER_CAPITAL", "500000"),
        "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
    })

@app.route("/api/status")
def api_status():
    portfolio = shared_state.get("paper_portfolio", {})
    return jsonify({
        "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
        "prices_loaded": len(price_cache), "last_update": last_update,
        "watchlist_count": len(WATCHLIST), "alerts_sent": len(alert_log),
        "paper_trades": portfolio.get("stats", {}).get("total_trades", 0),
        "paper_win_rate": portfolio.get("stats", {}).get("win_rate", 0),
        "agents_v2": AGENTS_AVAILABLE, "learning_active": LEARNING_AVAILABLE,
    })

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

def run_scheduler():
    schedule.every(5).minutes.do(fetch_all_prices)
    schedule.every().day.at("08:00").do(send_morning_brief)
    schedule.every().day.at("16:00").do(send_evening_debrief)
    schedule.every(15).minutes.do(check_alerts)
    if AGENTS_AVAILABLE:
        schedule.every(15).minutes.do(run_all_agents)
    log.info("⏰ Scheduler started — 14-agent cycle every 15 minutes")
    while True:
        schedule.run_pending()
        time.sleep(30)

# ── STARTUP ───────────────────────────────────────────────────────────────────
def _startup():
    """Called by both direct run (python app.py) and gunicorn (Railway/cloud)."""
    log.info("🚀 StockGuru v2.0 — 14-Agent Intelligence System")
    log.info("🔒 PAPER TRADING MODE: ACTIVE | LIVE TRADING: PERMANENTLY DISABLED")
    log.info("🧠 Claude AI: %s | Gemini AI: %s",
             "✅ configured" if ANTHROPIC_API_KEY else "❌ NOT SET — add ANTHROPIC_API_KEY to .env",
             "✅ configured" if GEMINI_API_KEY    else "⚠️  not set (optional but recommended)")

    threading.Thread(target=fetch_all_prices, daemon=True).start()
    if AGENTS_AVAILABLE:
        log.info("🤖 Launching 14-agent cycle on startup...")
        threading.Thread(target=run_all_agents, daemon=True).start()
    else:
        log.warning("⚠️  Agents not available — run from stockguru/ directory")
    threading.Thread(target=run_scheduler, daemon=True).start()

    log.info("✅ Server ready")
    log.info("🧠 AI Analysis → /api/claude-analysis")
    log.info("📊 Paper Portfolio → /api/paper-stats")
    log.info("📈 Learning → /api/learning-stats")
    log.info("🔑 Add API keys in dashboard Settings tab")

# Run startup for both gunicorn (Railway) and direct python app.py
_startup()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))   # Railway injects PORT automatically
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
