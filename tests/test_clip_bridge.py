import http.client
import json
import threading
import urllib.request

import pytest

import clip_bridge
from clip_bridge import ClipServer, bookmarklet, is_running, origin_allowed, send_url


@pytest.fixture
def server():
    received = []
    focused = threading.Event()
    srv = ClipServer(on_url=received.append, on_focus=focused.set, port=0)
    port = srv.start()
    yield srv, port, received, focused
    srv.stop()


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp.status, data


def test_ping_and_focus(server):
    _, port, _, focused = server
    status, body = request(port, "GET", "/ping")
    assert status == 200 and json.loads(body)["app"] == clip_bridge.APP_ID
    assert request(port, "GET", "/focus")[0] == 200
    assert focused.wait(2)


def test_clip_get_returns_closing_page_for_bookmarklet(server):
    _, port, received, _ = server
    status, body = request(port, "GET", "/clip?url=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1%26c%3D%3Cx%3E")
    assert status == 200
    assert "Sent to Web Clipper" in body and "&lt;x&gt;" in body and "window.close" in body
    assert received == ["https://example.com/a?b=1&c=<x>"]


def test_clip_post_json_and_form(server):
    _, port, received, _ = server
    status, body = request(port, "POST", "/clip", json.dumps({"url": "https://a.org"}),
                           {"Content-Type": "application/json", "Origin": "chrome-extension://abc"})
    assert status == 200 and json.loads(body) == {"ok": True, "url": "https://a.org"}
    request(port, "POST", "/clip", "url=https%3A%2F%2Fb.org", {"Content-Type": "application/x-www-form-urlencoded"})
    assert received == ["https://a.org", "https://b.org"]


def test_rejects_web_origins_bad_hosts_and_non_http_urls(server):
    _, port, received, _ = server
    assert request(port, "GET", "/clip?url=https://a.org", headers={"Origin": "https://evil.example"})[0] == 403
    assert request(port, "GET", "/clip?url=https://a.org", headers={"Host": "evil.example:80"})[0] == 403
    assert request(port, "GET", "/clip?url=file:///etc/passwd")[0] == 400
    assert request(port, "GET", "/clip?url=javascript:alert(1)")[0] == 400
    assert request(port, "GET", "/nope")[0] == 404
    assert received == []


def test_extension_origins_allowed():
    assert origin_allowed(None) and origin_allowed("")
    assert origin_allowed("chrome-extension://abcdef") and origin_allowed("moz-extension://1234")
    assert not origin_allowed("null") and not origin_allowed("http://127.0.0.1:47811")


def test_send_url_to_running_instance(server):
    _, port, received, _ = server
    assert is_running(port)
    assert send_url("https://example.com/x y", port)
    assert received == ["https://example.com/x y"]


def test_send_url_ignores_proxy_settings(server, monkeypatch):
    _, port, received, _ = server
    for var in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setattr(urllib.request, "_opener", None)
    assert is_running(port)
    assert send_url("https://example.com/p", port)
    assert received == ["https://example.com/p"]


def test_send_url_when_nothing_is_listening():
    srv = ClipServer(on_url=lambda u: None, port=0)
    port = srv.start()
    srv.stop()
    assert not is_running(port, timeout=0.5)
    assert not send_url("https://example.com", port, timeout=0.5)


def test_second_server_on_same_port_fails(server):
    _, port, _, _ = server
    with pytest.raises(OSError):
        ClipServer(on_url=lambda u: None, port=port).start()


def test_bookmarklet_targets_port():
    code = bookmarklet(5555)
    assert code.startswith("javascript:") and "http://127.0.0.1:5555/clip?url=" in code
    assert "encodeURIComponent(location.href)" in code
