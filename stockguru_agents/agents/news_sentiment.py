"""
AGENT 2 — NEWS SENTIMENT AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Goal    : Scrape financial news headlines, score sentiment,
          link news to affected stocks, flag high-impact events.
Runs    : Every 15 minutes
Reports : Telegram (high-impact only) + Dashboard
"""

import requests
import logging
import re
from datetime import datetime

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

    # Score & enrich each headline
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
            "emoji":           "🟢" if s > 0 else "🔴" if s < 0 else "⚪",
        })

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
    return scored[:25]
