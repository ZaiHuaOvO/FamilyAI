# V7：Apple iOS 客户端（首版）

> 状态：**代码完成，待 Xcode 构建与真机/模拟器测试（2026-11-24）**  
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
│   └── Assets.xcassets/
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

命令行构建（安装 Xcode 后）：

```bash
xcodebuild -project FamilyAI.xcodeproj -scheme FamilyAI \
  -sdk iphonesimulator -destination 'platform=iOS Simulator,name=iPhone 16' build
```

真机需要配置开发者团队与签名。

## 6. 已验证 / 待验证

已验证：

- XcodeGen 成功生成 `FamilyAI.xcodeproj` 与共享 Scheme。
- `swiftc -parse FamilyAI/*.swift` 通过（语法检查）。
- 后端依赖的 API（chat/stream/me/health）已由 V1.1–V6 验收。
- 139 项后端测试与 ruff 仍通过。

待验证（需要 Xcode）：

- [ ] Xcode 编译（严格并发 `complete`）。
- [ ] iOS Simulator 启动。
- [ ] 设置 Token → 测试连接 → 非流式聊天。
- [ ] 流式聊天增量显示与 done 耗时。
- [ ] 401/429/服务端错误提示。
- [ ] 真机局域网权限与 ATS 行为。

## 7. 已知限制

- 当前开发机没有完整 Xcode，无法本轮编译/运行；代码只做了语法解析。
- 首版不含记忆、任务、知识库、Widget、通知、账户登录。
- 流式取消会取消本地 Task；服务端负责释放并发槽位。
- 默认 IP 为占位值，需按当前 Mac 局域网地址修改。
- 没有自动发现服务器；地址需手动配置。

## 8. 下一步

1. 安装 Xcode，打开 `ios/FamilyAI.xcodeproj`。
2. 配置签名与开发者团队，运行 Simulator/真机。
3. 完成第 6 节的待验证项后，再决定是否增加记忆/任务页面、Widget 或通知。
