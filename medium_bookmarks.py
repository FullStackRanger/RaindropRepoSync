#!/usr/bin/env python3
"""
Export Medium.com bookmarks from a Raindrop.io collection to CSV.
Extracts: URL, writer (author), and subject (title/topic).
"""

import os
import re
import sys
import csv
import time
import argparse
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


MEDIUM_DOMAIN_RE = re.compile(
    r"^(www\.)?medium\.com$|\.medium\.com$|^[a-z0-9-]+\.medium\.com$",
    re.IGNORECASE
)

# Known Medium custom domains (add more as needed)
MEDIUM_CUSTOM_DOMAINS = {
    "towardsdatascience.com",
    "betterprogramming.pub",
    "levelup.gitconnected.com",
    "javascript.plainenglish.io",
    "blog.devgenius.io",
    "aws.plainenglish.io",
    "python.plainenglish.io",
    "infosecwriteups.com",
}


def is_medium_url(url: str) -> bool:
    """Check if URL is a Medium article (including custom domains)."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        
        # Direct medium.com or subdomains
        if MEDIUM_DOMAIN_RE.match(host):
            return True
        
        # Known custom domains
        if host in MEDIUM_CUSTOM_DOMAINS or host.lstrip("www.") in MEDIUM_CUSTOM_DOMAINS:
            return True
        
        return False
    except Exception:
        return False


def extract_author_from_url(url: str) -> str | None:
    """Try to extract author username from Medium URL pattern."""
    # Pattern: medium.com/@username/article-slug
    match = re.search(r"medium\.com/@([^/]+)", url)
    if match:
        return f"@{match.group(1)}"
    return None


def fetch_medium_metadata(session: requests.Session, url: str, timeout: int = 15) -> dict:
    """Scrape Medium page for author and title metadata."""
    metadata = {"author": None, "title": None}
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Try to get author from meta tags
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta and author_meta.get("content"):
            metadata["author"] = author_meta["content"]
        
        # Fallback: look for JSON-LD structured data
        if not metadata["author"]:
            for script in soup.find_all("script", {"type": "application/ld+json"}):
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        author = data.get("author")
                        if isinstance(author, dict):
                            metadata["author"] = author.get("name")
                        elif isinstance(author, str):
                            metadata["author"] = author
                        if metadata["author"]:
                            break
                except (json.JSONDecodeError, TypeError):
                    continue
        
        # Get title
        title_tag = soup.find("title")
        if title_tag:
            # Clean up " | Medium" suffix
            title = title_tag.get_text().strip()
            title = re.sub(r"\s*\|\s*Medium\s*$", "", title)
            title = re.sub(r"\s*[-–—]\s*Medium\s*$", "", title)
            metadata["title"] = title
        
        # Also try og:title
        if not metadata["title"]:
            og_title = soup.find("meta", {"property": "og:title"})
            if og_title and og_title.get("content"):
                metadata["title"] = og_title["content"]
                
    except requests.RequestException as e:
        print(f"  Warning: Could not fetch {url}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"  Warning: Error parsing {url}: {e}", file=sys.stderr)
    
    return metadata


def raindrop_request(session: requests.Session, base_url: str, token: str, path: str, params=None):
    """Make authenticated request to Raindrop API."""
    headers = {"Authorization": f"Bearer {token}"}
    url = base_url.rstrip("/") + path
    resp = session.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_collection_items(session, base_url, token, collection_id: int, per_page=50, max_pages=200):
    """Paginate through all items in a Raindrop collection."""
    items = []
    for page in range(max_pages):
        data = raindrop_request(
            session, base_url, token,
            f"/raindrops/{collection_id}",
            params={"page": page, "perpage": per_page}
        )
        batch = data.get("items", [])
        if not batch:
            break
        items.extend(batch)
        time.sleep(0.1)
    return items


def main():
    ap = argparse.ArgumentParser(
        description="Export Medium.com bookmarks from Raindrop.io to CSV."
    )
    ap.add_argument(
        "--token",
        default=os.getenv("RAINDROP_TOKEN"),
        help="Raindrop API token (or set RAINDROP_TOKEN env var)."
    )
    ap.add_argument(
        "--collection-id",
        type=int,
        required=True,
        help="Raindrop collection ID (numeric)."
    )
    ap.add_argument(
        "--output", "-o",
        default="medium_bookmarks.csv",
        help="Output CSV filename (default: medium_bookmarks.csv)."
    )
    ap.add_argument(
        "--fetch-metadata",
        action="store_true",
        help="Fetch author/title from Medium pages (slower but more accurate)."
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between fetches in seconds (default: 0.5)."
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be saved without writing CSV."
    )
    args = ap.parse_args()

    if not args.token:
        print("Error: Missing token. Provide --token or set RAINDROP_TOKEN.", file=sys.stderr)
        sys.exit(1)

    base_url = "https://api.raindrop.io/rest/v1"
    session = requests.Session()

    print(f"Fetching items from collection {args.collection_id}...")
    items = fetch_collection_items(session, base_url, args.token, args.collection_id)
    print(f"Found {len(items)} total bookmarks.")

    # Filter for Medium URLs
    medium_items = []
    for item in items:
        link = item.get("link", "")
        if is_medium_url(link):
            medium_items.append(item)

    print(f"Found {len(medium_items)} Medium articles.")

    if not medium_items:
        print("No Medium bookmarks found in this collection.")
        return

    # Build records
    records = []
    for i, item in enumerate(medium_items, 1):
        url = item.get("link", "")
        title = item.get("title", "")
        tags = ", ".join(item.get("tags", []))
        
        # Try to get author from URL first
        author = extract_author_from_url(url)
        
        # Optionally fetch from page
        if args.fetch_metadata:
            print(f"  [{i}/{len(medium_items)}] Fetching: {url[:60]}...")
            meta = fetch_medium_metadata(session, url)
            if meta["author"]:
                author = meta["author"]
            if meta["title"]:
                title = meta["title"]
            time.sleep(args.delay)
        
        records.append({
            "url": url,
            "writer": author or "Unknown",
            "subject": title,
            "tags": tags,
        })

    if args.dry_run:
        print("\n--- DRY RUN (would save these records) ---")
        for r in records:
            print(f"  {r['writer']}: {r['subject'][:50]}...")
        return

    # Write CSV
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "writer", "subject", "tags"])
        writer.writeheader()
        writer.writerows(records)

    print(f"\nSaved {len(records)} records to: {args.output}")


if __name__ == "__main__":
    main()