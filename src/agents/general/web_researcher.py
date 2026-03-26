"""
AGENT 8 — WEB RESEARCHER
━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : On-demand deep research on breakout stocks.
          When paper_trader is about to execute, this agent does a
          final web search to verify no negative hidden news exists.
          "Last-mile intelligence" before committing to a paper trade.
Runs    : On-demand (triggered by paper_trader pre-execution check)
Cost    : Gemini Flash free tier (1M tokens/day free)
          Falls back to basic scraping if no API key
"""

import requests
import re
import os
import json
import logging
from datetime import datetime

log = logging.getLogger("WebResearcher")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── DUCKDUCKGO SEARCH (no API key needed) ────────────────────────────────────
def ddg_search(query, max_results=5):
    """DuckDuckGo Instant Answer API — no key, no CAPTCHA."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        r = requests.get(url, params=params,
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        data  = r.json()
        results = []

        # Abstract text
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", ""),
                "text":  data["AbstractText"][:300],
                "source": data.get("AbstractSource", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            text = topic.get("Text", "")
            if text and len(text) > 30:
                results.append({
                    "title": text[:80],
                    "text":  text[:300],
                    "source": "DuckDuckGo",
                })

        return results
    except Exception as e:
        log.debug("DDG search failed: %s", e)
        return []

def scrape_google_news(stock_name, max_results=3):
    """Try Google News RSS for recent headlines."""
    try:
        query = f"{stock_name} NSE stock news"
        url   = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        r     = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', r.text)
        if not titles:
            titles = re.findall(r'<title>(.*?)</title>', r.text)
        return [{"title": t, "source": "Google News"} for t in titles[1:max_results+1]]
    except Exception as e:
        log.debug("Google News scrape failed: %s", e)
        return []

# ── GEMINI SUMMARIZER ─────────────────────────────────────────────────────────
def gemini_analyze(stock_name, search_results):
    """
    Use Gemini Flash to summarize search results and flag risks.
    Free tier: 15 req/min, 1M tokens/day.
    """
    if not GEMINI_API_KEY or not search_results:
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model   = genai.GenerativeModel("gemini-2.5-flash")

        content = "\n".join([
            f"- {r.get('title','')} {r.get('text','')[:150]}"
            for r in search_results
        ])

        prompt = f"""You are a stock market risk analyst. Review these recent news items for {stock_name} (NSE India).

News found:
{content}

Respond in JSON only:
{{
  "sentiment": "POSITIVE|NEGATIVE|NEUTRAL",
  "risk_level": "HIGH|MEDIUM|LOW",
  "key_finding": "<one sentence summary>",
  "red_flags": ["<flag1>", "<flag2>"],
  "safe_to_trade": true/false
}}

Rules:
- safe_to_trade = false if: fraud, SEBI action, massive loss, ban, regulatory issue
- safe_to_trade = true if: positive results, order wins, analyst upgrade, or no major news"""

        response = model.generate_content(prompt)
        text     = response.text
        start    = text.find("{")
        end      = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        log.debug("Gemini analyze failed: %s", e)

    return None

def basic_sentiment_check(search_results, stock_name):
    """Simple keyword-based fallback if Gemini unavailable."""
    danger_words = [
        "fraud", "scam", "sebi notice", "ban", "penalty", "default",
        "insolvency", "liquidation", "fir", "arrested", "seized",
        "major loss", "massive decline", "promoter selling"
    ]
    positive_words = [
        "profit", "order win", "expansion", "results beat",
        "dividend", "buyback", "upgrade", "record revenue"
    ]

    all_text = " ".join([
        (r.get("title", "") + " " + r.get("text", "")).lower()
        for r in search_results
    ])

    red_flags   = [w for w in danger_words   if w in all_text]
    green_flags = [w for w in positive_words if w in all_text]

    if red_flags:
        sentiment = "NEGATIVE"
        risk      = "HIGH"
        safe      = False
    elif green_flags:
        sentiment = "POSITIVE"
        risk      = "LOW"
        safe      = True
    else:
        sentiment = "NEUTRAL"
        risk      = "LOW"
        safe      = True

    return {
        "sentiment":    sentiment,
        "risk_level":   risk,
        "key_finding":  f"Found {len(green_flags)} positives, {len(red_flags)} red flags",
        "red_flags":    red_flags[:3],
        "safe_to_trade": safe,
        "method":       "keyword",
    }

# ── MAIN RESEARCH FUNCTION ────────────────────────────────────────────────────
def research_stock(stock_name, sector=""):
    """
    Full research pipeline for one stock.
    Called by paper_trader before executing any paper trade.
    """
    log.info("🔍 WebResearcher: Researching %s (%s)...", stock_name, sector)

    results = []

    # Search 1: Recent news
    results += ddg_search(f"{stock_name} NSE India stock news 2025 2026")

    # Search 2: Negative events
    results += ddg_search(f"{stock_name} SEBI NSE fraud penalty news")

    # Search 3: Google News
    results += scrape_google_news(stock_name)

    # Deduplicate
    seen    = set()
    unique  = []
    for r in results:
        key = r.get("title", "")[:50]
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    if not unique:
        log.info("  No web results found — assuming safe (neutral)")
        return {
            "stock":        stock_name,
            "safe_to_trade": True,
            "sentiment":    "NEUTRAL",
            "risk_level":   "LOW",
            "key_finding":  "No recent news found",
            "red_flags":    [],
            "results_count": 0,
            "researched_at": datetime.now().strftime("%H:%M:%S"),
        }

    # Analyze with Gemini (or fallback)
    analysis = gemini_analyze(stock_name, unique)
    if not analysis:
        analysis = basic_sentiment_check(unique, stock_name)

    analysis["stock"]        = stock_name
    analysis["results_count"] = len(unique)
    analysis["headlines"]    = [r.get("title", "")[:80] for r in unique[:3]]
    analysis["researched_at"] = datetime.now().strftime("%H:%M:%S")

    log.info("  %s: sentiment=%s | risk=%s | safe=%s | %d results",
             stock_name, analysis["sentiment"], analysis["risk_level"],
             analysis["safe_to_trade"], len(unique))
    return analysis

def run(shared_state):
    """
    Research top 3 actionable signals before paper trading.
    Updates shared_state["web_research"] with findings.
    """
    signals = shared_state.get("risk_reviewed_signals", [])
    to_research = [
        s for s in signals
        if s.get("risk", {}).get("approved")
    ][:3]  # Only research approved signals (save API quota)

    if not to_research:
        log.info("WebResearcher: No approved signals to research")
        shared_state["web_research"] = {}
        return {}

    research_results = {}
    log.info("🔍 WebResearcher: Researching %d approved signals...", len(to_research))

    for sig in to_research:
        name   = sig.get("name", "")
        sector = sig.get("sector", "")
        if name:
            research_results[name] = research_stock(name, sector)

    shared_state["web_research"]      = research_results
    shared_state["web_research_last"] = datetime.now().strftime("%d %b %H:%M:%S")
    log.info("✅ WebResearcher: %d stocks researched", len(research_results))
    return research_results
