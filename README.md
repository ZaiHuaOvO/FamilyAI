# Family AI

家庭局域网内使用的本地大模型服务。Mac 本机通过 [Ollama](https://ollama.com/) 运行模型，[FastAPI](https://fastapi.tiangolo.com/) 提供带访问令牌的统一 HTTP API。

> 当前状态：**V6 已完成（`v6.0.0`）**；**V7 iOS 客户端已编译并在 Simulator 启动，待 Token/聊天手动验证**。后续规划见 [路线图](docs/05-路线图/后续路线图.md)。

## 能力

- Mac 本机运行本地开源大模型并对话。
- 通过带 Token 认证的 HTTP API 调用模型。
- 非流式与 SSE 流式聊天。
- 客户端携带多轮对话历史（服务端不持久化）。
- 请求日志查询接口与查看页面（只记录元数据，仅 admin 可读）。
- 本地 Markdown/TXT 知识库问答（返回来源）。
- 长期记忆：私有/共享；显式新增/编辑/删除 + 自动提取。
- 家庭任务：私有/共享、CRUD、今日/逾期筛选、手动简报、可选天气、管理页面。
- 工具调用：只读工具自动执行；写工具需要 API 二次确认。
- 多成员 Token；成员管理使用 CLI；记忆与任务按成员隔离。
- 家庭 Wi-Fi 内设备可访问 FastAPI，Ollama 端口只监听本机。

不包含：客户端 App、外部向量数据库（当前为 Ollama Embedding + SQLite + numpy）、主动提醒、公网访问。

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

# 3. 启动服务（监听地址与端口读取 .env 的 APP_HOST / APP_PORT）
uv run python -m family_ai_api
```

开发时可使用热重载（会覆盖 `.env` 的监听配置）：

```bash
uv run uvicorn family_ai_api.main:app --reload --host 127.0.0.1 --port 8000
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
| GET | `/api/v1/me` | 当前成员 | 是 |
| GET | `/api/v1/models` | 服务允许的模型 | 是 |
| POST | `/api/v1/chat` | 非流式聊天，可带 `history` | 是 |
| POST | `/api/v1/chat/stream` | SSE 流式聊天 | 是 |
| GET | `/api/v1/logs` | 最近请求元数据（仅 admin） | 是 |
| GET | `/api/v1/logs/view` | 日志查看页面 | 页面可访问，数据需 admin Token |
| POST | `/api/v1/rag/query` | 知识库问答，返回来源 | 是 |
| GET | `/api/v1/kb/stats` | 知识库文档/片段统计 | 是 |
| POST | `/api/v1/memory` | 新增记忆 | 是 |
| GET | `/api/v1/memory` | 记忆列表/搜索 | 是 |
| PATCH | `/api/v1/memory/{memory_id}` | 修改记忆 | 是 |
| DELETE | `/api/v1/memory/{memory_id}` | 删除记忆 | 是 |
| GET | `/api/v1/memory/view` | 记忆管理页面 | 页面可访问，数据需 Token |
| POST | `/api/v1/tasks` | 新建任务 | 是 |
| GET | `/api/v1/tasks` | 任务列表/筛选 | 是 |
| PATCH | `/api/v1/tasks/{task_id}` | 修改/完成任务 | 是 |
| DELETE | `/api/v1/tasks/{task_id}` | 删除任务 | 是 |
| GET | `/api/v1/tasks/view` | 任务管理页面 | 页面可访问，数据需 Token |
| GET | `/api/v1/briefing` | 今日/逾期简报 + 可选天气 | 是 |
| POST | `/api/v1/agent/chat` | 工具规划与回答 | 是 |
| GET | `/api/v1/agent/tools` | 白名单工具 | 是 |
| GET | `/api/v1/agent/audit` | 工具调用审计（仅 admin） | 是 |
| POST | `/api/v1/agent/actions/{action_id}/confirm` | 确认写操作 | 是 |
| POST | `/api/v1/agent/actions/{action_id}/cancel` | 取消写操作 | 是 |

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

成员管理（Token 只打印一次；现有 `.env` Token 首次启动映射为 admin）：

```bash
uv run python -m family_ai_api.members.cli create --name alice --role member
uv run python -m family_ai_api.members.cli list
uv run python -m family_ai_api.members.cli rotate --name alice
uv run python -m family_ai_api.members.cli revoke --name alice
```

## iOS 客户端

`ios/` 包含 SwiftUI iOS/iPadOS 聊天客户端（V7 首版），支持 Keychain Token、非流式/流式聊天与历史。完整构建需要 Xcode：

```bash
cd ios
xcodegen generate
open FamilyAI.xcodeproj
```

详见 [ios/README.md](ios/README.md)。

可选天气：在 `.env` 中设置 `WEATHER_LATITUDE`、`WEATHER_LONGITUDE` 与 `WEATHER_LOCATION_NAME`，简报会使用 Open-Meteo 获取天气；留空即禁用。

工具调用：只读工具自动执行；`create_task`、`complete_task`、`add_memory` 会先返回 `pending_action`，需调用 `/api/v1/agent/actions/{action_id}/confirm` 才会执行。写工具可用 `AGENT_WRITE_TOOLS_ENABLED=false` 关闭。

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
- [V5 工具调用](docs/02-实施阶段/V5-工具调用.md)
- [V6 家庭成员权限](docs/02-实施阶段/V6-家庭成员权限.md)
- [V7 Apple 客户端（代码完成）](docs/02-实施阶段/V7-Apple客户端.md)
- [iOS 客户端说明](ios/README.md)
- [API 接口规范](docs/03-设计与规范/API接口规范.md)
- [原始开发指南（归档）](docs/00-归档/原始开发文档-V1.1.md)

## 安全约定

- `.env`、真实 Token、私人聊天记录和家庭文件不得提交到 Git。
- 对局域网提供服务的唯一入口是 FastAPI；不要暴露 Ollama 的 11434 端口。
- 不在 URL 查询参数中传递 Token。
