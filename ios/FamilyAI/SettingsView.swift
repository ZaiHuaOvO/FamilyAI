import SwiftUI

struct SettingsView: View {
    @ObservedObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss
    @State private var status: String?
    @State private var testing = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(
                        "http://192.168.5.18:8000",
                        text: $settings.baseURL
                    )
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)

                    SecureField("API Token", text: $settings.token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Toggle("流式输出", isOn: $settings.streamingEnabled)
                } header: {
                    Text("服务器")
                } footer: {
                    Text("填写 Mac 的局域网地址与成员 Token。Token 只保存在本机 Keychain；地址和流式开关保存在 UserDefaults。")
                }

                Section {
                    Button {
                        Task { @MainActor in
                            await testConnection()
                        }
                    } label: {
                        HStack {
                            if testing {
                                ProgressView()
                            } else {
                                Text("测试连接")
                            }
                        }
                    }
                    .disabled(testing || !settings.isConfigured)

                    if let status {
                        Text(status)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                } footer: {
                    Text("局域网 IP 可能因 DHCP 变化；连接失败时先确认 Mac 当前 IP 与服务是否运行。")
                }
            }
            .navigationTitle("设置")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") {
                        dismiss()
                    }
                }
            }
        }
    }

    private func testConnection() async {
        guard let url = settings.normalizedBaseURL else {
            status = "服务器地址无效"
            return
        }
        let token = settings.token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !token.isEmpty else {
            status = "请填写 Token"
            return
        }

        testing = true
        status = "连接中…"
        defer { testing = false }

        let client = APIClient(baseURL: url, token: token)
        do {
            let me = try await client.me()
            try? await client.health()
            status = "已连接：\(me.name)（\(me.role)）"
        } catch {
            status = "连接失败：\(error.localizedDescription)"
        }
    }
}
