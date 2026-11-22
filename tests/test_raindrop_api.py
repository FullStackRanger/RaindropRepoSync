import io
import json
import urllib.error

import pytest

from md_links import Link
from raindrop_api import (
    UNSORTED_COLLECTION_ID,
    RaindropClient,
    RaindropError,
    build_collection_tree,
)


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, payload=None, headers=None):
    body = io.BytesIO(json.dumps(payload or {}).encode("utf-8"))
    return urllib.error.HTTPError("https://api", code, "err", headers or {}, body)


class FakeTransport:
    """Routes (method, path) to a handler returning a payload or raising."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, req, timeout):
        path = req.full_url.replace("https://api.raindrop.io/rest/v1", "")
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.calls.append((req.get_method(), path, body, dict(req.header_items())))
        handler = self.routes[(req.get_method(), path)]
        result = handler(body) if callable(handler) else handler
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)


def make_client(routes, **kwargs):
    transport = FakeTransport(routes)
    sleeps = []
    client = RaindropClient("tok", transport=transport, sleep=sleeps.append, **kwargs)
    return client, transport, sleeps


def test_requires_token():
    with pytest.raises(RaindropError):
        RaindropClient("")


def test_get_collections_builds_nested_paths():
    client, transport, _ = make_client({
        ("GET", "/collections"): {"result": True, "items": [
            {"_id": 1, "title": "Work", "count": 3},
            {"_id": 2, "title": "reading"},
        ]},
        ("GET", "/collections/childrens"): {"result": True, "items": [
            {"_id": 10, "title": "Python", "parent": {"$id": 1}, "count": 5},
            {"_id": 11, "title": "Async", "parent": {"$id": 10}},
        ]},
    })
    collections = client.get_collections()
    assert [(c.id, c.path) for c in collections] == [
        (UNSORTED_COLLECTION_ID, "Unsorted"),
        (2, "reading"),
        (1, "Work"),
        (10, "Work / Python"),
        (11, "Work / Python / Async"),
    ]
    assert collections[3].count == 5
    assert transport.calls[0][3]["Authorization"] == "Bearer tok"


def test_collection_tree_tolerates_missing_parent_and_cycles():
    tree = build_collection_tree(
        [],
        [
            {"_id": 5, "title": "Orphan", "parent": {"$id": 999}},
            {"_id": 6, "title": "A", "parent": {"$id": 7}},
            {"_id": 7, "title": "B", "parent": {"$id": 6}},
        ],
    )
    paths = {c.id: c.path for c in tree}
    assert paths[5] == "Orphan"
    assert paths[6].endswith("A") and paths[7].endswith("B")


def test_create_bookmark_payload():
    client, transport, _ = make_client({
        ("POST", "/raindrop"): {"result": True, "item": {"_id": 42}},
    })
    item = client.create_bookmark("https://x.example", 7, title="X", tags=["md", ""])
    assert item == {"_id": 42}
    method, path, body, headers = transport.calls[0]
    assert body == {
        "link": "https://x.example",
        "collection": {"$id": 7},
        "pleaseParse": {},
        "title": "X",
        "tags": ["md"],
    }
    assert headers["Content-type"] == "application/json"


def test_create_bookmark_omits_empty_title_and_tags():
    client, transport, _ = make_client({("POST", "/raindrop"): {"result": True, "item": {}}})
    client.create_bookmark("https://x.example", -1)
    assert transport.calls[0][2] == {"link": "https://x.example", "collection": {"$id": -1}, "pleaseParse": {}}


def test_api_result_false_raises():
    client, _, _ = make_client({("GET", "/collections"): {"result": False, "errorMessage": "bad"}})
    with pytest.raises(RaindropError, match="bad"):
        client.request("GET", "/collections")


def test_unauthorized_message():
    client, _, _ = make_client({("GET", "/collections"): http_error(401)})
    with pytest.raises(RaindropError, match="token") as info:
        client.request("GET", "/collections")
    assert info.value.status == 401


def test_rate_limit_is_retried():
    attempts = []

    def handler(body):
        attempts.append(1)
        return http_error(429, headers={"Retry-After": "3"}) if len(attempts) < 3 else {"result": True, "item": {}}

    client, _, sleeps = make_client({("POST", "/raindrop"): handler})
    client.create_bookmark("https://x.example", 1)
    assert len(attempts) == 3
    assert sleeps == [3.0, 3.0]


def test_rate_limit_gives_up_after_max_retries():
    client, _, sleeps = make_client({("POST", "/raindrop"): http_error(429)}, max_retries=2)
    with pytest.raises(RaindropError) as info:
        client.create_bookmark("https://x.example", 1)
    assert info.value.status == 429
    assert sleeps == [2.0, 4.0]


def test_network_error_is_wrapped():
    client, _, _ = make_client({("GET", "/collections"): urllib.error.URLError("no route")})
    with pytest.raises(RaindropError, match="Network error"):
        client.request("GET", "/collections")


def test_find_existing_batches_requests():
    urls = [f"https://e.example/{i}" for i in range(150)]

    def handler(body):
        dups = [{"_id": 1000 + i, "link": u} for i, u in enumerate(body["urls"]) if u.endswith("/5") or u.endswith("/120")]
        return {"result": True, "duplicates": dups}

    client, transport, _ = make_client({("POST", "/import/url/exists"): handler})
    existing = client.find_existing(urls)
    assert len(transport.calls) == 2
    assert len(transport.calls[0][2]["urls"]) == 100
    assert set(existing) == {"https://e.example/5", "https://e.example/120"}


def test_save_links_reports_progress_skips_and_errors():
    def create(body):
        if body["link"] == "https://bad.example":
            return http_error(400, {"errorMessage": "invalid link"})
        return {"result": True, "item": {"_id": 1}}

    client, transport, _ = make_client({
        ("POST", "/import/url/exists"): {"result": True, "duplicates": [{"_id": 9, "link": "https://dup.example"}]},
        ("POST", "/raindrop"): create,
    })
    links = [Link("https://ok.example", "OK"), Link("https://dup.example"), Link("https://bad.example")]
    progress = []
    results = client.save_links(links, 3, tags=["t"], progress=lambda i, n, r: progress.append((i, n, r.url)))

    assert [(r.url, r.ok, r.skipped) for r in results] == [
        ("https://ok.example", True, False),
        ("https://dup.example", True, True),
        ("https://bad.example", False, False),
    ]
    assert results[1].raindrop_id == 9
    assert "invalid link" in results[2].error
    assert progress == [(1, 3, "https://ok.example"), (2, 3, "https://dup.example"), (3, 3, "https://bad.example")]
    created = [c[2]["link"] for c in transport.calls if c[1] == "/raindrop"]
    assert created == ["https://ok.example", "https://bad.example"]


def test_save_links_without_skip_existing_does_not_check():
    client, transport, _ = make_client({("POST", "/raindrop"): {"result": True, "item": {"_id": 1}}})
    client.save_links([Link("https://a.example")], 1, skip_existing=False)
    assert [c[1] for c in transport.calls] == ["/raindrop"]


def test_save_links_can_be_stopped():
    client, _, _ = make_client({("POST", "/raindrop"): {"result": True, "item": {}}})
    links = [Link(f"https://e.example/{i}") for i in range(5)]
    seen = []
    results = client.save_links(links, 1, skip_existing=False,
                                progress=lambda i, n, r: seen.append(i), should_stop=lambda: len(seen) >= 2)
    assert len(results) == 2
