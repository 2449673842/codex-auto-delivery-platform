# Evidence Board / Run Timeline Design

## Status

- Stage: S22.0 design only.
- Implementation: not started.
- Scope: TaskDetail evidence memory and task run timeline.
- Non-scope: backend API, frontend page, database migration, provider call, Browser AI execution, repository writes.

## Product Goal

Evidence Board turns scattered task records into a durable evidence layer. A user should be able to reopen a task weeks later and answer:

- What happened during the task?
- Which AI or skill produced each piece of evidence?
- Which artifact, dispatch job, repair packet, or verification result supports a decision?
- Which safety boundary applied?
- Which evidence was missing, failed, partial, or redacted?

Run Timeline turns the same data into a chronological view. It explains the sequence: task creation, AI runs, artifacts, Browser AI answers, Multi-AI Evidence Run jobs, synthesis refreshes, failure evidence, repair packets, handoff previews, repair attempts, verification imports, and skill review report imports.

The product outcome is not another executor. The outcome is long-term traceability: decisions, evidence, risks, and handoffs remain readable after the original Codex / OMX session is gone.

## Why This Is Platform Core Value

Codex / OMX skills are good at one-shot reading, judgment, and execution handoff. They can inspect a PR, compare claims with evidence, and generate a review report. They are not the long-term system of record for every task.

The platform should own Evidence Board / Run Timeline because it already owns:

- task identity and status,
- agent run identity,
- artifacts,
- dispatch batch and job identity,
- Browser AI and Multi-AI Evidence Run outputs,
- Answer Synthesis,
- repair loop records,
- human review and safety boundary context.

This is platform memory, not a weak Codex clone. Skills may produce evidence, but the platform stores, indexes, filters, links, redacts, and presents it across tasks.

## Evidence Sources

S22 evidence aggregation must cover these sources:

- Task created / updated.
- AgentRun.
- TaskArtifact.
- TaskEvent.
- DispatchBatch / DispatchJob.
- Browser AI answer artifact.
- Multi-AI Evidence Run artifacts.
- Answer Synthesis.
- Failure Evidence Packet.
- Repair Packet.
- Codex / OMX Repair Handoff.
- Repair Attempt Timeline.
- Verification Result artifact.
- PR / CI / Sonar Reader skill review report.
- Sandbox / Gate artifact.
- Patch artifact.

## Evidence Type Taxonomy

The first taxonomy should be stable enough for filtering, UI grouping, and future imports:

| evidence_type | Meaning |
| --- | --- |
| `task_event` | Task lifecycle or audit event from TaskEvent. |
| `agent_run` | AI run record with status, model/provider, and linked artifacts. |
| `artifact` | Generic TaskArtifact that does not map to a narrower type. |
| `browser_ai_answer` | Browser AI answer artifact from a web provider. |
| `multi_ai_evidence` | S19 Multi-AI Evidence Run batch/job output. |
| `answer_synthesis` | Answer Synthesis preview or refreshed synthesis artifact. |
| `failure_evidence` | S20.1 Failure Evidence Packet preview/result. |
| `repair_packet` | S20.2 repair packet artifact. |
| `repair_handoff` | S20.3 Codex / OMX / generic AI handoff preview. |
| `repair_attempt` | S20.4 repair attempt event or status record. |
| `verification_result` | Imported verification result artifact. |
| `skill_review_report` | Imported PR / CI / Sonar Reader skill report. |
| `sandbox_result` | Sandbox apply or sandbox gate artifact/result. |
| `patch_artifact` | Patch, diff, or patch review artifact. |

## Timeline Event Taxonomy

Run Timeline should normalize source records into event types. The first version should support:

- `task_created`
- `ai_run_started`
- `ai_run_finished`
- `ai_run_failed`
- `artifact_created`
- `browser_ai_answer_saved`
- `multi_ai_evidence_started`
- `multi_ai_evidence_finished`
- `synthesis_refreshed`
- `failure_evidence_previewed`
- `repair_packet_generated`
- `repair_handoff_previewed`
- `repair_attempt_created`
- `repair_attempt_status_changed`
- `verification_result_imported`
- `skill_review_report_imported`

Each normalized item should keep its source record ids so the UI can open the underlying artifact, run, batch, job, or attempt.

## UI Information Architecture

TaskDetail should expose at least two views.

### Run Timeline

Run Timeline is chronological and optimized for reconstructing what happened.

Each timeline item should show at minimum:

- time,
- type,
- title,
- status,
- source,
- linked ids,
- summary,
- safety flags.

Recommended item groups:

- task lifecycle,
- AI and Browser AI runs,
- dispatch and Multi-AI Evidence Run,
- artifact creation,
- synthesis,
- repair loop,
- imported skill review reports,
- verification imports.

### Evidence Board

Evidence Board is grouped by type/source and optimized for inspection, filtering, and comparison.

Filters should include:

- evidence type,
- source,
- status,
- provider,
- role,
- date,
- has artifact,
- has risk,
- safety boundary.

The detail panel should show:

- summary,
- raw excerpt,
- linked AgentRun / Artifact / DispatchBatch / RepairAttempt,
- safety notes,
- redaction status,
- copy handoff,
- copy evidence summary.

The UI should make clear that this board is read and import oriented. It must not imply that the platform will execute a repair, create a PR, run CI, query Sonar, merge, or deploy.

## Backend API Design Draft

S22.0 does not implement APIs. Later phases can add:

```text
GET /api/tasks/{task_id}/timeline
GET /api/tasks/{task_id}/evidence-board
POST /api/tasks/{task_id}/skill-review-report/import
```

### `GET /api/tasks/{task_id}/timeline`

Returns normalized chronological items:

```json
{
  "task_id": 123,
  "items": [
    {
      "time": "2026-05-26T10:00:00Z",
      "type": "repair_packet_generated",
      "title": "Repair packet generated",
      "status": "completed",
      "source": "repair_loop",
      "linked_ids": {
        "artifact_id": 802,
        "dispatch_batch_id": 201
      },
      "summary": "Generated one-attempt repair packet from failure evidence.",
      "safety_flags": ["no_repository_writes", "human_decision_required"]
    }
  ]
}
```

### `GET /api/tasks/{task_id}/evidence-board`

Returns grouped evidence summaries and filter metadata:

```json
{
  "task_id": 123,
  "filters": {
    "evidence_type": ["repair_packet", "verification_result"],
    "source": ["repair_loop", "skill_review"],
    "status": ["completed", "failed", "partial"]
  },
  "items": [
    {
      "evidence_type": "repair_packet",
      "source": "repair_loop",
      "status": "completed",
      "artifact_id": 802,
      "summary": "Narrow repair strategy for sandbox gate failure.",
      "raw_excerpt": "Failure summary...",
      "safety_notes": ["Codex / OMX or user must execute repair."],
      "redaction_status": {
        "redaction_applied": true,
        "truncated": false
      }
    }
  ]
}
```

### `POST /api/tasks/{task_id}/skill-review-report/import`

Design-only future endpoint for importing a PR / CI / Sonar Reader skill output as a `skill_review_report` artifact. The platform should store the report and create a timeline event. It should not query GitHub or Sonar itself in this stage.

## Data Model Reuse

S22 should start by reusing existing records:

- Task for task identity and project_id.
- AgentRun for AI run records.
- TaskArtifact for all persisted evidence payloads.
- TaskEvent for audit and timeline event sources.
- DispatchBatch and DispatchJob for Multi-AI Evidence Run structure.
- Repair Attempt Timeline from S20.4 through TaskEvent metadata.
- `verification_result` TaskArtifact for imported verification results.
- Future `skill_review_report` TaskArtifact for PR / CI / Sonar Reader skill outputs.

No complex new database table is required for S22 MVP. Normalized timeline and board items can be computed from existing records first.

## S22 MVP Scope

S22.1 / S22.2 should first implement:

- aggregate existing TaskEvent / AgentRun / TaskArtifact / DispatchBatch / DispatchJob records,
- return timeline items,
- return evidence summaries,
- show a TaskDetail timeline list,
- show a TaskDetail evidence board list,
- keep detail payloads redacted and truncated,
- preserve links to underlying ids.

MVP constraints:

- do not add complex database tables,
- do not execute external commands,
- do not call providers,
- do not open Browser AI,
- do not query GitHub or Sonar directly.

## S22 Non-Scope

S22 does not do:

- automatic code execution,
- repository writes,
- reading `.env` or `secret_ref`,
- provider calls,
- Browser AI execution,
- GitHub PR / CI / Sonar / Deploy creation,
- automatic approve / merge / deploy,
- active GitHub / Sonar API reader implementation,
- Codex / OMX replacement,
- infinite repair loop,
- automatic next repair attempt.

S21 decided PR / CI / Sonar reading remains skill-first. Platform work should focus on importing and presenting the skill output when the user chooses to preserve it.

## Safety Boundaries

For S22.0:

- Evidence Board implementation: no, design only.
- Timeline API: no, design only.
- Skill review report import API: no, design only.
- Provider call: no.
- Browser AI open: no.
- Shell / subprocess execution: no.
- `.env` / `secret_ref` read: no.
- Project.root_path access: no.
- AgentRun / TaskArtifact / TaskEvent write: no.
- Real repository write: no.
- GitHub PR / CI / Sonar / Deploy platform capability: no.
- Automatic approve / merge: no.

For later S22 implementation, the same boundaries remain unless a future design explicitly changes them and passes mastermind review.

## Roadmap

### S22.0 — Evidence Board / Run Timeline Design

Create this design and the strategy comparison with skill-based review. No code implementation.

### S22.1 — Evidence Summary API

Implement read-only aggregation for timeline and evidence summaries using existing records.

### S22.2 — TaskDetail Timeline UI

Add TaskDetail Run Timeline and a first evidence list using S22.1 APIs.

### S22.3 — Evidence Board Filters / Details

Add type/source/status/provider/role/date/risk/safety filters and a detail panel with excerpts and linked ids.

### S22.4 — Skill Review Report Artifact Import

Add import only if S21 skill outputs prove useful to persist. This should save user-confirmed skill reports as artifacts; it should not become a platform GitHub / Sonar reader.
