import Foundation

/// Port of `raindrop_api.py`: a minimal Raindrop.io REST client for listing collections and saving bookmarks.
public let raindropAPIBase = URL(string: "https://api.raindrop.io/rest/v1")!
public let unsortedCollectionID = -1
let existsBatchSize = 100

public struct RaindropError: Error, LocalizedError, Equatable, Sendable {
    public var message: String
    public var status: Int?

    public init(_ message: String, status: Int? = nil) {
        self.message = message
        self.status = status
    }

    public var errorDescription: String? { message }
}

public struct SaveResult: Hashable, Sendable {
    public var url: String
    public var ok: Bool
    public var error: String = ""
    public var skipped: Bool = false
    public var raindropID: Int?
}

public protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionTransport: HTTPTransport {
    public init() {}

    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw RaindropError("Network error: unexpected response")
        }
        return (data, http)
    }
}

public struct RaindropClient: Sendable {
    public typealias Sleep = @Sendable (Double) async throws -> Void

    public let token: String
    public let baseURL: URL
    public var timeout: TimeInterval = 30
    public var maxRetries = 3
    private let transport: any HTTPTransport
    private let sleep: Sleep
    private let now: @Sendable () -> Date

    public init(
        token: String,
        baseURL: URL = raindropAPIBase,
        transport: any HTTPTransport = URLSessionTransport(),
        maxRetries: Int = 3,
        sleep: @escaping Sleep = { try await Task.sleep(for: .seconds($0)) },
        now: @escaping @Sendable () -> Date = Date.init
    ) throws {
        guard !token.isEmpty else { throw RaindropError("Missing Raindrop API token") }
        self.token = token
        self.baseURL = baseURL
        self.transport = transport
        self.maxRetries = maxRetries
        self.sleep = sleep
        self.now = now
    }

    func request(_ method: String, _ path: String, payload: [String: Any]? = nil) async throws -> [String: Any] {
        var request = URLRequest(url: URL(string: baseURL.absoluteString + path)!, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let payload {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        for attempt in 0...maxRetries {
            let data: Data
            let response: HTTPURLResponse
            do {
                (data, response) = try await transport.send(request)
            } catch let error as RaindropError {
                throw error
            } catch let error as URLError {
                throw RaindropError("Network error: \(error.localizedDescription)")
            }

            if response.statusCode == 429 && attempt < maxRetries {
                try await sleep(retryDelay(response, attempt: attempt))
                continue
            }
            if !(200..<300).contains(response.statusCode) {
                throw RaindropError(httpErrorMessage(response.statusCode, body: data), status: response.statusCode)
            }

            let result: [String: Any]
            if data.isEmpty {
                result = [:]
            } else {
                guard let object = try? JSONSerialization.jsonObject(with: data) else {
                    throw RaindropError("Invalid JSON in Raindrop response")
                }
                result = object as? [String: Any] ?? [:]
            }
            if result["result"] as? Bool == false {
                throw RaindropError(nonEmptyString(result["errorMessage"]) ?? nonEmptyString(result["error"]) ?? "Raindrop API error")
            }
            return result
        }
        throw RaindropError("Rate limited by Raindrop API", status: 429)
    }

    /// All collections (root + nested), sorted by their "Parent / Child" path, plus Unsorted first.
    public func getCollections() async throws -> [RaindropCollection] {
        let roots = try await request("GET", "/collections")["items"] as? [[String: Any]] ?? []
        let children = try await request("GET", "/collections/childrens")["items"] as? [[String: Any]] ?? []
        return buildCollectionList(roots: roots, children: children)
    }

    /// Map each already-bookmarked URL (as passed in) to its raindrop id.
    public func findExisting(_ urls: [String]) async throws -> [String: Int] {
        var existing: [String: Int] = [:]
        for start in stride(from: 0, to: urls.count, by: existsBatchSize) {
            let batch = Array(urls[start..<min(start + existsBatchSize, urls.count)])
            let data = try await request("POST", "/import/url/exists", payload: ["urls": batch])
            for duplicate in data["duplicates"] as? [[String: Any]] ?? [] {
                if let link = duplicate["link"] as? String, !link.isEmpty {
                    existing[link] = duplicate["_id"] as? Int
                }
            }
        }
        let requested = Set(urls)
        return existing.filter { requested.contains($0.key) }
    }

    /// Creates a bookmark and returns its raindrop id (if the API reported one).
    @discardableResult
    public func createBookmark(url: String, collectionID: Int, title: String = "", tags: [String] = []) async throws -> Int? {
        var payload: [String: Any] = [
            "link": url,
            "collection": ["$id": collectionID],
            "pleaseParse": [String: Any](),
        ]
        if !title.isEmpty { payload["title"] = title }
        let tags = tags.filter { !$0.isEmpty }
        if !tags.isEmpty { payload["tags"] = tags }
        let item = try await request("POST", "/raindrop", payload: payload)["item"] as? [String: Any]
        return item?["_id"] as? Int
    }

    /// Save `links` one by one, reporting each result.
    ///
    /// A failure for one link never aborts the rest; it is recorded in its `SaveResult`.
    /// `shouldStop` is checked before each link, so a stop finishes the link in flight first.
    public func saveLinks(
        _ links: [Link],
        collectionID: Int,
        tags: [String] = [],
        skipExisting: Bool = true,
        shouldStop: @Sendable () -> Bool = { false },
        progress: (@Sendable (Int, Int, SaveResult) async -> Void)? = nil
    ) async throws -> [SaveResult] {
        var existing: [String: Int] = [:]
        if skipExisting && !links.isEmpty {
            existing = try await findExisting(links.map(\.url))
        }

        var results: [SaveResult] = []
        for (index, link) in links.enumerated() {
            if shouldStop() { break }
            let result: SaveResult
            if let id = existing[link.url] {
                result = SaveResult(url: link.url, ok: true, skipped: true, raindropID: id)
            } else {
                do {
                    let id = try await createBookmark(url: link.url, collectionID: collectionID, title: link.title, tags: tags)
                    result = SaveResult(url: link.url, ok: true, raindropID: id)
                } catch let error as RaindropError {
                    result = SaveResult(url: link.url, ok: false, error: error.message)
                }
            }
            results.append(result)
            await progress?(index + 1, links.count, result)
        }
        return results
    }

    private func retryDelay(_ response: HTTPURLResponse, attempt: Int) -> Double {
        if let value = response.value(forHTTPHeaderField: "Retry-After"), let seconds = Double(value) {
            return max(1, seconds)
        }
        if let value = response.value(forHTTPHeaderField: "X-RateLimit-Reset"), let reset = Double(value) {
            return min(60, max(1, reset - now().timeIntervalSince1970))
        }
        return pow(2, Double(attempt + 1))
    }

    private func httpErrorMessage(_ status: Int, body: Data) -> String {
        if status == 401 { return "Unauthorized: check your Raindrop API token" }
        let json = (try? JSONSerialization.jsonObject(with: body)) as? [String: Any]
        let detail = nonEmptyString(json?["errorMessage"]) ?? nonEmptyString(json?["error"])
        return "HTTP \(status): \(detail ?? HTTPURLResponse.localizedString(forStatusCode: status))"
    }
}

private func nonEmptyString(_ value: Any?) -> String? {
    guard let s = value as? String, !s.isEmpty else { return nil }
    return s
}
