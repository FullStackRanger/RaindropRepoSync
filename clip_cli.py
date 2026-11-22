#!/usr/bin/env python3
"""JSON command-line front end to the web clipper engine, used by the macOS app (macos/WebClipper).

Every command prints one JSON object to stdout; failures print ``{"error": "..."}`` and exit 1.
Commands that take structured input read a JSON object from stdin.

    clip_cli.py clip URL                      -> {"article": {...}, "tags": "...", "info": "..."}
    clip_cli.py save            < {"article", "title", "tags", "body", "folder"}  -> {"path"}
    clip_cli.py copy-to-vault   < {"path", "vault", "folder", "tags"}             -> {"path"}
    clip_cli.py vault-info VAULT              -> {"exists", "is_vault", "folders": [...]}
    clip_cli.py relative-folder VAULT FOLDER  -> {"folder"}
    clip_cli.py settings [--set < {...}]      -> {"save_dir", "copy_to_vault", "vault_path", "vault_folder"}
    clip_cli.py bookmarklet [--port N]        -> {"bookmarklet"}
    clip_cli.py serve [--port N]              -> JSON lines: {"event": "listening"|"url"|"focus"|"error", ...}

``serve`` runs the browser-button listener (clip_bridge) until stdin closes, so it exits with the app.
"""

import argparse
import json
import sys
import threading
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit

from clip_bridge import DEFAULT_PORT, ClipServer, bookmarklet
from clip_storage import (DEFAULT_TAGS, DOWNLOADS, Settings, VaultError, copy_to_vault, is_obsidian_vault,
                          list_vault_folders, normalize_tag, note_filename, parse_tags, relative_vault_folder,
                          save_note)
from web_clip import Article, ClipError, build_note, clip_url


class CliError(Exception):
    pass


def _emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _read_input() -> Dict[str, Any]:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError as e:
        raise CliError(f"invalid JSON input: {e}") from None
    if not isinstance(data, dict):
        raise CliError("expected a JSON object on stdin")
    return data


def _article(data: Any) -> Article:
    if not isinstance(data, dict):
        raise CliError("missing article")
    known = {f.name for f in fields(Article)}
    return Article(**{k: v for k, v in data.items() if k in known})


def article_info(article: Article) -> str:
    details = [urlsplit(article.url).netloc, article.author, article.published and f"published {article.published}"]
    return " \u00b7 ".join(d for d in details if d) + f" \u00b7 {len(article.markdown.split())} words"


def cmd_clip(url: str) -> Dict[str, Any]:
    article = clip_url(url)
    keywords = [normalize_tag(k) for k in article.tags[:5]]
    tags = " ".join(parse_tags(" ".join([DEFAULT_TAGS] + keywords)))
    return {"article": asdict(article), "tags": tags, "info": article_info(article)}


def cmd_save(data: Dict[str, Any]) -> Dict[str, Any]:
    article = _article(data.get("article"))
    title = str(data.get("title") or "").strip()
    if not title:
        raise CliError("Give the note a title.")
    body = data.get("body")
    note = build_note(article, tags=parse_tags(str(data.get("tags") or "")), title=title,
                      body=None if body is None else str(body))
    folder = str(data.get("folder") or "").strip() or str(DOWNLOADS)
    path = save_note(note, folder, note_filename(title, fallback=urlsplit(article.url).netloc))
    return {"path": str(path)}


def cmd_copy_to_vault(data: Dict[str, Any]) -> Dict[str, Any]:
    path = copy_to_vault(str(data.get("path") or ""), str(data.get("vault") or "").strip(),
                         str(data.get("folder") or ""), tags=parse_tags(str(data.get("tags") or "")))
    return {"path": str(path)}


def cmd_vault_info(vault: str) -> Dict[str, Any]:
    exists = bool(vault) and Path(vault).expanduser().is_dir()
    return {"exists": exists, "is_vault": exists and is_obsidian_vault(vault),
            "folders": list_vault_folders(vault) if exists else []}


def cmd_settings(update: bool) -> Dict[str, Any]:
    settings = Settings.load()
    if update:
        data = _read_input()
        for f in fields(Settings):
            if f.name in data and isinstance(data[f.name], type(getattr(settings, f.name))):
                setattr(settings, f.name, data[f.name])
        settings.save()
    result = asdict(settings)
    result["save_dir"] = result["save_dir"] or str(DOWNLOADS)
    return result


def cmd_serve(port: int) -> int:
    lock = threading.Lock()

    def emit(payload: Dict[str, Any]) -> None:
        with lock:
            _emit(payload)

    server = ClipServer(on_url=lambda url: emit({"event": "url", "url": url}),
                        on_focus=lambda: emit({"event": "focus"}), port=port)
    try:
        bound = server.start()
    except OSError as e:
        emit({"event": "error", "message": f"port {port} busy: {e}"})
        return 2
    emit({"event": "listening", "port": bound})
    try:
        sys.stdin.read()
    except KeyboardInterrupt:
        pass
    server.stop()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="JSON interface to the web clipper engine.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("clip").add_argument("url")
    sub.add_parser("save")
    sub.add_parser("copy-to-vault")
    sub.add_parser("vault-info").add_argument("vault")
    rel = sub.add_parser("relative-folder")
    rel.add_argument("vault")
    rel.add_argument("folder")
    sub.add_parser("settings").add_argument("--set", action="store_true", help="update from a JSON object on stdin")
    sub.add_parser("bookmarklet").add_argument("--port", type=int, default=DEFAULT_PORT)
    sub.add_parser("serve").add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    if args.command == "serve":
        return cmd_serve(args.port)
    try:
        if args.command == "clip":
            result = cmd_clip(args.url)
        elif args.command == "save":
            result = cmd_save(_read_input())
        elif args.command == "copy-to-vault":
            result = cmd_copy_to_vault(_read_input())
        elif args.command == "vault-info":
            result = cmd_vault_info(args.vault)
        elif args.command == "relative-folder":
            result = {"folder": relative_vault_folder(args.vault, args.folder)}
        elif args.command == "settings":
            result = cmd_settings(args.set)
        else:
            result = {"bookmarklet": bookmarklet(args.port)}
    except (ClipError, VaultError, CliError) as e:
        _emit({"error": str(e)})
        return 1
    except OSError as e:
        _emit({"error": f"{type(e).__name__}: {e}"})
        return 1
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
