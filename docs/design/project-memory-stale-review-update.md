# Project Memory Stale Review / Update Flow Design

## Status

- Stage: S23.4 design only.
- Implementation: not started.
- Scope: conservative stale review, candidate review, confirmation, supersede, archive, and reject flow for Project Memory.
- Non-scope: backend API, frontend UI, database migration, automatic memory writing, provider call, Browser AI execution, repository scan, GitHub / Sonar query.

S23.4 design-only PR does not implement any APIs, UI, database table, stale update flow, or automatic memory mutation.

## Product Goal

S23.4 defines how Project Memory changes safely over time.

Project Memory is valuable only if it is stable, source-backed, and trusted. It is also dangerous if old verification commands, delivery rules, safety boundaries, or runbooks silently remain active after the project changes. The stale review / update flow should let the platform show that a memory may be outdated, propose a replacement, preserve source references, and require a human confirmation before active memory changes.

The user outcome is:

- stale memory is visible before it damages a handoff,
- updates are reviewable and reversible,
- old memory is retained for audit instead of silently overwritten,
- secret values never enter memory,
- AI output can propose candidates but cannot directly become active memory.

## Why Memory Update Must Be Conservative

Memory is used to shape future Codex / OMX / Browser AI / external AI handoffs. A wrong memory item can repeatedly mislead later work. The highest-risk memories are not code snippets; they are policies and boundaries:

- safety policy,
- delivery policy,
- verification policy,
- runbook commands,
- known failure mitigations,
- user preferences.

For that reason:

- Project Memory must not automatically trust AI output.
- PR bodies, skill reports, and timeline evidence can propose candidates, but cannot silently update active memory.
- Memory updates need source references and explicit user confirmation.
- Stale markers need a reason.
- Supersede keeps the old record for audit; it does not physically delete it.
- Secret values are always redacted and rejected before persistence.

## Lifecycle

Recommended lifecycle:

```text
candidate
-> active
-> stale
-> superseded
-> archived

candidate
-> rejected

active
-> archived

stale
-> active
```

### `candidate`

A proposed memory item or proposed update. It may come from manual user input, a PR body, Evidence Board, Timeline, TaskArtifact, TaskEvent, Repair Attempt, Skill Review Report, or docs. It is not used by handoff packets until confirmed.

Required fields:

- `memory_type`
- `title`
- `summary`
- `content`
- `source_refs`
- `confidence`
- `created_at`
- `proposed_by`
- `redaction_status`

### `active`

A confirmed memory item used by memory summaries, Project Memory UI, and memory-backed handoff packets.

Required fields:

- `memory_id`
- `memory_type`
- `title`
- `summary`
- `content`
- `source_refs`
- `confidence`
- `updated_at`
- `stale=false`

### `stale`

An active memory that may no longer be safe to rely on. Stale memory can still be shown, but handoff packets must mark it as stale and advise verification before acting.

Required additional fields:

- `stale=true`
- `stale_reason`
- `stale_marked_at`
- `stale_source_refs`

### `superseded`

A memory replaced by a newer confirmed memory. The old memory remains visible for audit and explanation.

Required additional fields:

- `superseded_by`
- `superseded_at`
- `supersede_reason`

### `archived`

A memory intentionally removed from active use without a direct replacement. Archived memories are retained for audit.

Required additional fields:

- `archived_at`
- `archive_reason`

### `rejected`

A candidate that was reviewed and not accepted.

Required additional fields:

- `rejected_at`
- `rejected_reason`

## State Transitions

Allowed transitions:

| From | To | Rule |
| --- | --- | --- |
| `candidate` | `active` | Human confirms candidate after reviewing source refs and redaction. |
| `candidate` | `rejected` | Human rejects candidate or it fails safety checks. |
| `active` | `stale` | Human marks stale, or a future detector proposes stale and human confirms. |
| `stale` | `active` | Human confirms existing memory is still valid. |
| `stale` | `superseded` | Human confirms a replacement memory. |
| `active` | `superseded` | Human confirms direct replacement. |
| `active` | `archived` | Human archives without replacement. |
| `stale` | `archived` | Human archives stale memory without replacement. |

Disallowed transitions:

- `candidate` directly to `superseded`
- `rejected` back to `active`
- physical deletion as a normal user action
- automatic update from AI output to `active`
- automatic update from PR body to `active`

## Which Memory Can Be Marked Stale

Any active memory can be marked stale when there is a source-backed reason.

High-priority stale candidates:

- `runbook`: command, port, local service, or environment variable names changed.
- `verification_policy`: test/build/Sonar requirements changed.
- `delivery_policy`: branch, PR body, review, or merge rules changed.
- `safety_policy`: safety boundary wording changed by explicit mastermind decision.
- `known_failure`: mitigation no longer applies.
- `handoff_template`: target output format or required sections changed.
- `project_profile`: technology stack or directory structure changed.
- `user_preference`: user explicitly changes a preference.

## Which Memory Can Be Updated

Update is allowed only after confirmation and source review.

Normally updatable:

- `project_profile`
- `runbook`
- `verification_policy`
- `known_failure`
- `handoff_template`
- `user_preference`

High-friction updates:

- `delivery_policy`
- `safety_policy`

These two should require explicit user or mastermind confirmation. They should not be updated from PR body, AI output, or inferred evidence alone.

## Which Memory Is Forbidden To Auto-Update

The platform must not automatically update:

- safety boundaries,
- delivery rules,
- auto approve / merge / deploy policy,
- secret handling policy,
- repository write policy,
- provider execution policy,
- `.env` / `secret_ref` policy,
- `Project.root_path` policy,
- user preferences,
- any memory that contains unredacted secret-like content.

AI output, Browser AI answers, PR bodies, and Skill Review Reports may create candidate proposals only. They cannot directly mutate active memory.

## Source, Confidence, And Audit Fields

Each memory record should include:

```json
{
  "memory_id": "default-verification-policy",
  "memory_type": "verification_policy",
  "status": "active",
  "title": "Verification policy",
  "summary": "Backend changes require targeted pytest, full pytest, and compileall.",
  "content": {},
  "source_refs": [
    {
      "source_type": "docs",
      "path": "AGENTS.md"
    }
  ],
  "confidence": "high",
  "updated_at": "2026-05-29T00:00:00Z",
  "stale": false,
  "stale_reason": "",
  "superseded_by": null,
  "redaction_status": {
    "redaction_applied": true,
    "truncated": false,
    "max_chars": 4000
  }
}
```

Field rules:

- `source_refs` is required for candidates and active memory.
- `confidence` should be `low`, `medium`, or `high`.
- `updated_at` changes only when active memory is confirmed or superseded.
- `stale_reason` is required when `stale=true`.
- `superseded_by` is required when status is `superseded`.
- `redaction_status` must be present for user-visible content.

## Future API Draft

S23.4 design-only PR does not implement these APIs.

Possible future endpoints:

```text
POST /api/projects/{project_id}/memory/candidates
POST /api/projects/{project_id}/memory/{memory_id}/confirm
POST /api/projects/{project_id}/memory/{memory_id}/mark-stale
POST /api/projects/{project_id}/memory/{memory_id}/supersede
GET /api/projects/{project_id}/memory/stale-review
```

### Candidate Creation

`POST /api/projects/{project_id}/memory/candidates`

Purpose: create a proposed memory record from explicit user input or a selected evidence source.

Required constraints:

- redacts content before saving,
- rejects secret-like values,
- requires `source_refs`,
- does not activate the candidate,
- does not scan repository files,
- does not read `.env`,
- does not read `secret_ref`.

### Confirm Candidate

`POST /api/projects/{project_id}/memory/{memory_id}/confirm`

Purpose: make a reviewed candidate active.

Required constraints:

- only candidate records can be confirmed,
- human confirmation is required,
- policy memories require explicit confirmation text,
- old active memory of the same type may be superseded only if requested.

### Mark Stale

`POST /api/projects/{project_id}/memory/{memory_id}/mark-stale`

Purpose: mark a memory as stale with a reason.

Required constraints:

- requires `stale_reason`,
- preserves the memory content,
- handoff packets must show stale warning.

### Supersede

`POST /api/projects/{project_id}/memory/{memory_id}/supersede`

Purpose: replace an active or stale memory with a confirmed new memory.

Required constraints:

- preserves old memory,
- sets `superseded_by`,
- links source refs for the replacement,
- requires confirmation.

### Stale Review

`GET /api/projects/{project_id}/memory/stale-review`

Purpose: show active stale memory, candidate replacements, and evidence links for review.

## Future UI Draft

S23.4 design-only PR does not implement this UI.

Suggested Project Memory UI additions:

- Stale Review tab.
- Candidate list grouped by memory type.
- Active memory vs proposed memory side-by-side.
- Source refs panel.
- Redaction status panel.
- Confidence selector.
- Stale reason input.
- Confirm, reject, mark stale, supersede, archive actions.
- Warning banner for `delivery_policy` and `safety_policy` updates.

The UI must always show:

- Project Memory update requires human confirmation.
- Memory may be stale; verify before acting.
- Secret values are never allowed.
- The platform does not execute code or write repositories.

## S23.4 MVP Scope

Future S23.4 MVP may include:

- candidate creation from explicit user input or selected evidence ids,
- read-only stale review list,
- mark stale with required `stale_reason`,
- confirm candidate into active memory,
- supersede while preserving old memory,
- archive without physical delete,
- redaction and truncation for all memory content,
- source refs display,
- tests proving no provider, Browser AI, shell, repository write, GitHub, or Sonar call.

## S23.4 Non-Scope

S23.4 must not do:

- automatic memory generation from repository scan,
- automatic memory update from AI output,
- automatic memory update from PR body,
- automatic update of delivery policy or safety policy,
- `.env` read,
- `secret_ref` read,
- secret value persistence,
- `Project.root_path` scan,
- GitHub / Sonar active query,
- provider call,
- Browser AI execution,
- shell / subprocess execution,
- repository write,
- PR / CI / Sonar / Deploy platform capability,
- automatic approve / merge / deploy.

## Safety Boundaries

For this design-only PR:

- S23.4 memory update implementation: no.
- Memory write API: no.
- Memory UI: no.
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
