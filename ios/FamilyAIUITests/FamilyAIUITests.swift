import XCTest
import UIKit

@MainActor
final class FamilyAIUITests: XCTestCase {
    private struct Credentials: Decodable {
        let base_url: String
        let token: String
    }

    func testConnectChatAndPersist() async throws {
        continueAfterFailure = false

        let (baseURL, token) = try await loadCredentials()
        let app = XCUIApplication()
        app.launch()

        openSettings(in: app)

        let urlField = app.textFields["baseURLField"]
        XCTAssertTrue(urlField.waitForExistence(timeout: 10))
        urlField.tap()
        if (urlField.value as? String) != baseURL {
            let current = (urlField.value as? String) ?? ""
            urlField.typeText(
                String(
                    repeating: XCUIKeyboardKey.delete.rawValue,
                    count: current.count + 5
                )
            )
            urlField.typeText(baseURL)
        }

        let tokenField = app.secureTextFields["tokenField"]
        XCTAssertTrue(tokenField.exists)
        tokenField.tap()
        tokenField.typeText(token)

        let testButton = app.buttons["testConnectionButton"]
        XCTAssertTrue(testButton.isEnabled)
        testButton.tap()

        let status = app.staticTexts["settingsStatusText"].firstMatch
        XCTAssertTrue(status.waitForExistence(timeout: 15))
        wait(
            for: NSPredicate(format: "label BEGINSWITH %@", "已连接："),
            on: status,
            timeout: 90,
            message: "连接失败：\(status.label)"
        )

        app.buttons["doneButton"].tap()

        let input = app.textFields["chatInput"]
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        input.typeText("Say exactly: hello")
        app.buttons["sendButton"].tap()

        let reply = app.staticTexts["assistantMessageText"].firstMatch
        XCTAssertTrue(reply.waitForExistence(timeout: 30))
        wait(
            for: NSPredicate(format: "label != %@ AND label != %@", "…", ""),
            on: reply,
            timeout: 180,
            message: "流式聊天未收到回复"
        )
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 180))

        openSettings(in: app)
        let streamingToggle = app.switches["streamingToggle"]
        XCTAssertTrue(streamingToggle.waitForExistence(timeout: 5))
        if (streamingToggle.value as? String) == "1" {
            streamingToggle.tap()
        }
        app.buttons["doneButton"].tap()

        send("Say exactly: ok", in: app)
        let replies = app.staticTexts.matching(identifier: "assistantMessageText")
        let secondReply = replies.element(boundBy: 1)
        XCTAssertTrue(secondReply.waitForExistence(timeout: 30))
        wait(
            for: NSPredicate(format: "label != %@ AND label != %@", "…", ""),
            on: secondReply,
            timeout: 180,
            message: "非流式聊天未收到回复"
        )
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 180))

        openSettings(in: app)
        let settingsTokenField = app.secureTextFields["tokenField"]
        XCTAssertTrue(settingsTokenField.waitForExistence(timeout: 5))
        clear(settingsTokenField)
        settingsTokenField.typeText("invalid-token")
        app.buttons["testConnectionButton"].tap()
        let settingsStatus = app.staticTexts["settingsStatusText"].firstMatch
        wait(
            for: NSPredicate(format: "label CONTAINS %@", "Token 无效"),
            on: settingsStatus,
            timeout: 30,
            message: "无效 Token 未显示 401 提示：\(settingsStatus.label)"
        )

        clear(settingsTokenField)
        settingsTokenField.typeText(token)
        app.buttons["testConnectionButton"].tap()
        wait(
            for: NSPredicate(format: "label BEGINSWITH %@", "已连接："),
            on: settingsStatus,
            timeout: 90,
            message: "恢复 Token 后连接失败：\(settingsStatus.label)"
        )

        if (streamingToggle.value as? String) == "0" {
            streamingToggle.tap()
        }
        app.buttons["doneButton"].tap()

        XCTAssertEqual(
            app.staticTexts.matching(
                NSPredicate(format: "label CONTAINS %@", "网络错误")
            ).count,
            0
        )

        app.terminate()
        app.launch()

        XCTAssertTrue(app.buttons["settingsButton"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.buttons["openSettingsButton"].exists)
        let launchStatus = app.staticTexts["connectionStatusText"]
        XCTAssertTrue(launchStatus.waitForExistence(timeout: 15))
        wait(
            for: NSPredicate(format: "label BEGINSWITH %@", "已连接："),
            on: launchStatus,
            timeout: 90,
            message: "重启后 Token 未从 Keychain 恢复：\(launchStatus.label)"
        )
    }

    private func loadCredentials() async throws -> (String, String) {
        let env = ProcessInfo.processInfo.environment
        if let baseURL = env["FAMILYAI_UI_BASE_URL"],
           let token = env["FAMILYAI_UI_TOKEN"],
           !baseURL.isEmpty, !token.isEmpty {
            return (baseURL, token)
        }

        // Test-only loopback helper: ios/scripts/ui-test-credentials.py.
        if let url = URL(string: "http://127.0.0.1:8765/credentials"),
           let (data, response) = try? await URLSession.shared.data(from: url),
           (response as? HTTPURLResponse)?.statusCode == 200,
           let credentials = try? JSONDecoder().decode(Credentials.self, from: data) {
            return (credentials.base_url, credentials.token)
        }

        let payload = UIPasteboard.general.string ?? ""
        let lines = payload
            .split(separator: "\n", omittingEmptySubsequences: true)
            .map(String.init)
        guard lines.count == 2 else {
            throw XCTSkip(
                "Simulator 剪贴板需要两行：第一行服务器地址，第二行成员 Token"
            )
        }
        return (lines[0], lines[1])
    }

    private func openSettings(in app: XCUIApplication) {
        let setupButton = app.buttons["openSettingsButton"]
        if setupButton.waitForExistence(timeout: 8) {
            setupButton.tap()
            return
        }
        let gear = app.buttons["settingsButton"]
        XCTAssertTrue(gear.waitForExistence(timeout: 8))
        gear.tap()
    }

    private func send(_ text: String, in app: XCUIApplication) {
        let input = app.textFields["chatInput"]
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        input.typeText(text)
        app.buttons["sendButton"].tap()
    }

    private func clear(_ field: XCUIElement) {
        field.coordinate(
            withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)
        ).tap()
        field.typeText(
            String(repeating: XCUIKeyboardKey.delete.rawValue, count: 60)
        )
    }

    private func wait(
        for predicate: NSPredicate,
        on element: XCUIElement,
        timeout: TimeInterval,
        message: String
    ) {
        let expectation = XCTNSPredicateExpectation(
            predicate: predicate,
            object: element
        )
        let result = XCTWaiter.wait(for: [expectation], timeout: timeout)
        XCTAssertEqual(result, .completed, message)
    }
}
