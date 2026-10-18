# 阶段2：直接测试 Ollama HTTP API

> 状态：**已完成（2026-10-18）**  
> 前置：阶段1 已完成（Ollama 已安装、模型可对话）  
> 产出：确认 Ollama 本机 API 可用，理解它与 Family AI API 的边界

## 1. 目标

不经过自己编写的任何代码，先用 `curl` 确认 Ollama 的 HTTP API 正常工作。这样后续 FastAPI 出问题时，可以快速判断是 Ollama 还是后端代码的问题。

## 2. 确认服务与监听地址

```bash
curl http://127.0.0.1:11434/api/tags
```

该接口返回本机模型列表。若连接失败：

- 确认 Ollama 应用正在运行。
- 确认端口是 11434。
- 不要为了排查问题把监听地址改为 `0.0.0.0`。

确认只监听本机：

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
```

预期是 `127.0.0.1:11434`（或 IPv6 的 `::1`），不应出现 `*:11434` 或 `0.0.0.0:11434`。

## 3. 测试聊天接口

```bash
curl http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3.5:4b",
    "messages": [
      {"role": "user", "content": "请用中文解释什么是本地大模型。"}
    ],
    "stream": false
  }'
```

预期返回 JSON，其中 `message.content` 包含模型回答，并带有 `model`、耗时等字段。字段细节以实际版本为准。

如果提示模型不存在：

```bash
ollama list
```

用输出中的准确名称替换 `model`。

> `stream: false` 便于查看完整 JSON。V1 后端同样先使用非流式请求。

## 4. 两个服务的边界

```text
Family AI API（你自己写的，默认 8000）
    └── 认证、校验、超时、日志
            ↓ 本机调用
Ollama API（现成的，11434）
    └── 模型加载与推理
```

- 家用设备只访问 FastAPI，不直接访问 Ollama。
- FastAPI 的 Token 认证不能省，因为 Ollama 本身不做家庭访问控制。
- Ollama 的 11434 端口不向局域网或公网开放。

## 5. 本机实测结果（2026-10-18）

| 检查 | 结果 |
|---|---|
| `GET /api/tags` | 200，返回 `qwen3.5:4b`，大小约 4.0GB |
| `POST /api/chat`（`stream:false`） | 200，返回真实中文回答 |
| `lsof -iTCP:11434` | 仅 `127.0.0.1:11434` 监听 |
| 冷启动 | 4.3s（加载 2.2s） |
| 热启动 | 1.7～3.0s |

## 6. 验收

- [x] `/api/tags` 返回模型列表。
- [x] `/api/chat` 返回模型回答。
- [x] 理解 Ollama API 与 Family AI API 是两个服务。
- [x] `lsof` 确认 Ollama 只监听 `127.0.0.1:11434`。

通过后进入[阶段3](阶段3-FastAPI项目搭建.md)（项目骨架已在初始化时完成），或直接进入[阶段4](阶段4-聊天API与安全.md)。
