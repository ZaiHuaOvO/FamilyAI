# API 接口规范（V2）

> 状态：**生效（V2 已实现）**  
> 基础地址（本机）：`http://127.0.0.1:8000`  
> 基础地址（局域网）：`http://<Mac局域网IP>:8000`

## 1. 通用约定

### 1.1 协议

- 仅支持 HTTP（V1 局域网内）；后续可评估私有网络或反向代理提供 TLS。
- 请求与响应均为 `application/json; charset=utf-8`。
- 时间单位：毫秒（`duration_ms`）。

### 1.2 认证

除健康检查外，所有接口要求：

```http
Authorization: Bearer <token>
```

- Token 由服务端 `.env` 配置，客户端不得通过 URL 查询参数传递。
- 缺失、格式错误或 Token 不匹配：`401 Unauthorized`。
- 服务端未配置 Token：受保护接口返回 `503`，不降级为匿名访问。

### 1.3 错误格式

采用 FastAPI 标准错误体：

```json
{
  "detail": "unauthorized"
}
```

校验错误（422）可能返回 FastAPI 默认的结构化列表，但不得包含 Token、内部路径、环境变量或异常堆栈。

### 1.4 通用状态码

| 状态码 | 含义 |
|---|---|
| 200 | 成功 |
| 401 | 未认证或 Token 错误 |
| 403 | 认证方案错误 / 禁止访问 |
| 409 | 知识库为空或索引不兼容 |
| 413 | 请求体过大 |
| 422 | 参数校验失败 |
| 429 | 并发或频率超限 |
| 502 | 上游（Ollama）返回错误 |
| 503 | 模型服务不可用 / 服务未配置认证 |
| 504 | 上游超时 |

## 2. `GET /api/v1/health`

用途：判断 API 是否运行。无需认证。

响应 `200`：

```json
{
  "status": "ok"
}
```

要求：

- 不返回版本、模型、配置、路径、进程信息。
- 不触发模型加载。

## 3. `GET /api/v1/models`

用途：返回本服务允许使用的模型。需要 Token。

响应 `200`：

```json
{
  "default_model": "qwen3.5:4b",
  "models": ["qwen3.5:4b"]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `default_model` | string | 默认模型（来自服务端配置） |
| `models` | string[] | 允许使用的模型白名单 |

要求：

- 只返回服务端配置的模型，不返回 Ollama 的全部模型。
- 不返回 Ollama 地址、模型文件路径或内部元数据。

## 4. `POST /api/v1/chat`

用途：将消息发送给本机模型并返回完整回答。需要 Token。

### 4.1 请求

```json
{
  "message": "请解释一下 RAG 是什么。",
  "history": [
    {"role": "user", "content": "上一轮问题"},
    {"role": "assistant", "content": "上一轮回答"}
  ]
}
```

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `message` | string | 是 | 去除首尾空白后非空；长度 ≤ `MAX_MESSAGE_CHARS`（默认 6000） |
| `history` | array | 否 | 历史消息；最多 `MAX_HISTORY_MESSAGES`（默认 20）条，总字符数 ≤ `MAX_HISTORY_CHARS`（默认 12000） |
| `history[].role` | string | 是 | 只能是 `user` 或 `assistant` |
| `history[].content` | string | 是 | 去除首尾空白后非空 |

约束：

- 不接受客户端指定模型、Ollama 地址、`stream`、`system` 等参数。
- 请求体默认上限 16KB（`MAX_REQUEST_BYTES`）。
- 服务端不持久化历史；每次请求由客户端携带所需上下文。
- 服务端对思考型模型关闭思考（`think: false`），只返回最终回答，不返回思考过程。

### 4.2 成功响应 `200`

```json
{
  "message": "RAG 是先检索相关资料，再把资料交给模型生成回答的一种方法。",
  "model": "qwen3.5:4b",
  "duration_ms": 1234
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `message` | string | 模型回答 |
| `model` | string | 实际使用的模型（服务端配置） |
| `duration_ms` | int | 从收到请求到得到上游完整响应的耗时 |

### 4.3 错误响应

| 情况 | 状态码 | 示例 detail |
|---|---|---|
| 无 / 错误 Token | 401 | `unauthorized` |
| 认证未配置 | 503 | `service authentication is not configured` |
| `message` 缺失、空、仅空格 | 422 | `message must not be empty` |
| `message` 超长 | 422 | `message is too long` |
| 历史条数超限 | 422 | `history is too long` |
| 历史总字符超限 | 422 | `history is too large` |
| 历史内容为空 | 422 | `history content must not be empty` |
| 历史角色非法 | 422 | FastAPI 默认结构 |
| 非法 JSON / 类型错误 | 422 | FastAPI 默认结构 |
| 请求体过大 | 413 | `request body too large` |
| 并发已满 | 429 | `too many concurrent requests` |
| 频率超限 | 429 | `rate limit exceeded` |
| Ollama 不可达 | 503 | `model service unavailable` |
| 配置模型不存在 | 502 | `configured model is not available` |
| 上游超时 | 504 | `model request timed out` |
| 其他上游错误 | 502 | `model request failed` |

## 5. `POST /api/v1/chat/stream`

用途：流式返回模型回答。需要 Token。请求体与 `/api/v1/chat` 完全一致（含可选 `history`）。

响应 `200`，类型 `text/event-stream; charset=utf-8`。

### 5.1 事件

| 事件 | data | 说明 |
|---|---|---|
| `delta` | `{"delta": "文本片段"}` | 增量文本，可能多次 |
| `done` | `{"model": "qwen3.5:4b", "duration_ms": 1234}` | 正常结束，含真实生成耗时 |
| `error` | `{"detail": "model service unavailable", "status": 503}` | 流开始后的错误 |

示例：

```text
event: delta
data: {"delta": "家庭"}

event: delta
data: {"delta": "自建"}

event: done
data: {"model": "qwen3.5:4b", "duration_ms": 3449}
```

规则：

- 认证、JSON 格式、消息/历史校验、频率限制失败仍返回普通 HTTP 错误（401/422/429）。
- 流开始后（已发送 200 与响应头），上游错误和并发已满通过 `event: error` 返回。
- 客户端必须处理 `event: error`，不要假定流一定以 `done` 结束。
- 客户端断开时服务端释放并发槽位。

## 6. `GET /api/v1/logs`

用途：查看最近的请求元数据。需要 Token。

### 6.1 请求参数

| 参数 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `limit` | int | 否 | 1～200，默认 50 |

### 6.2 响应 `200`

```json
{
  "entries": [
    {
      "timestamp": "2026-10-18T14:30:00+00:00",
      "method": "POST",
      "path": "/api/v1/chat",
      "status": 200,
      "duration_ms": 593.0,
      "client": "192.168.5.18"
    }
  ]
}
```

- 按时间倒序返回（最新在前）。
- 仅包含元数据；不包含 Token、请求头、查询参数、聊天正文或模型回答。
- 保存在进程内存中，默认最多 200 条，重启后清空。

## 7. `GET /api/v1/logs/view`

用途：请求日志查看页面，无需认证。页面本身不包含任何日志数据；输入 Token 后由浏览器调用 `/api/v1/logs` 获取。

- Token 仅保存在页面内存中，不写入 Cookie、localStorage 或服务端日志。
- 页面通过 `Cache-Control: no-store` 禁止缓存。

## 8. `POST /api/v1/rag/query`

用途：基于本地知识库回答问题，并返回来源。需要 Token。

### 8.1 请求

```json
{
  "message": "默认聊天模型是什么？",
  "top_k": 4
}
```

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `message` | string | 是 | 去除首尾空白后非空；长度 ≤ `MAX_MESSAGE_CHARS` |
| `top_k` | int | 否 | 1～10，默认使用 `KB_TOP_K`（4） |

### 8.2 成功响应 `200`

```json
{
  "answer": "默认聊天模型是 qwen3.5:4b。",
  "model": "qwen3.5:4b",
  "duration_ms": 1500,
  "sources": [
    {
      "title": "Family AI 项目概览",
      "path": "family-ai-overview.md",
      "chunk_index": 0,
      "score": 0.82
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `answer` | string | 基于检索资料生成的回答 |
| `model` | string | 聊天模型 |
| `duration_ms` | int | 模型生成耗时 |
| `sources` | array | 检索到的来源元数据 |
| `sources[].title` | string | 文档标题（首个 Markdown 标题或文件名） |
| `sources[].path` | string | 相对路径，不含绝对路径 |
| `sources[].chunk_index` | int | 片段序号 |
| `sources[].score` | number | 余弦相似度 |

### 8.3 错误

| 情况 | 状态码 | detail |
|---|---|---|
| 无 / 错误 Token | 401 | `unauthorized` |
| 消息为空 / 超长 / top_k 越界 | 422 | 校验错误 |
| 知识库为空 | 409 | `knowledge base is empty` |
| Embedding 服务不可用 | 503 | `embedding service unavailable` |
| 索引维度不兼容 | 409 | `knowledge base index is incompatible; re-index required` |
| 聊天模型不可用 / 超时 | 502/503/504 | 与 `/chat` 相同 |

## 9. `GET /api/v1/kb/stats`

用途：查看知识库统计。需要 Token。

响应 `200`：

```json
{
  "documents": 2,
  "chunks": 5,
  "last_indexed_at": "2026-10-18T15:00:00+00:00",
  "embedding_model": "qwen3-embedding:0.6b"
}
```

- 不返回数据库路径、文档正文或绝对路径。

## 10. 调用示例

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

模型列表：

```bash
curl http://127.0.0.1:8000/api/v1/models \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN'
```

聊天：

```bash
curl http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN' \
  -d '{"message":"请用中文介绍一下你能做什么。"}'
```

流式聊天（`-N` 关闭 curl 缓冲）：

```bash
curl -N http://127.0.0.1:8000/api/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN' \
  -d '{"message":"请用三句话介绍本地大模型的优点。"}'
```

请求日志：

```bash
curl "http://127.0.0.1:8000/api/v1/logs?limit=20" \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN'
```

日志查看页面：<http://127.0.0.1:8000/api/v1/logs/view>

知识库问答：

```bash
curl http://127.0.0.1:8000/api/v1/rag/query \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN' \
  -d '{"message":"默认聊天模型是什么？"}'
```

知识库统计：

```bash
curl http://127.0.0.1:8000/api/v1/kb/stats \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN'
```

> 示例中的 Token 必须替换为本地 `.env` 的真实值；不要把带真实 Token 的命令提交、截图或分享。

## 11. 版本与兼容

- V1 路径固定为 `/api/v1`。
- 新增可选字段不视为破坏性变更；删除字段、改变字段含义或改变认证方式需要新版本路径。
- V1.1 新增可选 `history`、`/chat/stream`、`/logs` 与 `/logs/view`。
- V2 新增 `/rag/query` 与 `/kb/stats`，不改变已有接口契约。
- `/chat` 保持非流式；需要逐字输出时使用 `/chat/stream`。
