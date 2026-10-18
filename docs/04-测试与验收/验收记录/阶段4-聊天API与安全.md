# 阶段4验收记录：聊天 API 与安全

## 基本信息

| 项目 | 内容 |
|---|---|
| 阶段 | 阶段4：实现聊天 API 与安全保护 |
| 日期 | 2026-10-18 |
| 执行人 | Claude Code + 用户 |
| 环境 | macOS 27.0.1 / M3 16GB；Python 3.12.15；FastAPI 0.143.5；Ollama 0.40.6；qwen3.5:4b |

## 实施内容

新增/修改：

- `src/family_ai_api/config.py`：增加并发数、限流、请求体上限配置。
- `src/family_ai_api/security.py`：Bearer Token 校验，`secrets.compare_digest` 常量时间比较，返回 Token 指纹用于限流键。
- `src/family_ai_api/services/limits.py`：滑动窗口限流。
- `src/family_ai_api/services/ollama_client.py`：异步 httpx 请求、`think: false`、总超时、`trust_env=False`、错误分类。
- `src/family_ai_api/routers/models.py`：`GET /api/v1/models`。
- `src/family_ai_api/routers/chat.py`：`POST /api/v1/chat`，校验、限流、并发信号量、错误映射。
- `src/family_ai_api/main.py`：生命周期初始化、请求体大小检查、访问日志、挂载路由。
- `tests/test_api.py`、`tests/test_ollama_client.py`：接口与上游映射测试。
- `.env.example`：补充并发、限流、请求体配置。

## 执行的命令与真实结果

```bash
uv run pytest -q
```

结果：`24 passed in 0.79s`。

```bash
uv run ruff check .
```

结果：`All checks passed!`。

### 接口验证

| 检查 | 结果 |
|---|---|
| `/api/v1/health` | 200，`{"status":"ok"}` |
| `/api/v1/models` 无 Token | 401 |
| `/api/v1/models` 错误 Token | 401 |
| `/api/v1/models` 正确 Token | 200，`{"default_model":"qwen3.5:4b","models":["qwen3.5:4b"]}` |
| `/api/v1/chat` 无 Token | 401，未调用模型 |
| `/api/v1/chat` 空消息 / 仅空格 | 422 |
| `/api/v1/chat` 超长消息（6001 字符） | 422 |
| `/api/v1/chat` 请求体约 20KB | 413 |
| `/api/v1/chat` 真实模型 | 200，中文回答，3026ms / 1648ms / 1776ms |
| Ollama 不可达（未监听端口） | 503，78ms |
| 日志 | Token 出现 0 次，聊天正文出现 0 次 |

### 真实回答示例

- “请用一句话解释什么是 RAG。” → “RAG（检索增强生成）是一种通过先检索外部知识库中相关的片段，再将其内容输入给大语言模型进行综合生成的混合架构技术……”
- “请写一段 50 字左右的家庭周末活动建议。” → “周末约家人去户外散步或公园野餐，一起动手做顿家常饭，聊聊生活趣事，在欢声笑语中增进感情。”

## 实现过程中发现并修复的问题

1. **思考型模型返回空 `content`**：Qwen3.5 默认把推理放在 `message.thinking`。已在上游请求中设置 `"think": false`。
2. **系统代理接管本地请求**：macOS 系统代理开启时，httpx 默认读取代理设置，未监听端口的请求被代理转成 502（耗时 3.45s）。已设置 `trust_env=False`；修复后同场景返回 503（78ms），并避免聊天内容经过代理。

## 验收清单

- [x] `/api/v1/models` 需要 Token，只返回配置允许的模型。
- [x] `/api/v1/chat` 返回本地模型的实际回答。
- [x] Token 缺失或错误时请求被拒绝，且没有调用模型。
- [x] 空消息、仅空格、超长消息或非法 JSON 被拒绝。
- [x] Ollama 关闭/不可达时，API 在有限时间内返回错误。
- [x] 并发上限与基础限流生效（单元测试覆盖）。
- [x] 日志与错误响应不泄露 Token、配置和聊天全文。
- [x] 测试和静态检查通过。

## 已知问题与限制

- 限流与并发状态保存在单进程内存中；多进程部署需要共享存储（V1 不涉及）。
- 请求体大小检查依赖 `Content-Length`；消息长度与上游限制仍作为兜底。
- 尚未进行局域网访问与连续/并发压力测试（阶段5、6）。

## 安全确认

- [x] 未提交 `.env`、真实 Token、聊天记录或家庭私人资料。
- [x] Token 只从 `Authorization: Bearer` 读取，不放入 URL。
- [x] 日志与错误响应不含 Token、堆栈、路径或聊天正文。
- [x] Ollama 仅监听本机。

## 下一步

- 阶段5：在家庭局域网开放 FastAPI（需用户确认并准备第二台设备验证）。
- 阶段6：性能基线与连续请求稳定性。
