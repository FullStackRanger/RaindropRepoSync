import SwiftUI

struct EditorView: View {
    @Environment(ClipperModel.self) private var model
    var body: some View {
        @Bindable var model = model
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 8) {
                TextField("Title", text: $model.title, axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(.title, design: .serif, weight: .semibold))
                    .lineLimit(1...3)

                if let article = model.article {
                    HStack(spacing: 6) {
                        Image(systemName: "globe")
                        Link(URL(string: article.url)?.host() ?? article.url, destination: URL(string: article.url) ?? URL(fileURLWithPath: "/"))
                        if !article.author.isEmpty {
                            Text("·")
                            Label(article.author, systemImage: "person").labelStyle(.titleAndIcon)
                        }
                        if !article.published.isEmpty {
                            Text("·")
                            Label(article.published, systemImage: "calendar").labelStyle(.titleAndIcon)
                        }
                        Text("·")
                        Text("\(model.body.split(whereSeparator: \.isWhitespace).count) words")
                    }
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                }
            }

            TagEditor()

            HStack {
                Picker("Mode", selection: $model.editorMode) {
                    ForEach(EditorMode.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
                Spacer()
                if model.savedPath != nil {
                    Label("Saved", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                        .font(.callout)
                } else {
                    Label("Not saved yet", systemImage: "circle.dashed")
                        .foregroundStyle(.secondary)
                        .font(.callout)
                }
            }

            Group {
                switch model.editorMode {
                case .markdown:
                    TextEditor(text: $model.body)
                        .font(.system(size: 13, design: .monospaced))
                        .scrollContentBackground(.hidden)
                        .padding(10)
                case .preview:
                    ScrollView {
                        MarkdownPreview(text: model.body)
                            .padding(18)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.separator, lineWidth: 0.5))
        }
        .padding(.horizontal, 24)
        .padding(.top, 18)
        .padding(.bottom, 8)
    }
}

struct TagEditor: View {
    @Environment(ClipperModel.self) private var model

    var body: some View {
        @Bindable var model = model
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: "tag")
                    .foregroundStyle(.secondary)
                TextField("Tags (comma or space separated)", text: $model.tags)
                    .textFieldStyle(.roundedBorder)
            }
            let tags = ClipperModel.parsedTags(model.tags)
            if !tags.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(tags, id: \.self) { tag in
                        HStack(spacing: 4) {
                            Text("#" + tag)
                            Button {
                                model.removeTag(tag)
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.caption2.weight(.bold))
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(.secondary)
                            .help("Remove tag")
                        }
                        .font(.callout)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 3)
                        .background(Color.accentColor.opacity(0.14), in: Capsule())
                    }
                }
                .padding(.leading, 26)
            }
        }
    }
}

/// Lightweight block-aware Markdown preview (headings, quotes, lists, code fences, rules, paragraphs).
struct MarkdownPreview: View {
    let text: String

    private enum Block: Hashable {
        case heading(Int, String)
        case paragraph(String)
        case quote(String)
        case bullet(String)
        case code(String)
        case rule
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                view(for: block)
            }
        }
        .textSelection(.enabled)
    }

    @ViewBuilder
    private func view(for block: Block) -> some View {
        switch block {
        case .heading(let level, let text):
            inline(text)
                .font(level == 1 ? .title.bold() : level == 2 ? .title2.bold() : .title3.bold())
                .padding(.top, 6)
        case .paragraph(let text):
            inline(text).font(.body)
        case .quote(let text):
            inline(text)
                .foregroundStyle(.secondary)
                .padding(.leading, 12)
                .overlay(alignment: .leading) { Rectangle().fill(.tertiary).frame(width: 3) }
        case .bullet(let text):
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("•")
                inline(text)
            }
        case .code(let text):
            Text(text)
                .font(.system(size: 12, design: .monospaced))
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
        case .rule:
            Divider()
        }
    }

    private func inline(_ text: String) -> Text {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return Text((try? AttributedString(markdown: text, options: options)) ?? AttributedString(text))
    }

    private var blocks: [Block] {
        var result: [Block] = []
        var paragraph: [String] = []
        var code: [String]?

        func flush() {
            if !paragraph.isEmpty { result.append(.paragraph(paragraph.joined(separator: " "))) }
            paragraph = []
        }

        for raw in text.components(separatedBy: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("```") {
                if let lines = code {
                    result.append(.code(lines.joined(separator: "\n")))
                    code = nil
                } else {
                    flush()
                    code = []
                }
                continue
            }
            if code != nil {
                code?.append(raw)
                continue
            }
            if line.isEmpty {
                flush()
            } else if let hashes = line.firstIndex(where: { $0 != "#" }), line.hasPrefix("#"),
                      line[hashes] == " ", line.distance(from: line.startIndex, to: hashes) <= 6 {
                flush()
                result.append(.heading(line.distance(from: line.startIndex, to: hashes), String(line[hashes...]).trimmingCharacters(in: .whitespaces)))
            } else if line.hasPrefix(">") {
                flush()
                result.append(.quote(String(line.dropFirst()).trimmingCharacters(in: .whitespaces)))
            } else if line.hasPrefix("- ") || line.hasPrefix("* ") || line.hasPrefix("+ ") {
                flush()
                result.append(.bullet(String(line.dropFirst(2))))
            } else if line == "---" || line == "***" {
                flush()
                result.append(.rule)
            } else {
                paragraph.append(line)
            }
        }
        if let lines = code { result.append(.code(lines.joined(separator: "\n"))) }
        flush()
        return result
    }
}
