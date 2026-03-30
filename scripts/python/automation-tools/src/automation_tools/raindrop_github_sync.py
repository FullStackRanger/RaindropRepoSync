"""Sync GitHub repos saved in Raindrop.io to a local directory.

Connects to the Raindrop.io API, navigates a configurable collection path,
clones/pulls all saved repos in parallel, and generates a README.md.
"""

import argparse
import logging
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

API_BASE = "https://api.raindrop.io/rest/v1"
GITHUB_REPO_RE = re.compile(
    r"^https?://github\.com/([^/]+/[^/?#]+)(?:\.git|[/?#].*)?$"
)
DEFAULT_TARGET_DIR = Path.home() / "Public" / "GitHub"
DEFAULT_COLLECTION_PATH = "Personal/Technology/GitHub"

log = logging.getLogger(__name__)


class SyncError(Exception):
    """Raised when a sync operation fails."""


# --- Raindrop API -----------------------------------------------------------


def find_collection(client: httpx.Client, path: str) -> int:
    """Walk a slash-separated collection path and return the leaf collection ID.

    Example path: "Personal/Technology/GitHub"
    """
    segments = [s.strip() for s in path.split("/") if s.strip()]
    if not segments:
        raise SyncError("Collection path is empty")

    root_name, *child_names = segments

    # Find the root collection
    data = client.get(f"{API_BASE}/collections").raise_for_status().json()
    root_id: int | None = None
    for col in data.get("items", []):
        if col.get("title") == root_name:
            root_id = col["_id"]
            break
    if root_id is None:
        raise SyncError(f"Root collection '{root_name}' not found")

    if not child_names:
        return root_id

    # Fetch all children and index by parent
    data = client.get(f"{API_BASE}/collections/childrens").raise_for_status().json()
    by_parent: dict[int, list[dict]] = {}
    for col in data.get("items", []):
        pid = (col.get("parent") or {}).get("$id")
        if pid is not None:
            by_parent.setdefault(pid, []).append(col)

    # Walk remaining segments
    current_id = root_id
    for segment in child_names:
        found = None
        for col in by_parent.get(current_id, []):
            if col.get("title") == segment:
                found = col["_id"]
                break
        if found is None:
            raise SyncError(
                f"Collection '{segment}' not found under parent {current_id}"
            )
        current_id = found

    return current_id


def fetch_raindrops(client: httpx.Client, collection_id: int) -> list[dict]:
    """Fetch all bookmarks from a collection, paginating through all pages."""
    raindrops: list[dict] = []
    page = 0
    while True:
        data = (
            client.get(
                f"{API_BASE}/raindrops/{collection_id}",
                params={"perpage": 50, "page": page},
            )
            .raise_for_status()
            .json()
        )
        items = data.get("items", [])
        if not items:
            break
        raindrops.extend(items)
        page += 1
    return raindrops


# --- GitHub helpers ----------------------------------------------------------


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL, or None if invalid."""
    m = GITHUB_REPO_RE.match(url)
    if not m:
        return None
    parts = m.group(1).split("/")
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return None


def canonical_clone_url(url: str) -> str:
    """Return a clean GitHub clone URL without query strings or fragments."""
    parsed = parse_github_url(url)
    if not parsed:
        return url
    owner, repo = parsed
    return f"https://github.com/{owner}/{repo}"


# --- Git operations ----------------------------------------------------------


def clone_or_pull(repo_url: str, target_dir: Path) -> Path | None:
    """Clone a repo if absent, otherwise skip. Returns repo path."""
    parsed = parse_github_url(repo_url)
    if not parsed:
        log.warning("Skipping invalid GitHub URL: %s", repo_url)
        return None

    owner, repo = parsed
    clone_url = canonical_clone_url(repo_url)
    repo_path = target_dir / repo

    if (repo_path / ".git").is_dir():
        log.debug("Skipping existing repo %s/%s", owner, repo)
        return repo_path
    else:
        log.info("Cloning %s/%s", owner, repo)
        result = subprocess.run(
            ["git", "clone", clone_url, str(repo_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.error(
                "Clone failed for %s/%s: %s", owner, repo, result.stderr.strip()
            )
            return None

    return repo_path


def sync_repos(
    raindrops: list[dict], target_dir: Path, *, workers: int = 4
) -> list[Path]:
    """Clone/pull repos in parallel. Returns list of synced repo paths."""
    urls = [
        rd["link"]
        for rd in raindrops
        if parse_github_url(rd.get("link", "")) is not None
    ]

    results: list[Path] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(clone_or_pull, url, target_dir): url for url in urls}
        for future in as_completed(futures):
            path = future.result()
            if path is not None:
                results.append(path)

    return sorted(results)


# --- README generation -------------------------------------------------------


def get_repo_description(repo_path: Path) -> str:
    """Extract description from README.md in the repository."""
    readme_paths = [
        repo_path / "README.md",
        repo_path / "readme.md",
        repo_path / "Readme.md",
        repo_path / "README",
    ]
    
    for readme_path in readme_paths:
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                # Get first paragraph after title
                lines = [line.strip() for line in content.split("\n") if line.strip()]
                
                # Skip title lines (usually start with #)
                description_lines = []
                in_description = False
                
                for line in lines:
                    # Skip markdown headers, badges, and images
                    if line.startswith("#"):
                        in_description = True
                        continue
                    if line.startswith("[") and "]" in line and "(" in line:
                        continue  # Skip badges and images
                    if line.startswith("!"):
                        continue  # Skip images
                    
                    if in_description and line and not line.startswith("##"):
                        description_lines.append(line)
                        # Get first meaningful paragraph
                        if len(" ".join(description_lines)) > 100:
                            break
                
                if description_lines:
                    desc = " ".join(description_lines)
                    # Truncate to reasonable length
                    if len(desc) > 200:
                        desc = desc[:197] + "..."
                    return desc
            except Exception as e:
                log.debug("Failed to read README for %s: %s", repo_path.name, e)
    
    return "No description available"


def generate_readme(target_dir: Path, raindrops: list[dict]) -> None:
    """Write a README.md listing all cloned repos with descriptions."""
    meta_by_repo: dict[str, dict[str, str]] = {}
    for rd in raindrops:
        parsed = parse_github_url(rd.get("link", ""))
        if parsed:
            _, repo = parsed
            meta_by_repo[repo] = {
                "url": canonical_clone_url(rd["link"]),
                "raindrop_description": rd.get("excerpt") or rd.get("note") or "",
            }

    repos = sorted(
        entry.name
        for entry in target_dir.iterdir()
        if entry.is_dir() and (entry / ".git").is_dir()
    )

    lines = ["# GitHub Repos", "", "Repos synced from Raindrop.io.", ""]
    
    log.info("Extracting repo descriptions...")
    for repo in repos:
        meta = meta_by_repo.get(repo, {})
        url = meta.get("url", f"https://github.com/?/{repo}")
        
        # Get description from the actual repository
        repo_path = target_dir / repo
        repo_desc = get_repo_description(repo_path)
        
        line = f"- [**{repo}**]({url})"
        if repo_desc:
            line += f" — {repo_desc}"
        lines.append(line)

    readme_path = target_dir / "README.md"
    readme_path.write_text("\n".join(lines) + "\n")
    log.info("README.md written to %s", readme_path)


# --- CLI ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync GitHub repos from a Raindrop.io collection.",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=DEFAULT_TARGET_DIR,
        help=f"Directory to clone repos into (default: {DEFAULT_TARGET_DIR})",
    )
    parser.add_argument(
        "--collection-path",
        default=DEFAULT_COLLECTION_PATH,
        help=(
            "Slash-separated Raindrop.io collection path "
            f"(default: {DEFAULT_COLLECTION_PATH})"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel git operations (default: 4)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List repos without cloning or pulling",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    token = os.environ.get("RAINDROP_TOKEN")
    if not token:
        raise SyncError("Set the RAINDROP_TOKEN environment variable")

    target_dir: Path = args.target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        log.info("Finding collection at '%s'...", args.collection_path)
        collection_id = find_collection(client, args.collection_path)
        log.info("Found collection ID: %d", collection_id)

        log.info("Fetching bookmarks...")
        raindrops = fetch_raindrops(client, collection_id)
        log.info("Found %d bookmarks", len(raindrops))

        github_raindrops = [
            rd for rd in raindrops if parse_github_url(rd.get("link", "")) is not None
        ]
        log.info("%d are valid GitHub repo URLs", len(github_raindrops))

        if args.dry_run:
            log.info("\nDry run — repos that would be synced:")
            for rd in github_raindrops:
                parsed = parse_github_url(rd["link"])
                if parsed:
                    log.info("  %s/%s", *parsed)
            return

        log.info("\nSyncing repos (workers=%d)...", args.workers)
        sync_repos(github_raindrops, target_dir, workers=args.workers)
        generate_readme(target_dir, raindrops)

    log.info("Done.")
