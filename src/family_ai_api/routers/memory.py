from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from family_ai_api.config import Settings, get_settings
from family_ai_api.knowledge.embeddings import EmbeddingError
from family_ai_api.memory import service as memory_service
from family_ai_api.memory.store import DuplicateMemoryError, Memory, MemorySearchResult
from family_ai_api.security import require_token

router = APIRouter(tags=["memory"])


class MemoryCreateRequest(BaseModel):
    content: str
    tags: list[str] = Field(default_factory=list)


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    tags: list[str] | None = None


class MemoryResponse(BaseModel):
    id: int
    content: str
    tags: list[str]
    source: str
    created_at: str
    updated_at: str
    score: float | None = None


class MemoryListResponse(BaseModel):
    entries: list[MemoryResponse]


def _response(memory: Memory, score: float | None = None) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        content=memory.content,
        tags=memory.tags,
        source=memory.source,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        score=score,
    )


@router.post(
    "/memory",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_token)],
)
async def create_memory(
    payload: MemoryCreateRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MemoryResponse:
    try:
        memory = await memory_service.add_memory(payload.content, payload.tags, settings)
    except memory_service.MemoryValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except DuplicateMemoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="memory already exists"
        ) from exc
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedding service unavailable",
        ) from exc
    return _response(memory)


@router.get(
    "/memory",
    response_model=MemoryListResponse,
    dependencies=[Depends(require_token)],
)
async def list_memory(
    settings: Annotated[Settings, Depends(get_settings)],
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MemoryListResponse:
    try:
        entries = await memory_service.list_memories(query, limit, settings)
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedding service unavailable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="memory index is incompatible; re-index required",
        ) from exc

    if entries and isinstance(entries[0], MemorySearchResult):
        return MemoryListResponse(
            entries=[_response(entry.memory, entry.score) for entry in entries]
        )
    return MemoryListResponse(entries=[_response(entry) for entry in entries])


@router.patch(
    "/memory/{memory_id}",
    response_model=MemoryResponse,
    dependencies=[Depends(require_token)],
)
async def update_memory(
    memory_id: int,
    payload: MemoryUpdateRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MemoryResponse:
    try:
        memory = await memory_service.update_memory(
            memory_id, payload.content, payload.tags, settings
        )
    except memory_service.MemoryValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except memory_service.MemoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="memory not found"
        ) from exc
    except DuplicateMemoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="memory already exists"
        ) from exc
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedding service unavailable",
        ) from exc
    return _response(memory)


@router.delete("/memory/{memory_id}", dependencies=[Depends(require_token)])
async def delete_memory(
    memory_id: int,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, bool]:
    deleted = await memory_service.delete_memory(memory_id, settings)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="memory not found"
        )
    return {"deleted": True}


MEMORY_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family AI 记忆管理</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 2rem; background: #f7f7f8; color: #1f2328; }
  h1 { font-size: 1.4rem; }
  .row { display: flex; gap: .5rem; margin: .6rem 0; flex-wrap: wrap; }
  input, textarea { padding: .5rem .6rem; border: 1px solid #d0d7de; border-radius: 6px;
                    font-size: .95rem; font-family: inherit; }
  textarea { width: 100%; min-height: 3.2rem; }
  button { padding: .45rem .9rem; border: 0; border-radius: 6px; background: #1f6feb;
           color: #fff; cursor: pointer; }
  button.secondary { background: #6e7781; }
  button.danger { background: #cf222e; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; margin-top: 1rem; }
  th, td { text-align: left; padding: .55rem .7rem; border-bottom: 1px solid #eaeef2;
           font-size: .9rem; vertical-align: top; }
  th { background: #f6f8fa; font-weight: 600; }
  #status { margin: .5rem 0; color: #57606a; font-size: .9rem; }
  .actions { display: flex; gap: .4rem; }
</style>
</head>
<body>
<h1>Family AI 记忆管理</h1>
<p>记忆只保存在本机，可随时编辑或删除。页面不会嵌入记忆内容，Token 只保存在当前页面内存中。</p>
<div class="row">
  <input id="token" type="password" placeholder="API Token" autocomplete="off" style="flex:1;max-width:28rem">
  <button id="reload" class="secondary" type="button">加载</button>
</div>
<div id="status"></div>
<div>
  <textarea id="content" placeholder="要记住的内容"></textarea>
  <div class="row">
    <input id="tags" placeholder="标签，用逗号分隔（可选）" style="flex:1">
    <button id="add" type="button">新增记忆</button>
  </div>
</div>
<table>
  <thead><tr><th>内容</th><th>标签</th><th>来源</th><th>更新时间</th><th>操作</th></tr></thead>
  <tbody id="body"></tbody>
</table>
<script>
const tokenInput = document.getElementById('token');
const contentInput = document.getElementById('content');
const tagsInput = document.getElementById('tags');
const statusEl = document.getElementById('status');
const tbody = document.getElementById('body');

function authHeaders() {
  return { Authorization: 'Bearer ' + tokenInput.value };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.headers || {}), ...authHeaders() }
  });
  if (!response.ok) {
    let detail = 'HTTP ' + response.status;
    try { const body = await response.json(); if (body.detail) detail = body.detail; } catch (e) {}
    throw new Error(detail);
  }
  return response.json();
}

function cell(text) {
  const td = document.createElement('td');
  td.textContent = text;
  return td;
}

function render(entries) {
  tbody.replaceChildren();
  for (const entry of entries) {
    const row = document.createElement('tr');
    row.appendChild(cell(entry.content));
    row.appendChild(cell((entry.tags || []).join(', ')));
    row.appendChild(cell(entry.source));
    row.appendChild(cell(entry.updated_at));
    const actions = document.createElement('td');
    const edit = document.createElement('button');
    edit.textContent = '编辑';
    edit.className = 'secondary';
    edit.onclick = async () => {
      const value = prompt('修改记忆内容', entry.content);
      if (value === null) return;
      try {
        await api('/api/v1/memory/' + entry.id, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: value })
        });
        await load();
      } catch (error) { statusEl.textContent = '修改失败：' + error.message; }
    };
    const remove = document.createElement('button');
    remove.textContent = '删除';
    remove.className = 'danger';
    remove.onclick = async () => {
      if (!confirm('确定删除这条记忆？')) return;
      try {
        await api('/api/v1/memory/' + entry.id, { method: 'DELETE' });
        await load();
      } catch (error) { statusEl.textContent = '删除失败：' + error.message; }
    };
    const wrap = document.createElement('div');
    wrap.className = 'actions';
    wrap.append(edit, remove);
    actions.appendChild(wrap);
    row.appendChild(actions);
    tbody.appendChild(row);
  }
}

async function load() {
  statusEl.textContent = '加载中…';
  try {
    const data = await api('/api/v1/memory?limit=100');
    render(data.entries || []);
    statusEl.textContent = '共 ' + (data.entries || []).length + ' 条';
  } catch (error) {
    statusEl.textContent = '加载失败：' + error.message;
  }
}

document.getElementById('reload').onclick = load;

document.getElementById('add').onclick = async () => {
  const content = contentInput.value.trim();
  if (!content) return;
  const tags = tagsInput.value.split(',').map(t => t.trim()).filter(Boolean);
  try {
    await api('/api/v1/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, tags })
    });
    contentInput.value = '';
    tagsInput.value = '';
    await load();
  } catch (error) { statusEl.textContent = '新增失败：' + error.message; }
};
</script>
</body>
</html>
"""


@router.get("/memory/view", response_class=HTMLResponse)
async def memory_page() -> HTMLResponse:
    return HTMLResponse(content=MEMORY_PAGE, headers={"Cache-Control": "no-store"})
