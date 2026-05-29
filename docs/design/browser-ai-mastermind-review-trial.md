# Browser AI Mastermind Review Trial Design

## Status

- Stage: S24.1.0 design only.
- Implementation: not started.
- Scope: controlled design for a Browser AI based mastermind review trial.
- Non-scope: Browser AI mastermind review execution, review execute API, artifact write, UI, database migration, provider call, automatic approve, automatic merge, automatic deploy, automatic rework.

S24.1.0 design-only PR does not implement Browser AI mastermind review execution, review execute APIs, artifact persistence, UI, database changes, Browser AI automation, provider calls, PR operations, CI / Sonar operations, automatic approval, automatic merge, deployment, or automatic rework.

## Product Goal

The product goal is to design a controlled trial where the platform can ask a GPT mastermind session to review a PR or task package and return a structured review verdict.

The target user outcome is an audit-friendly review loop:

1. The platform prepares a PR / task Mastermind Review Packet.
2. Browser AI submits the packet to a user-authorized GPT mastermind conversation.
3. Browser AI reads the visible mastermind response.
4. The platform parses the response into a bounded review verdict.
5. The platform stores the result later as a `mastermind_review_report` artifact.
6. Evidence Board and Run Timeline can display the review result.
7. The user remains responsible for approve, merge, deploy, and rework decisions.

The first trial should answer one question only:

```text
Can a browser-based GPT mastermind reliably participate in review when given a structured review packet and required structured output?
```

It should not answer:

```text
Can the platform automatically approve, merge, deploy, or repair code?
```

## Why This Is Closer To The Automatic Review Loop Than MCP

MCP read-only tools solve a context export problem. They let external AI retrieve Project Memory, Evidence Board, Timeline, and handoff packets. That is useful, but it does not validate the review loop itself.

Browser AI Mastermind Review Trial is closer to the original automatic review ambition because it tests the actual review sequence:

- collect current PR / task evidence,
- submit the evidence to a reviewer model,
- receive a review verdict,
- normalize the verdict,
- preserve the review as auditable evidence,
- keep human authority over merge and follow-up.

MCP remains important, but it is infrastructure for external AI context access. The Browser AI mastermind trial validates whether the platform can turn its existing memory and evidence into a review packet that a GPT mastermind can judge consistently.

The two directions are not mutually exclusive:

- Browser AI Mastermind Review Trial focuses on the automatic review loop.
- MCP focuses on external AI context retrieval.
- Both should remain read-only and non-executing in their first versions.

## Current Platform Foundations

S24.1.0 builds on existing foundations:

- Browser AI: user-authorized web AI interaction, visible response extraction, login / captcha safety boundaries, and Browser AI answer artifacts.
- Evidence Board: task evidence aggregation, evidence type taxonomy, redaction status, safety notes, linked ids, and filters.
- Run Timeline: chronological task events, AI runs, artifacts, repair events, verification imports, and skill review report imports.
- Project Memory: project profile, runbook, verification policy, delivery policy, safety policy, known failures, user preferences, and handoff templates.
- Memory-backed Handoff: AI and repair handoff previews enriched with read-only Project Memory context.
- Repair Packet / Repair Attempt: controlled repair context, repair handoff, attempt records, and verification import design.
- Multi-AI Evidence Run: multiple AI evidence collection, dispatch batch / job records, answer synthesis, and artifact summaries.

These foundations mean the platform can prepare a high-quality review packet without adding a general executor.

## Mastermind Review Packet Design

The Mastermind Review Packet is the structured input sent to the GPT mastermind session. It must be explicit, bounded, redacted, and source-linked.

### Required Packet Fields

At minimum, the packet must include:

- PR URL.
- PR number.
- head commit.
- base commit.
- changed files.
- PR body.
- verification results.
- SonarCloud summary.
- security hotspots.
- duplication on new code.
- new issues.
- safety boundary checklist.
- relevant Task summary.
- relevant Evidence Board summary.
- relevant Run Timeline summary.
- relevant Project Memory summary.
- prior repair / handoff context if available.

### Packet Shape Draft

```json
{
  "packet_type": "mastermind_review_packet",
  "task_id": 123,
  "project_id": 1,
  "pr": {
    "url": "https://github.com/org/repo/pull/61",
    "number": 61,
    "head_commit": "full_sha",
    "base_commit": "full_sha",
    "changed_files": [
      "docs/design/example.md"
    ],
    "body": "redacted PR body excerpt"
  },
  "verification": {
    "backend_pytest": "not_run_docs_only",
    "compileall": "not_run_docs_only",
    "npm_build": "not_run_docs_only",
    "frontend_smoke": "not_run_docs_only",
    "git_diff_check": "passed"
  },
  "sonarcloud": {
    "quality_gate": "Passed",
    "security_hotspots": 0,
    "duplication_on_new_code": "0.0%",
    "new_issues": 0
  },
  "safety_boundary_checklist": {
    "provider_call": false,
    "browser_ai_execution": false,
    "repository_write": false,
    "github_sonar_platform_query": false,
    "auto_approve_merge_deploy": false
  },
  "task_summary": "Current task summary.",
  "evidence_board_summary": "Relevant evidence summary.",
  "run_timeline_summary": "Relevant timeline summary.",
  "project_memory_summary": "Relevant project memory summary.",
  "prior_repair_handoff_context": "Optional prior repair and handoff context.",
  "redaction_status": {
    "redaction_applied": true,
    "truncated": false,
    "max_chars": 12000
  }
}
```

### Packet Rules

- The packet is review input, not merge authority.
- The packet must include source ids or source refs when available.
- The packet must use redacted summaries rather than unbounded raw logs.
- The packet must clearly say that the mastermind answer is advisory.
- The packet must state that suggested merge approval does not authorize automatic merge.
- The packet must not include account credentials, cookies, sessions, API keys, or secret values.

## Browser AI Submit Flow

Future implementation can submit the packet through a user-authorized Browser AI session.

Conceptual flow:

```text
user clicks future review trial action
-> platform builds Mastermind Review Packet preview
-> user confirms Browser AI submission
-> Browser AI opens or resumes the selected GPT mastermind session
-> platform injects a review instruction plus packet into the visible chat UI
-> Browser AI waits for a stable visible response
-> Browser AI extracts the visible response text
-> parser validates structured output
-> platform returns review verdict preview
```

Submission requirements:

- Use visible browser UI only.
- Require an existing user-authorized session.
- Do not bypass login, captcha, 2FA, paywall, rate limits, or service restrictions.
- Do not save account, password, cookie, session, localStorage, or browser profile plaintext.
- Do not call hidden web APIs as the primary implementation path.
- Do not submit secrets.
- Do not auto retry indefinitely.

S24.1.0 does not implement this flow.

## Mastermind Response Read Flow

Future response reading should reuse Browser AI stable response extraction patterns:

1. Wait for the response container to become stable.
2. Extract only visible assistant response text.
3. Bound the extracted text.
4. Redact secret-like content.
5. Preserve raw excerpt for audit.
6. Send the extracted text to the verdict parser.
7. Classify response extraction failures as review failures, not merge blockers by themselves.

Failure examples:

- login expired,
- captcha or 2FA required,
- selector failure,
- stable response timeout,
- response too long,
- malformed structured output,
- ambiguous review.

Any failure should result in `invalid_review` or `needs_human`, not automatic approve, merge, deploy, or rework.

## Required Mastermind Output Contract

The mastermind must be asked to return structured output. Free-form prose can be included only inside bounded fields.

Draft response contract:

```json
{
  "verdict": "approved | request_changes | needs_human | invalid_review",
  "summary": "Short review summary.",
  "blocking_items": [
    {
      "severity": "blocker | major | minor",
      "title": "Issue title",
      "evidence": "Why this is grounded in packet evidence.",
      "recommended_action": "What should be done next."
    }
  ],
  "recommended_actions": [
    "Action item"
  ],
  "safety_notes": [
    "Safety note"
  ],
  "confidence": "high | medium | low",
  "review_scope_confirmed": true
}
```

The prompt must instruct:

- Do not invent files, checks, or Sonar results.
- Compare PR body claims against provided packet evidence.
- Treat missing evidence as a reason for `needs_human`.
- Use `request_changes` for concrete blocking defects.
- Use `needs_human` for ambiguous authority, unclear evidence, or policy uncertainty.
- Use `invalid_review` only when the review cannot be parsed or the output contract cannot be satisfied.
- If recommending merge, state that it is advisory and does not authorize automatic merge.

## Verdict Taxonomy And Parsing Design

Supported verdicts:

| verdict | Meaning |
| --- | --- |
| `approved` | The mastermind found no blocking issue in the provided packet. Advisory only. |
| `request_changes` | The mastermind found concrete blocking issues or evidence mismatches. |
| `needs_human` | The mastermind cannot decide safely due to ambiguity, missing evidence, authority limits, or unclear scope. |
| `invalid_review` | The response does not satisfy the required structured format or cannot be parsed. |

Parsing requirements:

- Do not rely on crude keyword matching.
- Require structured output with an explicit `verdict` field.
- Validate verdict against the taxonomy.
- Validate required fields.
- Validate that `blocking_items` and `recommended_actions` are arrays.
- Validate that the response does not claim platform authority to merge, approve, deploy, or rework.
- If the format is invalid, return `invalid_review`.
- If the response is vague, contradictory, or authority-confused, return `needs_human`.
- If the mastermind suggests merge, record it only as advisory; do not treat it as merge authorization.

Parser output should keep:

- normalized verdict,
- normalized summary,
- blocking items,
- recommended actions,
- safety notes,
- raw excerpt,
- parse errors,
- redaction status.

## `mastermind_review_report` Artifact Draft

Future artifact type:

```text
mastermind_review_report
```

Suggested artifact payload:

```json
{
  "artifact_type": "mastermind_review_report",
  "task_id": 123,
  "project_id": 1,
  "pr_url": "https://github.com/org/repo/pull/61",
  "pr_number": 61,
  "head_commit": "full_sha",
  "base_commit": "full_sha",
  "verdict": "needs_human",
  "summary": "Advisory mastermind review summary.",
  "blocking_items": [],
  "recommended_actions": [],
  "safety_notes": [
    "Mastermind review is advisory and does not authorize automatic merge."
  ],
  "raw_excerpt": "Bounded, redacted excerpt from the visible Browser AI response.",
  "redaction_status": {
    "redaction_applied": true,
    "truncated": false,
    "max_chars": 4000
  },
  "source_agent_run_ids": [],
  "source_artifact_ids": [],
  "source_timeline_event_ids": [],
  "source_evidence_ids": [],
  "read_only": true,
  "persisted": true
}
```

Notes:

- `persisted=true` only applies in a future artifact-save implementation.
- The report remains evidence, not authority.
- `approved` does not mean platform-approved.
- Human review remains required before merge.

## Timeline / Evidence Board Integration Design

Future Run Timeline event taxonomy can add:

```text
mastermind_review_packet_previewed
mastermind_review_submitted
mastermind_review_response_received
mastermind_review_report_imported
```

Future Evidence Board evidence type can add:

```text
mastermind_review_report
```

Timeline item draft:

```json
{
  "time": "2026-05-29T00:00:00Z",
  "type": "mastermind_review_report_imported",
  "title": "Mastermind review report imported",
  "status": "completed",
  "source": "browser_ai_mastermind_review",
  "linked_ids": {
    "agent_run_id": 900,
    "artifact_id": 1200,
    "dispatch_batch_id": null,
    "dispatch_job_id": null,
    "repair_attempt_id": null
  },
  "summary": "Mastermind review returned needs_human.",
  "safety_flags": [
    "advisory_only",
    "human_decision_required",
    "no_auto_merge"
  ]
}
```

Evidence Board item draft:

```json
{
  "evidence_type": "mastermind_review_report",
  "source": "browser_ai_mastermind_review",
  "status": "needs_human",
  "provider": "browser_ai",
  "role": "mastermind_reviewer",
  "artifact_id": 1200,
  "agent_run_id": 900,
  "summary": "Advisory mastermind review summary.",
  "raw_excerpt": "Bounded raw excerpt.",
  "safety_notes": [
    "Browser AI mastermind review cannot approve, merge, deploy, or trigger rework."
  ],
  "redaction_status": {
    "redaction_applied": true,
    "truncated": false,
    "max_chars": 4000
  }
}
```

## Safety Boundary

S24.1.0 design does not authorize:

- Browser AI mastermind review implementation.
- review execute API.
- artifact writes.
- UI.
- database migration.
- provider calls.
- Browser AI opening or execution.
- shell or subprocess execution as platform capability.
- `.env` read.
- `secret_ref` read.
- account, password, cookie, or session storage.
- login, captcha, 2FA, paywall, rate-limit, or service restriction bypass.
- AgentRun / TaskArtifact / TaskEvent writes.
- Project / Task modification.
- repository writes.
- GitHub / Sonar queries as platform capability.
- GitHub PR / CI / Sonar / Deploy platform capability.
- automatic approve.
- automatic merge.
- automatic deploy.
- automatic rework.

The review result must always be treated as advisory evidence. It must never become an implicit permission grant.

## MVP Scope

S24.1.0 is design only.

Future S24.1.1 MVP can implement only a packet preview API:

- build a Mastermind Review Packet from existing PR / task inputs,
- include Evidence Board summary,
- include Run Timeline summary,
- include Project Memory summary,
- include verification and Sonar fields supplied by the current workflow,
- redact and truncate packet content,
- return preview only,
- write nothing.

Future S24.1.2 can test Browser AI execution and artifact save only after S24.1.1 proves packet quality.

## Non-Scope

This stage does not do:

- Browser AI mastermind review execution.
- review execute API.
- artifact writing.
- UI.
- automatic approve.
- automatic merge.
- automatic deploy.
- automatic rework.
- PR creation.
- CI / Sonar execution or active platform queries.
- provider calls.
- shell / subprocess execution as platform capability.
- repository writes.
- `.env` reads.
- `secret_ref` reads.
- account / password / cookie / session saving.
- login / captcha bypass.
- treating web AI output as unquestionable truth.

## Follow-Up Route

- S24.1.0 Browser AI Mastermind Review Trial Design.
- S24.1.1 Mastermind Review Packet Preview API.
- S24.1.2 Browser AI Mastermind Review Execute + artifact save.
- S24.1.3 TaskDetail Mastermind Review UI + Evidence Board integration.
- S24.1.4 Controlled Mastermind Gate, evaluate later and do not include in the current implementation path.

## Design Decision

The platform should first prove that a GPT mastermind can produce consistent structured review evidence from platform packets. Only after that should the project evaluate whether the result can become a controlled gate.

Even then, the controlled gate should remain separate from automatic merge. The safest boundary is:

```text
mastermind review can inform humans
mastermind review can block automation
mastermind review cannot approve or merge by itself
```
