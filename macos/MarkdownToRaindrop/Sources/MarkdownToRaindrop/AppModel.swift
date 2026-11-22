import Foundation
import Observation
import RaindropKit

enum LinkStatus: Hashable {
    case none, saved, skipped
    case failed(String)
}

struct LinkRow: Identifiable, Hashable {
    var link: Link
    var isChecked: Bool
    var status: LinkStatus

    var id: String { link.url }
    var title: String { link.title }
    var url: String { link.url }
    var sourceNames: String { link.sources.map { ($0 as NSString).lastPathComponent }.joined(separator: ", ") }
    var statusOrder: Int {
        switch status {
        case .failed: 0
        case .none: 1
        case .skipped: 2
        case .saved: 3
        }
    }
}

struct LogEntry: Identifiable {
    let id = UUID()
    let date = Date()
    let message: String
    let isError: Bool
}

struct AlertItem: Identifiable {
    let id = UUID()
    let title: String
    let message: String
}

final class StopFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var stopped = false
    var isSet: Bool { lock.withLock { stopped } }
    func set() { lock.withLock { stopped = true } }
}

@MainActor @Observable
final class AppModel {
    let demoMode: Bool
    private let tokenStore = TokenStore()

    var token = ""
    var tokenSource: TokenStore.Source = .none

    var files: [String] = []
    var rows: [LinkRow] = []
    var collections: [RaindropCollection] = []
    var collectionTree: [CollectionNode] = []
    var selectedCollectionID: Int?
    var tags = ""
    var skipExisting = true

    var statusMessage = "Add Markdown files to get started."
    var progressDone = 0
    var progressTotal = 0
    var isSaving = false
    var isCancelling = false
    var isLoadingCollections = false
    var log: [LogEntry] = []
    var isLogVisible = false
    var alert: AlertItem?

    private var stopFlag: StopFlag?

    init(demoMode: Bool) {
        self.demoMode = demoMode
        if demoMode {
            token = "demo-token"
            tokenSource = .environment
        } else {
            (token, tokenSource) = tokenStore.resolve()
        }
    }

    // MARK: Derived state

    var selectedCount: Int { rows.lazy.filter(\.isChecked).count }
    var failedCount: Int { rows.lazy.filter { if case .failed = $0.status { true } else { false } }.count }
    var selectedCollection: RaindropCollection? { collections.first { $0.id == selectedCollectionID } }
    var hasToken: Bool { !token.trimmingCharacters(in: .whitespaces).isEmpty }
    var canSave: Bool { !isSaving && selectedCount > 0 && selectedCollection != nil && hasToken }
    var progressFraction: Double { progressTotal == 0 ? 0 : Double(progressDone) / Double(progressTotal) }

    func linkCount(for file: String) -> Int { rows.lazy.filter { $0.link.sources.contains(file) }.count }

    // MARK: Token

    func saveToken(_ newToken: String) {
        let trimmed = newToken.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            if trimmed.isEmpty {
                try tokenStore.delete()
                (token, tokenSource) = tokenStore.resolve()
                appendLog("Removed token from Keychain.")
            } else {
                try tokenStore.save(trimmed)
                token = trimmed
                tokenSource = .keychain
                appendLog("Saved token to Keychain.")
                loadCollections()
            }
        } catch {
            show("Keychain", error)
        }
    }

    // MARK: Files

    func addFiles(_ urls: [URL]) {
        var added = false
        for url in urls where url.isFileURL {
            let path = url.standardizedFileURL.path
            guard MarkdownLinks.fileExtensions.contains(url.pathExtension.lowercased()) else {
                appendLog("Skipped \(url.lastPathComponent): not a Markdown or text file.", isError: true)
                continue
            }
            if !files.contains(path) {
                files.append(path)
                added = true
            }
        }
        if added { refreshLinks() }
    }

    func removeFiles(_ paths: Set<String>) {
        files.removeAll { paths.contains($0) }
        refreshLinks()
    }

    func clearFiles() {
        files = []
        refreshLinks()
    }

    private func refreshLinks() {
        let links: [Link]
        do {
            links = try MarkdownLinks.extractLinks(fromFiles: files)
        } catch {
            appendLog("Could not read file: \(error.localizedDescription)", isError: true)
            alert = AlertItem(title: "Read Error", message: error.localizedDescription)
            return
        }
        let previous = Dictionary(rows.map { ($0.url, $0) }, uniquingKeysWith: { first, _ in first })
        rows = links.map { link in
            LinkRow(link: link, isChecked: previous[link.url]?.isChecked ?? true, status: previous[link.url]?.status ?? .none)
        }
        statusMessage = files.isEmpty
            ? "Add Markdown files to get started."
            : "Found \(links.count) unique links in \(files.count) file\(files.count == 1 ? "" : "s")."
    }

    // MARK: Selection

    func setChecked(_ ids: Set<String>, to value: Bool) {
        for index in rows.indices where ids.contains(rows[index].id) {
            rows[index].isChecked = value
        }
    }

    /// Space-bar behaviour from the tkinter app: check all unless every row is already checked.
    func toggleChecked(_ ids: Set<String>) {
        let targets = rows.filter { ids.contains($0.id) }
        guard !targets.isEmpty else { return }
        setChecked(ids, to: !targets.allSatisfy(\.isChecked))
    }

    func setAll(_ value: Bool) {
        for index in rows.indices { rows[index].isChecked = value }
    }

    // MARK: Raindrop

    private func makeClient() -> RaindropClient? {
        do {
            return try RaindropClient(
                token: token.trimmingCharacters(in: .whitespacesAndNewlines),
                transport: demoMode ? DemoTransport() : URLSessionTransport()
            )
        } catch {
            alert = AlertItem(title: "Missing Token", message: "Add your Raindrop API token in Settings (or set RAINDROP_TOKEN).")
            return nil
        }
    }

    func loadCollections() {
        guard !isLoadingCollections, let client = makeClient() else { return }
        isLoadingCollections = true
        statusMessage = "Loading collections…"
        Task {
            defer { isLoadingCollections = false }
            do {
                let loaded = try await client.getCollections()
                collections = loaded
                collectionTree = buildCollectionTree(loaded)
                if selectedCollection == nil { selectedCollectionID = loaded.first?.id }
                statusMessage = "Loaded \(loaded.count) collections."
                appendLog("Loaded \(loaded.count) collections.")
            } catch {
                statusMessage = "Could not load collections."
                appendLog("Failed to load collections: \(error.localizedDescription)", isError: true)
                show("Could Not Load Collections", error)
            }
        }
    }

    func retryFailed() {
        for index in rows.indices {
            if case .failed = rows[index].status { rows[index].isChecked = true } else { rows[index].isChecked = false }
        }
        save()
    }

    func save() {
        let toSave = rows.filter(\.isChecked).map(\.link)
        guard !toSave.isEmpty else {
            alert = AlertItem(title: "Nothing to Save", message: "Select at least one link.")
            return
        }
        guard let collection = selectedCollection else {
            alert = AlertItem(title: "No Collection", message: "Load your collections and choose where to save.")
            return
        }
        guard let client = makeClient() else { return }

        let tags = tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        let skipExisting = skipExisting
        let flag = StopFlag()
        stopFlag = flag
        isSaving = true
        isCancelling = false
        progressDone = 0
        progressTotal = toSave.count
        let ids = Set(toSave.map(\.url))
        for index in rows.indices where ids.contains(rows[index].id) { rows[index].status = .none }
        statusMessage = "Saving \(toSave.count) links to “\(collection.path)”…"
        appendLog("Saving \(toSave.count) links to \(collection.path)…")

        Task {
            do {
                let results = try await client.saveLinks(
                    toSave, collectionID: collection.id, tags: tags, skipExisting: skipExisting,
                    shouldStop: { flag.isSet }
                ) { i, total, result in
                    await self.showProgress(i, total, result)
                }
                finishSave(results, requested: toSave.count)
            } catch {
                isSaving = false
                statusMessage = "Save failed."
                appendLog("Save failed: \(error.localizedDescription)", isError: true)
                show("Save Failed", error)
            }
        }
    }

    func cancelSave() {
        stopFlag?.set()
        isCancelling = true
        statusMessage = "Cancelling after the current link…"
    }

    private func showProgress(_ i: Int, _ total: Int, _ result: SaveResult) {
        progressDone = i
        if !isCancelling { statusMessage = "Saving \(i)/\(total)…" }
        guard let index = rows.firstIndex(where: { $0.url == result.url }) else { return }
        if result.ok {
            rows[index].status = result.skipped ? .skipped : .saved
            rows[index].isChecked = false
            appendLog(result.skipped ? "SKIP (already saved): \(result.url)" : "SAVED: \(result.url)")
        } else {
            rows[index].status = .failed(result.error)
            appendLog("FAILED: \(result.url) — \(result.error)", isError: true)
        }
    }

    private func finishSave(_ results: [SaveResult], requested: Int) {
        isSaving = false
        isCancelling = false
        let saved = results.filter { $0.ok && !$0.skipped }.count
        let skipped = results.filter(\.skipped).count
        let failed = results.filter { !$0.ok }.count
        var summary = "Saved \(saved), skipped \(skipped), failed \(failed)"
        if results.count < requested { summary += ", cancelled \(requested - results.count)" }
        statusMessage = summary + "."
        appendLog(summary + ".", isError: failed > 0)
        if failed > 0 {
            alert = AlertItem(
                title: "Some Links Failed",
                message: "\(summary).\nFailed links stay selected so you can retry. See the log for details."
            )
        }
    }

    // MARK: Log

    func appendLog(_ message: String, isError: Bool = false) {
        log.append(LogEntry(message: message, isError: isError))
    }

    private func show(_ title: String, _ error: any Error) {
        alert = AlertItem(title: title, message: error.localizedDescription)
    }
}
