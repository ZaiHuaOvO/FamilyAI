# Family AI iOS 客户端（V7 首版）

SwiftUI iOS/iPadOS 客户端，连接家庭局域网内的 Family AI FastAPI 服务。

## 首版功能

- 配置 Mac 局域网地址与成员 Token。
- 测试连接（`/api/v1/me` + `/api/v1/health`）。
- 非流式聊天（`POST /api/v1/chat`）。
- 流式聊天（`POST /api/v1/chat/stream`，SSE）。
- 客户端携带最近对话历史；服务端不持久化。
- 连接/认证/限流/服务端错误提示。
- 清空当前会话。

不包含：记忆、任务、知识库页面、Widget、通知、登录账户系统。

## 构建要求

- macOS 上安装完整 **Xcode**（不是仅 Command Line Tools），并至少启动一次。
- iOS 17.0+。
- 已在仓库中包含 `FamilyAI.xcodeproj`（由 XcodeGen 生成）；修改 `project.yml` 后可重新生成：

```bash
cd ios
xcodegen generate
open FamilyAI.xcodeproj
```

如果 `xcodegen` 未安装，可从 <https://github.com/yonaskolb/XcodeGen/releases> 下载，或使用 Homebrew；也可以直接用 Xcode 打开已有的 `FamilyAI.xcodeproj`。

## 配置

1. 先确认 Mac 上的 FastAPI 正在运行，并取得当前局域网地址（例如 `http://192.168.5.18:8000`）。
2. 在 Mac 上创建成员 Token：

```bash
cd ..
uv run python -m family_ai_api.members.cli create --name iphone --role member
```

3. 在 App 设置中填写服务器地址与 Token，点击“测试连接”。
4. 返回聊天页开始对话。

外出访问：先按 [V8 运维手册](../docs/03-设计与规范/V8-外部访问运维手册.md) 启用 Tailscale Serve，然后在设置中填写完整 HTTPS 地址 `https://<machine>.<tailnet>.ts.net`。不要使用 Tailscale Funnel。裸 `*.ts.net` 地址会自动补 `https://`；其他地址仍默认 `http://`。

> Token 只保存在 iOS Keychain；服务器地址与流式开关保存在 UserDefaults。Token 轮换或撤销后，App 会收到 401，需要在设置中更新 Token。Keychain 访问依赖 `FamilyAI.entitlements` 的 `keychain-access-groups`；用 `CODE_SIGNING_ALLOWED=NO` 构建的安装包无法保存 Token。

## 网络与安全

- 只连接家庭局域网，不开放公网。
- `Info.plist` 设置 `NSAllowsLocalNetworking`，并声明本地网络用途。
- 如果 ATS 阻止当前 IP 的 HTTP 请求，可为该私有 IP 增加精确的 `NSExceptionDomains`，不要开启全局 `NSAllowsArbitraryLoads`。
- 不把 Token、聊天内容写入日志或截图。
- 默认地址 `http://192.168.5.18:8000` 只是占位，DHCP 变化后需要在设置中修改。

## 构建与运行

```bash
cd ios
xcodebuild -project FamilyAI.xcodeproj -scheme FamilyAI \
  -destination 'platform=iOS Simulator,name=iPhone 17' build
```

真机运行需要在 Xcode 中配置开发者团队与签名。

## 测试

```bash
cd ios
xcodebuild test -project FamilyAI.xcodeproj -scheme FamilyAI \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath /tmp/FamilyAI-DerivedData \
  -only-testing:FamilyAITests
```

- `FamilyAITests`：Keychain 保存/读取/删除；服务器地址归一化（https、裸 ts.net、局域网 http、非法 scheme）。
- `FamilyAIUITests`：连接、流式/非流式聊天、401 提示、重启后 Token 保持。
  UI 测试无法从运行环境取得 Token，需要先启动本机回环助手：

```bash
FAMILYAI_UI_TOKEN=<临时成员 Token> python3 scripts/ui-test-credentials.py
```

  助手只监听 `127.0.0.1:8765`，仅用于本地测试；测试结束后停止助手并撤销临时成员。
  没有助手时 UI 测试自动跳过。

## 代码结构

| 文件 | 职责 |
|---|---|
| `FamilyAIApp.swift` | App 入口 |
| `RootView.swift` | 未配置/聊天页切换、设置入口 |
| `SettingsView.swift` | 地址、Token、流式开关、测试连接 |
| `ChatView.swift` | 消息列表、输入、错误提示 |
| `ChatViewModel.swift` | 发送、流式增量、历史、错误处理 |
| `APIClient.swift` | HTTP 与 SSE 解析 |
| `Models.swift` | 请求/响应模型 |
| `KeychainStore.swift` | Token 安全存储 |
| `AppSettings.swift` | 配置持久化与地址归一化 |
| `FamilyAI.entitlements` | Keychain 访问组 |
| `FamilyAITests/` | Keychain 与地址归一化单元测试 |
| `FamilyAIUITests/` | 端到端 UI 测试 |

## 已知限制

- 首版不包含 Widget、通知、记忆/任务/知识库界面。
- 流式取消依赖 Task 取消；服务端会释放并发槽位。
- 真机签名、局域网权限与 ATS 尚未验证。
- 使用 Tailscale 时同一时间只能启用一个 VPN；后台挂起或 On Demand 行为需真机验证。
