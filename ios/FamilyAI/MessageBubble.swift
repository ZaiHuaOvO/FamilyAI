import SwiftUI

struct MessageBubble: View {
    let message: ChatMessage

    private var isUser: Bool {
        message.role == .user
    }

    var body: some View {
        HStack {
            if isUser {
                Spacer(minLength: 44)
            }

            VStack(
                alignment: isUser ? .trailing : .leading,
                spacing: 4
            ) {
                Text(message.content.isEmpty ? "…" : message.content)
                    .padding(11)
                    .background(
                        isUser
                            ? Color.accentColor
                            : Color.gray.opacity(0.16)
                    )
                    .foregroundStyle(isUser ? Color.white : Color.primary)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .textSelection(.enabled)

                if let duration = message.durationMs, !isUser {
                    Text("\(duration) ms")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if !isUser {
                Spacer(minLength: 44)
            }
        }
    }
}
