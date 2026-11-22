import RaindropKit
import SwiftUI
import UniformTypeIdentifiers

enum MarkdownTypes {
    static let all: [UTType] = {
        var types = MarkdownLinks.fileExtensions.compactMap { UTType(filenameExtension: $0) }
        if let markdown = UTType("net.daringfireball.markdown") { types.append(markdown) }
        return types + [.plainText]
    }()
}

struct ContentView: View {
    @Environment(AppModel.self) private var model
    @State private var showImporter = false
    @State private var isDropTargeted = false
    @State private var search = ""

    var body: some View {
        @Bindable var model = model
        NavigationSplitView {
            SidebarView(showImporter: $showImporter)
                .navigationSplitViewColumnWidth(min: 220, ideal: 270, max: 380)
        } detail: {
            LinksView(search: search, showImporter: $showImporter)
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    SaveBar().padding(14)
                }
                .overlay {
                    if isDropTargeted { DropOverlay().transition(.opacity) }
                }
                .animation(.easeOut(duration: 0.15), value: isDropTargeted)
        }
        .navigationTitle("Markdown → Raindrop")
        .navigationSubtitle(model.rows.isEmpty ? "No links" : "\(model.selectedCount) of \(model.rows.count) selected")
        .searchable(text: $search, placement: .toolbar, prompt: "Filter links")
        .inspector(isPresented: $model.isLogVisible) {
            LogView().inspectorColumnWidth(min: 240, ideal: 300, max: 480)
        }
        .toolbar { toolbar }
        .dropDestination(for: URL.self) { urls, _ in
            model.addFiles(urls)
            return !urls.isEmpty
        } isTargeted: { isDropTargeted = $0 }
        .fileImporter(isPresented: $showImporter, allowedContentTypes: MarkdownTypes.all, allowsMultipleSelection: true) { result in
            switch result {
            case let .success(urls): model.addFiles(urls)
            case let .failure(error): model.appendLog("Could not open files: \(error.localizedDescription)", isError: true)
            }
        }
        .alert(
            model.alert?.title ?? "",
            isPresented: Binding(get: { model.alert != nil }, set: { if !$0 { model.alert = nil } }),
            presenting: model.alert
        ) { _ in
            Button("OK") {}
            if model.failedCount > 0 && !model.isSaving {
                Button("Show Log") { model.isLogVisible = true }
            }
        } message: { Text($0.message) }
        .onReceive(NotificationCenter.default.publisher(for: .showFileImporter)) { _ in showImporter = true }
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button { showImporter = true } label: {
                Label("Add Files", systemImage: "doc.badge.plus")
            }
            .help("Add Markdown files (⌘O)")

            Button { model.loadCollections() } label: {
                Label("Reload Collections", systemImage: "arrow.clockwise")
            }
            .help("Reload Raindrop collections (⌘R)")
            .disabled(model.isLoadingCollections || model.isSaving || !model.hasToken)

            Menu {
                Button("Select All") { model.setAll(true) }
                Button("Select None") { model.setAll(false) }
            } label: {
                Label("Selection", systemImage: "checklist")
            }
            .help("Select or deselect all links")
            .disabled(model.rows.isEmpty || model.isSaving)

            if model.failedCount > 0 && !model.isSaving {
                Button { model.retryFailed() } label: {
                    Label("Retry Failed", systemImage: "arrow.counterclockwise.circle")
                }
                .help("Retry the \(model.failedCount) failed link(s)")
            }
        }

        ToolbarItem(placement: .primaryAction) {
            Button { model.isLogVisible.toggle() } label: {
                Label("Log", systemImage: "list.bullet.rectangle.portrait")
            }
            .help("Show or hide the activity log (⌥⌘L)")
            .keyboardShortcut("l", modifiers: [.command, .option])
        }
    }
}

private struct DropOverlay: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 24, style: .continuous)
            .strokeBorder(Color.accentColor, style: StrokeStyle(lineWidth: 3, dash: [10, 6]))
            .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay {
                Label("Drop Markdown Files", systemImage: "arrow.down.doc.fill")
                    .font(.title2.weight(.semibold))
                    .padding(.horizontal, 22)
                    .padding(.vertical, 14)
                    .glassCapsule(tint: .accentColor)
            }
            .padding(16)
            .allowsHitTesting(false)
    }
}
