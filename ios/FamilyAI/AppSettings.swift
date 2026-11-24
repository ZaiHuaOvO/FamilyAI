import Combine
import Foundation

final class AppSettings: ObservableObject {
    private enum Keys {
        static let baseURL = "familyai.baseURL"
        static let streaming = "familyai.streamingEnabled"
        static let tokenAccount = "familyai.apiToken"
    }

    @Published var baseURL: String {
        didSet {
            UserDefaults.standard.set(baseURL, forKey: Keys.baseURL)
        }
    }

    @Published var token: String {
        didSet {
            _ = KeychainStore.save(token, account: Keys.tokenAccount)
        }
    }

    @Published var streamingEnabled: Bool {
        didSet {
            UserDefaults.standard.set(streamingEnabled, forKey: Keys.streaming)
        }
    }

    init() {
        baseURL = UserDefaults.standard.string(forKey: Keys.baseURL)
            ?? "http://192.168.5.18:8000"
        token = KeychainStore.read(account: Keys.tokenAccount) ?? ""
        streamingEnabled = UserDefaults.standard.object(forKey: Keys.streaming)
            as? Bool ?? true
    }

    var isConfigured: Bool {
        !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && normalizedBaseURL != nil
    }

    var normalizedBaseURL: URL? {
        Self.normalizeBaseURL(baseURL)
    }

    static func normalizeBaseURL(_ raw: String) -> URL? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        var candidate = trimmed
        if !trimmed.contains("://") {
            let host = trimmed.split(separator: "/", maxSplits: 1).first ?? ""
            let hostname = host.split(separator: ":", maxSplits: 1).first ?? ""
            let scheme = hostname.hasSuffix(".ts.net") ? "https" : "http"
            candidate = "\(scheme)://\(trimmed)"
        }

        guard var components = URLComponents(string: candidate),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = components.host,
              !host.isEmpty else {
            return nil
        }
        return components.url
    }
}
