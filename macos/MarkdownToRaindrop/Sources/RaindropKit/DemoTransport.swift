import Foundation

/// Offline stand-in for the Raindrop API used by `--demo`: serves a fixed collection tree,
/// reports a few URLs as already saved, and rejects URLs containing "fail" with HTTP 400.
public actor DemoTransport: HTTPTransport {
    public static let alreadySaved: Set<String> = ["https://developer.apple.com/design/human-interface-guidelines"]

    private var saved = DemoTransport.alreadySaved
    private var nextID = 1000
    private let delay: Duration

    public init(delay: Duration = .milliseconds(250)) {
        self.delay = delay
    }

    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let path = request.url?.path.replacingOccurrences(of: "/rest/v1", with: "") ?? ""
        let body = request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        try await Task.sleep(for: delay)

        switch (request.httpMethod ?? "GET", path) {
        case ("GET", "/collections"):
            return respond(["result": true, "items": [
                ["_id": 1, "title": "Development", "count": 128],
                ["_id": 2, "title": "Design", "count": 42],
                ["_id": 3, "title": "Reading List", "count": 17],
            ]])
        case ("GET", "/collections/childrens"):
            return respond(["result": true, "items": [
                ["_id": 10, "title": "Swift", "count": 64, "parent": ["$id": 1]],
                ["_id": 11, "title": "SwiftUI", "count": 31, "parent": ["$id": 10]],
                ["_id": 12, "title": "Python", "count": 22, "parent": ["$id": 1]],
                ["_id": 13, "title": "Tooling", "count": 9, "parent": ["$id": 1]],
                ["_id": 20, "title": "Liquid Glass", "count": 6, "parent": ["$id": 2]],
                ["_id": 21, "title": "Typography", "count": 11, "parent": ["$id": 2]],
            ]])
        case ("POST", "/import/url/exists"):
            let urls = body["urls"] as? [String] ?? []
            let duplicates = urls.filter(saved.contains).enumerated().map { ["_id": 500 + $0.offset, "link": $0.element] as [String: Any] }
            return respond(["result": true, "duplicates": duplicates])
        case ("POST", "/raindrop"):
            let link = body["link"] as? String ?? ""
            if link.contains("fail") {
                return respond(["result": false, "errorMessage": "Invalid link (demo failure)"], status: 400)
            }
            saved.insert(link)
            nextID += 1
            return respond(["result": true, "item": ["_id": nextID, "link": link]])
        default:
            return respond(["result": false, "errorMessage": "Not found"], status: 404)
        }
    }

    private func respond(_ object: [String: Any], status: Int = 200) -> (Data, HTTPURLResponse) {
        let data = (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
        let response = HTTPURLResponse(url: raindropAPIBase, statusCode: status, httpVersion: nil, headerFields: nil)!
        return (data, response)
    }
}
