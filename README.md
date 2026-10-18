# Family AI

家庭局域网内使用的本地大模型服务。Mac 本机通过 [Ollama](https://ollama.com/) 运行模型，[FastAPI](https://fastapi.tiangolo.com/) 提供带访问令牌的统一 HTTP API。

> 当前状态：**V1 已完成（`v1.0.0`）**——本机模型、带 Token 的聊天 API、安全保护与家庭局域网访问均已验证。后续规划见 [路线图](docs/05-路线图/后续路线图.md)。

## 目标（V1）

- Mac 本机运行本地开源大模型并对话。
- 通过带 Token 认证的 HTTP API 调用模型。
- 家庭 Wi-Fi 内设备可访问 FastAPI，Ollama 端口只监听本机。
- 具备基础测试、日志、错误处理与文档。

V1 不包含：客户端 App、RAG/向量库、长期记忆、主动提醒、公网访问。

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

# 3. 启动开发服务
uv run uvicorn family_ai_api.main:app --reload --host 127.0.0.1 --port 8000
```

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- 接口文档：<http://127.0.0.1:8000/docs>

## 测试与检查

```bash
uv run pytest
uv run ruff check .
```

## 文档

- [文档库索引](docs/README.md)
- [进度追踪](docs/进度追踪.md)
- [原始开发指南（归档）](docs/00-归档/原始开发文档-V1.1.md)

## 安全约定

- `.env`、真实 Token、私人聊天记录和家庭文件不得提交到 Git。
- 对局域网提供服务的唯一入口是 FastAPI；不要暴露 Ollama 的 11434 端口。
- 不在 URL 查询参数中传递 Token。
