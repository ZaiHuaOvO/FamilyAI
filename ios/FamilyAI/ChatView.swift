import SwiftUI

struct ChatView: View {
    @ObservedObject var model: ChatViewModel
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            if let status = model.connectionStatus {
                Text(status)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                    .padding(.top, 6)
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 10) {
                        if model.messages.isEmpty {
                            Text("开始和家庭 AI 聊天吧。")
                                .foregroundStyle(.secondary)
                                .padding(.top, 48)
                        }
                        ForEach(model.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: model.messages) { _, newValue in
                    guard let last = newValue.last else { return }
                    withAnimation {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }

            if let error = model.errorMessage {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                    Text(error)
                        .font(.footnote)
                    Spacer()
                    Button {
                        model.errorMessage = nil
                    } label: {
                        Image(systemName: "xmark")
                    }
                }
                .padding(10)
                .background(Color.red.opacity(0.12))
            }

            HStack(alignment: .bottom, spacing: 8) {
                TextField("输入消息…", text: $model.input, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.roundedBorder)
                    .focused($inputFocused)
                    .disabled(model.isSending)

                if model.isSending {
                    Button {
                        model.cancel()
                    } label: {
                        Image(systemName: "stop.circle.fill")
                            .font(.title2)
                    }
                } else {
                    Button {
                        model.send()
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
                    }
                    .disabled(!model.canSend)
                }
            }
            .padding(10)
        }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("清空") {
                    model.clear()
                }
                .disabled(model.messages.isEmpty || model.isSending)
            }
        }
        .task {
            await model.checkConnection()
        }
    }
}
