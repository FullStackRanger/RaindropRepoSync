import SwiftUI

/// Liquid Glass on macOS 26+, translucent materials before that.
extension View {
    @ViewBuilder
    func glassPanel(cornerRadius: CGFloat = 18) -> some View {
        if #available(macOS 26.0, *) {
            glassEffect(.regular, in: .rect(cornerRadius: cornerRadius))
        } else {
            background(.regularMaterial, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous).strokeBorder(.separator.opacity(0.5)))
        }
    }

    @ViewBuilder
    func glassCapsule(tint: Color? = nil) -> some View {
        if #available(macOS 26.0, *) {
            glassEffect(.regular.tint(tint), in: .capsule)
        } else {
            background((tint ?? .clear).opacity(0.15), in: Capsule())
                .background(.thinMaterial, in: Capsule())
        }
    }

    @ViewBuilder
    func prominentGlassButton() -> some View {
        if #available(macOS 26.0, *) {
            buttonStyle(.glassProminent)
        } else {
            buttonStyle(.borderedProminent)
        }
    }

    @ViewBuilder
    func glassButton() -> some View {
        if #available(macOS 26.0, *) {
            buttonStyle(.glass)
        } else {
            buttonStyle(.bordered)
        }
    }
}

/// Groups sibling glass shapes so they blend and morph together on macOS 26+.
struct GlassGroup<Content: View>: View {
    var spacing: CGFloat = 12
    @ViewBuilder var content: Content

    var body: some View {
        if #available(macOS 26.0, *) {
            GlassEffectContainer(spacing: spacing) { content }
        } else {
            content
        }
    }
}
