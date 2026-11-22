import Foundation
import Testing
@testable import RaindropKit

private enum Reply {
    case json([String: Any], status: Int = 200, headers: [String: String] = [:])
    case failure(any Error)
}

private struct Call {
    var method: String
    var path: String
    var body: [String: Any]?
    var headers: [String: String]
}

/// Routes (method, path) to a handler, recording every request — mirrors FakeTransport in the pytest suite.
private final class FakeTransport: HTTPTransport, @unchecked Sendable {
    private let lock = NSLock()
    private let routes: [String: ([String: Any]?) -> Reply]
    private var recorded: [Call] = []

    init(_ routes: [String: ([String: Any]?) -> Reply]) {
        self.routes = routes
    }

    var calls: [Call] { lock.withLock { recorded } }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let method = request.httpMethod ?? "GET"
        let path = request.url!.absoluteString.replacingOccurrences(of: raindropAPIBase.absoluteString, with: "")
        let body = request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
        let reply: Reply = lock.withLock {
            recorded.append(Call(method: method, path: path, body: body, headers: request.allHTTPHeaderFields ?? [:]))
            return routes["\(method) \(path)"]!(body)
        }
        switch reply {
        case let .json(object, status, headers):
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: headers)!
            return (try JSONSerialization.data(withJSONObject: object), response)
        case let .failure(error):
            throw error
        }
    }
}

private final class SleepLog: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [Double] = []
    var all: [Double] { lock.withLock { values } }
    func append(_ value: Double) { lock.withLock { values.append(value) } }
}

private func makeClient(
    _ routes: [String: ([String: Any]?) -> Reply],
    maxRetries: Int = 3
) throws -> (RaindropClient, FakeTransport, SleepLog) {
    let transport = FakeTransport(routes)
    let sleeps = SleepLog()
    let client = try RaindropClient(token: "tok", transport: transport, maxRetries: maxRetries, sleep: { sleeps.append($0) })
    return (client, transport, sleeps)
}

private func always(_ reply: Reply) -> ([String: Any]?) -> Reply { { _ in reply } }

@Suite struct RaindropClientTests {
    @Test func requiresToken() {
        #expect(throws: RaindropError.self) { try RaindropClient(token: "") }
    }

    @Test func getCollectionsBuildsNestedPaths() async throws {
        let (client, transport, _) = try makeClient([
            "GET /collections": always(.json(["result": true, "items": [
                ["_id": 1, "title": "Work", "count": 3],
                ["_id": 2, "title": "reading"],
            ]])),
            "GET /collections/childrens": always(.json(["result": true, "items": [
                ["_id": 10, "title": "Python", "parent": ["$id": 1], "count": 5],
                ["_id": 11, "title": "Async", "parent": ["$id": 10]],
            ]])),
        ])
        let collections = try await client.getCollections()
        #expect(collections.map(\.id) == [unsortedCollectionID, 2, 1, 10, 11])
        #expect(collections.map(\.path) == ["Unsorted", "reading", "Work", "Work / Python", "Work / Python / Async"])
        #expect(collections[3].count == 5)
        #expect(transport.calls[0].headers["Authorization"] == "Bearer tok")

        let tree = buildCollectionTree(collections)
        #expect(tree.map(\.collection.title) == ["Unsorted", "reading", "Work"])
        #expect(tree[2].children?.map(\.collection.title) == ["Python"])
        #expect(tree[2].children?[0].children?.map(\.collection.title) == ["Async"])
        #expect(tree[0].children == nil)
    }

    @Test func collectionTreeToleratesMissingParentAndCycles() {
        let list = buildCollectionList(roots: [], children: [
            ["_id": 5, "title": "Orphan", "parent": ["$id": 999]],
            ["_id": 6, "title": "A", "parent": ["$id": 7]],
            ["_id": 7, "title": "B", "parent": ["$id": 6]],
        ])
        let paths = Dictionary(uniqueKeysWithValues: list.map { ($0.id, $0.path) })
        #expect(paths[5] == "Orphan")
        #expect(paths[6]!.hasSuffix("A") && paths[7]!.hasSuffix("B"))

        func ids(_ nodes: [CollectionNode]) -> [Int] { nodes.flatMap { [$0.id] + ids($0.children ?? []) } }
        #expect(Set(ids(buildCollectionTree(list))) == [unsortedCollectionID, 5, 6, 7])
    }

    @Test func createBookmarkPayload() async throws {
        let (client, transport, _) = try makeClient(["POST /raindrop": always(.json(["result": true, "item": ["_id": 42]]))])
        let id = try await client.createBookmark(url: "https://x.example", collectionID: 7, title: "X", tags: ["md", ""])
        #expect(id == 42)
        let call = transport.calls[0]
        #expect(NSDictionary(dictionary: call.body!) == NSDictionary(dictionary: [
            "link": "https://x.example",
            "collection": ["$id": 7],
            "pleaseParse": [String: Any](),
            "title": "X",
            "tags": ["md"],
        ]))
        #expect(call.headers["Content-Type"] == "application/json")
    }

    @Test func createBookmarkOmitsEmptyTitleAndTags() async throws {
        let (client, transport, _) = try makeClient(["POST /raindrop": always(.json(["result": true, "item": [String: Any]()]))])
        try await client.createBookmark(url: "https://x.example", collectionID: -1)
        #expect(NSDictionary(dictionary: transport.calls[0].body!) == NSDictionary(dictionary: [
            "link": "https://x.example", "collection": ["$id": -1], "pleaseParse": [String: Any](),
        ]))
    }

    @Test func apiResultFalseThrows() async throws {
        let (client, _, _) = try makeClient(["GET /collections": always(.json(["result": false, "errorMessage": "bad"]))])
        await #expect(throws: RaindropError("bad")) { _ = try await client.request("GET", "/collections") }
    }

    @Test func unauthorizedMessage() async throws {
        let (client, _, _) = try makeClient(["GET /collections": always(.json([:], status: 401))])
        let error = await #expect(throws: RaindropError.self) { _ = try await client.request("GET", "/collections") }
        #expect(error?.message.contains("token") == true)
        #expect(error?.status == 401)
    }

    @Test func httpErrorIncludesAPIDetail() async throws {
        let (client, _, _) = try makeClient(["GET /collections": always(.json(["errorMessage": "nope"], status: 400))])
        await #expect(throws: RaindropError("HTTP 400: nope", status: 400)) { _ = try await client.request("GET", "/collections") }
    }

    @Test func rateLimitIsRetried() async throws {
        let attempts = SleepLog()
        let (client, _, sleeps) = try makeClient(["POST /raindrop": { _ in
            attempts.append(1)
            return attempts.all.count < 3
                ? .json([:], status: 429, headers: ["Retry-After": "3"])
                : .json(["result": true, "item": [String: Any]()])
        }])
        try await client.createBookmark(url: "https://x.example", collectionID: 1)
        #expect(attempts.all.count == 3)
        #expect(sleeps.all == [3, 3])
    }

    @Test func rateLimitGivesUpAfterMaxRetries() async throws {
        let (client, _, sleeps) = try makeClient(["POST /raindrop": always(.json([:], status: 429))], maxRetries: 2)
        let error = await #expect(throws: RaindropError.self) {
            try await client.createBookmark(url: "https://x.example", collectionID: 1)
        }
        #expect(error?.status == 429)
        #expect(sleeps.all == [2, 4])
    }

    @Test func networkErrorIsWrapped() async throws {
        let (client, _, _) = try makeClient(["GET /collections": always(.failure(URLError(.cannotConnectToHost)))])
        let error = await #expect(throws: RaindropError.self) { _ = try await client.request("GET", "/collections") }
        #expect(error?.message.hasPrefix("Network error") == true)
    }

    @Test func findExistingBatchesRequests() async throws {
        let all = (0..<150).map { "https://e.example/\($0)" }
        let (client, transport, _) = try makeClient(["POST /import/url/exists": { body in
            let batch = body?["urls"] as? [String] ?? []
            let dups = batch.enumerated()
                .filter { $0.element.hasSuffix("/5") || $0.element.hasSuffix("/120") }
                .map { ["_id": 1000 + $0.offset, "link": $0.element] as [String: Any] }
            return .json(["result": true, "duplicates": dups])
        }])
        let existing = try await client.findExisting(all)
        #expect(transport.calls.count == 2)
        #expect((transport.calls[0].body?["urls"] as? [String])?.count == 100)
        #expect(Set(existing.keys) == ["https://e.example/5", "https://e.example/120"])
    }

    @Test func saveLinksReportsProgressSkipsAndErrors() async throws {
        let (client, transport, _) = try makeClient([
            "POST /import/url/exists": always(.json(["result": true, "duplicates": [["_id": 9, "link": "https://dup.example"]]])),
            "POST /raindrop": { body in
                body?["link"] as? String == "https://bad.example"
                    ? .json(["errorMessage": "invalid link"], status: 400)
                    : .json(["result": true, "item": ["_id": 1]])
            },
        ])
        let links = [Link(url: "https://ok.example", title: "OK"), Link(url: "https://dup.example"), Link(url: "https://bad.example")]
        let progress = ProgressLog()
        let results = try await client.saveLinks(links, collectionID: 3, tags: ["t"], progress: { i, n, r in progress.append(i, n, r.url) })

        #expect(results.map(\.url) == links.map(\.url))
        #expect(results.map(\.ok) == [true, true, false])
        #expect(results.map(\.skipped) == [false, true, false])
        #expect(results[1].raindropID == 9)
        #expect(results[2].error.contains("invalid link"))
        #expect(progress.entries == ["1/3 https://ok.example", "2/3 https://dup.example", "3/3 https://bad.example"])
        let created = transport.calls.filter { $0.path == "/raindrop" }.compactMap { $0.body?["link"] as? String }
        #expect(created == ["https://ok.example", "https://bad.example"])
    }

    @Test func saveLinksWithoutSkipExistingDoesNotCheck() async throws {
        let (client, transport, _) = try makeClient(["POST /raindrop": always(.json(["result": true, "item": ["_id": 1]]))])
        _ = try await client.saveLinks([Link(url: "https://a.example")], collectionID: 1, skipExisting: false)
        #expect(transport.calls.map(\.path) == ["/raindrop"])
    }

    @Test func saveLinksCanBeStopped() async throws {
        let (client, _, _) = try makeClient(["POST /raindrop": always(.json(["result": true, "item": [String: Any]()]))])
        let links = (0..<5).map { Link(url: "https://e.example/\($0)") }
        let seen = ProgressLog()
        let results = try await client.saveLinks(
            links, collectionID: 1, skipExisting: false,
            shouldStop: { seen.entries.count >= 2 },
            progress: { i, n, r in seen.append(i, n, r.url) }
        )
        #expect(results.count == 2)
    }

    @Test func demoTransportServesTreeDuplicatesAndFailures() async throws {
        let client = try RaindropClient(token: "demo", transport: DemoTransport(delay: .zero))
        let tree = buildCollectionTree(try await client.getCollections())
        #expect(tree.first?.collection.title == "Unsorted")
        #expect(tree.contains { $0.children?.contains { $0.children != nil } == true })

        let saved = DemoTransport.alreadySaved.first!
        let results = try await client.saveLinks(
            [Link(url: saved), Link(url: "https://new.example"), Link(url: "https://fail.example")], collectionID: 1
        )
        #expect(results.map(\.skipped) == [true, false, false])
        #expect(results.map(\.ok) == [true, true, false])
    }
}

private final class ProgressLog: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String] = []
    var entries: [String] { lock.withLock { values } }
    func append(_ i: Int, _ n: Int, _ url: String) { lock.withLock { values.append("\(i)/\(n) \(url)") } }
}
