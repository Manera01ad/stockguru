# ══════════════════════════════════════════════════════════════════════════════
# StockGuru — Builder Agent (Phase 2)
# Proposes new dashboard panels via Telegram APPROVE/REJECT.
# On APPROVE: auto-patches static/index.html by injecting HTML into
# <div id="builder-extensions"> between <!-- BUILDER_START --> / <!-- BUILDER_END -->.
# All generated JS references ONLY existing Flask routes — no new routes needed.
# Telegram callback prefix: "bld_" (distinct from HITL "approve_/reject_").
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import logging
import uuid
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

_DATA_DIR     = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
_PROPOSALS_FILE = os.path.join(_DATA_DIR, "builder_proposals.json")
_INDEX_HTML     = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "static", "index.html")
)
_MAX_PROPOSALS = 50
_EXPIRY_HOURS  = 24

# Available proposal templates (Builder picks the most relevant)
_TEMPLATES = [
    "oi_heatmap_chart",
    "promoter_holding_table",
    "block_deals_feed",
    "backtest_probability_gauge",
    "memory_lessons_timeline",
    "scryer_delta_chart",
]


# ─── Public entry point ────────────────────────────────────────────────────────

def run(shared_state: dict, send_telegram_fn) -> dict:
    """
    Daily entry point. Selects the best proposal template, generates HTML,
    sends Telegram inline message. Fails gracefully.
    """
    log.info("Builder Agent: daily run starting")

    # Expire any old PENDING proposals first
    _expire_old_proposals()

    # Pick the best template based on available data
    template = _select_best_proposal(shared_state)
    if not template:
        log.info("Builder Agent: no suitable template — skipping")
        return {"status": "skipped", "reason": "no template selected"}

    # Generate the HTML/JS panel code via LLM
    try:
        html_code, title, why = _generate_panel_code(template, shared_state)
    except Exception as e:
        log.warning(f"Builder Agent: code generation failed: {e}")
        return {"status": "error", "error": str(e)}

    # Create proposal record
    proposal_id = f"BLD_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:4].upper()}"
    proposal = {
        "id":          proposal_id,
        "template":    template,
        "title":       title,
        "why":         why,
        "data_source": "/api/observer-data",
        "html_code":   html_code,
        "status":      "PENDING",
        "created_at":  datetime.now().isoformat(),
        "expires_at":  (datetime.now() + timedelta(hours=_EXPIRY_HOURS)).isoformat(),
        "applied_at":  None,
        "lines":       len(html_code.splitlines()),
    }

    # Save proposal
    _save_proposal(proposal)

    # Send Telegram inline keyboard
    try:
        _send_builder_proposal(proposal, send_telegram_fn)
    except Exception as e:
        log.warning(f"Builder Agent: Telegram send failed: {e}")

    out = {"status": "proposed", "id": proposal_id, "template": template, "title": title}
    shared_state["builder_output"] = out
    log.info(f"Builder Agent: proposal sent — {proposal_id} ({template})")
    return out


def process_callback(callback_data: str, update: dict, send_telegram_fn) -> str:
    """
    Handle Telegram callback: bld_approve_ID / bld_reject_ID / bld_expire_ID.
    Called from hitl_controller.process_telegram_update() when prefix is "bld_".
    Returns status string for logging.
    """
    try:
        # Answer callback query to remove Telegram spinner
        cq = update.get("callback_query", {})
        cq_id = cq.get("id")
        if cq_id:
            _answer_callback(cq_id, "Processing...")

        parts = callback_data.split("_", 2)  # e.g. ["bld", "approve", "BLD_20260228_..."]
        if len(parts) < 3:
            return "invalid_callback"

        action      = parts[1]  # approve / reject
        proposal_id = parts[2]

        proposals = _load_proposals()
        proposal  = next((p for p in proposals if p["id"] == proposal_id), None)

        if not proposal:
            if send_telegram_fn:
                send_telegram_fn(f"⚠️ Builder: proposal {proposal_id} not found.")
            return "proposal_not_found"

        if proposal["status"] != "PENDING":
            if send_telegram_fn:
                send_telegram_fn(f"ℹ️ Builder: proposal already {proposal['status']}.")
            return "already_handled"

        if action == "approve":
            success = _apply_patch(proposal)
            if success:
                proposal["status"]    = "APPLIED"
                proposal["applied_at"] = datetime.now().isoformat()
                _update_proposal(proposals, proposal)
                if send_telegram_fn:
                    send_telegram_fn(
                        f"✅ *Builder: Panel Applied!*\n"
                        f"_{proposal['title']}_ is now live.\n"
                        f"Reload the dashboard to see it."
                    )
                return "applied"
            else:
                if send_telegram_fn:
                    send_telegram_fn(f"❌ Builder: failed to patch index.html. Check logs.")
                return "patch_failed"

        elif action == "reject":
            proposal["status"] = "REJECTED"
            _update_proposal(proposals, proposal)
            if send_telegram_fn:
                send_telegram_fn(f"❌ Builder: proposal *{proposal['title']}* rejected.")
            return "rejected"

    except Exception as e:
        log.error(f"Builder callback error: {e}")
        return f"error: {e}"

    return "unknown_action"


def get_proposals_for_api() -> list:
    """Return all proposals (for /api/builder-proposals)."""
    return _load_proposals()


# ─── Template Selection ───────────────────────────────────────────────────────

def _select_best_proposal(shared_state: dict) -> str:
    """
    Pick the most relevant template based on currently available data.
    Priority:
    1. OI heatmap — if Observer has found OI data
    2. Block deals — if Observer found deals today
    3. Backtest gauge — if synthetic_backtest has run and shows MEDIUM/HIGH risk
    4. Promoter table — if Observer has promoter data
    5. Memory timeline — always available if memory_engine has lessons
    6. Scryer delta chart — fallback if scryer_output has shock data
    """
    obs  = shared_state.get("observer_output", {})
    bt   = shared_state.get("synthetic_backtest", {})
    scr  = shared_state.get("scryer_output", {})

    # Already applied templates this session
    applied = {p["template"] for p in _load_proposals() if p["status"] in ("APPLIED", "PENDING")}

    if obs.get("oi_heatmap", {}).get("pcr") and "oi_heatmap_chart" not in applied:
        return "oi_heatmap_chart"
    if obs.get("block_deals_today") and "block_deals_feed" not in applied:
        return "block_deals_feed"
    if bt.get("black_swan_probability") in ("MEDIUM", "HIGH") and "backtest_probability_gauge" not in applied:
        return "backtest_probability_gauge"
    if obs.get("promoter_holdings") and "promoter_holding_table" not in applied:
        return "promoter_holding_table"
    if scr.get("shock_map") and "scryer_delta_chart" not in applied:
        return "scryer_delta_chart"
    if "memory_lessons_timeline" not in applied:
        return "memory_lessons_timeline"

    return ""  # nothing new to propose


# ─── Code Generation ──────────────────────────────────────────────────────────

def _generate_panel_code(template: str, shared_state: dict) -> tuple:
    """
    Call Claude Haiku to generate a complete HTML/JS panel for the given template.
    Returns (html_code: str, title: str, why: str).
    Only generates code that calls existing Flask routes.
    """
    obs = shared_state.get("observer_output", {})
    bt  = shared_state.get("synthetic_backtest", {})

    # Context snippets for each template
    template_contexts = {
        "oi_heatmap_chart": {
            "title": "NSE Option Chain OI Heatmap",
            "why":   f"Observer found max pain at {obs.get('oi_heatmap',{}).get('max_pain','?')} with PCR {obs.get('oi_heatmap',{}).get('pcr','?')} — not visible in current dashboard",
            "data_route": "/api/observer-data",
            "data_path":  "d.observer.oi_heatmap",
        },
        "block_deals_feed": {
            "title": "Institutional Block Deals Today",
            "why":   f"Observer found {len(obs.get('block_deals_today',[]))} block deals — smart money moves missing from dashboard",
            "data_route": "/api/observer-data",
            "data_path":  "d.observer.block_deals_today",
        },
        "backtest_probability_gauge": {
            "title": "Portfolio Risk Gauge",
            "why":   f"Stress tests show {bt.get('black_swan_probability','?')} black swan probability — needs visual risk indicator",
            "data_route": "/api/synthetic-backtest",
            "data_path":  "d.current",
        },
        "promoter_holding_table": {
            "title": "Promoter Holding Tracker",
            "why":   "Screener.in data shows promoter holding trends — key insider signal missing from watchlist",
            "data_route": "/api/observer-data",
            "data_path":  "d.observer.promoter_holdings",
        },
        "scryer_delta_chart": {
            "title": "Shock vs Reality Delta Chart",
            "why":   "Scryer overreaction data is text-only — needs visual bar chart to spot news/price divergence",
            "data_route": "/api/sovereign-status",
            "data_path":  "d.scryer.shock_map",
        },
        "memory_lessons_timeline": {
            "title": "Trade Memory Timeline",
            "why":   "SQLite trade lessons exist but are only in a table — timeline view shows learning progression",
            "data_route": "/api/agent-memory",
            "data_path":  "d.lessons",
        },
    }

    ctx = template_contexts.get(template, {
        "title": "Dashboard Enhancement",
        "why":   "Improving dashboard coverage",
        "data_route": "/api/observer-data",
        "data_path":  "d.observer",
    })

    # Try LLM generation first
    try:
        html_code = _llm_generate_html(template, ctx)
    except Exception as e:
        log.warning(f"Builder LLM generation failed: {e} — using fallback")
        html_code = _fallback_html(template, ctx)

    return html_code, ctx["title"], ctx["why"]


def _llm_generate_html(template: str, ctx: dict) -> str:
    """Call Claude Haiku to generate the dashboard panel HTML/JS."""
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("No ANTHROPIC_API_KEY")

    prompt = (
        f"Generate a self-contained dashboard panel for a stock trading app.\n\n"
        f"Panel: {ctx['title']}\n"
        f"Data source: fetch('{ctx['data_route']}') → access {ctx['data_path']}\n\n"
        f"Requirements:\n"
        f"- Complete HTML+JavaScript, no external CDN beyond what's already on the page (Chart.js, no others)\n"
        f"- CSS uses these CSS vars: --bg-card, --accent, --accent4, --muted, --border, --green, --red, --gold\n"
        f"- Wrap in a single <div class='card' style='margin-top:1rem'> with card-head and card-title divs\n"
        f"- Use async/await fetch to load data; show 'Loading...' placeholder\n"
        f"- Data path in response: {ctx['data_path']}\n"
        f"- Max 120 lines total\n"
        f"- Assign a unique function name like fetchBuilderPanel_{template}()\n"
        f"- Call the function immediately: fetchBuilderPanel_{template}();\n\n"
        f"Generate ONLY the HTML. No explanation."
    )

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    html = resp.content[0].text.strip()
    # Strip markdown code fences if present
    if html.startswith("```"):
        lines = html.splitlines()
        html = "\n".join(l for l in lines if not l.startswith("```"))
    return html


def _fallback_html(template: str, ctx: dict) -> str:
    """Static fallback panel used if LLM is unavailable."""
    return f"""<div class="card" style="margin-top:1rem">
  <div class="card-head">
    <div class="card-title">📊 {ctx['title']}</div>
    <div style="font-size:.72rem;color:var(--muted)">Auto-generated</div>
  </div>
  <div id="builder-panel-{template}" style="padding:.75rem;color:var(--muted);font-size:.82rem">
    Loading {ctx['title']}...
  </div>
  <script>
  (async function fetchBuilderPanel_{template}() {{
    try {{
      const d = await fetch('{ctx["data_route"]}').then(r => r.json());
      const el = document.getElementById('builder-panel-{template}');
      const data = {ctx["data_path"].replace("d.", "d?.")} || {{}};
      el.innerHTML = '<pre style="font-size:.75rem;white-space:pre-wrap">' +
        JSON.stringify(data, null, 2).slice(0, 800) + '</pre>';
    }} catch(e) {{ }}
  }})();
  </script>
</div>"""


# ─── HTML Auto-Patcher ────────────────────────────────────────────────────────

def _apply_patch(proposal: dict) -> bool:
    """
    Inject proposal["html_code"] into index.html between
    <!-- BUILDER_START --> and <!-- BUILDER_END --> markers.
    Returns True on success.
    """
    try:
        if not os.path.exists(_INDEX_HTML):
            log.error(f"Builder: index.html not found at {_INDEX_HTML}")
            return False

        with open(_INDEX_HTML, "r", encoding="utf-8") as f:
            content = f.read()

        start_marker = "<!-- BUILDER_START -->"
        end_marker   = "<!-- BUILDER_END -->"

        if start_marker not in content or end_marker not in content:
            log.error("Builder: BUILDER_START/END markers not found in index.html")
            return False

        # Extract existing builder content
        start_idx = content.index(start_marker) + len(start_marker)
        end_idx   = content.index(end_marker)
        existing  = content[start_idx:end_idx]

        # Append new panel (preserving existing panels)
        timestamp = datetime.now().strftime("%d %b %Y %H:%M")
        new_block = (
            f"\n<!-- Builder Panel: {proposal['title']} | Applied: {timestamp} -->\n"
            + proposal["html_code"]
            + "\n"
        )
        new_content = (
            content[:start_idx]
            + existing
            + new_block
            + content[end_idx:]
        )

        with open(_INDEX_HTML, "w", encoding="utf-8") as f:
            f.write(new_content)

        log.info(f"Builder: patch applied — {proposal['id']} | {proposal['title']}")
        return True

    except Exception as e:
        log.error(f"Builder: patch failed: {e}")
        return False


# ─── Telegram Inline Keyboard ─────────────────────────────────────────────────

def _send_builder_proposal(proposal: dict, send_telegram_fn) -> None:
    """Send Telegram message with inline APPLY/REJECT buttons."""
    if not send_telegram_fn:
        return

    token = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("Builder: Telegram not configured")
        return

    import requests as req

    pid = proposal["id"]
    msg = (
        f"🏗️ *BUILDER PROPOSAL*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 {proposal['title']}\n\n"
        f"_Why:_ {proposal['why']}\n\n"
        f"Source: `{proposal.get('data_source', '/api/observer-data')}`\n"
        f"Size: ~{proposal.get('lines', '?')} lines HTML/JS\n\n"
        f"⏰ Expires in {_EXPIRY_HOURS}h"
    )

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ APPLY IT",  "callback_data": f"bld_approve_{pid}"},
            {"text": "❌ REJECT",    "callback_data": f"bld_reject_{pid}"},
        ]]
    }

    try:
        import json as _json
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = req.post(url, json={
            "chat_id":      chat_id,
            "text":         msg,
            "parse_mode":   "Markdown",
            "reply_markup": _json.dumps(keyboard),
        }, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            proposal["telegram_msg_id"] = result.get("result", {}).get("message_id")
            log.info(f"Builder: Telegram proposal sent — msg_id={proposal.get('telegram_msg_id')}")
    except Exception as e:
        log.warning(f"Builder: Telegram send error: {e}")


def _answer_callback(callback_query_id: str, text: str = "Done") -> None:
    """Dismiss the Telegram loading spinner."""
    token = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        return
    try:
        import requests as req
        req.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=5,
        )
    except Exception:
        pass


# ─── Proposal Persistence ─────────────────────────────────────────────────────

def _load_proposals() -> list:
    try:
        if os.path.exists(_PROPOSALS_FILE):
            with open(_PROPOSALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_proposal(proposal: dict) -> None:
    proposals = _load_proposals()
    proposals.append(proposal)
    if len(proposals) > _MAX_PROPOSALS:
        proposals = proposals[-_MAX_PROPOSALS:]
    _write_proposals(proposals)


def _update_proposal(proposals: list, updated: dict) -> None:
    for i, p in enumerate(proposals):
        if p["id"] == updated["id"]:
            proposals[i] = updated
            break
    _write_proposals(proposals)


def _write_proposals(proposals: list) -> None:
    try:
        with open(_PROPOSALS_FILE, "w", encoding="utf-8") as f:
            json.dump(proposals, f, indent=2, default=str)
    except Exception as e:
        log.error(f"Builder: failed to write proposals: {e}")


def _expire_old_proposals() -> None:
    """Mark expired PENDING proposals as EXPIRED."""
    proposals = _load_proposals()
    changed = False
    now = datetime.now()
    for p in proposals:
        if p["status"] == "PENDING":
            try:
                expires = datetime.fromisoformat(p["expires_at"])
                if now > expires:
                    p["status"] = "EXPIRED"
                    changed = True
            except (ValueError, KeyError):
                pass
    if changed:
        _write_proposals(proposals)
