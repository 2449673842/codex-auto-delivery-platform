# Project Memory vs Agent Skill

## Decision

Project Memory and Codex / OMX skills should remain separate surfaces.

- Skills handle how to perform the current task.
- Project Memory handles what the platform should remember long term.

The platform should not replace Codex execution. It should provide stable, source-backed context that makes Codex / OMX / Browser AI / Multi-AI work more consistent and less repetitive.

## What Skills Own

Skills are best for current, procedural work:

- run a PR / CI / Sonar review SOP,
- inspect current changed files,
- compare claimed verification with observed evidence,
- generate a repair handoff,
- ask Browser AI or Multi-AI providers for current analysis,
- produce a bounded recommendation for the current task.

Skills can adapt to live context and external state. They are allowed to reason flexibly, challenge assumptions, and produce a current verdict.

## What Project Memory Owns

Project Memory is best for stable, reusable context:

- project profile,
- runbook,
- verification policy,
- delivery policy,
- safety policy,
- known failures,
- user preferences,
- handoff templates.

Memory should be source-backed, redacted, timestamped, confidence-scored, and explicitly marked stale when needed.

## Why The Split Matters

If the platform tries to turn every skill workflow into a first-class platform feature, it becomes a weaker Codex and grows brittle integrations too early. If everything stays inside skills, the platform loses durable memory, cross-task retrieval, and long-term evidence value.

The hybrid model is:

```text
Skill reads / reasons / reviews / drafts
-> platform stores confirmed evidence and memory
-> future skill runs receive concise memory-backed context
```

This keeps live judgment in Codex / OMX while making stable project knowledge durable.

## Relationship With Evidence Board

Evidence Board stores task-level facts: artifacts, timeline events, repair attempts, verification results, and skill review reports.

Project Memory stores project-level durable conclusions extracted from confirmed evidence or explicit user input.

Examples:

- Evidence: "PR #51 old head had a service file replaced by a one-line placeholder."
- Memory: "Known failure: placeholder / worktree pointer file damage must be checked by inspecting real diff for high-risk files."

- Evidence: "PR #55 frontend UI change ran npm build and frontend smoke."
- Memory: "Verification policy: TaskDetail UI changes require npm build and frontend display smoke."

## How Skills Should Use Memory

A skill should receive only the memory needed for the current task.

Recommended packet sections:

- project profile summary,
- relevant delivery policy,
- relevant safety policy,
- verification policy for changed area,
- known failures relevant to the task,
- handoff template for the target role.

The packet should include source references and stale flags. A stale memory should be treated as a warning, not a command.

## Safety Boundary

Project Memory must not:

- read `.env`,
- read `secret_ref`,
- save API keys, cookies, sessions, passwords, or token values,
- query GitHub / Sonar automatically,
- execute shell / subprocess as product behavior,
- write a real repository,
- create PR / CI / Sonar / Deploy platform capability,
- automatically approve / merge / deploy,
- claim that Codex or OMX performed changes.

Project Memory should:

- store redacted stable context,
- keep source references,
- expose read-only summaries,
- help users and AI tools start with better context,
- preserve the platform as evidence layer and memory layer.
