from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from family_ai_api.config import Settings
from family_ai_api.knowledge.embeddings import embed_query
from family_ai_api.knowledge.store import KnowledgeStore
from family_ai_api.memory import service as memory_service
from family_ai_api.memory.store import DuplicateMemoryError, MemorySearchResult
from family_ai_api.tasks import service as task_service
from family_ai_api.tasks.store import Task, TaskStore


class ToolError(Exception):
    pass


class UnknownToolError(ToolError):
    pass


class ToolValidationError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    write: bool


TOOLS: dict[str, ToolSpec] = {
    "get_briefing": ToolSpec(
        name="get_briefing",
        description="获取今天的任务简报（今日到期、逾期任务，可能包含天气）。",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        write=False,
    ),
    "list_tasks": ToolSpec(
        name="list_tasks",
        description="列出任务，可按状态和到期时间筛选。",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["all", "open", "done"]},
                "due": {"type": "string", "enum": ["all", "today", "overdue"]},
            },
            "additionalProperties": False,
        },
        write=False,
    ),
    "search_knowledge": ToolSpec(
        name="search_knowledge",
        description="检索本地知识库，返回最相关的文档片段与来源。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        write=False,
    ),
    "list_memories": ToolSpec(
        name="list_memories",
        description="检索长期记忆，返回与查询相关的记忆内容。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        write=False,
    ),
    "create_task": ToolSpec(
        name="create_task",
        description="创建一条家庭任务。此操作需要用户确认。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "due_at": {
                    "type": "string",
                    "description": "ISO 8601 时间，可选；只有用户明确给出日期时才填写，不要猜测",
                },
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        write=True,
    ),
    "complete_task": ToolSpec(
        name="complete_task",
        description="把指定任务标记为完成。此操作需要用户确认。",
        parameters={
            "type": "object",
            "properties": {"task_id": {"type": "integer", "minimum": 1}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
        write=True,
    ),
    "add_memory": ToolSpec(
        name="add_memory",
        description="新增一条长期记忆。此操作需要用户确认。",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        write=True,
    ),
}


def tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
            "write": spec.write,
        }
        for spec in TOOLS.values()
    ]


def _reject_extra(arguments: dict, allowed: set[str]) -> None:
    extra = set(arguments) - allowed
    if extra:
        raise ToolValidationError(f"unexpected arguments: {sorted(extra)}")


def _text(
    arguments: dict,
    key: str,
    *,
    required: bool = False,
    max_len: int = 2000,
) -> str | None:
    value = arguments.get(key)
    if value is None:
        if required:
            raise ToolValidationError(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise ToolValidationError(f"{key} must be a string")
    stripped = value.strip()
    if required and not stripped:
        raise ToolValidationError(f"{key} must not be empty")
    if len(value) > max_len:
        raise ToolValidationError(f"{key} is too long")
    return stripped


def _integer(
    arguments: dict,
    key: str,
    *,
    required: bool = False,
    minimum: int = 1,
    maximum: int = 100,
    default: int | None = None,
) -> int | None:
    value = arguments.get(key)
    if value is None:
        if required:
            raise ToolValidationError(f"{key} is required")
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolValidationError(f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ToolValidationError(f"{key} is out of range")
    return value


def validate_arguments(
    name: str,
    arguments: dict | None,
    settings: Settings,
) -> dict[str, Any]:
    spec = TOOLS.get(name)
    if spec is None:
        raise UnknownToolError(name)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolValidationError("arguments must be an object")

    if name == "get_briefing":
        _reject_extra(arguments, set())
        return {}

    if name == "list_tasks":
        _reject_extra(arguments, {"status", "due"})
        status = arguments.get("status", "all")
        due = arguments.get("due", "all")
        if status not in {"all", "open", "done"}:
            raise ToolValidationError("invalid status")
        if due not in {"all", "today", "overdue"}:
            raise ToolValidationError("invalid due")
        return {"status": status, "due": due}

    if name == "search_knowledge":
        _reject_extra(arguments, {"query", "top_k"})
        query = _text(arguments, "query", required=True)
        top_k = _integer(arguments, "top_k", minimum=1, maximum=10, default=4)
        return {"query": query, "top_k": top_k}

    if name == "list_memories":
        _reject_extra(arguments, {"query", "limit"})
        query = _text(arguments, "query", required=False)
        limit = _integer(arguments, "limit", minimum=1, maximum=100, default=20)
        return {"query": query, "limit": limit}

    if name == "create_task":
        _reject_extra(arguments, {"title", "notes", "due_at"})
        try:
            title = task_service.normalize_title(_text(arguments, "title", required=True) or "")
            notes = task_service.normalize_notes(_text(arguments, "notes") or "")
            due_at = task_service.normalize_due_at(_text(arguments, "due_at"))
        except task_service.TaskValidationError as exc:
            raise ToolValidationError(str(exc)) from exc
        return {"title": title, "notes": notes, "due_at": due_at}

    if name == "complete_task":
        _reject_extra(arguments, {"task_id"})
        task_id = _integer(
            arguments, "task_id", required=True, minimum=1, maximum=2**31 - 1
        )
        return {"task_id": task_id}

    if name == "add_memory":
        _reject_extra(arguments, {"content", "tags"})
        raw_content = _text(arguments, "content", required=True)
        raw_tags = arguments.get("tags", [])
        if not isinstance(raw_tags, list) or any(
            not isinstance(tag, str) for tag in raw_tags
        ):
            raise ToolValidationError("tags must be a string array")
        try:
            content = memory_service.normalize_content(raw_content or "", settings)
            tags = memory_service.normalize_tags(raw_tags)
        except memory_service.MemoryValidationError as exc:
            raise ToolValidationError(str(exc)) from exc
        return {"content": content, "tags": tags}

    raise UnknownToolError(name)


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def tool_result_text(result: Any, max_chars: int) -> str:
    text = json.dumps(to_jsonable(result), ensure_ascii=False)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...（结果已截断）"
    return text


def _task_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due_at": task.due_at,
        "done": task.done,
    }


def _memory_dict(memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "content": memory.content,
        "tags": memory.tags,
        "source": memory.source,
        "updated_at": memory.updated_at,
    }


async def execute_tool(name: str, arguments: dict, settings: Settings) -> Any:
    if name == "get_briefing":
        return to_jsonable(await task_service.build_briefing(settings))

    if name == "list_tasks":
        store = TaskStore(settings.tasks_db_path)
        try:
            tasks = store.list(status=arguments["status"], due=arguments["due"])
        finally:
            store.close()
        return {"entries": [_task_dict(task) for task in tasks]}

    if name == "search_knowledge":
        embedding = await embed_query(arguments["query"], settings)
        store = KnowledgeStore(settings.kb_db_path)
        try:
            results = store.search(embedding, arguments["top_k"])
        finally:
            store.close()
        return {
            "results": [
                {
                    "title": result.title,
                    "source": result.source,
                    "chunk_index": result.chunk_index,
                    "score": round(result.score, 4),
                    "content": result.content,
                }
                for result in results
            ]
        }

    if name == "list_memories":
        entries = await memory_service.list_memories(
            arguments["query"], arguments["limit"], settings
        )
        if entries and isinstance(entries[0], MemorySearchResult):
            return {
                "entries": [
                    {**_memory_dict(entry.memory), "score": round(entry.score, 4)}
                    for entry in entries
                ]
            }
        return {"entries": [_memory_dict(entry) for entry in entries]}

    if name == "create_task":
        store = TaskStore(settings.tasks_db_path)
        try:
            task = store.add(
                arguments["title"], arguments["notes"], arguments["due_at"]
            )
        finally:
            store.close()
        return _task_dict(task)

    if name == "complete_task":
        store = TaskStore(settings.tasks_db_path)
        try:
            task = store.update(arguments["task_id"], done=True)
        finally:
            store.close()
        if task is None:
            raise ToolExecutionError("task not found")
        return _task_dict(task)

    if name == "add_memory":
        try:
            memory = await memory_service.add_memory(
                arguments["content"],
                arguments["tags"],
                settings,
                source="agent",
            )
        except DuplicateMemoryError as exc:
            raise ToolExecutionError("memory already exists") from exc
        return _memory_dict(memory)

    raise UnknownToolError(name)
