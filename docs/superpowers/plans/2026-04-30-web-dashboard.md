# Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local web dashboard for browsing and managing ai-memory records via browser.

**Architecture:** FastAPI server with embedded HTML/JS. Single-process startup via CLI command. Reads existing SQLite store and review queue.

**Tech Stack:** FastAPI, uvicorn, Jinja2 (or simple string templates), vanilla JS

---

## File Structure

```
src/ai_memory/
  web/
    __init__.py
    dashboard.py      # FastAPI app, CLI entry
    routes.py        # API route handlers
    static/
      __init__.py
      index.html     # Main dashboard UI
      style.css      # Styles
      app.js         # Frontend logic
```

---

## Task 1: FastAPI App Skeleton

**Files:**
- Create: `src/ai_memory/web/__init__.py`
- Create: `src/ai_memory/web/dashboard.py`
- Modify: `src/ai_memory/cli/main.py`

- [ ] **Step 1: Create web module init**

```python
# src/ai_memory/web/__init__.py
```

- [ ] **Step 2: Create minimal FastAPI app skeleton**

```python
# src/ai_memory/web/dashboard.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


def create_app(home: Path) -> FastAPI:
    app = FastAPI(title="ai-memory Dashboard")

    @app.get("/")
    async def root():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    app = create_app()
    uvicorn.run(app, host=host, port=port)
```

- [ ] **Step 3: Add CLI parser and handler in main.py**

In `build_parser()`, add:
```python
web_parser = subparsers.add_parser("web", help="Start web dashboard")
web_parser.add_argument("--host", default="127.0.0.1")
web_parser.add_argument("--port", type=int, default=8080)
web_parser.add_argument("--home", type=Path, default=Path.home() / ".ai-memory")
```

In `run()`, add:
```python
if args.command == "web":
    from ai_memory.web.dashboard import run_server
    run_server(host=args.host, port=args.port)
    return 0
```

- [ ] **Step 4: Create minimal HTML shell**

```html
<!-- src/ai_memory/web/static/index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>ai-memory Dashboard</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <h1>ai-memory Dashboard</h1>
    <div id="app"></div>
    <script src="/static/app.js"></script>
</body>
</html>
```

```css
/* src/ai_memory/web/static/style.css */
body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
```

```js
// src/ai_memory/web/static/app.js
console.log("ai-memory dashboard loaded");
```

- [ ] **Step 5: Test server starts**

Run: `uv run ai-memory web --port 8765`
Expected: Server starts on port 8765

- [ ] **Step 6: Commit**

```bash
git add src/ai_memory/web/ src/ai_memory/cli/main.py
git commit -m "feat: add web dashboard skeleton with FastAPI"
```

---

## Task 2: Memory List API + Browser Tab

**Files:**
- Modify: `src/ai_memory/web/dashboard.py`
- Create: `src/ai_memory/web/routes.py`
- Modify: `src/ai_memory/web/static/index.html`
- Modify: `src/ai_memory/web/static/app.js`

- [ ] **Step 1: Write API test**

```python
# tests/unit/test_web_dashboard.py
from fastapi.testclient import TestClient
from ai_memory.web.dashboard import create_app


def test_list_memories_empty(client, tmp_path):
    # Setup empty store
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    # ... create app with test config ...
    response = client.get("/api/memories")
    assert response.status_code == 200
    assert response.json()["memories"] == []
```

- [ ] **Step 2: Implement memory list route in routes.py**

```python
# src/ai_memory/web/routes.py
from fastapi import APIRouter, Depends, Query
from pathlib import Path

router = APIRouter()


def get_store():
    from ai_memory.store.sqlite import SQLiteMemoryStore
    from ai_memory.core.config import load_config
    config = load_config()
    return SQLiteMemoryStore(config.store_path)


@router.get("/api/memories")
def list_memories(
    status: str | None = None,
    type_: str | None = Query(None, alias="type"),
    scope: str | None = None,
    q: str | None = None,
    limit: int = 50,
):
    store = get_store()
    store.initialize()

    if status:
        status_filter = tuple(status.split(","))
    else:
        status_filter = None

    records = store.list_all(status_filter=status_filter)
    return {"memories": records}
```

- [ ] **Step 3: Wire routes into app**

```python
# In create_app():
from ai_memory.web.routes import router as api_router
app.include_router(api_router)
```

- [ ] **Step 4: Build Memory Browser HTML**

```html
<div class="tab-content" id="tab-memories">
    <h2>Memory Browser</h2>
    <div class="filters">
        <select id="filter-status">
            <option value="">All Status</option>
            <option value="approved">Approved</option>
            <option value="auto_approved">Auto Approved</option>
            <option value="proposed">Proposed</option>
        </select>
        <input type="text" id="search-q" placeholder="Search...">
        <button onclick="loadMemories()">Refresh</button>
    </div>
    <div id="memories-list"></div>
</div>
```

- [ ] **Step 5: Implement loadMemories() in app.js**

```js
async function loadMemories() {
    const status = document.getElementById('filter-status').value;
    const q = document.getElementById('search-q').value;
    let url = '/api/memories?';
    if (status) url += `status=${status}&`;
    if (q) url += `q=${encodeURIComponent(q)}&`;

    const res = await fetch(url);
    const data = await res.json();
    renderMemories(data.memories);
}

function renderMemories(memories) {
    const list = document.getElementById('memories-list');
    if (!memories.length) {
        list.innerHTML = '<p>No memories found</p>';
        return;
    }
    list.innerHTML = memories.map(m => `
        <div class="memory-card">
            <h3>${m.uri}</h3>
            <span class="badge">${m.status}</span>
            <p>${m.content.slice(0, 100)}...</p>
        </div>
    `).join('');
}
```

- [ ] **Step 6: Test API and UI**

Run: `uv run pytest tests/unit/test_web_dashboard.py -v`
Expected: Tests pass

- [ ] **Step 7: Commit**

```bash
git add src/ai_memory/web/ tests/unit/test_web_dashboard.py
git commit -m "feat: add memory list API and browser tab"
```

---

## Task 3: Memory Update API + Editor Tab

**Files:**
- Modify: `src/ai_memory/web/routes.py`
- Modify: `src/ai_memory/web/static/index.html`
- Modify: `src/ai_memory/web/static/app.js`

- [ ] **Step 1: Write update API test**

```python
# Add to test_web_dashboard.py
def test_update_memory(client, tmp_path, store):
    response = client.put("/api/memories/test-id", json={"content": "New content"})
    assert response.status_code == 200
```

- [ ] **Step 2: Implement update route**

```python
@router.put("/api/memories/{memory_id}")
def update_memory(memory_id: str, body: dict):
    store = get_store()
    content = body.get("content")
    if not content:
        return {"error": "content required"}, 400

    record = store.get_memory(memory_id)
    if not record:
        return {"error": "Not found"}, 404

    updated = store.update_memory(memory_id, content, "web dashboard edit")
    return {"memory": updated}
```

- [ ] **Step 3: Add editor modal to HTML**

```html
<div id="editor-modal" class="modal" style="display:none">
    <div class="modal-content">
        <h3>Edit Memory</h3>
        <input type="hidden" id="edit-id">
        <textarea id="edit-content" rows="10" style="width:100%"></textarea>
        <div class="modal-actions">
            <button onclick="saveMemory()">Save</button>
            <button onclick="closeEditor()">Cancel</button>
        </div>
    </div>
</div>
```

- [ ] **Step 4: Add edit handlers to JS**

```js
function openEditor(id, content) {
    document.getElementById('edit-id').value = id;
    document.getElementById('edit-content').value = content;
    document.getElementById('editor-modal').style.display = 'block';
}

async function saveMemory() {
    const id = document.getElementById('edit-id').value;
    const content = document.getElementById('edit-content').value;
    const res = await fetch(`/api/memories/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content})
    });
    if (res.ok) {
        closeEditor();
        loadMemories();
    }
}

function closeEditor() {
    document.getElementById('editor-modal').style.display = 'none';
}
```

- [ ] **Step 5: Add edit button to memory cards**

In renderMemories():
```js
<div class="actions">
    <button onclick="openEditor('${m.id}', '${m.content.replace(/'/g, "\\'")}')">Edit</button>
</div>
```

- [ ] **Step 6: Commit**

```bash
git add src/ai_memory/web/
git commit -m "feat: add memory update API and editor"
```

---

## Task 4: Review Queue API + Review Tab

**Files:**
- Modify: `src/ai_memory/web/routes.py`
- Modify: `src/ai_memory/web/static/index.html`
- Modify: `src/ai_memory/web/static/app.js`

- [ ] **Step 1: Implement review routes**

```python
@router.get("/api/review")
def list_review():
    config = load_config()
    queue = ReviewQueue(config.review_queue_path)
    items = queue.list_pending()
    return {"items": items}

@router.post("/api/review/{review_id}/approve")
def approve_review(review_id: str):
    config = load_config()
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()
    queue = ReviewQueue(config.review_queue_path)
    item = queue.get_pending(review_id)
    validate_candidate(item.candidate)
    existing = store.get_by_uri(item.candidate.uri)
    if existing is None:
        store.create_memory(item.candidate, status="approved", change_reason=f"approved review item {review_id}")
    else:
        store.append_source(existing.id, item.candidate)
    queue.mark(review_id, "approved")
    return {"status": "approved"}

@router.post("/api/review/{review_id}/reject")
def reject_review(review_id: str):
    config = load_config()
    queue = ReviewQueue(config.review_queue_path)
    queue.mark(review_id, "rejected")
    return {"status": "rejected"}
```

- [ ] **Step 2: Add Review tab HTML**

```html
<div class="tab-content" id="tab-review">
    <h2>Review Queue</h2>
    <div id="review-list"></div>
</div>
```

- [ ] **Step 3: Add review handlers to JS**

```js
async function loadReview() {
    const res = await fetch('/api/review');
    const data = await res.json();
    renderReview(data.items);
}

function renderReview(items) {
    const list = document.getElementById('review-list');
    if (!items.length) {
        list.innerHTML = '<p>No pending review items</p>';
        return;
    }
    list.innerHTML = items.map(item => `
        <div class="review-card">
            <h4>${item.candidate.uri}</h4>
            <p>${item.candidate.content}</p>
            <p class="reason">Reason: ${item.reason}</p>
            <div class="actions">
                <button class="approve" onclick="handleReview('${item.id}', 'approve')">Approve</button>
                <button class="reject" onclick="handleReview('${item.id}', 'reject')">Reject</button>
            </div>
        </div>
    `).join('');
}

async function handleReview(id, action) {
    const res = await fetch(`/api/review/${id}/${action}`, {method: 'POST'});
    if (res.ok) loadReview();
}
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add review queue API and tab"
```

---

## Task 5: Statistics API + Stats Tab

**Files:**
- Modify: `src/ai_memory/web/routes.py`
- Modify: `src/ai_memory/web/static/index.html`
- Modify: `src/ai_memory/web/static/app.js`

- [ ] **Step 1: Implement stats route**

```python
@router.get("/api/stats")
def get_stats():
    store = get_store()
    store.initialize()
    records = store.list_all()

    by_status = {}
    by_type = {}
    by_scope = {}

    for r in records:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_type[r.type] = by_type.get(r.type, 0) + 1
        by_scope[r.scope] = by_scope.get(r.scope, 0) + 1

    return {
        "total": len(records),
        "by_status": by_status,
        "by_type": by_type,
        "by_scope": by_scope,
    }
```

- [ ] **Step 2: Add Stats tab with simple charts (CSS-based bars)**

```html
<div class="tab-content" id="tab-stats">
    <h2>Statistics</h2>
    <div class="stat-card">
        <h3>Total Memories</h3>
        <p id="stat-total">-</p>
    </div>
    <div class="charts">
        <div>
            <h4>By Status</h4>
            <div id="chart-status"></div>
        </div>
        <div>
            <h4>By Type</h4>
            <div id="chart-type"></div>
        </div>
    </div>
</div>
```

- [ ] **Step 3: Render bar charts in JS**

```js
function renderBarChart(container, data) {
    const max = Math.max(...Object.values(data));
    return Object.entries(data).map(([k, v]) => {
        const pct = (v / max * 100).toFixed(1);
        return `<div class="bar-row">
            <span class="bar-label">${k}</span>
            <div class="bar-container">
                <div class="bar" style="width:${pct}%"></div>
            </div>
            <span class="bar-value">${v}</span>
        </div>`;
    }).join('');
}
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add statistics API and stats tab"
```

---

## Task 6: Source Explorer Tab

**Files:**
- Modify: `src/ai_memory/web/routes.py`
- Modify: `src/ai_memory/web/static/index.html`
- Modify: `src/ai_memory/web/static/app.js`

- [ ] **Step 1: Implement source routes**

```python
@router.get("/api/sources")
def list_sources():
    config = load_config()
    raw_dir = config.raw_dir
    if not raw_dir.exists():
        return {"sources": []}

    sources = []
    for client_dir in raw_dir.iterdir():
        if client_dir.is_dir():
            for f in client_dir.iterdir():
                if f.is_file():
                    sources.append({
                        "client": client_dir.name,
                        "name": f.name,
                        "path": f.relative_to(raw_dir),
                        "size": f.stat().st_size,
                    })
    return {"sources": sources}

@router.get("/api/sources/{path:path}")
def read_source(path: str):
    config = load_config()
    source_path = config.raw_dir / path
    if not source_path.exists() or not source_path.is_file():
        return {"error": "Not found"}, 404
    content = source_path.read_text(encoding="utf-8")
    return {"content": content}
```

- [ ] **Step 2: Add Sources tab HTML and JS**

```html
<div class="tab-content" id="tab-sources">
    <h2>Source Explorer</h2>
    <div id="sources-list"></div>
    <pre id="source-preview"></pre>
</div>
```

```js
async function loadSources() {
    const res = await fetch('/api/sources');
    const data = await res.json();
    // render list with clickable items
}

async function previewSource(path) {
    const res = await fetch(`/api/sources/${path}`);
    const data = await res.json();
    document.getElementById('source-preview').textContent = data.content;
}
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add source explorer tab"
```

---

## Task 7: Styling and Polish

**Files:**
- Modify: `src/ai_memory/web/static/style.css`

- [ ] Add responsive layout, tab navigation, card styling, modal styles, badge colors for status
- [ ] Commit

---

## Self-Review Checklist

- [ ] Spec coverage: All 5 tabs implemented?
- [ ] No placeholders: All code is complete?
- [ ] Type consistency: Method names match across files?
- [ ] Tests: API tests written?
- [ ] CLI: `ai-memory web` works?