import AppKit
import RaindropKit
import SwiftUI

struct SidebarView: View {
    @Environment(AppModel.self) private var model
    @Binding var showImporter: Bool
    @State private var collapsed: Set<Int> = []

    var body: some View {
        @Bindable var model = model
        List(selection: $model.selectedCollectionID) {
            Section("Markdown Files") {
                if model.files.isEmpty {
                    Button { showImporter = true } label: {
                        Label("Add Files…", systemImage: "plus.circle")
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .selectionDisabled()
                }
                ForEach(model.files, id: \.self) { path in
                    FileRow(path: path, linkCount: model.linkCount(for: path))
                        .selectionDisabled()
                        .contextMenu {
                            Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)]) }
                            Divider()
                            Button("Remove", role: .destructive) { model.removeFiles([path]) }
                                .disabled(model.isSaving)
                        }
                }
            }

            Section {
                if !model.hasToken {
                    TokenPrompt().selectionDisabled()
                } else if model.collectionTree.isEmpty {
                    HStack(spacing: 8) {
                        if model.isLoadingCollections { ProgressView().controlSize(.small) }
                        Text(model.isLoadingCollections ? "Loading…" : "No collections loaded")
                            .foregroundStyle(.secondary)
                    }
                    .selectionDisabled()
                } else {
                    CollectionRows(nodes: model.collectionTree, collapsed: $collapsed)
                }
            } header: {
                HStack {
                    Text("Save To")
                    Spacer()
                    if model.isLoadingCollections && !model.collectionTree.isEmpty {
                        ProgressView().controlSize(.mini)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .disabled(model.isSaving)
        .safeAreaInset(edge: .bottom) {
            if !model.files.isEmpty {
                HStack {
                    Button { showImporter = true } label: { Label("Add", systemImage: "plus") }
                    Spacer()
                    Button(role: .destructive) { model.clearFiles() } label: { Label("Clear Files", systemImage: "xmark.circle") }
                        .disabled(model.isSaving)
                }
                .labelStyle(.iconOnly)
                .buttonStyle(.borderless)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
            }
        }
    }
}

private struct FileRow: View {
    let path: String
    let linkCount: Int

    var body: some View {
        Label {
            HStack {
                Text((path as NSString).lastPathComponent).lineLimit(1).truncationMode(.middle)
                Spacer()
                Text("\(linkCount)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        } icon: {
            Image(systemName: "doc.text")
        }
        .help(path)
    }
}

private struct CollectionRows: View {
    let nodes: [CollectionNode]
    @Binding var collapsed: Set<Int>

    var body: some View {
        ForEach(nodes) { node in
            if let children = node.children {
                DisclosureGroup(isExpanded: expansion(node.id)) {
                    CollectionRows(nodes: children, collapsed: $collapsed)
                } label: {
                    CollectionLabel(collection: node.collection, hasChildren: true)
                        .tag(Optional(node.id))
                }
            } else {
                CollectionLabel(collection: node.collection, hasChildren: false)
                    .tag(Optional(node.id))
            }
        }
    }

    private func expansion(_ id: Int) -> Binding<Bool> {
        Binding(
            get: { !collapsed.contains(id) },
            set: { expanded in if expanded { collapsed.remove(id) } else { collapsed.insert(id) } }
        )
    }
}

private struct CollectionLabel: View {
    let collection: RaindropCollection
    let hasChildren: Bool

    var body: some View {
        Label(collection.title, systemImage: icon)
            .badge(collection.count)
            .help(collection.path)
    }

    private var icon: String {
        if collection.id == unsortedCollectionID { return "tray" }
        return hasChildren ? "folder.fill" : "folder"
    }
}

private struct TokenPrompt: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Connect Raindrop.io", systemImage: "key.fill")
                .font(.headline)
            Text("Add your API token to load collections.")
                .font(.callout)
                .foregroundStyle(.secondary)
            SettingsLink { Text("Open Settings…") }
                .glassButton()
                .controlSize(.small)
        }
        .padding(.vertical, 6)
    }
}
