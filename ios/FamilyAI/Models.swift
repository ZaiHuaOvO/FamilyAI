import Foundation

enum ChatRole: String, Codable, Sendable {
    case user
    case assistant
}

struct ChatMessage: Identifiable, Equatable, Sendable {
    let id: UUID
    var role: ChatRole
    var content: String
    var durationMs: Int?

    init(id: UUID = UUID(), role: ChatRole, content: String, durationMs: Int? = nil) {
        self.id = id
        self.role = role
        self.content = content
        self.durationMs = durationMs
    }
}

struct HistoryMessage: Encodable, Sendable {
    let role: String
    let content: String
}

struct ChatRequest: Encodable, Sendable {
    let message: String
    let history: [HistoryMessage]
}

struct ChatResponse: Decodable, Sendable {
    let message: String
    let model: String
    let durationMs: Int

    enum CodingKeys: String, CodingKey {
        case message
        case model
        case durationMs = "duration_ms"
    }
}

struct HealthResponse: Decodable, Sendable {
    let status: String
}

struct MeResponse: Decodable, Sendable {
    let id: Int
    let name: String
    let role: String
}

struct APIErrorBody: Decodable, Sendable {
    let detail: String?
}

enum ChatStreamEvent: Sendable {
    case delta(String)
    case done(durationMs: Int)
}
