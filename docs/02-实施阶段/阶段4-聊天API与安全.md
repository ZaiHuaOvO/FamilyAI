# 阶段4：实现聊天 API 与安全保护

> 状态：**待开始**  
> 前置：阶段1、2 完成（Ollama 与模型可用），阶段3 完成（FastAPI 骨架）  
> 产出：`GET /api/v1/models`、`POST /api/v1/chat`，Token 认证、输入校验、超时、并发与限流

## 1. 目标

把本机 Ollama 包装成安全的家庭 API。所有聊天请求必须经过：

1. Token 认证；
2. 消息格式与长度校验；
3. 超时与并发保护；
4. 明确的错误映射；
5. 不泄露密钥与聊天正文的日志。

V1 只做非流式请求，不保存对话历史。

## 2. 配置

### 2.1 `.env`（不提交 Git）

```dotenv
APP_HOST=127.0.0.1
APP_PORT=8000
OLLAMA_BASE_URL=http://127.0.0.1:11434
AI_MODEL=qwen3.5:4b
API_ACCESS_TOKEN=请替换为真正的随机长密钥
REQUEST_TIMEOUT_SECONDS=180
MAX_MESSAGE_CHARS=6000
```

阶段4 新增配置建议：

```dotenv
MAX_CONCURRENT_REQUESTS=2
RATE_LIMIT_PER_MINUTE=30
MAX_REQUEST_BYTES=16384
```

### 2.2 生成 Token

```bash
openssl rand -hex 32
```

把结果写入本地 `.env`，不要发给 AI、不要写进 README、日志、截图或 Git 提交。

### 2.3 配置读取

- 服务只从 `config.Settings` 读取模型名、Ollama 地址和 Token。
- 客户端不能指定模型名或 Ollama 地址。
- `API_ACCESS_TOKEN` 为空时，聊天接口必须拒绝服务（可以启动，但所有受保护请求返回 503/401），不允许“未配置即放行”。

## 3. 接口设计

| 方法 | 路径 | 用途 | 认证 |
|---|---|---|---|
| `GET` | `/api/v1/health` | 仅返回服务是否运行 | 否，返回内容最小化 |
| `GET` | `/api/v1/models` | 返回本服务允许使用的模型 | 是 |
| `POST` | `/api/v1/chat` | 请求 Ollama 并返回回答 | 是 |

### 3.1 认证方式

```http
Authorization: Bearer <token>
```

- 使用 FastAPI 依赖集中校验。
- 使用 `secrets.compare_digest` 做常量时间比较。
- 缺失或错误 Token：返回 `401`；Token 中无 `Bearer` 方案时返回 `401`/`403`。不得继续调用模型。

### 3.2 `GET /api/v1/models`

响应示例：

```json
{
  "default_model": "qwen3.5:4b",
  "models": ["qwen3.5:4b"]
}
```

只返回服务端允许的模型，不把 Ollama 全部模型或内部地址暴露给客户端。

### 3.3 `POST /api/v1/chat`

请求：

```json
{
  "message": "请解释一下 RAG 是什么。"
}
```

成功响应：

```json
{
  "message": "RAG 是先检索相关资料，再把资料交给模型生成回答的一种方法。",
  "model": "qwen3.5:4b",
  "duration_ms": 1234
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `message` | string | 模型实际返回内容 |
| `model` | string | 服务端配置的模型名 |
| `duration_ms` | int | 本次请求实际耗时（毫秒） |

## 4. 内部流程

```text
客户端 POST /api/v1/chat
    ↓
依赖：校验 Bearer Token（常量时间比较）
    ↓
Pydantic：message 非空、去除空白后非空、长度 ≤ MAX_MESSAGE_CHARS
    ↓
请求体大小检查（Content-Length / 中间件）
    ↓
基础限流（每客户端每分钟请求数）
    ↓
并发信号量（同时最多 N 个模型请求，超出返回 429）
    ↓
httpx.AsyncClient 请求 {OLLAMA_BASE_URL}/api/chat
    - stream=false
    - 总超时 REQUEST_TIMEOUT_SECONDS
    ↓
解析响应 message.content
    ↓
返回 {message, model, duration_ms}
```

## 5. 安全实现要求

### 5.1 Token

- 只在 Header 中接收，不从 URL 查询参数读取。
- 不记录 Token；错误响应不包含 Token。
- 比较使用常量时间函数。
- `.env` 被 `.gitignore` 忽略；提交前检查 `git diff --cached`。

### 5.2 输入校验

- `message` 必须是非空字符串；仅空格的输入也拒绝。
- 长度上限来自配置 `MAX_MESSAGE_CHARS`（默认 6000）。
- 非法 JSON / 错误字段类型由 FastAPI 返回 `422`。
- 请求体上限默认 16KB，防止超大 body。
- 不接受客户端传入 `model`、`system`、Ollama 地址等字段（多余字段忽略，不参与调用）。

### 5.3 资源保护

| 保护 | 建议值 | 行为 |
|---|---|---|
| 上游超时 | 180s（可配置） | 超时返回 `504`，不无限等待 |
| 并发上限 | 2 | 同时最多 2 个模型请求，超出立即 `429` |
| 基础限流 | 30 次/分钟 | 单进程内存计数；超出 `429` |
| 消息长度 | 6000 字符 | 超出 `422` |
| 请求体 | 16KB | 超出 `413` |

V1 单进程运行，限流使用内存计数即可；多进程部署时需要换成共享存储（不在 V1 范围）。

### 5.4 日志

只记录：

- 时间、HTTP 方法、路由、状态码、耗时；
- 错误类型摘要（如 `ollama_unavailable`、`timeout`）。

不记录：

- `Authorization` Header、Token；
- 完整聊天正文（可记录字符数，不记录内容）；
- 环境变量、异常堆栈、文件路径。

### 5.5 错误响应

- 统一返回 FastAPI 的 `{"detail": "..."}`，内容可读但不泄露内部信息。
- 不返回异常堆栈、系统路径、环境变量、上游原始响应全文。
- 详细异常只写服务端日志（不含敏感内容）。

### 5.6 错误映射

| 情况 | 状态码 | detail（建议） |
|---|---|---|
| 缺少 / 错误 Token | 401 | `unauthorized` |
| message 为空 / 仅空格 | 422 | `message must not be empty` |
| message 超长 | 422 | `message is too long` |
| 非法 JSON / 类型错误 | 422 | FastAPI 默认校验错误 |
| 请求体过大 | 413 | `request body too large` |
| 并发已满 | 429 | `too many concurrent requests` |
| 请求频率超限 | 429 | `rate limit exceeded` |
| Ollama 无法连接 | 503 | `model service unavailable` |
| 模型不存在 | 502 | `configured model is not available` |
| 上游超时 | 504 | `model request timed out` |
| 其他上游错误 | 502 | `model request failed` |
| 服务端未配置 Token | 503 | `service authentication is not configured` |

## 6. 测试要求

优先把 HTTP 层与 Ollama 解耦，用 mock 覆盖大部分场景，不每次加载模型。

### 6.1 单元 / 接口测试（mock）

- 健康检查返回 200。
- `/models` 无 Token → 401；正确 Token → 返回配置的模型。
- `/chat` 无 Token / 错误 Token → 401，且不调用上游。
- 空字符串、仅空格、超长消息 → 422。
- 非法 JSON → 422。
- 正常请求 → 200，返回 mock 的 `message`、`model`、`duration_ms`。
- Ollama 连接失败 → 503。
- 上游超时 → 504。
- 并发超出 → 429。
- 日志中不含 Token 与消息正文（可用 caplog 检查）。

### 6.2 集成测试（少量）

- 真实 Ollama 已启动、模型已下载时，调用 `/api/v1/chat` 返回真实回答。
- Ollama 停止时，API 在超时时间内返回 503/504，而不是挂起。

### 6.3 本机 curl 验证

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

无 Token 应被拒绝：

```bash
curl -i http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"你好"}'
```

带 Token（替换为真实值，不要提交该命令）：

```bash
curl http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN' \
  -d '{"message":"请用中文介绍一下你能做什么。"}'
```

静态检查与测试：

```bash
uv run pytest
uv run ruff check .
```

## 7. 验收

- [ ] `/api/v1/models` 需要 Token，只返回配置允许的模型。
- [ ] `/api/v1/chat` 返回本地模型的实际回答。
- [ ] Token 缺失或错误时请求被拒绝，且没有调用模型。
- [ ] 空消息、仅空格、超长消息或非法 JSON 被拒绝。
- [ ] Ollama 关闭时，API 在有限时间内返回错误，而不是无限等待。
- [ ] 并发上限与基础限流生效。
- [ ] 日志与错误响应不泄露 Token、配置和聊天全文。
- [ ] 测试和静态检查通过。
- [ ] 已完成阶段验收记录。

## 8. 下一阶段

[阶段5：局域网开放](阶段5-局域网开放.md)。必须先确认本阶段的认证与输入校验全部通过。
