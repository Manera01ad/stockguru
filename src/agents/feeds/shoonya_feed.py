"""
Shoonya (Finvasia) Feed — WebSocket + REST  [FREE]
Requires: SHOONYA_USER, SHOONYA_PASSWORD, SHOONYA_API_KEY, SHOONYA_TOTP_KEY
pip install NorenRestApiPy pyotp

Full DOM (order book depth), ~200ms latency. Completely free for Shoonya customers.

Symbol resolution:
  - Indices / MCX / CDS → looked up in _SYM_MAP (exchange, tsym)
  - NSE equities → strip .NS suffix, append -EQ  (e.g. BHARTIARTL.NS → NSE:BHARTIARTL-EQ)
  - All symbols resolved to Shoonya numeric token via SearchScrip (cached in-memory)
"""
import os
import time
import logging
import requests
from datetime import datetime, timedelta
from .base import DataFeed

log = logging.getLogger("shoonya_feed")


class ShoonyaFeed(DataFeed):
    NAME         = "shoonya"
    LABEL        = "Shoonya (Finvasia)"
    REQUIRED_ENV = ["SHOONYA_USER", "SHOONYA_PASSWORD", "SHOONYA_API_KEY", "SHOONYA_TOTP_KEY"]
    LATENCY_MS   = 200
    OB_LEVELS    = 5
    IS_REALTIME  = True

    BASE     = "https://api.shoonya.com/NorenWClientTP"
    _session = None
    _token_cache: dict = {}   # class-level cache: (EXCHANGE, TSYM) → "token_str"

    # ── Auth error tracking (class-level so all instances share it) ───────────
    _auth_error:     str   = ""        # last auth failure message
    _auth_failed_at: float = 0.0       # epoch when last failure occurred
    _AUTH_RETRY_SEC: int   = 300       # retry login no sooner than 5 min after failure

    # ── Public connection test ────────────────────────────────────────────────
    @classmethod
    def test_connection(cls) -> dict:
        """
        Explicitly test Shoonya login. Returns a dict with:
          ok (bool), message (str), user (str), totp_ok (bool), error (str)
        Call via GET /api/shoonya-test
        """
        result = {"ok": False, "user": os.getenv("SHOONYA_USER","?"),
                  "totp_ok": False, "error": "", "message": ""}
        # 1. Check env vars
        missing = [k for k in ["SHOONYA_USER","SHOONYA_PASSWORD","SHOONYA_API_KEY","SHOONYA_TOTP_KEY"]
                   if not os.getenv(k,"").strip()]
        if missing:
            result["error"] = f"Missing env vars: {', '.join(missing)}"
            result["message"] = "❌ Shoonya credentials not configured"
            return result

        # 2. Test TOTP generation
        try:
            import pyotp
            totp_secret = os.getenv("SHOONYA_TOTP_KEY","").replace(" ","")
            totp = pyotp.TOTP(totp_secret).now()
            result["totp_ok"] = True
            log.debug(f"Shoonya TOTP generated OK: {totp}")
        except Exception as e:
            result["error"] = f"TOTP generation failed: {e}"
            result["message"] = (
                "❌ TOTP key invalid. Open Google Authenticator, tap the ⋮ menu "
                "→ Export accounts → scan the QR code, and copy the exact base32 secret "
                "into SHOONYA_TOTP_KEY in your .env file."
            )
            return result

        # 3. Test login
        try:
            cls._session = None          # force fresh login
            cls._auth_failed_at = 0.0
            cls._auth_error = ""
            session_token = cls()._get_session()
            if session_token:
                result["ok"] = True
                result["message"] = f"✅ Shoonya connected — user {result['user']}"
                log.info("Shoonya test_connection: SUCCESS for %s", result["user"])
            else:
                result["error"] = "Login returned empty token"
                result["message"] = "❌ Shoonya login returned no session token"
        except Exception as e:
            cls._session = None
            result["error"] = str(e)
            # Give the user an actionable fix message
            err = str(e).lower()
            if "invalid totp" in err or "totp" in err or "base32" in err:
                result["message"] = (
                    "❌ TOTP failed. Your SHOONYA_TOTP_KEY is wrong or your server clock "
                    "is off. Rescan the QR code in Shoonya API settings and update .env."
                )
            elif "password" in err or "auth" in err or "invalid" in err:
                result["message"] = (
                    "❌ Authentication failed. Check SHOONYA_USER and SHOONYA_PASSWORD. "
                    "Password is case-sensitive."
                )
            elif "vendor" in err or "vc" in err:
                result["message"] = (
                    "❌ Vendor code mismatch. Set SHOONYA_VENDOR_CODE in .env. "
                    "You can find this in Shoonya API Manager → App Details."
                )
            elif "connection" in err or "timeout" in err or "network" in err:
                result["message"] = "❌ Network error — could not reach api.shoonya.com. Check your internet connection."
            elif "2fa" in err or "totp" in err:
                result["message"] = "❌ 2FA/TOTP failure. Verify your SHOONYA_TOTP_KEY (base32 secret from QR code) and server time."
            else:
                result["message"] = f"❌ Login error: {e}"
        return result

    # ── Direct yahoo→shoonya symbol map for non-equity instruments ────────────
    # Shoonya tsym values: exactly as they appear in the scrip master / SearchScrip
    _SYM_MAP = {
        # NSE Indices
        "^NSEI":     ("NSE", "Nifty 50"),
        "^NSEBANK":  ("NSE", "Nifty Bank"),
        "^INDIAVIX": ("NSE", "India VIX"),
        # Sector Indices
        "^CNXFIN":      ("NSE", "Finnifty"),
        "^CNXMIDCAP":   ("NSE", "Midcpnifty"),
        "^CNXJUNIOR":   ("NSE", "Nifty Next 50"),
        "^CNXIT":       ("NSE", "Nifty IT"),
        "^CNXMETAL":    ("NSE", "Nifty Metal"),
        "^CNXPHARMA":   ("NSE", "Nifty Pharma"),
        "^CNXAUTO":     ("NSE", "Nifty Auto"),
        "^CNXFMCG":     ("NSE", "Nifty FMCG"),
        "^CNXREALTY":    ("NSE", "Nifty Realty"),
        "^CNXENERGY":   ("NSE", "Nifty Energy"),
        # BSE Index
        "^BSESN":    ("BSE", "SENSEX"),
        # MCX Commodities
        "GC=F":      ("MCX", "GOLD"),
        "SI=F":      ("MCX", "SILVER"),
        "CL=F":      ("MCX", "CRUDEOIL"),
        "NG=F":      ("MCX", "NATURALGAS"),
        # Currency Derivatives
        "INR=X":     ("CDS", "USDINR"),
    }

    # ── Symbol helpers ────────────────────────────────────────────────────────

    def _to_shoonya_sym(self, yahoo_sym: str):
        """
        Convert a Yahoo Finance symbol to a Shoonya (exchange, tsym) tuple.
        - Symbols in _SYM_MAP are returned directly.
        - NSE equities (ending in .NS) → (NSE, SYMBOL-EQ)
        - BSE equities (ending in .BO) → (BSE, SYMBOL-BE)
        """
        if yahoo_sym in self._SYM_MAP:
            return self._SYM_MAP[yahoo_sym]

        # Explicitly reject Crypto pairs so they trigger Yahoo fallback instantly
        if "-USD" in yahoo_sym or "-INR" in yahoo_sym:
            raise ValueError(f"Crypto not supported by Shoonya: {yahoo_sym}")

        clean = self._strip_suffix(yahoo_sym)

        if self._is_bse(yahoo_sym):
            return ("BSE", f"{clean}-BE")

        # Default: NSE equity
        return ("NSE", f"{clean}-EQ")

    def _resolve_token(self, exchange: str, tsym: str) -> str:
        """
        Resolve (exchange, tsym) → Shoonya numeric token string.
        Uses SearchScrip API with in-memory caching.
        Falls back to tsym as-is if lookup fails (allows partial functionality).
        """
        cache_key = (exchange.upper(), tsym.upper())
        if cache_key in ShoonyaFeed._token_cache:
            return ShoonyaFeed._token_cache[cache_key]

        try:
            # Derive a good search text:
            # "BHARTIARTL-EQ" → search "BHARTIARTL"
            # "Nifty 50"      → search "Nifty 50"
            # "GOLD"          → search "GOLD"
            search_text = tsym.split("-")[0] if "-" in tsym and tsym.endswith(("-EQ", "-BE", "-F", "-GR")) else tsym

            result = self._post("SearchScrip", {"exch": exchange, "stext": search_text})

            # SearchScrip can return a list directly or {"values": [...]}
            scrips = result if isinstance(result, list) else result.get("values", [])

            # 1st pass: exact tsym + exchange match
            for s in scrips:
                if (s.get("tsym", "").upper() == tsym.upper() and
                        s.get("exch", "").upper() == exchange.upper()):
                    token = str(s.get("token", "")).strip()
                    if token:
                        ShoonyaFeed._token_cache[cache_key] = token
                        log.debug(f"✅ Shoonya token resolved: {exchange}:{tsym} → {token}")
                        return token

            # 2nd pass: first result matching the exchange
            for s in scrips:
                if s.get("exch", "").upper() == exchange.upper():
                    token = str(s.get("token", "")).strip()
                    if token:
                        ShoonyaFeed._token_cache[cache_key] = token
                        log.debug(f"⚠️  Shoonya token (fuzzy): {exchange}:{tsym} → {token} ({s.get('tsym')})")
                        return token

        except Exception as e:
            log.debug(f"SearchScrip failed for {exchange}:{tsym}: {e}")

        # Last resort: pass tsym as token — Shoonya will return an error which
        # triggers Yahoo fallback in fetch_all_prices()
        log.debug(f"Could not resolve Shoonya token for {exchange}:{tsym}, using name as-is")
        return tsym

    # ── Session / HTTP ────────────────────────────────────────────────────────

    def _get_session(self):
        if ShoonyaFeed._session:
            return ShoonyaFeed._session

        # Don't hammer Shoonya API — wait _AUTH_RETRY_SEC after a failure
        if ShoonyaFeed._auth_error and ShoonyaFeed._auth_failed_at:
            age = time.time() - ShoonyaFeed._auth_failed_at
            if age < ShoonyaFeed._AUTH_RETRY_SEC:
                raise ConnectionError(
                    f"Shoonya auth previously failed ({ShoonyaFeed._auth_error}). "
                    f"Retrying in {int(ShoonyaFeed._AUTH_RETRY_SEC - age)}s. "
                    f"Run GET /api/shoonya-test to debug or update credentials."
                )

        try:
            import pyotp
            from NorenRestApiPy.NorenApi import NorenApi as _NorenApi

            totp_secret = os.getenv("SHOONYA_TOTP_KEY", "").replace(" ", "")
            try:
                totp = pyotp.TOTP(totp_secret).now()
            except Exception as e:
                raise ValueError(f"Invalid TOTP Secret (must be base32): {e}")

            uid      = os.getenv("SHOONYA_USER", "")
            pwd      = os.getenv("SHOONYA_PASSWORD", "")
            api_key  = os.getenv("SHOONYA_API_KEY", "")
            # vendor_code: set SHOONYA_VENDOR_CODE in .env if your app's vc differs
            # If not set, Shoonya convention is uid + "_U" BUT only when uid doesn't already end in _U
            vc = os.getenv("SHOONYA_VENDOR_CODE", "")
            if not vc:
                vc = uid if uid.endswith("_U") else uid + "_U"


            class _Api(_NorenApi):
                def __init__(self):
                    super().__init__(
                        host="https://api.shoonya.com/NorenWClientTP",
                        websocket="wss://api.shoonya.com/NorenWSTP/"
                    )

            api = _Api()
            ret = api.login(userid=uid, password=pwd, twoFA=totp,
                            vendor_code=vc, api_secret=api_key, imei="abc1234")
            if ret is not None and ret.get("stat") == "Ok":
                session = ret.get("susertoken")
                ShoonyaFeed._session = session
                ShoonyaFeed._noren_api   = api
                ShoonyaFeed._auth_error = ""
                ShoonyaFeed._auth_failed_at = 0.0
                log.info("✅ Shoonya login SUCCESS total OK for user %s", uid)
                return session
            else:
                msg = ret.get("emsg", "Unknown Shoonya error") if ret else "Login returned empty response"
                raise ConnectionError(msg)
        except ImportError:
            raise ImportError("Run: pip install NorenRestApiPy pyotp")
        except Exception as e:
            # Cache the failure so we don't retry for _AUTH_RETRY_SEC
            ShoonyaFeed._auth_error    = str(e)
            ShoonyaFeed._auth_failed_at = time.time()
            ShoonyaFeed._session       = None
            log.warning("⚠️ Shoonya login FAILED for %s: %s", os.getenv("SHOONYA_USER","?"), e)
            log.warning("⚠️ Shoonya falling back to Yahoo Finance. Run GET /api/shoonya-test to debug.")
            raise



    def _post(self, endpoint: str, jdata: dict) -> dict:
        import json
        session = self._get_session()
        payload = {"jData": json.dumps({
            **jdata,
            "uid":         os.getenv("SHOONYA_USER"),
            "actid":       os.getenv("SHOONYA_USER"),
            "susertoken":  session,
        })}
        r = requests.post(f"{self.BASE}/{endpoint}", data=payload, timeout=8)
        return r.json()

    # ── Core data methods ─────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> dict:
        try:
            exchange, tsym = self._to_shoonya_sym(symbol)
            token = self._resolve_token(exchange, tsym)
            data = self._post("GetQuotes", {"exch": exchange, "token": token})
            if data.get("stat") != "Ok":
                raise ValueError(data.get("emsg", "Shoonya quote error"))
            curr = float(data.get("lp", 0))
            prev = float(data.get("c",  curr) or curr)
            return {
                "price":      round(curr, 4),
                "prev_close": round(prev, 4),
                "change_pct": round(((curr - prev) / prev) * 100, 2) if prev else 0,
                "day_high":   float(data.get("h",  curr)),
                "day_low":    float(data.get("l",  curr)),
                "volume":     int(data.get("v", 0)),
                "currency":   "INR",
                "name":       data.get("cname", symbol),
            }
        except Exception as e:
            return {"price": 0, "error": str(e)}

    def get_orderbook(self, symbol: str, depth: int = 5) -> dict:
        try:
            exchange, tsym = self._to_shoonya_sym(symbol)
            token = self._resolve_token(exchange, tsym)
            data = self._post("GetQuotes", {"exch": exchange, "token": token})
            if data.get("stat") != "Ok":
                raise ValueError(data.get("emsg", ""))
            price = float(data.get("lp", 0))

            bids, asks  = [], []
            cum_b = cum_a = 0
            for i in range(1, 6):    # Shoonya returns bp1..bp5, bq1..bq5
                bp = float(data.get(f"bp{i}", 0) or 0)
                bq = int(data.get(f"bq{i}",   0) or 0)
                sp = float(data.get(f"sp{i}", 0) or 0)
                sq = int(data.get(f"sq{i}",   0) or 0)
                if bp: cum_b += bq; bids.append({"price": bp, "qty": bq, "total": cum_b})
                if sp: cum_a += sq; asks.append({"price": sp, "qty": sq, "total": cum_a})

            best_bid = bids[0]["price"] if bids else 0
            best_ask = asks[0]["price"] if asks else 0
            spread   = round(best_ask - best_bid, 4) if (best_bid and best_ask) else 0
            total    = cum_b + cum_a
            return {
                "bids": bids, "asks": asks,
                "spread": spread,
                "best_bid": best_bid, "best_ask": best_ask,
                "buy_pct":  round(cum_b / total * 100) if total else 50,
                "sell_pct": round(cum_a / total * 100) if total else 50,
                "price": price, "note": "live",
            }
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_orderbook(symbol, depth)

    def get_candles(self, symbol: str, interval: str, range_: str) -> dict:
        try:
            exchange, tsym = self._to_shoonya_sym(symbol)
            token = self._resolve_token(exchange, tsym)
            days    = {"1d":1,"5d":5,"1mo":30,"3mo":90,"6mo":180,"1y":365}.get(range_, 5)
            end_dt  = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            start_dt= (datetime.now() - timedelta(days=days)).strftime("%d-%m-%Y %H:%M:%S")
            tf_secs = {"1m":60,"5m":300,"15m":900,"30m":1800,"60m":3600,"1h":3600,"1d":86400}.get(interval, 900)

            data = self._post("TPSeries", {
                "exch":  exchange,
                "token": token,
                "st":    start_dt,
                "et":    end_dt,
                "intrv": str(tf_secs),
            })
            candles = []
            for row in (data if isinstance(data, list) else []):
                try:
                    ts = int(datetime.strptime(row["time"], "%d-%m-%Y %H:%M:%S").timestamp())
                    candles.append({
                        "time":   ts,
                        "open":   round(float(row.get("into", 0)), 4),
                        "high":   round(float(row.get("inth", 0)), 4),
                        "low":    round(float(row.get("intl", 0)), 4),
                        "close":  round(float(row.get("intc", 0)), 4),
                        "volume": int(row.get("intv", 0)),
                    })
                except Exception:
                    continue
            candles.sort(key=lambda x: x["time"])
            q = self.get_quote(symbol)
            return {
                "candles":  candles,
                "symbol":   symbol,
                "name":     symbol,
                "currency": "INR",
                **{k: q.get(k, 0) for k in ("price","prev_close","change_pct","day_high","day_low","volume")},
                "interval": interval,
                "range":    range_,
            }
        except Exception as e:
            from .yahoo_feed import YahooFeed
            return YahooFeed().get_candles(symbol, interval, range_)
