import SwiftUI

@MainActor
struct RootView: View {
    @ObservedObject var settings: AppSettings
    @StateObject private var model: ChatViewModel
    @State private var showSettings = false

    init(settings: AppSettings) {
        self.settings = settings
        _model = StateObject(wrappedValue: ChatViewModel(settings: settings))
    }

    var body: some View {
        NavigationStack {
            Group {
                if settings.isConfigured {
                    ChatView(model: model)
                } else {
                    SetupView(showSettings: $showSettings)
                }
            }
            .navigationTitle("Family AI")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityIdentifier("settingsButton")
                    .accessibilityLabel("设置")
                }
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView(settings: settings)
        }
    }
}

private struct SetupView: View {
    @Binding var showSettings: Bool

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "house.fill")
                .font(.system(size: 56))
                .foregroundStyle(.tint)
            Text("连接家庭 AI")
                .font(.title2.bold())
            Text("在设置中填写 Mac 的局域网地址或 Tailscale 私有网络地址，以及成员 Token。Token 只保存在本机 Keychain。")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("打开设置") {
                showSettings = true
            }
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier("openSettingsButton")
        }
        .padding(28)
    }
}
