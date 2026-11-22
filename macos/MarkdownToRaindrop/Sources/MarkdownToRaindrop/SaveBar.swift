import SwiftUI

struct SaveBar: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        GlassGroup(spacing: 10) {
            HStack(spacing: 12) {
                HStack(spacing: 6) {
                    Image(systemName: "tag").foregroundStyle(.secondary)
                    TextField("Tags, comma-separated", text: $model.tags)
                        .textFieldStyle(.plain)
                }
                .frame(minWidth: 110, idealWidth: 220, maxWidth: 260)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .glassCapsule()
                .layoutPriority(1)

                Toggle("Skip existing", isOn: $model.skipExisting)
                    .toggleStyle(.switch)
                    .controlSize(.small)
                    .fixedSize()
                    .help("Ask Raindrop which links already exist and skip them")

                VStack(alignment: .trailing, spacing: 4) {
                    Text(model.statusMessage)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .contentTransition(.opacity)
                    if model.isSaving {
                        ProgressView(value: model.progressFraction)
                            .progressViewStyle(.linear)
                            .frame(maxWidth: 200)
                    } else if let collection = model.selectedCollection {
                        Label(collection.path, systemImage: "folder")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                            .truncationMode(.head)
                    }
                }
                .frame(minWidth: 0, maxWidth: .infinity, alignment: .trailing)

                Group {
                    if model.isSaving {
                        Button(role: .cancel) { model.cancelSave() } label: {
                            Label("Cancel", systemImage: "stop.fill")
                        }
                        .glassButton()
                        .disabled(model.isCancelling)
                    } else {
                        Button { model.save() } label: {
                            Label(saveTitle, systemImage: "tray.and.arrow.down.fill")
                        }
                        .prominentGlassButton()
                        .disabled(!model.canSave)
                    }
                }
                .controlSize(.large)
                .fixedSize()
            }
            .padding(.leading, 12)
            .padding(.trailing, 8)
            .padding(.vertical, 8)
            .glassPanel(cornerRadius: 26)
        }
        .animation(.snappy, value: model.isSaving)
    }

    private var saveTitle: String {
        let count = model.selectedCount
        return count == 0 ? "Save" : "Save \(count) Link\(count == 1 ? "" : "s")"
    }
}
