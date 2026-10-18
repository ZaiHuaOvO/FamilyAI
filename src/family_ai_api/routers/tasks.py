from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from family_ai_api.config import Settings, get_settings
from family_ai_api.security import require_token
from family_ai_api.tasks import service as task_service
from family_ai_api.tasks.store import Task, TaskStore
from family_ai_api.tasks.weather import Weather

router = APIRouter(tags=["tasks"])


class TaskCreateRequest(BaseModel):
    title: str
    notes: str = ""
    due_at: str | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    notes: str | None = None
    due_at: str | None = None
    done: bool | None = None


class TaskResponse(BaseModel):
    id: int
    title: str
    notes: str
    due_at: str | None
    done: bool
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    entries: list[TaskResponse]


class WeatherResponse(BaseModel):
    location: str
    temperature_c: float | None
    description: str
    high_c: float | None
    low_c: float | None
    precipitation_probability: float | None


class BriefingResponse(BaseModel):
    date: str
    counts: dict[str, int]
    tasks: dict[str, list[TaskResponse]]
    weather: WeatherResponse | None
    weather_configured: bool


def _task_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        notes=task.notes,
        due_at=task.due_at,
        done=task.done,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _weather_response(weather: Weather) -> WeatherResponse:
    return WeatherResponse(
        location=weather.location,
        temperature_c=weather.temperature_c,
        description=weather.description,
        high_c=weather.high_c,
        low_c=weather.low_c,
        precipitation_probability=weather.precipitation_probability,
    )


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_token)],
)
async def create_task(
    payload: TaskCreateRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TaskResponse:
    try:
        title = task_service.normalize_title(payload.title)
        notes = task_service.normalize_notes(payload.notes)
        due_at = task_service.normalize_due_at(payload.due_at)
    except task_service.TaskValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    store = TaskStore(settings.tasks_db_path)
    try:
        task = store.add(title, notes, due_at)
    finally:
        store.close()
    return _task_response(task)


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    dependencies=[Depends(require_token)],
)
async def list_tasks(
    settings: Annotated[Settings, Depends(get_settings)],
    status_filter: Annotated[
        Literal["all", "open", "done"], Query(alias="status")
    ] = "all",
    due: Annotated[Literal["all", "today", "overdue"], Query()] = "all",
) -> TaskListResponse:
    store = TaskStore(settings.tasks_db_path)
    try:
        tasks = store.list(status=status_filter, due=due)
    finally:
        store.close()
    return TaskListResponse(entries=[_task_response(task) for task in tasks])


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    dependencies=[Depends(require_token)],
)
async def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TaskResponse:
    fields = payload.model_fields_set
    updates: dict[str, object] = {}

    try:
        if "title" in fields:
            updates["title"] = task_service.normalize_title(payload.title or "")
        if "notes" in fields:
            updates["notes"] = task_service.normalize_notes(payload.notes or "")
        if "due_at" in fields:
            updates["due_at"] = task_service.normalize_due_at(payload.due_at)
        if "done" in fields and payload.done is not None:
            updates["done"] = payload.done
    except task_service.TaskValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="no fields to update",
        )

    store = TaskStore(settings.tasks_db_path)
    try:
        task = store.update(task_id, **updates)
    finally:
        store.close()

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
        )
    return _task_response(task)


@router.delete("/tasks/{task_id}", dependencies=[Depends(require_token)])
async def delete_task(
    task_id: int,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, bool]:
    store = TaskStore(settings.tasks_db_path)
    try:
        deleted = store.delete(task_id)
    finally:
        store.close()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
        )
    return {"deleted": True}


@router.get("/briefing", response_model=BriefingResponse, dependencies=[Depends(require_token)])
async def briefing(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BriefingResponse:
    data = await task_service.build_briefing(settings)
    weather = data["weather"]
    return BriefingResponse(
        date=data["date"],
        counts=data["counts"],
        tasks={
            key: [_task_response(task) for task in tasks]
            for key, tasks in data["tasks"].items()
        },
        weather=_weather_response(weather) if weather is not None else None,
        weather_configured=data["weather_configured"],
    )


TASKS_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family AI 家庭任务</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 2rem; background: #f7f7f8; color: #1f2328; }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1.05rem; margin-top: 1.4rem; }
  .row { display: flex; gap: .5rem; margin: .6rem 0; flex-wrap: wrap; align-items: center; }
  input, textarea, select { padding: .5rem .6rem; border: 1px solid #d0d7de;
                            border-radius: 6px; font-size: .95rem; font-family: inherit; }
  input.title { flex: 1; min-width: 14rem; }
  textarea { width: 100%; min-height: 2.6rem; }
  button { padding: .45rem .9rem; border: 0; border-radius: 6px; background: #1f6feb;
           color: #fff; cursor: pointer; }
  button.secondary { background: #6e7781; }
  button.danger { background: #cf222e; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; margin-top: .8rem; }
  th, td { text-align: left; padding: .55rem .7rem; border-bottom: 1px solid #eaeef2;
           font-size: .9rem; vertical-align: top; }
  th { background: #f6f8fa; font-weight: 600; }
  tr.done td { color: #8c959f; text-decoration: line-through; }
  #status { margin: .5rem 0; color: #57606a; font-size: .9rem; }
  .briefing { background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
              padding: .8rem 1rem; margin-top: .8rem; white-space: pre-wrap; }
  .actions { display: flex; gap: .4rem; }
</style>
</head>
<body>
<h1>Family AI 家庭任务</h1>
<p>任务只保存在本机。页面不嵌入任务数据，Token 只保存在当前页面内存中。</p>
<div class="row">
  <input id="token" type="password" placeholder="API Token" autocomplete="off" style="flex:1;max-width:28rem">
  <button id="reload" class="secondary" type="button">加载任务</button>
</div>
<div id="status"></div>

<h2>新增任务</h2>
<div class="row">
  <input id="title" class="title" placeholder="任务标题">
  <input id="due" type="datetime-local">
  <button id="add" type="button">新增</button>
</div>
<textarea id="notes" placeholder="备注（可选）"></textarea>

<h2>今日简报</h2>
<div class="row">
  <button id="briefingBtn" class="secondary" type="button">加载简报</button>
</div>
<div id="briefing" class="briefing">尚未加载。</div>

<h2>任务列表</h2>
<div class="row">
  <select id="statusFilter">
    <option value="all">全部</option>
    <option value="open">未完成</option>
    <option value="done">已完成</option>
  </select>
  <select id="dueFilter">
    <option value="all">全部时间</option>
    <option value="today">今天到期</option>
    <option value="overdue">已逾期</option>
  </select>
</div>
<table>
  <thead><tr><th>完成</th><th>标题</th><th>到期</th><th>备注</th><th>操作</th></tr></thead>
  <tbody id="body"></tbody>
</table>
<script>
const tokenInput = document.getElementById('token');
const titleInput = document.getElementById('title');
const dueInput = document.getElementById('due');
const notesInput = document.getElementById('notes');
const statusEl = document.getElementById('status');
const briefingEl = document.getElementById('briefing');
const tbody = document.getElementById('body');

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: 'Bearer ' + tokenInput.value }
  });
  if (!response.ok) {
    let detail = 'HTTP ' + response.status;
    try { const body = await response.json(); if (body.detail) detail = JSON.stringify(body.detail); } catch (e) {}
    throw new Error(detail);
  }
  return response.json();
}

function cell(text) {
  const td = document.createElement('td');
  td.textContent = text == null ? '' : String(text);
  return td;
}

function render(entries) {
  tbody.replaceChildren();
  for (const task of entries) {
    const row = document.createElement('tr');
    if (task.done) row.className = 'done';
    const checkCell = document.createElement('td');
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.checked = task.done;
    check.onchange = async () => {
      try { await api('/api/v1/tasks/' + task.id, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: check.checked })
      }); await load(); } catch (e) { statusEl.textContent = '更新失败：' + e.message; }
    };
    checkCell.appendChild(check);
    row.appendChild(checkCell);
    row.appendChild(cell(task.title));
    row.appendChild(cell(task.due_at || ''));
    row.appendChild(cell(task.notes || ''));
    const actions = document.createElement('td');
    const edit = document.createElement('button');
    edit.textContent = '编辑';
    edit.className = 'secondary';
    edit.onclick = async () => {
      const value = prompt('修改任务标题', task.title);
      if (value === null) return;
      try { await api('/api/v1/tasks/' + task.id, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: value })
      }); await load(); } catch (e) { statusEl.textContent = '修改失败：' + e.message; }
    };
    const remove = document.createElement('button');
    remove.textContent = '删除';
    remove.className = 'danger';
    remove.onclick = async () => {
      if (!confirm('确定删除这个任务？')) return;
      try { await api('/api/v1/tasks/' + task.id, { method: 'DELETE' }); await load(); }
      catch (e) { statusEl.textContent = '删除失败：' + e.message; }
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
  const status = document.getElementById('statusFilter').value;
  const due = document.getElementById('dueFilter').value;
  try {
    const data = await api('/api/v1/tasks?status=' + status + '&due=' + due);
    render(data.entries || []);
    statusEl.textContent = '共 ' + (data.entries || []).length + ' 条';
  } catch (e) { statusEl.textContent = '加载失败：' + e.message; }
}

document.getElementById('reload').onclick = load;
document.getElementById('statusFilter').onchange = load;
document.getElementById('dueFilter').onchange = load;

document.getElementById('add').onclick = async () => {
  const title = titleInput.value.trim();
  if (!title) return;
  const due = dueInput.value || null;
  try {
    await api('/api/v1/tasks', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, notes: notesInput.value, due_at: due })
    });
    titleInput.value = ''; dueInput.value = ''; notesInput.value = '';
    await load();
  } catch (e) { statusEl.textContent = '新增失败：' + e.message; }
};

document.getElementById('briefingBtn').onclick = async () => {
  briefingEl.textContent = '加载中…';
  try {
    const data = await api('/api/v1/briefing');
    const lines = [];
    lines.push('日期：' + data.date);
    lines.push('今日到期：' + data.counts.today + ' 条；逾期：' + data.counts.overdue + ' 条；未完成：' + data.counts.open + ' 条');
    if (data.weather) {
      lines.push('天气：' + data.weather.location + ' ' + data.weather.description +
                 '，当前 ' + (data.weather.temperature_c == null ? '—' : data.weather.temperature_c + '°C') +
                 '，最高 ' + (data.weather.high_c == null ? '—' : data.weather.high_c + '°C') +
                 '，最低 ' + (data.weather.low_c == null ? '—' : data.weather.low_c + '°C') +
                 '，降水概率 ' + (data.weather.precipitation_probability == null ? '—' : data.weather.precipitation_probability + '%'));
    } else {
      lines.push(data.weather_configured ? '天气：暂不可用' : '天气：未配置（设置 WEATHER_LATITUDE / WEATHER_LONGITUDE）');
    }
    lines.push('');
    lines.push('今日任务：');
    if (!data.tasks.today.length) lines.push('- 无');
    for (const task of data.tasks.today) lines.push('- ' + task.title);
    lines.push('逾期任务：');
    if (!data.tasks.overdue.length) lines.push('- 无');
    for (const task of data.tasks.overdue) lines.push('- ' + task.title);
    briefingEl.textContent = lines.join('\\n');
  } catch (e) { briefingEl.textContent = '加载失败：' + e.message; }
};
</script>
</body>
</html>
"""


@router.get("/tasks/view", response_class=HTMLResponse)
async def tasks_page() -> HTMLResponse:
    return HTMLResponse(content=TASKS_PAGE, headers={"Cache-Control": "no-store"})
