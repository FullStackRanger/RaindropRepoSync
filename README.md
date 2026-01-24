# Raindrop.io Bookmark Export Tools

A collection of Python CLI tools for exporting and syncing bookmarks from Raindrop.io.

## Tools

### 1. GitHub Repository Cloner (`bookmarks_github.py`)
Clones GitHub repositories from your Raindrop.io bookmark collections for offline access or archival purposes.

### 2. Medium Bookmarks Exporter (`medium_bookmarks.py`)
Exports Medium.com articles from your Raindrop.io collections to CSV format with author and title metadata.

## Features

### GitHub Repository Cloner
- Fetches bookmarks from any Raindrop.io collection via API
- Automatically identifies and filters GitHub repository URLs
- Supports both HTTPS and SSH clone URLs
- Shallow clones (depth=1) for faster downloads
- Deduplicates URLs automatically
- Dry-run mode to preview actions
- URL-only mode for listing without cloning
- Skip existing repositories to avoid duplicates

### Medium Bookmarks Exporter
- Filters Medium.com articles from Raindrop collections (including custom domains)
- Exports to CSV format with URL, author, title, and tags
- Optional metadata fetching via web scraping for accurate author names
- Supports dry-run mode
- Configurable fetch delays to respect rate limits

## Prerequisites

- Python 3.9 or higher
- Git installed and available in PATH
- Raindrop.io account with API access

## Installation

1. Clone this repository or download `bookmarks_github.py`

2. Install required Python dependencies:
```bash
# For GitHub cloner
pip install requests

# For Medium exporter (additional dependency)
pip install requests beautifulsoup4
```

3. Get your Raindrop.io API token:
   - Go to [Raindrop.io App Settings](https://app.raindrop.io/settings/integrations)
   - Create a new app or use an existing one
   - Copy the test token

## Usage

### GitHub Repository Cloner

#### Basic Usage

```bash
# Set your token as an environment variable
export RAINDROP_TOKEN="your-token-here"

# Clone repos from a collection
python bookmarks_github.py --collection-id 12345678
```

#### Command-Line Options

```bash
# Specify token directly (alternative to env var)
python bookmarks_github.py --token YOUR_TOKEN --collection-id 12345678

# Custom destination directory
python bookmarks_github.py --collection-id 12345678 --dest ./my-repos

# Use SSH clone URLs instead of HTTPS
python bookmarks_github.py --collection-id 12345678 --ssh

# Dry run - preview what would be cloned without actually cloning
python bookmarks_github.py --collection-id 12345678 --dry-run

# Just list GitHub URLs without cloning
python bookmarks_github.py --collection-id 12345678 --dump-urls
```

### Medium Bookmarks Exporter

#### Basic Usage

```bash
# Export Medium bookmarks to CSV
export RAINDROP_TOKEN="your-token-here"
python medium_bookmarks.py --collection-id 12345678
```

#### Command-Line Options

```bash
# Specify token directly
python medium_bookmarks.py --token YOUR_TOKEN --collection-id 12345678

# Custom output filename
python medium_bookmarks.py --collection-id 12345678 --output my_medium_articles.csv

# Fetch author and title from Medium pages (slower but more accurate)
python medium_bookmarks.py --collection-id 12345678 --fetch-metadata

# Adjust delay between fetches (default: 0.5 seconds)
python medium_bookmarks.py --collection-id 12345678 --fetch-metadata --delay 1.0

# Dry run - preview what would be exported
python medium_bookmarks.py --collection-id 12345678 --dry-run
```

### Finding Your Collection ID

1. Go to [Raindrop.io](https://app.raindrop.io)
2. Navigate to the collection you want to sync
3. The collection ID is in the URL: `https://app.raindrop.io/my/12345678`

## How It Works

### GitHub Repository Cloner

1. **Fetch Bookmarks**: Paginates through the Raindrop API to retrieve all items in the specified collection
2. **Filter URLs**: Identifies and normalizes GitHub repository URLs (e.g., `https://github.com/owner/repo`)
3. **Deduplicate**: Removes duplicate URLs while preserving order
4. **Clone**: Performs shallow clones (`--depth 1`) of each repository to the destination directory
5. **Skip Existing**: Automatically skips repositories that already exist in the destination

### Medium Bookmarks Exporter

1. **Fetch Bookmarks**: Retrieves all items from the specified Raindrop collection
2. **Filter Medium URLs**: Identifies Medium.com articles including custom domains (towardsdatascience.com, betterprogramming.pub, etc.)
3. **Extract Metadata**: Optionally scrapes author and title information from Medium pages
4. **Export to CSV**: Saves results with columns: URL, Writer (author), Subject (title), Tags

## Example Output

### GitHub Cloner

```
Found 15 GitHub repos. Cloning into: raindrop_github_repos
CLONE: git clone --depth 1 https://github.com/user/repo1.git raindrop_github_repos/repo1
SKIP (exists): raindrop_github_repos/repo2
CLONE: git clone --depth 1 https://github.com/user/repo3.git raindrop_github_repos/repo3
```

### Medium Exporter

```
Fetching items from collection 12345678...
Found 150 total bookmarks.
Found 23 Medium articles.
Saved 23 records to: medium_bookmarks.csv
```

## Limitations

### GitHub Cloner
- Only works with public GitHub repositories (unless you have Git credentials configured)
- Only detects standard GitHub repo URLs (e.g., `https://github.com/owner/repo`)
- Performs shallow clones by default (full history not included)

### Medium Exporter
- Metadata fetching requires web scraping, which may be slower and subject to rate limits
- Some custom Medium domains may not be detected (can be added to MEDIUM_CUSTOM_DOMAINS list)
- Author extraction from URLs works only for standard @username patterns

## API Rate Limits

The script includes a 100ms delay between API requests to respect Raindrop.io's rate limits. For very large collections (1000+ bookmarks), the script may take several minutes to complete.

## License

MIT

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.
