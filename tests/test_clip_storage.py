import json

import pytest

from clip_storage import (Settings, VaultError, copy_to_vault, list_vault_folders, note_filename,
                          parse_tags, relative_vault_folder, resolve_vault_folder, save_note,
                          set_front_matter_tags, split_front_matter)


def test_parse_tags_normalizes_and_dedupes():
    assert parse_tags("#Python, web scraping  python ai/llm, 2024, ,#") == ["Python", "web", "scraping", "ai/llm"]
    assert parse_tags("") == []
    assert parse_tags("c++ résumé") == ["c", "résumé"]


def test_set_front_matter_tags_merges_into_block_list():
    note = "---\ntitle: \"T\"\ntags:\n  - clippings\ndate: 2026-11-22\n---\n\nBody\n"
    out = set_front_matter_tags(note, ["ai", "Clippings"])
    assert out == "---\ntitle: \"T\"\ntags:\n  - clippings\n  - ai\ndate: 2026-11-22\n---\n\nBody\n"


def test_set_front_matter_tags_handles_inline_lists_and_missing_key():
    assert "tags:\n  - a\n  - b\n  - c\n" in set_front_matter_tags("---\ntags: [a, \"b\"]\n---\nx", ["c"])
    assert set_front_matter_tags("---\ntitle: x\n---\nbody", ["new"]) == "---\ntitle: x\ntags:\n  - new\n---\nbody"
    assert set_front_matter_tags("just text", ["t"]) == "---\ntags:\n  - t\n---\n\njust text"


def test_set_front_matter_tags_replace_mode():
    out = set_front_matter_tags("---\ntags:\n  - old\n---\n", ["new"], merge=False)
    lines, _ = split_front_matter(out)
    assert lines == ["tags:", "  - new"]


def test_note_filename_is_safe_for_filesystems_and_obsidian():
    assert note_filename('What is C#? A "guide": part 1/2 [draft]') == "What is C A guide part 1 2 draft.md"
    assert note_filename("   ", fallback="example.com") == "example.com.md"
    assert note_filename("...") == "Untitled.md"
    long = note_filename("word " * 60)
    assert long.endswith("word.md") and len(long) <= 123


def test_save_note_never_overwrites(tmp_path):
    first = save_note("one", tmp_path / "new", "Note.md")
    second = save_note("two", tmp_path / "new", "Note.md")
    third = save_note("three", tmp_path / "new", "Note.md")
    assert [p.name for p in (first, second, third)] == ["Note.md", "Note (2).md", "Note (3).md"]
    assert first.read_text() == "one" and third.read_text() == "three"


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "Vault"
    for d in (".obsidian", ".trash", "Clippings", "Projects/Alpha", "Projects/Beta/Deep"):
        (root / d).mkdir(parents=True)
    return root


def test_list_vault_folders_skips_hidden(vault):
    assert list_vault_folders(vault) == ["Clippings", "Projects", "Projects/Alpha", "Projects/Beta",
                                         "Projects/Beta/Deep"]
    assert list_vault_folders(vault, max_depth=1) == ["Clippings", "Projects"]
    assert list_vault_folders(vault / "missing") == []


def test_copy_to_vault_creates_folder_and_adds_tags(vault, tmp_path):
    note = save_note("---\ntitle: \"T\"\ntags:\n  - clippings\n---\n\nBody\n", tmp_path / "dl", "T.md")
    copied = copy_to_vault(note, vault, "Clippings/2026", tags=["reading"])
    assert copied == (vault / "Clippings" / "2026" / "T.md").resolve()
    assert "  - clippings\n  - reading\n" in copied.read_text()
    assert "reading" not in note.read_text()
    assert copy_to_vault(note, vault, "").parent == vault.resolve()


def test_vault_folder_must_stay_inside_vault(vault, tmp_path):
    with pytest.raises(VaultError):
        resolve_vault_folder(vault, "../escape")
    with pytest.raises(VaultError):
        resolve_vault_folder(vault, str(tmp_path))
    with pytest.raises(VaultError):
        resolve_vault_folder("", "x")
    with pytest.raises(VaultError):
        resolve_vault_folder(vault / "nope", "")
    assert resolve_vault_folder(vault, str(vault / "Projects")) == (vault / "Projects").resolve()


def test_relative_vault_folder(vault, tmp_path):
    assert relative_vault_folder(vault, vault / "Projects" / "Alpha") == "Projects/Alpha"
    assert relative_vault_folder(vault, vault) == ""
    with pytest.raises(VaultError):
        relative_vault_folder(vault, tmp_path)


def test_settings_round_trip_and_bad_files(tmp_path):
    path = tmp_path / "cfg" / "settings.json"
    assert Settings.load(path) == Settings()
    Settings(save_dir="/notes", copy_to_vault=True, vault_path="/v", vault_folder="Inbox").save(path)
    assert Settings.load(path) == Settings("/notes", True, "/v", "Inbox")

    path.write_text("{not json")
    assert Settings.load(path) == Settings()
    path.write_text(json.dumps({"save_dir": 5, "vault_path": "/v", "unknown": 1}))
    loaded = Settings.load(path)
    assert loaded.vault_path == "/v" and loaded.save_dir == Settings().save_dir


def test_settings_path_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_CLIPPER_CONFIG", str(tmp_path / "c.json"))
    Settings(save_dir="/x").save()
    assert Settings.load().save_dir == "/x"
