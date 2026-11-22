import AppKit
import Observation
import SwiftUI

struct LogEntry: Identifiable {
    let id = UUID()
    let date = Date()
    let message: String
    let isError: Bool
}

enum BridgeState: Equatable {
    case off
    case listening(Int)
    case failed(String)

    var label: String {
        switch self {
        case .off: "Browser button off"
        case .listening(let port): "Listening on 127.0.0.1:\(port)"
        case .failed(let reason): "Browser button off — \(reason)"
        }
    }
}

enum EditorMode: String, CaseIterable, Identifiable {
    case markdown = "Markdown"
    case preview = "Preview"
    var id: String { rawValue }
}

struct AlertItem: Identifiable {
    let id = UUID()
    let title: String
    let message: String
}

@MainActor
@Observable
final class ClipperModel {
    static let portDefaultsKey = "bridgePort"
    static let defaultPort = Int(ProcessInfo.processInfo.environment["WEB_CLIPPER_PORT"] ?? "") ?? 47811

    var urlText = ""
    var article: Article?
    var title = ""
    var tags = "clippings"
    var body = ""
    var info = ""
    var isBusy = false
    var savedPath: URL?
    var vaultCopyPath: URL?

    var saveDir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads").path
    var copyToVault = false
    var vaultPath = ""
    var vaultFolder = ""
    var vaultFolders: [String] = []
    var vaultHint = ""
    var vaultLooksValid = false

    var bridge: BridgeState = .off
    var status = "Paste a URL and press Clip."
    var log: [LogEntry] = []
    var alert: AlertItem?
    var engineProblem: String?
    var focusURLRequest = 0
    var showInspector = true
    var editorMode: EditorMode = .markdown

    var hasUnsavedClip: Bool { article != nil && savedPath == nil }
    var canSave: Bool { article != nil && !isBusy }
    var port: Int {
        let saved = UserDefaults.standard.integer(forKey: Self.portDefaultsKey)
        return saved > 0 ? saved : Self.defaultPort
    }

    private var engine: Engine?
    private let listener = BridgeListener()
    private var pendingURL: String?
    private var started = false

    static let downloads = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads").path
    static let documents = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents").path

    // MARK: - Lifecycle

    func start(initialURL: String?) async {
        guard !started else { return }
        started = true
        do {
            engine = try Engine.locate()
        } catch {
            engineProblem = error.localizedDescription
            status = "The clipper engine is not available."
            addLog(error.localizedDescription, error: true)
            return
        }
        await loadSettings()
        startListener()
        if let initialURL {
            urlText = initialURL
            await clip()
        } else {
            prefillFromClipboard()
        }
    }

    func reloadEngine() async {
        listener.stop()
        engine = nil
        engineProblem = nil
        started = false
        await start(initialURL: nil)
    }

    func shutdown() {
        listener.stop()
    }

    private func loadSettings() async {
        guard let engine else { return }
        do {
            let settings: EngineSettings = try await engine.run(["settings"])
            saveDir = settings.saveDir
            copyToVault = settings.copyToVault
            vaultPath = settings.vaultPath
            vaultFolder = settings.vaultFolder
        } catch {
            addLog("Could not read settings: \(error.localizedDescription)", error: true)
        }
        await refreshVault()
    }

    func remember() {
        guard let engine else { return }
        let settings = EngineSettings(saveDir: saveDir.trimmingCharacters(in: .whitespaces).isEmpty ? Self.downloads : saveDir,
                                      copyToVault: copyToVault, vaultPath: vaultPath.trimmingCharacters(in: .whitespaces),
                                      vaultFolder: vaultFolder.trimmingCharacters(in: .whitespaces))
        Task {
            do {
                let _: EngineSettings = try await engine.run(["settings", "--set"], body: settings)
            } catch {
                addLog("Could not save settings: \(error.localizedDescription)", error: true)
            }
        }
    }

    // MARK: - Browser button

    func startListener() {
        guard let engine else { return }
        listener.onMessage = { [weak self] message in
            guard let self else { return }
            switch message.event {
            case "listening":
                bridge = .listening(message.port ?? port)
            case "url":
                if let url = message.url { receive(url: url, source: "browser") }
            case "focus":
                bringToFront()
            case "error":
                bridge = .failed(message.message ?? "unavailable")
                addLog("Browser button: \(message.message ?? "listener failed")", error: true)
            case "stopped":
                if case .listening = bridge { bridge = .off }
            default:
                break
            }
        }
        do {
            try listener.start(engine: engine, port: port)
        } catch {
            bridge = .failed(error.localizedDescription)
            addLog("Could not start the browser-button listener: \(error.localizedDescription)", error: true)
        }
    }

    func restartListener() {
        listener.stop()
        bridge = .off
        startListener()
    }

    /// `webclipper://clip?url=<encoded>` — lets a browser or script launch the app with a page.
    func handle(openURL url: URL) {
        guard url.scheme == "webclipper" else { return }
        let target = URLComponents(url: url, resolvingAgainstBaseURL: false)?
            .queryItems?.first { $0.name == "url" }?.value
        if let target, Self.isWebURL(target) {
            receive(url: target, source: "link")
        } else {
            bringToFront()
        }
    }

    func receive(url: String, source: String) {
        bringToFront()
        addLog("Received from \(source): \(url)")
        if !started || isBusy || engine == nil {
            pendingURL = url
            return
        }
        urlText = url
        Task { await clip() }
    }

    func bringToFront() {
        NSApp.activate(ignoringOtherApps: true)
        NSApp.windows.first { $0.canBecomeMain }?.makeKeyAndOrderFront(nil)
    }

    func copyBookmarklet() {
        guard let engine else { return }
        Task {
            do {
                let result: BookmarkletResult = try await engine.run(["bookmarklet", "--port", String(port)])
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(result.bookmarklet, forType: .string)
                status = "Bookmarklet copied — paste it as the address of a new bookmark."
            } catch {
                report(error, context: "Could not build the bookmarklet")
            }
        }
    }

    // MARK: - Clip

    static func isWebURL(_ text: String) -> Bool {
        guard let comps = URLComponents(string: text), let scheme = comps.scheme?.lowercased() else { return false }
        return ["http", "https"].contains(scheme) && !(comps.host ?? "").isEmpty
    }

    private func clipboardText() -> String {
        (NSPasteboard.general.string(forType: .string) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func prefillFromClipboard() {
        let text = clipboardText()
        if Self.isWebURL(text), !text.contains("\n") {
            urlText = text
            status = "URL from clipboard — press Clip (or Return)."
        }
    }

    func pasteAndClip() async {
        let text = clipboardText()
        guard let first = text.split(whereSeparator: \.isWhitespace).first else {
            status = "Clipboard is empty."
            return
        }
        urlText = String(first)
        await clip()
    }

    func clip() async {
        guard let engine, !isBusy else { return }
        let url = urlText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !url.isEmpty else {
            status = "Enter a URL first."
            focusURLRequest += 1
            return
        }
        isBusy = true
        status = "Fetching \(url)…"
        do {
            let result: ClipResult = try await engine.run(["clip", url])
            isBusy = false
            if let article, savedPath == nil { addLog("Discarded unsaved clip: \(article.title)") }
            article = result.article
            savedPath = nil
            vaultCopyPath = nil
            urlText = result.article.url
            title = result.article.title
            tags = result.tags
            body = result.article.markdown
            info = result.info
            status = "Review the note, then Save (⌘S)."
            addLog("Clipped: \(result.article.title)")
            nextPending()
        } catch {
            isBusy = false
            status = "Could not clip that page."
            addLog("Failed: \(error.localizedDescription)", error: true)
            if !nextPending() {
                alert = AlertItem(title: "Could not clip that page", message: error.localizedDescription)
            }
        }
    }

    @discardableResult
    private func nextPending() -> Bool {
        guard let url = pendingURL else { return false }
        pendingURL = nil
        urlText = url
        Task { await clip() }
        return true
    }

    // MARK: - Save

    func save() async {
        guard let engine, let article, !isBusy else { return }
        let cleanTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanTitle.isEmpty else {
            alert = AlertItem(title: "Missing title", message: "Give the note a title.")
            return
        }
        let folder = saveDir.trimmingCharacters(in: .whitespaces).isEmpty ? Self.downloads : saveDir
        do {
            let request = SaveRequest(article: article, title: cleanTitle, tags: tags, body: body, folder: folder)
            let result: PathResult = try await engine.run(["save"], body: request)
            savedPath = URL(fileURLWithPath: result.path)
            vaultCopyPath = nil
            remember()
            addLog("Saved: \(result.path)")
            status = "Saved to \(result.path)"
            if copyToVault { await copyToVaultNow() }
        } catch {
            report(error, context: "Could not save the note")
        }
    }

    func chooseSaveFolder() {
        if let url = pickFolder(title: "Save notes to", start: saveDir, canCreate: true) {
            saveDir = url.path
            remember()
        }
    }

    func setSaveFolder(_ path: String) {
        saveDir = path
        remember()
    }

    func reveal() {
        guard let path = vaultCopyPath ?? savedPath else { return }
        NSWorkspace.shared.activateFileViewerSelecting([path])
    }

    // MARK: - Obsidian

    func refreshVault() async {
        let vault = vaultPath.trimmingCharacters(in: .whitespaces)
        guard !vault.isEmpty else {
            vaultFolders = []
            vaultLooksValid = false
            vaultHint = "Choose your vault folder (the one that contains .obsidian)."
            return
        }
        guard let engine else { return }
        do {
            let info: VaultInfo = try await engine.run(["vault-info", vault])
            vaultFolders = info.folders
            vaultLooksValid = info.isVault
            if !info.exists {
                vaultHint = "Folder not found."
            } else if !info.isVault {
                vaultHint = "No .obsidian folder here — is this your vault?"
            } else {
                vaultHint = "Leave Folder empty for the vault root; type a new name to create it."
            }
        } catch {
            vaultHint = error.localizedDescription
        }
    }

    func chooseVault() async {
        guard let url = pickFolder(title: "Choose your Obsidian vault", start: vaultPath) else { return }
        vaultPath = url.path
        vaultFolder = ""
        remember()
        await refreshVault()
    }

    func chooseVaultFolder() async {
        let vault = vaultPath.trimmingCharacters(in: .whitespaces)
        guard let engine, !vault.isEmpty else {
            await chooseVault()
            return
        }
        let start = (vault as NSString).appendingPathComponent(vaultFolder)
        guard let url = pickFolder(title: "Choose a folder inside your vault", start: start, canCreate: true) else { return }
        do {
            let result: FolderResult = try await engine.run(["relative-folder", vault, url.path])
            vaultFolder = result.folder
            remember()
            await refreshVault()
        } catch {
            alert = AlertItem(title: "Not in the vault", message: error.localizedDescription)
        }
    }

    func copyToVaultNow() async {
        guard let engine, let savedPath else { return }
        do {
            let request = VaultCopyRequest(path: savedPath.path, vault: vaultPath.trimmingCharacters(in: .whitespaces),
                                           folder: vaultFolder, tags: tags)
            let result: PathResult = try await engine.run(["copy-to-vault"], body: request)
            vaultCopyPath = URL(fileURLWithPath: result.path)
            remember()
            await refreshVault()
            addLog("Copied to vault: \(result.path)")
            status = "Saved to \(savedPath.deletingLastPathComponent().path) and copied to the vault."
        } catch {
            report(error, context: "Could not copy into the vault")
        }
    }

    func openInObsidian() {
        guard let path = vaultCopyPath else { return }
        var allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
        allowed.insert(charactersIn: "-._~")
        guard let encoded = path.path.addingPercentEncoding(withAllowedCharacters: allowed),
              let uri = URL(string: "obsidian://open?path=" + encoded) else { return }
        NSWorkspace.shared.open(uri)
    }

    // MARK: - Helpers

    private func pickFolder(title: String, start: String, canCreate: Bool = false) -> URL? {
        let panel = NSOpenPanel()
        panel.message = title
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = canCreate
        panel.allowsMultipleSelection = false
        panel.prompt = "Choose"
        let expanded = (start as NSString).expandingTildeInPath
        panel.directoryURL = URL(fileURLWithPath: expanded.isEmpty ? NSHomeDirectory() : expanded)
        return panel.runModal() == .OK ? panel.url : nil
    }

    private func report(_ error: Error, context: String) {
        addLog("\(context): \(error.localizedDescription)", error: true)
        status = context + "."
        alert = AlertItem(title: context, message: error.localizedDescription)
    }

    func addLog(_ message: String, error: Bool = false) {
        log.append(LogEntry(message: message, isError: error))
        if log.count > 200 { log.removeFirst(log.count - 200) }
    }

    static func parsedTags(_ text: String) -> [String] {
        var seen = Set<String>()
        return text.split(whereSeparator: { $0 == "," || $0.isWhitespace })
            .map { $0.trimmingCharacters(in: CharacterSet(charactersIn: "#")) }
            .filter { !$0.isEmpty && seen.insert($0.lowercased()).inserted }
    }

    func removeTag(_ tag: String) {
        tags = Self.parsedTags(tags).filter { $0.caseInsensitiveCompare(tag) != .orderedSame }.joined(separator: " ")
    }
}
