# API 接口规范（V1）

> 状态：**生效（阶段3部分实现；阶段4完成后全部生效）**  
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

用途：将单轮消息发送给本机模型并返回回答。需要 Token。

### 4.1 请求

```json
{
  "message": "请解释一下 RAG 是什么。"
}
```

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `message` | string | 是 | 去除首尾空白后非空；长度 ≤ `MAX_MESSAGE_CHARS`（默认 6000） |

约束：

- 不接受客户端指定模型、Ollama 地址、`stream`、`system` 等参数。
- 请求体默认上限 16KB（`MAX_REQUEST_BYTES`）。
- V1 不保存历史，不提供多轮上下文；客户端如需多轮，需自行拼接后作为单条消息发送（后续版本再设计）。
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
| 非法 JSON / 类型错误 | 422 | FastAPI 默认结构 |
| 请求体过大 | 413 | `request body too large` |
| 并发已满 | 429 | `too many concurrent requests` |
| 频率超限 | 429 | `rate limit exceeded` |
| Ollama 不可达 | 503 | `model service unavailable` |
| 配置模型不存在 | 502 | `configured model is not available` |
| 上游超时 | 504 | `model request timed out` |
| 其他上游错误 | 502 | `model request failed` |

## 5. 调用示例

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

> 示例中的 Token 必须替换为本地 `.env` 的真实值；不要把带真实 Token 的命令提交、截图或分享。

## 6. 版本与兼容

- V1 路径固定为 `/api/v1`。
- 新增可选字段不视为破坏性变更；删除字段、改变字段含义或改变认证方式需要新版本路径。
- V1 不提供流式响应；后续若增加，将以可选参数或新接口形式引入。
