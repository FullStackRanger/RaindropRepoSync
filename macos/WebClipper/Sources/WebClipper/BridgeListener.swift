import Foundation

/// Keeps `clip_cli.py serve` running: the localhost listener the browser button and bookmarklet talk to.
/// The child exits when its stdin closes, so it never outlives the app.
final class BridgeListener {
    struct Message: Decodable {
        let event: String
        var url: String?
        var port: Int?
        var message: String?
    }

    var onMessage: (Message) -> Void = { _ in }

    private var process: Process?
    private var stdin: Pipe?
    private var buffer = Data()

    var isRunning: Bool { process?.isRunning ?? false }

    func start(engine: Engine, port: Int) throws {
        stop()
        let process = engine.makeProcess(["serve", "--port", String(port)])
        let stdin = Pipe(), stdout = Pipe()
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = FileHandle.nullDevice
        buffer = Data()
        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty else {
                handle.readabilityHandler = nil
                return
            }
            self?.consume(chunk)
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.onMessage(Message(event: "stopped")) }
        }
        try process.run()
        self.process = process
        self.stdin = stdin
    }

    func stop() {
        guard let process else { return }
        process.terminationHandler = nil
        try? stdin?.fileHandleForWriting.close()
        if process.isRunning { process.terminate() }
        self.process = nil
        stdin = nil
    }

    private func consume(_ chunk: Data) {
        buffer.append(chunk)
        while let newline = buffer.firstIndex(of: UInt8(ascii: "\n")) {
            let line = buffer[buffer.startIndex..<newline]
            buffer.removeSubrange(buffer.startIndex...newline)
            guard let message = try? JSONDecoder().decode(Message.self, from: Data(line)) else { continue }
            DispatchQueue.main.async { [weak self] in self?.onMessage(message) }
        }
    }

    deinit { stop() }
}
