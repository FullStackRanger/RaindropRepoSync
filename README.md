# Toolbelt

A collection of Python automation tools for personal productivity and content management.

## Tools

### 1. Raindrop GitHub Sync (`raindrop-github-sync`)

Syncs GitHub repositories from your Raindrop.io bookmark collections to a local directory.

**Features:**
- Fetches bookmarks from any Raindrop.io collection via API
- Automatically identifies and filters GitHub repository URLs
- Clones repositories in parallel for faster syncing
- Skips existing repositories to avoid duplicates
- Generates comprehensive README with repo descriptions extracted from each project
- Dry-run mode to preview actions

**Installation:**
```bash
cd scripts/python/automation-tools
pip install -e .
```

**Usage:**
```bash
# Set your token
export RAINDROP_TOKEN="your-token-here"

# Sync repos (defaults to ~/Public/GitHub)
raindrop-github-sync

# Custom options
raindrop-github-sync --target-dir ./my-repos --collection-path "Personal/Tech/Projects" --workers 8

# Dry run
raindrop-github-sync --dry-run
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
