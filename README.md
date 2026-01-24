# Bookmarks to GitHub Sync

A Python CLI tool that clones GitHub repositories from your Raindrop.io bookmark collections. This tool fetches bookmarks via the Raindrop API, filters for GitHub repository URLs, and batch-clones them locally for offline access or archival purposes.

## Features

- Fetches bookmarks from any Raindrop.io collection via API
- Automatically identifies and filters GitHub repository URLs
- Supports both HTTPS and SSH clone URLs
- Shallow clones (depth=1) for faster downloads
- Deduplicates URLs automatically
- Dry-run mode to preview actions
- URL-only mode for listing without cloning
- Skip existing repositories to avoid duplicates

## Prerequisites

- Python 3.9 or higher
- Git installed and available in PATH
- Raindrop.io account with API access

## Installation

1. Clone this repository or download `bookmarks_github.py`

2. Install required Python dependencies:
```bash
pip install requests
```

3. Get your Raindrop.io API token:
   - Go to [Raindrop.io App Settings](https://app.raindrop.io/settings/integrations)
   - Create a new app or use an existing one
   - Copy the test token

## Usage

### Basic Usage

```bash
# Set your token as an environment variable
export RAINDROP_TOKEN="your-token-here"

# Clone repos from a collection
python bookmarks_github.py --collection-id 12345678
```

### Command-Line Options

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

### Finding Your Collection ID

1. Go to [Raindrop.io](https://app.raindrop.io)
2. Navigate to the collection you want to sync
3. The collection ID is in the URL: `https://app.raindrop.io/my/12345678`

## How It Works

1. **Fetch Bookmarks**: Paginates through the Raindrop API to retrieve all items in the specified collection
2. **Filter URLs**: Identifies and normalizes GitHub repository URLs (e.g., `https://github.com/owner/repo`)
3. **Deduplicate**: Removes duplicate URLs while preserving order
4. **Clone**: Performs shallow clones (`--depth 1`) of each repository to the destination directory
5. **Skip Existing**: Automatically skips repositories that already exist in the destination

## Example Output

```
Found 15 GitHub repos. Cloning into: raindrop_github_repos
CLONE: git clone --depth 1 https://github.com/user/repo1.git raindrop_github_repos/repo1
SKIP (exists): raindrop_github_repos/repo2
CLONE: git clone --depth 1 https://github.com/user/repo3.git raindrop_github_repos/repo3
```

## Limitations

- Only works with public GitHub repositories (unless you have Git credentials configured)
- Only detects standard GitHub repo URLs (e.g., `https://github.com/owner/repo`)
- Performs shallow clones by default (full history not included)

## API Rate Limits

The script includes a 100ms delay between API requests to respect Raindrop.io's rate limits. For very large collections (1000+ bookmarks), the script may take several minutes to complete.

## License

MIT

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.
