#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import argparse
import subprocess
from urllib.parse import urlparse, urlunparse

import requests

GITHUB_REPO_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+)$",
    re.IGNORECASE
)

def normalize_url(url: str) -> str:
    """Remove query/fragment, trim trailing slash, keep scheme/host/path only."""
    url = url.strip()
    p = urlparse(url)
    p = p._replace(query="", fragment="")
    clean = urlunparse(p).rstrip("/")
    return clean

def is_github_repo_url(url: str) -> bool:
    return GITHUB_REPO_RE.match(url) is not None

def to_clone_url(url: str, use_ssh: bool) -> str:
    """Convert https github repo URL to either https clone or ssh clone."""
    m = GITHUB_REPO_RE.match(url)
    if not m:
        return url
    owner = m.group("owner")
    repo = m.group("repo").removesuffix(".git")
    if use_ssh:
        return f"git@github.com:{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"

def raindrop_request(session: requests.Session, base_url: str, token: str, path: str, params=None):
    headers = {"Authorization": f"Bearer {token}"}
    url = base_url.rstrip("/") + path
    r = session.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_collection_items(session, base_url, token, collection_id: int, per_page=50, max_pages=200):
    """Paginate through collection items."""
    items = []
    for page in range(0, max_pages):
        data = raindrop_request(
            session, base_url, token,
            f"/raindrops/{collection_id}",
            params={"page": page, "perpage": per_page}
        )
        batch = data.get("items", [])
        if not batch:
            break
        items.extend(batch)
        time.sleep(0.1)  # be polite
    return items

def clone_repo(clone_url: str, dest_dir: str, dry_run: bool):
    repo_name = clone_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    target_path = os.path.join(dest_dir, repo_name)

    if os.path.exists(target_path):
        print(f"SKIP (exists): {target_path}")
        return

    cmd = ["git", "clone", "--depth", "1", clone_url, target_path]
    print("CLONE:", " ".join(cmd))
    if dry_run:
        return
    subprocess.check_call(cmd)

def main():
    ap = argparse.ArgumentParser(description="Clone GitHub repos from a Raindrop.io collection via API.")
    ap.add_argument("--token", default=os.getenv("RAINDROP_TOKEN"), help="Raindrop API token (or set RAINDROP_TOKEN).")
    ap.add_argument("--collection-id", type=int, required=True, help="Raindrop collection ID (numeric).")
    ap.add_argument("--dest", default="raindrop_github_repos", help="Destination folder for clones.")
    ap.add_argument("--ssh", action="store_true", help="Use SSH clone URLs (git@github.com:owner/repo.git).")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without cloning.")
    ap.add_argument("--dump-urls", action="store_true", help="Only print extracted GitHub repo URLs and exit.")
    args = ap.parse_args()

    if not args.token:
        print("Error: Missing token. Provide --token or set RAINDROP_TOKEN.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.dest, exist_ok=True)

    base_url = "https://api.raindrop.io/rest/v1"
    session = requests.Session()

    items = fetch_collection_items(session, base_url, args.token, args.collection_id)

    urls = []
    for it in items:
        link = it.get("link")
        if not link:
            continue
        clean = normalize_url(link)
        if is_github_repo_url(clean):
            urls.append(clean)

    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    if args.dump_urls:
        for u in unique_urls:
            print(u)
        return

    if not unique_urls:
        print("No GitHub repo URLs found in that collection.")
        return

    print(f"Found {len(unique_urls)} GitHub repos. Cloning into: {args.dest}")
    for u in unique_urls:
        clone_url = to_clone_url(u, use_ssh=args.ssh)
        try:
            clone_repo(clone_url, args.dest, args.dry_run)
        except subprocess.CalledProcessError as e:
            print(f"FAILED: {clone_url} ({e})", file=sys.stderr)

if __name__ == "__main__":
    main()