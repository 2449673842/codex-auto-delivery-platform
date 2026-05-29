# Browser AI Mastermind Review Versus MCP

## Decision

S24 should move Browser AI Mastermind Review Trial ahead of read-only MCP tools.

MCP remains part of the roadmap, but the next priority is to validate the review loop:

```text
platform evidence -> GPT mastermind review -> structured verdict -> stored evidence -> human decision
```

This better matches the original platform ambition of automatic review support without crossing into automatic approve, merge, deploy, or repair.

## What Browser AI Mastermind Review Solves

Browser AI Mastermind Review Trial tests whether a web GPT mastermind can review a platform-generated PR / task packet and return a structured verdict.

It focuses on:

- PR / task review quality,
- packet completeness,
- claim versus evidence checking,
- review verdict parsing,
- advisory review artifact design,
- Evidence Board and Run Timeline integration.

It does not focus on external tool interoperability.

## What MCP Solves

MCP solves external context access.

It lets tools such as Codex, Claude Desktop, Cursor, or other local AI clients retrieve platform context:

- Project Memory,
- Evidence Board,
- Run Timeline,
- AI Handoff previews,
- Repair Handoff previews,
- artifact summaries,
- repair attempt summaries.

MCP is the right mechanism when an external AI needs to ask the platform for context. It is not, by itself, a review workflow.

## Why The Review Trial Comes First

The project already has:

- Browser AI,
- Multi-AI Evidence Run,
- Evidence Board,
- Run Timeline,
- Project Memory,
- Memory-backed Handoff,
- Repair Packet / Repair Attempt.

Those assets are enough to test whether a structured review packet can produce a useful mastermind verdict.

Read-only MCP tools are still valuable, but they export context. They do not prove that the platform can close the review loop.

## Relationship Between The Two Tracks

The two tracks should reinforce each other:

- Browser AI Mastermind Review Trial defines the review packet and verdict artifact.
- MCP later exposes the same packet, evidence summaries, and review reports as read-only resources.
- Both use redaction, truncation, source refs, and safety notes.
- Both keep execution authority outside the first version.

## Safety Position

Browser AI mastermind review is advisory only.

The first version must not:

- auto approve,
- auto merge,
- auto deploy,
- auto rework,
- create PRs,
- run CI or Sonar,
- call providers,
- bypass login or captcha,
- save account credentials, cookies, or sessions,
- treat web AI output as unquestionable fact.

MCP first version must also remain read-only:

- no execute tools,
- no shell,
- no repository write,
- no provider call,
- no Browser AI execute,
- no PR / CI / Sonar / Deploy operation.

## Strategy Summary

Preferred order:

```text
S24.1.0 Browser AI Mastermind Review Trial Design
S24.1.1 Mastermind Review Packet Preview API
S24.1.2 Browser AI Mastermind Review Execute
S24.1.3 TaskDetail Mastermind Review UI + Evidence Board integration
S24.2 Read-only MCP resources/tools
```

The order changes, but the platform positioning does not:

```text
Platform = memory, evidence, handoff, context, and advisory review record
Codex / OMX / humans = execution and final delivery authority
```
