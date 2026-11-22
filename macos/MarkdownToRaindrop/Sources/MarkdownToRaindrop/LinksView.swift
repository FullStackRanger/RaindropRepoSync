import AppKit
import SwiftUI

struct LinksView: View {
    @Environment(AppModel.self) private var model
    let search: String
    @Binding var showImporter: Bool
    @State private var selection: Set<String> = []
    @State private var sortOrder: [KeyPathComparator<LinkRow>] = []

    var body: some View {
        if model.rows.isEmpty {
            EmptyState(hasFiles: !model.files.isEmpty, showImporter: $showImporter)
        } else {
            table
        }
    }

    private var displayedRows: [LinkRow] {
        let query = search.trimmingCharacters(in: .whitespaces)
        let filtered = query.isEmpty ? model.rows : model.rows.filter {
            $0.title.localizedCaseInsensitiveContains(query) || $0.url.localizedCaseInsensitiveContains(query)
                || $0.sourceNames.localizedCaseInsensitiveContains(query)
        }
        return sortOrder.isEmpty ? filtered : filtered.sorted(using: sortOrder)
    }

    private var table: some View {
        Table(displayedRows, selection: $selection, sortOrder: $sortOrder) {
            TableColumn("") { row in
                Toggle("Save", isOn: Binding(get: { row.isChecked }, set: { model.setChecked([row.id], to: $0) }))
                    .labelsHidden()
                    .toggleStyle(.checkbox)
                    .disabled(model.isSaving)
            }
            .width(24)

            TableColumn("Title", value: \.title) { row in
                Text(row.title.isEmpty ? "Untitled" : row.title)
                    .foregroundStyle(row.title.isEmpty ? .tertiary : .primary)
                    .lineLimit(1)
            }
            .width(min: 140, ideal: 240)

            TableColumn("URL", value: \.url) { row in
                Text(row.url)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .width(min: 160, ideal: 300)

            TableColumn("Source", value: \.sourceNames) { row in
                Text(row.sourceNames).foregroundStyle(.secondary).lineLimit(1)
            }
            .width(min: 80, ideal: 120)

            TableColumn("Status", value: \.statusOrder) { row in
                StatusBadge(status: row.status)
            }
            .width(min: 76, ideal: 84)
        }
        .tableStyle(.inset(alternatesRowBackgrounds: true))
        .onKeyPress(.space) {
            guard !model.isSaving, !selection.isEmpty else { return .ignored }
            model.toggleChecked(selection)
            return .handled
        }
        .contextMenu(forSelectionType: String.self) { ids in
            Button("Check") { model.setChecked(ids, to: true) }.disabled(model.isSaving)
            Button("Uncheck") { model.setChecked(ids, to: false) }.disabled(model.isSaving)
            Divider()
            Button("Open in Browser") { open(ids) }
            Button("Copy URL\(ids.count == 1 ? "" : "s")") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(ids.sorted().joined(separator: "\n"), forType: .string)
            }
        } primaryAction: { ids in
            open(ids)
        }
    }

    private func open(_ ids: Set<String>) {
        for id in ids { if let url = URL(string: id) { NSWorkspace.shared.open(url) } }
    }
}

private struct StatusBadge: View {
    let status: LinkStatus

    var body: some View {
        switch status {
        case .none:
            Text("—").foregroundStyle(.quaternary)
        case .saved:
            Label("Saved", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
        case .skipped:
            Label("Exists", systemImage: "arrow.uturn.forward.circle.fill").foregroundStyle(.secondary)
                .help("Already in Raindrop — skipped")
        case let .failed(message):
            Label("Failed", systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red)
                .help(message)
        }
    }
}

private struct EmptyState: View {
    let hasFiles: Bool
    @Binding var showImporter: Bool

    var body: some View {
        ContentUnavailableView {
            Label(hasFiles ? "No Links Found" : "Drop Markdown Files Here", systemImage: hasFiles ? "link.badge.plus" : "doc.text.magnifyingglass")
        } description: {
            Text(hasFiles
                 ? "These files have no http(s) links outside code blocks."
                 : "Links are extracted from inline, reference-style, autolinks and bare URLs. Images and code are skipped.")
        } actions: {
            Button { showImporter = true } label: {
                Label("Choose Files…", systemImage: "folder")
            }
            .prominentGlassButton()
            .controlSize(.large)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
