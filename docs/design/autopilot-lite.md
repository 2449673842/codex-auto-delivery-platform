# AutoPilot Lite Design

## Status

- Stage: S24.1.9 design only.
- Implementation: not started.
- Scope: thin design for a Multi-Web-AI Review Batch and AutoPilot Lite flow that chains existing advisory evidence capabilities.
- Non-scope: AutoPilot API, UI, database migration, Browser AI execution, provider calls, GitHub / Sonar query, AgentRun / TaskArtifact / TaskEvent writes, automatic approve, automatic merge, automatic deploy, automatic rework.

S24.1.9 does not implement AutoPilot Lite. This document defines the future shape only.

## Product Goal

AutoPilot Lite should give a user one task-level action that runs the existing review evidence loop in order and returns a clear next-step recommendation.

The user outcome is:

```text
one guided review batch
-> multiple web AI second opinions
-> synthesis
-> mastermind review
-> controlled gate preview
-> next-step recommendation
-> human decides what to do
```

AutoPilot Lite is not a full automatic delivery robot. It is an evidence and recommendation coordinator for a personal AI automation workbench.

## Why AutoPilot Lite

The platform already has useful individual controls, but users still need to know which button comes next. AutoPilot Lite exists to remove workflow guesswork without expanding authority.

It should:

- build the current task / PR context,
- collect multiple web AI second opinions,
- refresh synthesis,
- run mastermind review,
- run Controlled Gate Preview,
- generate a human-readable recommendation,
- optionally prepare a Codex / OMX handoff packet candidate.

It should not:

- write code,
- modify the repository,
- approve PRs,
- merge PRs,
- deploy,
- rework automatically,
- bypass login / captcha / 2FA,
- save browser sessions or cookies.

The value is a guided loop, not autonomous external-state change.

## Why Browser AI First

AutoPilot Lite should prioritize Browser AI / web AI over API token providers in the MVP.

Reasons:

- Many users already have logged-in web AI accounts but do not want to manage provider API keys.
- Web AI can be used as visible, user-authorized evidence collection rather than hidden backend execution.
- Browser AI keeps the product aligned with personal workstation workflows.
- It avoids making API-token provider setup a prerequisite for review automation.
- It fits the current safety posture: visible UI, no token storage, no hidden provider API as the primary path.

Provider API token calls may be considered later only when the user explicitly enables them and the safety model is updated. They are not part of S24.1.9 or the first AutoPilot Lite implementation.

## Existing Capabilities

AutoPilot Lite should only chain capabilities that already exist or are explicitly scheduled next.

Existing foundations:

- Task context and TaskDetail task cockpit.
- Browser AI single-run preview and execute.
- Browser AI Pool preview and execute.
- `browser_ai_pool_answer` artifacts.
- AgentRun / TaskArtifact / TaskEvent evidence recording for Browser AI Pool execute.
- Evidence Board.
- Run Timeline.
- Project Memory summary.
- Multi-AI Answer Synthesis preview.
- Mastermind Review Packet Preview.
- Browser AI Mastermind Review Execute.
- `mastermind_review_report` artifact.
- Controlled Mastermind Gate Preview API.
- TaskDetail Mastermind Review and Controlled Gate UI.
- Repair packet and Codex / OMX handoff preview capabilities for later follow-up.

AutoPilot Lite should not duplicate these components. It should orchestrate them conservatively.

## AutoPilot Lite MVP Flow

Future MVP flow:

```text
Run AutoPilot Lite
-> Build context packet
-> Browser AI Pool Preview
-> Browser AI Pool Execute
-> Save browser_ai_pool_answer artifacts
-> Answer Synthesis Preview
-> Mastermind Review Packet Preview
-> Browser AI Mastermind Review Execute
-> Save mastermind_review_report
-> Controlled Gate Preview
-> Generate AutoPilot recommendation
```

The flow should stop early when a safety boundary, missing evidence, login requirement, selector failure, timeout, invalid review, or stale review makes the next step unsafe or low value.

Preview and execute should be separate future APIs:

- Preview shows planned steps and provider jobs without Browser AI execution.
- Execute chains the existing APIs and persists only the artifacts/events that those existing execute steps already persist.

## Multi-Web-AI Review Batch Design

Multi-Web-AI Review Batch is the web AI collection phase inside AutoPilot Lite.

Roles:

| role | Purpose |
| --- | --- |
| `reviewer` | General PR / task review and issue spotting. |
| `risk` | Safety, policy, stale evidence, authority, and process risk. |
| `testing` | Verification coverage, missing tests, flaky checks, and validation gaps. |
| `architecture` | System boundary, maintainability, coupling, and long-term design risk. |
| `product_ux` | User workflow, copy, information architecture, and practical usability. |
| `security` | Secret handling, credential storage, bypass risk, and external side effects. |

Provider candidates:

- ChatGPT Web.
- Gemini Web.
- DeepSeek Web.
- Kimi Web.
- Claude Web.
- custom web AI.

Mapping rules:

- First version lets the user choose providers and roles.
- The platform does not auto-create multiple logged-in windows.
- The platform does not copy login state.
- The platform does not save cookie, session, localStorage, account, or password data.
- Same-provider jobs can run sequentially in MVP.
- `max_total_concurrency` and provider limits are bounded settings for future window-pool expansion.

Each successful role answer becomes advisory evidence. Disagreement between providers should be preserved in synthesis rather than hidden.

## AutoPilot Lite Inputs

Future API draft:

```json
{
  "task_id": 123,
  "mode": "review_batch | repair_planning | delivery_check",
  "prompt": "",
  "providers": [],
  "include_task_context": true,
  "include_project_memory": true,
  "include_evidence_board": true,
  "include_timeline": true,
  "include_mastermind_review": true,
  "run_gate_preview": true,
  "max_total_concurrency": 2,
  "prompt_budget": 12000
}
```

This is a future API draft only. S24.1.9 does not implement this schema.

Input notes:

- `mode=review_batch` collects second opinions and completes the review / gate path.
- `mode=repair_planning` focuses the prompts on why a failed or request-changes task should be repaired.
- `mode=delivery_check` focuses the prompts on whether evidence is complete enough for human confirmation.
- `providers` should reuse Browser AI Pool provider profile shape.
- GitHub / Sonar data must be supplied by the caller or already existing evidence. AutoPilot Lite must not actively query GitHub or Sonar as platform capability.

## AutoPilot Lite Outputs

Future API draft:

```json
{
  "task_id": 123,
  "project_id": 1,
  "status": "succeeded | partial | failed | needs_human",
  "pool_run_id": 1,
  "browser_ai_artifact_ids": [],
  "synthesis_status": "ready | attention_required | failed",
  "mastermind_review_artifact_id": 2,
  "gate_status": "gate_advisory_approved",
  "recommendation": "ready_for_human_confirmation | request_codex_rework | needs_human | blocked",
  "recommended_actions": [],
  "blocking_reasons": [],
  "safety_notes": [],
  "advisory_only": true,
  "human_confirmation_required": true,
  "no_auto_merge": true
}
```

This is a future API draft only. S24.1.9 does not implement this output.

Output requirements:

- Always include `advisory_only=true`.
- Always include `human_confirmation_required=true`.
- Always include `no_auto_merge=true`.
- Include source ids for pool answers, synthesis, mastermind review, and gate preview when available.
- Preserve partial success instead of hiding failed provider jobs.
- Explain blocking reasons in user-readable language.

## State Machine

Supported future states:

| state | Meaning |
| --- | --- |
| `autopilot_not_started` | No AutoPilot Lite run has started. |
| `context_ready` | Task / PR / evidence context packet is ready. |
| `pool_running` | Browser AI Pool jobs are executing through visible UI. |
| `pool_partial` | Some provider jobs succeeded and some failed. |
| `pool_failed` | No provider job produced usable evidence. |
| `synthesis_ready` | Answer Synthesis has a usable result. |
| `mastermind_running` | Browser AI mastermind review is executing. |
| `mastermind_failed` | Mastermind review failed or could not produce a valid report. |
| `gate_ready` | Controlled Gate Preview has produced a gate status. |
| `recommendation_ready` | AutoPilot recommendation has been derived. |
| `needs_human` | The run needs manual judgment before continuing. |
| `blocked_by_safety` | A safety boundary blocks further automation. |

State rules:

- Safety blocks override normal progress.
- A partial pool can continue to synthesis if at least one usable answer exists.
- A failed pool should usually produce `insufficient_evidence`.
- A failed mastermind review should not run the gate as if the review were valid.
- Gate states map to recommendations conservatively.

## Recommendation Taxonomy

Supported future recommendations:

| recommendation | Trigger |
| --- | --- |
| `ready_for_human_confirmation` | Gate is `gate_advisory_approved` with complete evidence. |
| `request_codex_rework` | Gate is `gate_request_changes` or synthesis identifies concrete repair work. |
| `needs_human_review` | Evidence is ambiguous, low-confidence, or requires policy judgment. |
| `blocked_by_safety` | A safety boundary is crossed or requested. |
| `stale_review_rerun_required` | Gate is `gate_stale_review` or head/evidence changed. |
| `invalid_review_rerun_required` | Mastermind review is malformed or gate is `gate_invalid_review`. |
| `insufficient_evidence` | Pool, synthesis, verification, or Sonar evidence is missing. |

Mapping examples:

- `gate_advisory_approved` -> `ready_for_human_confirmation`.
- `gate_request_changes` -> `request_codex_rework`.
- `gate_needs_human` -> `needs_human_review`.
- `gate_blocked_by_safety` -> `blocked_by_safety`.
- `gate_stale_review` -> `stale_review_rerun_required`.
- `gate_invalid_review` -> `invalid_review_rerun_required`.
- missing Browser AI Pool answer or missing synthesis -> `insufficient_evidence`.

## Error Handling

Errors should be surfaced as workflow status and user-readable reasons.

Browser AI Pool errors:

- login required -> mark job failed with `manual_login_required=true`, continue other jobs.
- selector failure -> mark job failed, preserve selector failure reason.
- timeout -> mark job failed, do not retry indefinitely.
- empty answer -> mark job failed.
- all jobs failed -> `pool_failed` and recommendation `insufficient_evidence`.

Synthesis errors:

- failed or unavailable synthesis -> `needs_human` unless enough direct evidence exists and user chooses to continue.

Mastermind errors:

- login required, selector failure, timeout, empty response, parse error, or invalid contract -> `mastermind_failed` or `invalid_review_rerun_required`.

Gate errors:

- missing report -> `insufficient_evidence`.
- stale review -> `stale_review_rerun_required`.
- safety violation -> `blocked_by_safety`.

The platform should never convert an error into approval.

## Human Confirmation Boundary

AutoPilot Lite can prepare a recommendation, but it cannot make delivery decisions.

Human confirmation is required for:

- approve,
- merge,
- deploy,
- repair / rework,
- retrying after login / captcha / 2FA,
- accepting an advisory approved gate,
- continuing when evidence is stale, missing, or ambiguous.

Future UI should show:

- the final recommendation,
- which artifacts and runs support it,
- failed provider jobs,
- gate status,
- human confirmation reminder,
- no automatic approve / merge / deploy / rework actions.

## Safety Boundary

AutoPilot Lite output is advisory recommendation only.

It must not:

- automatically approve,
- automatically merge,
- automatically deploy,
- automatically rework,
- directly write the real repository,
- call provider API tokens unless a future user-enabled provider-token mode is explicitly designed,
- save account, password, cookie, session, or localStorage data,
- bypass login, captcha, 2FA, paywall, or rate limit,
- read `.env`,
- read `secret_ref`,
- access `Project.root_path`,
- query GitHub / Sonar as platform capability,
- create GitHub PR / CI / Sonar / Deploy platform capability.

Default execution path:

- Browser AI visible UI only.
- User-authorized web sessions only.
- No hidden web API as the primary path.
- No automatic external-state-changing action.

## Non-Scope

S24.1.9 does not do:

- AutoPilot Lite implementation.
- AutoPilot preview API.
- AutoPilot execute API.
- TaskDetail AutoPilot UI.
- database migration.
- Browser AI execution.
- provider API token call.
- GitHub / Sonar query as platform capability.
- AgentRun / TaskArtifact / TaskEvent writes.
- repository writes.
- PR creation.
- PR approval.
- PR merge.
- deploy.
- automatic repair / rework.
- persistent browser window pool.
- login-state copy.
- cookie / session storage.

## Follow-Up Route

- S24.1.9 AutoPilot Lite Design, current docs-only task.
- S24.1.10 AutoPilot Lite Preview API, read-only preview that plans steps and provider jobs without Browser AI execution.
- S24.1.11 AutoPilot Lite Execute API, chain existing Browser AI Pool / Answer Synthesis / Mastermind Review / Controlled Gate capabilities without approve / merge / deploy / rework.
- S24.1.12 TaskDetail AutoPilot Lite UI, display preview, run progress, recommendation, and human confirmation reminders.
- S24.1.13 Persistent Browser Window Pool Design, define browser window lifecycle, visibility, user authorization, and safety.
- S24.1.14 Persistent Browser Window Pool MVP, implement a minimal visible-window pool if the design is approved.

## Design Decision

AutoPilot Lite should be a guided evidence workflow, not a general agent runtime.

The safe boundary is:

```text
AutoPilot Lite can collect evidence
AutoPilot Lite can recommend next steps
AutoPilot Lite can prepare handoff candidates
AutoPilot Lite cannot approve, merge, deploy, rework, or write the repository
```
