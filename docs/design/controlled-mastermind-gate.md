# Controlled Mastermind Gate Design

## Status

- Stage: S24.1.4 design only.
- Implementation: not started.
- Scope: design a controlled gate that interprets existing `mastermind_review_report` artifacts before human confirmation.
- Non-scope: gate evaluator implementation, gate API, UI, database migration, GitHub / Sonar query, Browser AI execution, provider call, automatic approve, automatic merge, automatic deploy, automatic rework.

S24.1.4 design-only PR does not implement Controlled Mastermind Gate, gate APIs, UI, database changes, Browser AI execution, provider calls, GitHub / Sonar operations, PR operations, deployment, automatic approval, automatic merge, or automatic rework.

## Product Goal

Controlled Mastermind Gate turns a stored Browser AI mastermind review into a clear pre-confirmation gate status.

The target user outcome is:

```text
mastermind_review_report
-> gate status
-> explanation of why the task can continue, cannot continue, is stale, or needs human judgment
-> human confirmation remains required
```

The gate is a review evidence interpreter. It is not an approval engine and not a merge gate that can act by itself.

Controlled Mastermind Gate should answer:

- Is there a usable latest `mastermind_review_report`?
- Did the mastermind review match the current PR head commit?
- Did the review satisfy the structured contract?
- Did the review identify blocking issues?
- Is the evidence complete enough for a human to decide?
- Did the review preserve the advisory-only and no-auto-merge boundaries?

It should not answer:

- Should the platform merge this PR automatically?
- Should the platform approve the PR automatically?
- Should the platform deploy or rework automatically?

## Why Browser AI Verdict Cannot Be Merge Authorization

Browser AI mastermind review is useful evidence, but it cannot be treated as direct merge authorization.

Reasons:

- Browser AI output is generated text, not an accountable platform actor.
- The model may misunderstand stale evidence, PR body claims, or repository state.
- The browser session may show incomplete context, hidden truncation, selector mistakes, or stale chat state.
- The review packet is bounded and redacted, so it may intentionally omit details.
- Sonar, verification, and PR metadata are supplied evidence, not live platform authority in the review step.
- A verdict of `approved` only means the model found no blocking issue in the packet it saw.
- Merge, approve, deploy, and rework decisions change external state and must remain human-authorized.

The safest rule is:

```text
mastermind verdict can recommend
controlled gate can classify
human confirms
platform does not auto approve / merge / deploy / rework
```

## Gate Inputs

Future Controlled Mastermind Gate should read existing stored evidence and current request context. It should not open Browser AI or query GitHub / Sonar by itself.

Primary input:

- latest `mastermind_review_report`.

Fields read from the report:

- `verdict`.
- `blocking_items`.
- `recommended_actions`.
- `safety_notes`.
- `parse_errors`.
- `confidence`.
- `review_scope_confirmed`.
- `advisory_only`.
- `human_confirmation_required`.
- `no_auto_merge`.
- `source_agent_run_ids`.
- `source_artifact_ids`.
- `source_evidence_ids`.
- `source_timeline_event_ids`.

PR and evidence context:

- PR metadata.
- verification results.
- SonarCloud summary.
- Evidence Board summary.
- Run Timeline summary.
- reviewed head commit from the report.
- current PR head commit supplied by the caller or already stored evidence.

The gate must not read:

- `.env`.
- `secret_ref`.
- account credentials.
- cookies.
- sessions.
- `Project.root_path` for real repository operations.

## Gate Outputs

The gate output is a read-only preview of status and reasoning.

Future API draft:

```json
{
  "task_id": 123,
  "project_id": 1,
  "gate_status": "gate_advisory_approved",
  "source_artifact_id": 456,
  "source_agent_run_id": 789,
  "pr_url": "",
  "pr_number": 65,
  "head_commit": "",
  "reviewed_head_commit": "",
  "summary": "",
  "blocking_reasons": [],
  "recommended_actions": [],
  "human_confirmation_required": true,
  "advisory_only": true,
  "no_auto_merge": true,
  "read_only": true,
  "persisted": false,
  "safety_notes": []
}
```

This is a future API draft only. S24.1.4 does not implement this API.

Output requirements:

- `read_only=true`.
- `persisted=false` for preview.
- `human_confirmation_required=true`.
- `advisory_only=true`.
- `no_auto_merge=true`.
- include source ids when available.
- include blocking reasons in human-readable form.
- include safety notes when a boundary is relevant.

## Gate Status Taxonomy

Supported gate statuses:

| status | Meaning |
| --- | --- |
| `gate_not_ready` | No usable `mastermind_review_report` exists yet. |
| `gate_needs_human` | Evidence is incomplete, ambiguous, low-confidence, or requires human judgment. |
| `gate_request_changes` | The mastermind review or evidence identifies concrete blocking work. |
| `gate_advisory_approved` | The mastermind suggests the task can continue, but human confirmation is still required. |
| `gate_invalid_review` | The mastermind review violates the required structured contract or has parse errors. |
| `gate_blocked_by_safety` | The report contains dangerous authority, secret, auto-merge, deploy, or rework signals. |
| `gate_stale_review` | The reviewed head commit does not match the current PR head or the evidence is stale. |

Status details:

- `gate_advisory_approved` only means the review suggests continuing. It never means the platform may automatically merge.
- `gate_request_changes` means the mastermind clearly requested rework or found blocking issues.
- `gate_needs_human` means evidence is insufficient, the answer is unclear, or policy judgment is needed.
- `gate_invalid_review` means the review cannot be trusted as structured review evidence.
- `gate_blocked_by_safety` means the review or artifact crossed a safety boundary.
- `gate_stale_review` means the review no longer matches the PR or evidence being considered.

## Gate Decision Rules

Rules should be deterministic and conservative. Safety and staleness checks should take precedence over advisory approval.

Baseline rules:

- No `mastermind_review_report` -> `gate_not_ready`.
- `verdict=request_changes` -> `gate_request_changes`.
- `verdict=invalid_review` -> `gate_invalid_review`.
- `parse_errors` non-empty -> `gate_invalid_review` when the contract is broken, otherwise `gate_needs_human`.
- `blocking_items` non-empty with severity `blocker` or `major` -> `gate_request_changes`.
- `review_scope_confirmed=false` -> `gate_needs_human`.
- `confidence=low` -> `gate_needs_human`.
- `advisory_only=false` -> `gate_blocked_by_safety`.
- `human_confirmation_required=false` -> `gate_blocked_by_safety`.
- `no_auto_merge=false` -> `gate_blocked_by_safety`.
- Review claims that it already approved, merged, deployed, or reworked -> `gate_blocked_by_safety`.
- Reviewed head commit does not match current PR head commit -> `gate_stale_review`.
- Sonar or verification evidence is missing -> `gate_needs_human`.
- `verdict=approved` with no blocker / major items, complete evidence, matching head commit, confirmed scope, and preserved safety flags -> `gate_advisory_approved`.

Recommended precedence:

1. Safety boundary violations -> `gate_blocked_by_safety`.
2. Head commit or evidence staleness -> `gate_stale_review`.
3. Missing report -> `gate_not_ready`.
4. Invalid structured review -> `gate_invalid_review`.
5. Explicit blockers -> `gate_request_changes`.
6. Missing evidence, low confidence, or unconfirmed scope -> `gate_needs_human`.
7. Clean approved advisory result -> `gate_advisory_approved`.

## Human Confirmation Requirement

Every gate status requires human awareness. Only `gate_advisory_approved` is eligible to be presented as "ready for human confirmation".

Human confirmation must be required because:

- the review is advisory,
- the packet may be incomplete,
- current PR state may change after review,
- merge / approve / deploy are external side effects,
- safety boundaries cannot be delegated to a browser AI response.

Future UI should show:

- gate status,
- source review artifact,
- current head commit versus reviewed head commit,
- blocking reasons,
- recommended actions,
- safety notes,
- explicit "human confirmation required" text.

It should not show an automatic merge or approve action as part of the gate.

## Relationship With Evidence Board, Timeline, And Project Memory

Evidence Board:

- `mastermind_review_report` remains the source evidence.
- Controlled Gate should reference the report artifact and any source evidence ids.
- Future gate preview can appear as derived evidence, but it should not replace the original report.

Run Timeline:

- S24.1.2 already records Browser AI review submission, response, and imported report events.
- Future S24.1.5 may add a read-only gate preview event only if persistence is explicitly designed later.
- S24.1.4 does not add new event types.

Project Memory:

- Project Memory can inform review packets and policy explanations.
- Gate decisions should not write or update memory.
- Gate status should not automatically change `delivery_policy` or `safety_policy`.
- If a repeated gate failure suggests a memory update, that belongs to a future human-confirmed memory update flow, not this gate.

## Division Of Labor

Codex:

- implements task changes,
- prepares PRs,
- runs verification when instructed,
- responds to review feedback,
- does not self-review or self-merge.

OMX / Codex skills:

- can help package evidence and SOPs,
- can perform external reader workflows under user control,
- do not become merge authority.

Browser AI:

- provides advisory mastermind review through visible user-authorized UI,
- returns structured review evidence,
- cannot approve, merge, deploy, or rework.

Platform:

- stores memory, evidence, timeline, handoff packets, and review reports,
- derives controlled gate status,
- preserves audit links and safety boundaries,
- does not become a general agent runtime or automatic delivery executor.

Human:

- confirms whether to proceed,
- decides merge / approve / deploy / rework,
- resolves ambiguous or unsafe gate states.

## MVP Scope

S24.1.4 is design only.

Future S24.1.5 Controlled Mastermind Gate Preview API can implement:

- read the latest `mastermind_review_report`,
- compare reviewed head commit with supplied current head commit,
- evaluate deterministic gate rules,
- return read-only gate status,
- include source artifact / run ids,
- include blocking reasons and recommended actions,
- persist nothing by default.

Future S24.1.6 TaskDetail Gate UI can implement:

- display gate status,
- display source report links,
- display reviewed versus current head commit,
- display human confirmation reminder,
- refresh after mastermind review execution,
- avoid approve / merge / deploy / rework actions.

Future S24.1.7 Browser AI Provider Pool / Multi-window Queue Design can evaluate:

- multiple visible Browser AI windows,
- bounded queueing,
- provider profile availability,
- failure isolation,
- login / captcha safety behavior.

S24.2 Read-only MCP resources/tools remains on the roadmap after the controlled review gate path.

## Non-Scope

This stage does not do:

- gate evaluator implementation.
- gate API.
- UI.
- database migration.
- GitHub / Sonar query.
- Browser AI opening or execution.
- provider call.
- shell / subprocess execution as platform capability.
- real repository write.
- PR creation.
- PR approval.
- PR merge.
- deploy.
- automatic rework.
- treating Browser AI verdict as final authorization.

## Follow-Up Route

- S24.1.4 Controlled Mastermind Gate Design, current docs-only task.
- S24.1.5 Controlled Mastermind Gate Preview API, read-only gate evaluator with no action execution.
- S24.1.6 TaskDetail Gate UI, display gate status and human confirmation reminder only.
- S24.1.7 Browser AI Provider Pool / Multi-window Queue Design, optional design for multiple web AI resources.
- S24.2 Read-only MCP resources/tools.

## Safety Boundary

S24.1.4 does not authorize:

- Controlled Mastermind Gate implementation.
- gate API.
- UI.
- database migration.
- provider calls.
- Browser AI opening or execution.
- shell or subprocess execution as platform capability.
- `.env` read.
- `secret_ref` read.
- account, password, cookie, or session storage.
- login, captcha, 2FA, paywall, rate-limit, or service restriction bypass.
- `Project.root_path` access.
- AgentRun / TaskArtifact / TaskEvent writes.
- Project / Task modification.
- repository writes.
- GitHub / Sonar queries as platform capability.
- GitHub PR / CI / Sonar / Deploy platform capability.
- automatic approve.
- automatic merge.
- automatic deploy.
- automatic rework.

Even when the future gate status is `gate_advisory_approved`, the result remains advisory and human confirmation remains required.
