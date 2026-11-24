import XCTest
@testable import FamilyAI

final class KeychainStoreTests: XCTestCase {
    func testSaveReadDelete() {
        let account = "keychain.test.\(UUID().uuidString)"
        XCTAssertTrue(KeychainStore.save("token-value", account: account))
        XCTAssertEqual(KeychainStore.read(account: account), "token-value")
        KeychainStore.delete(account: account)
        XCTAssertNil(KeychainStore.read(account: account))
    }
}
