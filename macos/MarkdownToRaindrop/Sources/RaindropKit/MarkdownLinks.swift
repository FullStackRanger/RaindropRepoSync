import Foundation

/// Port of `md_links.py`: extracts http(s) links from Markdown text.
///
/// Handles inline links (`[text](url "title")`), reference-style links
/// (`[text][id]` + `[id]: url "title"`), autolinks (`<url>`) and bare URLs.
/// Image links and anything inside code spans or fenced code blocks are ignored.
/// Indented code blocks are not detected, so links in deeply nested lists still count.
///
/// All offsets are UTF-16 (NSString) offsets; every blanking pass preserves UTF-16 length
/// so positions stay comparable across passes, as they do in the Python original.
public struct Link: Hashable, Sendable, Identifiable {
    public var url: String
    public var title: String
    public var sources: [String]

    public var id: String { url }

    public init(url: String, title: String = "", sources: [String] = []) {
        self.url = url
        self.title = title
        self.sources = sources
    }
}

public enum MarkdownLinks {
    public static let fileExtensions: Set<String> = ["md", "markdown", "mdown", "mkd", "txt"]

    /// The unique http(s) links in `text`, in order of first appearance.
    public static func extractLinks(_ text: String, source: String = "") -> [Link] {
        // Code spans are blanked in `text` but kept in `original` (same offsets) so
        // their content can still appear in link titles.
        let original = stripFencedCode(text) as NSString
        var text = substitute(Pattern.codeSpan, in: original as String) { m, ns in blank(ns.substring(with: m.range)) }
        var found: [(position: Int, url: String, title: String)] = []

        func linkText(_ m: NSTextCheckingResult) -> String {
            original.substring(with: m.range(withName: "text"))
        }

        var definitions: [String: (url: String, title: String)] = [:]
        var definitionOrder: [String] = []
        let textNS = text as NSString
        for m in Pattern.refDef.matches(in: text, range: NSRange(location: 0, length: textNS.length)) {
            let label = normalizeLabel(m.group("id", in: textNS) ?? "")
            guard definitions[label] == nil else { continue }
            let title = firstNonEmpty(m.group("t1", in: textNS), m.group("t2", in: textNS), m.group("t3", in: textNS)) ?? ""
            definitions[label] = (m.group("url", in: textNS) ?? "", title)
            definitionOrder.append(label)
        }
        text = substitute(Pattern.refDef, in: text) { m, ns in blank(ns.substring(with: m.range)) }

        text = substitute(Pattern.inline, in: text) { m, ns in
            if (m.group("bang", in: ns) ?? "").isEmpty {
                let url = (firstNonEmpty(m.group("aurl", in: ns), m.group("url", in: ns)) ?? "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                let title = firstNonEmpty(m.group("t1", in: ns), m.group("t2", in: ns), m.group("t3", in: ns))
                    ?? cleanText(linkText(m))
                found.append((m.range.location, url, title))
            }
            return blank(ns.substring(with: m.range))
        }

        var usedLabels = Set<String>()
        text = substitute(Pattern.refUse, in: text) { m, ns in
            let refID = m.group("id", in: ns) ?? ""
            let label = normalizeLabel(refID.isEmpty ? linkText(m) : refID)
            guard let definition = definitions[label] else { return ns.substring(with: m.range) }
            if (m.group("bang", in: ns) ?? "").isEmpty {
                let title = definition.title.isEmpty ? cleanText(linkText(m)) : definition.title
                found.append((m.range.location, definition.url, title))
            }
            usedLabels.insert(label)
            return blank(ns.substring(with: m.range))
        }

        // Definitions nobody referenced are still links the author wrote down.
        let end = (text as NSString).length
        for label in definitionOrder where !usedLabels.contains(label) {
            let definition = definitions[label]!
            found.append((end, definition.url, definition.title))
        }

        text = substitute(Pattern.autolink, in: text) { m, ns in
            found.append((m.range.location, m.group("url", in: ns) ?? "", ""))
            return blank(ns.substring(with: m.range))
        }

        let finalNS = text as NSString
        for m in Pattern.bareURL.matches(in: text, range: NSRange(location: 0, length: finalNS.length)) {
            let url = trimBareURL(finalNS.substring(with: m.range))
            if !url.isEmpty {
                found.append((m.range.location, url, ""))
            }
        }

        let ordered = found.enumerated()
            .sorted { ($0.element.position, $0.offset) < ($1.element.position, $1.offset) }
            .map(\.element)
        return mergeLinks(ordered.filter { isHTTP($0.url) }.map {
            Link(url: $0.url, title: $0.title, sources: source.isEmpty ? [] : [source])
        })
    }

    /// Dedupe links (see `dedupeKey`), keeping first-seen order and the first non-empty title.
    public static func mergeLinks(_ links: [Link]) -> [Link] {
        var merged: [Link] = []
        var indexByKey: [String: Int] = [:]
        for link in links {
            let key = dedupeKey(link.url)
            guard let index = indexByKey[key] else {
                indexByKey[key] = merged.count
                merged.append(link)
                continue
            }
            if merged[index].title.isEmpty && !link.title.isEmpty {
                merged[index].title = link.title
            }
            for source in link.sources where !merged[index].sources.contains(source) {
                merged[index].sources.append(source)
            }
        }
        return merged
    }

    /// Extract and dedupe links across several Markdown files. Invalid UTF-8 is replaced, not rejected.
    public static func extractLinks(fromFiles paths: [String]) throws -> [Link] {
        var all: [Link] = []
        for path in paths {
            let data = try Data(contentsOf: URL(fileURLWithPath: path))
            all.append(contentsOf: extractLinks(String(decoding: data, as: UTF8.self), source: path))
        }
        return mergeLinks(all)
    }

    /// Key used to treat URLs as duplicates: case-insensitive scheme/host, no trailing slash
    /// (mirrors Python's `urlunsplit(urlsplit(url))` with the path's trailing slashes removed).
    public static func dedupeKey(_ url: String) -> String {
        var rest = Substring(url)
        var scheme = ""
        if let colon = rest.firstIndex(of: ":"), isScheme(rest[..<colon]) {
            scheme = rest[..<colon].lowercased()
            rest = rest[rest.index(after: colon)...]
        }
        var netloc: Substring?
        if rest.hasPrefix("//") {
            rest = rest.dropFirst(2)
            let end = rest.firstIndex { "/?#".contains($0) } ?? rest.endIndex
            netloc = rest[..<end]
            rest = rest[end...]
        }
        var fragment: Substring = ""
        if let hash = rest.firstIndex(of: "#") {
            fragment = rest[rest.index(after: hash)...]
            rest = rest[..<hash]
        }
        var query: Substring = ""
        if let mark = rest.firstIndex(of: "?") {
            query = rest[rest.index(after: mark)...]
            rest = rest[..<mark]
        }
        var path = String(rest)
        while path.hasSuffix("/") { path.removeLast() }

        var out = ""
        if !scheme.isEmpty { out += scheme + ":" }
        let host = netloc.map { $0.lowercased() } ?? ""
        if !host.isEmpty || (netloc != nil && ["http", "https"].contains(scheme)) {
            if !path.isEmpty && !path.hasPrefix("/") { path = "/" + path }
            out += "//" + host
        }
        out += path
        if !query.isEmpty { out += "?" + query }
        if !fragment.isEmpty { out += "#" + fragment }
        return out
    }

    // MARK: - Helpers

    enum Pattern {
        static let fence = regex(#"^ {0,3}(`{3,}|~{3,})"#)
        static let codeSpan = regex(#"(`+)(.+?)\1"#, [.dotMatchesLineSeparators])
        // [id]: <url> "title"  /  [id]: url 'title'  /  [id]: url (title)
        static let refDef = regex(
            #"^ {0,3}\[(?<id>[^\]]+)\]:[ \t]*<?(?<url>[^\s>]+)>?"#
                + #"(?:[ \t]+(?:"(?<t1>[^"]*)"|'(?<t2>[^']*)'|\((?<t3>[^)]*)\)))?[ \t]*$"#,
            [.anchorsMatchLines]
        )
        // Link text allows one level of nested brackets, e.g. [see [docs]](url).
        static let linkText = #"(?<text>(?:[^\[\]]|\[[^\[\]]*\])*)"#
        static let inline = regex(
            #"(?<bang>!?)\["# + linkText + #"\]\(\s*"#
                + #"(?:<(?<aurl>[^>]*)>|(?<url>(?:[^\s()]|\([^\s()]*\))+))"#
                + #"(?:\s+(?:"(?<t1>[^"]*)"|'(?<t2>[^']*)'|\((?<t3>[^)]*)\)))?\s*\)"#
        )
        // [text][id], [text][] and shortcut [text] (only resolved if a definition exists).
        static let refUse = regex(#"(?<bang>!?)\["# + linkText + #"\](?:\[(?<id>[^\]]*)\])?"#)
        static let autolink = regex(#"<(?<url>https?://[^\s<>]+)>"#, [.caseInsensitive])
        static let bareURL = regex(#"https?://[^\s<>"'`\[\]{}|\\^]+"#, [.caseInsensitive])
        static let emphasis = regex(#"[*_`~]+"#)
        static let nestedInline = regex(#"!?\[([^\]]*)\]\([^)]*\)"#)

        private static func regex(_ pattern: String, _ options: NSRegularExpression.Options = []) -> NSRegularExpression {
            // Patterns are compile-time constants covered by tests.
            try! NSRegularExpression(pattern: pattern, options: options)
        }
    }

    private static let trailingPunctuation: Set<Character> = [".", ",", ":", ";", "!", "?", "*", "_", "~", "'", "\""]

    static func isHTTP(_ url: String) -> Bool {
        let lower = url.lowercased()
        return lower.hasPrefix("http://") || lower.hasPrefix("https://")
    }

    static func normalizeLabel(_ label: String) -> String {
        collapseWhitespace(label).lowercased()
    }

    static func cleanText(_ text: String) -> String {
        var text = replace(Pattern.emphasis, in: text, with: "")
        text = replace(Pattern.nestedInline, in: text, with: "$1")
        text = text.replacingOccurrences(of: "[", with: "").replacingOccurrences(of: "]", with: "")
        return collapseWhitespace(text)
    }

    static func stripFencedCode(_ text: String) -> String {
        var out: [String] = []
        var fence: String?
        for line in text.components(separatedBy: "\n") {
            let ns = line as NSString
            let marker = Pattern.fence.firstMatch(in: line, range: NSRange(location: 0, length: ns.length))
                .map { ns.substring(with: $0.range(at: 1)) }
            if let open = fence {
                if let marker, marker.first == open.first, marker.count >= open.count {
                    fence = nil
                }
                out.append("")
            } else if let marker {
                fence = marker
                out.append("")
            } else {
                out.append(line)
            }
        }
        return out.joined(separator: "\n")
    }

    static func trimBareURL(_ url: String) -> String {
        var url = url
        while let last = url.last {
            if trailingPunctuation.contains(last) {
                url.removeLast()
            } else if last == ")" && url.filter({ $0 == ")" }).count > url.filter({ $0 == "(" }).count {
                url.removeLast()
            } else {
                break
            }
        }
        return url
    }

    /// Replace with spaces (newlines kept), one per UTF-16 unit so offsets don't shift.
    private static func blank(_ s: String) -> String {
        String(s.utf16.map { $0 == 0x0A ? "\n" : " " })
    }

    private static func collapseWhitespace(_ s: String) -> String {
        s.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }

    private static func firstNonEmpty(_ values: String?...) -> String? {
        values.lazy.compactMap { $0 }.first { !$0.isEmpty }
    }

    private static func isScheme(_ s: Substring) -> Bool {
        guard let first = s.first, first.isASCII, first.isLetter else { return false }
        return s.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || "+-.".contains($0)) }
    }

    private static func replace(_ re: NSRegularExpression, in text: String, with template: String) -> String {
        re.stringByReplacingMatches(in: text, range: NSRange(location: 0, length: (text as NSString).length), withTemplate: template)
    }

    /// Equivalent of Python's `re.sub(pattern, fn, text)`: matches are found on the input, then replaced.
    private static func substitute(
        _ re: NSRegularExpression,
        in text: String,
        _ transform: (NSTextCheckingResult, NSString) -> String
    ) -> String {
        let ns = text as NSString
        var out = ""
        var last = 0
        for m in re.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            out += ns.substring(with: NSRange(location: last, length: m.range.location - last))
            out += transform(m, ns)
            last = NSMaxRange(m.range)
        }
        out += ns.substring(from: last)
        return out
    }
}

extension NSTextCheckingResult {
    func group(_ name: String, in string: NSString) -> String? {
        let range = range(withName: name)
        return range.location == NSNotFound ? nil : string.substring(with: range)
    }
}
