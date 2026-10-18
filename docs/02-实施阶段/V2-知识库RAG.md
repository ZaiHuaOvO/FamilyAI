# V2：本地知识库与 RAG

> 状态：**已完成（2026-10-18）**  
> 前置：V1.1（`v1.1.0`）已完成  
> 决策依据：[V2 知识库方案决策](../06-决策记录/V2-知识库方案.md)

## 1. 目标与范围

让 Family AI 基于用户明确指定的 Markdown/TXT 文档回答问题，并返回来源。

已确认的范围：

- 轻量自建：FastAPI + Ollama Embedding + SQLite + numpy。
- 首版只索引 `knowledge.example/` 中的示例文档。
- 只支持 `.md` / `.markdown` / `.txt`，不解析 PDF。
- Embedding 模型：`qwen3-embedding:0.6b`（639MB）。

不做：

- 自动扫描主目录、聊天记录、照片、邮件。
- PDF/DOCX/网页抓取。
- 多用户权限、长期记忆、工具调用。

## 2. 架构

```text
索引（CLI）：
Markdown/TXT → 分块 → Ollama /api/embed → SQLite（文档 + 片段 + 向量）

查询（API）：
问题 → Ollama /api/embed → 余弦相似度 Top-K
     → 拼接资料上下文 → 本地模型回答 → 返回答案 + 来源
```

## 3. 代码模块

| 文件 | 职责 |
|---|---|
| `knowledge/chunker.py` | 文件收集、跳过规则、分块、标题提取 |
| `knowledge/embeddings.py` | 调用 Ollama `/api/embed` |
| `knowledge/store.py` | SQLite 文档/片段/向量存储、哈希、检索 |
| `knowledge/ingest.py` | 索引 CLI（`python -m family_ai_api.knowledge.ingest`） |
| `knowledge/service.py` | 检索、上下文拼接、RAG 回答 |
| `routers/rag.py` | `/api/v1/rag/query`、`/api/v1/kb/stats` |
| `services/chat_guard.py` | 聊天与 RAG 共用的限流/并发保护 |

## 4. 索引规则

- 输入为目录时，`source` 为相对该目录的路径；输入为文件时，`source` 为文件名。
- 跳过：隐藏文件/目录、`.env`、`.git`、`.venv`、`node_modules`、`data`、`logs`、非 MD/TXT 文件。
- 分块：默认 500 字符、重叠 80 字符；优先在段落、句号、换行处切分。
- 去重：按文件内容 SHA256；未变化则跳过。
- 重复索引同一 `source` 时先删除旧片段再写入。
- 数据文件：`data/knowledge.db`（已被 `.gitignore` 忽略）。
- 示例资料：`knowledge.example/`（可提交）。

## 5. 接口

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| `POST` | `/api/v1/rag/query` | 基于知识库回答 | 是 |
| `GET` | `/api/v1/kb/stats` | 文档/片段数量与最近索引时间 | 是 |

请求：

```json
{
  "message": "默认聊天模型是什么？",
  "top_k": 4
}
```

响应：

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

## 6. 配置

```dotenv
EMBEDDING_MODEL=qwen3-embedding:0.6b
KB_DB_PATH=data/knowledge.db
KB_TOP_K=4
KB_MAX_CONTEXT_CHARS=6000
KB_CHUNK_CHARS=500
KB_CHUNK_OVERLAP=80
```

## 7. 索引命令

```bash
# 索引示例文档
uv run python -m family_ai_api.knowledge.ingest knowledge.example

# 删除已索引的示例文档
uv run python -m family_ai_api.knowledge.ingest knowledge.example --delete
```

索引时只输出文件名与数量，不输出文档正文。

## 8. 安全与隐私

- 只索引用户显式指定的路径；不自动扫描个人目录。
- 不索引 `.env`、隐藏文件、二进制文件。
- `rag/query` 与 `kb/stats` 都需要 Token。
- 来源只返回相对路径、标题、片段序号与分数，不返回绝对路径或完整文档。
- 请求日志只记录路径等元数据，不记录问题、检索片段或答案。
- 知识库内容视为数据而非指令；只应索引可信来源，避免恶意文档影响回答。
- 真实资料目录 `knowledge/` 与索引 `data/` 均不提交 Git。

## 9. 测试

- 单元测试：分块、跳过规则、标题提取、存储/去重/删除、余弦排序、维度不匹配。
- API 测试：认证、参数校验、空知识库、Embedding 错误、来源返回、日志脱敏。
- 真实测试：索引示例文档 → 提问 → 检查答案与来源。

### 9.1 测试与真实验证结果

单元测试：`uv run pytest -q` → **60 passed**；`uv run ruff check .` → **All checks passed**。

Embedding：

- `/api/embed` 返回 2 条 1024 维向量，冷启动约 1.17s。

索引：

- `knowledge.example`：2 个文档、3 个片段，索引耗时约 0.93s。
- 再次索引：`indexed files: 0, skipped: 2`，哈希去重生效。
- `--delete` 后重建：2 个来源删除成功，重新索引得到 3 个片段。

RAG 查询：

| 问题 | 回答 | Top 来源 | 分数 | 耗时 |
|---|---|---|---|---|
| 默认聊天模型是什么？ | `qwen3.5:4b` | `family-ai-overview.md` | 0.5339 | 7503ms |
| Ollama 默认监听哪个端口？ | `11434` | `ollama-notes.md` | 0.7636 | 7312ms |

其他检查：

- `/kb/stats`：`documents=2`、`chunks=3`、`embedding_model=qwen3-embedding:0.6b`。
- `/rag/query` 与 `/kb/stats` 无 Token：401。
- 请求日志中问题与片段内容出现 0 次。
- 内存：聊天模型约 4.3GB + Embedding 模型约 1.2GB，均 100% GPU。
- `data/` 被 Git 忽略，未跟踪真实索引。

## 10. 验收

- [x] 只索引显式指定路径，跳过隐藏文件、`.env`、非 MD/TXT 与符号链接。
- [x] 分块、重叠、标题提取与哈希去重正常。
- [x] SQLite 存储、余弦检索、删除与重建正常。
- [x] `/rag/query` 返回答案与来源，`/kb/stats` 返回统计。
- [x] 两个接口都需要 Token。
- [x] 空知识库返回 409，Embedding 不可用返回 503（单元测试）。
- [x] 来源只返回相对路径、标题、片段序号与分数。
- [x] 日志不包含问题、检索片段或回答。
- [x] 真实索引与查询验证通过。
- [x] 测试与静态检查通过。

## 11. 已知限制

- RAG 查询实测约 7.3～7.5s，明显慢于普通聊天；主要来自检索上下文与生成长度。后续可通过缩短上下文、流式输出或减少 Top-K 优化。
- 当前相似度分数在 0.5～0.76 区间，片段较短；文档增多后可评估更好的分块与 Embedding 模型。
- 只支持 MD/TXT；PDF/DOCX 未实现。
- 检索在 Python 内存中计算余弦，适合中小知识库；文档量很大时应改用向量索引（Chroma/LanceDB 等）。
- 聊天与 Embedding 模型同时加载约 5.5GB，需持续观察 16GB 机器的 swap。
- 知识库内容视为数据而非指令；只索引可信来源。
