"""
Medium Daily Digest Agent - Configuration
==========================================
Customize your topics, feeds, and output preferences here.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# ANTHROPIC API
# ---------------------------------------------------------------------------
# Set your API key as an environment variable: ANTHROPIC_API_KEY
# Or hardcode it here (not recommended for shared machines):
# ANTHROPIC_API_KEY = "sk-ant-..."

# Model to use for summarization
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ---------------------------------------------------------------------------
# TOPICS & RSS FEEDS
# ---------------------------------------------------------------------------
# Medium exposes RSS feeds at: https://medium.com/feed/tag/<tag>
# You can also add publication feeds: https://medium.com/feed/<publication>

TOPICS = {
    "MacBooks & macOS Development": {
        "feeds": [
            "https://medium.com/feed/tag/macbook",
            "https://medium.com/feed/tag/macos",
            "https://medium.com/feed/tag/mac-development",
            "https://medium.com/feed/tag/apple-silicon",
            "https://medium.com/feed/tag/xcode",
        ],
        "max_articles": 5,
    },
    "AI Tools & Frameworks": {
        "feeds": [
            "https://medium.com/feed/tag/artificial-intelligence",
            "https://medium.com/feed/tag/ai-tools",
            "https://medium.com/feed/tag/large-language-models",
            "https://medium.com/feed/tag/langchain",
            "https://medium.com/feed/tag/claude-ai",
            "https://medium.com/feed/tag/generative-ai",
            "https://medium.com/feed/tag/ai-agents",
        ],
        "max_articles": 5,
    },
    "Software Engineering": {
        "feeds": [
            "https://medium.com/feed/tag/software-engineering",
            "https://medium.com/feed/tag/python",
            "https://medium.com/feed/tag/golang",
            "https://medium.com/feed/tag/react",
            "https://medium.com/feed/tag/nodejs",
            "https://medium.com/feed/tag/coding",
        ],
        "max_articles": 5,
    },
    "DevOps & Platform Engineering": {
        "feeds": [
            "https://medium.com/feed/tag/devops",
            "https://medium.com/feed/tag/platform-engineering",
            "https://medium.com/feed/tag/kubernetes",
            "https://medium.com/feed/tag/backstage",
            "https://medium.com/feed/tag/docker",
            "https://medium.com/feed/tag/github-actions",
            "https://medium.com/feed/tag/infrastructure-as-code",
        ],
        "max_articles": 5,
    },
    "Information Security": {
        "feeds": [
            "https://medium.com/feed/tag/infosec",
            "https://medium.com/feed/tag/cybersecurity",
            "https://medium.com/feed/tag/application-security",
            "https://medium.com/feed/tag/zero-trust",
            "https://medium.com/feed/tag/devsecops",
            "https://medium.com/feed/tag/penetration-testing",
        ],
        "max_articles": 5,
    },
}

# ---------------------------------------------------------------------------
# CONTENT EXTRACTION
# ---------------------------------------------------------------------------
# Use Jina Reader (free, no API key needed) to extract article text
JINA_READER_PREFIX = "https://r.jina.ai/"

# Maximum characters to extract per article (to control token usage)
MAX_CONTENT_CHARS = 3000

# Only include articles published in the last N days
LOOKBACK_DAYS = 1

# ---------------------------------------------------------------------------
# FALLBACK: GOOGLE NEWS RSS
# ---------------------------------------------------------------------------
# If Medium RSS is blocked (403), use Google News RSS filtered to medium.com
# Format: https://news.google.com/rss/search?q=<query>+site:medium.com&hl=en-US&gl=US
ENABLE_GOOGLE_NEWS_FALLBACK = True

GOOGLE_NEWS_QUERIES = {
    "MacBooks & macOS Development": [
        "macbook development site:medium.com",
        "macos developer tools site:medium.com",
        "apple silicon programming site:medium.com",
    ],
    "AI Tools & Frameworks": [
        "AI tools 2026 site:medium.com",
        "large language model framework site:medium.com",
        "AI agents development site:medium.com",
        "generative AI tools site:medium.com",
    ],
    "Software Engineering": [
        "software engineering best practices site:medium.com",
        "python golang development site:medium.com",
        "react nodejs site:medium.com",
    ],
    "DevOps & Platform Engineering": [
        "devops platform engineering site:medium.com",
        "kubernetes backstage site:medium.com",
        "github actions docker site:medium.com",
    ],
    "Information Security": [
        "cybersecurity infosec site:medium.com",
        "application security devsecops site:medium.com",
        "zero trust security site:medium.com",
    ],
}

# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
# Directory where daily markdown summaries are saved
OUTPUT_DIR = Path.home() / "medium-digests"

# ---------------------------------------------------------------------------
# SCHEDULING (for reference — configure via cron / launchd)
# ---------------------------------------------------------------------------
# Recommended cron (runs daily at 7:00 AM):
#   0 7 * * * cd ~/medium-digest-agent && python main.py
#
# macOS launchd plist is generated by: python setup_schedule.py
