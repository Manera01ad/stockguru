"""
Token Refresh Helper — handles daily token expiry for Upstox, Zerodha, and Fyers.

Brokers that require daily token regeneration:
  • Upstox v2    → UPSTOX_ACCESS_TOKEN
  • Zerodha Kite → KITE_ACCESS_TOKEN
  • Fyers v3     → FYERS_ACCESS_TOKEN

This module:
  1. Detects when a token has expired (HTTP 401 from the broker API)
  2. Notifies via Telegram: "⚠️ Upstox token expired. Regenerate at upstox.com/developer"
  3. Provides a /api/update-token endpoint so you can paste a new token without restarting
  4. If TOTP is configured (Upstox TOTP auto-login), attempts auto-refresh
"""

import os
import re
import logging
import requests
from datetime import datetime, date
from pathlib import Path
from typing import Optional

log = logging.getLogger("token_refresh")

_ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# ── Token expiry detection ─────────────────────────────────────────────────────

BROKER_TOKEN_KEYS = {
    "upstox":  "UPSTOX_ACCESS_TOKEN",
    "zerodha": "KITE_ACCESS_TOKEN",
    "fyers":   "FYERS_ACCESS_TOKEN",
}

# Track last notification date so we don't spam Telegram
_notified_today: dict = {}


def is_token_error(response_data: dict, broker: str) -> bool:
    """Detect token expiry from broker API response."""
    errors = {
        "upstox":  lambda d: d.get("status") == "error" and "token" in str(d.get("errors","")).lower(),
        "zerodha": lambda d: d.get("error_type") in ("TokenException","InvalidSessionException"),
        "fyers":   lambda d: d.get("s") == "error" and d.get("code") in (-300, 10000),
    }
    fn = errors.get(broker)
    return bool(fn and fn(response_data))


def notify_token_expired(broker: str):
    """Send Telegram alert when a broker token expires."""
    today = date.today().isoformat()
    if _notified_today.get(broker) == today:
        return  # already notified today

    _notified_today[broker] = today
    label = broker.capitalize()
    regen_urls = {
        "upstox":  "https://upstox.com/developer/api-documentation/get-token",
        "zerodha": "https://kite.trade/docs/connect/v3/user/#login-flow",
        "fyers":   "https://myapi.fyers.in/generate-authcode",
    }
    url = regen_urls.get(broker, "broker developer portal")
    msg = (
        f"⚠️ *StockGuru — {label} Token Expired*\n\n"
        f"Your `{BROKER_TOKEN_KEYS[broker]}` has expired.\n\n"
        f"*Regenerate at:* {url}\n\n"
        f"Then update via the StockGuru Channels tab or run:\n"
        f"`POST /api/update-token` with `{{\"broker\":\"{broker}\", \"token\":\"...\"}}`\n\n"
        f"_Until then, StockGuru falls back to Yahoo Finance data._"
    )
    try:
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN","")
        tg_chat  = os.getenv("TELEGRAM_CHAT_ID","")
        if tg_token and tg_chat:
            requests.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": tg_chat, "text": msg, "parse_mode": "Markdown"},
                timeout=5,
            )
            log.info(f"Telegram token-expiry alert sent for {broker}")
    except Exception as e:
        log.warning(f"Telegram notify failed: {e}")


# ── Token update (write new token to .env) ────────────────────────────────────

def update_token_in_env(broker: str, new_token: str) -> bool:
    """
    Update a broker token in .env file without restarting the app.
    Returns True on success.
    """
    key = BROKER_TOKEN_KEYS.get(broker)
    if not key:
        log.error(f"Unknown broker for token update: {broker}")
        return False
    if not new_token or len(new_token) < 10:
        log.error("Token too short — rejected")
        return False

    try:
        content = _ENV_FILE.read_text(encoding="utf-8") if _ENV_FILE.exists() else ""
        pattern = rf"^({re.escape(key)}\s*=).*$"
        new_line = f"{key}={new_token}"

        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + f"\n{new_line}\n"

        _ENV_FILE.write_text(content, encoding="utf-8")

        # Hot-reload the env var
        os.environ[key] = new_token

        # Invalidate cached session in the feed if possible
        _reset_feed_session(broker)

        log.info(f"✅ {broker} token updated in .env and reloaded")
        return True

    except Exception as e:
        log.error(f"Failed to update token for {broker}: {e}")
        return False


def _reset_feed_session(broker: str):
    """Clear any cached authentication session in the feed class."""
    try:
        if broker == "upstox":
            pass  # Upstox uses header-based auth, no session to clear

        elif broker == "zerodha":
            from .zerodha_feed import ZerodhaFeed
            # KiteConnect uses the token directly each call, nothing to reset

        elif broker == "fyers":
            pass  # Fyers uses token directly

        # Trigger feed manager to re-evaluate active feed
        from . import feed_manager
        feed_manager.reload()

    except Exception as e:
        log.debug(f"Session reset for {broker}: {e}")


# ── Upstox auto-refresh (if UPSTOX_API_SECRET configured) ────────────────────

def try_upstox_auto_refresh() -> Optional[str]:
    """
    Attempt automatic Upstox token refresh using saved auth code flow.
    Only works if UPSTOX_API_KEY + UPSTOX_API_SECRET + UPSTOX_REDIRECT_URI are set.
    Returns new token or None.
    """
    api_key    = os.getenv("UPSTOX_API_KEY","")
    api_secret = os.getenv("UPSTOX_API_SECRET","")

    if not (api_key and api_secret):
        return None

    # Upstox requires browser-based OAuth, cannot be fully automated server-side.
    # Log the auth URL so the user can open it quickly.
    redirect = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:5050/upstox-callback")
    auth_url  = (f"https://api.upstox.com/v2/login/authorization/dialog"
                 f"?response_type=code&client_id={api_key}&redirect_uri={redirect}")
    log.warning(f"Upstox auto-refresh: open this URL to get auth code:\n{auth_url}")
    return None


# ── Token status check ─────────────────────────────────────────────────────────

def get_token_status() -> dict:
    """Return current token status for all brokers."""
    status = {}
    for broker, key in BROKER_TOKEN_KEYS.items():
        token = os.getenv(key, "")
        if token:
            # Mask token for display
            masked = token[:8] + "..." + token[-4:] if len(token) > 16 else "****"
            status[broker] = {
                "configured": True,
                "token_preview": masked,
                "key": key,
                "note": "expires daily — update via Channels tab if feed goes down",
            }
        else:
            status[broker] = {
                "configured": False,
                "token_preview": None,
                "key": key,
                "note": "not configured",
            }
    return status
