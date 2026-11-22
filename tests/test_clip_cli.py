import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import clip_cli
from web_clip import Article

ROOT = Path(__file__).resolve().parent.parent


def run(monkeypatch, capsys, argv, stdin=None):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin) if stdin is not None else ""))
    code = clip_cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_CLIPPER_CONFIG", str(tmp_path / "settings.json"))


def test_clip_returns_article_tags_and_info(monkeypatch, capsys):
    article = Article(title="Hello", markdown="one two three", url="https://example.com/a",
                      author="Ann", tags=["AI", "Machine Learning"])
    monkeypatch.setattr(clip_cli, "clip_url", lambda url: article)
    code, out = run(monkeypatch, capsys, ["clip", "https://example.com/a"])
    assert code == 0
    assert out["article"]["title"] == "Hello"
    assert out["tags"] == "clippings AI Machine-Learning"
    assert out["info"] == "example.com \u00b7 Ann \u00b7 3 words"


def test_clip_error_is_json(monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, ["clip", "mailto:x@example.com"])
    assert code == 1
    assert "error" in out


def test_save_uses_edited_title_tags_and_body(tmp_path, monkeypatch, capsys):
    request = {"article": {"title": "Old", "url": "https://example.com/", "markdown": "old", "bogus": 1},
               "title": "New: Title", "tags": "a, b", "body": "Edited body\n", "folder": str(tmp_path / "out")}
    code, out = run(monkeypatch, capsys, ["save"], request)
    assert code == 0
    path = Path(out["path"])
    assert path.name == "New Title.md"
    text = path.read_text()
    assert 'title: "New: Title"' in text and "  - a\n  - b" in text and text.endswith("Edited body\n")


def test_save_requires_title(monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, ["save"], {"article": {"url": "https://x.org"}, "title": " "})
    assert code == 1 and out["error"] == "Give the note a title."


def test_vault_info_and_copy(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Clips" / "Web").mkdir(parents=True)
    code, out = run(monkeypatch, capsys, ["vault-info", str(vault)])
    assert out == {"exists": True, "is_vault": True, "folders": ["Clips", "Clips/Web"]}

    note = tmp_path / "n.md"
    note.write_text("---\ntitle: n\ntags:\n  - x\n---\nbody\n")
    code, out = run(monkeypatch, capsys, ["copy-to-vault"],
                    {"path": str(note), "vault": str(vault), "folder": "Clips/Web", "tags": "y"})
    assert code == 0
    copied = Path(out["path"])
    assert copied.parent == (vault / "Clips" / "Web").resolve()
    assert "  - x\n  - y" in copied.read_text()

    code, out = run(monkeypatch, capsys, ["relative-folder", str(vault), str(tmp_path)])
    assert code == 1 and "not inside the vault" in out["error"]


def test_settings_round_trip(monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, ["settings", "--set"],
                    {"vault_path": "/v", "copy_to_vault": True, "save_dir": 5})
    assert out["vault_path"] == "/v" and out["copy_to_vault"] is True and out["save_dir"].endswith("Downloads")
    code, out = run(monkeypatch, capsys, ["settings"])
    assert out["vault_path"] == "/v"


def test_serve_streams_events():
    proc = subprocess.Popen([sys.executable, str(ROOT / "clip_cli.py"), "serve", "--port", "0"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT)
    try:
        first = json.loads(proc.stdout.readline())
        assert first["event"] == "listening"
        import clip_bridge
        assert clip_bridge.send_url("https://example.com/x", first["port"])
        assert json.loads(proc.stdout.readline()) == {"event": "url", "url": "https://example.com/x"}
    finally:
        proc.stdin.close()
        assert proc.wait(timeout=5) == 0
