# Family AI 项目概览

Family AI 是一个家庭局域网内使用的本地大模型服务。FastAPI 提供带 Token 认证的 HTTP API，Ollama 负责模型推理。

## 默认模型

默认聊天模型是 `qwen3.5:4b`，默认 Embedding 模型是 `qwen3-embedding:0.6b`。

## 主要接口

- `GET /api/v1/health`：健康检查，不需要 Token。
- `GET /api/v1/models`：返回服务允许的模型，需要 Token。
- `POST /api/v1/chat`：非流式聊天，可携带 `history`。
- `POST /api/v1/chat/stream`：SSE 流式聊天。
- `POST /api/v1/rag/query`：基于知识库回答问题。
- `GET /api/v1/logs`：查看最近的请求元数据，需要 Token。

## 网络与安全

FastAPI 默认监听 8000 端口；Ollama 只监听本机 `127.0.0.1:11434`。

家庭局域网内的设备必须携带 Bearer Token。V1.1 不在服务端保存聊天历史，历史由客户端在每次请求中携带。
