# V7验收记录：Apple iOS 客户端

> 状态：**通过（Simulator 自动化验证；真机待验证）— 2026-11-24**

## 基本信息

| 项目 | 内容 |
|---|---|
| 版本 | V7（`v7.0.0`） |
| 日期 | 2026-11-24 |
| 执行人 | Claude Code + 用户 |
| 平台 | iOS/iPadOS 17+，SwiftUI，Swift 6 |
| 代码位置 | `ios/` |
| 测试设备 | iPhone 17 Simulator（iOS 27.2） |

## 实施内容

- XcodeGen `project.yml` 与生成的 `FamilyAI.xcodeproj`。
- SwiftUI 聊天界面、消息气泡、输入、清空、停止流式。
- 设置页：服务器地址、成员 Token、流式开关、测试连接。
- `APIClient`：`/me`、`/health`、`/chat`、`/chat/stream` SSE 解析。
- Keychain 保存 Token；UserDefaults 保存地址/开关。
- 客户端携带最近 20 条历史（总字符 ≤ 12000）。
- 401/429/网络/服务端错误提示。
- `Info.plist` 本地网络与 ATS 配置。
- `FamilyAI.entitlements`：`keychain-access-groups`，保证 Simulator/真机可写入 Keychain。
- 单元测试目标 `FamilyAITests`（Keychain 保存/读取/删除）。
- UI 测试目标 `FamilyAIUITests`（连接、流式/非流式聊天、401、重启后 Token 保持）。

## 缺陷与修复

早期“测试连接失败/重启后回到引导页”有两个独立原因：

1. FastAPI 服务当时未运行，客户端报 `NSURLErrorDomain -1004`（连接被拒绝）。
2. 首次安装包使用 `CODE_SIGNING_ALLOWED=NO` 构建，未嵌入 Keychain 权限，Token 写入失败，重启后设置丢失。

修复：

- 启动后端服务后，健康检查在 `127.0.0.1` 与 `192.168.5.18` 均返回 200。
- 增加 `FamilyAI.entitlements` 并在 `project.yml` 设置 `CODE_SIGN_ENTITLEMENTS`；
  Simulator 构建的 `FamilyAI.app-Simulated.xcent` 已包含
  `keychain-access-groups = FAKETEAMID.com.familyai.app`。
- Debug 配置启用 `ENABLE_TESTABILITY`，测试目标补 `BUNDLE_LOADER`，使 `@testable import FamilyAI` 可链接。

## 测试命令与真实结果

后端未改动；此前结果 `139 passed`、`ruff All checks passed!` 仍有效。

Keychain 单元测试：

```bash
cd ios
xcodegen generate
xcodebuild test -project FamilyAI.xcodeproj -scheme FamilyAI \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath /tmp/FamilyAI-DerivedData \
  -only-testing:FamilyAITests
```

结果：`KeychainStoreTests.testSaveReadDelete` 通过（0.026s），`** TEST SUCCEEDED **`。

端到端 UI 测试：

```bash
xcodebuild test -project FamilyAI.xcodeproj -scheme FamilyAI \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath /tmp/FamilyAI-DerivedData \
  -only-testing:FamilyAIUITests/FamilyAIUITests/testConnectChatAndPersist
```

结果：`testConnectChatAndPersist` 通过（81.3s），`** TEST SUCCEEDED **`。用例实际完成：

1. 全新安装后进入设置，输入局域网地址与临时成员 Token。
2. “测试连接”返回 `已连接：<成员名>（member/…）`。
3. 流式聊天：收到真实增量回复（默认流式）。
4. 关闭流式开关后再次聊天：非流式接口返回真实回复。
5. 输入无效 Token：显示“Token 无效或已被撤销”的 401 提示；恢复 Token 后重新连接成功。
6. 结束进程并重新启动：不再显示引导页，Token 从 Keychain 恢复，连接状态为已连接。
7. 全程未出现“网络错误”提示。

测试凭据处理：

- 临时成员由 CLI 创建，测试结束后全部撤销（`uitest-*` 无 active 项）。
- Token 仅通过 `127.0.0.1` 的临时测试端点交给 UI 测试进程；助手脚本位于
  `ios/scripts/ui-test-credentials.py`，从环境变量读取 Token，不写盘。
- Token 未写入源码、文档、日志或提交记录。

## 已验证清单

- [x] Xcode 编译通过（Swift 6 严格并发）。
- [x] Simulator 安装并启动。
- [x] 设置 Token 后测试连接成功。
- [x] 非流式聊天返回真实回答。
- [x] 流式聊天返回真实增量回复。
- [x] 无 Token/错误 Token 显示 401 提示。
- [x] Keychain 跨进程重启保持 Token。
- [x] 局域网 HTTP 访问正常（ATS 未拦截）。

## 未验证 / 已知限制

- 真机签名、开发者团队、真机局域网权限与 ATS 未验证。
- 429 限流的客户端提示未在 UI 中构造验证；后端已有覆盖。
- 首版仅聊天核心；无记忆/任务/知识库/Widget/通知。
- 默认服务器地址为占位 IP，需手动修改；无自动发现。
- 客户端不持久化聊天记录。

## 安全确认

- [x] Token 只存 Keychain，不写 UserDefaults/源码/日志。
- [x] 未开放公网访问。
- [x] ATS 仅允许本地网络，未开启全局 `NSAllowsArbitraryLoads`。
- [x] 客户端不持久化聊天记录。
- [x] 测试成员已全部撤销。

## 下一步

1. 用户在 Simulator 中把自己的成员 Token 重新填入设置（旧安装未保存成功）。
2. 如需真机：配置开发者团队与签名后重复上述连接/聊天验证。
3. 再决定是否增加记忆/任务页面、Widget 或通知。
