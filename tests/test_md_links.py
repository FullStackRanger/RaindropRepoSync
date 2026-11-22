from md_links import Link, dedupe_key, extract_links, extract_links_from_files, merge_links


def urls(links):
    return [link.url for link in links]


def test_inline_links_with_titles():
    md = 'See [Example](https://example.com "Example Site") and [Docs](<https://docs.example.com/a b>).'
    links = extract_links(md)
    assert urls(links) == ["https://example.com", "https://docs.example.com/a b"]
    assert links[0].title == "Example Site"
    assert links[1].title == "Docs"


def test_inline_link_with_parentheses_in_url():
    links = extract_links("[Wiki](https://en.wikipedia.org/wiki/Foo_(bar)) after")
    assert urls(links) == ["https://en.wikipedia.org/wiki/Foo_(bar)"]


def test_link_text_formatting_is_cleaned():
    links = extract_links("[**Bold** `code` [nested]](https://example.com)")
    assert links[0].title == "Bold code nested"


def test_reference_style_links():
    md = """
Read [the guide][guide], [Other][] and [shortcut].

[guide]: https://example.com/guide "The Guide"
[other]: <https://example.com/other>
[Shortcut]: https://example.com/short 'Short'
"""
    links = extract_links(md)
    assert urls(links) == [
        "https://example.com/guide",
        "https://example.com/other",
        "https://example.com/short",
    ]
    assert [link.title for link in links] == ["The Guide", "Other", "Short"]


def test_unused_reference_definition_is_still_extracted():
    links = extract_links("[orphan]: https://example.com/orphan")
    assert urls(links) == ["https://example.com/orphan"]


def test_brackets_without_definition_are_ignored():
    assert extract_links("- [ ] todo item and [not a link]") == []


def test_autolinks_and_bare_urls():
    md = "Visit <https://auto.example.com/x> or https://bare.example.com/path?q=1, ok."
    assert urls(extract_links(md)) == ["https://auto.example.com/x", "https://bare.example.com/path?q=1"]


def test_bare_url_trailing_punctuation_and_parens():
    md = "(see https://example.com/a) and https://example.com/b. Also https://en.wikipedia.org/wiki/X_(y)!"
    assert urls(extract_links(md)) == [
        "https://example.com/a",
        "https://example.com/b",
        "https://en.wikipedia.org/wiki/X_(y)",
    ]


def test_images_are_skipped():
    md = "![logo](https://example.com/logo.png) [site](https://example.com)"
    assert urls(extract_links(md)) == ["https://example.com"]


def test_linked_image_keeps_outer_link():
    md = "[![badge](https://img.shields.io/x.svg)](https://ci.example.com)"
    assert urls(extract_links(md)) == ["https://ci.example.com"]


def test_non_http_links_are_ignored():
    md = "[mail](mailto:a@b.c) [rel](./other.md) [anchor](#top) [ftp](ftp://x.org) [ok](http://ok.example)"
    assert urls(extract_links(md)) == ["http://ok.example"]


def test_code_is_ignored():
    md = """
Inline `https://code.example.com` is skipped.

```bash
curl https://fenced.example.com
```

~~~
[x](https://tilde.example.com)
~~~

After https://after.example.com
"""
    assert urls(extract_links(md)) == ["https://after.example.com"]


def test_nested_list_links_are_kept():
    md = "- top\n    - [deep](https://deep.example.com)\n"
    assert urls(extract_links(md)) == ["https://deep.example.com"]


def test_dedupe_preserves_order_and_prefers_titled_entry():
    md = "https://example.com/ then [Example](https://EXAMPLE.com) then https://other.example"
    links = extract_links(md)
    assert urls(links) == ["https://example.com/", "https://other.example"]
    assert links[0].title == "Example"


def test_dedupe_key_keeps_query_and_path_case():
    assert dedupe_key("HTTPS://Example.COM/Path/") == "https://example.com/Path"
    assert dedupe_key("https://e.com/?a=1") != dedupe_key("https://e.com/?a=2")


def test_merge_links_combines_sources():
    merged = merge_links([
        Link("https://a.example", "", ["one.md"]),
        Link("https://a.example/", "A", ["two.md"]),
    ])
    assert len(merged) == 1
    assert merged[0].title == "A"
    assert merged[0].sources == ["one.md", "two.md"]


def test_extract_links_from_files(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("[A](https://a.example) https://shared.example", encoding="utf-8")
    b.write_text("https://shared.example and [B][b]\n\n[b]: https://b.example", encoding="utf-8")
    links = extract_links_from_files([str(a), str(b)])
    assert urls(links) == ["https://a.example", "https://shared.example", "https://b.example"]
    shared = links[1]
    assert shared.sources == [str(a), str(b)]
