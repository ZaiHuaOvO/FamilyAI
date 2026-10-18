# 阶段3：创建 FastAPI 项目

> 状态：**已完成（2026-10-18）**  
> 前置：阶段0 已完成  
> 产出：可启动的最小 FastAPI 服务、健康检查、自动 OpenAPI 文档、基础测试

## 1. 目标

建立职责清晰的 Python 项目骨架，只实现健康检查，验证“依赖安装 → 启动 → 测试 → 文档”链路。聊天与认证留到阶段4，避免一次生成整套系统。

## 2. 实施步骤（已执行）

### 2.1 初始化项目

```bash
uv init --app --python 3.12 --name family-ai-api
uv add "fastapi[standard]" httpx pydantic-settings
uv add --dev pytest pytest-asyncio ruff
```

实际环境：

- Python 3.12.15（uv 管理）
- FastAPI 0.143.5、httpx 0.28.1、pydantic-settings 2.16.0
- pytest 9.1.1、pytest-asyncio 1.4.0、ruff 0.17.1

### 2.2 模块职责

| 文件 | 职责 |
|---|---|
| `src/family_ai_api/main.py` | 创建 `FastAPI` 应用，挂载路由 |
| `src/family_ai_api/config.py` | 用 `pydantic-settings` 读取 `.env` / 环境变量 |
| `src/family_ai_api/routers/health.py` | `GET /api/v1/health` |
| `src/family_ai_api/services/` | 预留 Ollama 通讯层（阶段4） |
| `tests/test_health.py` | 健康检查接口测试 |

配置项已按最终形态定义（主机、端口、Ollama 地址、模型、Token、超时、消息长度），阶段4 直接使用：

```python
class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    ollama_base_url: str = "http://127.0.0.1:11434"
    ai_model: str = "qwen3.5:4b"
    api_access_token: str = ""
    request_timeout_seconds: float = 180.0
    max_message_chars: int = 6000
```

### 2.3 健康检查

```python
@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

设计要求：不返回版本、配置、模型、路径等细节，只回答“服务是否在运行”。

### 2.4 启动开发服务

```bash
uv run uvicorn family_ai_api.main:app --reload --host 127.0.0.1 --port 8000
```

- `--reload` 只用于本机开发，不作为长期运行配置。
- 如果包名变化，使用真实的包路径，不要机械复制命令。

访问：

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- 交互式文档：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>

## 3. 实际验证结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 单元测试 | `uv run pytest -q` | 1 passed |
| 静态检查 | `uv run ruff check .` | All checks passed |
| 健康检查 | `curl /api/v1/health` | `{"status":"ok"}`，HTTP 200 |
| 接口文档 | `curl /docs` | HTTP 200 |
| OpenAPI | `curl /openapi.json` | HTTP 200 |

完整记录见[阶段3验收记录](../04-测试与验收/验收记录/阶段3-FastAPI项目搭建.md)。

## 4. 验收

- [x] 项目能通过 `uv` 安装依赖。
- [x] `uv.lock` 已生成并提交。
- [x] FastAPI 服务可启动。
- [x] 健康检查接口可访问。
- [x] `/docs` 能显示接口定义。
- [x] Ollama 调用代码尚未与路由混在一起（本阶段未引入）。

## 5. 下一阶段

[阶段4：聊天 API 与安全](阶段4-聊天API与安全.md)。需要新增：

- `routers/models.py`、`routers/chat.py`
- `security.py`（Bearer Token，常量时间比较）
- `services/ollama_client.py`（异步 httpx、超时、错误映射）
- 请求/响应模型、并发保护、日志与测试
