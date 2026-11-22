import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    var model: ClipperModel?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Running the bare executable (`swift run`) starts as a background process otherwise.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        MainActor.assumeIsolated {
            model?.remember()
            model?.shutdown()
        }
    }
}

@main
struct WebClipperApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    private let model = ClipperModel()

    private var initialURL: String? {
        CommandLine.arguments.dropFirst().first { ClipperModel.isWebURL($0) }
    }

    var body: some Scene {
        Window("Web Clipper", id: "main") {
            ContentView()
                .environment(model)
                .task {
                    appDelegate.model = model
                    #if DEBUG
                    DebugSnapshot.install(model: model)
                    #endif
                    await model.start(initialURL: initialURL)
                }
                .onOpenURL { model.handle(openURL: $0) }
        }
        .defaultSize(width: 1080, height: 780)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(after: .newItem) {
                Button("Open Location…") { model.focusURLRequest += 1 }
                    .keyboardShortcut("l")
                Button("Paste and Clip") { Task { await model.pasteAndClip() } }
                    .keyboardShortcut("v", modifiers: [.command, .shift])
                Divider()
                Button("Save Note") { Task { await model.save() } }
                    .keyboardShortcut("s")
                    .disabled(!model.canSave)
                Button("Copy to Vault") { Task { await model.copyToVaultNow() } }
                    .keyboardShortcut("s", modifiers: [.command, .option])
                    .disabled(model.savedPath == nil)
                Button("Show in Finder") { model.reveal() }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                    .disabled(model.savedPath == nil)
                Button("Open in Obsidian") { model.openInObsidian() }
                    .keyboardShortcut("o", modifiers: [.command, .shift])
                    .disabled(model.vaultCopyPath == nil)
            }
        }

        Settings {
            SettingsView()
                .environment(model)
        }
    }
}
