# V7：Apple iOS 客户端（首版）

> 状态：**已完成（Simulator 自动化验收通过；真机待验证）— 2026-11-24**  
> 前置：V6（`v6.0.0`）已完成  
> 决策依据：[V7 Apple 客户端方案决策](../06-决策记录/V7-Apple客户端方案.md)

## 1. 目标与决定

为家庭局域网提供原生 iOS/iPadOS 聊天客户端。

已确认的决定：

- 平台：**iOS/iPadOS SwiftUI**。
- 首版范围：**聊天核心**（Token 配置、健康检查、非流式/流式聊天、历史、错误提示）。
- 通知：**首版无通知**。
- 代码位置：当前仓库 `ios/`。

## 2. 代码结构

```text
ios/
├── project.yml                  # XcodeGen 工程定义
├── FamilyAI.xcodeproj           # 生成的 Xcode 工程
├── FamilyAI/
│   ├── FamilyAIApp.swift
│   ├── RootView.swift
│   ├── ChatView.swift
│   ├── MessageBubble.swift
│   ├── SettingsView.swift
│   ├── ChatViewModel.swift
│   ├── APIClient.swift          # HTTP + SSE
│   ├── AppSettings.swift        # 地址/流式开关持久化
│   ├── KeychainStore.swift      # Token 安全存储
│   ├── Models.swift
│   ├── Info.plist
│   ├── FamilyAI.entitlements   # Keychain 访问组
│   └── Assets.xcassets/
├── FamilyAITests/               # Keychain 单元测试
├── FamilyAIUITests/             # 端到端 UI 测试
└── README.md
```

## 3. 功能

- 设置服务器地址与成员 Token；Token 存 Keychain。
- `GET /api/v1/me` + `GET /api/v1/health` 测试连接，显示成员名与角色。
- `POST /api/v1/chat` 非流式聊天。
- `POST /api/v1/chat/stream` SSE 流式聊天（delta/done/error）。
- 客户端携带最近 20 条、总字符 ≤ 12000 的历史；服务端不持久化。
- 401/429/网络错误/服务端错误给出可读提示。
- 清空当前会话、停止流式输出。

## 4. 网络与安全

- 只访问家庭局域网；不接公网。
- `Info.plist`：`NSAllowsLocalNetworking` + 本地网络用途说明。
- Token 只保存在 Keychain（`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`）。
- `FamilyAI.entitlements` 声明 `keychain-access-groups`；Simulator 构建会写入
  `FAKETEAMID.com.familyai.app`。不要再用 `CODE_SIGNING_ALLOWED=NO` 构建安装包，
  否则 Token 无法写入 Keychain。
- 不在日志、源码或 UserDefaults 中保存 Token。
- Token 轮换/撤销后收到 401，需要重新配置。
- 默认地址 `http://192.168.5.18:8000` 只是占位；DHCP 变化后需修改。

## 5. 构建

需要完整 Xcode（不是仅 Command Line Tools）：

```bash
cd ios
xcodegen generate   # 修改 project.yml 后
open FamilyAI.xcodeproj
```

命令行构建与测试：

```bash
cd ios
xcodegen generate
xcodebuild -project FamilyAI.xcodeproj -scheme FamilyAI \
  -destination 'platform=iOS Simulator,name=iPhone 17' build

xcodebuild test -project FamilyAI.xcodeproj -scheme FamilyAI \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath /tmp/FamilyAI-DerivedData \
  -only-testing:FamilyAITests
```

端到端 UI 测试（需要本机临时凭据端点，见验收记录）：

```bash
xcodebuild test -project FamilyAI.xcodeproj -scheme FamilyAI \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath /tmp/FamilyAI-DerivedData \
  -only-testing:FamilyAIUITests/FamilyAIUITests/testConnectChatAndPersist
```

真机需要配置开发者团队与签名。

## 6. 已验证 / 待验证

已验证（2026-11-24，iPhone 17 Simulator / iOS 27.2）：

- Xcode 27.2 编译通过：`** BUILD SUCCEEDED **`。
- Keychain 单元测试通过：保存、读取、删除。
- UI 测试通过（81.3s）：临时成员登录 → 测试连接 → 流式聊天 → 非流式聊天
  → 无效 Token 显示 401 → 恢复 Token → 结束进程重启后自动连接。
- 139 项后端测试与 ruff 仍通过（后端未改动）。
- 测试用临时成员已全部撤销；Token 未写入源码、日志或提交。

待验证：

- [ ] 真机签名、局域网权限与 ATS 行为。
- [ ] 429 限流提示（后端已有覆盖）。

## 7. 已知限制

- 首版不含记忆、任务、知识库、Widget、通知、账户登录。
- 真机未验证；Simulator 与真机的本地网络权限提示不同。
- 默认 IP 为占位值，需按当前 Mac 局域网地址修改；没有自动发现。
- 流式取消会取消本地 Task；服务端负责释放并发槽位。
- UI 自动化测试依赖本机 `127.0.0.1` 临时凭据端点（`ios/scripts/ui-test-credentials.py`），缺少时自动跳过。

## 8. 下一步

1. 用户在 Simulator 中填入自己的成员 Token（旧的无签名安装未保存成功）。
2. 如需真机，配置签名与开发者团队后重复连接/聊天验证。
3. 再决定是否增加记忆/任务页面、Widget 或通知。
