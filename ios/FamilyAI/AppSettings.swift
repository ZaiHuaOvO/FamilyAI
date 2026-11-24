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
        let raw = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { return nil }
        guard var components = URLComponents(string: raw) else { return nil }
        if components.scheme == nil {
            components.scheme = "http"
        }
        return components.url
    }
}
