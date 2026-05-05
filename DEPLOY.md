# Deployment Guide

## Quick Start (Local)

```bash
# Install
pip install -e .

# Initialize
ai-memory init

# Start server
ai-memory server --host 0.0.0.0 --port 8080

# Register admin user (in another terminal)
curl -X POST "http://localhost:8080/api/auth/register?username=admin&password=your-password"

# Login and get token
curl -X POST "http://localhost:8080/api/auth/login?username=admin&password=your-password"
# Returns: {"token": "xxx", "user": {..., "api_key": "xxx"}}

# Add memory
ai-memory add project://demo/test "Use pytest for tests"

# Open browser
# http://localhost:8080
```

## Remote MCP Connection (Claude Code)

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "ai-memory": {
      "url": "http://your-server:8080/mcp",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

## Server Mode Features

- `/` - Web dashboard (UI)
- `/mcp` - MCP server (JSON-RPC)
- `/api/auth/*` - Authentication
- `/api/admin/*` - User management

## User Roles

| Role | Web Dashboard | MCP Tools |
|------|--------------|-----------|
| read | Read only | Search + Context |
| write | Read/Write | Search + Context + Write |
| admin | Full access | Full access + User management |
