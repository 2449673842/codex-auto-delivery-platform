# Codebase Index — Codex Automation Delivery Platform

> Human-and-AI-readable project map. Covers all modules, file roles, and task-to-file mappings.
> Version: v0.4.0 | Last updated: 2026-05-21

---

## 1. Project Structure Overview

```
codex-auto-delivery-platform/
├── backend/                        # FastAPI + SQLAlchemy async backend
│   ├── app/
│   │   ├── main.py                 # FastAPI app entry, CORS, router registration
│   │   ├── config.py               # Settings (host, db_url, frontend_origin)
│   │   ├── database.py             # SQLite + async SQLAlchemy engine
│   │   ├── enums.py                # All enums + state transition whitelists
│   │   ├── models/                 # SQLAlchemy ORM models (10 tables)
│   │   ├── schemas/                # Pydantic request/response schemas (18 files)
│   │   ├── routers/                # API route handlers (17 routers, 75+ endpoints)
│   │   └── services/               # Business logic (27 service files)
│   ├── data/                       # SQLite database file location
│   ├── tests/                      # pytest tests (12 files, 283+ tests)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                       # Vue 3 + TypeScript + Vite
│   ├── src/
│   │   ├── pages/                  # 8 page components
│   │   ├── components/             # 6 shared components
│   │   ├── router/                 # Vue Router config
│   │   ├── stores/                 # Pinia stores (2)
│   │   ├── services/               # API client functions
│   │   ├── types/                  # TypeScript interfaces + constants
│   │   └── styles/                 # Global CSS
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
├── docs/                           # Documentation
│   ├── releases/                   # Release notes (v0.1.0–v0.4.0)
│   ├── design/                     # Design documents
│   ├── harness/                    # AI development harness
│   ├── project-map/                # This directory
│   └── reports/                    # Audit/review reports
├── scripts/
│   └── ai_verify.sh                # Local verification script
├── AGENTS.md                       # AI agent project rules
└── README.md
```

---

## 2. Backend Core Files

| File | Role |
|------|------|
| `backend/app/main.py` | FastAPI entry point; creates app with lifespan; registers CORS; imports all 17 routers |
| `backend/app/config.py` | `Settings` dataclass; reads `CODEX_*` env vars; host 127.0.0.1:8700 |
| `backend/app/database.py` | `Base`, `get_engine()`, `get_session()`, `init_db()`; WAL mode SQLite |
| `backend/app/enums.py` | `TaskStatus` (10 states), `ArtifactType` (28), `EventType` (35), `AgentType` (4), `AgentProvider` (6), `AgentRunStatus` (6), `RiskLevel` (4); transition whitelists |

---

## 3. Backend Modules (by Feature)

### 3.1 Project Management

| Layer | File |
|-------|------|
| Router | `backend/app/routers/projects.py` |
| Service | `backend/app/services/project_service.py` |
| Schema | `backend/app/schemas/project.py` |
| Model | `backend/app/models/project.py` |
| Test | `backend/tests/test_mvp_full.py` |

**API**: `GET/POST /api/projects`, `GET/PATCH/DELETE /api/projects/{id}`, `GET /api/projects/{id}/branches`, `POST /api/projects/{id}/sync-git-info`

### 3.2 Task Management (10-state machine)

| Layer | File |
|-------|------|
| Router | `backend/app/routers/tasks.py` |
| Service | `backend/app/services/task_service.py` |
| Schema | `backend/app/schemas/task.py` |
| Model | `backend/app/models/task.py` |
| Test | `backend/tests/test_mvp_full.py` |

**API**: `GET/POST /api/tasks`, `GET/DELETE /api/tasks/{id}`, `POST /api/tasks/{id}/{action}` (generate-ticket, dispatch, submit-result, start-review, approve, reject, request-changes, require-human-approval, archive)

**States**: draft → ticket_ready → dispatched → result_submitted → reviewing → approved/rejected/changes_requested/human_required → archived

### 3.3 Task Events

| Layer | File |
|-------|------|
| Router | `backend/app/routers/events.py` |
| Service | `backend/app/services/event_service.py` |
| Schema | `backend/app/schemas/event.py` |
| Model | `backend/app/models/task_event.py` |

**API**: `GET /api/tasks/{id}/events`

### 3.4 Task Artifacts

| Layer | File |
|-------|------|
| Router | `backend/app/routers/artifacts.py` |
| Service | `backend/app/services/artifact_service.py` |
| Schema | `backend/app/schemas/artifact.py` |
| Model | `backend/app/models/task_artifact.py` |

**API**: `POST /api/tasks/{id}/artifacts`, `GET /api/tasks/{id}/artifacts`, `GET/DELETE /api/tasks/{id}/artifacts/{art_id}`

**Artifact types**: diff, execution_log, review_note, ci_log, screenshot, ticket, plan_md, patch_diff, review_md, risk_report, etc.

### 3.5 Human Reviews

| Layer | File |
|-------|------|
| Router | `backend/app/routers/reviews.py` |
| Service | `backend/app/services/review_service.py` |
| Schema | `backend/app/schemas/review.py` |
| Model | `backend/app/models/review_record.py` |

**API**: `GET/POST /api/tasks/{id}/reviews`

### 3.6 Agent Profiles

| Layer | File |
|-------|------|
| Router | `backend/app/routers/agents.py` |
| Service | `backend/app/services/agent_profile_service.py` |
| Schema | `backend/app/schemas/agent_profile.py` |
| Model | `backend/app/models/agent_profile.py` |
| Test | `backend/tests/test_v02_agent_core.py` |

**API**: `GET/POST /api/agents`, `GET/PATCH/DELETE /api/agents/{id}`

**Supported providers**: sandbox, openai, custom, browser_ai, mock, internal

### 3.7 Agent Runs

| Layer | File |
|-------|------|
| Router | `backend/app/routers/agent_runs.py` |
| Service | `backend/app/services/agent_run_service.py` |
| Schema | `backend/app/schemas/agent_run.py` |
| Model | `backend/app/models/agent_run.py` |

**API**: `POST /api/tasks/{id}/agent-runs`, `GET /api/tasks/{id}/agent-runs`, `GET/PATCH /api/tasks/{id}/agent-runs/{run_id}`, `POST /api/tasks/{id}/agent-runs/{run_id}/submit-result`

**Run types**: plan, execute, review, test, custom
**Run statuses**: queued → running → succeeded → failed, cancelled

### 3.8 AI Agent Reviews

| Layer | File |
|-------|------|
| Router | `backend/app/routers/agent_reviews.py` |
| Service | `backend/app/services/agent_review_service.py` |
| Schema | `backend/app/schemas/agent_review.py` |
| Model | `backend/app/models/agent_review.py` |
| Test | `backend/tests/test_v02_agent_core.py` |

**API**: `POST /api/tasks/{id}/agent-runs/{run_id}/review`, `GET /api/tasks/{id}/agent-reviews`

### 3.9 Approval Policies

| Layer | File |
|-------|------|
| Router | `backend/app/routers/approval_policies.py` |
| Service | `backend/app/services/approval_policy_service.py` |
| Schema | `backend/app/schemas/approval_policy.py` |
| Model | `backend/app/models/approval_policy.py` |
| Test | `backend/tests/test_v02_approval_core.py` |

**API**: `GET/POST /api/approval-policies`, `GET/PATCH/DELETE /api/approval-policies/{id}`

### 3.10 Approval Decisions

| Layer | File |
|-------|------|
| Router | `backend/app/routers/approval.py` |
| Service | `backend/app/services/approval_service.py` |
| Schema | `backend/app/schemas/approval_decision.py` |
| Model | `backend/app/models/approval_decision.py` |
| Test | `backend/tests/test_v02_approval_core.py` |

**API**: `POST /api/tasks/{id}/evaluate-approval`, `POST /api/tasks/{id}/auto-approve`, `GET /api/tasks/{id}/approval-decisions`

### 3.11 Orchestration

| Layer | File |
|-------|------|
| Router | `backend/app/routers/orchestration.py` |
| Service | `backend/app/services/orchestration_service.py` |
| Schema | `backend/app/schemas/orchestration.py` |
| Test | `backend/tests/test_v02_orchestration.py` |

**API**: `GET /api/tasks/{id}/orchestration/status`, `POST /api/tasks/{id}/orchestration/step`, `POST /api/tasks/{id}/orchestration/run`

### 3.12 AI Provider (Sandbox + OpenAI)

| Layer | File |
|-------|------|
| Service (base) | `backend/app/services/ai_provider_base.py` |
| Service (dispatch) | `backend/app/services/ai_provider_service.py` |
| Provider (sandbox) | `backend/app/services/sandbox_provider.py` |
| Provider (OpenAI) | `backend/app/services/openai_provider.py` |
| Schema | `backend/app/schemas/ai_provider.py` |
| Test | `backend/tests/test_v03_ai_provider.py`, `test_v03_real_ai_provider.py` |

**API**: via orchestration dispatch (no direct public endpoints)

### 3.13 AI Output Governance

| Layer | File |
|-------|------|
| Service | `backend/app/services/ai_output_governance_service.py` |
| Test | `backend/tests/test_v03_ai_output_governance.py`, `test_v03_ai_output_governance_integration.py` |

**Checks**: empty output validation, patch diff validation (header/secret/forbidden paths), review parsing, risk report checking, secret redaction (7 patterns)

### 3.14 Risk Assessment

| File | Role |
|------|------|
| `backend/app/services/risk_assessment_service.py` | Keyword-based risk level, secret detection, test/Sonar/confidence scoring |

### 3.15 Ticket Renderer

| File | Role |
|------|------|
| `backend/app/services/ticket_renderer.py` | Generates markdown tickets from task + project data |

### 3.16 Code Context

| Layer | File |
|-------|------|
| Router | `backend/app/routers/code_context.py` |
| Service | `backend/app/services/code_context_service.py` |
| Schema | `backend/app/schemas/code_context.py` |
| Test | `backend/tests/test_v04_ai_coding_sandbox.py` |

**API**: `POST/GET /api/tasks/{id}/code-context`

### 3.17 Patch Apply Sandbox

| Layer | File |
|-------|------|
| Router | `backend/app/routers/patch_sandbox.py` |
| Service | `backend/app/services/patch_apply_sandbox_service.py` |
| Schema | `backend/app/schemas/patch_sandbox.py` |
| Test | `backend/tests/test_v04_ai_coding_sandbox.py` |

**API**: `POST /api/tasks/{id}/agent-runs/{run_id}/sandbox/apply-patch`, `GET /api/tasks/{id}/sandbox/patch-results`

**Features**: in-memory unified diff application on virtual files from code context; forbidden path / secret detection

### 3.18 Sandbox Approval Gate

| Layer | File |
|-------|------|
| Router | `backend/app/routers/sandbox_gate.py` |
| Service | `backend/app/services/sandbox_approval_gate_service.py` |
| Schema | `backend/app/schemas/sandbox_gate.py` |
| Test | `backend/tests/test_sandbox_gate.py` |

**API**: `GET /api/tasks/{id}/sandbox/gate`, `POST /api/tasks/{id}/sandbox/evaluate-gate`

**10 checks**: archived_task, no_sandbox_result, not_applied, no_changed_files, forbidden_path, secret_detected, stale_result, run_unknown, risk_too_high, human_required

### 3.19 Review Packet Preview

| Layer | File |
|-------|------|
| Router | `backend/app/routers/review_packet.py` |
| Service | `backend/app/services/review_packet_service.py` |
| Schema | `backend/app/schemas/review_packet.py` |
| Test | `backend/tests/test_review_packet.py` |

**API**: `POST /api/review-packets/preview`

**Features**: Stateless PR review with MockGitHub/MockSonar; 22 check rules; 9 mock PR scenarios

### 3.20 Stub Endpoints

| File | Role |
|------|------|
| `backend/app/services/pr_builder.py` | STUB — create_pr returns "not implemented" |
| `backend/app/services/ci_client.py` | STUB — trigger_ci returns "not implemented" |
| `backend/app/services/deploy_hook.py` | STUB — trigger_deploy returns "not implemented" |

---

## 4. Health / Utility

| File | Role |
|------|------|
| `backend/app/routers/health.py` | `GET /api/health` — simple health check |

---

## 5. Test Files

| File | Tests | What it covers |
|------|-------|---------------|
| `backend/tests/test_mvp_full.py` | Full MVP flow | Project/Task CRUD, 9-state machine, 404/409, artifacts, reviews, events, stubs |
| `backend/tests/test_v02_agent_core.py` | Agent core | AgentProfile CRUD, AgentRun state machine, AgentReview, ApprovalPolicy, archived protection |
| `backend/tests/test_v02_approval_core.py` | Approval core | Evaluate, auto-approve, policy blocking, multi-policy, human_required |
| `backend/tests/test_v02_orchestration.py` | Orchestration | Status decisions, single-step, multi-step, archived/human_required blocking |
| `backend/tests/test_v03_ai_provider.py` | Sandbox provider | Plan/execute/review/test outputs, artifact creation, orchestration integration |
| `backend/tests/test_v03_real_ai_provider.py` | OpenAI provider | Default fallback, no-key failure, mocked plan/execute/review, governance |
| `backend/tests/test_v03_ai_output_governance.py` | Governance unit | Empty/invalid/patch-diff/review/risk/redaction/forbidden-path |
| `backend/tests/test_v03_ai_output_governance_integration.py` | Governance integration | Sandbox dispatch + governance trace |
| `backend/tests/test_v04_ai_coding_sandbox.py` | Coding sandbox | Code context, patch apply, boundary checks |
| `backend/tests/test_sandbox_gate.py` | Sandbox gate | 10 check scenarios |
| `backend/tests/test_review_packet.py` | Review packet | 9 mock PR scenarios, 22 rules, boundary checks |

---

## 6. Frontend Modules

### 6.1 Core Setup

| File | Role |
|------|------|
| `frontend/src/main.ts` | Vue app bootstrap (createApp + Pinia + Router) |
| `frontend/src/App.vue` | Root layout with top nav |
| `frontend/src/router/index.ts` | Routes: Dashboard, Projects, Tasks, Agents, ApprovalPolicies |
| `frontend/src/types/agent.ts` | All TypeScript interfaces + constants |
| `frontend/src/services/api.ts` | Axios client |
| `frontend/src/services/agentService.ts` | All API client functions |
| `frontend/src/stores/projectStore.ts` | Pinia project store |
| `frontend/src/stores/taskStore.ts` | Pinia task store |
| `frontend/src/styles/base.css` | Global CSS variables and styles |

### 6.2 Pages

| Page | File | Purpose |
|------|------|---------|
| Dashboard | `frontend/src/pages/DashboardPage.vue` | Stats, project overview, activity feed |
| Project List | `frontend/src/pages/ProjectListPage.vue` | CRUD grid |
| Project Config | `frontend/src/pages/ProjectConfigPage.vue` | Tabbed config |
| Task List | `frontend/src/pages/TaskListPage.vue` | Filtered list, pagination |
| Task Create | `frontend/src/pages/TaskCreatePage.vue` | Creation form |
| Task Detail | `frontend/src/pages/TaskDetailPage.vue` | 906 lines — most complex page |
| Agent List | `frontend/src/pages/AgentListPage.vue` | CRUD grid |
| Approval Policy | `frontend/src/pages/ApprovalPolicyPage.vue` | CRUD grid |

### 6.3 Components

| Component | File | Purpose |
|-----------|------|---------|
| StatusBadge | `frontend/src/components/StatusBadge.vue` | Colored status pill |
| DiffViewer | `frontend/src/components/DiffViewer.vue` | Monospace diff display |
| EventTimeline | `frontend/src/components/EventTimeline.vue` | Vertical event timeline |
| ReviewPanel | `frontend/src/components/ReviewPanel.vue` | Review list + form |
| ArtifactTab | `frontend/src/components/ArtifactTab.vue` | Tabbed artifact browser |
| TicketPreview | `frontend/src/components/TicketPreview.vue` | Markdown ticket renderer |

---

## 7. Documentation

| File | Purpose |
|------|---------|
| `docs/releases/v0.1.0.md` | MVP release notes |
| `docs/releases/v0.2.0.md` | Agent/approval/orch release notes |
| `docs/releases/v0.3.0.md` | AI Provider + Governance release notes |
| `docs/releases/v0.4.0.md` | Sandbox/Gate/Review Packet release notes |
| `docs/design/v0.4-browser-ai-provider.md` | Browser AI Provider design (future) |
| `docs/design/v0.4-project-map-codebase-index.md` | This design doc |
| `docs/harness/ai-development-harness.md` | AI development workflow |
| `docs/project-map/codebase-index.md` | This file |
| `docs/project-map/repository-map.json` | Programmatic index |
| `docs/project-map/update-policy.md` | Update rules |

---

## 8. Task-to-File Reference

When implementing a task, start with these files:

| Task Type | Primary Files |
|-----------|---------------|
| Add new router | `routers/`, `services/`, `schemas/`, `tests/`, `main.py` (register router) |
| Add new service | `services/`, `schemas/`, `models/` (if new table), `tests/` |
| Add new schema | `schemas/`, `tests/` |
| Add new model | `models/`, `schemas/`, `services/`, `tests/`, `enums.py` (if new enums) |
| Add new state | `enums.py`, `models/task.py`, `services/task_service.py`, `schemas/task.py`, `tests/` |
| Add new enum | `enums.py`, relevant model/schema/service, `tests/` |
| Add new frontend page | `pages/`, `router/index.ts`, `types/agent.ts` (if new types) |
| Add new API call | `services/agentService.ts`, `types/agent.ts` |
| Update safety boundary | `AGENTS.md`, `docs/project-map/` |
| Add test | `tests/`, match existing pattern |

---

## 9. Safety Boundary Files

### Must Not Modify

| File | Reason |
|------|--------|
| (none enforced at code level — AGENTS.md forbids real external calls, secret access, shell execution) |

### Handle With Care

| File | Reason |
|------|--------|
| `backend/app/main.py` | Router registration order matters |
| `backend/app/enums.py` | State machine integrity — changes affect transitions |
| `backend/app/models/task.py` | Archived guard logic |
| `backend/app/services/task_service.py` | Core state machine transitions |
| `backend/app/services/orchestration_service.py` | Complex orchestration flow |
| `backend/app/services/sandbox_approval_gate_service.py` | 10 security checks |
| `backend/app/services/review_packet_service.py` | 22 PR review rules |
| `backend/app/services/ai_output_governance_service.py` | Secret redaction + validation |
