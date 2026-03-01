"""
Medium Daily Digest Agent - Summarizer
=======================================
Uses Claude to summarize and curate articles into a daily digest.
"""

import os
import logging

from anthropic import Anthropic

from . import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a technical content curator for a Staff Engineer working in InfoSec \
and Platform Engineering at a large enterprise. Your job is to create a concise, \
insightful daily digest of Medium articles.

For each article provided, write:
1. A 2-3 sentence summary highlighting the key insight or takeaway
2. A relevance note: why this matters for a Staff Engineer focused on \
   DevOps, Platform Engineering, InfoSec, AI tooling, and macOS development
3. A quality rating: ⭐ to ⭐⭐⭐⭐⭐ based on depth, originality, and practical value

Be opinionated. Skip fluff. Highlight actionable insights. If an article is \
mostly surface-level or clickbait, say so and rate it low.

Format your response in clean Markdown. Do NOT wrap the entire response in a \
code block.
"""


def summarize_topic(topic_name: str, articles: list[dict]) -> str:
    """
    Send articles for a single topic to Claude for summarization.
    Returns a Markdown string with the curated summaries.
    """
    if not articles:
        return f"### {topic_name}\n\n_No new articles found in the last 24 hours._\n"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set!")
        raise EnvironmentError(
            "Set the ANTHROPIC_API_KEY environment variable to use Claude summarization."
        )

    client = Anthropic(api_key=api_key)

    # Build the article payload
    article_texts = []
    for i, a in enumerate(articles, 1):
        pub_date = (
            a["published"].strftime("%Y-%m-%d %H:%M UTC")
            if a["published"]
            else "Unknown date"
        )
        article_texts.append(
            f"--- Article {i} ---\n"
            f"Title: {a['title']}\n"
            f"Author: {a['author']}\n"
            f"Published: {pub_date}\n"
            f"URL: {a['link']}\n"
            f"Content:\n{a['content']}\n"
        )

    user_prompt = (
        f"Topic: {topic_name}\n\n"
        f"Here are {len(articles)} recent Medium articles on this topic. "
        f"Please summarize each one and provide your curation.\n\n"
        + "\n".join(article_texts)
    )

    try:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return f"## {topic_name}\n\n{response.content[0].text}\n"
    except Exception as e:
        logger.error(f"Claude API error for topic '{topic_name}': {e}")
        return _fallback_summary(topic_name, articles)


def _fallback_summary(topic_name: str, articles: list[dict]) -> str:
    """Generate a basic summary without Claude if the API fails."""
    lines = [f"## {topic_name}\n", "_⚠️ AI summarization unavailable — raw listings below._\n"]
    for a in articles:
        pub = (
            a["published"].strftime("%Y-%m-%d")
            if a["published"]
            else "Unknown date"
        )
        lines.append(f"### [{a['title']}]({a['link']})")
        lines.append(f"*{a['author']} · {pub}*\n")
        lines.append(f"{a.get('summary', 'No summary available.')}\n")
        lines.append("---\n")
    return "\n".join(lines)
