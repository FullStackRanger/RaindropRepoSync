# Toolbelt

A collection of Python automation tools for personal productivity and content management.

## Scripts

| Script | Description |
| --- | --- |
| [`bookmarks_github.py`](bookmarks_github.py) | Clone GitHub repos bookmarked in Raindrop.io (CLI). |
| [`medium_bookmarks.py`](medium_bookmarks.py) | Export Medium bookmarks from a Raindrop.io collection to CSV. |
| [`run.py`](run.py) | Run the Medium Daily Digest Agent. |
| [`setup_schedule.py`](setup_schedule.py) | Install/remove a macOS launchd schedule for the Medium digest. |
| [`web_clipper.py`](web_clipper.py) | GUI to clip a web page to a Markdown note (front matter, tags), optionally copied into an Obsidian vault; listens for the browser button. |
| [`web_clip.py`](web_clip.py) | Library for `web_clipper.py`: fetch a page, extract the main article, convert it to Markdown with front matter. |
| [`clip_storage.py`](clip_storage.py) | Library for `web_clipper.py`: safe file names, saving, Obsidian vault copy, front-matter tags, remembered settings. |
| [`clip_bridge.py`](clip_bridge.py) | Library for `web_clipper.py`: localhost listener (127.0.0.1:47811) that receives URLs from the browser button. |
| [`browser/web-clipper/`](browser/web-clipper/) | Chrome/Firefox (Manifest V3) "Send to Web Clipper" button extension; a bookmarklet is also available. |

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

### 3. Web Clipper (`web_clipper.py`)

A tkinter app that turns a web page into a clean Markdown note, plus a browser button that sends the current tab to it.

**Features:**
- Takes a URL pasted into the window, from the clipboard (pre-filled on launch), passed on the command line, or sent by the browser button
- Extracts the main article (drops navigation, sidebars, share buttons, ads, cookie banners, hidden elements) and converts it to Markdown: headings, emphasis, links and images made absolute, nested lists, code blocks with language, tables, quotes
- YAML front matter with `title`, `source`, `date` (clipped), `tags`, plus `author`, `published`, `site` and `description` when the page provides them
- Edit the title, tags and Markdown before saving; files are never overwritten (`Title (2).md`)
- Save folder defaults to `~/Downloads`, with one-click `~/Documents` or Browse; the last choice is remembered
- Optionally copies the saved note into a folder of your Obsidian vault (pick from the vault's folders, browse, or type a new one), merging the tags into its front matter; then **Open in Obsidian**
- Vault path, vault folder, save folder and the copy checkbox are remembered in `~/.config/toolbelt/web_clipper.json` (override with `WEB_CLIPPER_CONFIG`)

```markdown
---
title: "Things we learned about LLMs in 2024"
source: "https://simonwillison.net/2024/Dec/31/llms-in-2024/"
author: "Simon Willison"
date: 2026-11-22
site: "Simon Willison’s Weblog"
tags:
  - clippings
  - ai
---

A *lot* has happened in the world of Large Language Models…
```

**Usage:**
```bash
python web_clipper.py                        # paste a URL in the window
python web_clipper.py https://example.com    # clip straight away (or hand it to the open window)
python web_clipper.py URL --no-gui --save-to ~/Notes --tags reading,ai   # no window, prints the path
```

Shortcuts: Return in the URL box clips, ⌘S / Ctrl+S saves, ⌘L / Ctrl+L focuses the URL box.

Uses only the standard library (no new dependencies). Logic lives in `web_clip.py`, `clip_storage.py` and `clip_bridge.py`, tested in `tests/test_web_clip.py`, `tests/test_clip_storage.py` and `tests/test_clip_bridge.py`.

#### macOS setup

1. **Python with Tk.** The python.org installer includes Tk. With Homebrew: `brew install python python-tk` (match the version, e.g. `python-tk@3.12`). Check with `python3 -m tkinter` (a small window should open).
2. **Start the clipper** from this repo: `python3 web_clipper.py`. The window shows *Browser button: listening on 127.0.0.1:47811*. Leave it open (minimised is fine) while you browse. Running it again just brings the open window forward.
3. **Add a browser button** (pick one or more):
   - **Chrome / Edge / Brave / Arc:** open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and choose the `browser/web-clipper` folder. Pin *Send to Web Clipper* from the puzzle-piece menu. Click it (or press ⌥⇧C) on any page: the badge shows **OK** and the clipper window comes forward with the page loaded. A red **!** means the clipper isn't running.
   - **Firefox (121+):** open `about:debugging#/runtime/this-firefox`, click **Load Temporary Add-on…** and pick `browser/web-clipper/manifest.json` (temporary add-ons are removed when Firefox quits; for a permanent install, sign it via [addons.mozilla.org](https://addons.mozilla.org/developers/) as an unlisted add-on). If clicks show **!**, open `about:addons` → *Send to Web Clipper* → **Permissions** and allow access to `127.0.0.1`.
   - **Safari or any browser — bookmarklet:** click **Copy bookmarklet** in the clipper window, create a bookmark (Safari: *Bookmarks → Add Bookmark*, then *Edit Address*) and paste it as the address. It opens a tiny window that says *Sent to Web Clipper* and closes itself. The code is:
     ```text
     javascript:(()=>{window.open('http://127.0.0.1:47811/clip?url='+encodeURIComponent(location.href),'webclipper','width=380,height=170')})()
     ```
4. **Allow the window to come forward (optional).** When a URL arrives the clipper asks macOS to activate it via System Events; the first time, macOS asks whether *Terminal* (or your Python app) may control *System Events*. Allow it, or just switch to the window yourself.
5. **Start at login (optional).** Save this as `~/Library/LaunchAgents/local.toolbelt.web-clipper.plist`, replacing both paths (`which python3` and the repo path), then run `launchctl load ~/Library/LaunchAgents/local.toolbelt.web-clipper.plist`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0"><dict>
     <key>Label</key><string>local.toolbelt.web-clipper</string>
     <key>ProgramArguments</key>
     <array><string>/opt/homebrew/bin/python3</string><string>/Users/you/toolbelt/web_clipper.py</string></array>
     <key>RunAtLoad</key><true/>
   </dict></plist>
   ```

**Port:** the default is 47811. To change it, run `web_clipper.py --port N` (or set `WEB_CLIPPER_PORT`), and update `CLIPPER` in `browser/web-clipper/background.js` and `host_permissions` in its `manifest.json` (the bookmarklet from **Copy bookmarklet** uses the current port).

**Security:** the listener binds to 127.0.0.1 only, rejects requests whose `Origin` is a web page or whose `Host` isn't localhost, and accepts only http(s) URLs. A URL it receives is only fetched and previewed; nothing is saved until you press **Save note**.

## Prerequisites

- Python 3.12 or higher
- Git installed and available in PATH
- API keys for respective services (Raindrop.io, Anthropic)

## Project Structure

```
toolbelt/
├── browser/
│   └── web-clipper/              # Browser button extension for web_clipper.py
├── scripts/
│   └── python/
│       ├── automation-tools/     # Raindrop sync and other utilities
│       └── medium-digest-agent/  # AI article curation
├── tests/
└── README.md
```

## License

MIT
