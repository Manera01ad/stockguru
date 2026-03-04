"""
gunicorn.conf.py — StockGuru Production Server Config
======================================================
Flask-SocketIO + gevent requires:
  - GeventWebSocketWorker (not default sync worker)
  - Exactly 1 worker   (shared-memory state can't be forked across workers)
  - Long timeout       (15-min agent cycle + 5-min price fetch)

Railway deployment:
  PORT env var is auto-injected by Railway.
  Set all other env vars in Railway Dashboard → Variables.

Local dev:
  python app.py        (uses socketio.run() with gevent directly)
  gunicorn app:app --config gunicorn.conf.py   (production-equivalent)
"""

import os

# ── Binding ──────────────────────────────────────────────────────────────────
bind    = f"0.0.0.0:{os.getenv('PORT', '5050')}"

# ── Worker ───────────────────────────────────────────────────────────────────
# GeventWebSocketWorker: extends gevent worker with WebSocket upgrade support.
# Required for Flask-SocketIO async_mode='gevent'.
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
workers      = 1        # MUST be 1 — shared_state + price_cache are in-memory
worker_connections = 1000

# ── Timeouts ─────────────────────────────────────────────────────────────────
timeout      = 300      # 5 min: covers 15-min agent cycle gracefully
keepalive    = 5
graceful_timeout = 30

# ── Logging ──────────────────────────────────────────────────────────────────
accesslog    = "-"      # stdout → Railway logs
errorlog     = "-"      # stdout → Railway logs
loglevel     = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Process ──────────────────────────────────────────────────────────────────
preload_app  = False    # Do NOT preload — _startup() must run in worker context
daemon       = False    # Railway manages the process
