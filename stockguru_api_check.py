"""
StockGuru — API Diagnostic Checker
Run this ONCE to pinpoint exactly why the Anthropic API is failing.
Usage: python stockguru_api_check.py
"""

import os
import sys
import json

# ── Load .env manually (no dotenv needed) ─────────────────────────────────────
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def load_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

env = load_env(ENV_PATH)

ANTHROPIC_KEY = env.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
GEMINI_KEY    = env.get("GEMINI_API_KEY",    os.getenv("GEMINI_API_KEY", ""))
TG_TOKEN      = env.get("TELEGRAM_TOKEN",    os.getenv("TELEGRAM_TOKEN", ""))
TG_CHAT_ID    = env.get("TELEGRAM_CHAT_ID",  os.getenv("TELEGRAM_CHAT_ID", ""))

print("=" * 60)
print("  StockGuru API Diagnostic — Running checks...")
print("=" * 60)

# ── CHECK 1: Key presence ──────────────────────────────────────────────────────
print("\n📋 STEP 1 — Checking API keys in .env file")

def mask(key):
    if not key or key.startswith("your_"):
        return None
    return key[:8] + "..." + key[-4:] if len(key) > 16 else "SET (short key?)"

checks = {
    "ANTHROPIC_API_KEY": ANTHROPIC_KEY,
    "GEMINI_API_KEY":    GEMINI_KEY,
    "TELEGRAM_TOKEN":    TG_TOKEN,
    "TELEGRAM_CHAT_ID":  TG_CHAT_ID,
}

all_ok = True
for name, val in checks.items():
    m = mask(val)
    if m is None:
        print(f"  ❌  {name:<25} NOT SET or still placeholder")
        all_ok = False
    else:
        print(f"  ✅  {name:<25} {m}")

# ── CHECK 2: Anthropic API live call ──────────────────────────────────────────
print("\n📋 STEP 2 — Live test call to Anthropic API (Claude Haiku)")

try:
    import urllib.request, urllib.error

    if not ANTHROPIC_KEY or ANTHROPIC_KEY.startswith("your_"):
        print("  ⏭️  Skipping — ANTHROPIC_API_KEY not set")
    else:
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": "Reply with: OK"}]
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key":         ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                reply = data["content"][0]["text"].strip()
                print(f"  ✅  Anthropic API WORKING — Response: '{reply}'")
                print(f"      Model used: {data.get('model', 'unknown')}")
                print(f"      Input tokens: {data.get('usage', {}).get('input_tokens', '?')}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  ❌  Anthropic API ERROR {e.code}: {body}")
            if "credit" in body.lower() or "balance" in body.lower():
                print("\n  ⚠️  DIAGNOSIS: Credits still not reflecting.")
                print("      → Wait 2–3 minutes and try again.")
                print("      → OR your API key might be from a DIFFERENT account than")
                print("        where you added credits. Check console.anthropic.com")
            elif "invalid" in body.lower() and "key" in body.lower():
                print("\n  ⚠️  DIAGNOSIS: Your API key is INVALID or EXPIRED.")
                print("      → Go to console.anthropic.com → API Keys → Create new key")
                print("      → Paste the new key into your .env file")

except Exception as ex:
    print(f"  ❌  Unexpected error during Anthropic test: {ex}")

# ── CHECK 3: Flask server ─────────────────────────────────────────────────────
print("\n📋 STEP 3 — Checking if StockGuru Flask server is running")

try:
    import urllib.request
    with urllib.request.urlopen("http://localhost:5050/api/status", timeout=4) as r:
        data = json.loads(r.read())
        print(f"  ✅  Flask server is UP on port 5050")
        print(f"      Agents available: {data.get('agents_available', '?')}")
except Exception:
    print("  ⚠️  Flask server NOT running on localhost:5050")
    print("      → Double-click START.bat to launch StockGuru")

# ── CHECK 4: Gemini API ────────────────────────────────────────────────────────
print("\n📋 STEP 4 — Checking Gemini API key")

if not GEMINI_KEY or GEMINI_KEY.startswith("your_"):
    print("  ⚠️  GEMINI_API_KEY not set — Gemini parallel reviews disabled")
    print("      → Get free key: https://aistudio.google.com/app/apikey")
else:
    print(f"  ✅  Gemini key present: {mask(GEMINI_KEY)}")

# ── CHECK 5: Telegram ─────────────────────────────────────────────────────────
print("\n📋 STEP 5 — Checking Telegram config")

if not TG_TOKEN or TG_TOKEN.startswith("your_"):
    print("  ❌  TELEGRAM_TOKEN not set — alerts will NOT be sent")
elif not TG_CHAT_ID or TG_CHAT_ID.startswith("your_"):
    print("  ❌  TELEGRAM_CHAT_ID not set — alerts will NOT be sent")
else:
    print(f"  ✅  Telegram token:   {mask(TG_TOKEN)}")
    print(f"  ✅  Telegram chat ID: {TG_CHAT_ID}")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  DIAGNOSTIC COMPLETE")
print("  Share the output above so we can apply the exact fix.")
print("=" * 60)
