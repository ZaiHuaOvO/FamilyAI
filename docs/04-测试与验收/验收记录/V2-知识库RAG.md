# V2验收记录：本地知识库与 RAG

## 基本信息

| 项目 | 内容 |
|---|---|
| 版本 | V2（`v2.0.0`） |
| 日期 | 2026-10-18 |
| 执行人 | Claude Code + 用户 |
| 环境 | macOS 27.0.1 / M3 16GB；Ollama 0.40.6；qwen3.5:4b；qwen3-embedding:0.6b；FastAPI `0.0.0.0:8000` |
| 知识库 | `knowledge.example/`，2 个 Markdown 文档、3 个片段 |

## 实施内容

- 新增 `knowledge/chunker.py`：文件收集、跳过规则、分块、标题提取。
- 新增 `knowledge/embeddings.py`：调用 Ollama `/api/embed`。
- 新增 `knowledge/store.py`：SQLite 文档/片段/向量存储、哈希去重、余弦检索、删除。
- 新增 `knowledge/ingest.py`：索引 CLI。
- 新增 `knowledge/service.py`：检索、上下文拼接、RAG 回答。
- 新增 `routers/rag.py`：`/api/v1/rag/query`、`/api/v1/kb/stats`。
- 新增 `services/chat_guard.py`：聊天与 RAG 共用的限流/并发保护。
- 新增 `knowledge.example/` 示例资料；`data/`、`knowledge/` 加入 `.gitignore`。
- 配置新增 Embedding、知识库路径、Top-K、上下文与分块参数。

## 执行的命令与真实结果

```bash
uv run pytest -q
```

结果：`60 passed`。

```bash
uv run ruff check .
```

结果：`All checks passed!`。

```bash
uv run python -m family_ai_api.knowledge.ingest knowledge.example
```

结果：`indexed files: 2, skipped: 0, new chunks: 3`；索引耗时约 0.93s。

再次执行：`indexed files: 0, skipped: 2`，哈希去重生效。

`--delete` 后重建：删除 2 个来源，重新索引得到 3 个片段。

## RAG 查询结果

| 问题 | 回答 | Top 来源 | 分数 | 耗时 |
|---|---|---|---|---|
| 默认聊天模型是什么？ | `qwen3.5:4b` | `family-ai-overview.md` | 0.5339 | 7503ms |
| Ollama 默认监听哪个端口？ | `11434` | `ollama-notes.md` | 0.7636 | 7312ms |

| 检查 | 结果 |
|---|---|
| `/kb/stats` | 2 documents / 3 chunks / `qwen3-embedding:0.6b` |
| `/rag/query` 无 Token | 401 |
| `/kb/stats` 无 Token | 401 |
| 日志中问题/片段内容 | 0 处 |
| 内存占用 | 聊天 4.3GB + Embedding 1.2GB，100% GPU |
| `data/` 是否被 Git 忽略 | 是 |

## 验收清单

- [x] 只索引显式路径，跳过隐藏文件、`.env`、非 MD/TXT 与符号链接。
- [x] 分块、重叠、标题提取、哈希去重正常。
- [x] SQLite 存储、余弦检索、删除与重建正常。
- [x] RAG 接口返回答案与来源，统计接口正常。
- [x] 两个接口都需要 Token。
- [x] 空知识库 409、Embedding 错误 503（单元测试）。
- [x] 来源只返回相对路径、标题、片段序号与分数。
- [x] 日志不含问题、片段或回答。
- [x] 真实索引与查询通过。
- [x] 测试与静态检查通过。

## 安全确认

- [x] 未提交真实资料、索引数据库或 Token。
- [x] `data/`、`knowledge/` 已被 `.gitignore` 忽略。
- [x] 知识库只处理显式路径，不自动扫描个人目录。
- [x] RAG 接口需要 Token，来源不含绝对路径。
- [x] Ollama 仍只监听本机。

## 已知限制

- RAG 查询约 7.3～7.5s，慢于普通聊天。
- 仅支持 MD/TXT；PDF/DOCX 未实现。
- 检索在内存中计算，适合中小知识库。
- 聊天与 Embedding 模型同时加载约 5.5GB，需观察 swap。

## 下一步

- V3（长期记忆）需要先设计可见、可编辑、可删除与来源记录机制，属于后续决策事项。
