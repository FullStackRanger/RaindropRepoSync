import Foundation

public struct RaindropCollection: Identifiable, Hashable, Sendable {
    public var id: Int
    public var title: String
    /// "Parent / Child" path, used for sorting and display outside the tree.
    public var path: String
    public var count: Int
    public var parentID: Int?

    public init(id: Int, title: String, path: String, count: Int = 0, parentID: Int? = nil) {
        self.id = id
        self.title = title
        self.path = path
        self.count = count
        self.parentID = parentID
    }
}

public struct CollectionNode: Identifiable, Hashable, Sendable {
    public var collection: RaindropCollection
    /// `nil` for leaves so `OutlineGroup` shows no disclosure triangle.
    public var children: [CollectionNode]?

    public var id: Int { collection.id }
}

/// Port of `build_collection_tree` from `raindrop_api.py`: flat list sorted by path, Unsorted first.
/// Tolerates missing parents and parent cycles.
public func buildCollectionList(roots: [[String: Any]], children: [[String: Any]]) -> [RaindropCollection] {
    var byID: [Int: [String: Any]] = [:]
    var order: [Int] = []
    for raw in roots + children {
        guard let id = raw["_id"] as? Int else { continue }
        if byID[id] == nil { order.append(id) }
        byID[id] = raw
    }

    func parentID(_ raw: [String: Any]) -> Int? {
        (raw["parent"] as? [String: Any])?["$id"] as? Int
    }

    func path(of raw: [String: Any], seen: Set<Int> = []) -> String {
        let title = raw["title"] as? String ?? ""
        guard let pid = parentID(raw), let parent = byID[pid], !seen.contains(pid), let id = raw["_id"] as? Int else {
            return title
        }
        return path(of: parent, seen: seen.union([id])) + " / " + title
    }

    let collections = order.compactMap { id -> RaindropCollection? in
        guard let raw = byID[id] else { return nil }
        let pid = parentID(raw).flatMap { byID[$0] != nil ? $0 : nil }
        return RaindropCollection(
            id: id,
            title: raw["title"] as? String ?? "",
            path: path(of: raw),
            count: raw["count"] as? Int ?? 0,
            parentID: pid
        )
    }
    .sorted { $0.path.lowercased() < $1.path.lowercased() }
    return [RaindropCollection(id: unsortedCollectionID, title: "Unsorted", path: "Unsorted")] + collections
}

/// Nest a flat collection list into a tree for the sidebar. Nodes in a parent cycle become roots
/// so nothing disappears; order within each level follows the input (path-sorted) order.
public func buildCollectionTree(_ collections: [RaindropCollection]) -> [CollectionNode] {
    let ids = Set(collections.map(\.id))
    var childrenByParent: [Int: [RaindropCollection]] = [:]
    for c in collections {
        if let pid = c.parentID, ids.contains(pid) {
            childrenByParent[pid, default: []].append(c)
        }
    }

    var placed = Set<Int>()
    func node(_ c: RaindropCollection) -> CollectionNode {
        placed.insert(c.id)
        let kids = (childrenByParent[c.id] ?? []).filter { !placed.contains($0.id) }.map(node)
        return CollectionNode(collection: c, children: kids.isEmpty ? nil : kids)
    }

    var roots = collections.filter { c in c.parentID.map { !ids.contains($0) } ?? true }.map(node)
    for c in collections where !placed.contains(c.id) {
        roots.append(node(c))
    }
    return roots
}
