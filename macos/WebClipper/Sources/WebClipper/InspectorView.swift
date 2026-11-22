import SwiftUI

struct InspectorView: View {
    @Environment(ClipperModel.self) private var model

    var body: some View {
        @Bindable var model = model
        Form {
            Section {
                LabeledContent {
                    Text(abbreviated(model.saveDir))
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .help(model.saveDir)
                } label: {
                    Label("Folder", systemImage: "folder")
                }
                HStack {
                    Button("Downloads") { model.setSaveFolder(ClipperModel.downloads) }
                    Button("Documents") { model.setSaveFolder(ClipperModel.documents) }
                    Spacer()
                    Button("Choose…") { model.chooseSaveFolder() }
                }
                .controlSize(.small)
            } header: {
                Text("Save To")
            }

            Section {
                Toggle("Also copy into my vault after saving", isOn: $model.copyToVault)
                    .onChange(of: model.copyToVault) { _, _ in model.remember() }

                LabeledContent {
                    HStack {
                        Text(model.vaultPath.isEmpty ? "Not set" : abbreviated(model.vaultPath))
                            .foregroundStyle(model.vaultPath.isEmpty ? .secondary : .primary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .help(model.vaultPath)
                        Button("Choose…") { Task { await model.chooseVault() } }
                            .controlSize(.small)
                    }
                } label: {
                    Label("Vault", systemImage: model.vaultLooksValid ? "books.vertical.fill" : "books.vertical")
                }

                VStack(alignment: .leading, spacing: 6) {
                    Label("Folder in vault", systemImage: "folder.badge.plus")
                    HStack(spacing: 4) {
                        TextField("Folder", text: $model.vaultFolder, prompt: Text("Vault root"))
                            .textFieldStyle(.roundedBorder)
                            .labelsHidden()
                            .onSubmit { model.remember() }
                        Menu {
                            Button("Vault root") { model.vaultFolder = ""; model.remember() }
                            if !model.vaultFolders.isEmpty { Divider() }
                            ForEach(model.vaultFolders, id: \.self) { folder in
                                Button(folder) { model.vaultFolder = folder; model.remember() }
                            }
                            Divider()
                            Button("Choose in Finder…") { Task { await model.chooseVaultFolder() } }
                            Button("Refresh") { Task { await model.refreshVault() } }
                        } label: {
                            Label("Vault folders", systemImage: "list.bullet")
                                .labelStyle(.iconOnly)
                        }
                        .menuIndicator(.hidden)
                        .fixedSize()
                        .help("Pick a folder from the vault")
                        .disabled(model.vaultPath.isEmpty)
                    }
                }

                Text(model.vaultHint)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    Button {
                        Task { await model.copyToVaultNow() }
                    } label: {
                        Label("Copy to Vault", systemImage: "tray.and.arrow.down")
                    }
                    .disabled(model.savedPath == nil)
                    Spacer()
                    Button {
                        model.openInObsidian()
                    } label: {
                        Label("Open", systemImage: "arrow.up.forward.app")
                    }
                    .disabled(model.vaultCopyPath == nil)
                    .help("Open the vault copy in Obsidian")
                }
                .controlSize(.small)
            } header: {
                Text("Obsidian")
            }

            Section {
                LabeledContent {
                    BridgeBadge()
                } label: {
                    Label("Status", systemImage: "puzzlepiece.extension")
                }
                HStack {
                    Button("Copy Bookmarklet") { model.copyBookmarklet() }
                    Spacer()
                    if case .listening = model.bridge {} else {
                        Button("Retry") { model.restartListener() }
                    }
                }
                .controlSize(.small)
            } header: {
                Text("Browser Button")
            }

            if let saved = model.savedPath {
                Section {
                    fileRow("Note", systemImage: "doc.text", url: saved)
                    if let copy = model.vaultCopyPath {
                        fileRow("Vault copy", systemImage: "doc.on.doc", url: copy)
                    }
                    Button("Show in Finder") { model.reveal() }
                        .controlSize(.small)
                } header: {
                    Text("Saved")
                }
            }

            Section {
                if model.log.isEmpty {
                    Text("Nothing yet.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(model.log.suffix(12).reversed()) { entry in
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Image(systemName: entry.isError ? "exclamationmark.circle.fill" : "circle.fill")
                                .font(entry.isError ? .caption : .system(size: 5))
                                .foregroundStyle(entry.isError ? Color.red : Color.secondary)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(entry.message)
                                    .foregroundStyle(entry.isError ? .red : .primary)
                                    .lineLimit(3)
                                    .textSelection(.enabled)
                                Text(entry.date, style: .time)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .font(.caption)
                    }
                }
            } header: {
                Text("Activity")
            }
        }
        .formStyle(.grouped)
    }

    private func fileRow(_ title: String, systemImage: String, url: URL) -> some View {
        LabeledContent {
            Text(url.lastPathComponent)
                .lineLimit(1)
                .truncationMode(.middle)
                .help(url.path)
        } label: {
            Label(title, systemImage: systemImage)
        }
    }

    private func abbreviated(_ path: String) -> String {
        (path as NSString).abbreviatingWithTildeInPath
    }
}

struct SettingsView: View {
    @Environment(ClipperModel.self) private var model
    @AppStorage(Engine.pythonDefaultsKey) private var pythonPath = ""
    @AppStorage(ClipperModel.portDefaultsKey) private var port = ClipperModel.defaultPort

    var body: some View {
        Form {
            Section {
                TextField("Python 3 interpreter", text: $pythonPath, prompt: Text(Engine.locatePython()?.path ?? "/opt/homebrew/bin/python3"))
                Text("Leave empty to use the first of: \(Engine.pythonCandidates.joined(separator: ", ")).")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } header: {
                Text("Engine")
            }
            Section {
                TextField("Port", value: $port, format: .number.grouping(.never))
                Text("Must match CLIPPER and host_permissions in browser/web-clipper.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } header: {
                Text("Browser Button")
            }
            HStack {
                Spacer()
                Button("Apply") { Task { await model.reloadEngine() } }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .formStyle(.grouped)
        .frame(width: 460)
        .fixedSize(horizontal: false, vertical: true)
    }
}
