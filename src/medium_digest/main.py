#!/usr/bin/env python3
"""
Medium Daily Digest Agent
=========================
Fetches recent Medium articles across configured topics,
summarizes them with Claude, and writes a daily Markdown digest.

Usage:
    python main.py                  # Run with default settings
    python main.py --lookback 3     # Override lookback to 3 days
    python main.py --no-ai          # Skip Claude, just list articles
    python main.py --dry-run        # Print to stdout, don't save file

Requirements:
    pip install feedparser httpx anthropic python-dateutil

Environment:
    ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .fetcher import gather_articles_for_topic
from .summarizer import summarize_topic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_digest(use_ai: bool = True) -> str:
    """
    Gather articles for all topics and build the full digest Markdown.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %d, %Y")

    sections = [
        f"# 📰 Medium Daily Digest",
        f"**{date_str}**\n",
        f"_Curated by your AI digest agent — {len(config.TOPICS)} topics tracked._\n",
        "---\n",
    ]

    total_articles = 0

    for topic_name, topic_cfg in config.TOPICS.items():
        logger.info(f"📡 Fetching: {topic_name}")
        articles = gather_articles_for_topic(
            feed_urls=topic_cfg["feeds"],
            max_articles=topic_cfg.get("max_articles", 5),
            topic_name=topic_name,
        )
        total_articles += len(articles)

        if use_ai:
            logger.info(f"🤖 Summarizing {len(articles)} articles with Claude...")
            section = summarize_topic(topic_name, articles)
        else:
            section = _plain_listing(topic_name, articles)

        sections.append(section)
        sections.append("---\n")

    # Footer
    sections.append(
        f"\n_Generated at {now.strftime('%Y-%m-%d %H:%M UTC')} · "
        f"{total_articles} articles processed across {len(config.TOPICS)} topics._\n"
    )

    return "\n".join(sections)


def _plain_listing(topic_name: str, articles: list[dict]) -> str:
    """Simple article listing without AI summarization."""
    if not articles:
        return f"## {topic_name}\n\n_No new articles found._\n"

    lines = [f"## {topic_name}\n"]
    for a in articles:
        pub = (
            a["published"].strftime("%Y-%m-%d %H:%M")
            if a["published"]
            else "Unknown"
        )
        lines.append(f"- **[{a['title']}]({a['link']})** — {a['author']} · {pub}")
        if a.get("summary"):
            lines.append(f"  > {a['summary'][:200]}...")
        lines.append("")
    return "\n".join(lines)


def save_digest(content: str) -> Path:
    """Save digest to a date-stamped Markdown file."""
    output_dir = config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    date_stamp = datetime.now().strftime("%Y-%m-%d")
    filepath = output_dir / f"digest-{date_stamp}.md"

    filepath.write_text(content, encoding="utf-8")
    return filepath


def main():
    parser = argparse.ArgumentParser(
        description="Medium Daily Digest Agent — AI-curated tech reading"
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=None,
        help=f"Override lookback days (default: {config.LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip Claude summarization, just list articles",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to stdout instead of saving to file",
    )
    args = parser.parse_args()

    # Apply overrides
    if args.lookback:
        config.LOOKBACK_DAYS = args.lookback

    logger.info("🚀 Medium Daily Digest Agent starting...")
    logger.info(
        f"   Topics: {len(config.TOPICS)} | "
        f"Lookback: {config.LOOKBACK_DAYS} day(s) | "
        f"AI: {'on' if not args.no_ai else 'off'}"
    )

    digest = build_digest(use_ai=not args.no_ai)

    if args.dry_run:
        print(digest)
    else:
        filepath = save_digest(digest)
        logger.info(f"✅ Digest saved to: {filepath}")
        print(f"\n📄 Digest saved: {filepath}")


if __name__ == "__main__":
    main()
