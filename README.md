# Family AI

家庭局域网内使用的本地大模型服务。Mac 本机通过 [Ollama](https://ollama.com/) 运行模型，[FastAPI](https://fastapi.tiangolo.com/) 提供带访问令牌的统一 HTTP API。

> 当前状态：**V4 已完成（`v4.0.0`）**——本地模型、流式聊天、对话历史、请求日志、知识库/RAG、长期记忆与家庭任务/简报均已验证。后续规划见 [路线图](docs/05-路线图/后续路线图.md)。

## 能力

- Mac 本机运行本地开源大模型并对话。
- 通过带 Token 认证的 HTTP API 调用模型。
- 非流式与 SSE 流式聊天。
- 客户端携带多轮对话历史（服务端不持久化）。
- 请求日志查询接口与查看页面（只记录元数据）。
- 本地 Markdown/TXT 知识库问答（返回来源）。
- 长期记忆：显式新增/编辑/删除 + 自动提取；聊天默认不使用，需 `use_memory: true`。
- 家庭任务：CRUD、今日/逾期筛选、手动简报、可选天气、管理页面。
- 家庭 Wi-Fi 内设备可访问 FastAPI，Ollama 端口只监听本机。

不包含：客户端 App、RAG/向量库、长期记忆、主动提醒、公网访问。

## 架构

```text
iPhone / iPad / 家庭内其他电脑
              │ HTTP + API Token
              ▼
     FastAPI（本项目）
     认证 · 校验 · 超时 · 限流 · 日志
              │ 仅本机
              ▼
     Ollama 127.0.0.1:11434
              ▼
     本地开源大模型
```

## 快速开始

```bash
# 1. 安装依赖（需要 uv）
uv sync

# 2. 配置本地环境变量
cp .env.example .env
# 编辑 .env，至少替换 API_ACCESS_TOKEN

# 3. 启动服务（本机开发用 127.0.0.1；局域网访问用 0.0.0.0）
uv run uvicorn family_ai_api.main:app --host 0.0.0.0 --port 8000
```

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- 接口文档：<http://127.0.0.1:8000/docs>
- 请求日志页面：<http://127.0.0.1:8000/api/v1/logs/view>
- 记忆管理页面：<http://127.0.0.1:8000/api/v1/memory/view>
- 任务管理页面：<http://127.0.0.1:8000/api/v1/tasks/view>

## API 概览

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| GET | `/api/v1/health` | 健康检查 | 否 |
| GET | `/api/v1/models` | 服务允许的模型 | 是 |
| POST | `/api/v1/chat` | 非流式聊天，可带 `history` | 是 |
| POST | `/api/v1/chat/stream` | SSE 流式聊天 | 是 |
| GET | `/api/v1/logs` | 最近请求元数据 | 是 |
| GET | `/api/v1/logs/view` | 日志查看页面 | 页面可访问，数据需 Token |
| POST | `/api/v1/rag/query` | 知识库问答，返回来源 | 是 |
| GET | `/api/v1/kb/stats` | 知识库文档/片段统计 | 是 |
| POST | `/api/v1/memory` | 新增记忆 | 是 |
| GET | `/api/v1/memory` | 记忆列表/搜索 | 是 |
| PATCH | `/api/v1/memory/{id}` | 修改记忆 | 是 |
| DELETE | `/api/v1/memory/{id}` | 删除记忆 | 是 |
| GET | `/api/v1/memory/view` | 记忆管理页面 | 页面可访问，数据需 Token |
| POST | `/api/v1/tasks` | 新建任务 | 是 |
| GET | `/api/v1/tasks` | 任务列表/筛选 | 是 |
| PATCH | `/api/v1/tasks/{id}` | 修改/完成任务 | 是 |
| DELETE | `/api/v1/tasks/{id}` | 删除任务 | 是 |
| GET | `/api/v1/tasks/view` | 任务管理页面 | 页面可访问，数据需 Token |
| GET | `/api/v1/briefing` | 今日/逾期简报 + 可选天气 | 是 |

流式调用示例：

```bash
curl -N http://127.0.0.1:8000/api/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_REAL_TOKEN' \
  -d '{"message":"请用三句话介绍本地大模型的优点。"}'
```

知识库索引（只索引显式指定的 Markdown/TXT）：

```bash
uv run python -m family_ai_api.knowledge.ingest knowledge.example
```

> 真实资料目录 `knowledge/` 与索引 `data/` 已被 `.gitignore` 忽略；示例资料在 `knowledge.example/`。

可选天气：在 `.env` 中设置 `WEATHER_LATITUDE`、`WEATHER_LONGITUDE` 与 `WEATHER_LOCATION_NAME`，简报会使用 Open-Meteo 获取天气；不设置则只返回任务。

## 测试与检查

```bash
uv run pytest
uv run ruff check .
```

## 文档

- [文档库索引](docs/README.md)
- [进度追踪](docs/进度追踪.md)
- [V1.1 调用体验](docs/02-实施阶段/V1.1-调用体验.md)
- [V2 知识库/RAG](docs/02-实施阶段/V2-知识库RAG.md)
- [V3 长期记忆](docs/02-实施阶段/V3-长期记忆.md)
- [V4 家庭任务与提醒](docs/02-实施阶段/V4-家庭任务与提醒.md)
- [API 接口规范](docs/03-设计与规范/API接口规范.md)
- [原始开发指南（归档）](docs/00-归档/原始开发文档-V1.1.md)

## 安全约定

- `.env`、真实 Token、私人聊天记录和家庭文件不得提交到 Git。
- 对局域网提供服务的唯一入口是 FastAPI；不要暴露 Ollama 的 11434 端口。
- 不在 URL 查询参数中传递 Token。
