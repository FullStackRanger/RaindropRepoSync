import SwiftUI

struct ContentView: View {
    @Environment(ClipperModel.self) private var model
    @FocusState private var urlFocused: Bool

    var body: some View {
        @Bindable var model = model
        Group {
            if model.article != nil {
                EditorView()
            } else {
                EmptyStateView()
            }
        }
        .frame(minWidth: 560, minHeight: 520)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            StatusBar()
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
        }
        .navigationTitle(model.article == nil ? "Web Clipper" : (model.title.isEmpty ? "Untitled" : model.title))
        .navigationSubtitle(model.article == nil ? "Clip a page to Markdown" : model.info)
        .toolbar { toolbar }
        .inspector(isPresented: $model.showInspector) {
            InspectorView()
                .inspectorColumnWidth(min: 280, ideal: 320, max: 420)
        }
        .onChange(of: model.focusURLRequest) { _, _ in urlFocused = true }
        .alert(item: $model.alert) { item in
            Alert(title: Text(item.title), message: Text(item.message))
        }
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        @Bindable var model = model
        ToolbarItem(placement: .principal) {
            HStack(spacing: 6) {
                Image(systemName: model.isBusy ? "arrow.triangle.2.circlepath" : "link")
                    .foregroundStyle(.secondary)
                    .symbolEffect(.pulse, isActive: model.isBusy)
                TextField("Paste or type a URL", text: $model.urlText)
                    .textFieldStyle(.plain)
                    .focused($urlFocused)
                    .onSubmit { Task { await model.clip() } }
                    .disabled(model.isBusy)
                if !model.urlText.isEmpty && !model.isBusy {
                    Button {
                        model.urlText = ""
                        urlFocused = true
                    } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.tertiary)
                    }
                    .buttonStyle(.plain)
                    .help("Clear")
                }
            }
            .padding(.horizontal, 10)
            .frame(minWidth: 320, idealWidth: 460, maxWidth: 560)
        }

        ToolbarItemGroup(placement: .primaryAction) {
            Button {
                Task { await model.pasteAndClip() }
            } label: {
                Label("Paste and Clip", systemImage: "doc.on.clipboard")
            }
            .help("Clip the URL on the clipboard (⇧⌘V)")
            .disabled(model.isBusy)

            Button {
                Task { await model.clip() }
            } label: {
                Label("Clip", systemImage: "scissors")
            }
            .help("Fetch the page and convert it to Markdown (Return)")
            .disabled(model.isBusy || model.urlText.trimmingCharacters(in: .whitespaces).isEmpty)
        }

        ToolbarItemGroup(placement: .primaryAction) {
            Button {
                Task { await model.save() }
            } label: {
                Label("Save Note", systemImage: "square.and.arrow.down")
            }
            .help("Save the note (⌘S)")
            .disabled(!model.canSave)

            Menu {
                Button("Copy to Vault", systemImage: "tray.and.arrow.down") { Task { await model.copyToVaultNow() } }
                    .disabled(model.savedPath == nil)
                Button("Show in Finder", systemImage: "folder") { model.reveal() }
                    .disabled(model.savedPath == nil)
                Button("Open in Obsidian", systemImage: "arrow.up.forward.app") { model.openInObsidian() }
                    .disabled(model.vaultCopyPath == nil)
            } label: {
                Label("More", systemImage: "ellipsis")
            }
            .help("Vault, Finder and Obsidian")
        }

        ToolbarItem(placement: .primaryAction) {
            Button {
                model.showInspector.toggle()
            } label: {
                Label("Inspector", systemImage: "sidebar.trailing")
            }
            .help("Show or hide save and Obsidian options")
        }
    }
}

struct EmptyStateView: View {
    @Environment(ClipperModel.self) private var model

    var body: some View {
        VStack(spacing: 20) {
            if let problem = model.engineProblem {
                ContentUnavailableView {
                    Label("Clipper engine unavailable", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(problem)
                } actions: {
                    SettingsLink { Text("Open Settings…") }
                    Button("Try Again") { Task { await model.reloadEngine() } }
                }
            } else if model.isBusy {
                ProgressView {
                    Text("Fetching page…")
                }
                .controlSize(.large)
            } else {
                ContentUnavailableView {
                    Label("Clip a web page", systemImage: "doc.richtext")
                } description: {
                    Text("Paste a URL in the toolbar and press Return, or click **Send to Web Clipper** in your browser. You can edit the title, tags and Markdown before saving.")
                } actions: {
                    HStack {
                        Button {
                            Task { await model.pasteAndClip() }
                        } label: {
                            Label("Paste and Clip", systemImage: "doc.on.clipboard")
                        }
                        .prominentGlassButton()
                        .controlSize(.large)
                        .fixedSize()
                        Button {
                            model.focusURLRequest += 1
                        } label: {
                            Label("Type a URL", systemImage: "keyboard")
                        }
                        .glassButton()
                        .controlSize(.large)
                        .fixedSize()
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct StatusBar: View {
    @Environment(ClipperModel.self) private var model

    var body: some View {
        HStack(spacing: 10) {
            if model.isBusy {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: statusSymbol)
                    .foregroundStyle(statusColor)
                    .contentTransition(.symbolEffect(.replace))
            }
            Text(model.status)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
            Spacer(minLength: 12)
            BridgeBadge()
        }
        .font(.callout)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .glassSurface(in: Capsule())
    }

    private var statusSymbol: String {
        if model.vaultCopyPath != nil { return "checkmark.seal.fill" }
        if model.savedPath != nil { return "checkmark.circle.fill" }
        if model.log.last?.isError == true { return "exclamationmark.triangle.fill" }
        return "info.circle"
    }

    private var statusColor: Color {
        if model.savedPath != nil { return .green }
        if model.log.last?.isError == true { return .orange }
        return .secondary
    }
}

struct BridgeBadge: View {
    @Environment(ClipperModel.self) private var model

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(color)
                .frame(width: 7, height: 7)
            Text(short)
                .foregroundStyle(.secondary)
        }
        .help(model.bridge.label)
    }

    private var color: Color {
        switch model.bridge {
        case .listening: .green
        case .off: .gray
        case .failed: .orange
        }
    }

    private var short: String {
        switch model.bridge {
        case .listening(let port): "Browser button · \(port)"
        case .off: "Browser button off"
        case .failed: "Port busy"
        }
    }
}
