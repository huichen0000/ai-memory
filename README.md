# ai-memory

`ai-memory` 是一个面向 AI 编程工具的长期记忆系统，用 SQLite 保存项目约定、测试命令、用户偏好、历史坑点、架构决策等上下文，并通过 CLI、Web Dashboard、MCP 和历史 transcript 导入流程让 Claude Code、Codex CLI、Gemini CLI 等工具共享同一套记忆。

它的目标不是单纯归档聊天记录，而是把历史对话和手动输入沉淀为可检索、可审核、可更新的长期记忆。

## 核心能力

- SQLite 记忆库：memories、sources、versions、tags、triggers、FTS 搜索索引。
- CLI：初始化、添加、搜索、上下文组装、导入、审核、更新、服务启动。
- Web Dashboard：记忆列表、搜索、分页、编辑、Review Queue、统计、Source Explorer、用户管理。
- 集中式 Server：Web + MCP + 认证 + 用户管理。
- MCP 工具：`memory_search`、`memory_context`、`memory_read`、`memory_write`。
- 历史导入：支持 Claude Code、Codex CLI、Gemini CLI、本地泛用 transcript。
- 远程历史推送：本机自动发现历史并上传到远程服务器处理。
- Review Queue：高影响或不确定候选记忆进入审核。
- 隐私保护：常见 secret redaction、敏感路径检测、上传大小限制。
- 多用户绑定：历史导入和远程 push 生成的记忆绑定到当前认证用户。

## 安装

开发安装：

```bash
python -m pip install -e ".[dev]"
```

如果只想运行当前项目里的命令，可以在项目根目录使用虚拟环境：

```bash
.venv/Scripts/ai-memory.exe --help
```

## 初始化

```bash
ai-memory init
```

默认 home：

```text
~/.ai-memory
```

也可以指定：

```bash
ai-memory init --home /path/to/.ai-memory
```

初始化后会创建：

```text
.ai-memory/
  config.yaml
  extractor.json
  memory.db
  raw/
  logs/
  review-queue.jsonl
```

`init` 默认配置项目内置 extractor。也可以手动配置 OpenAI-compatible AI 参数：

```bash
ai-memory init \
  --extractor-base-url https://api.openai.com/v1 \
  --extractor-api-key YOUR_API_KEY \
  --extractor-model gpt-4o-mini \
  --extractor-mode auto
```

## 手动添加和检索记忆

添加记忆：

```bash
ai-memory add project://local/demo/commands "Use pytest for tests."
```

搜索：

```bash
ai-memory search pytest
```

为当前 prompt 生成上下文：

```bash
ai-memory context --prompt "run tests"
```

输出示例：

```markdown
# Retrieved Memory

## project://local/demo/commands

- Type: project_command
- Status: approved
- Memory: Use pytest for tests.
```

## 历史记忆初始化

从本机历史 transcript 初始化记忆：

```bash
ai-memory history init --clients all --review-only --redact-archive
```

支持的内置客户端：

- `claude-code`
- `codex-cli`
- `gemini-cli`

只预览、不写入：

```bash
ai-memory history init --clients all --dry-run
```

低风险高置信度候选自动写入，高影响候选仍进入 review：

```bash
ai-memory history init --clients all --auto-write-low-risk --redact-archive
```

导入泛用 transcript 文件或目录：

```bash
ai-memory history init --include-generic ./old-chats --review-only --redact-archive
```

绑定到指定本地用户：

```bash
ai-memory history init \
  --clients all \
  --auto-write-low-risk \
  --owner-username admin \
  --redact-archive
```

不传 `--owner-username` 时，如果本地 `auth.db` 存在用户，会默认绑定最早创建的 admin；没有 admin 时绑定最早创建的用户。

## 最低成本远程历史导入

远程服务器无法直接读取用户本机的 Claude/Codex/Gemini 历史目录。最低使用成本的方式是：**用户在本机运行一条命令，本机自动发现历史并上传到远程服务器处理**。

```bash
ai-memory history push \
  --server http://localhost:8080 \
  --api-key YOUR_TOKEN_OR_API_KEY \
  --clients all \
  --auto-write-low-risk \
  --redact-archive
```

流程：

1. 本机自动发现 Claude Code、Codex CLI、Gemini CLI 历史 transcript。
2. 跳过敏感路径和超大文件。
3. 可选本地脱敏后上传。
4. 服务端创建 import session。
5. 服务端运行 extractor。
6. 低风险候选自动写入，高影响候选进入 review queue。
7. 生成的记忆绑定到当前认证用户。

Web Dashboard 的 Sources 页面也会生成可复制的 import 命令。

如果 `/process` 处理时间较长，CLI 会等待更久；即使最终等待超时，服务端也可能仍在继续处理，可以刷新 Web Dashboard 查看结果。

## 泛用 transcript 归档

只归档泛用 transcript：

```bash
ai-memory import --client generic --path ./chat.md --archive-only --redact-archive
```

默认会拒绝敏感路径。确实需要导入敏感路径时才使用：

```bash
ai-memory import --client generic --path ./chat.md --archive-only --allow-sensitive-source --redact-archive
```

## Review Queue

查看待审核项：

```bash
ai-memory review
```

批准：

```bash
ai-memory approve <review_id>
```

拒绝：

```bash
ai-memory reject <review_id>
```

批准逻辑：

- 如果同 URI 不存在已批准记忆，则写入为 approved。
- 如果同 URI 已存在且内容相同，则追加 source，不重复创建。
- 如果同 URI 已存在但内容不同，则阻止批准，避免静默覆盖。

## Web Dashboard

启动本地 Dashboard：

```bash
ai-memory web --host 127.0.0.1 --port 8080
```

访问：

```text
http://127.0.0.1:8080
```

Dashboard 包含：

- Memories：搜索、分页、编辑。
- Review：审核队列分页。
- Stats：按状态、类型、scope 统计。
- Sources：查看 raw archive，并复制远程 history push 命令。
- Users：admin 用户管理。

## 集中式 Server

多用户部署建议使用 combined server：

```bash
ai-memory server --host 0.0.0.0 --port 8080
```

提供：

- `/`：Web Dashboard。
- `/mcp`：HTTP MCP 服务。
- `/api/auth/*`：注册、登录、当前用户。
- `/api/admin/*`：用户管理。
- `/api/history/import-sessions`：远程历史导入会话。

### 注册和登录

首个注册用户会自动成为 admin，后续注册用户默认为 read。

注册：

```bash
curl -X POST "http://localhost:8080/api/auth/register?username=admin&password=your-password"
```

登录：

```bash
curl -X POST "http://localhost:8080/api/auth/login?username=admin&password=your-password"
```

返回：

```json
{
  "token": "...",
  "user": {
    "id": "...",
    "username": "admin",
    "role": "admin",
    "api_key": "..."
  }
}
```

### 用户角色

| 角色 | Web Dashboard | MCP 工具 |
|---|---|---|
| `read` | 只读 | Search + Context |
| `write` | 读写 | Search + Context + Write |
| `admin` | 全权限 | 全权限 + 用户管理 |

### 用户管理

列出用户：

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/admin/users
```

创建用户：

```bash
curl -X POST "http://localhost:8080/api/admin/users?username=bob&password=secret&role=write" \
  -H "Authorization: Bearer $TOKEN"
```

删除用户：

```bash
curl -X DELETE "http://localhost:8080/api/admin/users/$USER_ID" \
  -H "Authorization: Bearer $TOKEN"
```

重新生成 API key：

```bash
curl -X POST "http://localhost:8080/api/admin/users/$USER_ID/regenerate-key" \
  -H "Authorization: Bearer $TOKEN"
```

## MCP 使用

本地 stdio MCP：

```bash
ai-memory mcp serve
```

远程 MCP 可配置到 Claude Code：

```json
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

MCP 工具：

- `memory_search`：搜索 approved / auto_approved 记忆。
- `memory_context`：根据 prompt 生成上下文。
- `memory_read`：按 memory id 读取。
- `memory_write`：提交候选记忆，仍走统一写入策略。

## 记忆 URI 模型

示例：

```text
global://user/preferences
project://github.com/acme/app/testing
branch://github.com/acme/app/feature-login/state
path://github.com/acme/app/apps-web
tool://claude-code/notes
system://boot
```

支持 namespace：

```text
global
org
project
branch
path
tool
system
```

URI 表示记忆的逻辑位置和作用范围，不是文件路径。

## 记忆类型和写入策略

常见 memory type：

```text
user_preference
workflow_rule
project_overview
project_command
coding_style
testing_rule
architecture_decision
api_contract
security_constraint
pitfall
bug_pattern
dependency_note
branch_state
task_todo
tool_note
external_reference
```

低风险类型可自动写入：

```text
project_command
branch_state
task_todo
dependency_note
tool_note
pitfall
```

高影响类型默认进入 review：

```text
user_preference
workflow_rule
architecture_decision
api_contract
security_constraint
coding_style
testing_rule
```

自动写入条件：

```text
risk = low
confidence >= 0.85
无敏感内容
无冲突
类型允许 auto-write
```

## 隐私和安全

### 内容脱敏

支持常见内容脱敏：

- Bearer token。
- API key assignment。
- password assignment。
- private key block。
- database URL password。

示例：

```text
Authorization: Bearer abc+def/ghi=
```

会替换为：

```text
Authorization: Bearer [REDACTED:BEARER_TOKEN]
```

### 敏感路径

默认识别并拒绝常见敏感路径：

- `.env`、`.env.*`
- `*.pem`、`*.key`
- `id_rsa`、`id_ed25519`、`id_ecdsa`、`id_dsa`
- `credentials.json`、`client_secret.json`、`token.json`、`secrets.json`
- 名称包含 `secret`、`credential`、`token`、`private_key`、`private-key`、`service-account`、`service_account`
- `.ssh`、`.aws`、`.kube`、`.docker`、`.azure`、`.terraform.d`、`.cargo`、`.gradle`、`gcloud`、`gh`、`hub`

内置客户端自动发现到的敏感路径始终跳过。`--allow-sensitive-source` 只适用于显式 generic import 或 `history init --include-generic`。

### 原始归档

raw archive 可能包含原始 transcript 文本。建议默认使用：

```bash
--redact-archive
```

## 项目架构

源码结构：

```text
src/ai_memory/
  auth/          用户、API key、JWT、密码哈希
  adapters/      Claude Code、Codex CLI、Gemini CLI、Generic transcript
  cli/           命令行入口
  core/          数据模型、URI、config、policy
  extraction/    transcript 归一化、candidate validation、extractor provider
  history/       历史扫描和初始化
  mcp/           MCP 工具和服务
  privacy/       secret redaction、sensitive path detection
  retrieval/     环境检测、排序、上下文组装
  review/        JSONL review queue
  server/        combined server、认证、远程导入 API
  store/         SQLite 持久化和 FTS
  web/           Web Dashboard
  wrappers/      aiwrap prompt 构造
```

核心数据流：

1. 手动添加、MCP 写入、历史导入或远程 push 生成 MemoryCandidate。
2. Candidate 经过 validation、redaction 和 routing。
3. 低风险候选写入 SQLite；高影响候选进入 review queue。
4. 检索时按 status、scope、repo、branch、path、trigger、FTS 排序。
5. CLI、MCP、Web Dashboard 使用同一 SQLite store。

## CLI 命令总览

```bash
ai-memory init
ai-memory add
ai-memory search
ai-memory context
ai-memory discover
ai-memory review
ai-memory approve
ai-memory reject
ai-memory import
ai-memory history init
ai-memory history push
ai-memory capture
ai-memory wiki
ai-memory web
ai-memory server
ai-memory mcp serve
ai-memory system init
ai-memory memory show
ai-memory memory list
ai-memory memory update
```

## 测试

运行单元测试：

```bash
python -m pytest
```

当前覆盖：

- config 初始化和 extractor 配置。
- URI parse / validation。
- policy routing。
- SQLite CRUD / FTS / version / source。
- 隐私脱敏和敏感路径检测。
- Review Queue。
- retrieval / context。
- CLI add / search / context / import / history init / history push。
- extractor command provider。
- MCP tools。
- Web memories / review / sources API。
- server auth 和 admin 注册逻辑。
- 历史导入 owner 绑定。

## 当前限制

- 不会自动安装 Claude Code hook；只提供可手动配置的 CLI/MCP 能力。
- MCP 写入策略保守，高影响或不可信候选仍进入 review。
- 候选写入要求 URI namespace 与 scope 一致，格式错误的 extractor 输出会被丢弃或进入 review。
- 检索仍以 SQLite FTS + scope/repo/branch/path/trigger 确定性排序为主，暂未实现 embedding 语义检索。
- SQLite 是唯一 canonical store；wiki 只是只读投影。

## 建议路线

1. 增强 transcript adapter，覆盖更多 Claude Code / Codex / Gemini 格式细节。
2. 增加冲突合并和版本比较命令。
3. 增加后台 import job 状态 API 和 Web 进度条。
4. 在确定性检索稳定后增加可选 embedding 检索。
5. 增强 Web Dashboard 的筛选、owner 展示和批量操作。
