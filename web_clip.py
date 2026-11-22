"""Fetch a web page, extract its main article and convert it to Markdown.

Standard library only. Content extraction is a small readability-style heuristic:
prefer ``<article>`` / ``<main>``, otherwise score blocks by paragraph text and
link density, after dropping navigation, sidebars, ads and other boilerplate.
"""

import codecs
import datetime as _dt
import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Dict, Iterator, List, Optional, Union
from urllib.parse import urljoin, urlsplit

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
MAX_BYTES = 15 * 1024 * 1024


class ClipError(Exception):
    """A page could not be fetched or converted."""


# --------------------------------------------------------------------------- DOM


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: Optional[Dict[str, str]] = None, parent: "Optional[Node]" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: List[Union["Node", str]] = []
        self.parent = parent

    def iter(self) -> Iterator["Node"]:
        """Yield this node and all element descendants, depth first."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed([c for c in node.children if isinstance(c, Node)]))

    def text(self) -> str:
        parts: List[str] = []
        stack: List[Union[Node, str]] = [self]
        while stack:
            item = stack.pop()
            if isinstance(item, str):
                parts.append(item)
            else:
                stack.extend(reversed(item.children))
        return "".join(parts)

    def find(self, tag: str) -> "Optional[Node]":
        return next((n for n in self.iter() if n.tag == tag), None)

    def remove(self):
        if self.parent is not None:
            self.parent.children = [c for c in self.parent.children if c is not self]
            self.parent = None

    def __repr__(self) -> str:
        return f"<Node {self.tag}>"


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
         "source", "track", "wbr"}
_CLOSES_P = {"address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset",
             "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
             "hr", "main", "menu", "nav", "ol", "p", "pre", "section", "table", "ul"}
# tag -> (tags it implicitly closes, tags that stop the search)
_IMPLIED_END = {
    "li": ({"li"}, {"ul", "ol", "menu"}),
    "dt": ({"dt", "dd"}, {"dl"}),
    "dd": ({"dt", "dd"}, {"dl"}),
    "tr": ({"tr", "td", "th"}, {"table", "thead", "tbody", "tfoot"}),
    "td": ({"td", "th"}, {"tr", "table"}),
    "th": ({"td", "th"}, {"tr", "table"}),
    "thead": ({"thead", "tbody", "tfoot", "tr", "td", "th"}, {"table"}),
    "tbody": ({"thead", "tbody", "tfoot", "tr", "td", "th"}, {"table"}),
    "tfoot": ({"thead", "tbody", "tfoot", "tr", "td", "th"}, {"table"}),
    "option": ({"option"}, {"select"}),
}


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def _close_to(self, targets, boundaries) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            tag = self.stack[i].tag
            if tag in targets:
                del self.stack[i:]
                return
            if tag in boundaries:
                return

    def _open(self, tag, attrs, self_closing=False):
        if tag in _CLOSES_P:
            self._close_to({"p"}, {"button", "td", "th", "li", "blockquote", "div", "section", "article"})
        if tag in _IMPLIED_END:
            self._close_to(*_IMPLIED_END[tag])
        parent = self.stack[-1]
        node = Node(tag, {k: (v or "") for k, v in attrs}, parent)
        parent.children.append(node)
        if tag not in _VOID and not self_closing:
            self.stack.append(node)

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, self_closing=True)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        children = self.stack[-1].children
        if children and isinstance(children[-1], str):
            children[-1] += data
        else:
            children.append(data)


def parse_html(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# ----------------------------------------------------------------------- metadata


@dataclass
class Article:
    title: str = ""
    markdown: str = ""
    url: str = ""
    author: str = ""
    published: str = ""
    site_name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)


_ARTICLE_TYPES = {"article", "newsarticle", "blogposting", "techarticle", "report",
                  "scholarlyarticle", "webpage", "posting"}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _iso_date(value: str) -> str:
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", value or "")
    return m.group(1) if m else ""


def _json_ld_objects(root: Node) -> List[dict]:
    objects: List[dict] = []
    for node in root.iter():
        if node.tag != "script" or "ld+json" not in node.attrs.get("type", ""):
            continue
        try:
            data = json.loads(node.text().strip())
        except ValueError:
            continue
        pending = data if isinstance(data, list) else [data]
        while pending:
            item = pending.pop(0)
            if isinstance(item, dict):
                objects.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    pending.extend(graph)
    return objects


def _ld_author(value) -> str:
    if isinstance(value, list):
        return ", ".join(filter(None, (_ld_author(v) for v in value)))
    if isinstance(value, dict):
        return _clean(str(value.get("name", "")))
    return _clean(str(value)) if isinstance(value, str) else ""


def extract_metadata(root: Node) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    keywords = ""
    for node in root.iter():
        if node.tag == "meta":
            key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
            content = _clean(node.attrs.get("content", ""))
            if key and content and key not in meta:
                meta[key] = content
            if key in ("keywords", "news_keywords") and not keywords:
                keywords = content

    ld: Dict[str, str] = {}
    for obj in _json_ld_objects(root):
        types = obj.get("@type", "")
        types = [t.lower() for t in (types if isinstance(types, list) else [types]) if isinstance(t, str)]
        if not (set(types) & _ARTICLE_TYPES or "headline" in obj):
            continue
        ld.setdefault("headline", _clean(str(obj.get("headline", "") or "")))
        ld.setdefault("author", _ld_author(obj.get("author")))
        ld.setdefault("published", _iso_date(str(obj.get("datePublished", "") or "")))
        ld = {k: v for k, v in ld.items() if v}

    title_node = root.find("title")
    h1 = root.find("h1")
    time_node = next((n for n in root.iter() if n.tag == "time" and n.attrs.get("datetime")), None)

    def first(*values: str) -> str:
        return next((v for v in values if v), "")

    return {
        "title": first(meta.get("og:title"), meta.get("twitter:title"), ld.get("headline"),
                       _clean(title_node.text()) if title_node else "", _clean(h1.text()) if h1 else ""),
        "author": first(meta.get("author"), ld.get("author"), meta.get("article:author", "")
                        if not meta.get("article:author", "").startswith("http") else ""),
        "published": first(_iso_date(meta.get("article:published_time", "")), ld.get("published", ""),
                           _iso_date(meta.get("date", "")), _iso_date(meta.get("dc.date", "")),
                           _iso_date(time_node.attrs["datetime"]) if time_node else ""),
        "site_name": first(meta.get("og:site_name"), meta.get("application-name")),
        "description": first(meta.get("og:description"), meta.get("description"),
                             meta.get("twitter:description")),
        "keywords": keywords,
    }


# ---------------------------------------------------------------- content picking

_DROP_TAGS = {"script", "style", "noscript", "template", "iframe", "svg", "canvas", "form", "button",
              "input", "select", "textarea", "nav", "footer", "aside", "link", "meta", "dialog",
              "object", "embed", "head", "title", "math"}
_NEGATIVE = {"comment", "comments", "share", "sharing", "social", "related", "sidebar", "sponsor",
             "sponsored", "promo", "advert", "advertisement", "ad", "ads", "newsletter", "subscribe",
             "subscription", "signup", "cookie", "cookies", "consent", "popup", "modal", "banner",
             "breadcrumb", "breadcrumbs", "menu", "nav", "navbar", "navigation", "masthead", "disqus",
             "outbrain", "taboola", "widget", "toolbar", "footer", "skip", "paywall", "recirc",
             "navbox", "ambox", "editsection", "noprint", "catlinks", "headerlink"}
_POSITIVE = {"article", "body", "content", "entry", "main", "post", "text", "story", "prose",
             "markdown", "blog", "hentry"}
_KEEP_TAGS = {"#root", "html", "body", "article", "main", "pre", "code", "table"}


def _tokens(node: Node) -> set:
    value = (node.attrs.get("class", "") + " " + node.attrs.get("id", "")).lower()
    return set(re.split(r"[^a-z0-9]+", value)) - {""}


def _class_weight(node: Node) -> int:
    tokens = _tokens(node)
    return (25 if tokens & _POSITIVE else 0) - (25 if tokens & _NEGATIVE else 0)


def _is_hidden(node: Node) -> bool:
    style = node.attrs.get("style", "").replace(" ", "").lower()
    return ("hidden" in node.attrs or node.attrs.get("aria-hidden") == "true"
            or "display:none" in style or "visibility:hidden" in style)


def _strip_boilerplate(root: Node) -> None:
    doomed = []
    for node in root.iter():
        if node.tag in _KEEP_TAGS:
            continue
        tokens = _tokens(node)
        if (node.tag in _DROP_TAGS or _is_hidden(node) or node.attrs.get("role") in ("navigation", "dialog")
                or (tokens & _NEGATIVE and not tokens & _POSITIVE)):
            doomed.append(node)
    for node in doomed:
        node.remove()


def _text_len(node: Node) -> int:
    return len(_clean(node.text()))


def link_density(node: Node) -> float:
    total = _text_len(node)
    if not total:
        return 0.0
    linked = sum(_text_len(a) for a in node.iter() if a.tag == "a")
    return min(1.0, linked / total)


_BLOCKISH = {"p", "div", "section", "article", "table", "ul", "ol", "pre", "blockquote", "h1", "h2",
             "h3", "h4", "h5", "h6", "figure", "dl"}


def _score_candidates(body: Node) -> Optional[Node]:
    scores: Dict[int, float] = {}
    nodes: Dict[int, Node] = {}
    for node in body.iter():
        is_para = node.tag in ("p", "pre", "td", "blockquote") or (
            node.tag == "div" and not any(isinstance(c, Node) and c.tag in _BLOCKISH for c in node.children))
        if not is_para:
            continue
        text = _clean(node.text())
        if len(text) < 25:
            continue
        score = 1 + text.count(",") + min(len(text) // 100, 3)
        ancestors = [node.parent, node.parent.parent if node.parent else None]
        for divider, anc in zip((1, 2), ancestors):
            if anc is None or anc.tag == "#root":
                continue
            if id(anc) not in scores:
                base = {"div": 5, "article": 10, "main": 10, "section": 3, "pre": 3, "td": 3,
                        "blockquote": 3}.get(anc.tag, 0)
                scores[id(anc)] = base + _class_weight(anc)
                nodes[id(anc)] = anc
            scores[id(anc)] += score / divider
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k] * (1 - link_density(nodes[k])))
    return nodes[best]


def _pick_content(root: Node) -> Node:
    body = root.find("body") or root
    for tags in (("article",), ("main",)):
        found = [n for n in body.iter() if n.tag in tags]
        if not found and tags == ("main",):
            found = [n for n in body.iter() if n.attrs.get("role") == "main"]
        if found:
            best = max(found, key=_text_len)
            if _text_len(best) >= 250:
                return best
    return _score_candidates(body) or body


def _clean_conditionally(content: Node) -> None:
    doomed = []
    for node in content.iter():
        if node is content or node.tag not in ("div", "section", "ul", "ol", "table", "header"):
            continue
        if any(n.tag in ("pre", "img", "picture", "video") for n in node.iter()):
            continue
        text_len = _text_len(node)
        if text_len and link_density(node) > 0.6 and text_len < 600:
            doomed.append(node)
    for node in doomed:
        node.remove()


# ---------------------------------------------------------------------- markdown

_BLOCK_TAGS = {"address", "article", "aside", "blockquote", "body", "center", "dd", "details", "dialog",
               "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4",
               "h5", "h6", "header", "hr", "html", "li", "main", "ol", "p", "pre", "section", "summary",
               "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul", "#root", "video", "audio"}
_BR = "\x00BR\x00"
_PERMALINK_TEXT = {"¶", "#", "§", "🔗", "\\#"}
_LINE_START_RE = re.compile(r"^(\s*)(#{1,6}(?=\s|$)|>|[-+](?=\s)|\d+(?=[.)]\s)|={3,}$)")


def escape_markdown(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = re.sub(r"([*`\[\]])", r"\\\1", text)
    text = re.sub(r"(?<!\w)_|_(?!\w)", r"\\_", text)
    text = re.sub(r"<(?=[A-Za-z/!])", r"\\<", text)
    return text


def _escape_line_start(line: str) -> str:
    m = _LINE_START_RE.match(line)
    if not m:
        return line
    lead, marker = m.group(1), m.group(2)
    rest = line[m.end():]
    if marker[0].isdigit():
        return f"{lead}{marker}\\{rest}"
    return f"{lead}\\{marker}{rest}"


def _md_url(url: str) -> str:
    url = url.strip().replace(" ", "%20")
    if "(" in url or ")" in url:
        return f"<{url}>"
    return url


class MarkdownRenderer:
    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self._has_block: Dict[int, bool] = {}

    # -- helpers
    def _abs(self, url: str) -> str:
        url = (url or "").strip()
        if not url or url.lower().startswith(("javascript:", "data:", "about:")):
            return ""
        return urljoin(self.base_url, url) if self.base_url else url

    def _contains_block(self, node: Node) -> bool:
        key = id(node)
        if key not in self._has_block:
            self._has_block[key] = any(
                isinstance(c, Node) and (c.tag in _BLOCK_TAGS or self._contains_block(c)) for c in node.children)
        return self._has_block[key]

    @staticmethod
    def _finish_inline(text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r" ?" + re.escape(_BR) + r" ?", _BR, text)
        lines = text.split(_BR)
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        text = _BR.join(lines)
        lines = [_escape_line_start(line.strip()) for line in text.split(_BR)]
        return "  \n".join(lines)

    # -- blocks
    def render(self, node: Node) -> str:
        return self._join(self._blocks(node)).strip() + "\n"

    @staticmethod
    def _join(blocks: List[str]) -> str:
        return "\n\n".join(b.strip("\n") for b in blocks if b.strip())

    def _blocks(self, node: Node) -> List[str]:
        out: List[str] = []
        inline: List[str] = []

        def flush():
            text = self._finish_inline("".join(inline))
            inline.clear()
            if text:
                out.append(text)

        for child in node.children:
            if isinstance(child, str):
                inline.append(escape_markdown(child))
            elif child.tag in _BLOCK_TAGS:
                flush()
                out.extend(self._block(child))
            elif self._contains_block(child) and child.tag not in ("a",):
                flush()
                out.extend(self._blocks(child))
            else:
                inline.append(self._inline(child))
        flush()
        return out

    def _block(self, node: Node) -> List[str]:
        tag = node.tag
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = self._finish_inline(self._inline_children(node)).replace("  \n", " ")
            return [f"{'#' * int(tag[1])} {text}"] if text else []
        if tag == "hr":
            return ["---"]
        if tag == "pre":
            return [self._code_block(node)]
        if tag in ("ul", "ol"):
            return [self._list(node)] if node.children else []
        if tag == "blockquote":
            inner = self._join(self._blocks(node))
            if not inner:
                return []
            return ["\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))]
        if tag == "table":
            return [self._table(node)]
        if tag in ("figcaption",):
            text = self._finish_inline(self._inline_children(node))
            return [f"*{text}*"] if text else []
        if tag == "dt":
            text = self._finish_inline(self._inline_children(node))
            return [f"**{text}**"] if text else []
        if tag in ("video", "audio"):
            src = self._abs(node.attrs.get("src", "") or next(
                (n.attrs.get("src", "") for n in node.iter() if n.tag == "source"), ""))
            return [f"[{tag.capitalize()}]({_md_url(src)})"] if src else []
        return self._blocks(node)

    def _code_block(self, node: Node) -> str:
        code = node.text()
        if code.startswith("\n"):
            code = code[1:]
        code = code.rstrip()
        lang = ""
        for n in node.iter():
            m = re.search(r"(?:language|lang|highlight-source)-([\w+#.-]+)", n.attrs.get("class", ""))
            if m:
                lang = m.group(1)
                break
        longest = max((len(r) for r in re.findall(r"`+", code)), default=0)
        fence = "`" * max(3, longest + 1)
        return f"{fence}{lang}\n{code}\n{fence}"

    def _list(self, node: Node) -> str:
        ordered = node.tag == "ol"
        try:
            number = int(node.attrs.get("start", "1"))
        except ValueError:
            number = 1
        items: List[str] = []
        for child in node.children:
            if isinstance(child, str):
                if child.strip():
                    items.append("- " + escape_markdown(child.strip()))
                continue
            if child.tag in ("ul", "ol"):
                nested = self._list(child)
                if items:
                    items[-1] += "\n" + "\n".join("  " + ln if ln else ln for ln in nested.split("\n"))
                else:
                    items.append(nested)
                continue
            if child.tag == "li":
                blocks = self._blocks(child)
            elif child.tag in _BLOCK_TAGS:
                blocks = self._block(child)
            else:
                blocks = [self._finish_inline(self._inline(child))]
            blocks = [b for b in blocks if b.strip()]
            if not blocks:
                continue
            marker = f"{number}. " if ordered else "- "
            number += 1
            body = blocks[0]
            for prev, block in zip(blocks, blocks[1:]):
                is_list = re.match(r"\s*(?:[-*+]|\d+\.)\s", block) is not None
                tight = is_list and not re.match(r"\s*(?:[-*+]|\d+\.)\s", prev)
                body += ("\n" if tight else "\n\n") + block
            pad = " " * len(marker)
            lines = body.split("\n")
            items.append(marker + lines[0] + "".join("\n" + (pad + ln if ln else "") for ln in lines[1:]))
        return "\n".join(items)

    def _table(self, node: Node) -> str:
        rows = [n for n in node.iter() if n.tag == "tr" and self._owning_table(n) is node]
        if any(self._contains_block(c) and any(n.tag in ("table", "ul", "ol", "pre") for n in c.iter())
               for r in rows for c in r.children if isinstance(c, Node)):
            return self._join([self._join(self._blocks(r)) for r in rows])
        grid = []
        for row in rows:
            cells = [c for c in row.children if isinstance(c, Node) and c.tag in ("td", "th")]
            grid.append([self._finish_inline(self._inline_children(c)).replace("  \n", " ").replace("|", "\\|")
                         for c in cells])
        grid = [r for r in grid if any(r)]
        if not grid:
            return ""
        width = max(len(r) for r in grid)
        grid = [r + [""] * (width - len(r)) for r in grid]
        lines = ["| " + " | ".join(grid[0]) + " |", "|" + " --- |" * width]
        lines += ["| " + " | ".join(r) + " |" for r in grid[1:]]
        return "\n".join(lines)

    @staticmethod
    def _owning_table(node: Node) -> Optional[Node]:
        parent = node.parent
        while parent is not None and parent.tag != "table":
            parent = parent.parent
        return parent

    # -- inline
    def _inline_children(self, node: Node) -> str:
        parts = []
        for child in node.children:
            if isinstance(child, str):
                parts.append(escape_markdown(child))
            elif child.tag in _BLOCK_TAGS:
                parts.append(" " + self._inline_children(child) + " ")
            else:
                parts.append(self._inline(child))
        return "".join(parts)

    @staticmethod
    def _wrap(inner: str, marker: str) -> str:
        m = re.match(r"^(\s*)(.*?)(\s*)$", inner, re.DOTALL)
        lead, core, trail = m.group(1), m.group(2), m.group(3)
        if not core or (core.startswith(marker) and core.endswith(marker)):
            return inner
        return f"{lead}{marker}{core}{marker}{trail}"

    def _image(self, node: Node) -> str:
        src = ""
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            candidate = self._abs(node.attrs.get(attr, ""))
            if candidate:
                src = candidate
                break
        if not src:
            srcset = node.attrs.get("srcset") or node.attrs.get("data-srcset") or ""
            src = self._abs(srcset.split(",")[0].strip().split(" ")[0]) if srcset.strip() else ""
        if not src or node.attrs.get("width") == "1" or node.attrs.get("height") == "1":
            return ""
        alt = _clean(node.attrs.get("alt", "")).replace("[", "").replace("]", "")
        return f"![{alt}]({_md_url(src)})"

    def _inline(self, node: Node) -> str:
        tag = node.tag
        if tag == "br":
            return _BR
        if tag == "img":
            return self._image(node)
        if tag == "picture":
            img = node.find("img")
            return self._image(img) if img else ""
        if tag in ("code", "kbd", "samp", "tt"):
            code = re.sub(r"\s+", " ", node.text())
            if not code.strip():
                return code
            longest = max((len(r) for r in re.findall(r"`+", code)), default=0)
            ticks = "`" * (longest + 1)
            pad = " " if code.startswith("`") or code.endswith("`") else ""
            return f"{ticks}{pad}{code}{pad}{ticks}"
        inner = self._inline_children(node)
        if tag in ("strong", "b"):
            return self._wrap(inner, "**")
        if tag in ("em", "i", "cite", "dfn"):
            return self._wrap(inner, "*")
        if tag in ("del", "s", "strike"):
            return self._wrap(inner, "~~")
        if tag == "a":
            href = node.attrs.get("href", "")
            url = "" if href.strip().startswith("#") else self._abs(href)
            text = re.sub(r"\s+", " ", inner.replace(_BR, " ")).strip()
            if text in _PERMALINK_TEXT:
                return ""
            if not url:
                return inner
            if not text:
                text = escape_markdown(url)
            return f"[{text}]({_md_url(url)})"
        return inner


def html_to_markdown(html_or_node: Union[str, Node], base_url: str = "") -> str:
    node = parse_html(html_or_node) if isinstance(html_or_node, str) else html_or_node
    return MarkdownRenderer(base_url).render(node)


# ----------------------------------------------------------------------- article


def _strip_leading_title(markdown: str, title: str) -> str:
    m = re.match(r"#{1,2} (.+)\n*", markdown)
    if m and title and _norm_title(m.group(1)) == _norm_title(title):
        return markdown[m.end():]
    return markdown


def _norm_title(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.replace("\\", "")).lower()


def extract_article(html: str, url: str = "") -> Article:
    """Return the page's metadata and main content as Markdown."""
    root = parse_html(html)
    base = root.find("base")
    base_url = urljoin(url, base.attrs.get("href", "")) if base is not None and base.attrs.get("href") else url
    meta = extract_metadata(root)
    _strip_boilerplate(root)
    content = _pick_content(root)
    _clean_conditionally(content)
    markdown = MarkdownRenderer(base_url).render(content)
    title = meta["title"] or (urlsplit(url).netloc if url else "Untitled")
    markdown = _strip_leading_title(markdown, title).strip() + "\n"
    keywords = [k.strip() for k in meta["keywords"].split(",") if k.strip()]
    return Article(title=title, markdown=markdown, url=url, author=meta["author"],
                   published=meta["published"], site_name=meta["site_name"],
                   description=meta["description"], tags=keywords)


# ------------------------------------------------------------------------- fetch


def normalize_url(url: str) -> str:
    """Trim the URL and add ``https://`` if no scheme is given; reject non-http(s) URLs."""
    url = (url or "").strip().strip("<>\"'")
    if not url:
        raise ClipError("Enter a URL.")
    # "host:8080/x" has no scheme; "javascript:..." or "mailto:..." does.
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)", url):
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise ClipError(f"Not a web page URL: {url}")
    return url


def _charset(content_type: str, head: bytes) -> str:
    m = re.search(r"charset=[\"']?([\w-]+)", content_type or "", re.I)
    if not m:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", head, re.I)
    name = m.group(1) if m else "utf-8"
    name = name.decode("ascii", "ignore") if isinstance(name, bytes) else name
    try:
        return codecs.lookup(name).name
    except LookupError:
        return "utf-8"


@dataclass
class FetchResult:
    url: str
    html: str
    content_type: str = ""


Opener = Callable[..., object]


def fetch_html(url: str, timeout: float = 20, opener: Optional[Opener] = None) -> FetchResult:
    """Download ``url`` and return its decoded HTML. Raises :class:`ClipError`."""
    url = normalize_url(url)
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8",
    })
    opener = opener or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if content_type and not re.search(r"html|xml|text/plain", content_type, re.I):
                raise ClipError(f"Not an HTML page ({content_type.split(';')[0]}).")
            data = response.read(MAX_BYTES + 1)
            final_url = response.geturl() or url
    except ClipError:
        raise
    except urllib.error.HTTPError as e:
        raise ClipError(f"HTTP {e.code} {e.reason} for {url}") from e
    except urllib.error.URLError as e:
        raise ClipError(f"Could not reach {urlsplit(url).netloc}: {e.reason}") from e
    except (socket.timeout, TimeoutError) as e:
        raise ClipError(f"Timed out fetching {url}") from e
    except OSError as e:
        raise ClipError(f"Could not fetch {url}: {e}") from e
    if len(data) > MAX_BYTES:
        raise ClipError("Page is too large to clip.")
    html = data.decode(_charset(content_type, data[:4096]), errors="replace")
    return FetchResult(url=final_url, html=html, content_type=content_type)


def clip_url(url: str, fetch: Callable[[str], FetchResult] = fetch_html) -> Article:
    """Fetch ``url`` and extract its article. The returned ``url`` is the address the user gave."""
    url = normalize_url(url)
    result = fetch(url)
    article = extract_article(result.html, result.url or url)
    article.url = url
    return article


# -------------------------------------------------------------------- front matter


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def front_matter(fields: Dict[str, Union[str, List[str]]]) -> str:
    """Render a YAML front matter block. Empty values are omitted; lists become block sequences."""
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                lines.extend(f"  - {_yaml_str(v) if _needs_quotes(v) else v}" for v in value)
            else:
                lines.append(f"{key}: []")
        elif value:
            is_date = re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
            lines.append(f"{key}: {value if is_date else _yaml_str(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _needs_quotes(value: str) -> bool:
    return not re.fullmatch(r"[A-Za-z_][\w/-]*", value) or value.lower() in ("true", "false", "null", "yes", "no")


def build_note(article: Article, tags: Optional[List[str]] = None, title: Optional[str] = None,
               body: Optional[str] = None, clipped: Optional[_dt.date] = None) -> str:
    """Return the full note: front matter (title, source, author, published, date, tags, ...) + body."""
    clipped = clipped or _dt.date.today()
    fields: Dict[str, Union[str, List[str]]] = {
        "title": (title if title is not None else article.title).strip(),
        "source": article.url,
        "author": article.author,
        "published": article.published,
        "date": clipped.isoformat(),
        "site": article.site_name,
        "description": article.description,
        "tags": list(tags or []),
    }
    content = (body if body is not None else article.markdown).strip()
    return front_matter(fields) + "\n" + content + "\n"


__all__ = [
    "Article", "ClipError", "FetchResult", "MarkdownRenderer", "Node", "build_note", "clip_url",
    "escape_markdown", "extract_article", "extract_metadata", "fetch_html", "front_matter",
    "html_to_markdown", "link_density", "normalize_url", "parse_html",
]
