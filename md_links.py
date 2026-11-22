"""Extract http(s) links from Markdown text.

Handles inline links (``[text](url "title")``), reference-style links
(``[text][id]`` + ``[id]: url "title"``), autolinks (``<url>``) and bare URLs.
Image links and anything inside code spans or fenced code blocks are ignored.
Indented code blocks are not detected, so links in deeply nested lists still count.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit


@dataclass
class Link:
    url: str
    title: str = ""
    sources: List[str] = field(default_factory=list)


_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1", re.DOTALL)

# [id]: <url> "title"  /  [id]: url 'title'  /  [id]: url (title)
_REF_DEF_RE = re.compile(
    r"""^\ {0,3}\[(?P<id>[^\]]+)\]:[ \t]*
        <?(?P<url>[^\s>]+)>?
        (?:[ \t]+(?:"(?P<t1>[^"]*)"|'(?P<t2>[^']*)'|\((?P<t3>[^)]*)\)))?
        [ \t]*$""",
    re.MULTILINE | re.VERBOSE,
)

# Link text allows one level of nested brackets, e.g. [see [docs]](url).
_LINK_TEXT = r"(?P<text>(?:[^\[\]]|\[[^\[\]]*\])*)"

_INLINE_RE = re.compile(
    r"(?P<bang>!?)\[" + _LINK_TEXT + r"\]\(\s*"
    r"(?:<(?P<aurl>[^>]*)>|(?P<url>(?:[^\s()]|\([^\s()]*\))+))"
    r"""(?:\s+(?:"(?P<t1>[^"]*)"|'(?P<t2>[^']*)'|\((?P<t3>[^)]*)\)))?\s*\)"""
)

# [text][id], [text][] and shortcut [text] (only resolved if a definition exists).
_REF_USE_RE = re.compile(r"(?P<bang>!?)\[" + _LINK_TEXT + r"\](?:\[(?P<id>[^\]]*)\])?")

_AUTOLINK_RE = re.compile(r"<(?P<url>https?://[^\s<>]+)>", re.IGNORECASE)

_BARE_URL_RE = re.compile(r"https?://[^\s<>\"'`\[\]{}|\\^]+", re.IGNORECASE)

_TRAILING_PUNCT = ".,:;!?*_~'\""


def _is_http(url: str) -> bool:
    return url.lower().startswith(("http://", "https://"))


def _normalize_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def _clean_text(text: str) -> str:
    text = re.sub(r"[*_`~]+", "", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("[", "").replace("]", "")
    return " ".join(text.split())


def _blank(match: "re.Match") -> str:
    """Replace a match with spaces (newlines kept) so later passes skip it."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _strip_fenced_code(text: str) -> str:
    lines = text.split("\n")
    out = []
    fence: Optional[str] = None
    for line in lines:
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                out.append("")
                continue
            out.append(line)
        else:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append("")
    return "\n".join(out)


def _trim_bare_url(url: str) -> str:
    while url:
        last = url[-1]
        if last in _TRAILING_PUNCT:
            url = url[:-1]
        elif last == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


def dedupe_key(url: str) -> str:
    """Key used to treat URLs as duplicates: case-insensitive scheme/host, no trailing slash."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, parts.fragment))


def extract_links(text: str, source: str = "") -> List[Link]:
    """Return the unique http(s) links in ``text`` in order of first appearance."""
    # Code spans are blanked in ``text`` but kept in ``original`` (same offsets) so
    # their content can still appear in link titles.
    original = _strip_fenced_code(text)
    text = _CODE_SPAN_RE.sub(_blank, original)
    found: List[Tuple[int, str, str]] = []

    def link_text(m: "re.Match") -> str:
        return original[m.start("text"):m.end("text")]

    definitions: Dict[str, Tuple[str, str]] = {}
    for m in _REF_DEF_RE.finditer(text):
        label = _normalize_label(m.group("id"))
        title = m.group("t1") or m.group("t2") or m.group("t3") or ""
        definitions.setdefault(label, (m.group("url"), title))
    text = _REF_DEF_RE.sub(_blank, text)

    def inline_sub(m: "re.Match") -> str:
        if not m.group("bang"):
            url = (m.group("aurl") or m.group("url") or "").strip()
            title = m.group("t1") or m.group("t2") or m.group("t3") or _clean_text(link_text(m))
            found.append((m.start(), url, title))
        return _blank(m)

    text = _INLINE_RE.sub(inline_sub, text)

    used_labels = set()

    def ref_sub(m: "re.Match") -> str:
        ref_id = m.group("id")
        label = _normalize_label(ref_id if ref_id else link_text(m))
        if label not in definitions:
            return m.group(0)
        if not m.group("bang"):
            url, def_title = definitions[label]
            found.append((m.start(), url, def_title or _clean_text(link_text(m))))
        used_labels.add(label)
        return _blank(m)

    text = _REF_USE_RE.sub(ref_sub, text)

    # Definitions nobody referenced are still links the author wrote down.
    for label, (url, title) in definitions.items():
        if label not in used_labels:
            found.append((len(text), url, title))

    def autolink_sub(m: "re.Match") -> str:
        found.append((m.start(), m.group("url"), ""))
        return _blank(m)

    text = _AUTOLINK_RE.sub(autolink_sub, text)

    for m in _BARE_URL_RE.finditer(text):
        url = _trim_bare_url(m.group(0))
        if url:
            found.append((m.start(), url, ""))

    found.sort(key=lambda item: item[0])
    return merge_links([Link(url, title, [source] if source else []) for _, url, title in found if _is_http(url)])


def merge_links(links: Iterable[Link]) -> List[Link]:
    """Dedupe links (see :func:`dedupe_key`), keeping first-seen order and the first non-empty title."""
    merged: Dict[str, Link] = {}
    for link in links:
        key = dedupe_key(link.url)
        existing = merged.get(key)
        if existing is None:
            merged[key] = Link(link.url, link.title, list(link.sources))
            continue
        if not existing.title and link.title:
            existing.title = link.title
        for src in link.sources:
            if src not in existing.sources:
                existing.sources.append(src)
    return list(merged.values())


def extract_links_from_files(paths: Iterable[str]) -> List[Link]:
    """Extract and dedupe links across several Markdown files."""
    all_links: List[Link] = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        all_links.extend(extract_links(text, source=str(path)))
    return merge_links(all_links)
