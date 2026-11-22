import Foundation
import Testing
@testable import RaindropKit

@Suite struct TokenStoreTests {
    private let missing = TokenStore(service: "com.fullstackranger.MarkdownToRaindrop.tests.\(UUID().uuidString)")

    @Test func fallsBackToEnvironmentWhenKeychainIsEmpty() {
        let resolved = missing.resolve(environment: ["RAINDROP_TOKEN": "  env-token \n"])
        #expect(resolved.token == "env-token")
        #expect(resolved.source == .environment)
        #expect(missing.resolve(environment: [:]).source == TokenStore.Source.none)
    }

    /// Writes to the login Keychain, so it only runs with RUN_KEYCHAIN_TESTS=1.
    @Test(.enabled(if: ProcessInfo.processInfo.environment["RUN_KEYCHAIN_TESTS"] == "1"))
    func keychainRoundTrip() throws {
        let store = missing
        defer { try? store.delete() }
        try store.save("first")
        try store.save("second")
        #expect(store.load() == "second")
        #expect(store.resolve(environment: ["RAINDROP_TOKEN": "env"]) == ("second", .keychain))
        try store.delete()
        #expect(store.load() == nil)
        try store.delete()
    }
}
