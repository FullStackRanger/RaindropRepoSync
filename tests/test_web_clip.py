import datetime as dt
import io
import urllib.error

import pytest

from clip_storage import read_front_matter_tags, split_front_matter
from web_clip import (Article, ClipError, FetchResult, build_note, clip_url, extract_article,
                      fetch_html, html_to_markdown, normalize_url)


def md(html, base="https://example.com/blog/post"):
    return html_to_markdown(html, base)


# ----------------------------------------------------------------- conversion

def test_headings_paragraphs_and_emphasis():
    out = md("<h2>Intro</h2><p>Some <strong>bold</strong>, <em>italic</em> and <del>gone</del> text.</p>")
    assert out == "## Intro\n\nSome **bold**, *italic* and ~~gone~~ text.\n"


def test_emphasis_moves_surrounding_spaces_outside_markers():
    assert md("<p>a<b> bold </b>b</p>") == "a **bold** b\n"


def test_links_are_made_absolute_and_permalinks_dropped():
    out = md('<h3>Title<a href="#t" class="x">¶</a></h3>'
             '<p><a href="../other">rel</a> <a href="#frag">anchor</a> <a href="javascript:x()">js</a></p>')
    assert out == "### Title\n\n[rel](https://example.com/other) anchor js\n"


def test_link_url_with_parentheses_or_spaces():
    out = md('<p><a href="https://en.wikipedia.org/wiki/Foo_(bar)">x</a> <a href="/a b">y</a></p>')
    assert "[x](<https://en.wikipedia.org/wiki/Foo_(bar)>)" in out
    assert "[y](https://example.com/a%20b)" in out


def test_images_including_lazy_loaded_and_tracking_pixels():
    out = md('<p><img src="/a.png" alt="A [pic]"><img data-src="b.jpg" alt="">'
             '<img src="data:image/gif;base64,xx" data-srcset="/c.png 1x, /c2.png 2x">'
             '<img src="/pixel.gif" width="1" height="1"></p>')
    assert out == ("![A pic](https://example.com/a.png)![](https://example.com/blog/b.jpg)"
                   "![](https://example.com/c.png)\n")


def test_nested_and_ordered_lists():
    out = md("<ul><li>one<ul><li>one-a</li></ul></li><li>two</li></ul>"
             '<ol start="3"><li><p>three</p><p>more</p></li><li>four</li></ol>')
    assert out == "- one\n  - one-a\n- two\n\n3. three\n\n   more\n4. four\n"


def test_unclosed_list_items_and_paragraphs():
    out = md("<ul><li>a<li>b</ul><p>one<p>two")
    assert out == "- a\n- b\n\none\n\ntwo\n"


def test_code_blocks_keep_whitespace_and_language():
    html = '<pre><code class="language-python">def f():\n    return "``"\n</code></pre><p>Use <code>a`b</code></p>'
    out = md(html)
    assert out == '```python\ndef f():\n    return "``"\n```\n\nUse ``a`b``\n'


def test_fence_grows_when_code_contains_triple_backticks():
    out = md("<pre>```\nx\n```</pre>")
    assert out.startswith("````\n```\nx\n```\n````")


def test_blockquote_hr_and_line_breaks():
    out = md("<blockquote><p>quoted<br>line</p><p>second</p></blockquote><hr><p>after</p>")
    assert out == "> quoted  \n> line\n>\n> second\n\n---\n\nafter\n"


def test_tables():
    html = ("<table><thead><tr><th>Name</th><th>Value</th></tr></thead>"
            "<tbody><tr><td>a|b</td><td><b>1</b></td></tr><tr><td>c</td></tr></tbody></table>")
    assert md(html) == "| Name | Value |\n| --- | --- |\n| a\\|b | **1** |\n| c |  |\n"


def test_markdown_characters_in_text_are_escaped():
    out = md("<p>2 * 3 = [6] and snake_case _x_</p><p># not a heading</p><p>1. not a list</p>")
    assert out == "2 \\* 3 = \\[6\\] and snake_case \\_x\\_\n\n\\# not a heading\n\n1\\. not a list\n"


def test_figure_caption():
    out = md('<figure><img src="/f.png" alt="F"><figcaption>A caption</figcaption></figure>')
    assert out == "![F](https://example.com/f.png)\n\n*A caption*\n"


# ----------------------------------------------------------------- extraction

PAGE = """<!doctype html><html><head>
<title>Fallback title | Site</title>
<meta property="og:title" content="The Real Title">
<meta property="og:site_name" content="Example Blog">
<meta name="description" content="A short summary.">
<meta name="keywords" content="python, web scraping">
<meta property="article:published_time" content="2024-05-06T10:00:00Z">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"Example"},
  {"@type":"BlogPosting","headline":"LD headline","author":[{"@type":"Person","name":"Ada Lovelace"}]}]}
</script>
<style>p{color:red}</style>
</head><body>
<header class="site-header"><nav><a href="/">Home</a><a href="/about">About</a></nav></header>
<div class="layout">
  <article class="post">
    <h1>The Real Title</h1>
    <p>First paragraph of the article, with enough words to look like real content, honestly.</p>
    <div class="share-buttons"><a href="https://twitter.com/x">Tweet</a></div>
    <p>Second paragraph continues the story, and keeps going for a while longer than the first.</p>
    <p style="display:none">Hidden text</p>
    <div class="newsletter-signup">Subscribe to our newsletter!</div>
    <ul class="related"><li><a href="/1">Related one</a></li><li><a href="/2">Related two</a></li></ul>
    <p>Third paragraph wraps things up with a final thought or two about the topic at hand.</p>
  </article>
  <aside class="sidebar"><p>Sidebar stuff that should never appear in the note at all.</p></aside>
</div>
<footer><p>Copyright footer</p></footer>
<script>console.log("tracking")</script>
</body></html>"""


def test_extracts_article_content_without_boilerplate():
    article = extract_article(PAGE, "https://example.com/posts/1")
    assert article.title == "The Real Title"
    body = article.markdown
    assert body.startswith("First paragraph")
    assert "Third paragraph" in body
    for junk in ("Home", "Tweet", "Hidden text", "newsletter", "Related one", "Sidebar", "Copyright",
                 "tracking", "color:red", "# The Real Title"):
        assert junk not in body


def test_extracts_metadata():
    article = extract_article(PAGE, "https://example.com/posts/1")
    assert article.author == "Ada Lovelace"
    assert article.published == "2024-05-06"
    assert article.site_name == "Example Blog"
    assert article.description == "A short summary."
    assert article.tags == ["python", "web scraping"]


def test_title_falls_back_to_title_tag_then_h1_then_host():
    assert extract_article("<title> Plain </title><p>x</p>", "https://a.com").title == "Plain"
    assert extract_article("<h1>Heading</h1><p>x</p>", "https://a.com").title == "Heading"
    assert extract_article("<p>x</p>", "https://a.com/page").title == "a.com"


def test_scoring_picks_densest_block_when_no_article_tag():
    filler = "This sentence has words, commas, and enough length to count as content. " * 3
    html = (f'<body><div id="menu"><a href="/a">A</a> <a href="/b">B</a></div>'
            f'<div class="links"><p><a href="/x">{"link text " * 10}</a></p></div>'
            f'<div class="story"><p>{filler}</p><p>{filler}</p><p>{filler}</p></div>'
            f'<div class="bottom"><p>Short footer-ish blurb that is not the article.</p></div></body>')
    article = extract_article(html, "https://a.com")
    assert article.markdown.count("This sentence") == 9
    assert "link text" not in article.markdown
    assert "blurb" not in article.markdown


def test_relative_links_resolve_against_base_tag():
    html = ('<head><base href="https://cdn.example.org/root/"></head><body><article>'
            + "<p>" + "words " * 60 + '<a href="page">here</a></p></article></body>')
    assert "[here](https://cdn.example.org/root/page)" in extract_article(html, "https://example.com/x").markdown


# ---------------------------------------------------------------------- fetch

def test_normalize_url():
    assert normalize_url("  example.com/a ") == "https://example.com/a"
    assert normalize_url("<http://x.org>") == "http://x.org"
    for bad in ("", "ftp://x.org/file", "javascript:alert(1)", "https://"):
        with pytest.raises(ClipError):
            normalize_url(bad)


class FakeResponse(io.BytesIO):
    def __init__(self, data, content_type="text/html", url="https://example.com/final"):
        super().__init__(data)
        self.headers = {"Content-Type": content_type}
        self._url = url

    def geturl(self):
        return self._url


def test_fetch_decodes_using_header_or_meta_charset():
    body = "<p>caf\u00e9</p>".encode("latin-1")
    result = fetch_html("example.com", opener=lambda req, timeout: FakeResponse(body, "text/html; charset=ISO-8859-1"))
    assert "café" in result.html
    assert result.url == "https://example.com/final"

    body = b'<meta charset="windows-1252"><p>\x93hi\x94</p>'
    result = fetch_html("https://example.com", opener=lambda req, timeout: FakeResponse(body))
    assert "\u201chi\u201d" in result.html


def test_fetch_sends_browser_user_agent():
    seen = {}

    def opener(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        return FakeResponse(b"<p>x</p>")

    fetch_html("https://example.com", opener=opener)
    assert "Mozilla" in seen["ua"]


def test_fetch_rejects_non_html_and_maps_errors():
    with pytest.raises(ClipError, match="Not an HTML page"):
        fetch_html("https://x.org/a.pdf", opener=lambda req, timeout: FakeResponse(b"%PDF", "application/pdf"))

    def http_error(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    with pytest.raises(ClipError, match="HTTP 404"):
        fetch_html("https://x.org/missing", opener=http_error)

    def url_error(req, timeout):
        raise urllib.error.URLError("nodename nor servname provided")

    with pytest.raises(ClipError, match="Could not reach x.org"):
        fetch_html("https://x.org", opener=url_error)


def test_clip_url_keeps_the_url_the_user_gave():
    def fake_fetch(url):
        return FetchResult(url="https://example.com/after-redirect", html=PAGE)

    article = clip_url("example.com/posts/1", fetch=fake_fetch)
    assert article.url == "https://example.com/posts/1"
    assert article.title == "The Real Title"


# --------------------------------------------------------------- front matter

def test_build_note_front_matter():
    article = Article(title='Quotes "and": colons', markdown="Body text.\n", url="https://example.com/a",
                      author="Ada", published="2024-05-06", description="")
    note = build_note(article, tags=["clippings", "ai/llm"], clipped=dt.date(2026, 11, 22))
    assert note == (
        "---\n"
        'title: "Quotes \\"and\\": colons"\n'
        'source: "https://example.com/a"\n'
        'author: "Ada"\n'
        "published: 2024-05-06\n"
        "date: 2026-11-22\n"
        "tags:\n"
        "  - clippings\n"
        "  - ai/llm\n"
        "---\n\nBody text.\n"
    )
    lines, body = split_front_matter(note)
    assert read_front_matter_tags(lines) == ["clippings", "ai/llm"]
    assert body.strip() == "Body text."


def test_build_note_overrides_title_and_body():
    note = build_note(Article(title="Old", url="https://x.org"), tags=[], title="New", body="Edited\n\n",
                      clipped=dt.date(2026, 1, 2))
    assert 'title: "New"' in note
    assert "tags: []" in note
    assert note.endswith("---\n\nEdited\n")
