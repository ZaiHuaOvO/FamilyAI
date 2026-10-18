# Ollama 使用笔记

Ollama 默认监听本机 11434 端口，提供 `/api/chat` 与 `/api/embed` 接口。

在 M3 16GB 的 Mac 上，4B 级模型运行时约占 4.1GB 内存，冷启动约 4 秒。

`qwen3.5:4b` 是思考型模型；Family AI 在请求时设置 `think: false`，让模型直接返回最终回答，而不是思考过程。

Embedding 请求使用 `/api/embed`，本项目默认模型为 `qwen3-embedding:0.6b`。知识库索引保存在本地 SQLite 数据库中，不依赖外部服务。
