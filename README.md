# Toolbelt

A collection of Python automation tools for personal productivity and content management.

## Tools

### 1. Raindrop GitHub Sync (`raindrop-github-sync`)

Syncs GitHub repositories from your Raindrop.io bookmark collections to a local directory.

**Features:**
- Fetches bookmarks from **all collections** or a specific Raindrop.io collection via API
- Automatically identifies and filters GitHub repository URLs from bookmarks
- Clones repositories with shallow clone (--depth 1) for faster syncing
- Skips existing repositories to avoid duplicates
- Supports both HTTPS and SSH clone URLs
- Dry-run mode to preview actions without cloning
- URL dump mode to just list GitHub repos found

**Installation:**
```bash
cd scripts/python/automation-tools
pip install -e .
```

**Usage:**
```bash
# Set your token
export RAINDROP_TOKEN="your-token-here"

# Fetch ALL bookmarks from all collections (default behavior)
python bookmarks_github.py --dest ~/Public/GitHub

# Fetch from a specific collection only
python bookmarks_github.py --collection-id 12345 --dest ~/Public/GitHub

# Dry run to preview what would be cloned
python bookmarks_github.py --dry-run

# Use SSH clone URLs instead of HTTPS
python bookmarks_github.py --ssh

# Just dump the GitHub URLs found (no cloning)
python bookmarks_github.py --dump-urls
```

### 2. Medium Daily Digest Agent

An AI-powered agent that curates and summarizes Medium articles across your key technical interests, delivering a daily Markdown digest.

**Topics Tracked:**
- MacBooks & macOS Development
- AI Tools & Frameworks  
- Software Engineering
- DevOps & Platform Engineering
- Information Security

**Quick Start:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python run.py
```

See the [Medium Digest documentation](scripts/python/medium-digest-agent/README.md) for full details.

## Prerequisites

- Python 3.12 or higher
- Git installed and available in PATH
- API keys for respective services (Raindrop.io, Anthropic)

## Project Structure

```
toolbelt/
├── scripts/
│   └── python/
│       ├── automation-tools/     # Raindrop sync and other utilities
│       └── medium-digest-agent/  # AI article curation
├── tests/
└── README.md
```

## License

MIT
