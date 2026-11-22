import Foundation
import Testing
@testable import RaindropKit

private func urls(_ links: [Link]) -> [String] { links.map(\.url) }
private func extract(_ md: String) -> [Link] { MarkdownLinks.extractLinks(md) }

@Suite struct MarkdownLinksTests {
    @Test func inlineLinksWithTitles() {
        let links = extract(#"See [Example](https://example.com "Example Site") and [Docs](<https://docs.example.com/a b>)."#)
        #expect(urls(links) == ["https://example.com", "https://docs.example.com/a b"])
        #expect(links[0].title == "Example Site")
        #expect(links[1].title == "Docs")
    }

    @Test func inlineLinkWithParenthesesInURL() {
        #expect(urls(extract("[Wiki](https://en.wikipedia.org/wiki/Foo_(bar)) after")) == ["https://en.wikipedia.org/wiki/Foo_(bar)"])
    }

    @Test func linkTextFormattingIsCleaned() {
        #expect(extract("[**Bold** `code` [nested]](https://example.com)")[0].title == "Bold code nested")
    }

    @Test func referenceStyleLinks() {
        let md = """

        Read [the guide][guide], [Other][] and [shortcut].

        [guide]: https://example.com/guide "The Guide"
        [other]: <https://example.com/other>
        [Shortcut]: https://example.com/short 'Short'

        """
        let links = extract(md)
        #expect(urls(links) == ["https://example.com/guide", "https://example.com/other", "https://example.com/short"])
        #expect(links.map(\.title) == ["The Guide", "Other", "Short"])
    }

    @Test func unusedReferenceDefinitionIsStillExtracted() {
        #expect(urls(extract("[orphan]: https://example.com/orphan")) == ["https://example.com/orphan"])
    }

    @Test func bracketsWithoutDefinitionAreIgnored() {
        #expect(extract("- [ ] todo item and [not a link]").isEmpty)
    }

    @Test func autolinksAndBareURLs() {
        let md = "Visit <https://auto.example.com/x> or https://bare.example.com/path?q=1, ok."
        #expect(urls(extract(md)) == ["https://auto.example.com/x", "https://bare.example.com/path?q=1"])
    }

    @Test func bareURLTrailingPunctuationAndParens() {
        let md = "(see https://example.com/a) and https://example.com/b. Also https://en.wikipedia.org/wiki/X_(y)!"
        #expect(urls(extract(md)) == ["https://example.com/a", "https://example.com/b", "https://en.wikipedia.org/wiki/X_(y)"])
    }

    @Test func imagesAreSkipped() {
        #expect(urls(extract("![logo](https://example.com/logo.png) [site](https://example.com)")) == ["https://example.com"])
    }

    @Test func linkedImageKeepsOuterLink() {
        #expect(urls(extract("[![badge](https://img.shields.io/x.svg)](https://ci.example.com)")) == ["https://ci.example.com"])
    }

    @Test func nonHTTPLinksAreIgnored() {
        let md = "[mail](mailto:a@b.c) [rel](./other.md) [anchor](#top) [ftp](ftp://x.org) [ok](http://ok.example)"
        #expect(urls(extract(md)) == ["http://ok.example"])
    }

    @Test func codeIsIgnored() {
        let md = """

        Inline `https://code.example.com` is skipped.

        ```bash
        curl https://fenced.example.com
        ```

        ~~~
        [x](https://tilde.example.com)
        ~~~

        After https://after.example.com

        """
        #expect(urls(extract(md)) == ["https://after.example.com"])
    }

    @Test func nestedListLinksAreKept() {
        #expect(urls(extract("- top\n    - [deep](https://deep.example.com)\n")) == ["https://deep.example.com"])
    }

    @Test func dedupePreservesOrderAndPrefersTitledEntry() {
        let links = extract("https://example.com/ then [Example](https://EXAMPLE.com) then https://other.example")
        #expect(urls(links) == ["https://example.com/", "https://other.example"])
        #expect(links[0].title == "Example")
    }

    @Test func dedupeKeyKeepsQueryAndPathCase() {
        #expect(MarkdownLinks.dedupeKey("HTTPS://Example.COM/Path/") == "https://example.com/Path")
        #expect(MarkdownLinks.dedupeKey("https://e.com/?a=1") != MarkdownLinks.dedupeKey("https://e.com/?a=2"))
    }

    @Test func mergeLinksCombinesSources() {
        let merged = MarkdownLinks.mergeLinks([
            Link(url: "https://a.example", title: "", sources: ["one.md"]),
            Link(url: "https://a.example/", title: "A", sources: ["two.md"]),
        ])
        #expect(merged.count == 1)
        #expect(merged[0].title == "A")
        #expect(merged[0].sources == ["one.md", "two.md"])
    }

    @Test func extractLinksFromFiles() throws {
        let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let a = dir.appending(path: "a.md").path
        let b = dir.appending(path: "b.md").path
        try "[A](https://a.example) https://shared.example".write(toFile: a, atomically: true, encoding: .utf8)
        try "https://shared.example and [B][b]\n\n[b]: https://b.example".write(toFile: b, atomically: true, encoding: .utf8)
        let links = try MarkdownLinks.extractLinks(fromFiles: [a, b])
        #expect(urls(links) == ["https://a.example", "https://shared.example", "https://b.example"])
        #expect(links[1].sources == [a, b])
    }

    @Test func nonASCIITextKeepsOffsetsAligned() {
        let links = extract("Café 🎉 `👩‍💻 code` [Ünïcode 🎉](https://u.example) then https://after.example")
        #expect(urls(links) == ["https://u.example", "https://after.example"])
        #expect(links[0].title == "Ünïcode 🎉")
    }

    @Test func invalidUTF8IsReplacedNotRejected() throws {
        let path = FileManager.default.temporaryDirectory.appending(path: "\(UUID().uuidString).md").path
        defer { try? FileManager.default.removeItem(atPath: path) }
        var data = Data("ok https://x.example ".utf8)
        data.append(contentsOf: [0xFF, 0xFE])
        try data.write(to: URL(fileURLWithPath: path))
        #expect(urls(try MarkdownLinks.extractLinks(fromFiles: [path])) == ["https://x.example"])
    }
}
