import Foundation
import Security

/// Stores the Raindrop API token as a generic password in the login Keychain.
public struct TokenStore: Sendable {
    public enum Source: String, Sendable {
        case keychain = "Keychain"
        case environment = "RAINDROP_TOKEN"
        case none = "Not set"
    }

    public var service: String
    public var account: String

    public init(service: String = "com.fullstackranger.MarkdownToRaindrop", account: String = "raindrop-api-token") {
        self.service = service
        self.account = account
    }

    /// Keychain first, then the `RAINDROP_TOKEN` environment variable.
    public func resolve(environment: [String: String] = ProcessInfo.processInfo.environment) -> (token: String, source: Source) {
        if let token = load(), !token.isEmpty { return (token, .keychain) }
        if let token = environment["RAINDROP_TOKEN"]?.trimmingCharacters(in: .whitespacesAndNewlines), !token.isEmpty {
            return (token, .environment)
        }
        return ("", .none)
    }

    public func load() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    public func save(_ token: String) throws {
        let data = Data(token.utf8)
        let status = SecItemUpdate(baseQuery as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var attributes = baseQuery
            attributes[kSecValueData as String] = data
            attributes[kSecAttrLabel as String] = "Markdown to Raindrop API token"
            try check(SecItemAdd(attributes as CFDictionary, nil))
        } else {
            try check(status)
        }
    }

    public func delete() throws {
        let status = SecItemDelete(baseQuery as CFDictionary)
        if status != errSecItemNotFound { try check(status) }
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    private func check(_ status: OSStatus) throws {
        guard status == errSecSuccess else {
            let message = SecCopyErrorMessageString(status, nil) as String? ?? "OSStatus \(status)"
            throw RaindropError("Keychain error: \(message)")
        }
    }
}
