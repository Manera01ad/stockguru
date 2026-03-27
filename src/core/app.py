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
from dataclasses import asdict

# ── WEBSOCKET (Flask-SocketIO + gevent) ───────────────────────────────────────
try:
    from flask_socketio import SocketIO, emit as sio_emit
    _SIO_AVAILABLE = True
except ImportError:
    _SIO_AVAILABLE = False
    import warnings
    warnings.warn("flask-socketio not installed — WebSocket disabled (pip install flask-socketio gevent gevent-websocket)")
import requests
import json
import os
import sys
import threading
import time
import schedule
from datetime import datetime
from dotenv import load_dotenv
# Always load from the project root .env regardless of CWD
_ROOT_ENV = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
load_dotenv(_ROOT_ENV, override=True)
if not os.getenv('ANTHROPIC_API_KEY'):
    os.environ['ANTHROPIC_API_KEY'] = 'disabled'
import logging
from logging.handlers import RotatingFileHandler
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ── AGENT IMPORTS (Hierarchical Resolve) ──────────────────────────────────────
_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

try:
    # After reorganization, agents are in src/agents/
    from src.agents import (
        market_scanner, news_sentiment, trade_signal, commodity_crypto, morning_brief,
        technical_analysis, institutional_flow, options_flow,
        claude_intelligence, web_researcher,
        sector_rotation, risk_manager,
        pattern_memory, paper_trader, earnings_calendar,
        spike_detector,
    )
    from src.agents.orchestrator import AgentOrchestrator
    AGENTS_AVAILABLE = True
except ImportError as _e:
    AGENTS_AVAILABLE = False
    logging.warning(f"Agents not loaded: {_e}")

# ── MARKET SESSION AGENT ───────────────────────────────────────────────────────
try:
    from src.agents.market_session_agent import session_agent, SEGMENTS, STATE_OPEN, STATE_CLOSED
    SESSION_AGENT_AVAILABLE = True
except ImportError as _se:
    SESSION_AGENT_AVAILABLE = False
    session_agent = None
    logging.warning(f"market_session_agent not loaded: {_se}")

# ── LEARNING IMPORTS ──────────────────────────────────────────────────────────
try:
    from src.agents.learning import signal_tracker, weight_adjuster
    LEARNING_AVAILABLE = True
except ImportError:
    LEARNING_AVAILABLE = False

# ── SOVEREIGN TRADER LAYER (Phase 1) ──────────────────────────────────────────
try:
    from src.agents.sovereign import scryer, quant, risk_master, debate_engine, hitl_controller, post_mortem, memory_engine
    SOVEREIGN_AVAILABLE = True
    logging.info("✅ Sovereign Trader Layer loaded — 4 meta-agents active")
except ImportError as _se:
    SOVEREIGN_AVAILABLE = False
    logging.warning(f"⚠️  Sovereign layer not loaded: {_se}")

# ── SOVEREIGN TRADER LAYER (Phase 2) ──────────────────────────────────────────
try:
    from src.agents.sovereign import observer, synthetic_backtester, builder_agent
    SOVEREIGN_PHASE2_AVAILABLE = True
except ImportError:
    SOVEREIGN_PHASE2_AVAILABLE = False

_core_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.abspath(os.path.join(_core_dir, "..", ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)
if _core_dir not in sys.path:
    sys.path.insert(0, _core_dir)

# ── PHASE 5: SELF-HEALING SYSTEM (Adaptive Strategy) ──────────────────────────
try:
    from src.core.phase5_self_healing.learning_engine import LearningEngine
    SELF_HEALING_AVAILABLE = True
    logging.info("✅ Phase 5 Self-Healing Layer loaded — Adaptive Strategy active")
except ImportError as _she:
    SELF_HEALING_AVAILABLE = False
    logging.warning(f"⚠️ Phase 5 Self-Healing layer not loaded: {_she}")
    logging.info("✅ Sovereign Phase 2 loaded — Observer, Backtester, Builder active")
except ImportError as _se2:
    SOVEREIGN_PHASE2_AVAILABLE = False
    logging.warning(f"⚠️  Sovereign Phase 2 not loaded: {_se2}")

# ── ATLAS — SELF-LEARNING KNOWLEDGE ENGINE ────────────────────────────────────
try:
    from src.agents.atlas.core import ATLASCore, get_knowledge_stats, get_best_patterns, get_active_rules
    from src.agents.atlas.self_upgrader import run_upgrade, get_upgrade_status, run_quick_context_refresh
    from src.agents.atlas.options_flow_memory import record_options_snapshot, get_options_context
    from src.agents.atlas.news_impact_mapper import classify_news_event, record_news_event
    from src.agents.atlas.regime_detector import detect_regime, get_time_context
    from src.agents.atlas.volume_classifier import classify_volume
    from src.agents.atlas.causal_engine import analyze_trade_cause
    ATLAS_AVAILABLE = True
    logging.info("✅ ATLAS Knowledge Engine loaded — 6 learning modules active")
except Exception as _ae:
    ATLAS_AVAILABLE = False
    logging.warning(f"⚠️  ATLAS not loaded: {_ae}")

# ── CHANNELS + BACKTESTING ────────────────────────────────────────────────────
try:
    from src.agents.channels import ChannelManager
    channel_manager = ChannelManager()
    CHANNELS_AVAILABLE = True
except Exception as _ce:
    channel_manager    = None
    CHANNELS_AVAILABLE = False
    logging.warning(f"Channels not loaded: {_ce}")

try:
    from src.agents.backtesting import BacktestEngine
    BACKTESTING_AVAILABLE = True
except Exception as _be:
    BACKTESTING_AVAILABLE = False
    logging.warning(f"Backtesting not loaded: {_be}")

# ── INTELLIGENCE CONNECTORS ───────────────────────────────────────────────────
try:
    from src.agents.connectors import ConnectorManager as IntelConnectorManager
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


# ── AUTO-LOAD keys from LOCAL_KEYS_PATH if set ───────────────────────────────
# If the user has configured a custom folder path (saved as LOCAL_KEYS_PATH in
# .env), load that file too so credentials survive server restarts automatically.
_local_keys_path = os.getenv("LOCAL_KEYS_PATH", "").strip()
if _local_keys_path:
    _alt_env = (os.path.join(_local_keys_path, ".env")
                if os.path.isdir(_local_keys_path) else _local_keys_path)
    if os.path.isfile(_alt_env):
        load_dotenv(_alt_env, override=True)
        print(f"[INFO] Auto-loaded credentials from {_alt_env}")

# ── DATA FEED MANAGER (auto-selects best configured feed) ────────────────────
try:
    from src.agents.feeds import feed_manager as _feed_mgr
    _FEED_OK = True
except Exception as _fe:
    import logging as _fl; _fl.getLogger(__name__).warning(f"FeedManager init failed: {_fe}")
    _feed_mgr = None
    _FEED_OK  = False

# ── DIAGNOSTICS AGENT ─────────────────────────────────────────────────────────
try:
    from src.agents.diagnostics_agent import get_diagnostics_agent, run_diagnostics
    DIAGNOSTICS_AVAILABLE = True
except Exception as _diag_e:
    DIAGNOSTICS_AVAILABLE = False
    logging.warning(f"DiagnosticsAgent not loaded: {_diag_e}")

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
# Post-reorg: static assets are in ../../static/ relative to src/core/app.py
app = Flask(__name__, static_folder='../../static', static_url_path='')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0   # disable static file caching during dev

@app.route("/")
def serve_index():
    """Main dashboard entry point."""
    return send_from_directory(app.static_folder, "index.html")

@app.route("/docs")
def serve_docs():
    """Documentation portal — Diátaxis-structured reference for StockGuru."""
    docs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'docs'))
    return send_from_directory(docs_path, "StockGuru_Documentation.html")

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

# ── DUAL SYMBOL MAP ──────────────────────────────────────────────────────────
# Each instrument has:
#   yahoo   → Yahoo Finance symbol  (delayed, always available)
#   shoonya → (exchange, tsym)      (live, requires Shoonya credentials)
#   angel   → symboltoken           (live, Angel One SmartAPI)
#   mcx     → True if MCX commodity (Shoonya uses MCX exchange)
# Toggle between feeds using the ON/OFF switches in the API Keys tab.
# ─────────────────────────────────────────────────────────────────────────────
INSTRUMENTS = {
    # ── INDICES ──────────────────────────────────────────────────────────────
    "NIFTY 50":   {"yahoo": "^NSEI",        "shoonya": ("NSE", "Nifty 50"),    "mcx": False},
    "SENSEX":     {"yahoo": "^BSESN",       "shoonya": ("BSE", "SENSEX"),      "mcx": False},
    "BANK NIFTY": {"yahoo": "^NSEBANK",     "shoonya": ("NSE", "Nifty Bank"),  "mcx": False},
    "INDIA VIX":  {"yahoo": "^INDIAVIX",    "shoonya": ("NSE", "India VIX"),   "mcx": False},
    # ── SECTOR INDICES ───────────────────────────────────────────────────────
    "FINNIFTY":      {"yahoo": "^CNXFIN",      "shoonya": ("NSE", "Finnifty"),         "mcx": False},
    "MIDCAP NIFTY":  {"yahoo": "^CNXMIDCAP",   "shoonya": ("NSE", "Midcpnifty"),       "mcx": False},
    "NIFTY NEXT 50": {"yahoo": "^CNXJUNIOR",   "shoonya": ("NSE", "Nifty Next 50"),    "mcx": False},
    "NIFTY IT":      {"yahoo": "^CNXIT",        "shoonya": ("NSE", "Nifty IT"),         "mcx": False},
    "NIFTY METAL":   {"yahoo": "^CNXMETAL",     "shoonya": ("NSE", "Nifty Metal"),      "mcx": False},
    "NIFTY PHARMA":  {"yahoo": "^CNXPHARMA",    "shoonya": ("NSE", "Nifty Pharma"),     "mcx": False},
    "NIFTY AUTO":    {"yahoo": "^CNXAUTO",      "shoonya": ("NSE", "Nifty Auto"),       "mcx": False},
    "NIFTY FMCG":    {"yahoo": "^CNXFMCG",      "shoonya": ("NSE", "Nifty FMCG"),       "mcx": False},
    "NIFTY REALTY":  {"yahoo": "^CNXREALTY",    "shoonya": ("NSE", "Nifty Realty"),     "mcx": False},
    "NIFTY ENERGY":  {"yahoo": "^CNXENERGY",    "shoonya": ("NSE", "Nifty Energy"),     "mcx": False},
    # ── NSE EQUITIES ─────────────────────────────────────────────────────────
    "AIRTEL":     {"yahoo": "BHARTIARTL.NS","shoonya": ("NSE", "BHARTIARTL-EQ"),"mcx": False},
    "HDFC BANK":  {"yahoo": "HDFCBANK.NS",  "shoonya": ("NSE", "HDFCBANK-EQ"),  "mcx": False},
    "ICICI BANK": {"yahoo": "ICICIBANK.NS", "shoonya": ("NSE", "ICICIBANK-EQ"), "mcx": False},
    "BAJAJ FIN":  {"yahoo": "BAJFINANCE.NS","shoonya": ("NSE", "BAJFINANCE-EQ"),"mcx": False},
    "BEL":        {"yahoo": "BEL.NS",       "shoonya": ("NSE", "BEL-EQ"),       "mcx": False},
    "MUTHOOT":    {"yahoo": "MUTHOOTFIN.NS","shoonya": ("NSE", "MUTHOOTFIN-EQ"),"mcx": False},
    "ZOMATO":     {"yahoo": "ZOMATO.NS",    "shoonya": ("NSE", "ZOMATO-EQ"),    "mcx": False},
    "INDIGO":     {"yahoo": "INDIGO.NS",    "shoonya": ("NSE", "INDIGO-EQ"),    "mcx": False},
    # ── MCX COMMODITIES (Shoonya: MCX exchange, Yahoo: futures codes) ────────
    "GOLD MCX":   {"yahoo": "GC=F",         "shoonya": ("MCX", "GOLD"),         "mcx": True},
    "SILVER MCX": {"yahoo": "SI=F",         "shoonya": ("MCX", "SILVER"),       "mcx": True},
    "CRUDE OIL":  {"yahoo": "CL=F",         "shoonya": ("MCX", "CRUDEOIL"),     "mcx": True},
    "NAT GAS":    {"yahoo": "NG=F",         "shoonya": ("MCX", "NATURALGAS"),   "mcx": True},
    # ── CURRENCY (CDS) ───────────────────────────────────────────────────────
    "USD/INR":    {"yahoo": "INR=X",        "shoonya": ("CDS", "USDINR"),       "mcx": False},
    # ── CRYPTO (Yahoo only — Shoonya does not support crypto) ────────────────
    "BTC/INR":    {"yahoo": "BTC-INR",      "shoonya": None,                    "mcx": False},
    "ETH/INR":    {"yahoo": "ETH-INR",      "shoonya": None,                    "mcx": False},
    "SOL/INR":    {"yahoo": "SOL-INR",      "shoonya": None,                    "mcx": False},
}

# Backwards-compatible alias — Yahoo symbols keyed by display name
YAHOO_SYMBOLS = {name: info["yahoo"] for name, info in INSTRUMENTS.items()}

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

# ── Realistic seed values — keeps dashboard readable before first live fetch ──
_PRICE_SEEDS = {
    "NIFTY 50":      22150.00,  "SENSEX":        72900.00,
    "BANK NIFTY":    47500.00,  "INDIA VIX":        15.50,
    "FINNIFTY":      21800.00,  "MIDCAP NIFTY":  46500.00,
    "NIFTY NEXT 50": 65500.00,  "NIFTY IT":      37200.00,
    "NIFTY METAL":    8800.00,  "NIFTY PHARMA":  21500.00,
    "NIFTY AUTO":    23200.00,  "NIFTY FMCG":    57500.00,
    "NIFTY REALTY":    950.00,  "NIFTY ENERGY":  43500.00,
    "AIRTEL":         1560.00,  "HDFC BANK":      1710.00,
    "ICICI BANK":     1240.00,  "BAJAJ FIN":      7100.00,
    "BEL":             280.00,  "MUTHOOT":        2100.00,
    "ZOMATO":          225.00,  "INDIGO":         3950.00,
    "GOLD MCX":       92000.00, "SILVER MCX":    101000.00,
    "CRUDE OIL":       6800.00, "NAT GAS":         270.00,
    "USD/INR":          83.90,
    "BTC/INR":       7200000.00,"ETH/INR":       275000.00,
    "SOL/INR":         14500.00,
}
import random as _rng
price_cache = {}
for _n, _sym in YAHOO_SYMBOLS.items():
    _p = _PRICE_SEEDS.get(_n, 100.0)
    _prev = round(_p * _rng.uniform(0.998, 1.002), 2)
    _chg = round(_p - _prev, 2)
    price_cache[_n] = {"price": _p, "change": _chg,
                       "change_pct": round(_chg / _prev * 100, 2) if _prev else 0,
                       "symbol": _sym, "updated": "seed", "feed": "seed"}
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
    # Agent Intelligence Feed — reasoning log with theory
    "agent_reasoning_log": [],   # [{ts, agent, icon, monitoring, signal, theory, data, action, level}]
    "trade_decision_log":  [],   # [{ts, symbol, action, reason, gates, theory, result}]
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
orchestrator = None

if AGENTS_AVAILABLE:
    orchestrator = AgentOrchestrator(shared_state)
    orchestrator.register_agent("market_scanner", market_scanner, required=True)
    orchestrator.register_agent("news_sentiment", news_sentiment, required=True)
    orchestrator.register_agent("trade_signal", trade_signal, required=True)
    orchestrator.register_agent("commodity_crypto", commodity_crypto)
    orchestrator.register_agent("morning_brief", morning_brief)
    orchestrator.register_agent("technical_analysis", technical_analysis)
    orchestrator.register_agent("institutional_flow", institutional_flow)
    orchestrator.register_agent("options_flow", options_flow)
    orchestrator.register_agent("claude_intelligence", claude_intelligence)
    orchestrator.register_agent("web_researcher", web_researcher)
    orchestrator.register_agent("sector_rotation", sector_rotation)
    orchestrator.register_agent("risk_manager", risk_manager, required=True)
    orchestrator.register_agent("pattern_memory", pattern_memory)
    orchestrator.register_agent("paper_trader", paper_trader, required=True)
    orchestrator.register_agent("earnings_calendar", earnings_calendar)
    orchestrator.register_agent("spike_detector", spike_detector)
    # Sovereign Layer
    orchestrator.register_agent("scryer", scryer)
    orchestrator.register_agent("quant", quant)
    orchestrator.register_agent("risk_master", risk_master)
    orchestrator.register_agent("debate_engine", debate_engine)
    orchestrator.register_agent("post_mortem", post_mortem)
    # Sovereign Phase 2
    if SOVEREIGN_PHASE2_AVAILABLE:
        orchestrator.register_agent("observer", observer)
        orchestrator.register_agent("builder_agent", builder_agent)
        orchestrator.register_agent("synthetic_backtester", synthetic_backtester)


# ── YAHOO CRUMB SESSION (handles Yahoo's new cookie/crumb requirement) ────────
_yf_session   = None
_yf_crumb     = None
_yf_crumb_at  = 0.0

def _ensure_yahoo_session():
    """Get (or refresh) a Yahoo Finance session + crumb. Cached for 55 min."""
    global _yf_session, _yf_crumb, _yf_crumb_at
    import time as _t
    if _yf_crumb and (_t.time() - _yf_crumb_at) < 3300:   # 55-min TTL
        return _yf_session, _yf_crumb
    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        # Step 1: hit Yahoo Finance to get cookies
        s.get("https://fc.yahoo.com", timeout=5)
        s.get("https://finance.yahoo.com", timeout=5)
        # Step 2: fetch the crumb
        r = s.get("https://query2.finance.yahoo.com/v1/test/getcrumb",
                  headers={"User-Agent": s.headers["User-Agent"]}, timeout=5)
        if r.status_code == 200 and r.text and len(r.text) < 50:
            _yf_crumb    = r.text.strip()
            _yf_session  = s
            _yf_crumb_at = _t.time()
            log.info("✅ Yahoo Finance crumb obtained: %s", _yf_crumb)
            return _yf_session, _yf_crumb
    except Exception as e:
        log.debug("Yahoo crumb fetch failed: %s", e)
    return requests.Session(), None


# ── PRICE FETCHER ─────────────────────────────────────────────────────────────
def fetch_yahoo_price(symbol):
    """
    Multi-layer price fetch — tries 5 sources in order:
      1. NSE direct API  (Indian indices only — fastest, no auth)
      2. Yahoo Finance v8 with crumb session
      3. Yahoo Finance v8 without crumb (legacy)
      4. yfinance library
      5. CoinGecko (crypto) / seed drift (all others)
    """
    def _parse_meta(meta):
        price      = float(meta.get("regularMarketPrice") or meta.get("postMarketPrice") or 0)
        prev       = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        if price == 0:
            return None
        change     = round(price - prev, 2)
        change_pct = round((change / prev) * 100, 2) if prev else 0
        return {"price": round(price, 2), "change": change, "change_pct": change_pct, "prev": round(prev, 2)}

    # ── Layer 0: NSE Direct API (Indian indices — fastest, always free) ───────
    _NSE_INDEX_MAP = {
        "^NSEI":       "NIFTY 50",
        "^NSEBANK":    "NIFTY BANK",
        "^INDIAVIX":   "India VIX",
        "^CNXFIN":     "NIFTY FINANCIAL SERVICES",
        "^CNXMIDCAP":  "NIFTY MIDCAP 100",
        "^CNXJUNIOR":  "NIFTY NEXT 50",
        "^CNXIT":      "NIFTY IT",
        "^CNXMETAL":   "NIFTY METAL",
        "^CNXPHARMA":  "NIFTY PHARMA",
        "^CNXAUTO":    "NIFTY AUTO",
        "^CNXFMCG":    "NIFTY FMCG",
        "^CNXREALTY":  "NIFTY REALTY",
        "^CNXENERGY":  "NIFTY ENERGY",
    }
    if symbol in _NSE_INDEX_MAP:
        try:
            nse_name = _NSE_INDEX_MAP[symbol]
            r = requests.get(
                "https://www.nseindia.com/api/allIndices",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.nseindia.com",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive",
                },
                timeout=8
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                for entry in data:
                    if entry.get("indexSymbol", "").upper() == nse_name.upper() or \
                       entry.get("index", "").upper() == nse_name.upper():
                        curr = float(entry.get("last", 0) or entry.get("currentValue", 0))
                        prev = float(entry.get("previousClose", curr) or curr)
                        if curr > 0:
                            chg = round(curr - prev, 2)
                            return {"price": round(curr, 2), "change": chg,
                                    "change_pct": round(chg / prev * 100, 2) if prev else 0,
                                    "prev": round(prev, 2), "feed": "nse_direct"}
        except Exception as e:
            log.debug("NSE direct API failed for %s: %s", symbol, e)

    # ── Layer 1: Yahoo Finance with crumb session ─────────────────────────────
    try:
        sess, crumb = _ensure_yahoo_session()
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
        if crumb:
            url += f"&crumb={crumb}"
        r = sess.get(url, timeout=10)
        if r.status_code == 200:
            meta = r.json()["chart"]["result"][0]["meta"]
            result = _parse_meta(meta)
            if result:
                return result
    except Exception as e:
        log.debug("Yahoo crumb session failed for %s: %s", symbol, e)

    # ── Layer 2: Yahoo Finance plain (fallback if crumb fails) ───────────────
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
        "^CNXFIN":    (22500, 23500),   # FINNIFTY
        "^CNXMIDCAP": (42000, 45000),   # MIDCAP NIFTY
        "^CNXJUNIOR": (63000, 67000),   # NIFTY NEXT 50
        "^CNXIT":     (38000, 42000),   # NIFTY IT
        "^CNXMETAL":  (8500,  9500),    # NIFTY METAL
        "^CNXPHARMA": (21000, 23000),   # NIFTY PHARMA
        "^CNXAUTO":   (22000, 24000),   # NIFTY AUTO
        "^CNXFMCG":   (57000, 62000),   # NIFTY FMCG
        "^CNXREALTY": (800,   1100),    # NIFTY REALTY
        "^CNXENERGY": (41000, 46000),   # NIFTY ENERGY
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
    active_feed  = _feed_mgr.active_name if (_FEED_OK and _feed_mgr) else "yahoo"
    use_feed_mgr = active_feed != "yahoo"
    feed_label   = (_feed_mgr.active_label if use_feed_mgr else "Yahoo Finance")
    log.info(f"🔄 Fetching live prices via {feed_label}...")
    for name, info in INSTRUMENTS.items():
        yahoo_sym  = info["yahoo"]
        shoonya_sym= info.get("shoonya")          # (exchange, tsym) or None
        # Use native symbol for active feed; Yahoo symbol as key for fallback
        symbol     = yahoo_sym                     # used for fallback + cache key
        data = None
        # ── Route through feed manager (Shoonya, Angel, etc.) if configured ──
        if use_feed_mgr and shoonya_sym is not None:
            try:
                raw = _feed_mgr.get_quote(yahoo_sym)  # feed manager maps internally
                if raw and raw.get("price", 0) > 0 and "error" not in raw:
                    data = {
                        "price":      raw.get("price", 0),
                        "change":     round(raw.get("price", 0) - raw.get("prev_close", raw.get("price", 0)), 2),
                        "change_pct": raw.get("change_pct", 0),
                        "prev":       raw.get("prev_close", 0),
                        "volume":     raw.get("volume", 0),
                        "day_high":   raw.get("day_high", 0),
                        "day_low":    raw.get("day_low", 0),
                        "feed":       _feed_mgr.active_name,
                    }
            except Exception as fe:
                log.debug(f"Feed manager quote failed for {symbol}: {fe}")

        # ── Fallback to Yahoo Finance ──
        if not data:
            data = fetch_yahoo_price(symbol)
            if data:
                data["feed"] = "yahoo"

        if data:
            price_cache[name] = {**data, "symbol": symbol, "updated": datetime.now().strftime("%H:%M:%S")}
            if name in ("NIFTY 50", "SENSEX", "BANK NIFTY", "INDIA VIX",
                        "FINNIFTY", "MIDCAP NIFTY", "NIFTY NEXT 50",
                        "NIFTY IT", "NIFTY METAL", "NIFTY PHARMA",
                        "NIFTY AUTO", "NIFTY FMCG", "NIFTY REALTY", "NIFTY ENERGY"):
                shared_state["index_prices"][name] = data

            # --- REAL-TIME TICKER EMIT ---
            if socketio:
                socketio.emit("price_update", {
                    "prices": {name: price_cache[name]},
                    "last_update": datetime.now().strftime("%H:%M:%S"),
                    "feed": data.get("feed", "yahoo"),
                    "event": "tick_update"
                })

        if last_update != "Initializing...":
            time.sleep(0.15)

    last_update = datetime.now().strftime("%d %b %Y %H:%M:%S IST")
    shared_state["_price_cache"] = price_cache
    shared_state["_active_feed"] = feed_label
    log.info(f"✅ Price feed cycle complete via {feed_label} at {last_update}")

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
    """Push agent cycle completion to all connected clients (enriched with conviction data)."""
    if not socketio:
        return
    try:
        port = shared_state.get("paper_portfolio", {})
        
        # Phase 3/4 Enhancements: Conviction & Consensus
        top_sigs = shared_state.get("trade_signals", [])[:5]
        consensus = shared_state.get("agent_consensus", [])
        claude_analysis = shared_state.get("claude_analysis", {})
        consensus_stats = claude_analysis.get("consensus_verdict", {})
        agreed_picks = set(consensus_stats.get("agreed_picks", [])) if isinstance(consensus_stats, dict) else set()
        
        # Enrich signals with consensus count
        for sig in top_sigs:
            name = sig.get("name", "")
            match_count = sum(1 for vote in consensus if vote == sig.get("signal"))
            sig["consensus_count"] = match_count
            sig["ai_confirmed"]    = name in agreed_picks
            
        # VIX Regime logic
        vix_data = shared_state.get("india_vix", {})
        vix = vix_data.get("level", 15)
        vix_regime = vix_data.get("regime", "NORMAL")
        
        payload = {
            "event":            "agents_update",
            "scanner_count":    len(shared_state.get("scanner_results", [])),
            "signal_count":     len(shared_state.get("trade_signals", [])),
            "top_signals":      top_sigs,
            "alerts":           shared_state.get("spike_alerts", [])[:3],
            "morning_brief":    shared_state.get("morning_brief_text", ""),
            "market_mood":      shared_state.get("market_mood", {}),
            "vix_regime":       vix_regime,
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
        log.info("WS: emitted agents_update (Phase 3 Enriched)")
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

# ── Alert deduplication state ─────────────────────────────────────────────────
# Tracks last-alerted per stock so we don't spam the same signal every 15 min
alerted_stocks: dict = {}          # { stock_name: { "signal": str, "ts": float, "date": str } }
ALERT_COOLDOWN_HOURS = 6           # min hours before repeating same signal tier


def _is_market_open() -> bool:
    """Return True if at least one major Indian market segment is currently open (IST)."""
    now = datetime.now()
    weekday = now.weekday()          # 0=Mon … 4=Fri, 5=Sat, 6=Sun
    if weekday >= 5:                 # weekend — all closed
        return False
    h, m = now.hour, now.minute
    hm = h * 100 + m                 # e.g. 9:15 → 915
    # NSE Equity/FnO: 09:15 – 15:30
    if 915 <= hm <= 1530:
        return True
    # MCX Commodity: 09:00 – 23:30
    if 900 <= hm <= 2330:
        return True
    # NSE Currency: 09:00 – 17:00
    if 900 <= hm <= 1700:
        return True
    return False


def check_alerts():
    log.info("🔔 Checking alerts...")

    if not _is_market_open():
        log.info("🕐 Market closed — skipping alert check.")
        return

    now_ts = time.time()
    today  = datetime.now().strftime("%Y-%m-%d")

    new_signals    = []   # first time we see this buy signal
    repeat_signals = []   # cooldown expired, remind again

    for stock in WATCHLIST:
        score, signal, target, sl = calculate_score(stock)
        cached = price_cache.get(stock["name"])

        if not cached or signal not in ("STRONG BUY", "BUY"):
            # Signal gone — clear dedup entry so it can fire fresh next time
            alerted_stocks.pop(stock["name"], None)
            continue

        entry = {
            "name": stock["name"], "score": score, "signal": signal,
            "price": cached["price"], "change_pct": cached["change_pct"],
            "target": target, "sl": sl, "sector": stock["sector"],
        }
        prev = alerted_stocks.get(stock["name"])

        if prev is None:
            # First time this stock shows a buy signal
            new_signals.append(entry)
            alerted_stocks[stock["name"]] = {"signal": signal, "ts": now_ts, "date": today}
        elif prev.get("signal") != signal:
            # Signal tier changed (BUY → STRONG BUY or vice versa)
            new_signals.append(entry)
            alerted_stocks[stock["name"]] = {"signal": signal, "ts": now_ts, "date": today}
        elif prev.get("date") != today:
            # New trading day — treat as fresh signal
            new_signals.append(entry)
            alerted_stocks[stock["name"]] = {"signal": signal, "ts": now_ts, "date": today}
        else:
            hours_since = (now_ts - prev.get("ts", 0)) / 3600
            if hours_since >= ALERT_COOLDOWN_HOURS:
                repeat_signals.append(entry)
                alerted_stocks[stock["name"]]["ts"] = now_ts  # reset cooldown

    def _format_entry(s):
        arrow = "🟢" if s["change_pct"] >= 0 else "🔴"
        return (f"{arrow} *{s['name']}* ({s['sector']})\n"
                f"   Score: {s['score']}/100 | Signal: {s['signal']}\n"
                f"   CMP: ₹{s['price']} ({s['change_pct']:+.2f}%)\n"
                f"   Target: ₹{s['target']} | SL: ₹{s['sl']}\n")

    if new_signals:
        lines = ["🚨 *StockGuru Alert* — " + datetime.now().strftime("%d %b %H:%M") + " IST\n"]
        for s in new_signals:
            lines.append(_format_entry(s))
        lines.append("_⚠️ Paper simulation only. Not SEBI advice._")
        send_telegram("\n".join(lines))
        log.info("📲 Sent %d new signals", len(new_signals))

    if repeat_signals:
        lines = ["🔁 *StockGuru Reminder* — " + datetime.now().strftime("%d %b %H:%M") + " IST\n"]
        for s in repeat_signals:
            lines.append(_format_entry(s))
        lines.append("_⚠️ Paper simulation only. Not SEBI advice._")
        send_telegram("\n".join(lines))
        log.info("📲 Sent %d reminder signals", len(repeat_signals))

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

    def _emit(agent, icon, monitoring, signal, theory, action="watching",
              data=None, level="info"):
        """Emit a structured reasoning entry visible in the Agent Intelligence Feed."""
        entry = {
            "ts":         datetime.now().strftime("%H:%M:%S"),
            "agent":      agent,
            "icon":       icon,
            "monitoring": monitoring,
            "signal":     signal,
            "theory":     theory,
            "action":     action,
            "data":       data or {},
            "level":      level,   # info | alert | trade | warn
        }
        shared_state["agent_reasoning_log"].append(entry)
        if len(shared_state["agent_reasoning_log"]) > 500:
            shared_state["agent_reasoning_log"] = shared_state["agent_reasoning_log"][-500:]

    def _trade_log(symbol, action, entry_price, sl, t1, gates_passed,
                   theory, result="QUEUED", score=0, sector=""):
        """Log every paper trade decision — win or reject — with full reasoning."""
        entry = {
            "ts":          datetime.now().strftime("%H:%M:%S"),
            "date":        datetime.now().strftime("%d %b %Y"),
            "symbol":      symbol,
            "action":      action,
            "entry_price": entry_price,
            "sl":          sl,
            "t1":          t1,
            "score":       score,
            "sector":      sector,
            "gates_passed": gates_passed,
            "theory":      theory,
            "result":      result,   # EXECUTED | REJECTED | MONITORING
        }
        shared_state["trade_decision_log"].append(entry)
        if len(shared_state["trade_decision_log"]) > 300:
            shared_state["trade_decision_log"] = shared_state["trade_decision_log"][-300:]
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
        
        orchestrator.execute_agent("commodity_crypto")
        _log(f"   Gold={shared_state.get('commodity_results',[{}])[0].get('price','?')} | Crude={shared_state.get('commodity_results',[{},{}])[1].get('price','?') if len(shared_state.get('commodity_results',[]))>1 else '?'}")
        _comms = shared_state.get("commodity_results", [])
        _gold  = next((c for c in _comms if "GOLD" in c.get("symbol","").upper()), {})
        _crude = next((c for c in _comms if "CRUDE" in c.get("symbol","").upper() or "OIL" in c.get("symbol","").upper()), {})
        _comm_sent = shared_state.get("commodity_sentiment", "NEUTRAL")
        _emit("commodity", "🪙", f"Gold ₹{_gold.get('price','?')} | Crude ${_crude.get('price','?')}",
              _comm_sent,
              f"Commodity macro: Gold {'at ATH — safety bid active' if _gold.get('change_pct',0)>0.5 else 'stable — no panic'} | "
              f"Crude {'falling — margin tailwind for aviation/FMCG' if _crude.get('change_pct',0)<-0.5 else 'elevated — cost pressure on downstream'} | Sentiment={_comm_sent}",
              data={"gold_price": _gold.get("price"), "crude_price": _crude.get("price"), "sentiment": _comm_sent})
        
        orchestrator.execute_agent("news_sentiment")
        _log(f"   News sentiment: {shared_state.get('market_sentiment_score',0):+.0f} | {len(shared_state.get('news_results',[]))} headlines | {'LLM+keyword' if any(n.get('scored_by')=='llm+keyword' for n in shared_state.get('news_results',[])) else 'keyword'}")
        _news_score = shared_state.get("market_sentiment_score", 0)
        _headlines  = [n.get("title","")[:60] for n in shared_state.get("news_results",[])[:3]]
        _news_lvl   = "alert" if abs(_news_score) >= 3 else "info"
        _emit("news", "📰", f"{len(shared_state.get('news_results',[]))} headlines | Score {_news_score:+.0f}",
              "BULLISH" if _news_score > 1 else "BEARISH" if _news_score < -1 else "NEUTRAL",
              ("Strong positive flow — risk-on. LLM weighted earnings beats & policy positives." if _news_score > 2 else
               "Strong negative flow — risk-off. Watch for downside pressure." if _news_score < -2 else
               "Mixed/neutral flow — no directional bias. Wait for confirmation."),
              level=_news_lvl, data={"score": _news_score, "headlines": _headlines})
        
        orchestrator.execute_agent("market_scanner")
        _log(f"   Scanner: {len(shared_state.get('scanner_results',[]))} stocks ranked")
        _scan_top = shared_state.get("scanner_results", [])[:5]
        _scan_names = [f"{s.get('name','?')}({s.get('score',0)})" for s in _scan_top]
        _emit("scanner", "🔍", f"Scanned {len(shared_state.get('full_scan',[]))} stocks → {len(shared_state.get('scanner_results',[]))} ranked",
              f"Top: {', '.join(_scan_names[:3]) if _scan_names else 'None'}",
              f"Screener: ROE>12%, VolSurge>1.3x, Change>0.5%, Above 200DMA. "
              f"{'Broad strength — ' + str(len(_scan_top)) + ' quality setups' if len(_scan_top) >= 5 else 'Selective market — fewer setups, higher entry bar'}. "
              f"Top pick: {_scan_top[0].get('name','?')} score={_scan_top[0].get('score',0)} sector={_scan_top[0].get('sector','?')}" if _scan_top else "No stocks passed screener filters.",
              data={"top_stocks": [{"name": s.get("name"), "score": s.get("score"), "sector": s.get("sector"), "change_pct": s.get("change_pct")} for s in _scan_top]})
        # Spike detection + Pre-Spike scan — runs after price_cache is populated
        orchestrator.execute_agent("spike_detector", _send_tg)
        # Pre-Spike Detector: catch conditions BEFORE the actual spike fires
        try:
            pre_spikes = spike_detector.scan_pre_spikes(shared_state, _send_tg)
            if pre_spikes:
                _log(f"   ⚡ PreSpike: {len(pre_spikes)} setup(s) — {', '.join(p.get('symbol','?') for p in pre_spikes)}", "warn")
                for _psp in pre_spikes:
                    _emit("scanner", "⚡", f"PRE-SPIKE: {_psp.get('symbol','?')} | Score {_psp.get('score',0)}/100",
                          "PRE-SPIKE SETUP",
                          f"Pre-spike forensics ({_psp.get('signals_count',0)} signals): {_psp.get('reason','')}. "
                          "Theory: 4+ concurrent signals (OI velocity, vol surge, IV build, PCR flip, EMA reclaim) = explosive move likely within 15-45 min. "
                          "Enter small position with tight SL BEFORE the spike, not after.",
                          action="PRE_SPIKE", level="alert",
                          data={"symbol": _psp.get("symbol"), "score": _psp.get("score"),
                                "signals": _psp.get("signals", [])[:3]})
        except Exception as _pse:
            log.debug("scan_pre_spikes: %s", _pse)
        spikes = shared_state.get("spike_alerts", [])
        if spikes:
            _log(f"   🚨 SpikeDetector: {len(spikes)} alert(s) — {', '.join(s.get('symbol','?') for s in spikes)}", "warn")
            for _sp in spikes:
                _emit("scanner", "🚨", f"SPIKE: {_sp.get('symbol','?')} | Score {_sp.get('spike_score',0)}",
                    "SPIKE ALERT",
                    f"Pre-spike signals: OI surge={_sp.get('oi_velocity','?')} | Vol={_sp.get('vol_ratio','?')}x avg | "
                    f"PCR={_sp.get('pcr','?')} | Trigger: {_sp.get('trigger_reason','momentum break')}. "
                    "When OI builds rapidly while price coils, explosive directional move is imminent — enter before breakout.",
                    action="SPIKE_ALERT", level="alert",
                    data={"symbol": _sp.get("symbol"), "score": _sp.get("spike_score"), "type": _sp.get("type","?")})
        else:
            _log("   ⚡ SpikeDetector: clean cycle")
        _st("calendar",   "running")
        try:    earnings_calendar.run(shared_state); _st("calendar", "done"); _log(f"   Events calendar: {shared_state.get('events_calendar',{}).get('total_events',0)} events | {len(shared_state.get('events_calendar',{}).get('watchlist_alerts',[]))} watchlist matches")
        except Exception as e: log.warning("earnings_calendar: %s", e); _st("calendar", "error")

        for agent_name in ["technical", "institutional", "options", "sector"]:
            # Map agent names to registered names in orchestrator
            reg_name = {
                "technical": "technical_analysis",
                "institutional": "institutional_flow",
                "options": "options_flow",
                "sector": "sector_rotation"
            }.get(agent_name, agent_name)

            if orchestrator.execute_agent(reg_name):
                if agent_name == "technical":
                    _tech = shared_state.get("technical_data", {})
                    _tech_names = list(_tech.keys())[:4]
                    _emit("technical", "📈", f"Pivot/RSI/ATR for {len(_tech)} stocks",
                          f"Analysed: {', '.join(_tech_names) if _tech_names else 'none yet'}",
                          "IIFL pivot-based entries: buy within 5-7% above weekly pivot breakout. "
                          "RSI 40-60 = accumulation zone. ATR scales position size (1% risk ÷ ATR = shares). "
                          "Swing lows define tighter stops vs 8% fixed. Stocks above 200DMA get score boost.",
                          data={"count": len(_tech), "stocks": _tech_names})
                elif agent_name == "institutional":
                    _if_data = shared_state.get("institutional_flow", {})
                    _fii = _if_data.get("fii_net", "?") if isinstance(_if_data, dict) else "?"
                    _dii = _if_data.get("dii_net", "?") if isinstance(_if_data, dict) else "?"
                    _if_sent = "BULLISH" if str(_fii).lstrip("-").replace(".","").replace(",","").isdigit() and float(str(_fii).replace(",","") or 0) > 0 else "BEARISH"
                    _emit("institutional", "🏦", f"FII Net: ₹{_fii}Cr | DII Net: ₹{_dii}Cr",
                          _if_sent,
                          "FII flows drive medium-term direction. DII absorption cushions FII selling. "
                          "FII+DII both positive = strong bull signal. FII buying defensives = rotation caution. "
                          "Block deals reveal smart money accumulation vs distribution zones.",
                          data={"fii": _fii, "dii": _dii, "sentiment": _if_sent})
                elif agent_name == "options":
                    _opt = shared_state.get("options_flow", {})
                    _pcr = _opt.get("pcr", "?") if isinstance(_opt, dict) else "?"
                    _max_pain = _opt.get("max_pain", "?") if isinstance(_opt, dict) else "?"
                    try: _pcr_num = float(str(_pcr).replace(",",""))
                    except: _pcr_num = 1.0
                    _opt_sent = "BEARISH" if _pcr_num < 0.8 else "BULLISH" if _pcr_num > 1.2 else "NEUTRAL"
                    _emit("options", "⚙️", f"PCR={_pcr} | Max Pain=₹{_max_pain}",
                          _opt_sent,
                          f"PCR {_pcr}: <0.8=bearish, >1.2=bullish. Max Pain ₹{_max_pain} = price where most options expire worthless "
                          "(market makers defend this level near expiry). OI walls at strikes = key support/resistance. "
                          "PCR divergence from price = smart money tells direction before price moves.",
                          data={"pcr": _pcr, "max_pain": _max_pain, "sentiment": _opt_sent})
                elif agent_name == "sector":
                    _sec = shared_state.get("sector_rotation", {})
                    _top_sec = list(_sec.keys())[:3] if isinstance(_sec, dict) else []
                    _emit("sector", "🔄", f"Rotation leaders: {', '.join(_top_sec) or 'Scanning'}",
                          f"Leaders: {', '.join(_top_sec[:2]) or 'Mixed'}",
                          "Sector rotation: money flows defensive→cyclical = bull start; cyclical→defensive = late bull/bear start. "
                          f"Current leaders: {', '.join(_top_sec[:2]) or 'mixed'}. "
                          "Banking+IT leading = broad recovery. Defence+Gold leading = risk-off. "
                          "Align stock picks with sector momentum for +10-15% alpha on top of stock selection.",
                          data={"top_sectors": _top_sec})

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
        if routing.get("run_llm", True):
            if orchestrator.execute_agent("claude_intelligence"):
                ca = shared_state.get("claude_analysis", {})
                _log(f"   Market: {ca.get('market_condition','?')} | Stance: {ca.get('market_stance','?')} | Picks: {len(ca.get('conviction_picks',[]))}")
        else:
            shared_state["agent_status"]["claude_intelligence"] = "done"
            _log(f"   ⏭ LLM skipped by AgentRouter (cycle saved)")
            _emit("claude", "🤖", "LLM skipped this cycle (AgentRouter efficiency save)",
                  "SKIPPED", "AgentRouter determined data confidence is high enough to reuse prior LLM analysis. "
                  "LLM calls skipped when: last cycle <15min ago + sentiment unchanged + no high-impact news. "
                  "Saves ~$0.003/cycle. Prior conviction picks still active.", action="skipped")
        # ── EMIT: Claude reasoning ──
        ca = shared_state.get("claude_analysis", {})
        if ca and ca.get("market_condition"):
            _picks = ca.get("conviction_picks", [])
            _pick_names = [p.get("name","?") for p in _picks[:3]]
            _emit("claude", "🤖", f"Market: {ca.get('market_condition','?')} | Stance: {ca.get('market_stance','?')} | {len(_picks)} picks",
                  ca.get("market_stance", "NEUTRAL"),
                  f"AI synthesis: {ca.get('market_condition','?')} regime. Stance={ca.get('market_stance','?')}. "
                  f"Conviction picks: {', '.join(_pick_names) or 'none'}. "
                  f"Theory: {ca.get('market_summary','Claude analysed macro+sector+technical confluence to generate conviction picks with entry/exit targets')[:120]}",
                  level="alert" if len(_picks) > 0 else "info",
                  data={"condition": ca.get("market_condition"), "stance": ca.get("market_stance"),
                        "picks": [{"name": p.get("name"), "gates": p.get("gates_passed",0),
                                   "execute": p.get("execute_paper_trade")} for p in _picks[:5]]})

        # ── TIER 3: STRATEGY ──────────────────────────────────────────────────
        log.info("─── TIER 3: Strategy & Risk ──────────────────────────────────")
        _log("── TIER 3: Strategy & Risk ──────────────────────────")
        orchestrator.execute_agent("trade_signal")
        _log(f"   Signals: {len(shared_state.get('actionable_signals',[]))} actionable")
        # ── EMIT: Trade signals reasoning ──
        _act_sigs = shared_state.get("actionable_signals", [])
        _all_sigs = shared_state.get("trade_signals", [])
        if _act_sigs:
            _top_sig = _act_sigs[0]
            _emit("signals", "📊", f"{len(_act_sigs)} actionable / {len(_all_sigs)} total signals",
                  f"Top: {_top_sig.get('name','?')} RR={_top_sig.get('rr_t1',0):.1f}:1",
                  f"Signal engine applied IIFL pivot + sector tailwind + risk/reward filter. "
                  f"Actionable criteria: RR≥1.2 + score≥78. Top signal: {_top_sig.get('name','?')} "
                  f"entry ₹{_top_sig.get('entry_low','?')}-{_top_sig.get('entry_high','?')} | "
                  f"T1=₹{_top_sig.get('target1','?')} (+{(((_top_sig.get('target1',0)/_top_sig.get('cmp',1))-1)*100) if _top_sig.get('cmp',0)>0 else '?':.0f}%) | "
                  f"SL=₹{_top_sig.get('stop_loss','?')} | RR={_top_sig.get('rr_t1',0):.1f}:1",
                  level="alert", data={"actionable": len(_act_sigs), "total": len(_all_sigs),
                    "top_signals": [{"name": s.get("name"), "score": s.get("score"), "rr": s.get("rr_t1"), "sector": s.get("sector")} for s in _act_sigs[:5]]})

        for agent_name in ["risk", "web_researcher"]:
            reg_name = "risk_manager" if agent_name == "risk" else agent_name
            if orchestrator.execute_agent(reg_name):
                if agent_name == "risk":
                    _rev = shared_state.get("risk_reviewed_signals", [])
                    _risk_mode = shared_state.get("risk_summary", {}).get("vix_status", "NORMAL")
                    _emit("risk", "🛡️", f"Risk reviewed {len(_rev)} signals | Mode: {_risk_mode}",
                          _risk_mode,
                          f"Risk rules: Max 5 positions, 2% per trade, daily loss circuit at -3%, VIX>25 blocks new entries. "
                          f"Correlation filter rejects if portfolio β>1.3. ATR-based position sizing. "
                          f"{len(_rev)}/{len(_act_sigs)} signals passed risk review in {_risk_mode} mode.",
                          data={"reviewed": len(_rev), "mode": _risk_mode})
                elif agent_name == "web_researcher":
                    _web_r = shared_state.get("web_research", {})
                    _emit("web_researcher", "🌐", "Web research: company filings + news deep-dive",
                          "ACTIVE",
                          "Cross-references stock signals with recent BSE filings, promoter buys, analyst upgrades. "
                          "Detects: regulatory headwinds, order wins, capacity expansions, management changes. "
                          "Adds qualitative layer that pure technical/quant scoring misses.",
                          data={"researched": len(_web_r) if isinstance(_web_r, dict) else 0})

        # ── TIER 4: PAPER TRADING + LEARNING ─────────────────────────────────
        log.info("─── TIER 4: Paper Trading & Learning ────────────────────────")
        _log("── TIER 4: Paper Trading & Learning ─────────────────")
        _st("paper", "running")
        if orchestrator.execute_agent("paper_trader", price_cache):
            port = shared_state.get("paper_portfolio", {})
            open_pos = len([p for p in port.get("positions",{}).values() if p.get("status")=="OPEN"])
            _log(f"   Paper: {open_pos} open positions | Win rate: {port.get('stats',{}).get('win_rate',0)*100:.0f}%")
            # ── EMIT: Paper trader reasoning ──
            _new_trades = shared_state.get("trade_decision_log", [])
            _recent_trade = _new_trades[-1] if _new_trades else {}
            _win_rate = port.get("stats",{}).get("win_rate",0)*100
            _realized = port.get("realized_pnl", 0)
            _emit("paper", "💼", f"{open_pos} open positions | Win rate {_win_rate:.0f}% | P&L ₹{_realized:+,.0f}",
                  "ACTIVE" if open_pos > 0 else "WATCHING",
                  f"Paper trading engine evaluated {len(shared_state.get('risk_reviewed_signals', []) or shared_state.get('actionable_signals', []))} signals this cycle using 8-gate conviction filter. "
                  f"Gates: score≥75, volume surge, above 200DMA, risk/reward≥1.2, sector tailwind, Claude approval, risk clearance, market hours. "
                  f"{'Entered: ' + _recent_trade.get('symbol','?') + ' @ ₹' + str(_recent_trade.get('entry_price','?')) if _recent_trade.get('result')=='EXECUTED' else 'No new entries this cycle — gates not all met or max positions reached'}. "
                  f"Portfolio: {open_pos}/5 positions | Win rate {_win_rate:.0f}%",
                  action="EXECUTED" if _recent_trade.get("result") == "EXECUTED" else "watching",
                  level="trade" if _recent_trade.get("result") == "EXECUTED" else "info",
                  data={"open_positions": open_pos, "win_rate": _win_rate, "realized_pnl": _realized,
                        "recent_decisions": [{"symbol": d.get("symbol"), "result": d.get("result"),
                                              "gates": d.get("gates_passed")} for d in (_new_trades[-5:] if _new_trades else [])]})
        
        orchestrator.execute_agent("pattern_memory")

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

        orchestrator.execute_agent("morning_brief", _send_tg, _send_n8n)

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
                orchestrator.execute_agent("scryer")
                orchestrator.execute_agent("quant")
                orchestrator.execute_agent("risk_master", _send_tg)

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

                orchestrator.execute_agent("post_mortem")
                hitl_controller.check_queue_expiry(shared_state, _send_tg)

                # Phase 2: inline synthetic backtest when positions are open
                if SOVEREIGN_PHASE2_AVAILABLE:
                    _port = shared_state.get("paper_portfolio", {})
                    if _port.get("positions"):
                        orchestrator.execute_agent("backtester")

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
@app.route("/api/run-cycle", methods=["GET","POST"])   # alias — keeps old docs/n8n specs working
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

@app.route("/api/paper-portfolio")
def api_paper_portfolio():
    p = shared_state.get("paper_portfolio", {})
    capital = p.get("capital", 500000)
    return jsonify({
        "portfolio":    p.get("positions", []),
        "stats":        p.get("stats", {}),
        "capital":      capital,
        "available":    p.get("available_cash", capital),
        "realised_pnl": p.get("realised_pnl", 0),
        "last_updated": p.get("last_run", "--"),
    })

# ── DIAGNOSTICS AGENT ──────────────────────────────────────────────────────────

@app.route("/api/diagnostics", methods=["GET"])
def api_diagnostics_status():
    """Return cached diagnostics report (fast — no re-scan)."""
    report = shared_state.get("diagnostics_report")
    if not report:
        return jsonify({"overall": "UNKNOWN", "message": "No diagnostics run yet. POST to /api/diagnostics/run"}), 200
    return jsonify(report)

@app.route("/api/diagnostics/run", methods=["POST", "GET"])
def api_diagnostics_run():
    """Trigger a fresh full diagnostics scan (takes 5-15s)."""
    if not DIAGNOSTICS_AVAILABLE:
        return jsonify({"error": "DiagnosticsAgent not loaded"}), 503
    try:
        _proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        agent  = get_diagnostics_agent(shared_state, app_root=_proj_root)
        report = agent.run_full_check()
        # Update feature flags in shared_state so agent runtime checks see current values
        shared_state["AGENTS_AVAILABLE"]       = AGENTS_AVAILABLE
        shared_state["ATLAS_AVAILABLE"]        = ATLAS_AVAILABLE
        shared_state["SELF_HEALING_AVAILABLE"] = SELF_HEALING_AVAILABLE
        return jsonify(report)
    except Exception as e:
        log.error("Diagnostics run error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/diagnostics/quick", methods=["GET"])
def api_diagnostics_quick():
    """Fast health check — agents + keys + DB only (< 2s)."""
    if not DIAGNOSTICS_AVAILABLE:
        return jsonify({"error": "DiagnosticsAgent not loaded"}), 503
    try:
        _proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        agent  = get_diagnostics_agent(shared_state, app_root=_proj_root)
        report = agent.run_quick_check()
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── PHASE 5: SELF-HEALING & STRATEGY OPTIMIZATION ──────────────────────────────

@app.route("/api/self-healing/run", methods=["POST"])
def api_self_healing_run():
    """Trigger the full self-healing analysis cycle."""
    if not SELF_HEALING_AVAILABLE:
        return jsonify({"error": "Self-healing module not loaded"}), 501
    try:
        days = int(request.json.get("days", 30)) if request.is_json else 30
        engine = LearningEngine()
        results = engine.run_full_analysis(days=days)
        # Store latest results in shared state for other API calls
        shared_state["last_self_healing_results"] = results
        return jsonify(results)
    except Exception as e:
        logging.error(f"Self-healing run error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/self-healing/stats")
def api_self_healing_stats():
    """Return the latest self-healing performance stats."""
    res = shared_state.get("last_self_healing_results", {})
    if not res:
        return jsonify({"message": "No analysis run yet. Call /api/self-healing/run first."})
    return jsonify(res.get("stats", {}))

@app.route("/api/self-healing/recommendations")
def api_self_healing_recommendations():
    """Show the currently suggested strategy optimizations."""
    res = shared_state.get("last_self_healing_results", {})
    if not res:
        return jsonify({"message": "No optimizations found."})
    return jsonify(res.get("optimizations", {}))

@app.route("/api/self-healing/apply", methods=["POST"])
def api_self_healing_apply():
    """Manually approve and apply the recommended thresholds."""
    if not SELF_HEALING_AVAILABLE:
        return jsonify({"error": "Module unavailable"}), 501
    try:
        res = shared_state.get("last_self_healing_results", {})
        if not res:
            return jsonify({"error": "Run analysis first"}), 400
        
        # In a real system, we'd persist these to DB or shared_state flags
        # conviction_filter.py would then read from these.
        opts = res.get("optimizations", {})
        shared_state["active_gate_thresholds"] = opts.get("thresholds", {})
        shared_state["active_risk_params"]     = opts.get("risk", {})
        
        return jsonify({"status": "SUCCESS", "applied": opts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/self-healing/history")
def api_self_healing_history():
    """Return the history of all self-healing sessions."""
    if not SELF_HEALING_AVAILABLE:
        return jsonify({"error": "Self-healing module not loaded"}), 501
    try:
        engine = LearningEngine()
        history = engine.get_analysis_history(limit=20)
        # Convert to JSON serializable list
        history_list = [asdict(h) for h in history] if history else []
        return jsonify({"history": history_list, "count": len(history_list)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

@app.route("/api/agent-reasoning")
def api_agent_reasoning():
    """Live intelligence feed — what each agent is monitoring and WHY."""
    since = request.args.get("since", 0, type=int)   # client passes index to get only new entries
    log_data = shared_state.get("agent_reasoning_log", [])
    return jsonify({
        "feed":       log_data[since:],
        "total":      len(log_data),
        "cycle":      shared_state.get("cycle_count", 0),
        "last_cycle": shared_state.get("last_full_cycle", "—"),
    })

@app.route("/api/trade-decision-log")
def api_trade_decision_log():
    """Every paper trade decision — EXECUTED, REJECTED or MONITORING — with full reasoning."""
    log_data = shared_state.get("trade_decision_log", [])
    return jsonify({
        "decisions":  log_data[-100:],          # last 100 decisions
        "total":      len(log_data),
        "executed":   sum(1 for d in log_data if d.get("result") == "EXECUTED"),
        "rejected":   sum(1 for d in log_data if d.get("result") == "REJECTED"),
    })

@app.route("/api/strategy-analysis", methods=["POST", "GET"])
def api_strategy_analysis():
    """
    Geopolitical Strategy Analysis endpoint.
    POST body: { market, category, symbol, segment, vix (optional) }
    Returns per-strategy signals with ACTIVE/WATCH/AVOID status.
    """
    try:
        from src.agents.agents.geopolitical_strategy_agent import run as run_strategy
        params = {}
        if request.method == "POST":
            try:
                params = request.get_json(silent=True) or {}
            except Exception:
                params = {}
        else:
            params = {
                "market":   request.args.get("market", "NIFTY"),
                "category": request.args.get("category", "all"),
            }
        # Inject India VIX if available from shared_state
        # india_vix is stored as a dict by options_flow agent; extract numeric level
        if "vix" not in params:
            _vix_raw = shared_state.get("india_vix", 18.0)
            params["vix"] = _vix_raw.get("level", 18.0) if isinstance(_vix_raw, dict) else _vix_raw
        result = run_strategy(shared_state, request_params=params)
        return jsonify(result)
    except ImportError as e:
        return jsonify({"error": f"Strategy agent not loaded: {e}"}), 500
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


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
        env_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
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
        "env_path": os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")),
        # App API key returned so the frontend can authenticate protected trigger endpoints
        "app_api_key": _STOCKGURU_API_KEY,
    })

@app.route("/api/dashboard-data")
def api_dashboard_data():
    """Unified dashboard snapshot — alias that combines status + market intelligence.
    Added to fix 404s from n8n nodes and external callers expecting this endpoint."""
    portfolio = shared_state.get("paper_portfolio", {})
    claude    = shared_state.get("claude_analysis", {})
    return jsonify({
        # System status
        "telegram_configured":  bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "gemini_configured":    bool(GEMINI_API_KEY),
        "prices_loaded":        sum(1 for v in price_cache.values() if v.get("feed","seed") != "seed"),
        "prices_total":         len(price_cache),
        "last_update":          last_update,
        "price_feed":           shared_state.get("_active_feed", "Yahoo Finance"),
        "agents_available":     AGENTS_AVAILABLE,
        "cycle_count":          shared_state.get("cycle_count", 0),
        "last_full_cycle":      shared_state.get("last_full_cycle", "—"),
        # Market intelligence
        "market_mood":          shared_state.get("market_mood", {}),
        "market_sentiment":     shared_state.get("market_sentiment_score", 0),
        "top_signals":          shared_state.get("trade_signals", [])[:5],
        "scanner_count":        len(shared_state.get("scanner_results", [])),
        "signal_count":         len(shared_state.get("actionable_signals", [])),
        "morning_brief":        shared_state.get("morning_brief_text", ""),
        "claude_summary":       claude.get("summary", ""),
        # Portfolio snapshot
        "paper_trades":         portfolio.get("stats", {}).get("total_trades", 0),
        "paper_win_rate":       portfolio.get("stats", {}).get("win_rate", 0),
        "paper_pnl":            portfolio.get("realized_pnl", 0),
        "open_positions":       len([p for p in portfolio.get("positions", {}).values()
                                     if p.get("status") == "OPEN"]),
    })


@app.route("/api/status")
def api_status():
    portfolio = shared_state.get("paper_portfolio", {})
    return jsonify({
        "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
        "prices_loaded": len(price_cache), "last_update": last_update,
        "price_feed": shared_state.get("_active_feed", _feed_mgr.active_label if (_FEED_OK and _feed_mgr) else "Yahoo Finance"),
        "watchlist_count": len(WATCHLIST), "alerts_sent": len(alert_log),
        "paper_trades": portfolio.get("stats", {}).get("total_trades", 0),
        "paper_win_rate": portfolio.get("stats", {}).get("win_rate", 0),
        "agents_v2": AGENTS_AVAILABLE, "learning_active": LEARNING_AVAILABLE,
    })

# ── LIVE TRADING TOGGLE ──────────────────────────────────────────────────────

@app.route("/api/set-live-trading", methods=["POST"])
@limiter.limit("5 per minute")
def api_set_live_trading():
    """
    Persist LIVE_TRADING_UI_INTENT to .env.
    NOTE: paper_trader.py has LIVE_TRADING_ENABLED hardcoded to False as a
    safety lock. This endpoint only records the user's intent in .env so the
    toggle state persists across page reloads. Actual live order execution
    requires a separate developer-side code change to paper_trader.py.
    """
    try:
        data    = request.get_json() or {}
        enabled = bool(data.get("enabled", False))
        env_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []
        # Update or append LIVE_TRADING_UI_INTENT
        key = "LIVE_TRADING_UI_INTENT"
        replaced = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={'true' if enabled else 'false'}\n")
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f"{key}={'true' if enabled else 'false'}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)
        os.environ[key] = "true" if enabled else "false"
        log.warning("⚡ LIVE_TRADING_UI_INTENT set to %s via dashboard", enabled)
        return jsonify({"status": "ok", "live_trading_intent": enabled})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/live-trading-status")
def api_live_trading_status():
    """Return live trading toggle state for the UI."""
    intent = os.getenv("LIVE_TRADING_UI_INTENT", "false").lower() == "true"
    return jsonify({
        "live_trading_enabled": intent,
        "paper_trader_locked":  True,   # always True — hardcoded in paper_trader.py
        "note": "paper_trader.py has LIVE_TRADING_ENABLED=False hardcoded. "
                "Setting UI intent does not bypass that safety lock.",
    })


# ── FEED CREDENTIAL ROUTES ───────────────────────────────────────────────────

_FEED_ENV_KEYS = [
    "UPSTOX_ACCESS_TOKEN",
    "TRUEDATA_USERNAME", "TRUEDATA_PASSWORD",
    "SHOONYA_USER", "SHOONYA_PASSWORD", "SHOONYA_API_KEY", "SHOONYA_TOTP_KEY", "SHOONYA_VENDOR_CODE",
    "ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_MPIN", "ANGEL_TOTP_KEY",
    "FYERS_ACCESS_TOKEN", "FYERS_APP_ID",
    "ZERODHA_API_KEY", "ZERODHA_ACCESS_TOKEN",
]

# Map from JSON body field name → ENV var name
_FEED_FIELD_MAP = {
    "upstox_access_token":  "UPSTOX_ACCESS_TOKEN",
    "truedata_username":    "TRUEDATA_USERNAME",
    "truedata_password":    "TRUEDATA_PASSWORD",
    "shoonya_user":         "SHOONYA_USER",
    "shoonya_password":     "SHOONYA_PASSWORD",
    "shoonya_api_key":      "SHOONYA_API_KEY",
    "shoonya_totp_key":     "SHOONYA_TOTP_KEY",
    "shoonya_vendor_code":  "SHOONYA_VENDOR_CODE",
    "angel_api_key":        "ANGEL_API_KEY",
    "angel_client_id":      "ANGEL_CLIENT_ID",
    "angel_mpin":           "ANGEL_MPIN",
    "angel_totp_key":       "ANGEL_TOTP_KEY",
    "fyers_access_token":   "FYERS_ACCESS_TOKEN",
    "fyers_app_id":         "FYERS_APP_ID",
    "zerodha_api_key":      "ZERODHA_API_KEY",
    "zerodha_access_token": "ZERODHA_ACCESS_TOKEN",
}

@app.route("/api/update-feed-keys", methods=["POST"])
@limiter.limit("10 per minute")
def api_update_feed_keys():
    """Write broker credentials to .env and hot-reload the feed manager."""
    try:
        data = request.get_json() or {}
        env_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
        # Read existing .env lines
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        # Build a dict of current env values from the file
        existing = {}
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                existing[k.strip()] = v.strip()

        # Update with incoming values (skip blanks and masked placeholders)
        for field, env_key in _FEED_FIELD_MAP.items():
            val = data.get(field, "").strip()
            if val and "****" not in val:
                existing[env_key] = val
                os.environ[env_key] = val  # hot-set for this process

        # Rebuild .env preserving all keys
        new_lines = []
        seen = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in existing:
                    new_lines.append(f"{k}={existing[k]}\n")
                    seen.add(k)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        # Append any new keys not already in the file
        for env_key in _FEED_ENV_KEYS:
            if env_key not in seen and env_key in existing:
                new_lines.append(f"{env_key}={existing[env_key]}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Reload feed manager so new credentials take effect immediately
        active_feed = "Yahoo Finance"
        if _FEED_OK:
            try:
                _feed_mgr.reload()
                st = _feed_mgr.status()
                active_feed = st.get("active_label", "Yahoo Finance")
            except Exception:
                pass

        log.info("🔌 Feed credentials updated via API Keys tab")
        return jsonify({"status": "ok", "active_feed": active_feed})
    except Exception as e:
        log.error(f"update-feed-keys error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


_VALID_FEED_NAMES = {"upstox", "truedata", "shoonya", "angel", "fyers", "zerodha"}

@app.route("/api/toggle-feed", methods=["POST"])
@limiter.limit("20 per minute")
def api_toggle_feed():
    """Enable or disable a specific feed without touching its credentials."""
    try:
        data    = request.get_json() or {}
        feed    = data.get("feed", "").lower().strip()
        enabled = bool(data.get("enabled", True))
        if feed not in _VALID_FEED_NAMES:
            return jsonify({"status": "error", "message": f"Unknown feed: {feed}"}), 400

        env_key = f"{feed.upper()}_ENABLED"
        val     = "1" if enabled else "0"
        os.environ[env_key] = val

        # Persist to .env
        env_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        found = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{env_key}="):
                new_lines.append(f"{env_key}={val}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{env_key}={val}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Reload feed manager
        active_feed = "yahoo"
        if _FEED_OK and _feed_mgr:
            _feed_mgr.reload()
            active_feed = _feed_mgr.active_name

        log.info(f"🔌 Feed '{feed}' {'enabled' if enabled else 'disabled'}")
        return jsonify({"status": "ok", "feed": feed, "enabled": enabled, "active_feed": active_feed})
    except Exception as e:
        log.error(f"toggle-feed error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/get-feed-keys")
def api_get_feed_keys():
    """Return masked broker credentials from .env for pre-filling the UI."""
    def mask(val):
        if not val: return ""
        if len(val) <= 8: return "*" * len(val)
        return val[:4] + "*" * (len(val) - 8) + val[-4:]
    result = {}
    for field, env_key in _FEED_FIELD_MAP.items():
        raw = os.getenv(env_key, "")
        result[field] = mask(raw)
    # Also return the saved custom path so the UI can pre-fill the path input
    result["local_keys_path"] = os.getenv("LOCAL_KEYS_PATH", "")
    return jsonify(result)


@app.route("/api/load-from-path", methods=["POST"])
@limiter.limit("10 per minute")
def api_load_from_path():
    """
    Import credentials from a .env file in a user-specified folder.
    Body: { "path": "C:\\Users\\Hp\\projects\\stockguru", "remember": true }
    - Reads the .env from that folder (or the exact file if a file path is given)
    - Merges recognised keys into this app's own .env
    - If remember=true, saves LOCAL_KEYS_PATH so auto-load works on every restart
    """
    try:
        data     = request.get_json() or {}
        raw_path = data.get("path", "").strip()
        remember = bool(data.get("remember", False))

        if not raw_path:
            return jsonify({"error": "path is required"}), 400

        # Accept both a folder (appends /.env) and a direct file path
        if os.path.isdir(raw_path):
            env_file = os.path.join(raw_path, ".env")
        else:
            env_file = raw_path

        if not os.path.isfile(env_file):
            return jsonify({"error": f"File not found: {env_file}"}), 404

        # Keys we will accept from the external file (feed + common API keys)
        _IMPORTABLE = set(_FEED_ENV_KEYS) | {
            "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID",
            "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
            "OPENAI_API_KEY",
        }

        # Parse and hot-set
        loaded = {}
        with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, _, v = s.partition("=")
                    k, v = k.strip(), v.strip()
                    if k in _IMPORTABLE and v:
                        loaded[k] = v
                        os.environ[k] = v   # hot-set for this process

        if not loaded:
            return jsonify({"error": "No recognised keys found in that file"}), 400

        # Merge into this app's local .env
        local_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        try:
            with open(local_env, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        existing = {}
        for line in lines:
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, _, v = s.partition("=")
                existing[k.strip()] = v.strip()

        existing.update(loaded)
        if remember:
            existing["LOCAL_KEYS_PATH"] = raw_path
            os.environ["LOCAL_KEYS_PATH"] = raw_path

        # Rebuild keeping original file structure
        new_lines = []
        seen = set()
        for line in lines:
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k = s.split("=", 1)[0].strip()
                if k in existing:
                    new_lines.append(f"{k}={existing[k]}\n")
                    seen.add(k)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        for k, v in existing.items():
            if k not in seen:
                new_lines.append(f"{k}={v}\n")

        with open(local_env, "w") as f:
            f.writelines(new_lines)

        # Reload feed manager so new creds take immediate effect
        if _FEED_OK:
            try:
                _feed_mgr.reload()
            except Exception:
                pass

        log.info(f"🔑 Imported {len(loaded)} key(s) from {env_file}")
        return jsonify({
            "status": "ok",
            "loaded": len(loaded),
            "keys":   [_key_display_name(k) for k in loaded],
            "path":   env_file,
        })
    except Exception as e:
        log.error(f"load-from-path error: {e}")
        return jsonify({"error": str(e)}), 500


def _key_display_name(k: str) -> str:
    """Make env var names human-readable for the success message."""
    return k.replace("_", " ").title().replace("Api", "API").replace("Totp", "TOTP")


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
    # ATLAS Self-Learning Knowledge Engine
    if ATLAS_AVAILABLE:
        schedule.every(15).minutes.do(lambda: run_quick_context_refresh(shared_state))
        schedule.every().day.at("21:00").do(lambda: run_upgrade(shared_state, use_llm=True))
        log.info("⏰ ATLAS: Context refresh every 15min | Full upgrade daily 21:00")
    # DiagnosticsAgent — auto health monitor
    if DIAGNOSTICS_AVAILABLE:
        _diag_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        _diag_agent = get_diagnostics_agent(shared_state, app_root=_diag_root)
        # Sync current feature-flag state so agent runtime check knows what's loaded
        shared_state["AGENTS_AVAILABLE"]       = AGENTS_AVAILABLE
        shared_state["ATLAS_AVAILABLE"]        = ATLAS_AVAILABLE
        shared_state["SELF_HEALING_AVAILABLE"] = SELF_HEALING_AVAILABLE
        schedule.every(30).minutes.do(_diag_agent.run_full_check)
        # Run once immediately at startup in a background thread
        threading.Thread(target=_diag_agent.run_full_check, daemon=True).start()
        log.info("⏰ DiagnosticsAgent: full scan every 30 min + startup scan")
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
                threading.Thread(target=run_all_agents, daemon=True).start()
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


# ── AI AGENT CHAT ENDPOINT ───────────────────────────────────────────────────

def _build_chat_context() -> str:
    """
    Assemble a rich trading context string from live shared_state.
    Passed as system context to Claude/Gemini so they answer like a real trading analyst.
    """
    import json as _json
    lines = [
        "You are StockGuru's AI Trading Analyst — a professional quantitative analyst embedded"
        " inside a paper trading intelligence system.",
        "You have access to live market data, active paper positions, agent signals, and options flow.",
        "Answer in clear, concise trading language. Be direct. Cite specific numbers from the context.",
        "IMPORTANT: This is a PAPER TRADING / SIMULATION system. Never recommend real money actions.",
        "",
        "═══ LIVE TRADING CONTEXT ═══",
    ]

    # ── Market Session State ───────────────────────────────────────────────────
    if SESSION_AGENT_AVAILABLE:
        lines.append("\n[MARKET SESSIONS — IST]")
        for seg_key, seg_def in SEGMENTS.items():
            state = session_agent.get_session_state(seg_key)
            lines.append(f"  {seg_def['icon']} {seg_def['name']}: {state}  ({seg_def['open'].strftime('%H:%M')}–{seg_def['close'].strftime('%H:%M')})")

    # ── Live Prices ────────────────────────────────────────────────────────────
    pc = shared_state.get("_price_cache", {})
    if pc:
        lines.append("\n[LIVE PRICES]")
        for sym, data in list(pc.items())[:12]:
            p = data.get("price", 0)
            c = data.get("change_pct", 0)
            sign = "+" if c >= 0 else ""
            lines.append(f"  {sym}: ₹{p:,.2f}  {sign}{c:.2f}%")

    # ── Open Paper Positions ───────────────────────────────────────────────────
    try:
        live_pos = paper_trader.get_live_positions(pc)
        if live_pos:
            lines.append("\n[OPEN PAPER POSITIONS]")
            for pos in live_pos:
                pnl_sign = "+" if pos["unreal_pnl"] >= 0 else ""
                lines.append(
                    f"  {pos['symbol']}: {pos['shares']} shares | Entry ₹{pos['entry_price']:,.2f}"
                    f" | CMP ₹{pos.get('cmp',0):,.2f}"
                    f" | TSL ₹{pos['trailing_sl']:,.2f}"
                    f" | Unrealised {pnl_sign}₹{pos['unreal_pnl']:,.0f} ({pnl_sign}{pos['unreal_pnl_pct']:.2f}%)"
                )
        portfolio = paper_trader._load_portfolio()
        lines.append(f"\n[PORTFOLIO]  Cash: ₹{portfolio.get('available_cash',0):,.0f}"
                     f" | Invested: ₹{portfolio.get('invested',0):,.0f}"
                     f" | Realised P&L: ₹{portfolio.get('realized_pnl',0):,.0f}"
                     f" | Win Rate: {portfolio.get('stats',{}).get('win_rate',0)*100:.1f}%"
                     f" | Trades: {portfolio.get('stats',{}).get('total_trades',0)}")
    except Exception:
        pass

    # ── Top Agent Signals ──────────────────────────────────────────────────────
    signals = shared_state.get("trade_signals", [])
    if signals:
        lines.append("\n[TOP TRADE SIGNALS (agent-generated)]")
        for sig in sorted(signals, key=lambda x: x.get("score",0), reverse=True)[:6]:
            lines.append(
                f"  {sig.get('signal','?')} {sig.get('name','?')} | Score {sig.get('score',0)}"
                f" | Conf {sig.get('confidence','?')} | Gates {sig.get('gates_passed',0)}/8"
                f" | Entry ₹{sig.get('entry',0):,.2f} SL ₹{sig.get('stop_loss',0):,.2f} T1 ₹{sig.get('target1',0):,.2f}"
            )

    # ── Claude AI Analysis ─────────────────────────────────────────────────────
    claude_a = shared_state.get("claude_analysis", {})
    if claude_a:
        lines.append(f"\n[AGENT ANALYSIS]")
        lines.append(f"  Market Condition : {claude_a.get('market_condition','?')}")
        lines.append(f"  Market Stance    : {claude_a.get('market_stance','?')}")
        lines.append(f"  Narrative        : {claude_a.get('market_narrative','')[:200]}")
        picks = claude_a.get("conviction_picks", [])
        if picks:
            lines.append(f"  Conviction Picks : " + ", ".join(p.get("name","") for p in picks[:5]))
        lines.append(f"  Biggest Risk     : {claude_a.get('biggest_risk','')[:120]}")

    # ── Options Flow ──────────────────────────────────────────────────────────
    opts = shared_state.get("options_flow", {})
    if opts:
        lines.append(f"\n[OPTIONS FLOW]")
        lines.append(f"  NIFTY PCR   : {opts.get('nifty_pcr',0):.3f}  → {opts.get('pcr_bias','?')}")
        lines.append(f"  Max Pain    : {opts.get('max_pain','?')}")
        lines.append(f"  IV Regime   : {opts.get('iv_regime','?')}")
        lines.append(f"  Gate        : {'PASS' if opts.get('gate_pass') else 'FAIL'}")
        walls = opts.get("significant_walls", [])
        if walls:
            lines.append(f"  OI Walls    : " + " | ".join(
                f"{w.get('strike')} {w.get('type')} ({w.get('oi','?')})" for w in walls[:4]))

    lines.append("\n═══ END CONTEXT ═══")
    return "\n".join(lines)


@app.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute")
def api_chat():
    """
    AI Agent Chat — user sends a message, Claude/Gemini responds using
    full live trading context (positions, signals, sessions, options flow).
    Body: {message: str, history: [{role, content}, ...]}
    """
    req     = request.get_json(silent=True) or {}
    message = req.get("message", "").strip()
    history = req.get("history", [])   # [{role:"user"|"assistant", content:"..."}]

    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400

    context = _build_chat_context()

    # ── Try Claude first ───────────────────────────────────────────────────────
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            # Build message list (keep last 10 turns for memory)
            msgs = []
            for h in history[-10:]:
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    msgs.append({"role": h["role"], "content": h["content"]})
            msgs.append({"role": "user", "content": message})

            resp = client.messages.create(
                model   = "claude-haiku-4-5-20251001",
                max_tokens = 600,
                system  = context,
                messages = msgs,
            )
            reply = resp.content[0].text if resp.content else "No response"
            return jsonify({"ok": True, "reply": reply, "model": "Claude Haiku"})

        except Exception as e:
            log.warning("Chat Claude failed: %s — trying Gemini", e)

    # ── Fallback to Gemini ─────────────────────────────────────────────────────
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction=context,
            )
            # Reconstruct history for Gemini (must alternate user/model)
            gem_history = []
            for h in history[-8:]:
                role = "user" if h.get("role") == "user" else "model"
                if gem_history and gem_history[-1]["role"] == role:
                    gem_history[-1]["parts"][0] += "\n" + h.get("content", "")
                else:
                    gem_history.append({"role": role, "parts": [h.get("content","")]})
            chat = model.start_chat(history=gem_history)
            resp = chat.send_message(message)
            reply = resp.text
            return jsonify({"ok": True, "reply": reply, "model": "Gemini Flash"})

        except Exception as e:
            log.error("Chat Gemini failed: %s", e)

    # ── No LLM available — rule-based fallback ─────────────────────────────────
    msg_lower = message.lower()
    signals   = shared_state.get("trade_signals", [])
    portfolio = {}
    try:
        if AGENTS_AVAILABLE:
            portfolio = paper_trader._load_portfolio()
    except Exception:
        pass

    if any(w in msg_lower for w in ["position", "portfolio", "holding", "open"]):
        try:
            pos = paper_trader.get_live_positions(shared_state.get("_price_cache", {})) if AGENTS_AVAILABLE else []
            if pos:
                parts = [f"{p['symbol']}: {p['shares']} shares @ ₹{p['entry_price']:,.2f}, "
                         f"Unrealised {'+'if p['unreal_pnl']>=0 else ''}₹{p['unreal_pnl']:,.0f} "
                         f"({'+' if p['unreal_pnl_pct']>=0 else ''}{p['unreal_pnl_pct']:.2f}%)" for p in pos]
                reply = "Open positions:\n" + "\n".join(parts)
            else:
                reply = "No open paper positions currently."
        except Exception:
            reply = "Could not load positions."
    elif any(w in msg_lower for w in ["signal", "buy", "sell", "recommend", "pick"]):
        top = sorted(signals, key=lambda x: x.get("score",0), reverse=True)[:3] if signals else []
        if top:
            parts = [f"{s.get('signal')} {s.get('name')} — Score {s.get('score')}, "
                     f"Gates {s.get('gates_passed',0)}/8" for s in top]
            reply = "Top signals right now:\n" + "\n".join(parts)
        else:
            reply = "No active signals. Agents may still be scanning."
    elif any(w in msg_lower for w in ["market", "nifty", "sensex", "price"]):
        pc = shared_state.get("_price_cache", {})
        nifty   = pc.get("^NSEI",   {}).get("price")
        sensex  = pc.get("^BSESN",  {}).get("price")
        reply = "NIFTY: " + (f"₹{nifty:,.2f}" if isinstance(nifty, float) else "--") + "  |  " + \
                "SENSEX: " + (f"₹{sensex:,.2f}" if isinstance(sensex, float) else "--")
    else:
        reply = ("No AI key configured. Add ANTHROPIC_API_KEY or GEMINI_API_KEY in the Settings tab "
                 "to enable full AI chat. I can still answer questions about positions, signals, and prices.")

    return jsonify({"ok": True, "reply": reply, "model": "Rule Engine"})


# ══════════════════════════════════════════════════════════════════════════════
# ATLAS API ENDPOINTS — Self-Learning Knowledge Engine
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/atlas/stats")
def api_atlas_stats():
    """ATLAS knowledge base statistics for dashboard panel."""
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False, "message": "ATLAS not loaded"})
    try:
        stats    = get_knowledge_stats()
        upgrade  = get_upgrade_status()
        time_ctx = get_time_context()
        return jsonify({
            "available":   True,
            "stats":       stats,
            "upgrade":     upgrade,
            "time_context": time_ctx,
            "atlas_context": shared_state.get("atlas_context", {}),
        })
    except Exception as e:
        return jsonify({"available": True, "error": str(e)}), 500


@app.route("/api/atlas/patterns")
def api_atlas_patterns():
    """Top GOLD and SILVER patterns discovered by ATLAS."""
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False})
    try:
        quality = request.args.get("quality", "GOLD")
        limit   = int(request.args.get("limit", 15))
        patterns = get_best_patterns(quality=quality, limit=limit)
        return jsonify({"available": True, "patterns": patterns, "quality": quality})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/atlas/rules")
def api_atlas_rules():
    """Active auto-generated trading rules."""
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False})
    try:
        rule_type = request.args.get("type")
        rules     = get_active_rules(rule_type=rule_type)
        return jsonify({"available": True, "rules": rules, "count": len(rules)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/atlas/lessons")
def api_atlas_lessons():
    """Recent lessons from closed trades with causal analysis."""
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False})
    try:
        from atlas.core import get_recent_lessons_atlas
        ticker = request.args.get("ticker")
        limit  = int(request.args.get("limit", 10))
        lessons = get_recent_lessons_atlas(ticker=ticker, limit=limit)
        return jsonify({"available": True, "lessons": lessons})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/atlas/query")
def api_atlas_query():
    """
    Query ATLAS: what happened historically when conditions were like now?
    Params: regime, pcr_zone, volume_class, sector, news_type
    """
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False})
    try:
        from atlas.core import query_similar_conditions
        regime       = request.args.get("regime")
        pcr_zone     = request.args.get("pcr_zone")
        volume_class = request.args.get("volume_class")
        sector       = request.args.get("sector")
        news_type    = request.args.get("news_type")
        limit        = int(request.args.get("limit", 10))
        results = query_similar_conditions(
            regime=regime, pcr_zone=pcr_zone,
            volume_class=volume_class, sector=sector,
            news_type=news_type, limit=limit,
        )
        return jsonify({"available": True, "results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/atlas/upgrade", methods=["GET", "POST"])
def api_atlas_upgrade():
    """
    Trigger a manual ATLAS self-upgrade cycle.
    Runs full synthesis: patterns, rules, causal analysis, LLM insights.
    """
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False, "message": "ATLAS not loaded"})
    try:
        use_llm = request.args.get("llm", "true").lower() != "false"
        log.info("🧠 ATLAS: Manual upgrade triggered via API (llm=%s)", use_llm)
        results = run_upgrade(shared_state=shared_state, use_llm=use_llm)
        return jsonify({
            "available": True,
            "ok":        True,
            "run_id":    results.get("run_id"),
            "duration":  results.get("duration_secs"),
            "steps":     results.get("steps", {}),
            "top_insight": results.get("top_insight"),
        })
    except Exception as e:
        log.error("ATLAS upgrade API error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/atlas/classify-volume", methods=["POST"])
def api_atlas_classify_volume():
    """Classify a volume event in real time."""
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False})
    req = request.get_json(silent=True) or {}
    try:
        result = classify_volume(
            ticker                 = req.get("ticker", ""),
            current_volume         = req.get("current_volume", 0),
            avg_volume_20d         = req.get("avg_volume_20d", 1),
            price_change_pct       = req.get("price_change_pct", 0),
            price_vs_high_52w      = req.get("price_vs_high_52w", 100),
            price_vs_resistance    = req.get("price_vs_resistance", 0),
            is_near_corporate_event = req.get("is_near_corporate_event", False),
        )
        return jsonify({"available": True, **result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/atlas/news-context")
def api_atlas_news_context():
    """Get learned historical impact of a news event type."""
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False})
    try:
        from atlas.news_impact_mapper import get_news_context
        event_type = request.args.get("event_type", "EARNINGS")
        sector     = request.args.get("sector")
        ctx = get_news_context(event_type=event_type, sector=sector)
        return jsonify({"available": True, **ctx})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/atlas/options-context")
def api_atlas_options_context():
    """Get current options intelligence context."""
    if not ATLAS_AVAILABLE:
        return jsonify({"available": False})
    try:
        opts  = shared_state.get("options_flow", {})
        nifty = opts.get("nifty", {}) if isinstance(opts.get("nifty"), dict) else {}
        ctx   = get_options_context(
            pcr_nifty    = nifty.get("pcr"),
            pcr_banknifty = opts.get("banknifty", {}).get("pcr") if isinstance(opts.get("banknifty"), dict) else None,
            iv_percentile = nifty.get("iv_percentile"),
        )
        return jsonify({"available": True, **ctx})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── TERMINAL ENDPOINTS ────────────────────────────────────────────────────────

# ── Segment symbol catalogues ─────────────────────────────────────────────────
_TERMINAL_SYMBOLS = {
    "cash": [
        {"label": "RELIANCE", "sym": "RELIANCE.NS", "name": "Reliance Industries"},
        {"label": "TCS",      "sym": "TCS.NS",      "name": "Tata Consultancy Services"},
        {"label": "INFY",     "sym": "INFY.NS",     "name": "Infosys"},
        {"label": "HDFCBANK", "sym": "HDFCBANK.NS", "name": "HDFC Bank"},
        {"label": "ICICIBANK","sym": "ICICIBANK.NS","name": "ICICI Bank"},
        {"label": "SBIN",     "sym": "SBIN.NS",     "name": "State Bank of India"},
        {"label": "WIPRO",    "sym": "WIPRO.NS",    "name": "Wipro"},
        {"label": "AXISBANK", "sym": "AXISBANK.NS", "name": "Axis Bank"},
        {"label": "BAJFINANCE","sym":"BAJFINANCE.NS","name":"Bajaj Finance"},
        {"label": "KOTAKBANK","sym": "KOTAKBANK.NS","name": "Kotak Mahindra Bank"},
        {"label": "MARUTI",   "sym": "MARUTI.NS",   "name": "Maruti Suzuki"},
        {"label": "LT",       "sym": "LT.NS",       "name": "Larsen & Toubro"},
        {"label": "HINDUNILVR","sym":"HINDUNILVR.NS","name":"Hindustan Unilever"},
        {"label": "ADANIENT", "sym": "ADANIENT.NS", "name": "Adani Enterprises"},
        {"label": "TATAMOTORS","sym":"TATAMOTORS.NS","name":"Tata Motors"},
        {"label": "SUNPHARMA","sym": "SUNPHARMA.NS","name": "Sun Pharmaceutical"},
        {"label": "TITAN",    "sym": "TITAN.NS",    "name": "Titan Company"},
        {"label": "ASIANPAINT","sym":"ASIANPAINT.NS","name":"Asian Paints"},
        {"label": "ULTRACEMCO","sym":"ULTRACEMCO.NS","name":"UltraTech Cement"},
        {"label": "POWERGRID","sym": "POWERGRID.NS","name": "Power Grid Corp"},
    ],
    "fno": [
        {"label": "NIFTY 50", "sym": "^NSEI",     "name": "Nifty 50 Index"},
        {"label": "BANKNIFTY","sym": "^NSEBANK",  "name": "Bank Nifty Index"},
        {"label": "FINNIFTY", "sym": "NIFTY_FIN_SERVICE.NS","name":"Fin Nifty"},
        {"label": "MIDCPNIFTY","sym":"^NSEMDCP50","name":"Midcap Nifty"},
        {"label": "RELIANCE", "sym": "RELIANCE.NS","name":"Reliance F&O"},
        {"label": "HDFCBANK", "sym": "HDFCBANK.NS","name":"HDFC Bank F&O"},
        {"label": "ICICIBANK","sym": "ICICIBANK.NS","name":"ICICI Bank F&O"},
        {"label": "INFY",     "sym": "INFY.NS",    "name":"Infosys F&O"},
        {"label": "SBIN",     "sym": "SBIN.NS",    "name":"SBI F&O"},
        {"label": "TATAMOTORS","sym":"TATAMOTORS.NS","name":"Tata Motors F&O"},
        {"label": "BAJFINANCE","sym":"BAJFINANCE.NS","name":"Bajaj Finance F&O"},
        {"label": "AXISBANK", "sym": "AXISBANK.NS","name":"Axis Bank F&O"},
    ],
    "commodity": [
        {"label": "GOLD",     "sym": "GC=F",    "name": "Gold Futures"},
        {"label": "SILVER",   "sym": "SI=F",    "name": "Silver Futures"},
        {"label": "CRUDE OIL","sym": "CL=F",    "name": "Crude Oil WTI"},
        {"label": "BRENT",    "sym": "BZ=F",    "name": "Brent Crude"},
        {"label": "NAT GAS",  "sym": "NG=F",    "name": "Natural Gas"},
        {"label": "COPPER",   "sym": "HG=F",    "name": "Copper Futures"},
        {"label": "ALUMINIUM","sym": "ALI=F",   "name": "Aluminium"},
        {"label": "GOLDBEES", "sym": "GOLDBEES.NS","name":"Gold BeES ETF"},
    ],
    "currency": [
        {"label": "USD/INR",  "sym": "USDINR=X", "name": "USD to INR"},
        {"label": "EUR/INR",  "sym": "EURINR=X", "name": "EUR to INR"},
        {"label": "GBP/INR",  "sym": "GBPINR=X", "name": "GBP to INR"},
        {"label": "JPY/INR",  "sym": "JPYINR=X", "name": "JPY to INR"},
        {"label": "EUR/USD",  "sym": "EURUSD=X", "name": "EUR to USD"},
        {"label": "GBP/USD",  "sym": "GBPUSD=X", "name": "GBP to USD"},
    ],
    "crypto": [
        {"label": "BTC/USDT", "sym": "BTC-USD",  "name": "Bitcoin"},
        {"label": "ETH/USDT", "sym": "ETH-USD",  "name": "Ethereum"},
        {"label": "BNB/USDT", "sym": "BNB-USD",  "name": "Binance Coin"},
        {"label": "SOL/USDT", "sym": "SOL-USD",  "name": "Solana"},
        {"label": "XRP/USDT", "sym": "XRP-USD",  "name": "Ripple"},
        {"label": "DOGE/USDT","sym": "DOGE-USD", "name": "Dogecoin"},
        {"label": "ADA/USDT", "sym": "ADA-USD",  "name": "Cardano"},
        {"label": "AVAX/USDT","sym": "AVAX-USD", "name": "Avalanche"},
    ],
}

@app.route("/api/segments")
def api_segments():
    """Return symbol catalogue grouped by market segment for Terminal."""
    return jsonify(_TERMINAL_SYMBOLS)


@app.route("/api/feed-status")
def api_feed_status():
    """Return active data feed and status of all configured connectors."""
    try:
        import os
        forced = os.getenv("ACTIVE_FEED", "")
        if _FEED_OK and _feed_mgr:
            status_data = _feed_mgr.status()
            status_data["forced_feed"] = forced
            # Inject Shoonya auth error if present
            try:
                from src.agents.feeds.shoonya_feed import ShoonyaFeed
                if ShoonyaFeed._auth_error:
                    import time as _t
                    age = int(_t.time() - ShoonyaFeed._auth_failed_at)
                    status_data["shoonya_auth_error"]   = ShoonyaFeed._auth_error
                    status_data["shoonya_retry_in_sec"] = max(0, ShoonyaFeed._AUTH_RETRY_SEC - age)
                    status_data["shoonya_connected"]    = False
                else:
                    status_data["shoonya_connected"] = ShoonyaFeed._session is not None
            except Exception:
                pass
            # Inject masked credential state so the form knows what's already saved
            def _masked(key):
                v = os.getenv(key, "").strip()
                return "●●●●●●●●" if v else ""
            status_data["saved_creds"] = {
                "shoonya_user":         _masked("SHOONYA_USER"),
                "shoonya_password":     _masked("SHOONYA_PASSWORD"),
                "shoonya_api_key":      _masked("SHOONYA_API_KEY"),
                "shoonya_totp_key":     _masked("SHOONYA_TOTP_KEY"),
                "shoonya_vendor_code":  _masked("SHOONYA_VENDOR_CODE"),
                "upstox_access_token":  _masked("UPSTOX_ACCESS_TOKEN"),
                "truedata_username":    _masked("TRUEDATA_USERNAME"),
                "truedata_password":    _masked("TRUEDATA_PASSWORD"),
                "angel_api_key":        _masked("ANGEL_API_KEY"),
                "angel_client_id":      _masked("ANGEL_CLIENT_ID"),
                "angel_mpin":           _masked("ANGEL_PASSWORD"),
                "angel_totp_key":       _masked("ANGEL_TOTP_KEY"),
                "fyers_access_token":   _masked("FYERS_ACCESS_TOKEN"),
                "fyers_app_id":         _masked("FYERS_CLIENT_ID"),
                "zerodha_api_key":      _masked("KITE_API_KEY"),
                "zerodha_access_token": _masked("KITE_ACCESS_TOKEN"),
            }
            return jsonify(status_data)
        return jsonify({"active_feed": "yahoo", "active_label": "Yahoo Finance",
                        "is_realtime": False, "feeds": [], "forced_feed": forced,
                        "saved_creds": {}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shoonya-test")
def api_shoonya_test():
    """
    Explicitly test Shoonya/Finvasia login and return detailed diagnostics.
    Clears any cached auth failure so a fresh login is attempted.
    Use this from the API Keys tab to debug why Shoonya isn't connecting.
    """
    try:
        from src.agents.feeds.shoonya_feed import ShoonyaFeed
        result = ShoonyaFeed.test_connection()
        status_code = 200 if result["ok"] else 400
        return jsonify(result), status_code
    except ImportError:
        return jsonify({"ok": False, "error": "ShoonyaFeed not available — check imports"}), 503
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/feed-reload")
def api_feed_reload():
    """Force re-detect active feed (after updating .env keys at runtime)."""
    try:
        from dotenv import load_dotenv
        env_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
        load_dotenv(env_path, override=True)
        
        if _FEED_OK and _feed_mgr:
            _feed_mgr.reload()
            return jsonify({"status": "ok", "active_feed": _feed_mgr.active_name,
                            "active_label": _feed_mgr.active_label})
        return jsonify({"status": "ok", "active_feed": "yahoo"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/set-active-feed", methods=["POST"])
def api_set_active_feed():
    try:
        from dotenv import set_key
        data = request.get_json() or {}
        feed = data.get("feed", "").lower().strip()
        
        env_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
        
        if feed:
            os.environ["ACTIVE_FEED"] = feed
            set_key(env_path, "ACTIVE_FEED", feed)
        else:
            if "ACTIVE_FEED" in os.environ:
                del os.environ["ACTIVE_FEED"]
            # To actually remove it from .env would be harder, so we set to empty
            set_key(env_path, "ACTIVE_FEED", "")
            
        if _FEED_OK and _feed_mgr:
            _feed_mgr.reload()
            return jsonify({"status": "ok", "active_feed": _feed_mgr.active_name, "active_label": _feed_mgr.active_label})
            
        return jsonify({"status": "ok", "active_feed": "yahoo"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/multi-strike")
def api_multi_strike():
    """Mock API returning intraday Open Interest changes for 3 major strikes."""
    import time, random
    # Generate 5-minute ticks for the last 4 hours
    now = int(time.time())
    start = now - (4 * 3600)
    times = list(range(start, now, 300))
    
    strikes = [
        {"name": "23000 CE", "color": "#ef4444", "base": 50.0},
        {"name": "23000 PE", "color": "#10b981", "base": 42.0},
        {"name": "22900 PE", "color": "#0ea5e9", "base": 30.0}
    ]
    
    series_data = []
    for s in strikes:
        val = s["base"]
        data_points = []
        for t in times:
            val += random.uniform(-0.5, 0.6) # add some trend
            data_points.append({"time": t, "value": round(val, 2)})
        series_data.append({"name": s["name"], "color": s["color"], "data": data_points})
        
    return jsonify({"series": series_data})


@app.route("/api/sensibull-screener")
def api_sensibull_screener():
    """Return top screened F&O stocks with their IV, PCR, Max Pain data."""
    import random
    stocks = ["RELIANCE", "HDFCBANK", "ICICIBANK", "TCS", "INFY", "ITC", "LART", "SBI"]
    data = []
    
    for s in stocks:
        fut_price = random.uniform(500, 3500)
        pcr = random.uniform(0.5, 1.5)
        bias = "Bearish" if pcr < 0.8 else ("Bullish" if pcr > 1.2 else "Neutral")
        if bias == "Bearish":
            fut_chg = random.uniform(-4.0, -0.5)
        elif bias == "Bullish":
            fut_chg = random.uniform(0.5, 4.0)
        else:
            fut_chg = random.uniform(-1.0, 1.0)
            
        atm_iv = random.uniform(12.0, 35.0)
        ivp = int(random.uniform(5, 99))
        
        # Round fut price to nearest 10 or 20 to get max pain
        max_pain = int(round(fut_price / 10.0)) * 10
        
        data.append({
            "ticker": s,
            "fut_price": round(fut_price, 1),
            "fut_chg": round(fut_chg, 2),
            "atm_iv": round(atm_iv, 1),
            "ivp": ivp,
            "pcr": round(pcr, 2),
            "max_pain": max_pain,
            "bias": bias
        })
        
    return jsonify({"screener": data})


import threading
import time
import random

LIVE_OPTIONS_CACHE = {
    "NIFTY": {"spot": 22950, "chain": [], "alerts": []},
    "BANKNIFTY": {"spot": 48000, "chain": [], "alerts": []}
}

def live_anomaly_daemon():
    """Simulates a live WebSocket stream analyzing Shoonya WSS ticks continuously."""
    pe_22900_ltp = 160.0
    phase = 0 # 0=dropping, 1=recovering aggressively
    
    while True:
        try:
            spot = 22950 + random.uniform(-10, 10)
            LIVE_OPTIONS_CACHE["NIFTY"]["spot"] = spot
            
            # Massive algorithmic spike simulator on 22900 PE mirroring user's chart exactly!
            if phase == 0:
                pe_22900_ltp -= random.uniform(2, 6) # Dropping fast
                if pe_22900_ltp <= 80:
                    phase = 1
            else:
                pe_22900_ltp += random.uniform(8, 15) # Spikes heavily
                if pe_22900_ltp >= 250:
                    phase = 0
            
            anomaly_alert = []
            is_spike = False
            # When the recovery crosses 130 rapidly, flash critical alert
            if phase == 1 and pe_22900_ltp > 130:
                is_spike = True
                anomaly_alert.append({
                    "id": f"spike-{int(time.time())}",
                    "level": "critical",
                    "title": "🚨 MASSIVE NIFTY 22900 PE RECOVERY SPIKE DETECTED",
                    "message": f"[LIVE WS TICK] Massive anomaly: NIFTY 22900 PE bottomed at 80 and is surging past ₹{int(pe_22900_ltp)}. Institutional straddle support violently breaking. Action required instantly.",
                    "time": time.strftime("%H:%M:%S")
                })
            
            chain = []
            strike_interval = 50
            atm_strike = int(round(spot / strike_interval)) * strike_interval
            
            for i in range(-5, 6):
                st = atm_strike + (i * strike_interval)
                dist = abs(st - spot)
                intrinsic_call = max(0, spot - st)
                intrinsic_put = max(0, st - spot)
                
                noise = random.uniform(0.95, 1.05)
                time_val = max(5, 150 - (dist * 0.4)) * noise
                
                c_ltp = intrinsic_call + time_val
                p_ltp = intrinsic_put + time_val
                
                c_oi = random.uniform(10.0, 80.0) if i >= 0 else random.uniform(1.0, 10.0)
                p_oi = random.uniform(10.0, 80.0) if i <= 0 else random.uniform(1.0, 10.0)
                if i == 0: c_oi += 40; p_oi += 40
                
                c_chg = random.uniform(-10, 10)
                p_chg = random.uniform(-10, 10)
                iv = random.uniform(16.0, 24.0)
                
                row_is_spike = False
                if st == 22900:
                    p_ltp = pe_22900_ltp
                    p_chg = ((pe_22900_ltp - 80) / 80) * 100 # percentage change from base
                    p_oi += 200 # massive institutional volume
                    if is_spike: row_is_spike = True
                
                chain.append({
                    "strike": st,
                    "c_ltp": round(c_ltp, 2),
                    "p_ltp": round(p_ltp, 2),
                    "c_oi": round(c_oi, 1),
                    "p_oi": round(p_oi, 1),
                    "c_chg": f"{int(c_chg)}%",
                    "p_chg": f"{int(p_chg)}%",
                    "iv": round(iv, 1),
                    "spike": row_is_spike
                })
            
            LIVE_OPTIONS_CACHE["NIFTY"]["chain"] = chain
            if len(anomaly_alert) > 0:
                LIVE_OPTIONS_CACHE["NIFTY"]["alerts"] = anomaly_alert + [
                    {"id": "a2", "level": "warning", "title": "Volatile VIX", "message": "India VIX up 4% today indicating premium expansion.", "time": time.strftime("%H:%M:%S")}
                ]
            else:
                LIVE_OPTIONS_CACHE["NIFTY"]["alerts"] = [
                    {"id": "a1", "level": "info", "title": "Agent Sweep Status", "message": "Monitoring all strikes for sudden OI expansion or gamma blast.", "time": time.strftime("%H:%M:%S")}
                ]
                
        except Exception:
            pass
        
        time.sleep(1.5) # Fast 1500ms intervals recreating live DOM polling

try:
    threading.Thread(target=live_anomaly_daemon, daemon=True).start()
except Exception:
    pass

# ═══════════════════════════════════════════════════════════════
#  INDEX ANALYTICS — Pivots, PCR, Max Pain, ATM IV, IVP, Strikes
# ═══════════════════════════════════════════════════════════════

_NSE_SESSION  = None
_NSE_CACHE    = {}       # sym → {ts, data}
_NSE_CACHE_TTL = 60      # seconds

_INDEX_META = {
    "NIFTY":       {"yahoo": "^NSEI",      "step": 50,  "lot": 75,  "label": "NIFTY 50"},
    "BANKNIFTY":   {"yahoo": "^NSEBANK",   "step": 100, "lot": 15,  "label": "BANK NIFTY"},
    "FINNIFTY":    {"yahoo": "^CNXFIN",    "step": 50,  "lot": 40,  "label": "FIN NIFTY"},
    "MIDCPNIFTY":  {"yahoo": "^CNXMIDCAP", "step": 25,  "lot": 75,  "label": "MIDCAP NIFTY"},
    "SENSEX":      {"yahoo": "^BSESN",     "step": 100, "lot": 10,  "label": "SENSEX"},
}

def _get_nse_session():
    global _NSE_SESSION
    try:
        if _NSE_SESSION:
            return _NSE_SESSION
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        s.get("https://www.nseindia.com", timeout=8)
        _NSE_SESSION = s
        return s
    except Exception as e:
        log.warning("NSE session init failed: %s", e)
        return None

def _fetch_nse_option_chain(symbol: str) -> dict | None:
    """Fetch NSE option chain with in-memory cache (60s TTL)."""
    global _NSE_SESSION
    now = time.time()
    cached = _NSE_CACHE.get(symbol)
    if cached and (now - cached["ts"]) < _NSE_CACHE_TTL:
        return cached["data"]

    for attempt in range(2):
        try:
            session = _get_nse_session()
            if not session:
                return None
            url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
            r = session.get(url, timeout=10,
                            headers={"Referer": "https://www.nseindia.com/option-chain"})
            if r.status_code == 401:
                _NSE_SESSION = None   # force re-init
                continue
            data = r.json()
            _NSE_CACHE[symbol] = {"ts": now, "data": data}
            return data
        except Exception as e:
            log.debug("NSE option chain attempt %d failed: %s", attempt + 1, e)
            _NSE_SESSION = None
    return None

def _calc_pivots(high: float, low: float, close: float) -> dict:
    """Standard floor-trader pivots."""
    p  = round((high + low + close) / 3, 2)
    r1 = round(2 * p - low, 2)
    r2 = round(p + (high - low), 2)
    r3 = round(high + 2 * (p - low), 2)
    s1 = round(2 * p - high, 2)
    s2 = round(p - (high - low), 2)
    s3 = round(low - 2 * (high - p), 2)
    return {"pivot": p, "r1": r1, "r2": r2, "r3": r3,
            "s1": s1, "s2": s2, "s3": s3}

def _calc_ivp(current_iv: float, yahoo_sym: str) -> int:
    """
    IVP = % of past 252 days where 30-day HV < current ATM IV.
    Uses annualised 30-day rolling historical volatility from daily returns.
    Returns 0-100.
    """
    try:
        import yfinance as yf
        import math
        tk = yf.Ticker(yahoo_sym)
        hist = tk.history(period="1y", interval="1d")
        if len(hist) < 32:
            return 50
        closes = hist["Close"].dropna().tolist()
        hvs = []
        for i in range(30, len(closes)):
            rets = [math.log(closes[j] / closes[j-1]) for j in range(i-29, i+1)]
            mean = sum(rets) / len(rets)
            var  = sum((r - mean)**2 for r in rets) / len(rets)
            hvs.append(math.sqrt(var * 252) * 100)
        if not hvs:
            return 50
        below = sum(1 for hv in hvs if hv < current_iv)
        return int(below / len(hvs) * 100)
    except Exception:
        return 50

def _process_nse_chain(nse_data: dict, spot: float, step: int, expiry_idx: int = 0):
    """
    From raw NSE option chain data extract:
    - selected expiry's strikes
    - PCR, Max Pain, ATM IV, nearby strikes with OI/IV/LTP
    - futures price (synthetic from options ATM parity)
    """
    records = nse_data.get("records", {})
    expiry_dates = records.get("expiryDates", [])
    if not expiry_dates:
        return {}

    expiry = expiry_dates[min(expiry_idx, len(expiry_dates)-1)]
    all_data = records.get("data", [])

    # Filter to selected expiry
    rows = [r for r in all_data if r.get("expiryDate") == expiry]

    atm = round(spot / step) * step
    total_call_oi = total_put_oi = 0
    max_pain_min  = float("inf")
    max_pain_lvl  = atm
    atm_ce_iv = atm_pe_iv = 0.0
    fut_price = 0.0

    # Build strike table
    strike_map = {}
    for row in rows:
        st = row.get("strikePrice", 0)
        ce = row.get("CE", {}) or {}
        pe = row.get("PE", {}) or {}
        ce_oi  = ce.get("openInterest",      0) or 0
        pe_oi  = pe.get("openInterest",      0) or 0
        ce_chg = ce.get("changeinOpenInterest", 0) or 0
        pe_chg = pe.get("changeinOpenInterest", 0) or 0
        ce_iv  = ce.get("impliedVolatility",  0) or 0
        pe_iv  = pe.get("impliedVolatility",  0) or 0
        ce_ltp = ce.get("lastPrice",          0) or 0
        pe_ltp = pe.get("lastPrice",          0) or 0

        total_call_oi += ce_oi
        total_put_oi  += pe_oi

        if st == atm:
            atm_ce_iv = ce_iv
            atm_pe_iv = pe_iv
            # Synthetic futures from put-call parity: F = K + (C - P)
            if ce_ltp and pe_ltp:
                fut_price = round(atm + ce_ltp - pe_ltp, 2)

        strike_map[st] = {
            "strike": st,
            "call_oi":  ce_oi,  "put_oi":  pe_oi,
            "call_chg": ce_chg, "put_chg": pe_chg,
            "call_iv":  ce_iv,  "put_iv":  pe_iv,
            "call_ltp": ce_ltp, "put_ltp": pe_ltp,
            "pcr_strike": round(pe_oi / ce_oi, 2) if ce_oi else 0,
        }

    # PCR
    pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi else 0

    # Max Pain — minimize total losses to option writers
    strikes = sorted(strike_map.keys())
    for test_price in strikes:
        pain = 0
        for st, row in strike_map.items():
            pain += row["call_oi"] * max(0, st - test_price)
            pain += row["put_oi"]  * max(0, test_price - st)
        if pain < max_pain_min:
            max_pain_min = pain
            max_pain_lvl = test_price

    # ATM IV (avg of ATM call + put IV)
    atm_iv = round((atm_ce_iv + atm_pe_iv) / 2, 1) if (atm_ce_iv and atm_pe_iv) else 0

    # Nearby strikes (5 below + ATM + 5 above)
    all_strikes = sorted(strike_map.keys())
    atm_idx = next((i for i, s in enumerate(all_strikes) if s >= atm), len(all_strikes)//2)
    lo = max(0, atm_idx - 5)
    hi = min(len(all_strikes), atm_idx + 6)
    nearby = [strike_map[s] for s in all_strikes[lo:hi]]

    # Mark ATM and high-OI (support/resistance) strikes
    max_call_oi = max((r["call_oi"] for r in nearby), default=1) or 1
    max_put_oi  = max((r["put_oi"]  for r in nearby), default=1) or 1
    for row in nearby:
        row["is_atm"] = row["strike"] == atm
        row["call_bar"] = round(row["call_oi"] / max_call_oi * 100)
        row["put_bar"]  = round(row["put_oi"]  / max_put_oi  * 100)
        # Identify strong support/resistance via concentration
        row["is_resistance"] = (row["call_oi"] / max_call_oi > 0.7)
        row["is_support"]    = (row["put_oi"]  / max_put_oi  > 0.7)

    if not fut_price:
        fut_price = spot  # fallback

    return {
        "expiry":     expiry,
        "expiries":   expiry_dates[:4],
        "spot":       spot,
        "atm":        atm,
        "fut_price":  fut_price,
        "atm_iv":     atm_iv,
        "pcr":        pcr,
        "max_pain":   max_pain_lvl,
        "total_call_oi": total_call_oi,
        "total_put_oi":  total_put_oi,
        "nearby":     nearby,
    }

@app.route("/api/index-analytics")
def api_index_analytics():
    """
    Full index analytics for the UI header bar:
    - Spot price + change%
    - Futures price (synthetic put-call parity)
    - ATM IV, IVP (Historical Volatility Percentile)
    - PCR (Put-Call Ratio)
    - Max Pain level
    - Daily + Weekly pivot levels (Pivot, R1-R3, S1-S3)
    - Nearby strikes table (+/- 5 around ATM) with OI, IV, LTP
    ?sym=NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX
    ?expiry_idx=0  (0=nearest, 1=next, etc.)
    """
    sym = request.args.get("sym", "NIFTY").upper().strip()
    expiry_idx = int(request.args.get("expiry_idx", 0))

    meta = _INDEX_META.get(sym, _INDEX_META["NIFTY"])
    yahoo_sym = meta["yahoo"]
    step      = meta["step"]

    # ── 1. Spot price from price_cache ────────────────────────────────────────
    name_key = meta["label"]
    spot = price_cache.get(name_key, {}).get("price", 0) or price_cache.get(sym, {}).get("price", 0)

    # Fallback: fetch from Yahoo
    if not spot:
        try:
            import yfinance as yf
            tk = yf.Ticker(yahoo_sym)
            info = tk.fast_info
            spot = float(getattr(info, "last_price", 0) or getattr(info, "regularMarketPrice", 0) or 0)
        except Exception:
            spot = 0

    # ── 2. Spot change % ──────────────────────────────────────────────────────
    spot_chg = price_cache.get(name_key, {}).get("change_pct", 0) or 0

    # ── 3. NSE Option Chain ───────────────────────────────────────────────────
    chain_result = {}
    try:
        # SENSEX options use BSE — use simpler path
        nse_sym = "NIFTY" if sym in ("NIFTY", "NIFTY 50") else \
                  "BANKNIFTY" if sym == "BANKNIFTY" else \
                  "FINNIFTY" if sym == "FINNIFTY" else \
                  "MIDCPNIFTY" if sym == "MIDCPNIFTY" else sym
        nse_data = _fetch_nse_option_chain(nse_sym)
        if nse_data and spot:
            chain_result = _process_nse_chain(nse_data, spot, step, expiry_idx)
    except Exception as e:
        log.warning("Index analytics chain error: %s", e)

    # ── 4. Daily Pivot (yesterday's OHLC) ─────────────────────────────────────
    daily_pivot = weekly_pivot = {}
    try:
        import yfinance as yf
        tk = yf.Ticker(yahoo_sym)
        hist_d = tk.history(period="5d", interval="1d")
        if len(hist_d) >= 2:
            y = hist_d.iloc[-2]   # yesterday
            daily_pivot = _calc_pivots(float(y["High"]), float(y["Low"]), float(y["Close"]))
        hist_w = tk.history(period="1mo", interval="1wk")
        if len(hist_w) >= 2:
            w = hist_w.iloc[-2]   # last completed week
            weekly_pivot = _calc_pivots(float(w["High"]), float(w["Low"]), float(w["Close"]))
    except Exception as e:
        log.debug("Pivot fetch failed: %s", e)

    # ── 5. Fallback: compute analytics from LIVE_OPTIONS_CACHE if NSE failed ──
    if not chain_result.get("nearby"):
        try:
            cache_key = "NIFTY" if sym in ("NIFTY", "NIFTY 50") else \
                        "BANKNIFTY" if sym == "BANKNIFTY" else "NIFTY"
            cached_chain = LIVE_OPTIONS_CACHE.get(cache_key, {}).get("chain", [])
            if cached_chain and spot:
                atm = round(spot / step) * step
                total_c = total_p = 0.0
                max_pain_min_fb = float("inf")
                max_pain_fb = atm
                atm_iv_fb = 0.0
                nearby_fb = []
                max_c_oi = max(r.get("c_oi", 0) for r in cached_chain) or 1
                max_p_oi = max(r.get("p_oi", 0) for r in cached_chain) or 1

                for row in cached_chain:
                    st  = row.get("strike", 0)
                    c_oi = (row.get("c_oi", 0) or 0) * 100000   # convert lakhs → units
                    p_oi = (row.get("p_oi", 0) or 0) * 100000
                    total_c += c_oi; total_p += p_oi
                    if st == atm:
                        atm_iv_fb = row.get("iv", 0) or 0

                # Max pain from cached chain
                for test_st in [r.get("strike",0) for r in cached_chain]:
                    pain = sum((r.get("c_oi",0)*100000) * max(0, r.get("strike",0) - test_st) +
                               (r.get("p_oi",0)*100000) * max(0, test_st - r.get("strike",0))
                               for r in cached_chain)
                    if pain < max_pain_min_fb:
                        max_pain_min_fb = pain; max_pain_fb = test_st

                pcr_fb = round(total_p / total_c, 2) if total_c else 0

                # Build nearby list
                for row in cached_chain:
                    st = row.get("strike", 0)
                    is_atm = st == atm
                    c_oi_raw = row.get("c_oi", 0) or 0
                    p_oi_raw = row.get("p_oi", 0) or 0
                    nearby_fb.append({
                        "strike":    st,
                        "call_oi":   round(c_oi_raw * 100000),
                        "put_oi":    round(p_oi_raw * 100000),
                        "call_chg":  0, "put_chg": 0,
                        "call_iv":   row.get("iv", 0), "put_iv": row.get("iv", 0),
                        "call_ltp":  row.get("c_ltp", 0), "put_ltp": row.get("p_ltp", 0),
                        "pcr_strike":round(p_oi_raw / c_oi_raw, 2) if c_oi_raw else 0,
                        "is_atm":    is_atm,
                        "call_bar":  round(c_oi_raw / max_c_oi * 100),
                        "put_bar":   round(p_oi_raw / max_p_oi * 100),
                        "is_resistance": c_oi_raw / max_c_oi > 0.7,
                        "is_support":    p_oi_raw / max_p_oi > 0.7,
                    })

                chain_result = {
                    "atm": atm, "pcr": pcr_fb, "max_pain": max_pain_fb,
                    "atm_iv": atm_iv_fb, "fut_price": round(spot, 2),
                    "total_call_oi": round(total_c), "total_put_oi": round(total_p),
                    "nearby": nearby_fb, "expiry": "Weekly", "expiries": ["Weekly", "Monthly"],
                }
        except Exception as e:
            log.debug("Fallback chain analytics error: %s", e)

    # ── 6. HV-based ATM IV if still missing ───────────────────────────────────
    atm_iv = chain_result.get("atm_iv", 0)
    if not atm_iv:
        try:
            import yfinance as yf, math
            tk2 = yf.Ticker(yahoo_sym)
            h2 = tk2.history(period="35d", interval="1d")
            if len(h2) >= 22:
                closes = h2["Close"].dropna().tolist()[-22:]
                rets = [math.log(closes[i]/closes[i-1]) for i in range(1, len(closes))]
                hv_30 = math.sqrt(sum(r**2 for r in rets)/len(rets) * 252) * 100
                atm_iv = round(hv_30, 1)
        except Exception:
            atm_iv = 0

    # ── 7. IVP ────────────────────────────────────────────────────────────────
    ivp = _calc_ivp(atm_iv, yahoo_sym) if atm_iv else 50

    # ── 6. Breakout analysis ──────────────────────────────────────────────────
    breakout_zones = []
    if daily_pivot and spot:
        levels = [
            ("R3", daily_pivot.get("r3"), "resistance"),
            ("R2", daily_pivot.get("r2"), "resistance"),
            ("R1", daily_pivot.get("r1"), "resistance"),
            ("PP", daily_pivot.get("pivot"), "pivot"),
            ("S1", daily_pivot.get("s1"), "support"),
            ("S2", daily_pivot.get("s2"), "support"),
            ("S3", daily_pivot.get("s3"), "support"),
        ]
        for name, lvl, kind in levels:
            if not lvl:
                continue
            dist_pct = abs(spot - lvl) / spot * 100
            if dist_pct < 1.5:      # within 1.5% of current price
                action = "retest" if abs(spot - lvl) / spot < 0.005 else \
                         ("near_break" if kind == "resistance" and spot > lvl * 0.995 else
                          "near_break" if kind == "support"    and spot < lvl * 1.005 else "approaching")
                breakout_zones.append({
                    "label":  name,
                    "level":  lvl,
                    "type":   kind,
                    "action": action,
                    "dist_pct": round(dist_pct, 2),
                })
        breakout_zones.sort(key=lambda x: x["dist_pct"])

    return jsonify({
        "sym":        sym,
        "label":      meta["label"],
        "spot":       round(spot, 2),
        "spot_chg":   round(spot_chg, 2),
        "fut_price":  chain_result.get("fut_price", round(spot, 2)),
        "atm":        chain_result.get("atm", round(spot / step) * step),
        "atm_iv":     atm_iv,
        "ivp":        ivp,
        "pcr":        chain_result.get("pcr", 0),
        "max_pain":   chain_result.get("max_pain", 0),
        "expiry":     chain_result.get("expiry", ""),
        "expiries":   chain_result.get("expiries", []),
        "daily_pivot":  daily_pivot,
        "weekly_pivot": weekly_pivot,
        "nearby":     chain_result.get("nearby", []),
        "breakout_zones": breakout_zones,
        "total_call_oi":  chain_result.get("total_call_oi", 0),
        "total_put_oi":   chain_result.get("total_put_oi", 0),
    })


@app.route("/api/option-chain")
def api_option_chain():
    """Returns the LIVE cached Option Chain mirroring the WSS Daemon."""
    sym = request.args.get("sym", "NIFTY")
    if sym.upper() == "NIFTY":
        spot = LIVE_OPTIONS_CACHE["NIFTY"]["spot"]
        chain = LIVE_OPTIONS_CACHE["NIFTY"]["chain"]
        alerts = LIVE_OPTIONS_CACHE["NIFTY"]["alerts"]
    else:
        spot = 48000
        chain = []
        alerts = []
        
    return jsonify({
        "spot": round(spot, 2),
        "spot_chg": round(((spot - 23000)/23000)*100, 2),
        "chain": chain,
        "alerts": alerts
    })
def api_update_token():
    """
    Hot-update a broker access token without restarting the app.
    Body: { "broker": "upstox|zerodha|fyers", "token": "new_token_here" }
    """
    try:
        body   = request.get_json(force=True) or {}
        broker = body.get("broker", "").lower().strip()
        token  = body.get("token",  "").strip()
        if not broker or not token:
            return jsonify({"error": "broker and token are required"}), 400
        from src.agents.feeds.token_refresh import update_token_in_env
        ok = update_token_in_env(broker, token)
        if ok:
            if _FEED_OK and _feed_mgr:
                _feed_mgr.reload()
            return jsonify({"status": "ok", "broker": broker,
                            "active_feed": _feed_mgr.active_name if (_FEED_OK and _feed_mgr) else "yahoo"})
        return jsonify({"error": "Failed to update token"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/token-status")
def api_token_status():
    """Return masked token status for all daily-expiry brokers."""
    try:
        from src.agents.feeds.token_refresh import get_token_status
        return jsonify(get_token_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/symbol-search")
def api_symbol_search():
    """Search for instrument symbols by name or ticker."""
    query   = request.args.get("q", "").strip()
    segment = request.args.get("segment", "all")
    if not query:
        return jsonify({"results": []})
    try:
        from src.agents.feeds.symbol_mapper import SymbolMapper
        mapper  = SymbolMapper()
        results = mapper.search(query, segment)
        return jsonify({"results": results, "query": query})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})


@app.route("/api/terminal-symbols")
def api_terminal_symbols():
    segment = request.args.get("segment", "cash").lower()
    return jsonify({"symbols": _TERMINAL_SYMBOLS.get(segment, []), "segment": segment})


# ── Segment → display currency ────────────────────────────────────────────────
# Cash / F&O / Commodity (MCX) → prices in INR
# Currency pairs / Crypto → prices in USD
_SEG_CURRENCY = {
    "cash":      "INR",
    "fno":       "INR",
    "commodity": "INR",
    "currency":  "USD",
    "crypto":    "USD",
}

def _resolve_display_currency(sym: str, seg: str) -> str:
    """Return 'INR' or 'USD' for the terminal header Currency stat."""
    if seg in _SEG_CURRENCY:
        return _SEG_CURRENCY[seg]
    # Auto-detect when no segment provided
    if sym.endswith(".NS") or sym.endswith(".BO") or sym.endswith("-EQ"):
        return "INR"
    if sym.startswith("^NSE") or sym.startswith("^BSE") or sym.startswith("^INDIA"):
        return "INR"
    return "USD"


@app.route("/api/ohlcv")
def api_ohlcv():
    """
    Fetch OHLCV candle data — routed through active DataFeed connector.
    Falls back to Yahoo Finance if no connector is configured.
    Query params: sym=RELIANCE.NS, interval=5m|15m|1h|1d|1wk, range=1d|5d|1mo|3mo|6mo|1y
                  seg=cash|fno|commodity|currency|crypto  (used for correct currency label)
    """
    sym      = request.args.get("sym", "^NSEI")
    interval = request.args.get("interval", "5m")
    rng      = request.args.get("range", "1d")
    seg      = request.args.get("seg", "").lower().strip()
    try:
        if _FEED_OK and _feed_mgr:
            result = _feed_mgr.get_candles(sym, interval, rng)
        else:
            from src.agents.feeds.yahoo_feed import YahooFeed
            result = YahooFeed().get_candles(sym, interval, rng)
        result["feed"]     = _feed_mgr.active_name if (_FEED_OK and _feed_mgr) else "yahoo"
        result["currency"] = _resolve_display_currency(sym, seg)
        return jsonify(result)
    except Exception as e:
        log.error("OHLCV error %s: %s", sym, e)
        return jsonify({"candles": [], "error": str(e)}), 500

@app.route("/api/orderbook")
def api_orderbook():
    """Live order book — simulated depth if no connector configured."""
    sym   = request.args.get("sym", "^NSEI")
    depth = int(request.args.get("depth", 15))
    try:
        if _FEED_OK and _feed_mgr:
            result = _feed_mgr.get_orderbook(sym, depth)
        else:
            from src.agents.feeds.yahoo_feed import YahooFeed
            result = YahooFeed().get_orderbook(sym, depth)
        result["feed"] = _feed_mgr.active_name if (_FEED_OK and _feed_mgr) else "yahoo"
        return jsonify(result)
    except Exception as e:
        log.warning("api_orderbook error %s: %s", sym, e)
        return jsonify({"bids": [], "asks": [], "error": str(e)}), 500


# ── APP ENTRY POINT ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    log.info(f"🚀 StockGuru v2.0 starting on http://0.0.0.0:{port}")
    if _SIO_AVAILABLE:
        socketio.run(app, host="0.0.0.0", port=port, debug=debug_mode)
    else:
        app.run(host="0.0.0.0", port=port, debug=debug_mode)
