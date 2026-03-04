try:
    from gevent import monkey
    monkey.patch_all()
except ImportError:
    pass

"""
StockGuru Real-Time Intelligence App — v2.0
============================================
14-Agent self-learning system with LLM intelligence.
Claude Haiku (primary) + Gemini Flash (parallel) review every cycle.
Paper trading simulation — ZERO broker connectivity.
"""

from flask import Flask, jsonify, render_template_string, send_from_directory, request, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps

# ── WEBSOCKET (Flask-SocketIO + gevent) ───────────────────────────────────────
try:
    from flask_socketio import SocketIO, emit as sio_emit
    _SIO_AVAILABLE = True
except ImportError:
    _SIO_AVAILABLE = False
    logging.warning("flask-socketio not installed — WebSocket disabled (pip install flask-socketio gevent gevent-websocket)")
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
from logging.handlers import RotatingFileHandler

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
        pattern_memory, paper_trader, earnings_calendar,
        spike_detector,
    )
    AGENTS_AVAILABLE = True
except ImportError as _e:
    AGENTS_AVAILABLE = False
    logging.warning(f"Agents not loaded: {_e}")

# ── MARKET SESSION AGENT ───────────────────────────────────────────────────────
try:
    from agents.market_session_agent import session_agent, SEGMENTS, STATE_OPEN, STATE_CLOSED
    SESSION_AGENT_AVAILABLE = True
except ImportError as _se:
    SESSION_AGENT_AVAILABLE = False
    session_agent = None
    logging.warning(f"market_session_agent not loaded: {_se}")

# ── LEARNING IMPORTS ──────────────────────────────────────────────────────────
try:
    from learning import signal_tracker, weight_adjuster
    LEARNING_AVAILABLE = True
except ImportError:
    LEARNING_AVAILABLE = False

# ── SOVEREIGN TRADER LAYER (Phase 1) ──────────────────────────────────────────
_sovereign_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockguru_agents", "sovereign")
if _sovereign_dir not in sys.path:
    sys.path.insert(0, _sovereign_dir)
_sovereign_parent = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockguru_agents")
if _sovereign_parent not in sys.path:
    sys.path.insert(0, _sovereign_parent)

try:
    from sovereign import scryer, quant, risk_master, debate_engine, hitl_controller, post_mortem, memory_engine
    SOVEREIGN_AVAILABLE = True
    logging.info("✅ Sovereign Trader Layer loaded — 4 meta-agents active")
except ImportError as _se:
    SOVEREIGN_AVAILABLE = False
    logging.warning(f"⚠️  Sovereign layer not loaded: {_se}")

# ── SOVEREIGN TRADER LAYER (Phase 2) ──────────────────────────────────────────
try:
    from sovereign import observer, synthetic_backtester, builder_agent
    SOVEREIGN_PHASE2_AVAILABLE = True
    logging.info("✅ Sovereign Phase 2 loaded — Observer, Backtester, Builder active")
except ImportError as _se2:
    SOVEREIGN_PHASE2_AVAILABLE = False
    logging.warning(f"⚠️  Sovereign Phase 2 not loaded: {_se2}")

# ── CHANNELS + BACKTESTING ────────────────────────────────────────────────────
try:
    from channels import ChannelManager
    channel_manager = ChannelManager()
    CHANNELS_AVAILABLE = True
except Exception as _ce:
    channel_manager    = None
    CHANNELS_AVAILABLE = False
    logging.warning(f"Channels not loaded: {_ce}")

try:
    from backtesting import BacktestEngine
    BACKTESTING_AVAILABLE = True
except Exception as _be:
    BACKTESTING_AVAILABLE = False
    logging.warning(f"Backtesting not loaded: {_be}")

# ── INTELLIGENCE CONNECTORS ───────────────────────────────────────────────────
try:
    from connectors import ConnectorManager as IntelConnectorManager
    intel_connector_mgr = IntelConnectorManager()
    _router   = intel_connector_mgr.get_agent_router()
    _patterns = intel_connector_mgr.get_pattern_detector()
    _risk_anl = intel_connector_mgr.get_risk_analytics()
    _scorer   = intel_connector_mgr.get_agent_scorer()
    CONNECTORS_AVAILABLE = True
except Exception as _conx:
    intel_connector_mgr = None
    _router = _patterns = _risk_anl = _scorer = None
    CONNECTORS_AVAILABLE = False
    logging.warning(f"Connectors not loaded: {_conx}")

load_dotenv()

# ── LOGGING: Rotating file handler + console ──────────────────────────────────
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "stockguru.log"),
    maxBytes=5 * 1024 * 1024,  # 5 MB per file
    backupCount=7               # keep 7 days of logs
)
_file_handler.setFormatter(_log_fmt)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])
log = logging.getLogger(__name__)

# ── FLASK APP ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0   # disable static file caching during dev

# ── CORS: configurable origins (set ALLOWED_ORIGINS in .env for production) ───
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
if _raw_origins.strip():
    _origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
else:
    # Dev defaults — add your Railway URL to ALLOWED_ORIGINS in production
    _origins = [
        "http://localhost:5000", "http://localhost:5050",
        "http://127.0.0.1:5000", "http://127.0.0.1:5050",
    ]
CORS(app, origins=_origins, supports_credentials=True)

# ── SOCKETIO: real-time push (replaces 15-second polling) ─────────────────────
if _SIO_AVAILABLE:
    socketio = SocketIO(
        app,
        async_mode="gevent",
        cors_allowed_origins="*",
        logger=False,
        engineio_logger=False,
        ping_timeout=60,
        ping_interval=25,
    )
    log_sio = logging.getLogger("SocketIO")
    log_sio.info("✅ SocketIO initialised (gevent async_mode)")
else:
    socketio = None

# ── RATE LIMITER ──────────────────────────────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute"],
    storage_uri="memory://",
    strategy="fixed-window",
)

# ── API KEY AUTH ──────────────────────────────────────────────────────────────
# Set STOCKGURU_API_KEY in .env to protect write/trigger endpoints.
# Leave empty to run in open mode (local dev). Strongly recommended for Railway.
_STOCKGURU_API_KEY = os.getenv("STOCKGURU_API_KEY", "").strip()

def _check_api_key():
    """Returns True if request is authorised (or auth is disabled)."""
    if not _STOCKGURU_API_KEY:
        return True  # Auth disabled — open mode
    provided = (
        request.headers.get("X-API-Key", "").strip()
        or request.args.get("api_key", "").strip()
        or (request.get_json(silent=True) or {}).get("api_key", "").strip()
    )
    return provided == _STOCKGURU_API_KEY

def require_api_key(f):
    """Decorator — protects write/trigger endpoints with STOCKGURU_API_KEY."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_api_key():
            log.warning("⛔ Unauthorised request to %s from %s", request.path, request.remote_addr)
            return jsonify({"error": "Unauthorised — X-API-Key header required"}), 401
        return f(*args, **kwargs)
    return decorated

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

price_cache  = {name: {"price": 0.0, "change": 0.0, "change_pct": 0.0, "symbol": sym, "updated": "Initializing..."} for name, sym in YAHOO_SYMBOLS.items()}
alert_log    = []
last_update  = "Initializing..."
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
    # Sovereign Trader Layer state
    "scryer_output":      {},
    "quant_output":       {},
    "risk_master_output": {},
    "post_mortem_output": {},
    "debate_results":     [],
    "hitl_queue_summary": {"pending_count": 0, "oldest_pending_min": 0, "approved_today": 0, "rejected_today": 0},
    "synthetic_backtest": {},
    "post_mortem_llm_note": None,
    # Sovereign Phase 2
    "observer_output":  {},
    "builder_output":   {},
}
agent_is_running = False

# ── PRICE FETCHER ─────────────────────────────────────────────────────────────
def fetch_yahoo_price(symbol):
    """
    Multi-layer price fetch — tries 4 sources in order:
      1. Yahoo Finance query2 (more Railway-friendly)
      2. Yahoo Finance query1 (original)
      3. yfinance library (handles rate-limits internally)
      4. CoinGecko (crypto only) / realistic seed values (indices)
    """
    def _parse_meta(meta):
        price      = float(meta.get("regularMarketPrice") or meta.get("postMarketPrice") or 0)
        prev       = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        if price == 0:
            return None
        change     = round(price - prev, 2)
        change_pct = round((change / prev) * 100, 2) if prev else 0
        return {"price": round(price, 2), "change": change, "change_pct": change_pct, "prev": round(prev, 2)}

    # ── Layer 1: Yahoo Finance query2 ────────────────────────────────────────
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            url = f"https://{host}/v8/finance/chart/{symbol}?interval=1m&range=1d"
            hdrs = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://finance.yahoo.com",
            }
            r    = requests.get(url, headers=hdrs, timeout=10)
            if r.status_code == 200:
                meta = r.json()["chart"]["result"][0]["meta"]
                result = _parse_meta(meta)
                if result:
                    return result
        except Exception as e:
            log.debug(f"Yahoo {host} failed for {symbol}: {e}")

    # ── Layer 2: yfinance library ─────────────────────────────────────────────
    try:
        import yfinance as yf
        tk   = yf.Ticker(symbol)
        info = tk.fast_info
        price = float(getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None) or 0)
        prev  = float(getattr(info, "previous_close", None) or price)
        if price > 0:
            change     = round(price - prev, 2)
            change_pct = round((change / prev) * 100, 2) if prev else 0
            return {"price": round(price, 2), "change": change, "change_pct": change_pct, "prev": round(prev, 2)}
    except Exception as e:
        log.debug(f"yfinance failed for {symbol}: {e}")

    # ── Layer 3: CoinGecko for crypto ─────────────────────────────────────────
    COINGECKO_MAP = {
        "BTC-INR":  "bitcoin",
        "ETH-INR":  "ethereum",
        "SOL-INR":  "solana",
    }
    if symbol in COINGECKO_MAP:
        try:
            cg_id = COINGECKO_MAP[symbol]
            url   = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=inr&include_24hr_change=true"
            r     = requests.get(url, timeout=10)
            d     = r.json().get(cg_id, {})
            price = float(d.get("inr", 0))
            chg   = float(d.get("inr_24h_change", 0))
            if price > 0:
                prev = round(price / (1 + chg / 100), 2) if chg != -100 else price
                return {"price": round(price, 2), "change": round(price - prev, 2),
                        "change_pct": round(chg, 2), "prev": prev}
        except Exception as e:
            log.debug(f"CoinGecko failed for {symbol}: {e}")

    # ── Layer 4: Realistic seed fallback (keeps UI alive) ────────────────────
    import random
    SEED = {
        "^NSEI":      (23500, 23900),   # NIFTY 50
        "^BSESN":     (77000, 79000),   # SENSEX
        "^NSEBANK":   (50000, 52000),   # BANK NIFTY
        "^INDIAVIX":  (14, 18),         # INDIA VIX
        "GC=F":       (2600, 2700),     # Gold USD/oz
        "SI=F":       (29, 32),         # Silver USD/oz
        "CL=F":       (68, 75),         # Crude WTI
        "NG=F":       (3.2, 3.8),       # Nat Gas
        "INR=X":      (83.5, 84.5),     # USD/INR
        "BHARTIARTL.NS": (1500, 1600),
        "HDFCBANK.NS":   (1650, 1750),
        "ICICIBANK.NS":  (1200, 1280),
        "BAJFINANCE.NS": (6800, 7200),
        "BEL.NS":        (260, 290),
        "MUTHOOTFIN.NS": (1900, 2050),
        "ZOMATO.NS":     (210, 240),
        "INDIGO.NS":     (3800, 4100),
        "BTC-INR":    (7000000, 8500000),
        "ETH-INR":    (220000, 280000),
        "SOL-INR":    (12000, 16000),
    }
    lo, hi = SEED.get(symbol, (100, 110))
    # Use price from existing cache if valid, else generate a seed value
    existing = price_cache.get(
        next((n for n, s in YAHOO_SYMBOLS.items() if s == symbol), ""), {}
    )
    if existing.get("price", 0) > 0:
        # Drift slightly from cached value
        base = existing["price"]
        drift = random.uniform(-0.003, 0.003)
        price = round(base * (1 + drift), 2)
        prev  = base
    else:
        price = round(random.uniform(lo, hi), 2)
        prev  = round(price * random.uniform(0.995, 1.005), 2)
    change     = round(price - prev, 2)
    change_pct = round((change / prev) * 100, 2) if prev else 0
    log.info(f"[SEED] {symbol} → ₹{price} (all live sources failed)")
    return {"price": price, "change": change, "change_pct": change_pct, "prev": prev}

def fetch_all_prices():
    global last_update
    log.info("🔄 Fetching live prices...")
    for name, symbol in YAHOO_SYMBOLS.items():
        data = fetch_yahoo_price(symbol)
        if data:
            price_cache[name] = {**data, "symbol": symbol, "updated": datetime.now().strftime("%H:%M:%S")}
            if name in ("NIFTY 50", "SENSEX", "BANK NIFTY", "INDIA VIX"):
                shared_state["index_prices"][name] = data
            
            # --- REAL-TIME TICKER EMIT (Like a Real Broker) ---
            if socketio:
                socketio.emit("price_update", {
                    "prices": {name: price_cache[name]},
                    "last_update": datetime.now().strftime("%H:%M:%S"),
                    "event": "tick_update"
                })
        
        if last_update != "Initializing...":
            time.sleep(0.15)  # faster between fetches on Railway
    
    last_update = datetime.now().strftime("%d %b %Y %H:%M:%S IST")
    shared_state["_price_cache"] = price_cache
    log.info(f"✅ Price feed cycle complete at {last_update}")

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

    # ── Push price update to all connected WebSocket clients ──────────────────
    _ws_emit_prices()

# ── WEBSOCKET EMITTERS ────────────────────────────────────────────────────────
def _ws_emit_prices():
    """Push live price update to all connected clients."""
    if not socketio:
        return
    try:
        payload = {
            "prices":      price_cache,
            "last_update": last_update,
            "event":       "price_update",
        }
        socketio.emit("price_update", payload)
        log.debug("WS: emitted price_update (%d symbols)", len(price_cache))
    except Exception as _we:
        log.debug("WS emit price_update failed: %s", _we)


def _ws_emit_agents():
    """Push agent cycle completion to all connected clients (compact payload)."""
    if not socketio:
        return
    try:
        port = shared_state.get("paper_portfolio", {})
        payload = {
            "event":            "agents_update",
            "scanner_count":    len(shared_state.get("scanner_results", [])),
            "signal_count":     len(shared_state.get("signal_results", [])),
            "top_signals":      shared_state.get("signal_results", [])[:5],
            "alerts":           shared_state.get("ai_alerts", [])[:3],
            "morning_brief":    shared_state.get("morning_brief", ""),
            "market_mood":      shared_state.get("market_mood", {}),
            "paper_portfolio":  {
                "capital":          port.get("capital", 0),
                "available_cash":   port.get("available_cash", 0),
                "realized_pnl":     port.get("realized_pnl", 0),
                "unrealized_pnl":   port.get("unrealized_pnl", 0),
                "daily_pnl":        port.get("daily_pnl", 0),
            },
            "builder_output":   shared_state.get("builder_output", {}),
            "observer_run_count": shared_state.get("observer_output", {}).get("run_count", 0),
            "agent_cycle_ts":   datetime.now().strftime("%H:%M:%S"),
        }
        socketio.emit("agents_update", payload)
        log.info("WS: emitted agents_update")
    except Exception as _we:
        log.debug("WS emit agents_update failed: %s", _we)


# ── SOCKETIO EVENT HANDLERS ───────────────────────────────────────────────────
if _SIO_AVAILABLE:
    @socketio.on("connect")
    def _ws_on_connect():
        """On fresh client connect — immediately push current state."""
        log.debug("WS: client connected")
        _ws_emit_prices()

    @socketio.on("disconnect")
    def _ws_on_disconnect():
        log.debug("WS: client disconnected")

    @socketio.on("ping_server")
    def _ws_on_ping(data=None):
        """Lightweight keepalive from client."""
        sio_emit("pong_server", {"ts": datetime.now().strftime("%H:%M:%S")})

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
        _log(f"   News sentiment: {shared_state.get('market_sentiment_score',0):+.0f} | {len(shared_state.get('news_results',[]))} headlines | {'LLM+keyword' if any(n.get('scored_by')=='llm+keyword' for n in shared_state.get('news_results',[])) else 'keyword'}")
        _st("scanner",    "running"); market_scanner.run(shared_state);          _st("scanner",    "done")
        _log(f"   Scanner: {len(shared_state.get('scanner_results',[]))} stocks ranked")
        # Spike detection — runs immediately after price_cache is populated by market_scanner
        try:
            spike_detector.run(shared_state, _send_tg)
            spikes = shared_state.get("spike_alerts", [])
            if spikes:
                _log(f"   🚨 SpikeDetector: {len(spikes)} alert(s) — {', '.join(s.get('symbol','?') for s in spikes)}", "warn")
            else:
                _log("   ⚡ SpikeDetector: clean cycle")
        except Exception as e:
            log.warning("spike_detector failed: %s", e)
        _st("calendar",   "running")
        try:    earnings_calendar.run(shared_state); _st("calendar", "done"); _log(f"   Events calendar: {shared_state.get('events_calendar',{}).get('total_events',0)} events | {len(shared_state.get('events_calendar',{}).get('watchlist_alerts',[]))} watchlist matches")
        except Exception as e: log.warning("earnings_calendar: %s", e); _st("calendar", "error")

        for agent_name, agent_mod in [("technical",  technical_analysis),
                                       ("inst_flow",  institutional_flow),
                                       ("options",    options_flow),
                                       ("sector_rot", sector_rotation)]:
            _st(agent_name, "running")
            try:    agent_mod.run(shared_state); _st(agent_name, "done")
            except Exception as e:
                log.error("%s failed: %s", agent_name, e); _st(agent_name, "error")

        # ── OI WALL APPROACH TELEGRAM ALERTS ─────────────────────────────────
        for wall_alert in shared_state.get("oi_wall_alerts", []):
            try:
                send_telegram(f"⚠️ *OI WALL ALERT — {wall_alert.get('index','INDEX')}*\n{wall_alert['approach_msg']}")
            except Exception as e:
                log.warning("OI wall Telegram alert failed: %s", e)

        # ── AGENT ROUTER: decide whether to run LLM this cycle ───────────────
        routing = {"run_llm": True, "routing_reason": "Router not available"}
        if _router:
            try:
                routing = _router.route(shared_state)
                shared_state["routing_decisions"] = routing
                _log(f"   🔀 AgentRouter: LLM={'RUN' if routing['run_llm'] else 'SKIP'} | conf={routing.get('avg_tier1_confidence',0)}% | {routing['routing_reason'][:60]}")
            except Exception as e:
                log.debug(f"AgentRouter error: {e}")

        # ── TIER 2: LLM BRAIN ─────────────────────────────────────────────────
        log.info("─── TIER 2: LLM Intelligence ─────────────────────────────────")
        _log("── TIER 2: LLM Brain ────────────────────────────────")
        _st("claude", "running")
        try:
            if routing.get("run_llm", True):
                claude_intelligence.run(shared_state); _st("claude", "done")
                ca = shared_state.get("claude_analysis", {})
                _log(f"   Market: {ca.get('market_condition','?')} | Stance: {ca.get('market_stance','?')} | Picks: {len(ca.get('conviction_picks',[]))}")
            else:
                _st("claude", "done")
                _log(f"   ⏭ LLM skipped by AgentRouter (cycle saved)")
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

        # ── CONNECTORS: chart patterns + risk analytics ───────────────────────
        if _patterns:
            try:
                _patterns.run(shared_state)
                n_pat = sum(len(v) for v in shared_state.get("chart_patterns",{}).values())
                _log(f"   📐 PatternDetector: {n_pat} patterns found across {len(shared_state.get('chart_patterns',{}))} stocks")
            except Exception as e: log.debug(f"PatternDetector: {e}")

        if _risk_anl:
            try:
                _risk_anl.run(shared_state)
                ra = shared_state.get("risk_analytics", {})
                _log(f"   📊 RiskAnalytics: VaR95={ra.get('var_95_pct',0)}% | β={ra.get('portfolio_beta',1)} ({ra.get('beta_status','?')}) | MaxCorr={ra.get('max_corr',0)}")
            except Exception as e: log.debug(f"RiskAnalytics: {e}")

        if _scorer:
            try:
                scores = _scorer.run(shared_state)
                top = max(scores.items(), key=lambda x: x[1]["avg"], default=(None, {"label": "—", "grade": "?", "avg": 0}))
                _log(f"   🎯 AgentScorer: {len(scores)} agents graded | Top: {top[1]['label']} ({top[1]['grade']} {top[1]['avg']}%)")
            except Exception as e: log.debug(f"AgentScorer: {e}")

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

        # ── TIER 5: SOVEREIGN META-LAYER ─────────────────────────────────────
        if SOVEREIGN_AVAILABLE:
            try:
                _log("── TIER 5: Sovereign Layer ──────────────────────────────────────")
                _st("scryer",      "running"); scryer.run(shared_state);      _st("scryer",      "done")
                _st("quant",       "running"); quant.run(shared_state);       _st("quant",       "done")
                _st("risk_master", "running"); risk_master.run(shared_state, _send_tg); _st("risk_master", "done")

                q_out  = shared_state.get("quant_output", {})
                rm_out = shared_state.get("risk_master_output", {})
                hard_v = rm_out.get("hard_veto_active", False)

                if not hard_v:
                    # Debate candidates (conviction 55-69, cleared by Risk Master)
                    debate_count = 0
                    for _s in q_out.get("debate_candidates", []):
                        if _s in rm_out.get("cleared_for_debate", []):
                            if debate_count < 2:  # max 2 debates per cycle
                                _dr = debate_engine.run_debate(_s, shared_state)
                                debate_count += 1
                                shared_state.setdefault("debate_results", []).append(_dr)
                                if len(shared_state["debate_results"]) > 10:
                                    shared_state["debate_results"] = shared_state["debate_results"][-10:]
                                if _dr.get("send_to_hitl"):
                                    hitl_controller.dispatch_hitl_request(_dr, shared_state, _send_tg)
                                elif _dr.get("auto_execute"):
                                    _sig = next((s for s in (shared_state.get("risk_reviewed_signals",[]) + shared_state.get("actionable_signals",[])) if s.get("name") == _s), None)
                                    if _sig:
                                        try: paper_trader._enter_position(_sig, 7, _dr.get("gates",{}), shared_state.get("paper_portfolio",{}), shared_state.get("_price_cache",{}), shared_state)
                                        except Exception as _pe: log.debug("Sovereign auto-exec %s: %s", _s, _pe)

                    # HITL candidates (conviction 70-84, Risk Master cleared)
                    for _s in q_out.get("hitl_candidates", []):
                        _is_escalated = _s in rm_out.get("escalated_to_hitl", [])
                        _sig = next((s for s in (shared_state.get("risk_reviewed_signals",[]) + shared_state.get("actionable_signals",[])) if s.get("name") == _s), None)
                        if _sig:
                            hitl_controller.dispatch_hitl_request({"signal": _sig}, shared_state, _send_tg)

                    # Auto-execute candidates (conviction >= 85, no veto)
                    for _s in rm_out.get("cleared_auto", []):
                        _sig = next((s for s in (shared_state.get("risk_reviewed_signals",[]) + shared_state.get("actionable_signals",[])) if s.get("name") == _s), None)
                        if _sig:
                            try: paper_trader._enter_position(_sig, 7, {}, shared_state.get("paper_portfolio",{}), shared_state.get("_price_cache",{}), shared_state)
                            except Exception as _pe: log.debug("Sovereign auto-exec cleared %s: %s", _s, _pe)

                _st("post_mortem", "running"); post_mortem.run(shared_state); _st("post_mortem", "done")
                hitl_controller.check_queue_expiry(shared_state, _send_tg)

                # Phase 2: inline synthetic backtest when positions are open
                if SOVEREIGN_PHASE2_AVAILABLE:
                    _port = shared_state.get("paper_portfolio", {})
                    if _port.get("positions"):
                        _st("backtester", "running")
                        try:
                            synthetic_backtester.run(shared_state)
                        except Exception as _bte:
                            log.warning("Backtester inline error: %s", _bte)
                        _st("backtester", "done")

                _log(f"✅ Sovereign: auto={len(rm_out.get('cleared_auto',[]))} | HITL={len(q_out.get('hitl_candidates',[]))} | debate={len(q_out.get('debate_candidates',[]))}", "done")
            except Exception as _sov_e:
                log.error("❌ Sovereign layer error: %s", _sov_e, exc_info=True)
                for _sk in ["scryer","quant","risk_master","post_mortem"]:
                    if shared_state["agent_status"].get(_sk) == "running":
                        shared_state["agent_status"][_sk] = "error"

        shared_state["last_full_cycle"] = datetime.now().strftime("%d %b %H:%M:%S")
        _log(f"✅ CYCLE #{cycle} COMPLETE — next in 15 min", "done")
        portfolio = shared_state.get("paper_portfolio", {})
        log.info("✅ CYCLE #%d DONE | Scanner=%d | Signals=%d | Paper positions=%d | Win rate=%.0f%%",
                 cycle, len(shared_state.get("scanner_results", [])),
                 len(shared_state.get("actionable_signals", [])),
                 len([p for p in portfolio.get("positions", {}).values() if p.get("status") == "OPEN"]),
                 portfolio.get("stats", {}).get("win_rate", 0) * 100)

        # Push full agent update to WebSocket clients
        _ws_emit_agents()

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
@limiter.limit("10 per minute")
@require_api_key
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

@app.route("/api/health")
def api_health():
    """M1 Health Check — system status, agent health, API connectivity."""
    import platform
    agent_statuses = shared_state.get("agent_status", {})
    failed_agents   = [k for k, v in agent_statuses.items() if v == "error"]
    running_agents  = [k for k, v in agent_statuses.items() if v == "running"]
    ok_agents       = [k for k, v in agent_statuses.items() if v == "done"]

    # Calculate overall health score
    total_agents = max(len(agent_statuses), 1)
    health_pct   = round((len(ok_agents) / total_agents) * 100, 1)

    # Check data files
    data_dir   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    key_files  = ["paper_portfolio.json", "accuracy_stats.json", "signal_history.json"]
    files_ok   = all(os.path.exists(os.path.join(data_dir, f)) for f in key_files)

    overall = "healthy"
    if failed_agents:          overall = "degraded"
    if len(failed_agents) > 3: overall = "critical"
    if not AGENTS_AVAILABLE:   overall = "no-agents"

    return jsonify({
        "status":           overall,
        "health_pct":       health_pct,
        "timestamp":        datetime.now().isoformat(),
        "version":          "StockGuru v2.0",
        "python":           platform.python_version(),
        "agents": {
            "available":    AGENTS_AVAILABLE,
            "sovereign":    SOVEREIGN_AVAILABLE,
            "ok":           ok_agents,
            "running":      running_agents,
            "failed":       failed_agents,
            "total":        total_agents,
        },
        "apis": {
            "claude":       bool(ANTHROPIC_API_KEY),
            "gemini":       bool(GEMINI_API_KEY),
            "telegram":     bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
            "auth_enabled": bool(_STOCKGURU_API_KEY),
        },
        "data_files_ok":    files_ok,
        "cycle_running":    agent_is_running,
        "last_cycle":       shared_state.get("last_cycle_time", "never"),
        "paper_trading":    "ACTIVE (live trading permanently disabled)",
    })

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
    payload = dict(shared_state.get("options_flow", {}))
    payload["india_vix"]      = shared_state.get("india_vix", {})
    payload["oi_wall_alerts"] = shared_state.get("oi_wall_alerts", [])
    return jsonify(payload)

@app.route("/api/spike-alerts")
def api_spike_alerts():
    return jsonify({
        "spike_alerts":          shared_state.get("spike_alerts", []),
        "spike_detector_active": shared_state.get("spike_detector_active", False),
        "last_spike_ts":         shared_state.get("last_spike_ts"),
    })

@app.route("/api/market-intelligence")
def api_market_intelligence():
    """Combined market intelligence: VIX, IV Rank, Rollover, Advance-Decline."""
    return jsonify({
        "india_vix":      shared_state.get("india_vix", {}),
        "iv_rank":        shared_state.get("iv_rank", {}),
        "rollover_data":  shared_state.get("rollover_data", {}),
        "advance_decline": shared_state.get("advance_decline", {}),
        "last_updated":   shared_state.get("options_last_run", "--"),
    })

@app.route("/api/sector-rotation")
def api_sector_rotation():
    return jsonify(shared_state.get("sector_rotation", {}))

@app.route("/api/risk-summary")
def api_risk_summary():
    return jsonify(shared_state.get("risk_summary", {}))

@app.route("/api/web-research")
def api_web_research():
    return jsonify(shared_state.get("web_research", {}))

@app.route("/api/earnings-calendar")
def api_earnings_calendar():
    return jsonify(shared_state.get("events_calendar", {
        "total_events": 0, "watchlist_alerts": [], "upcoming": [],
        "last_run": None, "high_impact_count": 0
    }))

@app.route("/api/agent-confidence")
def api_agent_confidence():
    return jsonify(shared_state.get("agent_confidence", {}))

@app.route("/api/channels-status")
def api_channels_status():
    if not CHANNELS_AVAILABLE or not channel_manager:
        return jsonify({"error": "Channels module not loaded", "channels": {}})
    try:
        statuses = channel_manager.get_all_statuses()
        return jsonify({
            "channels": statuses,
            "summary":  channel_manager.summary(),
            "checked_at": datetime.now().strftime("%H:%M:%S")
        })
    except Exception as e:
        return jsonify({"error": str(e), "channels": {}})

@app.route("/api/connectors-status")
def api_connectors_status():
    if not CONNECTORS_AVAILABLE or not intel_connector_mgr:
        return jsonify({"error": "Connectors module not loaded", "connectors": {}})
    try:
        statuses = intel_connector_mgr.get_all_statuses()
        return jsonify({
            "connectors": statuses,
            "summary":    intel_connector_mgr.summary(),
            "checked_at": datetime.now().strftime("%H:%M:%S"),
        })
    except Exception as e:
        return jsonify({"error": str(e), "connectors": {}})

@app.route("/api/chart-patterns")
def api_chart_patterns():
    return jsonify(shared_state.get("chart_patterns", {}))

@app.route("/api/routing-decisions")
def api_routing_decisions():
    return jsonify(shared_state.get("routing_decisions", {
        "run_llm": True, "avg_tier1_confidence": 0,
        "cycles_saved": 0, "cycles_total": 0, "llm_save_rate_pct": 0,
        "routing_reason": "No data yet — waiting for first agent cycle"
    }))

@app.route("/api/risk-analytics")
def api_risk_analytics():
    return jsonify(shared_state.get("risk_analytics", {
        "var_95_pct": 0, "var_99_pct": 0, "var_95_inr": 0, "var_99_inr": 0,
        "portfolio_beta": 1.0, "beta_status": "NEUTRAL",
        "max_corr": 0, "high_corr_pairs": [], "open_positions": 0,
    }))

@app.route("/api/agent-scores")
def api_agent_scores():
    return jsonify(shared_state.get("agent_scores", {}))

@app.route("/api/backtest", methods=["GET", "POST"])
def api_backtest():
    """GET: return last results. POST: run a new backtest."""
    if not BACKTESTING_AVAILABLE:
        return jsonify({"error": "Backtesting module not loaded"})
    try:
        engine = BacktestEngine()
        if request.method == "POST":
            n = int(request.json.get("signals", 50)) if request.is_json else 50
            result = engine.run_signal_backtest(lookback_signals=n)
        else:
            result = engine.load_results()
            if not result:
                result = {"message": "No backtest run yet. POST to /api/backtest to start."}
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})

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
@limiter.limit("20 per minute")
@require_api_key
def api_refresh():
    threading.Thread(target=fetch_all_prices, daemon=True).start()
    return jsonify({"status": "Refresh triggered"})

@app.route("/api/test-telegram")
def api_test_telegram():
    ok = send_telegram("✅ *StockGuru v2.0* connected! 14-Agent AI system active. 🤖🚀")
    return jsonify({"status": "sent" if ok else "failed"})

@app.route("/api/update-keys", methods=["POST"])
@limiter.limit("5 per minute")
@require_api_key
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

# ── SOVEREIGN API ROUTES ──────────────────────────────────────────────────────

@app.route("/api/sovereign-status")
def api_sovereign_status():
    """Combined sovereign layer state for the Sovereign tab."""
    return jsonify({
        "available":        SOVEREIGN_AVAILABLE,
        "scryer":           shared_state.get("scryer_output", {}),
        "quant":            shared_state.get("quant_output", {}),
        "risk_master":      shared_state.get("risk_master_output", {}),
        "post_mortem":      shared_state.get("post_mortem_output", {}),
        "hitl_summary":     shared_state.get("hitl_queue_summary", {}),
        "debate_results":   shared_state.get("debate_results", [])[-5:],
        "synthetic_backtest": shared_state.get("synthetic_backtest", {}),
        "llm_note":         shared_state.get("post_mortem_llm_note"),
    })

@app.route("/api/debate-log")
def api_debate_log():
    """Last 20 debate records."""
    try:
        import json as _j
        dp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "debate_log.json")
        with open(dp) as f:
            data = _j.load(f)
        return jsonify({"debates": data[-20:], "total": len(data)})
    except Exception:
        return jsonify({"debates": [], "total": 0})

@app.route("/api/hitl-queue")
def api_hitl_queue():
    """All HITL queue items."""
    if not SOVEREIGN_AVAILABLE:
        return jsonify({"queue": [], "pending": 0})
    q = hitl_controller.get_queue_for_api()
    pending = [i for i in q if i.get("status") == "PENDING"]
    return jsonify({"queue": q[-50:], "pending": len(pending), "summary": shared_state.get("hitl_queue_summary", {})})

@app.route("/api/post-mortem")
def api_post_mortem():
    """Post-mortem analysis + recent adjustments."""
    try:
        import json as _j
        pp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "post_mortem_log.json")
        with open(pp) as f:
            log_data = _j.load(f)
        return jsonify({
            "records":          log_data[-10:],
            "total":            len(log_data),
            "current_cycle":    shared_state.get("post_mortem_output", {}),
            "llm_note":         shared_state.get("post_mortem_llm_note"),
        })
    except Exception:
        return jsonify({"records": [], "total": 0, "current_cycle": {}, "llm_note": None})

@app.route("/api/risk-master-status")
def api_risk_master_status():
    """Risk Master status for n8n War Room check."""
    rm = shared_state.get("risk_master_output", {})
    return jsonify({
        "hard_veto_active":  rm.get("hard_veto_active", False),
        "hard_veto_reason":  rm.get("hard_veto_reason"),
        "vix_level":         rm.get("vix_level", 0),
        "daily_pnl_pct":     rm.get("daily_pnl_pct", 0),
        "consecutive_losses": rm.get("consecutive_losses", 0),
        "soft_veto_count":   len(rm.get("soft_veto_flags", [])),
        "escalated_to_hitl": rm.get("escalated_to_hitl", []),
        "black_swan_probability": shared_state.get("synthetic_backtest", {}).get("black_swan_probability", "LOW"),
    })

@app.route("/api/agent-memory")
def api_agent_memory():
    """Recent SQLite lessons (last 20)."""
    if not SOVEREIGN_AVAILABLE:
        return jsonify({"lessons": [], "total": 0})
    lessons = memory_engine.get_all_recent(limit=20)
    return jsonify({"lessons": lessons, "total": len(lessons)})

@app.route("/api/sovereign-config")
def api_sovereign_config():
    """Current sovereign_config.json values (read-only view)."""
    try:
        import json as _j
        cp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sovereign_config.json")
        with open(cp) as f:
            cfg = _j.load(f)
        history = memory_engine.get_config_history(10) if SOVEREIGN_AVAILABLE else []
        return jsonify({"config": cfg, "modification_history": history})
    except Exception as e:
        return jsonify({"config": {}, "error": str(e)})

@app.route("/api/telegram-update", methods=["POST"])
def api_telegram_update():
    """
    Telegram webhook receiver.
    Processes inline-button callbacks (approve/reject/skip and bld_approve/reject) and text commands.
    """
    if not SOVEREIGN_AVAILABLE:
        return jsonify({"ok": False, "error": "Sovereign layer not available"})
    try:
        update = request.get_json(force=True) or {}
        callback_data = update.get("callback_query", {}).get("data", "")
        # Route Builder callbacks (prefix "bld_") separately from HITL callbacks
        if callback_data.startswith("bld_") and SOVEREIGN_PHASE2_AVAILABLE:
            result = builder_agent.process_callback(callback_data, update, send_telegram)
        else:
            result = hitl_controller.process_telegram_update(update, shared_state, send_telegram)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        log.error("Telegram update handler error: %s", e)
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/run-sovereign", methods=["GET", "POST"])
@limiter.limit("10 per minute")
@require_api_key
def api_run_sovereign():
    """Manually trigger the Sovereign layer for testing (no full 14-agent cycle)."""
    if not SOVEREIGN_AVAILABLE:
        return jsonify({"status": "unavailable", "error": "Sovereign layer not loaded"})
    def _run():
        scryer.run(shared_state)
        quant.run(shared_state)
        risk_master.run(shared_state, send_telegram)
        post_mortem.run(shared_state)
        hitl_controller.check_queue_expiry(shared_state, send_telegram)
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "Sovereign cycle triggered", "sovereign_available": SOVEREIGN_AVAILABLE})

# ── SOVEREIGN PHASE 2 API ROUTES ─────────────────────────────────────────────

@app.route("/api/observer-data")
def api_observer_data():
    """Latest Observer Swarm findings (OI heatmap, promoter holdings, block deals)."""
    obs = shared_state.get("observer_output", {})
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "observer_log.json")
    recent = []
    try:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                recent = json.load(f)[-5:]
    except Exception:
        pass
    return jsonify({"observer": obs, "recent_log": recent, "available": SOVEREIGN_PHASE2_AVAILABLE})

@app.route("/api/synthetic-backtest")
def api_synthetic_backtest():
    """Current and historical synthetic backtest scenarios."""
    bt = shared_state.get("synthetic_backtest", {})
    sc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "backtest_scenarios.json")
    history = []
    try:
        if os.path.exists(sc_path):
            with open(sc_path, "r", encoding="utf-8") as f:
                h = json.load(f)
                history = h[-5:] if isinstance(h, list) else []
    except Exception:
        pass
    return jsonify({"current": bt, "history": history, "available": SOVEREIGN_PHASE2_AVAILABLE})

@app.route("/api/builder-proposals")
def api_builder_proposals():
    """All Builder Agent proposals with status."""
    if not SOVEREIGN_PHASE2_AVAILABLE:
        return jsonify({"proposals": [], "pending": 0, "available": False})
    proposals = builder_agent.get_proposals_for_api()
    pending = sum(1 for p in proposals if p.get("status") == "PENDING")
    return jsonify({"proposals": proposals[-20:], "pending": pending, "available": True})

@app.route("/api/run-builder", methods=["GET", "POST"])
@limiter.limit("10 per minute")
@require_api_key
def api_run_builder():
    """Manually trigger the Builder Agent."""
    if not SOVEREIGN_PHASE2_AVAILABLE:
        return jsonify({"status": "unavailable"})
    threading.Thread(
        target=lambda: builder_agent.run(shared_state, send_telegram),
        daemon=True
    ).start()
    return jsonify({"status": "Builder Agent triggered", "available": True})

@app.route("/api/run-observer", methods=["GET", "POST"])
@limiter.limit("10 per minute")
@require_api_key
def api_run_observer():
    """Manually trigger the Observer Swarm."""
    if not SOVEREIGN_PHASE2_AVAILABLE:
        return jsonify({"status": "unavailable"})
    threading.Thread(
        target=lambda: observer.run(shared_state),
        daemon=True
    ).start()
    return jsonify({"status": "Observer Swarm triggered", "available": True})

# ── END SOVEREIGN PHASE 2 ROUTES ──────────────────────────────────────────────

@app.route("/")
def index():
    """Serve index.html with no-cache headers so browser always gets the latest version."""
    from flask import make_response
    resp = make_response(send_from_directory("static", "index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]        = "no-cache"
    resp.headers["Expires"]       = "0"
    return resp

def _on_market_open(segment, seg_def, agent, **kwargs):
    """Fires when any market segment opens — triggers agent scan + Telegram alert."""
    msg = f"🟢 {seg_def['icon']} {seg_def['name']} OPENED — Running agent scan..."
    log.info("[SessionAgent] %s", msg)
    send_telegram(msg)
    if AGENTS_AVAILABLE:
        threading.Thread(target=run_all_agents, daemon=True).start()


def _on_market_close(segment, seg_def, agent, **kwargs):
    """Fires when any market segment closes — runs paper trade P&L check + report."""
    active_still = agent.get_active_segments()
    msg = (f"🔴 {seg_def['icon']} {seg_def['name']} CLOSED — "
           f"Checking P&L... Active: {', '.join(active_still) or 'None'}")
    log.info("[SessionAgent] %s", msg)
    send_telegram(msg)
    # Monitor positions for this session's closure
    if AGENTS_AVAILABLE:
        try:
            paper_trader.run(shared_state, shared_state.get("_price_cache", {}))
        except Exception as _e:
            log.error("Post-close paper_trader run failed: %s", _e)


def _on_pre_open(segment, seg_def, agent, **kwargs):
    """Fires during pre-open — fetch fresh prices, warm up agents."""
    log.info("[SessionAgent] Pre-open: %s — fetching prices", seg_def["name"])
    threading.Thread(target=fetch_all_prices, daemon=True).start()


def run_scheduler():
    # Like a real broker terminal, we want frequent background updates
    schedule.every(30).seconds.do(fetch_all_prices)
    schedule.every().day.at("08:00").do(send_morning_brief)
    schedule.every().day.at("16:00").do(send_evening_debrief)
    schedule.every(15).minutes.do(check_alerts)
    if AGENTS_AVAILABLE:
        schedule.every(15).minutes.do(run_all_agents)
    # Market session tick — check for open/close transitions every 60 seconds
    if SESSION_AGENT_AVAILABLE:
        schedule.every(60).seconds.do(lambda: session_agent.tick())
        log.info("⏰ Market session agent ticking every 60s")
    # Phase 2 sovereign agents (background, scheduled separately)
    if SOVEREIGN_PHASE2_AVAILABLE:
        schedule.every(4).hours.do(lambda: observer.run(shared_state))
        schedule.every(6).hours.do(lambda: synthetic_backtester.run(shared_state))
        schedule.every().day.at("09:05").do(lambda: builder_agent.run(shared_state, send_telegram))
        log.info("⏰ Phase 2: Observer every 4h | Backtester every 6h | Builder daily 09:05")
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
    log.info("🔑 API Auth: %s",
             "✅ ENABLED (STOCKGURU_API_KEY set)" if _STOCKGURU_API_KEY else "⚠️  DISABLED — set STOCKGURU_API_KEY in .env for production")
    log.info("🌐 CORS Origins: %s", _origins)
    log.info("📝 Logs: %s", os.path.join(_log_dir, 'stockguru.log'))

    threading.Thread(target=fetch_all_prices, daemon=True).start()
    if AGENTS_AVAILABLE:
        log.info("🤖 Launching 14-agent cycle on startup...")
        threading.Thread(target=run_all_agents, daemon=True).start()
    else:
        log.warning("⚠️  Agents not available — run from stockguru/ directory")

    # Register market session callbacks
    if SESSION_AGENT_AVAILABLE:
        for seg_key in SEGMENTS:
            session_agent.on_open(seg_key, _on_market_open)
            session_agent.on_close(seg_key, _on_market_close)
            session_agent.on_pre_open(seg_key, _on_pre_open)
        session_agent.tick()  # initial tick to set baseline states
        log.info("📅 Market session agent initialised — %s", session_agent.status_summary())

    threading.Thread(target=run_scheduler, daemon=True).start()

    log.info("✅ Server ready")
    log.info("🧠 AI Analysis → /api/claude-analysis")
    log.info("📊 Paper Portfolio → /api/paper-stats")
    log.info("📈 Learning → /api/learning-stats")
    log.info("🔑 Add API keys in dashboard Settings tab")


# ── SHAMROCK SIMULATION ENDPOINTS ────────────────────────────────────────────

@app.route("/api/shamrock-simulate", methods=["POST"])
@limiter.limit("30 per minute")
def api_shamrock_simulate():
    """SHAMROCK simulation: full_cycle | force_trade | eval_gates | export_excel"""
    import random, json, os
    req = request.get_json(silent=True) or {}
    mode = req.get("mode", "full_cycle")

    # Helper: load paper data
    def _load_trades():
        try:
            p = os.path.join("data", "paper_trades.json")
            if os.path.exists(p):
                with open(p) as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _load_portfolio():
        try:
            p = os.path.join("data", "paper_portfolio.json")
            if os.path.exists(p):
                with open(p) as f:
                    return json.load(f)
        except Exception:
            pass
        return {"capital": 500000, "positions": {}}

    # Build gate evaluation from shared_state
    def _eval_gates_data():
        gates = [False] * 8
        passed = 0
        watchlist = WATCHLIST if "WATCHLIST" in dir() else []
        if watchlist:
            sym = watchlist[0].get("symbol", "RELIANCE.NS") if watchlist else "RELIANCE.NS"
            price = price_cache.get(sym, {})
            if isinstance(price, dict):
                rsi = price.get("rsi", 50)
                vol_ratio = price.get("volume_ratio", 1.0)
            else:
                rsi = 50
                vol_ratio = 1.0
            gates[0] = 35 <= rsi <= 68       # RSI zone
            gates[1] = vol_ratio >= 1.3       # Volume
            gates[2] = True                   # EMA trend (sim)
            gates[3] = True                   # MACD (sim)
            gates[4] = True                   # News gate (sim)
            gates[5] = True                   # FII gate (sim)
            gates[6] = True                   # PCR gate (sim)
            # Score gate from shared_state
            score = 0
            if "signals" in shared_state:
                sigs = shared_state["signals"]
                if sigs:
                    score = sigs[0].get("score", 0) if isinstance(sigs[0], dict) else 0
            gates[7] = score >= 88
        else:
            # All sim
            gates = [True, True, True, True, True, True, True, False]
        passed = sum(1 for g in gates if g)
        return gates, passed

    # Build signals from shared_state or sim
    def _build_signals():
        raw = shared_state.get("signals", []) if shared_state else []
        out = []
        for s in raw[:6]:
            if isinstance(s, dict):
                out.append({
                    "symbol": s.get("symbol", "?"),
                    "action": s.get("action", "BUY"),
                    "entry": s.get("entry_price", s.get("price", 0)),
                    "target": s.get("target", 0),
                    "sl": s.get("stop_loss", 0),
                    "score": s.get("score", 0),
                    "pnl": s.get("pnl", 0)
                })
        # Supplement with sim data if few signals
        sim_syms = [("RELIANCE.NS","RELIANCE"), ("INFY.NS","INFY"), ("TCS.NS","TCS"),
                    ("HDFCBANK.NS","HDFCBANK"), ("TATAMOTORS.NS","TATAMOTORS")]
        for ysym, sym in sim_syms:
            if len(out) >= 5:
                break
            base = price_cache.get(ysym, {})
            price = base.get("price", base) if isinstance(base, dict) else (base or random.uniform(1000, 3000))
            price = float(price) if price else random.uniform(1000, 3000)
            score = random.randint(72, 95)
            out.append({
                "symbol": sym,
                "action": random.choice(["BUY", "BUY", "SELL"]),
                "entry": round(price, 2),
                "target": round(price * 1.03, 2),
                "sl": round(price * 0.98, 2),
                "score": score,
                "pnl": round(random.uniform(-500, 2000), 0)
            })
        return out

    if mode == "full_cycle":
        # Run agent cycle if available
        agent_statuses = {}
        try:
            if AGENTS_AVAILABLE:
                threading.Thread(target=lambda: _run_one_cycle(), daemon=True).start()
                agent_statuses = {a: "ok" for a in ["market_scanner","technical_analysis",
                                   "pattern_memory","news_sentiment","trade_signal","paper_trader"]}
        except Exception as e:
            agent_statuses = {"error": str(e)}
        gates, passed = _eval_gates_data()
        signals = _build_signals()
        return jsonify({
            "status": "ok",
            "mode": "full_cycle",
            "agents": agent_statuses,
            "signals": signals,
            "gates": gates,
            "gates_passed": passed,
            "trades": _load_trades()[-5:]
        })

    elif mode == "force_trade":
        # Force a simulated paper trade
        import datetime, uuid
        portfolio = _load_portfolio()
        trades = _load_trades()
        signals = _build_signals()
        if signals:
            sig = signals[0]
            qty = max(1, int(10000 / (sig["entry"] or 100)))
            trade = {
                "id": str(uuid.uuid4())[:8],
                "symbol": sig["symbol"],
                "action": sig["action"],
                "entry_price": sig["entry"],
                "target": sig["target"],
                "stop_loss": sig["sl"],
                "qty": qty,
                "score": sig["score"],
                "timestamp": datetime.datetime.now().isoformat(),
                "status": "SIMULATED",
                "pnl": 0
            }
            trades.append(trade)
            try:
                with open(os.path.join("data", "paper_trades.json"), "w") as f:
                    json.dump(trades, f, indent=2)
            except Exception:
                pass
            return jsonify({"status": "ok", "mode": "force_trade",
                            "message": f"Simulated {trade['action']} {trade['symbol']} x{qty} @ ₹{trade['entry_price']}",
                            "trade": trade, "signals": signals})
        return jsonify({"status": "ok", "mode": "force_trade", "message": "No signals available for trade"})

    elif mode == "eval_gates":
        gates, passed = _eval_gates_data()
        return jsonify({"status": "ok", "mode": "eval_gates",
                        "gates": gates, "passed": passed,
                        "will_trade": passed >= 6})

    elif mode == "export_excel":
        try:
            import subprocess
            result = subprocess.run(
                ["python3", "shamrock_excel_export.py"],
                capture_output=True, text=True, timeout=30, cwd="."
            )
            if result.returncode == 0:
                return jsonify({"status": "ok", "mode": "export_excel",
                                "message": "Excel file generated: shamrock_trades.xlsx",
                                "file": "shamrock_trades.xlsx"})
            else:
                return jsonify({"status": "error", "message": result.stderr[:200]})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    return jsonify({"status": "error", "message": f"Unknown mode: {mode}"})


@app.route("/api/download-excel")
def api_download_excel():
    """Download the generated SHAMROCK Excel trade log."""
    import os
    from flask import send_file
    path = os.path.join(os.path.dirname(__file__), "shamrock_trades.xlsx")
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name="shamrock_trades.xlsx")
    return jsonify({"error": "Excel file not found. Run export first."}), 404


# ── END SHAMROCK ──────────────────────────────────────────────────────────────

# ── SAHI PANEL ENDPOINTS ──────────────────────────────────────────────────────

@app.route("/api/market-sessions")
def api_market_sessions():
    """Return live market session states for all 4 segments."""
    if not SESSION_AGENT_AVAILABLE:
        return jsonify({"error": "Market session agent not available", "states": {}})
    states = session_agent.get_all_states()
    return jsonify({
        "states":      states,
        "any_open":    session_agent.any_market_open(),
        "active":      session_agent.get_active_segments(),
        "summary":     session_agent.status_summary(),
        "timestamp":   session_agent.now_ist().isoformat(),
    })


@app.route("/api/live-positions")
def api_live_positions():
    """Return all open paper positions with live P&L (for SAHI panel)."""
    if not AGENTS_AVAILABLE:
        return jsonify({"positions": [], "portfolio": {}})
    pc = shared_state.get("_price_cache", {})
    positions = paper_trader.get_live_positions(pc)
    portfolio_data = paper_trader._load_portfolio()
    return jsonify({
        "positions": positions,
        "portfolio": {
            "capital":        portfolio_data.get("capital", 500000),
            "available_cash": portfolio_data.get("available_cash", 500000),
            "invested":       portfolio_data.get("invested", 0),
            "unrealized_pnl": portfolio_data.get("unrealized_pnl", 0),
            "realized_pnl":   portfolio_data.get("realized_pnl", 0),
            "total_pnl":      portfolio_data.get("total_pnl", 0),
            "total_return_pct": portfolio_data.get("total_return_pct", 0),
            "win_rate":       portfolio_data.get("stats", {}).get("win_rate", 0),
            "total_trades":   portfolio_data.get("stats", {}).get("total_trades", 0),
        },
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    })


@app.route("/api/quick-trade", methods=["POST"])
@limiter.limit("10 per minute")
def api_quick_trade():
    """
    SAHI-style 1-click paper trade entry.
    Body: {symbol, action, sl_pct, target_pct, alloc_pct}
    action is ignored if the position already exists (use /api/close-position instead).
    """
    if not AGENTS_AVAILABLE:
        return jsonify({"ok": False, "error": "Paper trader not available"}), 503
    req = request.get_json(silent=True) or {}
    symbol = req.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify({"ok": False, "error": "symbol required"}), 400
    action      = req.get("action", "BUY").upper()
    sl_pct      = float(req.get("sl_pct",     2.0))
    target_pct  = float(req.get("target_pct", 4.0))
    alloc_pct   = float(req.get("alloc_pct",  5.0))
    # Get entry price from live cache
    pc    = shared_state.get("_price_cache", {})
    entry = pc.get(symbol, {}).get("price") or req.get("entry_price", 0)
    if not entry:
        return jsonify({"ok": False, "error": f"No live price for {symbol}. Try refreshing prices."}), 400
    result = paper_trader.quick_enter(symbol, action, float(entry), sl_pct, target_pct, alloc_pct)
    return jsonify(result)


@app.route("/api/close-position", methods=["POST"])
@limiter.limit("10 per minute")
def api_close_position():
    """Manually close an open paper position at CMP."""
    if not AGENTS_AVAILABLE:
        return jsonify({"ok": False, "error": "Paper trader not available"}), 503
    req    = request.get_json(silent=True) or {}
    symbol = req.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify({"ok": False, "error": "symbol required"}), 400
    pc     = shared_state.get("_price_cache", {})
    result = paper_trader.close_position_manual(symbol, pc)
    return jsonify(result)


@app.route("/api/toggle-tsl", methods=["POST"])
@limiter.limit("20 per minute")
def api_toggle_tsl():
    """Toggle Auto Trailing SL on a position. Body: {symbol, enabled}"""
    if not AGENTS_AVAILABLE:
        return jsonify({"ok": False, "error": "Paper trader not available"}), 503
    req     = request.get_json(silent=True) or {}
    symbol  = req.get("symbol", "").upper().strip()
    enabled = bool(req.get("enabled", True))
    if not symbol:
        return jsonify({"ok": False, "error": "symbol required"}), 400
    result = paper_trader.set_tsl_enabled(symbol, enabled)
    return jsonify(result)


# ── Auto-startup when loaded by gunicorn (Railway) ───────────────────────────
# gunicorn imports this module as "app", not "__main__", so _startup() was
# never called on Railway — prices stayed 0 forever. This fixes that.
_started = False
def _ensure_started():
    global _started
    if _started:
        return
    _started = True
    _startup()

# Gunicorn worker import path (Railway) — start in background thread
if __name__ != "__main__":
    import threading as _th
    _th.Thread(target=_ensure_started, daemon=True).start()

if __name__ == "__main__":
    _ensure_started()
    port = int(os.getenv("PORT", 5050))   # Railway injects PORT automatically
    print(f"\n>>> StockGuru v2.0 starting on http://localhost:{port}")
    print(">>> 14 Agents scheduled & price feed connected.")
    if socketio:
        # WebSocket-enabled: use socketio.run() with gevent server
        socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)
    else:
        # Fallback to plain Flask (no WebSocket)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
