"""Minimal Raindrop.io REST client (stdlib only) for listing collections and saving bookmarks."""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

API_BASE = "https://api.raindrop.io/rest/v1"
UNSORTED_COLLECTION_ID = -1
EXISTS_BATCH_SIZE = 100


class RaindropError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass
class Collection:
    id: int
    title: str
    path: str
    count: int = 0


@dataclass
class SaveResult:
    url: str
    ok: bool
    error: str = ""
    skipped: bool = False
    raindrop_id: Optional[int] = None


Transport = Callable[[urllib.request.Request, float], Any]


def _default_transport(req: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(req, timeout=timeout)


class RaindropClient:
    def __init__(
        self,
        token: str,
        base_url: str = API_BASE,
        transport: Transport = _default_transport,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 30,
        max_retries: int = 3,
    ):
        if not token:
            raise RaindropError("Missing Raindrop API token")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._sleep = sleep
        self.timeout = timeout
        self.max_retries = max_retries

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
            try:
                with self._transport(req, self.timeout) as resp:
                    body = resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < self.max_retries:
                    self._sleep(_retry_delay(e.headers, attempt))
                    continue
                raise RaindropError(_http_error_message(e), status=e.code) from e
            except urllib.error.URLError as e:
                raise RaindropError(f"Network error: {e.reason}") from e

            try:
                result = json.loads(body.decode("utf-8")) if body else {}
            except ValueError as e:
                raise RaindropError("Invalid JSON in Raindrop response") from e
            if isinstance(result, dict) and result.get("result") is False:
                raise RaindropError(result.get("errorMessage") or result.get("error") or "Raindrop API error")
            return result
        raise RaindropError("Rate limited by Raindrop API", status=429)

    def get_collections(self) -> List[Collection]:
        """All collections (root + nested), sorted by their "Parent / Child" path, plus Unsorted first."""
        roots = self.request("GET", "/collections").get("items", [])
        children = self.request("GET", "/collections/childrens").get("items", [])
        return build_collection_tree(roots, children)

    def find_existing(self, urls: Sequence[str]) -> Dict[str, int]:
        """Map each already-bookmarked URL (as passed in) to its raindrop id."""
        existing: Dict[str, int] = {}
        for start in range(0, len(urls), EXISTS_BATCH_SIZE):
            batch = list(urls[start:start + EXISTS_BATCH_SIZE])
            data = self.request("POST", "/import/url/exists", {"urls": batch})
            for dup in data.get("duplicates", []):
                link = dup.get("link")
                if link:
                    existing[link] = dup.get("_id")
        return {u: existing[u] for u in urls if u in existing}

    def create_bookmark(self, url: str, collection_id: int, title: str = "", tags: Iterable[str] = ()) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "link": url,
            "collection": {"$id": collection_id},
            "pleaseParse": {},
        }
        if title:
            payload["title"] = title
        tags = [t for t in tags if t]
        if tags:
            payload["tags"] = tags
        return self.request("POST", "/raindrop", payload).get("item", {})

    def save_links(
        self,
        links: Sequence[Any],
        collection_id: int,
        tags: Iterable[str] = (),
        skip_existing: bool = True,
        progress: Optional[Callable[[int, int, SaveResult], None]] = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> List[SaveResult]:
        """Save ``links`` (objects with ``url`` and ``title``) one by one, reporting each result.

        A failure for one link never aborts the rest; it is recorded in its ``SaveResult``.
        """
        tags = list(tags)
        existing: Dict[str, int] = {}
        if skip_existing and links:
            existing = self.find_existing([link.url for link in links])

        results: List[SaveResult] = []
        total = len(links)
        for i, link in enumerate(links, start=1):
            if should_stop():
                break
            if link.url in existing:
                result = SaveResult(link.url, ok=True, skipped=True, raindrop_id=existing[link.url])
            else:
                try:
                    item = self.create_bookmark(link.url, collection_id, link.title, tags)
                    result = SaveResult(link.url, ok=True, raindrop_id=item.get("_id"))
                except RaindropError as e:
                    result = SaveResult(link.url, ok=False, error=str(e))
            results.append(result)
            if progress:
                progress(i, total, result)
        return results


def build_collection_tree(roots: List[Dict[str, Any]], children: List[Dict[str, Any]]) -> List[Collection]:
    by_id = {c["_id"]: c for c in list(roots) + list(children)}

    def path_of(c: Dict[str, Any], seen=()) -> str:
        parent_id = (c.get("parent") or {}).get("$id")
        parent = by_id.get(parent_id)
        if parent is None or parent_id in seen:
            return c.get("title", "")
        return path_of(parent, seen + (c["_id"],)) + " / " + c.get("title", "")

    collections = [
        Collection(id=c["_id"], title=c.get("title", ""), path=path_of(c), count=c.get("count", 0))
        for c in by_id.values()
    ]
    collections.sort(key=lambda c: c.path.casefold())
    return [Collection(UNSORTED_COLLECTION_ID, "Unsorted", "Unsorted")] + collections


def _retry_delay(headers, attempt: int) -> float:
    retry_after = headers.get("Retry-After") if headers else None
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            pass
    reset = headers.get("X-RateLimit-Reset") if headers else None
    if reset:
        try:
            return min(60.0, max(1.0, float(reset) - time.time()))
        except ValueError:
            pass
    return float(2 ** (attempt + 1))


def _http_error_message(e: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        body = json.loads(e.read().decode("utf-8"))
        detail = body.get("errorMessage") or body.get("error") or ""
    except Exception:
        pass
    if e.code == 401:
        return "Unauthorized: check your Raindrop API token"
    return f"HTTP {e.code}: {detail or e.reason}"
