# 📰 Medium Daily Digest Agent

An AI-powered agent that curates and summarizes Medium articles across your key technical interests, delivering a daily Markdown digest right to your machine.

## Topics Tracked

- **MacBooks & macOS Development** — Apple Silicon, Xcode, macOS dev workflows
- **AI Tools & Frameworks** — LLMs, AI agents, LangChain, Claude, generative AI
- **Software Engineering** — Python, Go, React, Node.js, coding practices
- **DevOps & Platform Engineering** — Kubernetes, Docker, Backstage, GitHub Actions, IaC
- **Information Security** — InfoSec, AppSec, zero trust, DevSecOps, pen testing

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│ Medium RSS   │────▶│ Feed Parser  │────▶│ Jina Reader │────▶│ Claude API   │
│ Feeds (40+)  │     │ + Dedup      │     │ (content)   │     │ (summarize)  │
└─────────────┘     └──────────────┘     └─────────────┘     └──────┬───────┘
                                                                     │
                                                              ┌──────▼───────┐
                                                              │  Markdown    │
                                                              │  Digest File │
                                                              └──────────────┘
```

## Quick Start

### 1. Clone / Copy the project

```bash
# Copy to your preferred location
cp -r medium-digest-agent ~/projects/medium-digest-agent
cd ~/projects/medium-digest-agent
```

### 2. Install dependencies

**Option A: Using Poetry (recommended)**
```bash
poetry install
poetry shell
```

**Option B: Using pip**
```bash
pip install -r requirements.txt
```

### 3. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

# Or add to your shell profile:
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
```

### 4. Run it

**Using the convenience script:**
```bash
# Full AI-curated digest
python run.py

# Quick test without Claude (just lists articles)
python run.py --no-ai

# Print to terminal instead of saving
python run.py --dry-run

# Expand lookback window to 3 days
python run.py --lookback 3
```

**Or using Poetry:**
```bash
poetry run medium-digest
poetry run medium-digest --no-ai
```

Your digest will be saved to `~/medium-digests/digest-YYYY-MM-DD.md`.

## Schedule Daily Runs (macOS)

```bash
# Install the launchd agent (runs daily at 7:00 AM)
python setup_schedule.py

# Test it immediately
launchctl start com.judge.medium-digest-agent

# Remove the schedule
python setup_schedule.py --remove
```

### Alternative: cron (Linux / macOS)

```bash
# Edit crontab
crontab -e

# Add this line (runs at 7 AM daily):
0 7 * * * cd ~/projects/medium-digest-agent && /usr/bin/python3 main.py
```

## Configuration

Edit `config.py` to customize:

| Setting | Default | Description |
|---------|---------|-------------|
| `TOPICS` | 5 topics | Add/remove topics and their RSS feed URLs |
| `LOOKBACK_DAYS` | 1 | How far back to look for articles |
| `MAX_CONTENT_CHARS` | 3000 | Max chars extracted per article (controls API cost) |
| `CLAUDE_MODEL` | claude-sonnet-4-20250514 | Claude model for summarization |
| `OUTPUT_DIR` | `~/medium-digests` | Where digest files are saved |

### Adding Custom Topics

```python
# In config.py, add to TOPICS dict:
"Cloud Security": {
    "feeds": [
        "https://medium.com/feed/tag/cloud-security",
        "https://medium.com/feed/tag/aws-security",
        "https://medium.com/feed/@specific-author",  # Follow specific authors
    ],
    "max_articles": 5,
},
```

### Adding Publication Feeds

```python
# Medium publication feeds use this format:
"https://medium.com/feed/netflix-techblog"
"https://medium.com/feed/airbnb-engineering"
"https://medium.com/feed/the-pragmatic-programmer"
```

## Project Structure

```
medium-digest-agent/
├── src/
│   └── medium_digest/
│       ├── __init__.py
│       ├── main.py          # Entry point — orchestrates the pipeline
│       ├── config.py        # Topics, feeds, and settings
│       ├── fetcher.py       # RSS fetching + Jina content extraction
│       └── summarizer.py    # Claude API summarization
├── tests/
│   ├── __init__.py
│   └── test_config.py
├── run.py                   # Convenience CLI script
├── setup_schedule.py        # macOS launchd scheduling helper
├── pyproject.toml           # Poetry configuration
├── requirements.txt         # Python dependencies (legacy)
├── .gitignore
└── README.md
```

## Cost Estimate

With default settings (5 topics × 5 articles × ~3000 chars each):
- ~75K input tokens + ~10K output tokens per run
- Roughly **$0.10–0.25/day** using Claude Sonnet

## Troubleshooting

**No articles found?**
- Medium RSS feeds sometimes lag. Try `--lookback 3` to widen the window.
- Some tags have low volume. Check the feeds manually in a browser.

**Jina Reader extraction fails?**
- Paywalled articles may not extract fully. The agent falls back to RSS summaries.
- Jina has rate limits — if you hit them, reduce `max_articles` per topic.

**Claude API errors?**
- Verify `ANTHROPIC_API_KEY` is set correctly.
- The agent includes a fallback that lists articles without AI summaries.

## License

MIT — use it however you want.
