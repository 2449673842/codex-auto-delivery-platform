# Project Memory Design

## Status

- Stage: S23.0 design only.
- Implementation: not started.
- Scope: project-level durable memory for handoff, evidence context, policies, runbooks, and recurring failure knowledge.
- Non-scope: backend API, frontend UI, database migration, provider call, Browser AI execution, repository write, GitHub / Sonar query, automatic repair execution.

## Product Goal

Project Memory is the stable project context layer for the platform. It should preserve the facts, policies, runbooks, handoff templates, and recurring lessons that repeatedly shape Codex / OMX / Browser AI / external AI work.

The user outcome is less repeated prompt construction and less manual context transfer. A user should be able to start a new task and have the platform provide a concise, source-backed memory packet:

- what this project is,
- how it is usually verified,
- what safety boundaries always apply,
- what failures have happened before,
- what delivery rules must be followed,
- which handoff templates are trusted,
- which memories may be stale and need review.

Project Memory does not execute code. It prepares durable context for humans and AI tools that perform the work.

## Why Project Memory Is Platform Core Value

Codex / OMX skills can execute a current SOP, but they do not automatically preserve the project's stable working memory across many tasks, PRs, repairs, and reviews. Evidence Board and Run Timeline make task evidence durable; Project Memory turns repeated evidence and user-confirmed policies into reusable context.

This is platform core value because the platform already links:

- project identity,
- task identity,
- evidence artifacts,
- run timeline events,
- repair attempts,
- skill review reports,
- delivery and safety decisions.

Project Memory is the next layer above evidence. It does not replace Codex. It reduces context loss before Codex starts.

## Boundary With Codex / OMX Skills

Codex / OMX skills answer "how should this task be done now?" Project Memory answers "what should the platform remember long term about this project?"

Skills are appropriate for:

- current task execution,
- PR / CI / Sonar review,
- one-shot investigation,
- repair handoff generation,
- current evidence reading,
- flexible judgment using live context.

Project Memory is appropriate for:

- stable project profile,
- repeatable verification policy,
- delivery rules,
- safety policy,
- recurring failures and known mitigations,
- handoff templates,
- user preferences,
- source-backed context packets for future AI runs.

The platform should not become a weaker Codex executor. It should remain the evidence layer and memory layer that gives Codex / OMX better starting context.

## Memory Type Taxonomy

### `project_profile`

Stable project identity and structure.

Fields should include:

- project name,
- project goal,
- technology stack,
- repository owner / name / branch conventions,
- main directory structure,
- key architecture notes,
- active product stage,
- source references.

Example content:

```json
{
  "memory_type": "project_profile",
  "summary": "AI automation delivery platform with FastAPI backend and Vue/Vite frontend.",
  "source_refs": ["AGENTS.md", "docs/roadmap/next-after-s18.md"],
  "confidence": "high",
  "stale": false
}
```

### `runbook`

Operational commands and local service assumptions. It must record requirements without saving secret values.

Fields should include:

- backend start command,
- frontend start command,
- common ports,
- required environment variable names without values,
- local service dependencies such as `sub2api` or Browser AI mock,
- setup notes,
- source references.

Rules:

- Do not save `.env` contents.
- Do not save API keys, cookies, sessions, passwords, or tokens.
- Environment variables may be listed by name only.

### `verification_policy`

Verification rules that define done for this project.

Must cover:

- targeted backend pytest,
- full backend pytest,
- `python -m compileall backend/app`,
- `npm build`,
- frontend display smoke,
- Browser AI mock smoke when Browser AI / Multi-AI paths are touched,
- SonarCloud Quality Gate,
- Security Hotspots,
- Duplication on New Code,
- New Issues,
- when frontend or backend verification may reasonably be skipped for docs-only changes.

### `delivery_policy`

Delivery process rules.

Must cover:

- one independent PR per stage,
- branch from latest master,
- do not directly push master,
- PR body must be Chinese,
- PR body must match GitHub reality,
- changed files must match scope,
- no automatic approve / merge,
- merge only after mastermind review,
- report latest master commit after merge.

### `safety_policy`

Persistent safety boundaries.

Must cover:

- do not read `.env`,
- do not read `secret_ref`,
- do not expose API keys, cookies, sessions, or passwords,
- do not access `Project.root_path` for real modification unless a future stage explicitly authorizes it,
- do not write real repositories unless a stage explicitly allows it,
- do not create PR / CI / Sonar / Deploy platform capability unless a stage explicitly allows it,
- do not automatically approve / merge / deploy,
- do not bypass Browser AI login or captcha,
- keep secret-like test fixtures runtime-composed when static analysis may flag them.

### `known_failure`

Recurring failure patterns and mitigation notes.

Must cover at least:

- Sonar hardcoded secret false positive in tests or fixtures,
- placeholder / worktree pointer file damage, such as a source file replaced by a one-line pointer,
- Browser AI selector failure,
- stable response timeout,
- missing `OPENAI_API_KEY`,
- GitHub TLS / proxy failure,
- Sonar duplication issue,
- accessibility issue.

Each known failure should record:

- symptom,
- affected area,
- likely cause,
- observed mitigation,
- source evidence,
- confidence,
- stale flag.

### `user_preference`

User and mastermind preferences that should shape future handoffs.

Must cover:

- Chinese PR body,
- complete one frontend/backend loop per conversation when the stage includes both,
- merge only after mastermind review,
- conservative staged delivery,
- platform positioning as evidence layer / memory layer,
- do not build a weak Codex replacement,
- report concrete validation evidence and latest head commit.

### `handoff_template`

Reusable templates for AI and human handoff.

Must cover:

- Codex development task template,
- OMX controlled worker template,
- PR review template,
- Repair handoff template,
- Browser AI provider run template.

Each template should include:

- intended target,
- required inputs,
- safety boundaries,
- expected output format,
- verification requirements,
- source references,
- stale flag.

## Memory Sources

Project Memory can come from:

- manual user input,
- PR body,
- Evidence Board,
- Run Timeline,
- TaskArtifact,
- TaskEvent,
- Repair Attempt,
- Skill Review Report,
- `AGENTS.md`,
- `docs/roadmap`,
- `docs/design`,
- `docs/strategy`.

The source must remain visible. Memory without a source reference should be treated as lower confidence.

## Memory Lifecycle

Recommended lifecycle:

1. Candidate memory is proposed from a clear source.
2. User or mastermind confirms the memory or marks it as rejected.
3. Confirmed memory becomes active with `updated_at`, `confidence`, and `source_refs`.
4. Memory is used to build handoff packets, context summaries, and policy reminders.
5. Stale signals mark memory for review.
6. Reviewed memory is updated, superseded, archived, or rejected.

Suggested states:

- `candidate`
- `active`
- `stale`
- `superseded`
- `archived`
- `rejected`

Memory should prefer append-and-supersede semantics over silent overwrite when the old value explains earlier decisions.

## Memory Write Strategy

S23 first implementation should be conservative.

Rules:

- First version does not automatically scan the code repository to generate memory.
- First version does not read `.env`.
- First version does not read `secret_ref`.
- First version does not save secret values.
- First version does not automatically trust AI output.
- Memory writes require user confirmation or an explicit trusted source.
- Every memory item needs source references.
- Every memory item needs `updated_at`.
- Every memory item needs `confidence`.
- Every memory item needs a `stale` marker.
- Secret-like content must be redacted before persistence.

The platform can propose memory candidates later, but the user should control whether a candidate becomes active memory.

## Memory Update Strategy

Memory becomes risky when it is true historically but wrong operationally. Update strategy should make staleness visible.

Stale triggers can include:

- verification commands changed,
- framework or package changed,
- directory structure changed,
- delivery rules changed,
- repeated contradiction by recent PR body or mastermind review,
- failed handoff caused by stale memory,
- user marks a memory as outdated.

Update flow should:

- show old value,
- show proposed new value,
- show source references for the change,
- preserve previous memory as superseded when useful,
- require explicit confirmation for active memory updates.

## Usage Scenarios

Project Memory should support:

- automatically generating Codex / OMX handoff packets,
- reducing repeated prompt text,
- giving Browser AI / Multi-AI Evidence Run stable project context,
- explaining why a verification command must run,
- recording common failures and their mitigations,
- helping users understand project rules weeks later,
- exposing stable context to external AI through future MCP / Skill Adapter,
- reminding future PR authors about safety boundaries,
- helping Evidence Board summaries link repeated failures to known failure memories.

## Relationship With Evidence Board / Timeline

Evidence Board and Run Timeline answer: "what happened in this task?"

Project Memory answers: "what should remain true or reusable across tasks?"

Intended flow:

```text
Task execution / review / repair produces evidence
-> Evidence Board stores and displays task evidence
-> user identifies stable lesson or policy
-> Project Memory stores source-backed durable memory
-> future handoff packets include relevant memory
```

Memory should link back to evidence ids when the memory came from a task. Evidence remains the raw support; memory is the curated reusable statement.

## Relationship With MCP / Skill Adapter

Project Memory should become a stable context source for future MCP / Skill Adapter work.

Possible future reads:

- Codex skill asks for project profile and delivery policy.
- OMX controlled worker receives safety policy and verification policy.
- Browser AI prompt includes project profile and relevant known failures.
- Multi-AI Evidence Run receives concise memory-backed context.
- External AI receives memory excerpts through a read-only adapter.

Boundaries:

- MCP / Skill Adapter should read curated memory, not raw secrets.
- Memory export should be redacted and scoped.
- External AI should receive only the memory needed for the task.
- Memory export should not imply execution authority.

## S23 MVP Scope

S23.1 / S23.2 should first implement a small read-only memory surface:

- memory schema for the taxonomy above,
- read-only API for project memory summary,
- seedable or manually maintained memory records,
- source references,
- `updated_at`,
- `confidence`,
- `stale`,
- redacted content only,
- TaskDetail or Project page display.

MVP should favor simple, auditable records over automatic inference.

## S23 Non-Scope

S23 does not do:

- automatic code execution,
- repository writes,
- reading `.env`,
- reading `secret_ref`,
- saving secret values,
- provider calls,
- Browser AI execution,
- automatic repo scanning for memory generation,
- automatic trust of AI output,
- automatic memory mutation without confirmation,
- GitHub / Sonar active querying,
- PR / CI / Sonar / Deploy platform capability creation,
- automatic approve / merge / deploy,
- Codex / OMX replacement,
- infinite repair loop.

## Backend Design Notes For Later Phases

S23.0 does not implement APIs. Later phases can consider:

```text
GET /api/projects/{project_id}/memory
GET /api/projects/{project_id}/memory/summary
POST /api/projects/{project_id}/memory/candidates
POST /api/projects/{project_id}/memory/{memory_id}/confirm
POST /api/projects/{project_id}/memory/{memory_id}/mark-stale
```

Only the read-only endpoints belong in S23.1. Candidate and confirmation flows should wait until the schema and review UX are clear.

## Suggested Memory Item Shape

Design-only example:

```json
{
  "memory_id": 42,
  "project_id": 1,
  "memory_type": "verification_policy",
  "title": "Frontend display smoke is required for TaskDetail UI changes",
  "summary": "Run npm build and frontend display smoke when TaskDetail UI is changed.",
  "content": {
    "commands": ["npm.cmd run build", "node tests/s4-display.cjs"]
  },
  "source_refs": [
    {
      "source_type": "docs",
      "path": "AGENTS.md"
    },
    {
      "source_type": "pr_body",
      "pr_number": 55
    }
  ],
  "confidence": "high",
  "stale": false,
  "updated_at": "2026-05-27T00:00:00Z"
}
```

## Safety Boundaries

For S23.0:

- Project Memory implementation: no, design only.
- Memory API: no, design only.
- Memory UI: no, design only.
- Database migration: no.
- Provider call: no.
- Browser AI open: no.
- Shell / subprocess execution as product behavior: no.
- `.env` / `secret_ref` read: no.
- Project.root_path access: no.
- AgentRun / TaskArtifact / TaskEvent write: no.
- Real repository write: no.
- GitHub / Sonar query as product behavior: no.
- GitHub PR / CI / Sonar / Deploy platform capability: no.
- Automatic approve / merge: no.

For later S23 implementation, these boundaries remain unless a future design explicitly changes them and passes mastermind review.

## Roadmap

### S23.0 — Project Memory Design

Create this design document and the strategy comparison with agent skills. No implementation.

### S23.1 — Project Memory Read-Only Schema / API

Define the read model and return curated memory summaries. Keep it read-only and redacted.

### S23.2 — TaskDetail / Project Page Memory UI

Display project profile, runbook, policies, known failures, preferences, and templates. Show source references, confidence, stale status, and safety notes.

### S23.3 — Memory-Backed Handoff Packet

Use selected active memory to generate Codex / OMX / Browser AI / Multi-AI context packets. This should prepare context only; it should not execute repair or write code.

### S23.4 — Memory Stale Review / Update Flow

Add candidate review, stale marking, and explicit confirmation for updates. Avoid automatic mutation of active memory without user confirmation.
