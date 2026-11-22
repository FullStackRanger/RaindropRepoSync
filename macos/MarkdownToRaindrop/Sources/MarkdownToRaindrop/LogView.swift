import SwiftUI

struct LogView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScrollViewReader { proxy in
            List(model.log) { entry in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: entry.isError ? "exclamationmark.circle.fill" : "circle.fill")
                        .font(entry.isError ? .caption : .system(size: 5))
                        .foregroundStyle(entry.isError ? AnyShapeStyle(.red) : AnyShapeStyle(.tertiary))
                        .frame(width: 12)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.message)
                            .foregroundStyle(entry.isError ? .red : .primary)
                            .textSelection(.enabled)
                        Text(entry.date, format: .dateTime.hour().minute().second())
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
                .font(.callout)
                .id(entry.id)
            }
            .onChange(of: model.log.count) {
                if let last = model.log.last { proxy.scrollTo(last.id, anchor: .bottom) }
            }
        }
        .navigationTitle("Log")
        .overlay {
            if model.log.isEmpty {
                ContentUnavailableView("No Activity", systemImage: "list.bullet.rectangle.portrait")
            }
        }
    }
}
