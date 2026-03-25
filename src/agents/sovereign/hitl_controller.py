# ══════════════════════════════════════════════════════════════════════════════
# StockGuru Sovereign — HITL Controller
# Telegram inline-button approval queue for borderline trades.
#   • Dispatches trade proposals with ✅ APPROVE / ❌ REJECT / ⏩ SKIP buttons
#   • Processes callback_query responses from Flask /api/telegram-update
#   • Auto-expires pending items after 60 min
#   • Auto-executes high-conviction items after 45 min of silence
#   • Pulls pre-trade memory context from memory_engine
# ══════════════════════════════════════════════════════════════════════════════
import json, logging, os, requests
from datetime import datetime, timedelta

log = logging.getLogger("sovereign.hitl")

CONFIG_PATH    = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "sovereign_config.json"))
QUEUE_PATH     = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "hitl_queue.json"))
TELEGRAM_URL   = "https://api.telegram.org/bot{token}/{method}"

_queue_counter = [0]  # rolling ID counter


# ─────────────────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"hitl_expiry_minutes": 60, "hitl_auto_execute_minutes": 45,
                "hitl_auto_execute_min_conviction": 83}


def _load_queue() -> list:
    try:
        with open(QUEUE_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def _save_queue(queue: list):
    try:
        with open(QUEUE_PATH, "w") as f:
            json.dump(queue, f, indent=2, default=str)
    except Exception as e:
        log.error("HITL queue save failed: %s", e)


def _next_id() -> int:
    _queue_counter[0] += 1
    # Also check existing queue for max ID
    q = _load_queue()
    if q:
        existing_max = max((int(item.get("id_num", 0)) for item in q if item.get("id_num")), default=0)
        _queue_counter[0] = max(_queue_counter[0], existing_max + 1)
    return _queue_counter[0]


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_hitl_request(payload: dict, shared_state: dict, send_telegram_fn=None) -> str:
    """
    Add a trade proposal to the HITL queue and send Telegram inline-button message.
    payload: {"signal": {...}, "debate_summary": "...", "soft_veto_flags": [...]}
    Returns queue item ID.
    """
    config = _load_config()
    signal = payload.get("signal") or payload  # support flat or nested

    stock   = signal.get("name", signal.get("stock", "UNKNOWN"))
    sector  = signal.get("sector", "")
    conviction = (signal.get("composite_conviction") or
                  shared_state.get("quant_output", {}).get("conviction_map", {}).get(stock, {}).get("composite", 70))
    gates   = signal.get("gates_passed", 6)
    entry   = signal.get("entry_low") or signal.get("entry_price") or signal.get("cmp", 0)
    t1      = signal.get("target1", 0)
    t2      = signal.get("target2", 0)
    sl      = signal.get("stop_loss", 0)
    rr      = signal.get("rr_t2") or signal.get("rr_t1", 2.0)
    shares  = signal.get("risk", {}).get("position_size", 0) if isinstance(signal.get("risk"), dict) else 0
    capital = shared_state.get("paper_portfolio", {}).get("capital", 100000) if isinstance(shared_state.get("paper_portfolio"), dict) else 100000
    risk_pct = signal.get("risk", {}).get("actual_risk_pct", 1.0) if isinstance(signal.get("risk"), dict) else 1.0
    risk_amt = int(capital * risk_pct / 100)

    # Pre-trade memory context
    from src.agents.sovereign import memory_engine
    memory_ctx = memory_engine.format_memory_context(stock)

    # Soft veto flags
    rm_out = shared_state.get("risk_master_output", {})
    veto_flags = []
    for item in rm_out.get("soft_veto_flags", []):
        if item.get("name") == stock:
            veto_flags = item.get("flags", [])
            break

    # Debate summary (if came from debate engine)
    debate_summary = payload.get("debate_summary") or payload.get("resolution", {}).get("debate_summary", "")

    # Quant thesis
    quant_thesis = ""
    for setup in shared_state.get("quant_output", {}).get("overreaction_setups", []):
        if setup.get("name") == stock:
            quant_thesis = setup.get("quant_thesis", "")
            break
    if not quant_thesis:
        quant_thesis = signal.get("rationale", [""])[0] if signal.get("rationale") else ""

    item_id = _next_id()
    now = datetime.now()
    expiry_min = config.get("hitl_expiry_minutes", 60)
    expires_at = (now + timedelta(minutes=expiry_min)).isoformat()

    item = {
        "id":                  f"HITL_{stock.replace(' ', '_')}_{now.strftime('%Y%m%d_%H%M')}",
        "id_num":              item_id,
        "stock":               stock,
        "sector":              sector,
        "composite_conviction": round(float(conviction), 1),
        "entry_price":         entry,
        "target1":             t1,
        "target2":             t2,
        "stop_loss":           sl,
        "rr_ratio":            rr,
        "gates_passed":        gates,
        "shares":              shares,
        "risk_pct":            risk_pct,
        "risk_amount":         risk_amt,
        "quant_thesis":        quant_thesis,
        "debate_summary":      debate_summary,
        "soft_veto_flags":     veto_flags,
        "memory_context":      memory_ctx,
        "source":              "DEBATE" if debate_summary else "QUANT",
        "status":              "PENDING",
        "created_at":          now.isoformat(),
        "expires_at":          expires_at,
        "telegram_message_id": None,
        "response":            None,
        "responded_at":        None
    }

    # Append to queue
    queue = _load_queue()
    # Deduplicate: skip if same stock already PENDING
    if any(q["stock"] == stock and q["status"] == "PENDING" for q in queue):
        log.info("HITL: Skipping duplicate pending request for %s", stock)
        return item["id"]

    queue.append(item)
    _save_queue(queue)
    log.info("📬 HITL queued: %s [#%d] conviction=%.0f%%", stock, item_id, conviction)

    # Send Telegram inline-button message
    msg_id = _send_telegram_proposal(item)
    if msg_id:
        # Update message_id in queue
        queue[-1]["telegram_message_id"] = msg_id
        _save_queue(queue)

    return item["id"]


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM MESSAGING
# ─────────────────────────────────────────────────────────────────────────────

def _send_telegram_proposal(item: dict) -> int | None:
    """
    Send HITL proposal to Telegram with inline ✅ APPROVE / ❌ REJECT / ⏩ SKIP buttons.
    Returns Telegram message_id or None on failure.
    """
    token   = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("HITL: Telegram not configured — skipping message send")
        return None

    num = item["id_num"]
    msg = _format_hitl_message(item)

    payload = {
        "chat_id":    chat_id,
        "text":       msg,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps({
            "inline_keyboard": [[
                {"text": "✅ APPROVE",   "callback_data": f"approve_{num}"},
                {"text": "❌ REJECT",    "callback_data": f"reject_{num}"},
                {"text": "⏩ SKIP+1",   "callback_data": f"skip_{num}"}
            ]]
        })
    }

    try:
        url = TELEGRAM_URL.format(token=token, method="sendMessage")
        resp = requests.post(url, data={
            "chat_id":    payload["chat_id"],
            "text":       payload["text"],
            "parse_mode": payload["parse_mode"],
            "reply_markup": payload["reply_markup"]
        }, timeout=8)
        data = resp.json()
        if data.get("ok"):
            msg_id = data["result"]["message_id"]
            log.info("📤 HITL Telegram sent: %s [msg_id=%d]", item["stock"], msg_id)
            return msg_id
        else:
            log.error("HITL Telegram error: %s", data.get("description"))
    except Exception as e:
        log.error("HITL Telegram send failed: %s", e)
    return None


def _format_hitl_message(item: dict) -> str:
    """Build the Telegram message text for a HITL proposal."""
    stock   = item["stock"]
    sector  = item["sector"]
    num     = item["id_num"]
    conv    = item["composite_conviction"]
    entry   = item["entry_price"]
    t1      = item["target1"]
    t2      = item["target2"]
    sl      = item["stop_loss"]
    rr      = item["rr_ratio"]
    gates   = item["gates_passed"]
    risk_pct= item["risk_pct"]
    risk_amt= item["risk_amount"]
    def _sanitize(txt: str) -> str:
        return str(txt).replace("_", " ").replace("*", "").replace("`", "").replace("[", "").replace("]", "")

    thesis_san = _sanitize(thesis)
    memory_san = _sanitize(memory)
    debate_san = _sanitize(debate)
    sector_san = _sanitize(sector)

    lines = [
        f"🤖 *TRADE PROPOSAL {num}*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 *{stock}* ({sector_san}) | Conviction: *{conv:.0f}%*",
        f"Gates: {gates}/8 | R:R = {rr:.1f}x",
        "",
        f"Entry: ₹{entry:,.0f} | T1: ₹{t1:,.0f} | T2: ₹{t2:,.0f} | SL: ₹{sl:,.0f}",
        f"Risk: {risk_pct:.1f}% of capital (~₹{risk_amt:,})",
        "",
        f"🧠 Quant: _{thesis_san}_",
    ]

    if flags:
        flag_san = _sanitize(flags[0])
        lines.append(f"⚠️  Flag: {flag_san}")

    if debate_san:
        lines.append(f"🎭 Debate: _{debate_san[:60]}_")

    lines += [
        f"💭 Memory: _{memory_san}_",
        "",
        f"⏰ Expires in {expiry} min",
        "_Paper simulation only — not SEBI advice._"
    ]
    return "\n".join(lines)


def _answer_callback(callback_query_id: str, text: str):
    """Dismiss the Telegram 'loading' spinner after button press."""
    token = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        return
    try:
        requests.post(
            TELEGRAM_URL.format(token=token, method="answerCallbackQuery"),
            data={"callback_query_id": callback_query_id, "text": text},
            timeout=5
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK PROCESSING (called by Flask /api/telegram-update)
# ─────────────────────────────────────────────────────────────────────────────

def process_telegram_update(update: dict, shared_state: dict, send_telegram_fn=None) -> str:
    """
    Process incoming Telegram update dict.
    Handles: callback_query (button press) and message (text command fallback).
    Returns status string.
    """
    # ── Inline button callback ─────────────────────────────────────────────
    cq = update.get("callback_query")
    if cq:
        data      = cq.get("data", "")
        cq_id     = cq.get("id", "")
        user_name = cq.get("from", {}).get("first_name", "User")
        result    = _process_callback(data, shared_state, send_telegram_fn)
        _answer_callback(cq_id, result)
        return result

    # ── Text message fallback (/approve_47 style) ──────────────────────────
    msg = update.get("message", {})
    text = msg.get("text", "").strip().lower()
    if text.startswith("/approve_") or text.startswith("/reject_") or text.startswith("/skip_"):
        return _process_callback(text.lstrip("/"), shared_state, send_telegram_fn)
    if text == "/status":
        return _send_queue_status(send_telegram_fn)
    if text == "/veto":
        return _manual_veto(shared_state, send_telegram_fn)

    return "unhandled"


def _process_callback(data: str, shared_state: dict, send_telegram_fn) -> str:
    """Parse callback_data and execute the corresponding action."""
    parts = data.split("_", 1)
    if len(parts) != 2:
        return "invalid"

    action, id_str = parts[0], parts[1]
    try:
        item_id = int(id_str)
    except ValueError:
        return "invalid_id"

    queue = _load_queue()
    item  = next((q for q in queue if q.get("id_num") == item_id and q["status"] == "PENDING"), None)

    if not item:
        return f"Item #{item_id} not found or already processed"

    now = datetime.now().isoformat()

    if action == "approve":
        item["status"]       = "APPROVED"
        item["response"]     = "APPROVE"
        item["responded_at"] = now
        _save_queue(queue)
        _execute_approved_trade(item, shared_state)
        msg = f"✅ Trade APPROVED: {item['stock']} — paper order placed!"
        if send_telegram_fn:
            send_telegram_fn(msg)
        log.info("✅ HITL APPROVED: %s [#%d]", item["stock"], item_id)
        return "approved"

    elif action == "reject":
        item["status"]       = "REJECTED"
        item["response"]     = "REJECT"
        item["responded_at"] = now
        _save_queue(queue)
        msg = f"❌ Trade REJECTED: {item['stock']} — skipped this cycle."
        if send_telegram_fn:
            send_telegram_fn(msg)
        log.info("❌ HITL REJECTED: %s [#%d]", item["stock"], item_id)
        return "rejected"

    elif action == "skip":
        item["status"]       = "DEFERRED"
        item["response"]     = "SKIP"
        item["responded_at"] = now
        # Reduce conviction by 3 in shared_state so it doesn't auto-fire next cycle
        conv_map = shared_state.get("quant_output", {}).get("conviction_map", {})
        if item["stock"] in conv_map:
            conv_map[item["stock"]]["composite"] -= 3
        _save_queue(queue)
        msg = f"⏩ Trade DEFERRED: {item['stock']} — skipping +1 cycle."
        if send_telegram_fn:
            send_telegram_fn(msg)
        log.info("⏩ HITL DEFERRED: %s [#%d]", item["stock"], item_id)
        return "deferred"

    return "unknown_action"


def _execute_approved_trade(item: dict, shared_state: dict):
    """Call paper_trader to enter the approved position."""
    try:
        import sys, os
        agents_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "agents"))
        if agents_path not in sys.path:
            sys.path.insert(0, agents_path)
        from src.agents import paper_trader

        # Build a signal-like dict for paper_trader
        signal = {
            "name":        item["stock"],
            "sector":      item["sector"],
            "score":       int(item["composite_conviction"]),
            "signal":      "STRONG BUY",
            "cmp":         item["entry_price"],
            "entry_low":   item["entry_price"],
            "entry_high":  item["entry_price"] * 1.002,
            "target1":     item["target1"],
            "target2":     item["target2"],
            "stop_loss":   item["stop_loss"],
            "rr_t1":       item["rr_ratio"],
            "rr_t2":       item["rr_ratio"],
            "confidence":  "HIGH",
            "rationale":   [item["quant_thesis"]],
            "hitl_approved": True,
            "hitl_id":     item["id"]
        }

        gate_detail = {k: True for k in ["score_gate", "rsi_gate", "volume_gate",
                                           "trend_gate", "macd_gate", "news_gate",
                                           "fii_gate", "options_gate"]}
        paper_trader._enter_position(signal, 7, gate_detail,
                                     shared_state.get("paper_portfolio", {}),
                                     shared_state.get("_price_cache", {}),
                                     shared_state)
        log.info("📈 Paper position entered for HITL-approved: %s", item["stock"])
    except Exception as e:
        log.error("HITL execute trade failed for %s: %s", item["stock"], e)


# ─────────────────────────────────────────────────────────────────────────────
# QUEUE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def check_queue_expiry(shared_state: dict, send_telegram_fn=None):
    """
    Called every 15-min cycle.
    - Expire items past expiry_at → status=EXPIRED
    - Auto-execute items past auto_execute_minutes if high-conviction
    """
    config       = _load_config()
    auto_min     = config.get("hitl_auto_execute_minutes", 45)
    auto_conv    = config.get("hitl_auto_execute_min_conviction", 83)
    queue        = _load_queue()
    now          = datetime.now()
    changed      = False

    for item in queue:
        if item["status"] != "PENDING":
            continue

        created_at = datetime.fromisoformat(item["created_at"])
        expires_at = datetime.fromisoformat(item["expires_at"])
        age_minutes = (now - created_at).total_seconds() / 60

        # Auto-execute high-conviction items after silence
        if (age_minutes >= auto_min and
                item["composite_conviction"] >= auto_conv and
                _get_vix(shared_state) < 16):
            item["status"]       = "AUTO_EXECUTED"
            item["response"]     = "AUTO"
            item["responded_at"] = now.isoformat()
            _execute_approved_trade(item, shared_state)
            if send_telegram_fn:
                send_telegram_fn(
                    f"⏰ *AUTO-EXECUTED* (no response {auto_min} min): "
                    f"{item['stock']} — conviction {item['composite_conviction']:.0f}% | VIX safe"
                )
            log.info("⏰ HITL auto-executed: %s", item["stock"])
            changed = True

        # Expire items past expiry
        elif now >= expires_at:
            item["status"]       = "EXPIRED"
            item["response"]     = "TIMEOUT"
            item["responded_at"] = now.isoformat()
            log.info("⌛ HITL expired: %s", item["stock"])
            changed = True

    if changed:
        _save_queue(queue)

    # Update shared_state summary
    pending = [q for q in queue if q["status"] == "PENDING"]
    oldest_age = 0
    if pending:
        oldest = min(pending, key=lambda x: x["created_at"])
        oldest_age = round((now - datetime.fromisoformat(oldest["created_at"])).total_seconds() / 60)

    today_str = now.date().isoformat()
    shared_state["hitl_queue_summary"] = {
        "pending_count":     len(pending),
        "oldest_pending_min": oldest_age,
        "approved_today":    sum(1 for q in queue if q["status"] == "APPROVED" and q.get("responded_at", "")[:10] == today_str),
        "rejected_today":    sum(1 for q in queue if q["status"] == "REJECTED" and q.get("responded_at", "")[:10] == today_str),
        "total_items":       len(queue)
    }
    return pending


def _send_queue_status(send_telegram_fn) -> str:
    """Send current queue status via Telegram."""
    queue   = _load_queue()
    pending = [q for q in queue if q["status"] == "PENDING"]
    if not pending:
        msg = "📋 HITL Queue: Empty — no pending approvals"
    else:
        lines = [f"📋 HITL Queue: {len(pending)} pending"]
        for item in pending[:5]:
            lines.append(f"  #{item['id_num']} {item['stock']} ({item['composite_conviction']:.0f}%)")
        msg = "\n".join(lines)
    if send_telegram_fn:
        send_telegram_fn(msg)
    return "status_sent"


def _manual_veto(shared_state: dict, send_telegram_fn) -> str:
    """Human-triggered hard veto: reject all pending HITL items."""
    queue = _load_queue()
    count = 0
    for item in queue:
        if item["status"] == "PENDING":
            item["status"]       = "REJECTED"
            item["response"]     = "MANUAL_VETO"
            item["responded_at"] = datetime.now().isoformat()
            count += 1
    _save_queue(queue)
    msg = f"🛑 Manual VETO: {count} pending trades rejected."
    if send_telegram_fn:
        send_telegram_fn(msg)
    log.info("Manual VETO: %d trades rejected", count)
    return "vetoed"


def _get_vix(shared_state: dict) -> float:
    for k, v in shared_state.get("index_prices", {}).items():
        if "VIX" in k.upper():
            return float(v.get("price", 0)) if isinstance(v, dict) else float(v or 0)
    return float(shared_state.get("india_vix", 0) or 0)


def get_queue_for_api() -> list:
    """Return full queue for /api/hitl-queue endpoint."""
    return _load_queue()
