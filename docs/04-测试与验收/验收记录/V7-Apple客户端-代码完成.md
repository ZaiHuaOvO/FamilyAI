# V7验收记录：Apple iOS 客户端（代码完成）

## 基本信息

| 项目 | 内容 |
|---|---|
| 版本 | V7（首版代码；未打 `v7.0.0`） |
| 日期 | 2026-11-24 |
| 执行人 | Claude Code + 用户 |
| 平台 | iOS/iPadOS 17+，SwiftUI，Swift 6 |
| 代码位置 | `ios/` |

## 实施内容

- 新增 XcodeGen `project.yml` 与生成的 `FamilyAI.xcodeproj`。
- SwiftUI 聊天界面、消息气泡、输入、清空、停止流式。
- 设置页：服务器地址、成员 Token、流式开关、测试连接。
- `APIClient`：`/me`、`/health`、`/chat`、`/chat/stream` SSE 解析。
- Keychain 保存 Token；UserDefaults 保存地址/开关。
- 客户端携带最近 20 条历史（总字符 ≤ 12000）。
- 401/429/网络/服务端错误提示。
- `Info.plist` 本地网络与 ATS 配置。

## 已验证

```bash
swiftc -parse FamilyAI/*.swift
```

结果：退出码 0（仅语法解析）。

```bash
uv run pytest -q
uv run ruff check .
```

结果：`139 passed`，`All checks passed!`（后端未受影响）。

XcodeGen：

```bash
xcodegen generate
```

结果：成功生成 `FamilyAI.xcodeproj` 与共享 Scheme `FamilyAI`。

## 待用户验证（需要完整 Xcode）

- [ ] Xcode 编译通过（Swift 6 严格并发）。
- [ ] Simulator 启动。
- [ ] 设置 Token 后测试连接成功。
- [ ] 非流式聊天返回真实回答。
- [ ] 流式聊天增量显示并显示 done 耗时。
- [ ] 无 Token/错误 Token 显示 401 提示。
- [ ] 局域网权限提示与 ATS 行为正常。
- [ ] 真机运行（签名）。

## 为什么未完成构建验证

本机只有 Command Line Tools：

```text
xcode-select: error: tool 'xcodebuild' requires Xcode
```

没有 `/Applications/Xcode.app`、`simctl` 或 iOS SDK，因此无法编译/启动 Simulator。已用 Swift 解析器检查语法，但类型检查与运行必须由 Xcode 完成。

## 安全确认

- [x] Token 只存 Keychain，不写 UserDefaults/源码/日志。
- [x] 未开放公网访问。
- [x] ATS 仅允许本地网络，未开启全局 `NSAllowsArbitraryLoads`。
- [x] 客户端不持久化聊天记录。

## 已知限制

- 首版仅聊天核心；无记忆/任务/知识库/Widget/通知。
- 默认服务器地址为占位 IP，需手动修改。
- 代码尚未经过 Xcode 编译与运行验证。

## 下一步

安装 Xcode → 打开 `ios/FamilyAI.xcodeproj` → 完成上述待验证项。
