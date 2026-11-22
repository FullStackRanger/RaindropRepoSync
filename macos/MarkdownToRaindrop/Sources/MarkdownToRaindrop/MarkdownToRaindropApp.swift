import AppKit
import SwiftUI

/// Launch options. Markdown paths on the command line are preloaded, as with `md_to_raindrop.py`.
///   --demo                 use an offline stub API (no token needed)
///   --demo-save            with --demo: run a save right after launch (for screenshots)
///   --appearance light|dark
///   --show-log             open the log inspector at launch
struct LaunchOptions {
    var files: [URL] = []
    var demo = false
    var demoSave = false
    var showLog = false
    var appearance: NSAppearance.Name?

    init(arguments: [String] = Array(CommandLine.arguments.dropFirst())) {
        var iterator = arguments.makeIterator()
        while let arg = iterator.next() {
            switch arg {
            case "--demo": demo = true
            case "--demo-save": demoSave = true
            case "--show-log": showLog = true
            case "--appearance":
                appearance = iterator.next() == "dark" ? .darkAqua : .aqua
            case let path where !path.hasPrefix("-"):
                files.append(URL(fileURLWithPath: path))
            default:
                break // ignore AppKit/Xcode flags such as -NSDocumentRevisionsDebugMode
            }
        }
        demo = demo || ProcessInfo.processInfo.environment["MD2RD_DEMO"] == "1"
    }
}

@main
struct MarkdownToRaindropApp: App {
    @NSApplicationDelegateAdaptor private var appDelegate: AppDelegate
    @State private var model: AppModel
    private let options: LaunchOptions

    init() {
        let options = LaunchOptions()
        self.options = options
        _model = State(initialValue: AppModel(demoMode: options.demo))
    }

    var body: some Scene {
        Window("Markdown → Raindrop.io", id: "main") {
            ContentView()
                .environment(model)
                .frame(minWidth: 860, minHeight: 560)
                .task { start() }
        }
        .defaultSize(width: 1280, height: 780)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Add Markdown Files…") { NotificationCenter.default.post(name: .showFileImporter, object: nil) }
                    .keyboardShortcut("o")
            }
            CommandMenu("Links") {
                Button("Select All Links") { model.setAll(true) }
                    .keyboardShortcut("a", modifiers: [.command, .shift])
                Button("Deselect All Links") { model.setAll(false) }
                    .keyboardShortcut("d", modifiers: [.command, .shift])
                Divider()
                Button("Save Selected Links") { model.save() }
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(!model.canSave)
                Button("Cancel Saving") { model.cancelSave() }
                    .keyboardShortcut(".", modifiers: .command)
                    .disabled(!model.isSaving)
                Button("Reload Collections") { model.loadCollections() }
                    .keyboardShortcut("r")
            }
        }

        Settings {
            SettingsView()
                .environment(model)
        }
    }

    @MainActor private func start() {
        guard model.log.isEmpty else { return }
        if let appearance = options.appearance { NSApp.appearance = NSAppearance(named: appearance) }
        model.isLogVisible = options.showLog
        if model.demoMode { model.appendLog("Demo mode: using an offline stub of the Raindrop API.") }
        model.addFiles(options.files)
        if model.hasToken {
            model.loadCollections()
        } else {
            model.appendLog("No token yet. Add one in Settings (⌘,) or set RAINDROP_TOKEN.")
        }
        if model.demoMode && options.demoSave {
            Task {
                while model.isLoadingCollections { try? await Task.sleep(for: .milliseconds(100)) }
                model.selectedCollectionID = 11
                model.tags = "markdown, reading"
                model.save()
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Needed when launched as a bare SwiftPM executable rather than an .app bundle.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

extension Notification.Name {
    static let showFileImporter = Notification.Name("MarkdownToRaindrop.showFileImporter")
}
