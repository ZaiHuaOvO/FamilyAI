import XCTest
@testable import FamilyAI

final class AppSettingsTests: XCTestCase {
    func testTailscaleHostDefaultsToHTTPS() {
        XCTAssertEqual(
            AppSettings.normalizeBaseURL("family-ai-mac.example.ts.net")?
                .absoluteString,
            "https://family-ai-mac.example.ts.net"
        )
        XCTAssertEqual(
            AppSettings.normalizeBaseURL("family-ai-mac.example.ts.net:8443")?
                .absoluteString,
            "https://family-ai-mac.example.ts.net:8443"
        )
    }

    func testExplicitHTTPSIsPreserved() {
        XCTAssertEqual(
            AppSettings.normalizeBaseURL("https://family-ai-mac.example.ts.net")?
                .absoluteString,
            "https://family-ai-mac.example.ts.net"
        )
    }

    func testLANAddressStaysHTTP() {
        XCTAssertEqual(
            AppSettings.normalizeBaseURL("http://192.168.5.18:8000")?
                .absoluteString,
            "http://192.168.5.18:8000"
        )
        XCTAssertEqual(
            AppSettings.normalizeBaseURL("192.168.5.18:8000")?
                .absoluteString,
            "http://192.168.5.18:8000"
        )
    }

    func testPathAndTrailingSlashArePreserved() {
        XCTAssertEqual(
            AppSettings.normalizeBaseURL("family-ai-mac.example.ts.net/api/")?
                .absoluteString,
            "https://family-ai-mac.example.ts.net/api/"
        )
    }

    func testInvalidInputIsRejected() {
        XCTAssertNil(AppSettings.normalizeBaseURL(""))
        XCTAssertNil(AppSettings.normalizeBaseURL("   "))
        XCTAssertNil(AppSettings.normalizeBaseURL("ftp://family-ai-mac.example.ts.net"))
        XCTAssertNil(AppSettings.normalizeBaseURL("http://"))
    }
}
