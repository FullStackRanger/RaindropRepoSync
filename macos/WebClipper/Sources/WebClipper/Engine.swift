import Foundation

struct EngineError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

struct Article: Codable, Equatable {
    var title = ""
    var markdown = ""
    var url = ""
    var author = ""
    var published = ""
    var siteName = ""
    var description = ""
    var tags: [String] = []
}

struct ClipResult: Decodable {
    let article: Article
    let tags: String
    let info: String
}

struct ErrorReply: Decodable { let error: String? }
struct PathResult: Decodable { let path: String }
struct FolderResult: Decodable { let folder: String }
struct BookmarkletResult: Decodable { let bookmarklet: String }

struct VaultInfo: Decodable {
    let exists: Bool
    let isVault: Bool
    let folders: [String]
}

struct EngineSettings: Codable {
    var saveDir: String
    var copyToVault: Bool
    var vaultPath: String
    var vaultFolder: String
}

struct SaveRequest: Encodable {
    let article: Article
    let title: String
    let tags: String
    let body: String
    let folder: String
}

struct VaultCopyRequest: Encodable {
    let path: String
    let vault: String
    let folder: String
    let tags: String
}

/// Runs `clip_cli.py` (the Python clipper engine) and decodes its JSON replies.
struct Engine {
    static let pythonDefaultsKey = "pythonPath"
    static let pythonCandidates = [
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
        "/usr/bin/python3",
    ]

    let python: URL
    let directory: URL

    var script: URL { directory.appendingPathComponent("clip_cli.py") }

    /// Engine scripts: `$WEB_CLIPPER_ENGINE`, then the app bundle's `Resources/engine`, then this repo (for `swift run`).
    static func locateDirectory() -> URL? {
        var candidates: [URL] = []
        if let override = ProcessInfo.processInfo.environment["WEB_CLIPPER_ENGINE"] {
            candidates.append(URL(fileURLWithPath: (override as NSString).expandingTildeInPath))
        }
        if let resources = Bundle.main.resourceURL {
            candidates.append(resources.appendingPathComponent("engine"))
        }
        var repo = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { repo.deleteLastPathComponent() }
        candidates.append(repo)
        return candidates.first { FileManager.default.fileExists(atPath: $0.appendingPathComponent("clip_cli.py").path) }
    }

    static func locatePython() -> URL? {
        var candidates: [String] = []
        if let env = ProcessInfo.processInfo.environment["WEB_CLIPPER_PYTHON"] { candidates.append(env) }
        if let saved = UserDefaults.standard.string(forKey: pythonDefaultsKey), !saved.isEmpty { candidates.append(saved) }
        candidates += pythonCandidates
        return candidates
            .map { (($0 as NSString).expandingTildeInPath) }
            .first { FileManager.default.isExecutableFile(atPath: $0) }
            .map { URL(fileURLWithPath: $0) }
    }

    static func locate() throws -> Engine {
        guard let directory = locateDirectory() else {
            throw EngineError(message: "Engine scripts (clip_cli.py) not found. Rebuild the app with build-app.sh or set WEB_CLIPPER_ENGINE.")
        }
        guard let python = locatePython() else {
            throw EngineError(message: "No python3 found. Install Python 3 or choose an interpreter in Settings.")
        }
        return Engine(python: python, directory: directory)
    }

    func makeProcess(_ arguments: [String]) -> Process {
        let process = Process()
        process.executableURL = python
        process.arguments = [script.path] + arguments
        process.currentDirectoryURL = directory
        var env = ProcessInfo.processInfo.environment
        // The bundle is code-signed: never write __pycache__ into it.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        process.environment = env
        return process
    }

    func run<T: Decodable>(_ arguments: [String], as type: T.Type = T.self) async throws -> T {
        try await run(arguments, input: Optional<Data>.none)
    }

    func run<T: Decodable, I: Encodable>(_ arguments: [String], body: I, as type: T.Type = T.self) async throws -> T {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return try await run(arguments, input: try encoder.encode(body))
    }

    private func run<T: Decodable>(_ arguments: [String], input: Data?) async throws -> T {
        let data = try await Task.detached(priority: .userInitiated) { try execute(arguments, input: input) }.value
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        if let reply = try? decoder.decode(ErrorReply.self, from: data), let message = reply.error {
            throw EngineError(message: message)
        }
        return try decoder.decode(T.self, from: data)
    }

    private func execute(_ arguments: [String], input: Data?) throws -> Data {
        let process = makeProcess(arguments)
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = stderr
        try process.run()

        var errorData = Data()
        let errorRead = DispatchGroup()
        errorRead.enter()
        DispatchQueue.global().async {
            errorData = stderr.fileHandleForReading.readDataToEndOfFile()
            errorRead.leave()
        }
        // clip_cli reads all of stdin before writing, so writing first cannot deadlock.
        if let input { stdin.fileHandleForWriting.write(input) }
        try? stdin.fileHandleForWriting.close()
        let output = stdout.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        errorRead.wait()

        if output.isEmpty {
            let detail = String(decoding: errorData, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            let lastLine = detail.split(separator: "\n").last.map(String.init)
            throw EngineError(message: lastLine ?? "The clipper engine exited with status \(process.terminationStatus).")
        }
        return output
    }
}
