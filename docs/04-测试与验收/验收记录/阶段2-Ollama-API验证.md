# 阶段2验收记录：Ollama HTTP API 验证

## 基本信息

| 项目 | 内容 |
|---|---|
| 阶段 | 阶段2：直接测试 Ollama HTTP API |
| 日期 | 2026-10-18 |
| 执行人 | Claude Code + 用户 |
| 模型 | `qwen3.5:4b` |

## 执行的命令与真实结果

```bash
curl http://127.0.0.1:11434/api/tags
```

结果：HTTP 200，返回 `qwen3.5:4b`，大小约 4.0GB。

```bash
curl http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.5:4b","messages":[{"role":"user","content":"请用一句话解释什么是本地大模型。"}],"stream":false,"think":false}'
```

结果：HTTP 200，返回中文回答：

> 本地大模型是指用户在自己的私人服务器、个人电脑等硬件设备上独立部署和运行的 AI 大语言模型，数据完全不经过云端传输或第三方处理。

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
```

结果：仅 `127.0.0.1:11434` 监听，无 `0.0.0.0` 或 `*`。

## 测试结果

| 检查项 | 结果 | 备注 |
|---|---|---|
| `/api/tags` | 200 | 模型列表正常 |
| `/api/chat` | 200 | 返回真实回答 |
| 冷启动 | 4.3s | 加载 2.2s |
| 热启动 | 1.7～3.0s | |
| 监听地址 | `127.0.0.1:11434` | 未对外暴露 |

## 验收清单

- [x] `/api/tags` 返回模型列表。
- [x] `/api/chat` 返回模型回答。
- [x] 理解 Ollama API 与 Family AI API 是两个服务。
- [x] `lsof` 确认 Ollama 只监听 `127.0.0.1:11434`。

## 已知问题与限制

- `qwen3.5:4b` 是思考型模型；测试时使用 `"think": false` 直接获取答案。
- 本机系统代理会影响 httpx 请求（阶段4已用 `trust_env=False` 处理）。

## 安全确认

- [x] Ollama 未开放给局域网或公网。
- [x] 未在请求中传递真实 Token（本阶段直连 Ollama，不使用项目 Token）。

## 下一步

- 阶段4：通过 FastAPI 调用模型并加入认证与保护（已完成）。
