# Platform As Memory And Context Layer

## Decision

The platform's durable position is:

```text
Memory / Evidence / Handoff / Context Layer
```

It should not become a general Agent Runtime, a weak Codex clone, or a complex automatic execution system. Codex / OMX / Browser AI / external AI should do current task reasoning and execution. The platform should keep long-lived memory, task evidence, timeline, and handoff packets so those tools start with better context and leave better audit trails.

## Division Of Responsibilities

### Codex

Codex owns:

- code implementation,
- local reasoning over repository files,
- tests and verification when authorized by the task,
- PR preparation,
- repair execution outside the platform,
- applying current task instructions.

Codex should receive platform context, but the platform should not try to become Codex.

### OMX

OMX owns:

- controlled workflows,
- multi-agent coordination,
- skill execution,
- structured review and repair SOPs,
- team-style task decomposition when useful.

OMX can use Project Memory and Evidence Board as context. It should not require the platform to implement an execution runtime.

### Browser AI

Browser AI owns:

- collecting webpage AI answers when explicitly run by an allowed path,
- producing answer artifacts,
- providing additional evidence for Multi-AI Evidence Run.

The platform stores Browser AI outputs and safety notes. It should not open Browser AI from S24 context export.

### External AI

External AI tools such as Claude Desktop, Cursor, or other local clients can consume read-only context through future MCP / Skill Adapter work.

They should receive:

- Project Memory,
- Evidence Board,
- Run Timeline,
- handoff previews,
- repair handoff previews.

They should not receive execution authority through the first adapter.

## What Skills Own

Skills own "what to do now":

- PR / CI / Sonar review SOP,
- repair handoff review,
- current changed-file inspection,
- live comparison of claims vs evidence,
- current tool-specific execution procedure,
- current recommendation.

Skills are procedural and situational. They can adapt to a specific task and produce a current verdict.

## What The Platform Owns

The platform owns "what should remain durable":

- Project Memory,
- Evidence Board,
- Run Timeline,
- AgentRun and TaskArtifact records,
- Multi-AI Evidence Run artifacts,
- Answer Synthesis,
- Failure Evidence,
- Repair Packet,
- Repair Attempt Timeline,
- Skill Review Report artifacts when imported,
- Memory-backed Handoff packets.

This is the long-term system of record. It should be queryable and reusable across tasks.

## Why Not A General Agent Runtime

A general Agent Runtime would require:

- broad execution permissions,
- sandbox design,
- filesystem write authority,
- subprocess orchestration,
- credential management,
- external API operations,
- failure recovery,
- auditing,
- permission UI,
- security review.

That is a different product and a larger risk surface. The current platform already creates value without it by making memory and evidence durable. Execution should remain with Codex / OMX unless a future stage defines a narrow, reviewed capability.

## Why Not A Complex Automatic Executor

Complex automatic execution would blur the current safety boundary:

- repository write,
- shell execution,
- Browser AI execution,
- provider calls,
- PR creation,
- CI / Sonar operations,
- auto approve / merge / deploy.

The project has repeatedly chosen conservative staged delivery. S20 established controlled repair with human execution and imported verification results. S21 kept PR / CI / Sonar reading skill-first. S22 and S23 built evidence and memory layers. S24 should preserve that direction.

## Why S24 Starts With Read-Only Context Export

Read-only context export has high value and low risk:

- Codex / OMX receive better starting context.
- Browser AI and external AI can understand project policies.
- Evidence and memory become reusable outside the web UI.
- No new write path is needed.
- No new execution permission is needed.
- Existing redaction and truncation patterns can be reused.

The first S24 version should prove:

- context can be retrieved reliably,
- output is bounded,
- secrets are redacted,
- stale memory is visible,
- source refs and linked ids survive export,
- external AI can use the context without platform execution.

## When To Consider Pipeline / Execute Capabilities

Pipeline or execute-like capabilities should be considered only after:

- read-only MCP tools are stable,
- Project Memory stale review is safe,
- Evidence Board and Timeline have enough data to audit outcomes,
- permissions and audit model are designed,
- repository write boundaries are explicit,
- rollback and failure handling are documented,
- user confirmation is built into every high-risk action,
- mastermind review approves a narrow stage.

Even then, execute capability should be narrow and specific. It should not appear as a generic `run_shell` or `write_repository` tool.

## Strategy Summary

Preferred direction:

```text
Skills execute current SOP
Codex / OMX perform implementation and review
Browser AI supplies external AI evidence
Platform stores memory, evidence, timeline, and handoff context
MCP / Skill Adapter exports read-only context first
```

Rejected direction:

```text
Platform becomes generic agent runtime
Platform gets broad shell/repository/API execution
Platform tries to replace Codex
Platform performs automatic repair loops
```

The platform should make AI work more grounded, traceable, and less repetitive. It should not multiply execution surfaces before the memory and evidence layer is fully reliable.

## Safety Boundary

This strategy does not authorize:

- memory write implementation,
- MCP server implementation,
- Codex skill adapter implementation,
- HTTP / SSE transport implementation,
- provider calls,
- Browser AI execution,
- shell / subprocess execution,
- `.env` or `secret_ref` read,
- Project.root_path access,
- repository writes,
- GitHub / Sonar active queries,
- PR / CI / Sonar / Deploy operations,
- automatic approve / merge / deploy.
