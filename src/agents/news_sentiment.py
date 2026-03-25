"""
AGENT 2 — NEWS SENTIMENT AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Scrape financial news headlines, score sentiment,
          link news to affected stocks, flag high-impact events.
Runs    : Every 15 minutes
Reports : Telegram (high-impact only) + Dashboard
"""

import os
import json
import requests
import logging
import re
from datetime import datetime

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

log = logging.getLogger("NewsSentiment")

# ── NEWS SOURCES (RSS feeds — free, no API key) ─────────────────────────────
NEWS_FEEDS = [
    {
        "name": "Economic Times Markets",
        "url":  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "weight": 1.2
    },
    {
        "name": "Moneycontrol",
        "url":  "https://www.moneycontrol.com/rss/latestnews.xml",
        "weight": 1.0
    },
    {
        "name": "NSE India News",
        "url":  "https://www.nseindia.com/api/corporate-announcements?index=equities",
        "weight": 1.5   # direct exchange data = highest weight
    },
    {
        "name": "LiveMint Markets",
        "url":  "https://www.livemint.com/rss/markets",
        "weight": 1.0
    },
]

# ── KEYWORD SENTIMENT RULES ─────────────────────────────────────────────────
POSITIVE_KEYWORDS = [
    "profit", "growth", "record", "surge", "rally", "beat", "outperform",
    "upgrade", "buy", "strong", "acquisition", "order", "contract", "win",
    "dividend", "bonus", "buyback", "expansion", "launch", "approval", "approved",
    "q3 beat", "q4 beat", "eps beat", "revenue beat", "nii growth", "margin expansion",
    "rate cut", "rbi cut", "fii buying", "bulk deal buy", "block deal buy"
]

NEGATIVE_KEYWORDS = [
    "loss", "decline", "fall", "crash", "miss", "downgrade", "sell", "weak",
    "fraud", "scam", "penalty", "fine", "recall", "ban", "reject", "seized",
    "layoff", "warning", "default", "npa", "stressed", "insolvency",
    "rate hike", "fii selling", "margin pressure", "revenue miss"
]

HIGH_IMPACT_KEYWORDS = [
    "rbi", "sebi", "budget", "gdp", "inflation", "rate", "fed", "crude", "rupee",
    "ipo", "merger", "acquisition", "result", "quarterly", "annual", "dividend",
    "block deal", "bulk deal", "promoter", "fii", "dii", "circuit"
]

# Stock name → ticker mapping for news linking
STOCK_MENTIONS = {
    "hdfc bank": "HDFC BANK", "icici bank": "ICICI BANK", "sbi": "SBI",
    "reliance": "RELIANCE", "tcs": "TCS", "infosys": "INFOSYS",
    "airtel": "AIRTEL", "bharti": "AIRTEL", "bajaj finance": "BAJAJ FIN",
    "bajaj fin": "BAJAJ FIN", "zomato": "ZOMATO", "indigo": "INDIGO",
    "interglobe": "INDIGO", "bel": "BEL", "bharat electronics": "BEL",
    "muthoot": "MUTHOOT", "sun pharma": "SUN PHARMA", "maruti": "MARUTI",
    "tata motors": "TATA MOTORS", "l&t": "L&T", "larsen": "L&T",
    "ntpc": "NTPC", "ongc": "ONGC", "coal india": "COAL INDIA",
    "wipro": "WIPRO", "hcl": "HCL TECH", "divis": "DIVIS LAB",
    "apollo": "APOLLO HOSP", "max health": "MAX HEALTH", "hal": "HAL",
    "ultratech": "ULTRATECH", "tata steel": "TATA STEEL", "hindalco": "HINDALCO",
    "itc": "ITC", "hindustan unilever": "HINDUSTAN UNI", "hul": "HINDUSTAN UNI",
}

def fetch_rss(feed):
    """Fetch and parse RSS feed headlines."""
    items = []
    try:
        r = requests.get(feed["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        content = r.text

        # Extract titles from RSS
        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
        if not titles:
            titles = re.findall(r'<title>(.*?)</title>', content)

        # Extract pubDates
        dates = re.findall(r'<pubDate>(.*?)</pubDate>', content)

        for i, title in enumerate(titles[1:21]):  # skip channel title, max 20
            title = title.strip()
            if len(title) > 10:
                items.append({
                    "headline": title,
                    "source":   feed["name"],
                    "weight":   feed["weight"],
                    "pub_date": dates[i].strip() if i < len(dates) else "Today",
                })
    except Exception as e:
        log.debug(f"RSS fetch failed for {feed['name']}: {e}")
    return items

def score_headline(headline):
    """Score a headline: returns sentiment score -10 to +10."""
    text  = headline.lower()
    score = 0

    for kw in POSITIVE_KEYWORDS:
        if kw in text:
            score += 1.5 if kw in ["record","acquisition","order","approval","rate cut"] else 1

    for kw in NEGATIVE_KEYWORDS:
        if kw in text:
            score -= 1.5 if kw in ["fraud","default","ban","crash","insolvency"] else 1

    return round(max(-10, min(10, score)), 1)

def extract_stock_mentions(headline):
    """Find which stocks are mentioned in headline."""
    text     = headline.lower()
    mentions = []
    for phrase, ticker in STOCK_MENTIONS.items():
        if phrase in text:
            mentions.append(ticker)
    return list(set(mentions))

def classify_impact(score, headline):
    """Classify news impact level."""
    text = headline.lower()
    has_high_kw = any(kw in text for kw in HIGH_IMPACT_KEYWORDS)

    if abs(score) >= 3 or has_high_kw:
        return "HIGH"
    elif abs(score) >= 1.5:
        return "MEDIUM"
    else:
        return "LOW"

def _llm_batch_score(headlines: list, watchlist_names: list) -> dict:
    """
    Send top headlines to Claude Haiku for nuanced LLM sentiment scoring.
    Returns dict: {headline_idx: {score, reasoning, stocks, impact}}
    Falls back silently if API unavailable.
    """
    if not ANTHROPIC_API_KEY or not headlines:
        return {}
    try:
        wl_str = ", ".join(watchlist_names[:15]) if watchlist_names else "general Indian equities"
        numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines[:15]))
        prompt = f"""You are a financial news analyst for Indian equity markets.
Analyze these {len(headlines[:15])} headlines. For each, return a JSON array:

Watchlist stocks to watch: {wl_str}

Headlines:
{numbered}

Return ONLY a valid JSON array with one object per headline (same order):
[{{"idx":1,"score":-8,"impact":"HIGH","stocks":["HDFC BANK"],"reason":"NPA rise hurts bank stocks"}}, ...]

Rules:
- score: -10 (very negative) to +10 (very positive) for Indian markets
- impact: "HIGH" | "MEDIUM" | "LOW"
- stocks: list of watchlist stocks directly affected (empty list if none)
- reason: max 8 words explaining the market impact
Return ONLY the JSON array, no other text."""

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=12
        )
        if resp.status_code != 200:
            return {}
        content = resp.json()["content"][0]["text"].strip()
        # Extract JSON array from response
        start = content.find("[")
        end   = content.rfind("]") + 1
        if start < 0 or end <= start:
            return {}
        results = json.loads(content[start:end])
        return {r["idx"]: r for r in results if isinstance(r, dict)}
    except Exception as e:
        log.debug(f"LLM batch score error: {e}")
        return {}


def run(shared_state):
    """Main agent function — fetch, score, rank news."""
    log.info("📰 NewsSentiment: Fetching from %d sources...", len(NEWS_FEEDS))

    all_items = []
    for feed in NEWS_FEEDS:
        items = fetch_rss(feed)
        all_items.extend(items)
        log.info("  %s: %d headlines", feed["name"], len(items))

    if not all_items:
        # Fallback: return placeholder
        log.warning("No news fetched — using market hours check")
        shared_state["news_results"]  = []
        shared_state["market_sentiment_score"] = 0
        shared_state["news_last_run"] = datetime.now().strftime("%d %b %H:%M:%S")
        return []

    # ── Keyword-based scoring (fast, always runs) ────────────────────────────
    scored = []
    for item in all_items:
        s   = score_headline(item["headline"])
        imp = classify_impact(s, item["headline"])
        stk = extract_stock_mentions(item["headline"])
        scored.append({
            **item,
            "sentiment_score": s,
            "impact":          imp,
            "stocks_affected": stk,
            "scored_by":       "keyword",
            "emoji":           "🟢" if s > 0 else "🔴" if s < 0 else "⚪",
        })

    # ── LLM batch scoring (top 15 headlines — one API call) ──────────────────
    wl_names = [s.get("name", "") for s in shared_state.get("watchlist", [])]
    top_headlines = [item["headline"] for item in scored[:15]]
    llm_scores = _llm_batch_score(top_headlines, wl_names)

    if llm_scores:
        log.info(f"  LLM scored {len(llm_scores)} headlines (Claude Haiku)")
        for i, item in enumerate(scored[:15]):
            llm = llm_scores.get(i + 1, {})
            if llm:
                # Blend: LLM score takes 70% weight, keyword 30%
                blended = round(llm.get("score", item["sentiment_score"]) * 0.7
                                + item["sentiment_score"] * 0.3, 1)
                item["sentiment_score"] = blended
                item["impact"]          = llm.get("impact", item["impact"])
                item["llm_reason"]      = llm.get("reason", "")
                item["scored_by"]       = "llm+keyword"
                # Merge LLM-identified stocks with keyword-found ones
                llm_stocks = llm.get("stocks", [])
                item["stocks_affected"] = list(set(item["stocks_affected"] + llm_stocks))
                item["emoji"]           = "🟢" if blended > 0 else "🔴" if blended < 0 else "⚪"

    # Sort: high impact first, then by abs score
    scored.sort(key=lambda x: (
        0 if x["impact"] == "HIGH" else 1 if x["impact"] == "MEDIUM" else 2,
        -abs(x["sentiment_score"])
    ))

    # Overall market sentiment
    if scored:
        avg_score = round(sum(x["sentiment_score"] for x in scored) / len(scored), 2)
    else:
        avg_score = 0

    # Build stock-level sentiment map
    stock_sentiment = {}
    for item in scored:
        for stk in item.get("stocks_affected", []):
            if stk not in stock_sentiment:
                stock_sentiment[stk] = {"score": 0, "count": 0, "headlines": []}
            stock_sentiment[stk]["score"]  += item["sentiment_score"]
            stock_sentiment[stk]["count"]  += 1
            stock_sentiment[stk]["headlines"].append(item["headline"][:80])

    high_impact = [x for x in scored if x["impact"] == "HIGH"]
    log.info("✅ NewsSentiment: %d items scored. Avg: %.2f. High-impact: %d",
             len(scored), avg_score, len(high_impact))

    shared_state["news_results"]           = scored[:25]
    shared_state["news_high_impact"]       = high_impact[:8]
    shared_state["market_sentiment_score"] = avg_score
    shared_state["stock_sentiment_map"]    = stock_sentiment
    shared_state["news_last_run"]          = datetime.now().strftime("%d %b %H:%M:%S")

    # ── Agent handoff protocol ────────────────────────────────────────────────
    if "agent_confidence" not in shared_state:
        shared_state["agent_confidence"] = {}
    llm_used = any(s.get("scored_by") == "llm+keyword" for s in scored[:15])
    shared_state["agent_confidence"]["news_sentiment"] = {
        "confidence":    0.85 if llm_used else 0.60,
        "key_signal":    "BULLISH" if avg_score > 1 else "BEARISH" if avg_score < -1 else "NEUTRAL",
        "avg_score":     avg_score,
        "high_impact":   len(high_impact),
        "llm_enhanced":  llm_used,
        "handoff_notes": (
            f"{'LLM-scored' if llm_used else 'Keyword-scored'} | "
            f"Avg sentiment: {avg_score:+.1f} | "
            f"{len(high_impact)} high-impact headlines"
        )
    }
    return scored[:25]
