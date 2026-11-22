#if DEBUG
import AppKit

/// Debug builds only: lets scripts capture the main window without Screen Recording permission.
///   snapshot   object: output PNG path
///   appearance object: "dark" | "light" | "system"
///   editor     object: "markdown" | "preview"
///   save       object: replacement tags, or ""
@MainActor
enum DebugSnapshot {
    private static let prefix = "local.toolbelt.WebClipper.debug."

    static func install(model: ClipperModel) {
        let center = DistributedNotificationCenter.default()
        center.addObserver(forName: .init(prefix + "snapshot"), object: nil, queue: .main) { note in
            guard let path = note.object as? String else { return }
            MainActor.assumeIsolated { capture(to: path) }
        }
        center.addObserver(forName: .init(prefix + "appearance"), object: nil, queue: .main) { note in
            let value = note.object as? String
            MainActor.assumeIsolated {
                NSApp.appearance = value == "dark" ? NSAppearance(named: .darkAqua)
                    : value == "light" ? NSAppearance(named: .aqua) : nil
            }
        }
        center.addObserver(forName: .init(prefix + "editor"), object: nil, queue: .main) { note in
            let value = note.object as? String
            MainActor.assumeIsolated { model.editorMode = value == "preview" ? .preview : .markdown }
        }
        center.addObserver(forName: .init(prefix + "save"), object: nil, queue: .main) { note in
            let tags = note.object as? String
            MainActor.assumeIsolated {
                if let tags, !tags.isEmpty { model.tags = tags }
                Task { await model.save() }
            }
        }
    }

    private static func capture(to path: String) {
        guard let window = NSApp.windows.filter(\.isVisible).max(by: { $0.frame.height < $1.frame.height }),
              let frameView = window.contentView?.superview,
              let rep = frameView.bitmapImageRepForCachingDisplay(in: frameView.bounds) else { return }
        frameView.cacheDisplay(in: frameView.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
    }
}
#endif
