import Foundation

enum APIError: LocalizedError, Sendable {
    case invalidConfiguration
    case unauthorized
    case rateLimited
    case server(String)
    case network(String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidConfiguration:
            return "服务器地址或 Token 未配置"
        case .unauthorized:
            return "Token 无效或已被撤销，请在设置中更新"
        case .rateLimited:
            return "请求过于频繁或并发已满，请稍后再试"
        case .server(let detail):
            return "服务端错误：\(detail)"
        case .network(let detail):
            return "网络错误：\(detail)"
        case .decoding:
            return "响应解析失败"
        }
    }
}

struct APIClient: Sendable {
    let baseURL: URL
    let token: String

    private struct DeltaEvent: Decodable {
        let delta: String
    }

    private struct DoneEvent: Decodable {
        let durationMs: Int

        enum CodingKeys: String, CodingKey {
            case durationMs = "duration_ms"
        }
    }

    private struct StreamErrorEvent: Decodable {
        let detail: String
        let status: Int?
    }

    func health() async throws {
        let _: HealthResponse = try await send(makeRequest(path: "api/v1/health"))
    }

    func me() async throws -> MeResponse {
        try await send(makeRequest(path: "api/v1/me"))
    }

    func chat(message: String, history: [HistoryMessage]) async throws -> ChatResponse {
        var request = makeRequest(path: "api/v1/chat", method: "POST")
        request.httpBody = try JSONEncoder().encode(
            ChatRequest(message: message, history: history)
        )
        return try await send(request)
    }

    func streamChat(
        message: String,
        history: [HistoryMessage]
    ) -> AsyncThrowingStream<ChatStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var request = makeRequest(path: "api/v1/chat/stream", method: "POST")
                    request.httpBody = try JSONEncoder().encode(
                        ChatRequest(message: message, history: history)
                    )

                    let (bytes, response) = try await URLSession.shared.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw APIError.network("无效的服务器响应")
                    }

                    switch http.statusCode {
                    case 200...299:
                        break
                    case 401:
                        throw APIError.unauthorized
                    case 429:
                        throw APIError.rateLimited
                    default:
                        var body = ""
                        for try await line in bytes.lines {
                            body += line
                        }
                        throw APIError.server(
                            Self.errorDetail(from: body, status: http.statusCode)
                        )
                    }

                    var event = ""
                    for try await line in bytes.lines {
                        if line.hasPrefix("event:") {
                            event = String(line.dropFirst("event:".count))
                                .trimmingCharacters(in: .whitespaces)
                        } else if line.hasPrefix("data:") {
                            let payload = String(line.dropFirst("data:".count))
                                .trimmingCharacters(in: .whitespaces)
                            guard let data = payload.data(using: .utf8) else { continue }

                            switch event {
                            case "delta":
                                if let delta = try? JSONDecoder().decode(
                                    DeltaEvent.self, from: data
                                ) {
                                    continuation.yield(.delta(delta.delta))
                                }
                            case "done":
                                if let done = try? JSONDecoder().decode(
                                    DoneEvent.self, from: data
                                ) {
                                    continuation.yield(.done(durationMs: done.durationMs))
                                    continuation.finish()
                                    return
                                }
                            case "error":
                                if let streamError = try? JSONDecoder().decode(
                                    StreamErrorEvent.self, from: data
                                ) {
                                    throw APIError.server(streamError.detail)
                                }
                            default:
                                break
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private func makeRequest(path: String, method: String = "GET") -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.timeoutInterval = 180
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return request
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw APIError.network("无效的服务器响应")
            }

            switch http.statusCode {
            case 200...299:
                break
            case 401:
                throw APIError.unauthorized
            case 429:
                throw APIError.rateLimited
            default:
                throw APIError.server(
                    Self.errorDetail(
                        from: String(data: data, encoding: .utf8) ?? "",
                        status: http.statusCode
                    )
                )
            }

            do {
                return try JSONDecoder().decode(T.self, from: data)
            } catch {
                throw APIError.decoding("响应解析失败")
            }
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.network(error.localizedDescription)
        }
    }

    private static func errorDetail(from body: String, status: Int) -> String {
        if let data = body.data(using: .utf8),
           let decoded = try? JSONDecoder().decode(APIErrorBody.self, from: data),
           let detail = decoded.detail,
           !detail.isEmpty {
            return detail
        }
        return "HTTP \(status)"
    }
}
