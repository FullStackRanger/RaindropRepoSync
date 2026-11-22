# Toolbelt

A collection of Python automation tools for personal productivity and content management.

## Scripts

| Script | Description |
| --- | --- |
| [`bookmarks_github.py`](bookmarks_github.py) | Clone GitHub repos bookmarked in Raindrop.io (CLI). |
| [`md_to_raindrop.py`](md_to_raindrop.py) | GUI to extract links from Markdown files and save them as Raindrop.io bookmarks. |
| [`medium_bookmarks.py`](medium_bookmarks.py) | Export Medium bookmarks from a Raindrop.io collection to CSV. |
| [`run.py`](run.py) | Run the Medium Daily Digest Agent. |
| [`setup_schedule.py`](setup_schedule.py) | Install/remove a macOS launchd schedule for the Medium digest. |

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

### 2. Markdown → Raindrop.io (`md_to_raindrop.py`)

A small tkinter app that pulls every link out of one or more Markdown files and saves the ones you pick as Raindrop.io bookmarks.

**Features:**
- Extracts inline (`[text](url "title")`), reference-style (`[text][id]` / `[id]: url`), autolinks (`<url>`) and bare URLs
- Skips images and anything inside code spans or fenced code blocks; ignores non-http(s) links
- Dedupes across files (case-insensitive host, trailing slash ignored) and keeps link text as the bookmark title
- Loads your collections (including nested ones) so you can pick the destination
- Tick/untick links before saving, add tags, and optionally skip URLs already in Raindrop
- Per-link progress, a log with error details, and cancel; failed links stay selected for a retry

**Usage:**
```bash
export RAINDROP_TOKEN="your-token-here"   # or paste it into the app
python md_to_raindrop.py                  # pick files in the app
python md_to_raindrop.py notes.md todo.md # or preload files
```

Requires only the standard library (on Linux, tkinter may need `sudo apt install python3-tk`). Link extraction lives in `md_links.py` and the API client in `raindrop_api.py`.

### 3. Medium Daily Digest Agent

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
