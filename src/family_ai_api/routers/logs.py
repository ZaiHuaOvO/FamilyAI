from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from family_ai_api.security import require_token

router = APIRouter(tags=["logs"])


@router.get("/logs", dependencies=[Depends(require_token)])
async def recent_logs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    store = getattr(request.app.state, "request_log", None)
    entries = store.recent(limit) if store is not None else []
    return {"entries": [entry.as_dict() for entry in entries]}


LOGS_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family AI 请求日志</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 2rem; background: #f7f7f8; color: #1f2328; }
  h1 { font-size: 1.4rem; }
  form { display: flex; gap: .5rem; margin: 1rem 0; }
  input { flex: 1; max-width: 28rem; padding: .5rem .6rem; border: 1px solid #d0d7de;
          border-radius: 6px; font-size: .95rem; }
  button { padding: .5rem 1rem; border: 0; border-radius: 6px; background: #1f6feb;
           color: #fff; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; }
  th, td { text-align: left; padding: .55rem .7rem; border-bottom: 1px solid #eaeef2;
           font-size: .9rem; }
  th { background: #f6f8fa; font-weight: 600; }
  #status { margin: .5rem 0; color: #57606a; font-size: .9rem; }
</style>
</head>
<body>
<h1>Family AI 请求日志</h1>
<p>只显示请求元数据，不包含聊天正文或 Token。</p>
<form id="form">
  <input id="token" type="password" placeholder="API Token" autocomplete="off" required>
  <button type="submit">加载</button>
</form>
<div id="status"></div>
<table>
  <thead><tr><th>时间 (UTC)</th><th>方法</th><th>路径</th><th>状态</th><th>耗时</th><th>来源</th></tr></thead>
  <tbody id="body"></tbody>
</table>
<script>
const form = document.getElementById('form');
const tokenInput = document.getElementById('token');
const statusEl = document.getElementById('status');
const tbody = document.getElementById('body');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  statusEl.textContent = '加载中…';
  tbody.replaceChildren();
  try {
    const response = await fetch('/api/v1/logs?limit=100', {
      headers: { Authorization: 'Bearer ' + tokenInput.value }
    });
    if (!response.ok) {
      statusEl.textContent = '加载失败：HTTP ' + response.status;
      return;
    }
    const data = await response.json();
    for (const entry of data.entries) {
      const row = document.createElement('tr');
      for (const value of [entry.timestamp, entry.method, entry.path,
                           entry.status, entry.duration_ms + ' ms', entry.client]) {
        const cell = document.createElement('td');
        cell.textContent = String(value);
        row.appendChild(cell);
      }
      tbody.appendChild(row);
    }
    statusEl.textContent = '共 ' + data.entries.length + ' 条';
  } catch (error) {
    statusEl.textContent = '加载失败：' + error;
  }
});
</script>
</body>
</html>
"""


@router.get("/logs/view", response_class=HTMLResponse)
async def logs_page() -> HTMLResponse:
    return HTMLResponse(content=LOGS_PAGE, headers={"Cache-Control": "no-store"})
