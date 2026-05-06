# Web Dashboard Design

Date: 2026-04-30

## Overview

Local-first web dashboard for browsing and managing ai-memory records.

## Architecture

- **Server**: FastAPI, reads existing SQLite store
- **Static files**: Embedded HTML/CSS/JS, single-process startup
- **CLI entry**: `ai-memory web --host <host> --port <port>`

## Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/api/memories` | List memories (query params: status, type, scope, q, limit) |
| GET | `/api/memories/<id>` | Get single memory |
| PUT | `/api/memories/<id>` | Update memory content |
| GET | `/api/review` | List pending review items |
| POST | `/api/review/<id>/approve` | Approve review item |
| POST | `/api/review/<id>/reject` | Reject review item |
| GET | `/api/stats` | Memory statistics |
| GET | `/api/sources` | List raw archives |
| GET | `/api/sources/<path>` | Read archive content |

## Components

- `src/ai_memory/web/dashboard.py` - FastAPI application
- `src/ai_memory/web/templates/` - HTML/CSS/JS files
- `src/ai_memory/web/routes.py` - API route handlers
- `src/ai_memory/web/static/` - Static assets

## Tabs

1. **Memory Browser** - Filter by status/type/scope, search, paginated list
2. **Review Queue** - Pending items with approve/reject buttons
3. **Memory Editor** - View/edit memory content and metadata
4. **Statistics** - Charts showing memory distribution
5. **Source Explorer** - Browse raw transcript archives

## Security

- Local-only by default (localhost)
- Configurable host for LAN access
- Read-only for memories unless explicitly editing
- Review actions require confirmation

## Implementation Order

1. FastAPI app skeleton with CLI command
2. Memory list/read API + Browser tab
3. Memory update API + Editor tab
4. Review queue API + Review tab
5. Statistics API + Stats tab
6. Source explorer API + Sources tab
7. Styling and polish

## Testing

- Unit tests for API handlers
- Integration tests for CRUD operations
- Manual browser testing for UI