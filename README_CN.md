# ai-memory 中文说明

`ai-memory` 是一个本地优先的多工具 AI 编程记忆系统，目标是让 Claude Code、Codex CLI、Gemini CLI 以及其他 AI 编程工具共享同一套长期记忆，避免每次切换工具或项目时都重复说明编码规范、项目约定、测试命令、历史坑点等上下文。

它不是单纯的聊天记录归档工具，也不是只服务 Claude 的记忆层，而是一个工具无关的本地记忆核心，外层通过 CLI、MCP、适配器和 wrapper 与不同 AI 工具集成。

## 1. 项目目标

`ai-memory` 解决的问题是：

- 多个 AI 编程工具之间无法共享长期上下文。
- 每个项目都需要反复告诉 AI：
  - 用什么包管理器；
  - 如何运行测试；
  - 代码风格是什么；
  - 哪些目录不能动；
  - 哪些历史 bug 或坑点需要注意；
  - 用户偏好和工作流规则是什么。
- 历史对话中已经出现过很多有价值信息，但无法自动沉淀成可检索记忆。
- 下一次启动 AI 工具时，无法根据当前项目、分支、路径、prompt 自动取回相关记忆。

`ai-memory` 的目标是提供一个本地 SQLite 记忆库，让多个工具都能：

1. 在会话开始或 prompt 执行前检索相关记忆；
2. 在会话结束或 transcript 导入时提取候选记忆；
3. 对低风险记忆自动写入；
4. 对高影响记忆进入 review queue；
5. 支持 CLI 和 MCP 两种主要访问方式；
6. 未来可以扩展到更多 AI 编程工具。

## 2. 当前 MVP 已实现能力

当前版本已经实现一个完整的本地 MVP，包括：

### 核心能力

- Python 包结构和 CLI 入口。
- 配置初始化：`ai-memory init`。
- SQLite 记忆存储：memories、sources、versions、tags、triggers、FTS 搜索索引。
- URI 模型：`global://`、`org://`、`project://`、`branch://`、`path://`、`tool://`、`system://`。
- 记忆候选模型、正式记忆模型、路由策略。
- 写入策略：低风险高置信度记忆自动写入，高影响类型进入 review queue，敏感内容拒绝持久化。
- JSONL review queue：enqueue、list pending、approve、reject、atomic rewrite、status validation。
- 隐私保护：Bearer token、API key、password、private key、database URL password redaction，以及 sensitive path detection。

### 检索能力

- 环境检测：当前目录、git root、branch、remote、repo_id。
- SQLite FTS 搜索。
- prompt token 安全处理，避免 FTS 查询被特殊字符打崩。
- 记忆排序：scope specificity、status、confidence。
- Markdown context assembly。
- Claude Code hook JSON 输出格式：`--format hook-json`。

### CLI 命令

当前 CLI 支持：

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
ai-memory mcp serve
```

### Transcript / Extraction 基础

- Generic transcript adapter。
- Markdown 风格简单 transcript normalize。
- Extractor provider interface。
- Command-based extractor provider。
- Candidate validation。
- Candidate routing：auto-write、queue、discard。
- archive-only generic transcript import。

### MCP 能力

实现了 MCP 工具函数和 server 入口：

- `memory_search`
- `memory_context`
- `memory_read`
- `memory_write`

MCP 写入同样走统一 policy，不允许绕过 review policy。

### 多工具适配器

当前已实现初始适配器：

- Claude Code
- Codex CLI
- Gemini CLI
- Generic transcript

Claude/Codex/Gemini 目前主要支持 discovery 和基础 normalize，后续可以继续增强不同工具的 transcript 格式解析。

### aiwrap 骨架

实现了基础 wrapper prompt builder：

```bash
aiwrap <client> [client args...] -- <prompt>
```

当前是 skeleton，后续可接入 `ai-memory context` 自动拼接 prompt。

## 3. 安装与初始化

开发安装：

```bash
python -m pip install -e ".[dev]"
```

初始化本地 memory home：

```bash
ai-memory init
```

默认 home 路径：

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
  memory.db
  raw/
  logs/
  review-queue.jsonl
```

## 4. 手动添加和检索记忆

添加一条记忆：

```bash
ai-memory add project://local/demo/commands "Use pytest for tests."
```

搜索记忆：

```bash
ai-memory search pytest
```

生成当前 prompt 相关上下文：

```bash
ai-memory context --prompt "run tests"
```

示例输出：

```markdown
# Retrieved Memory

## project://local/demo/commands

- Type: project_command
- Status: approved
- Memory: Use pytest for tests.
```

如果没有相关 approved memory，会输出：

```markdown
# Retrieved Memory

_No relevant approved memory found._
```

## 5. Hook JSON 输出

为了接入 Claude Code 等支持 hook JSON 的工具，可以使用：

```bash
ai-memory context --format hook-json --event SessionStart
```

输出示例：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "# Retrieved Memory\n\n_No relevant approved memory found._"
  }
}
```

注意：当前 MVP 只提供 hook JSON 输出能力，不会自动修改 Claude Code settings 或自动安装 hook。实际自动接入需要用户手动配置对应工具的 hook。

## 6. Review Queue

高影响或需要确认的记忆不会直接写入 SQLite，而是进入 JSONL review queue。

查看待审核项：

```bash
ai-memory review
```

如果没有待审核项：

```text
No pending review items
```

批准：

```bash
ai-memory approve <review_id>
```

拒绝：

```bash
ai-memory reject <review_id>
```

review queue 文件位置：

```text
~/.ai-memory/review-queue.jsonl
```

当前实现包含：

- status validation；
- unknown review id 错误处理；
- atomic rewrite，避免 rewrite 中断导致文件损坏。

## 7. Transcript Import

当前 MVP 支持 generic transcript 的 archive-only 导入：

```bash
ai-memory import --client generic --path ./chat.md --archive-only
```

导入后会归档到：

```text
~/.ai-memory/raw/generic/<filename>
```

重要隐私说明：

`--archive-only` 会原样保存 transcript 文本，不会自动 redaction，也不会检查 sensitive path。

因此只应该导入你确认适合本地归档的 transcript。

当前 redaction / validation 主要发生在：

- adapter normalization；
- candidate validation；
- candidate routing；
- durable memory 写入前检查。

raw archive 本身仍可能包含原始内容。

## 历史记忆初始化

如果要从过去使用过的 AI 编程工具中初始化记忆，可以运行：

```bash
ai-memory history init --clients all --review-only
```

该命令会扫描本机支持的工具历史记录（`claude-code`、`codex-cli`、`gemini-cli`），把发现的 transcript 归档到 `~/.ai-memory/raw/<client>/`，并在已配置 extractor provider 时提取候选记忆。

默认是 review-only：有效候选记忆只进入 review queue，不会直接写入长期记忆库。

```bash
ai-memory review
ai-memory approve <review_id>
ai-memory reject <review_id>
```

只预览、不写入任何文件或记忆：

```bash
ai-memory history init --clients all --dry-run
```

如果你希望低风险、高置信度的候选记忆自动写入，同时高影响记忆仍然进入 review queue，可以运行：

```bash
ai-memory history init --clients all --auto-write-low-risk
```

也可以额外导入 generic transcript 文件或目录：

```bash
ai-memory history init --include-generic ./old-chats --review-only
```

隐私提醒：raw archive 可能包含原始 transcript 文本。redaction 和 validation 主要保护被提取出来的长期记忆，raw archive 本身仍然是源 transcript 的本地副本。

## 8. MCP Server

启动 MCP server：

```bash
ai-memory mcp serve
```

当前 MCP 工具包括：

### memory_search

搜索 approved / auto_approved memories。

### memory_context

根据 prompt 生成 Markdown context，并返回匹配项。

### memory_read

按 memory id 读取单条记忆。

### memory_write

提交候选记忆。写入会走统一 policy：

- 低风险候选可以 auto-approved；
- 高影响类型进入 review queue；
- 无效或敏感候选会被 discard。

## 9. 记忆 URI 模型

每条 memory 都有稳定 URI，例如：

```text
global://user/preferences
project://github.com/acme/app/testing
branch://github.com/acme/app/feature-login/state
path://github.com/acme/app/apps-web
tool://claude-code/notes
system://boot
```

URI 用于表示记忆的逻辑位置和作用范围，而不是文件路径。

当前支持 namespace：

```text
global
org
project
branch
path
tool
system
```

## 10. 记忆类型

当前设计支持的 memory type 包括：

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

不同类型会影响写入策略。

可自动写入的低风险类型包括：

```text
project_command
branch_state
task_todo
dependency_note
tool_note
pitfall
```

默认进入 review queue 的高影响类型包括：

```text
user_preference
workflow_rule
architecture_decision
api_contract
security_constraint
coding_style
testing_rule
```

## 11. 写入策略

`ai-memory` 使用半自动写入策略。

### Auto-write 条件

满足以下条件时，可以直接写入：

```text
risk = low
confidence >= 0.85
无敏感内容
无冲突
类型允许 auto-write
```

写入状态：

```text
auto_approved
```

### Review queue 条件

以下情况进入 review：

- 高影响类型；
- 低/中置信度；
- scope 不确定；
- 可能影响项目政策或用户行为；
- 与已有记忆冲突；
- 安全、架构、API、测试规则等敏感决策。

写入状态：

```text
proposed
```

## 12. 隐私保护

当前 redactor 支持识别和替换：

- Bearer token
- API key assignment
- password assignment
- private key block
- database URL password

示例：

```text
Authorization: Bearer abc+def/ghi=
```

会被替换为：

```text
Authorization: Bearer [REDACTED:BEARER_TOKEN]
```

敏感路径检测支持：

```text
.env
.env.*
*.pem
*.key
id_rsa
id_ed25519
credentials.json
.aws
.ssh
```

并且已做大小写不敏感处理。

## 13. 项目架构

当前源码结构大致如下：

```text
src/ai_memory/
  cli/
    main.py

  core/
    config.py
    models.py
    policy.py
    uri.py

  store/
    sqlite.py

  retrieval/
    environment.py
    ranking.py
    assembler.py

  extraction/
    transcript.py
    validator.py
    router.py
    providers/
      base.py
      command.py

  privacy/
    redactor.py
    sensitive_paths.py

  review/
    queue.py

  mcp/
    tools.py
    server.py

  adapters/
    base.py
    generic_transcript.py
    claude_code.py
    codex_cli.py
    gemini_cli.py

  wrappers/
    aiwrap.py
```

各层职责：

| 模块 | 职责 |
|---|---|
| `core` | 数据模型、URI、policy、config |
| `store` | SQLite 持久化、FTS、版本、source |
| `retrieval` | 环境检测、排序、上下文组装 |
| `extraction` | transcript 文本、candidate 校验、provider、路由 |
| `privacy` | secret redaction 和 sensitive path detection |
| `review` | JSONL review queue |
| `cli` | 命令行入口 |
| `mcp` | MCP 工具和 server |
| `adapters` | 不同 AI 工具 transcript 适配 |
| `wrappers` | wrapper prompt 构造 |

## 14. 已验证测试

最终完整单元测试已通过：

```text
py -m pytest tests/unit -v
74 passed
```

覆盖内容包括：

- config 初始化；
- URI parse/validation；
- policy routing；
- SQLite CRUD / FTS / version/source；
- privacy redaction；
- sensitive path detection；
- review queue；
- retrieval/context；
- CLI add/search/context；
- extraction pipeline；
- command extractor；
- MCP tools；
- adapters；
- aiwrap；
- CLI import/review/approve/reject。

## 15. 当前限制

当前 MVP 有一些明确限制：

1. 不会自动安装 Claude Code hook。
2. `import --archive-only` 只做原始归档，不做 redaction。
3. capture 命令还未实现。
4. doctor 命令还未实现。
5. extractor provider 已有接口和 command provider，但还没有默认 LLM extractor。
6. Codex/Gemini adapter 目前是基础 discovery + generic normalization。
7. 没有 Web dashboard。
8. 没有远程同步。
9. 没有多用户权限。
10. 没有强制 vector database。

## 16. 后续建议路线

后续可以按以下顺序继续增强：

### 1. 实现 capture 命令

目标：

```bash
ai-memory capture --client claude-code
```

能力：

- 找到最新 transcript；
- normalize；
- archive；
- redaction；
- extractor；
- route candidates；
- 输出统计。

### 2. 实现 extractor provider 配置

从 `config.yaml` 读取：

```yaml
extractor:
  provider: command
  command: ...
  max_input_chars: 60000
```

### 3. 接入 Claude Code hooks

提供文档或自动安装命令：

```bash
ai-memory hooks install claude-code
```

但需要非常谨慎，避免自动改用户配置。

### 4. 增强 transcript importer

支持：

- Claude Code JSONL 更完整格式；
- Codex CLI session 格式；
- Gemini CLI 历史格式；
- OpenCode / Cline / Cursor / Aider 等。

### 5. 实现 review approve 后写入 SQLite

当前 review queue 能 mark approve/reject。后续可增强为：

```bash
ai-memory approve <id>
```

批准后自动写入 SQLite，并生成 source/version。

### 6. 冲突检测和 dedupe

避免同类 memory 重复写入：

- URI-level dedupe；
- 内容相似度；
- type + scope + trigger 冲突检查。

### 7. 可选 embedding

在规则检索和 FTS 基础上增加 optional semantic search。

## 17. 一句话总结

`ai-memory` 当前已经是一个可运行、可测试、可扩展的本地优先 AI 编程记忆 MVP：它提供 SQLite 记忆库、CLI、MCP 工具、review queue、隐私 redaction、基础 transcript import、Claude/Codex/Gemini 适配器骨架，并已经完成完整测试和文档。
