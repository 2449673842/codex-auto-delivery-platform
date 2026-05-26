# Evidence Board vs Skill

## Decision

S21 confirmed that PR / CI / Sonar Reader should continue as a Codex / OMX skill trial, not become an immediate platform reader API. S22 keeps that split:

- Skills perform one-shot reading, judgment, and SOP-driven review.
- The platform stores, links, filters, and displays durable evidence.

The platform should not become a weaker Codex or an automatic executor. It should become the evidence layer and memory layer around Codex / OMX work.

## What Skills Are Good At

Codex / OMX skills are strongest when the job is bounded and current:

- read one PR,
- inspect changed files,
- compare PR body claims with observed checks,
- inspect SonarCloud bot comments or reports when available,
- produce a fixed-format review report,
- recommend approve / request changes / wait.

This matches S21 because PR / CI / Sonar review depends on live external state, credentials, UI/API availability, and reviewer judgment. Keeping it in a skill avoids building a brittle platform reader too early.

## What The Platform Is Good At

The platform is strongest when the job is durable and cross-task:

- preserve evidence after the session ends,
- link evidence to task, run, artifact, dispatch job, and repair attempt ids,
- support filtering and retrieval,
- compare patterns across tasks,
- show redaction and safety status,
- keep an audit trail of why work continued, stopped, or needed human confirmation.

Evidence Board and Run Timeline are therefore platform concerns. They are not one-shot readers; they are the memory surface for repeated work.

## How PR / CI / Sonar Reader Skill Output Enters Evidence Board

The intended flow is:

```text
Codex / OMX PR Reader skill reads external PR / CI / Sonar state
-> skill emits fixed-format review report
-> user confirms it should be preserved
-> platform imports it as TaskArtifact(artifact_type="skill_review_report")
-> Run Timeline adds skill_review_report_imported
-> Evidence Board indexes it by evidence_type, source, status, risk, and safety boundary
```

The platform should save the report and expose it in TaskDetail. It should not silently query GitHub or Sonar in the background during S22.

## Why Browser AI / Multi-AI / Repair Loop Belong In Platform Display

Browser AI, Multi-AI Evidence Run, and Repair Loop produce chains of evidence, not isolated judgments.

Browser AI evidence includes:

- provider profile,
- prompt source,
- answer artifact,
- redaction and safety notes,
- status and error messages.

Multi-AI Evidence Run includes:

- DispatchBatch,
- DispatchJob,
- provider,
- role,
- per-job status,
- artifact ids,
- partial failure state,
- synthesis refresh status.

Repair Loop includes:

- Failure Evidence Packet,
- Repair Packet,
- Codex / OMX handoff preview,
- Repair Attempt Timeline,
- imported Verification Result artifact.

These chains need long-term links and status history. A skill can inspect or generate one part of the chain, but the platform should present the full chain.

## Platform Is Not A Weak Codex

The platform should not try to compete with Codex / OMX execution.

The platform does not:

- automatically modify code,
- write a real repository,
- execute shell commands for repair,
- create PR / CI / Sonar / Deploy capabilities,
- automatically approve, merge, or deploy,
- bypass Browser AI login or captcha,
- call hidden APIs,
- run an infinite repair loop.

The platform does:

- collect evidence,
- store artifacts,
- record events,
- show timeline,
- synthesize answers,
- preserve repair packets and handoffs,
- import user-confirmed skill reports,
- help the user and Codex / OMX understand past decisions.

## Platformization Criteria

A workflow should stay skill-first when:

- it depends on live external systems,
- output is mostly a current judgment,
- it needs flexible reviewer reasoning,
- platform storage is not required,
- credentials or access mode vary by user.

A workflow should become platform-supported when:

- the result needs long-term retention,
- users need cross-task search or filtering,
- evidence must link to task artifacts and repair attempts,
- safety and redaction status must remain visible,
- repeated UI inspection saves time.

The likely long-term answer is a hybrid:

- Codex / OMX skills read and judge.
- Platform imports selected outputs.
- Evidence Board and Run Timeline make those outputs durable and inspectable.

## S22 Implication

S22 should implement the evidence memory surface before adding any new external reader. The first implementation should aggregate existing database records and imported reports. It should avoid new execution capabilities.
