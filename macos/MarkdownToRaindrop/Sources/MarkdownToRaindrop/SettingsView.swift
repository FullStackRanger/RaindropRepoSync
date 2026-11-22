import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var draft = ""
    @State private var reveal = false

    var body: some View {
        Form {
            Section {
                HStack {
                    Group {
                        if reveal {
                            TextField("API token", text: $draft)
                        } else {
                            SecureField("API token", text: $draft)
                        }
                    }
                    .textFieldStyle(.roundedBorder)
                    .font(.body.monospaced())
                    Button { reveal.toggle() } label: {
                        Image(systemName: reveal ? "eye.slash" : "eye")
                    }
                    .buttonStyle(.borderless)
                    .help(reveal ? "Hide token" : "Show token")
                }
                LabeledContent("Current source") {
                    Label(model.tokenSource.rawValue, systemImage: sourceIcon)
                }
                HStack {
                    Link("Get a token…", destination: URL(string: "https://app.raindrop.io/settings/integrations")!)
                    Spacer()
                    Button("Remove", role: .destructive) {
                        model.saveToken("")
                        draft = ""
                    }
                    .disabled(model.tokenSource != .keychain || model.demoMode)
                    Button("Save to Keychain") { model.saveToken(draft) }
                        .keyboardShortcut(.defaultAction)
                        .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty || model.demoMode)
                }
            } header: {
                Text("Raindrop.io")
            } footer: {
                Text(model.demoMode
                     ? "Demo mode uses an offline stub; tokens are not read or stored."
                     : "Create a test token under Integrations → For Developers. It is stored in your login Keychain; if none is saved, RAINDROP_TOKEN is used.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 480)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear { if model.tokenSource == .keychain { draft = model.token } }
    }

    private var sourceIcon: String {
        switch model.tokenSource {
        case .keychain: "key.fill"
        case .environment: "terminal"
        case .none: "xmark.circle"
        }
    }
}
