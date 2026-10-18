# 阶段3验收记录：FastAPI 项目搭建

## 基本信息

| 项目 | 内容 |
|---|---|
| 阶段 | 阶段3：创建 FastAPI 项目 |
| 日期 | 2026-10-18 |
| 执行人 | Claude Code + 用户 |
| 代码版本 | 首次阶段提交（阶段3） |
| 环境 | macOS 27.0.1 / arm64 / M3 16GB；Python 3.12.15；uv 0.13.1；FastAPI 0.143.5；ruff 0.17.1；pytest 9.1.1 |
| Ollama | 未安装（本阶段不依赖） |

## 实施内容

- 使用 `uv init --app --python 3.12 --name family-ai-api` 初始化项目。
- 安装 `fastapi[standard]`、`httpx`、`pydantic-settings`；开发依赖 `pytest`、`pytest-asyncio`、`ruff`。
- 新增 `src/family_ai_api/config.py`：集中读取 `.env` 配置。
- 新增 `src/family_ai_api/main.py`：应用工厂 + 路由挂载。
- 新增 `src/family_ai_api/routers/health.py`：`GET /api/v1/health`。
- 新增 `tests/test_health.py`：健康检查测试。
- 更新 `pyproject.toml`：项目描述、pytest/ruff 配置，移除无效的脚本入口。
- 新增 `README.md`、`AGENTS.md`、`CLAUDE.md`、`.env.example`；更新 `.gitignore`。
- 建立文档库并归档原始开发文档。

## 执行的命令与真实结果

```bash
uv add "fastapi[standard]" httpx pydantic-settings
```

结果：Resolved 62 packages；Created virtual environment at `.venv`（Python 3.12.15）。

```bash
uv add --dev pytest pytest-asyncio ruff
```

结果：Resolved 68 packages；安装 pytest 9.1.1、pytest-asyncio 1.4.0、ruff 0.17.1。

```bash
uv run pytest -q
```

结果：`1 passed in 1.00s`。

```bash
uv run ruff check .
```

结果：`All checks passed!`。

```bash
uv run uvicorn family_ai_api.main:app --host 127.0.0.1 --port 8000
```

结果：`Application startup complete`；`Uvicorn running on http://127.0.0.1:8000`。

## 测试结果

| 检查项 | 命令 | 结果 | 备注 |
|---|---|---|---|
| 单元测试 | `uv run pytest -q` | 1 passed | `tests/test_health.py` |
| 静态检查 | `uv run ruff check .` | All checks passed | |
| 健康检查 | `curl http://127.0.0.1:8000/api/v1/health` | 200，`{"status":"ok"}` | |
| 接口文档 | `curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/docs` | 200 | |
| OpenAPI | `curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/openapi.json` | 200 | |

## 验收清单

- [x] 项目能通过 `uv` 安装依赖。
- [x] `uv.lock` 已生成。
- [x] FastAPI 服务可启动。
- [x] 健康检查接口可访问。
- [x] `/docs` 能显示接口定义。
- [x] Ollama 调用代码未与路由混在一起（本阶段未引入）。

## 已知问题与限制

- Ollama 与本地模型尚未安装，聊天接口不可用（阶段1、2、4）。
- 受保护接口（`/models`、`/chat`）尚未实现。
- 本阶段未进行局域网测试。

## 安全确认

- [x] 未提交 `.env`、真实 Token、聊天记录或家庭私人资料。
- [x] 未开放 Ollama 端口或公网访问（Ollama 未安装）。
- [x] 健康检查只返回 `{"status":"ok"}`，不泄露配置。
- [x] `.env` 已加入 `.gitignore`。

## 下一步

- 阶段1：安装 Ollama，下载并验证 `qwen3.5:4b`。
- 阶段2：用 `curl` 验证 Ollama HTTP API。
- 阶段4：实现聊天接口与安全保护。
