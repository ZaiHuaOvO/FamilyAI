import Combine
import Foundation

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published var input: String = ""
    @Published private(set) var isSending = false
    @Published var errorMessage: String?
    @Published private(set) var connectionStatus: String?

    private let settings: AppSettings
    private var streamTask: Task<Void, Never>?

    init(settings: AppSettings) {
        self.settings = settings
    }

    var canSend: Bool {
        !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !isSending
            && settings.isConfigured
    }

    func checkConnection() async {
        guard let client = makeClient() else {
            connectionStatus = "未配置服务器或 Token"
            return
        }
        do {
            let me = try await client.me()
            try? await client.health()
            connectionStatus = "已连接：\(me.name)（\(me.role)）"
        } catch {
            connectionStatus = "连接失败：\(error.localizedDescription)"
        }
    }

    func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending, let client = makeClient() else { return }

        let history = makeHistory()
        input = ""
        errorMessage = nil
        messages.append(ChatMessage(role: .user, content: text))
        messages.append(ChatMessage(role: .assistant, content: ""))
        isSending = true

        streamTask = Task { @MainActor in
            defer {
                isSending = false
                streamTask = nil
            }

            do {
                if settings.streamingEnabled {
                    for try await event in client.streamChat(
                        message: text,
                        history: history
                    ) {
                        switch event {
                        case .delta(let delta):
                            appendDelta(delta)
                        case .done(let duration):
                            setDuration(duration)
                        }
                    }
                } else {
                    let response = try await client.chat(
                        message: text,
                        history: history
                    )
                    replaceLast(
                        content: response.message,
                        duration: response.durationMs
                    )
                }
            } catch {
                if Task.isCancelled {
                    return
                }
                errorMessage = error.localizedDescription
                removeEmptyAssistantIfNeeded()
            }
        }
    }

    func cancel() {
        streamTask?.cancel()
        streamTask = nil
        isSending = false
        removeEmptyAssistantIfNeeded()
    }

    func clear() {
        messages.removeAll()
        errorMessage = nil
    }

    private func makeClient() -> APIClient? {
        guard let url = settings.normalizedBaseURL else { return nil }
        let token = settings.token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !token.isEmpty else { return nil }
        return APIClient(baseURL: url, token: token)
    }

    private func makeHistory() -> [HistoryMessage] {
        var result: [HistoryMessage] = []
        var totalCharacters = 0

        for message in messages.reversed() {
            if result.count >= 20 {
                break
            }
            totalCharacters += message.content.count
            if totalCharacters > 12000 {
                break
            }
            result.append(
                HistoryMessage(
                    role: message.role.rawValue,
                    content: message.content
                )
            )
        }

        return Array(result.reversed())
    }

    private func appendDelta(_ delta: String) {
        guard let index = messages.indices.last else { return }
        messages[index].content += delta
    }

    private func setDuration(_ duration: Int) {
        guard let index = messages.indices.last else { return }
        messages[index].durationMs = duration
    }

    private func replaceLast(content: String, duration: Int) {
        guard let index = messages.indices.last else { return }
        messages[index].content = content
        messages[index].durationMs = duration
    }

    private func removeEmptyAssistantIfNeeded() {
        guard let last = messages.last,
              last.role == .assistant,
              last.content.isEmpty else {
            return
        }
        messages.removeLast()
    }
}
