"""Save clipped notes, copy them into an Obsidian vault and remember the user's choices."""

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import List, Optional, Tuple

HOME = Path.home()
DOWNLOADS = HOME / "Downloads"
DOCUMENTS = HOME / "Documents"
DEFAULT_TAGS = "clippings"

# Characters Obsidian can't use in note names / links, plus path separators.
_BAD_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|#^\[\]\x00-\x1f]")


def default_settings_path() -> Path:
    override = os.environ.get("WEB_CLIPPER_CONFIG")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
    return base / "toolbelt" / "web_clipper.json"


@dataclass
class Settings:
    save_dir: str = str(DOWNLOADS)
    copy_to_vault: bool = False
    vault_path: str = ""
    vault_folder: str = ""

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Settings":
        path = path or default_settings_path()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known and isinstance(v, type(getattr(cls(), k)))})

    def save(self, path: Optional[Path] = None) -> None:
        path = Path(path or default_settings_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)


# ------------------------------------------------------------------------- tags


def normalize_tag(tag: str) -> str:
    """Make ``tag`` a valid Obsidian tag: no ``#``, spaces become ``-``, only letters/digits/_-/."""
    tag = tag.strip().lstrip("#").strip()
    tag = re.sub(r"\s+", "-", tag)
    tag = re.sub(r"[^\w/-]", "", tag)
    tag = tag.strip("/")
    if not tag or tag.isdigit():
        return ""
    return tag


def parse_tags(text: str) -> List[str]:
    """Split a comma/space separated tag string into unique, normalized tags (order kept)."""
    seen = set()
    result = []
    for raw in re.split(r"[,\s]+", text or ""):
        tag = normalize_tag(raw)
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            result.append(tag)
    return result


def merge_tags(*groups: List[str]) -> List[str]:
    return parse_tags(" ".join(t for group in groups for t in group))


# ------------------------------------------------------------------ front matter

_FM_RE = re.compile(r"\A---[ \t]*\n(.*?\n)?---[ \t]*(?:\n|\Z)", re.DOTALL)


def split_front_matter(text: str) -> Tuple[Optional[List[str]], str]:
    """Return (front matter lines or None, body)."""
    m = _FM_RE.match(text)
    if not m:
        return None, text
    return (m.group(1) or "").splitlines(), text[m.end():]


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        if value[0] == '"':
            try:
                return json.loads(value)
            except ValueError:
                pass
        return value[1:-1]
    return value


def read_front_matter_tags(lines: List[str]) -> List[str]:
    tags: List[str] = []
    i = 0
    while i < len(lines):
        m = re.match(r"^tags:\s*(.*)$", lines[i])
        if m:
            inline = m.group(1).strip()
            if inline.startswith("[") and inline.endswith("]"):
                tags += [_unquote(t) for t in inline[1:-1].split(",") if t.strip()]
            elif inline:
                tags += [_unquote(t) for t in re.split(r"[,\s]+", inline) if t.strip()]
            i += 1
            while i < len(lines) and re.match(r"^\s*-\s", lines[i]):
                tags.append(_unquote(re.sub(r"^\s*-\s", "", lines[i])))
                i += 1
            continue
        i += 1
    return tags


def _tag_lines(tags: List[str]) -> List[str]:
    if not tags:
        return ["tags: []"]
    out = ["tags:"]
    for tag in tags:
        safe = re.fullmatch(r"[A-Za-z_][\w/-]*", tag) and tag.lower() not in ("true", "false", "null", "yes", "no")
        out.append(f"  - {tag}" if safe else f"  - {json.dumps(tag, ensure_ascii=False)}")
    return out


def set_front_matter_tags(text: str, tags: List[str], merge: bool = True) -> str:
    """Write ``tags`` into the note's YAML front matter (adding front matter if missing)."""
    lines, body = split_front_matter(text)
    if lines is None:
        return "---\n" + "\n".join(_tag_lines(parse_tags(" ".join(tags)))) + "\n---\n\n" + text.lstrip("\n")
    final = merge_tags(read_front_matter_tags(lines), tags) if merge else parse_tags(" ".join(tags))
    out: List[str] = []
    inserted = False
    i = 0
    while i < len(lines):
        if re.match(r"^tags:", lines[i]):
            i += 1
            while i < len(lines) and re.match(r"^\s*-\s", lines[i]):
                i += 1
            if not inserted:
                out += _tag_lines(final)
                inserted = True
            continue
        out.append(lines[i])
        i += 1
    if not inserted:
        out += _tag_lines(final)
    return "---\n" + "\n".join(out) + "\n---\n" + body


# ------------------------------------------------------------------------ saving


def note_filename(title: str, fallback: str = "Untitled", max_len: int = 120) -> str:
    """A filesystem- and Obsidian-safe ``<title>.md`` file name."""
    name = _BAD_FILENAME_CHARS.sub(" ", title or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = _BAD_FILENAME_CHARS.sub(" ", fallback).strip(" .") or "Untitled"
    if len(name) > max_len:
        name = name[:max_len].rsplit(" ", 1)[0].rstrip(" .") or name[:max_len]
    return name + ".md"


def unique_path(folder: Path, filename: str) -> Path:
    path = folder / filename
    stem, suffix = path.stem, path.suffix
    n = 2
    while path.exists():
        path = folder / f"{stem} ({n}){suffix}"
        n += 1
    return path


def save_note(content: str, folder, filename: str) -> Path:
    """Write ``content`` into ``folder`` (created if needed) without overwriting existing files."""
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    path = unique_path(folder, filename)
    with open(path, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return path


# ------------------------------------------------------------------------ vault


class VaultError(Exception):
    pass


def is_obsidian_vault(path) -> bool:
    return bool(path) and (Path(path).expanduser() / ".obsidian").is_dir()


def resolve_vault_folder(vault, subfolder: str) -> Path:
    """Return ``vault/subfolder``, refusing paths that escape the vault."""
    if not vault:
        raise VaultError("Choose your Obsidian vault folder first.")
    root = Path(vault).expanduser().resolve()
    if not root.is_dir():
        raise VaultError(f"Vault folder not found: {root}")
    subfolder = (subfolder or "").strip()
    sub = Path(subfolder).expanduser()
    if not sub.is_absolute():
        sub = Path(subfolder.strip("/\\"))
    else:
        try:
            sub = sub.resolve().relative_to(root)
        except ValueError:
            raise VaultError("That folder is not inside the vault.") from None
    target = (root / sub).resolve()
    if target != root and root not in target.parents:
        raise VaultError("That folder is not inside the vault.")
    return target


def relative_vault_folder(vault, folder) -> str:
    """``folder`` as a vault-relative path ("" for the vault root). Raises VaultError if outside."""
    root = Path(vault).expanduser().resolve()
    try:
        rel = Path(folder).expanduser().resolve().relative_to(root)
    except ValueError:
        raise VaultError("That folder is not inside the vault.") from None
    return "" if str(rel) == "." else rel.as_posix()


def list_vault_folders(vault, max_depth: int = 4, limit: int = 2000) -> List[str]:
    """Vault-relative folder paths (excluding hidden ones like ``.obsidian``), sorted."""
    root = Path(vault).expanduser()
    if not root.is_dir():
        return []
    found: List[str] = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)
        if depth >= max_depth:
            dirnames[:] = []
        if depth:
            found.append(rel.as_posix())
        if len(found) >= limit:
            break
    return sorted(found, key=str.lower)


def copy_to_vault(note_path, vault, subfolder: str = "", tags: Optional[List[str]] = None) -> Path:
    """Copy a saved note into ``vault/subfolder``, merging ``tags`` into its front matter."""
    target_dir = resolve_vault_folder(vault, subfolder)
    note_path = Path(note_path)
    text = note_path.read_text(encoding="utf-8")
    if tags:
        text = set_front_matter_tags(text, tags)
    return save_note(text, target_dir, note_path.name)
