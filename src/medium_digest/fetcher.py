"""
Medium Daily Digest Agent - Feed Fetcher
=========================================
Fetches and parses Medium RSS feeds, extracts article content.
"""

import re
import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser
import httpx
from dateutil import parser as dateparser

from . import config

logger = logging.getLogger(__name__)


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def strip_html(raw_html: str) -> str:
    """Remove HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", raw_html)
    return html.unescape(clean).strip()


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_feed(url: str, timeout: int = 15) -> list[dict]:
    """
    Fetch and parse a single RSS feed URL.
    Returns a list of article dicts with: title, link, published, summary.
    """
    try:
        resp = httpx.get(
            url, timeout=timeout, follow_redirects=True, headers=HEADERS
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except Exception as e:
        logger.warning(f"Failed to fetch feed {url}: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)
    articles = []

    for entry in feed.entries:
        # Parse publish date
        published = None
        for date_field in ("published", "updated"):
            raw = getattr(entry, date_field, None)
            if raw:
                try:
                    published = dateparser.parse(raw)
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                    break
                except (ValueError, TypeError):
                    pass

        # Skip articles older than lookback window
        if published and published < cutoff:
            continue

        summary = ""
        if hasattr(entry, "summary"):
            summary = strip_html(entry.summary)[:500]

        articles.append(
            {
                "title": entry.get("title", "Untitled"),
                "link": entry.get("link", ""),
                "published": published,
                "summary": summary,
                "author": entry.get("author", "Unknown"),
            }
        )

    return articles


def fetch_all_feeds(feed_urls: list[str]) -> list[dict]:
    """Fetch multiple feeds and deduplicate by URL."""
    seen_links = set()
    all_articles = []

    for url in feed_urls:
        articles = fetch_feed(url)
        for article in articles:
            if article["link"] not in seen_links:
                seen_links.add(article["link"])
                all_articles.append(article)

    # Sort by publish date (newest first)
    all_articles.sort(
        key=lambda a: a["published"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    return all_articles


def extract_content(url: str, timeout: int = 20) -> Optional[str]:
    """
    Extract readable article content using Jina Reader.
    Falls back to the RSS summary if extraction fails.
    """
    jina_url = f"{config.JINA_READER_PREFIX}{url}"
    try:
        resp = httpx.get(
            jina_url,
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "text/plain"},
        )
        resp.raise_for_status()
        content = resp.text.strip()
        if content:
            return content[:config.MAX_CONTENT_CHARS]
    except Exception as e:
        logger.warning(f"Jina extraction failed for {url}: {e}")

    return None


def gather_articles_for_topic(
    feed_urls: list[str], max_articles: int = 5, topic_name: str = ""
) -> list[dict]:
    """
    Fetch feeds for a topic, extract content for top articles.
    Falls back to Google News RSS if Medium feeds return nothing.
    Returns enriched article dicts with a 'content' field.
    """
    articles = fetch_all_feeds(feed_urls)

    # Fallback: Google News RSS filtered to medium.com
    if not articles and config.ENABLE_GOOGLE_NEWS_FALLBACK and topic_name in config.GOOGLE_NEWS_QUERIES:
        logger.info(f"  ↳ Medium RSS empty, trying Google News fallback...")
        fallback_urls = [
            GOOGLE_NEWS_RSS.format(query=q.replace(" ", "+"))
            for q in config.GOOGLE_NEWS_QUERIES[topic_name]
        ]
        articles = fetch_all_feeds(fallback_urls)

    articles = articles[:max_articles]

    for article in articles:
        logger.info(f"  Extracting: {article['title']}")
        content = extract_content(article["link"])
        article["content"] = content or article.get("summary", "")

    return articles
