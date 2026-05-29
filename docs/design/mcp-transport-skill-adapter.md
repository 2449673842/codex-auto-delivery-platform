# MCP Transport / Skill Adapter Design

## Status

- Stage: S24.0 design only.
- Implementation: not started.
- Scope: future MCP transport and skill adapter design for exporting read-only project context.
- Non-scope: MCP server implementation, stdio transport implementation, HTTP / SSE transport implementation, Codex skill adapter implementation, provider call, Browser AI execution, repository write, GitHub / Sonar query.

S24.0 design-only PR does not implement an MCP server, transport, skill adapter, API, UI, database migration, or execution capability.

## Product Goal

S24 makes the platform usable as a read-only context provider for external AI tools.

The platform already stores durable memory, evidence, timeline, repair context, and handoff packets. Codex / OMX / Browser AI / external AI can do better work when they can retrieve this context through a stable adapter instead of relying on manual prompt copying.

The first S24 product goal is read-only context export:

- expose Project Memory,
- expose Evidence Board,
- expose Run Timeline,
- expose Handoff previews,
- expose Repair Handoff previews,
- expose artifact summaries and repair attempt summaries,
- keep all output redacted, bounded, source-linked, and non-executable.

S24 is not a platform executor.

## Why MCP Transport / Skill Adapter

MCP and skill adapters provide a standard way for AI tools to ask for context. They are a better fit than building many bespoke integrations because the platform value is already in its stored memory and evidence.

The adapter should let external AI ask:

- What is this project?
- What safety policy applies?
- What evidence exists for this task?
- What happened in the timeline?
- What handoff packet should I read?
- What repair attempts already exist?

The adapter should not let external AI:

- run shell,
- modify repositories,
- create PRs,
- merge or approve,
- deploy,
- call providers,
- open Browser AI,
- read secrets.

## Current Context Assets

S24 builds on existing platform assets:

- Evidence Board: task-level evidence summaries and linked ids.
- Run Timeline: chronological task events and normalized source records.
- Project Memory: project-level profile, runbook, verification, delivery, safety, known failure, user preference, and handoff template memory.
- Memory-backed Handoff: AI and repair handoff previews with Project Memory context.
- Multi-AI Evidence Run: broadcast/routed evidence collection records and artifacts.
- Repair Packet / Repair Attempt: controlled repair evidence, handoff packet, attempt timeline, and imported verification result.
- Browser AI answer artifacts: web AI answers preserved as artifacts.
- Answer Synthesis: rule-based synthesis across dispatch jobs and artifacts.

These assets justify read-only context export. They do not justify execution authority.

## Product Positioning

S24 does not make the platform a weak Codex.

Codex / OMX / Browser AI / external AI remain responsible for current task reasoning and execution. The platform provides:

- memory,
- evidence,
- timeline,
- handoff packets,
- redacted context,
- audit links.

The first adapter should export context, not execute work.

## Read-Only First Version

S24 MVP should only expose read-only resources and tools:

- read-only Project Memory,
- read-only Project Memory summary,
- read-only task timeline,
- read-only Evidence Board,
- read-only AI handoff preview,
- read-only Repair Handoff preview,
- read-only task artifact summaries,
- read-only recent repair attempts.

Every response should include or preserve:

- read-only status,
- persisted status where applicable,
- source ids or source refs,
- redaction status,
- truncation status,
- safety notes.

## Stdio MCP Server Design

Future stdio MCP server shape:

```text
external AI client
-> local MCP stdio process
-> platform read-only service layer
-> redacted context response
```

The stdio server should:

- run locally,
- require explicit project/task ids,
- expose resources and tools mapped to existing read-only API/service functions,
- never access `Project.root_path`,
- never read `.env`,
- never read `secret_ref`,
- never shell out to run verification,
- never create or mutate business records unless a future user-confirmed import flow explicitly allows it.

The stdio process can be packaged later as a small adapter around existing FastAPI service logic or local HTTP calls. S24.0 does not choose the implementation mechanism.

## HTTP / SSE Transport Design

Future HTTP / SSE transport can support clients that cannot spawn stdio servers.

Design principles:

- authentication required,
- project/task authorization checks required,
- response budgets required,
- redaction and truncation required,
- no execute tools in MVP,
- no provider or Browser AI calls through transport,
- no GitHub / Sonar active queries through transport.

Possible endpoints for a future MCP-compatible HTTP bridge:

```text
GET /mcp/resources
POST /mcp/tools/call
GET /mcp/events
```

S24.0 does not implement these endpoints.

## Codex Skill Adapter Design

A Codex skill adapter should be a thin SOP wrapper that teaches Codex how to request platform context and how to use it safely.

Skill responsibilities:

- ask for project memory summary before a large task,
- ask for task timeline and evidence board before repair or review,
- request memory-backed handoff preview when switching agents,
- cite source ids in its report,
- treat stale memory as a warning,
- follow current task scope and PR boundary.

Skill non-responsibilities:

- no direct memory writes,
- no repository write through the platform,
- no execute command through the platform,
- no auto approve / merge / deploy,
- no hidden provider or Browser AI call.

The skill should prefer existing platform read-only endpoints/tools and should not invent new execution authority.

## Claude Desktop / Cursor Integration Draft

Future local integration can provide examples for:

- Claude Desktop MCP config using stdio transport.
- Cursor MCP config using stdio or HTTP transport.
- Local-only auth token or loopback allowlist.
- Project id and task id examples.
- Troubleshooting redaction/truncation and stale memory warnings.

Example conceptual config:

```json
{
  "mcpServers": {
    "codex-auto-delivery-platform": {
      "command": "platform-mcp",
      "args": ["--base-url", "http://localhost:8000", "--read-only"]
    }
  }
}
```

This is design-only; no binary, command, or config is implemented in S24.0.

## Tools / Resources Taxonomy

### Read-Only Tools Draft

S24 MVP read-only tools can include:

```text
get_project_memory
get_project_memory_summary
get_task_timeline
get_task_evidence_board
preview_ai_handoff
preview_repair_handoff
get_task_artifacts_summary
get_recent_repair_attempts
```

Tool rules:

- require explicit ids,
- return bounded output,
- redact secret-like content,
- never call provider,
- never execute shell,
- never write repository,
- never query GitHub or Sonar,
- never mutate memory or task state.

### Resource Draft

Potential resources:

```text
project://{project_id}/memory
project://{project_id}/memory-summary
task://{task_id}/timeline
task://{task_id}/evidence-board
task://{task_id}/artifacts
task://{task_id}/repair-attempts
```

Resources should be read-only snapshots. They should not imply live execution or external API lookup.

## Explicit Non-MVP Tools

S24 MVP must not include:

```text
execute_code
write_repository
create_pr
merge_pr
approve_pr
deploy
run_shell
read_env
read_secret_ref
browser_ai_execute
```

If a later design considers any execute-like tool, it must be a separate stage with explicit threat model, permissions, audit, user confirmation, and mastermind review.

## Authentication / Authorization

Future transport must define:

- local-only default,
- optional auth token for HTTP / SSE,
- no token values in logs,
- no token values in memory,
- project-level authorization checks,
- task-level authorization checks,
- clear errors when a client lacks access.

Stdio local transport may rely on local process permissions initially, but HTTP / SSE should not.

## Safety, Redaction, And Truncation

Every MCP or skill adapter response must:

- redact API keys, cookies, sessions, passwords, and token-like values,
- avoid returning `.env` contents,
- avoid returning `secret_ref` values,
- avoid returning `Project.root_path`,
- include truncation metadata when budgets apply,
- include source ids or source refs,
- include safety notes for handoff responses,
- treat stale memory as a warning.

Transport must not introduce a bypass around existing service-level redaction.

## S24 MVP Scope

Future S24.1 MVP may implement:

- local read-only MCP resources/tools,
- Project Memory summary resource,
- task timeline resource,
- evidence board resource,
- handoff preview tools,
- repair handoff preview tool,
- artifact summary tool,
- repair attempt summary tool,
- response budget and truncation,
- redaction tests,
- no-write/no-execute safety tests.

## S24 Non-Scope

S24 does not do:

- platform executor,
- weak Codex replacement,
- generic agent runtime,
- code execution,
- shell / subprocess,
- repository write,
- Browser AI execution,
- provider call,
- GitHub PR / CI / Sonar / Deploy operation,
- approve / merge / deploy,
- reading `.env`,
- reading `secret_ref`,
- accessing `Project.root_path` for real modification,
- automatic memory update,
- automatic repair loop implementation.

## Roadmap

### S24.0 — MCP Transport / Skill Adapter Design

Create this design and the strategy document. No implementation.

### S24.1 — Read-Only MCP Resources / Tools

Expose the read-only tools/resources listed above with redaction, truncation, and no-write tests.

### S24.2 — Codex Skill Adapter Docs / Example

Document how Codex should retrieve platform context and use it in handoff, repair, and review workflows.

### S24.3 — Claude Desktop / Cursor Local Integration Example

Provide local configuration examples and troubleshooting notes.

### S24.4 — Optional Authenticated HTTP / SSE Transport

Add authenticated HTTP / SSE transport only if stdio/local usage proves useful and safe.

## Safety Boundaries

For this design-only PR:

- MCP server implementation: no.
- stdio transport implementation: no.
- HTTP / SSE transport implementation: no.
- Codex skill adapter implementation: no.
- Backend API implementation: no.
- Frontend UI implementation: no.
- Database migration: no.
- Provider call: no.
- Browser AI open: no.
- Shell / subprocess execution as product behavior: no.
- `.env` / `secret_ref` read: no.
- Project.root_path access: no.
- AgentRun / TaskArtifact / TaskEvent write: no.
- Project / Task modification: no.
- Real repository write: no.
- GitHub / Sonar query as product behavior: no.
- GitHub PR / CI / Sonar / Deploy platform capability: no.
- Automatic approve / merge: no.
