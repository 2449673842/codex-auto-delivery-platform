# Codex Automation Delivery Platform — AI Agent Rules

## Project Overview

AI 自动代码交付平台 — Agent 编排、AI Provider、Patch Sandbox、Sandbox Gate、Review Packet Automation。

当前版本：**v0.4.0**
master commit：`d2480224c73feb531182bdad9e9e4461dea2a8f3`
tag：`v0.4.0`

## Directory Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py             # 配置项
│   │   ├── database.py           # SQLite + async SQLAlchemy
│   │   ├── enums.py              # 状态机 + 跃迁白名单
│   │   ├── models/               # ORM 模型
│   │   ├── schemas/              # Pydantic 请求/响应
│   │   ├── routers/              # API 路由
│   │   └── services/             # 业务逻辑
│   ├── data/                     # SQLite 数据库文件
│   ├── tests/                    # pytest 测试
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── router/
│   │   ├── stores/
│   │   └── services/
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
├── docs/
│   ├── releases/
│   │   ├── v0.1.0.md
│   │   ├── v0.2.0.md
│   │   ├── v0.3.0.md
│   │   └── v0.4.0.md
│   ├── design/
│   │   └── v0.4-browser-ai-provider.md
│   ├── project-map/
│   │   ├── codebase-index.md
│   │   ├── repository-map.json
│   │   └── update-policy.md
│   └── harness/
│       └── ai-development-harness.md
├── scripts/
│   └── ai_verify.sh
├── AGENTS.md
└── README.md
```

## Version Status

| Version | Status |
|---------|--------|
| v0.1.0 | MVP baseline — frozen |
| v0.2.0 | Agent core + approval + orchestration — frozen |
| v0.3.0 | AI Provider + Output Governance + TaskDetail Display — frozen |
| v0.4.0 | Patch Sandbox + Sandbox Gate + Review Packet — frozen |
| v0.4.0 S6-S7 | Browser AI Provider Design + Project Map & Codebase Index — frozen |
| v0.4.0 S8 | Context Selector from Project Map — in progress |

## Safety Boundaries

### Forbidden

- Do **not** access `Project.root_path`
- Do **not** execute shell / subprocess / os.system for business operations
- Do **not** read `secret_ref`
- Do **not** read `.env` files, tokens, API keys
- Do **not** git clone / commit / push (except via controlled PR flow)
- Do **not** directly push to `master`
- Do **not** create real GitHub PRs
- Do **not** call real CI APIs
- Do **not** call real Sonar API
- Do **not** deploy
- Do **not** auto-approve `human_required` tasks
- Do **not** auto-approve high/critical risk tasks
- Do **not** write business data after task is `archived`
- Do **not** implement Browser AI Provider (not yet designed)
- Do **not** implement real GitHub PR Adapter (not yet designed)
- Review Packet currently uses **MockGitHub / MockSonar connectors** — do not call real APIs

## Verification Commands

### Backend Tests

```bash
# Full test suite
python -m pytest backend/tests/ -v --rootdir backend

# Single file
python -m pytest backend/tests/test_mvp_full.py -v --rootdir backend

# Current count: 298 passed
```

### compileall

```bash
python -m compileall backend/app
```

### Frontend Build

```bash
cd frontend
npm install
npx vite build
```

### Playwright / MCP (when applicable)

```bash
cd frontend
npx playwright test
```

### SonarCloud

- Quality Gate must be **Passed** before requesting merge
- Security Hotspots must be **0**
- Duplication on New Code must be ≤ **3%**

## Branch / PR Rules

| Branch | Purpose |
|--------|---------|
| `master` | Stable mainline; only merge reviewed code |
| `feature/*` | New features |
| `fix/*` | Bug fixes |
| `test/*` | Test verification |
| `docs/*` | Documentation |
| `release/*` | Version releases |

### Workflow

1. Branch from latest `master`
2. Make changes
3. Run verification commands
4. Commit and push
5. Create PR
6. Wait for **mastermind review**
7. Apply fixes if blocked
8. After approval, mastermind merges (or gives permission)

## PR Body Requirements

Every PR must include the following fields in its body:

| Field | Required | Notes |
|-------|----------|-------|
| PR URL | ✅ | |
| PR number | ✅ | |
| head commit full SHA | ✅ | Short hash is **not** acceptable |
| base commit | ✅ | |
| changed files count + list | ✅ | Must match GitHub reality |
| pytest full result | ✅ | |
| compileall result | ✅ | |
| npm build result | ✅ if frontend changes | |
| Playwright / MCP result | ✅ if UI changes | |
| SonarCloud Quality Gate | ✅ | |
| Security Hotspots | ✅ | |
| Duplication on New Code | ✅ | |
| DB migration? | ✅ | |
| Frontend changes? | ✅ | |
| Backend changes? | ✅ | |
| New real GitHub PR/CI/Sonar/Deploy? | ✅ | Must be "no" unless explicitly planned |
| Project.root_path accessed? | ✅ | Must be "no" |
| shell/subprocess executed? | ✅ | Must be "no" |
| secret_ref read? | ✅ | Must be "no" |
| GitHub reference survey | ✅ for larger features | Search keywords, ref projects, borrowed points, rejected points, no-copy declaration |
| Project Map updated? | ✅ | yes / no / not_needed — see docs/project-map/update-policy.md |
| Safety boundary self-check | ✅ | |
| Known risks / unfinished | ✅ | |

### PR Body Consistency Rules

- PR body **must match** GitHub reality
- `changed_files` count must equal GitHub PR changed files count
- pytest number must match actual test output
- Sonar status must match current SonarCloud report
- **Inconsistency blocks merge**

## Mastermind Review Rules

- **AI1 cannot self-review or self-merge**
- AI1 cannot directly push to master
- All merges require mastermind review
- Mastermind checks against **real GitHub code**, not the report
- If report and code disagree, **code wins**
- SonarCloud failed → **blocked**
- pytest count mismatch → **blocked**
- changed files mismatch → **blocked** or **needs_update**
- Out-of-scope modifications → **blocked**
- Safety boundary violation → **blocked**
- Stale PR body → **blocked**
- Empty tests / pass placeholders / relaxed assertions → **blocked**

## Definition of Done

A task is complete only when ALL of the following are true:

- [ ] Functionality matches task scope
- [ ] Changed files match scope
- [ ] pytest passes
- [ ] compileall passes
- [ ] npm build passes (if frontend involved)
- [ ] Playwright / MCP passes (if UI involved)
- [ ] SonarCloud Quality Gate: **Passed**
- [ ] Security Hotspots: **0**
- [ ] PR body matches real results
- [ ] No undocumented DB migration
- [ ] No undocumented real external API entry
- [ ] Safety boundaries maintained
- [ ] Mastermind review approved
- [ ] Master commit reported after merge

## Common Failure Modes

| Failure | Cause | Prevention |
|---------|-------|------------|
| pytest count mismatch | Report != actual | Run pytest, copy exact output |
| changed files wrong | Guessed from local | Check GitHub PR files tab |
| Sonar failed | Code quality issue | Fix before requesting merge |
| PR body stale | Copied from old PR | Refresh all fields |
| Out-of-scope files | Branch drift | Check `git diff master...HEAD` |
| Safety boundary broken | Side effect | Review every new file for safety |
| Pass placeholder tests | `def test_x(): pass` | Never submit empty tests |
| Relaxed assertions | `assert True` | Write meaningful assertions |
| Secret exposed | Hardcoded in test/mock | Use `***REDACTED***` pattern |

## GitHub Reference Survey

Before starting larger features, mastermind produces a Reference Brief.

AI1 may supplement research, but PR body must include:

- Search keywords used
- Reference projects evaluated
- Borrowed design points
- Rejected approaches and why
- Explicit declaration: **no copyrighted code copied**

### Prohibited

- Directly copying code from external projects
- Importing license-incompatible code
- Using hidden APIs / workarounds as primary solution
- Using external code to bypass project safety boundaries

## AI1 Self-Restrictions

- AI1 must **not** review or merge its own PRs
- AI1 must **not** push directly to master
- AI1 must **not** report numbers that differ from real verification output
- AI1 must **not** submit tests with `pass` placeholder or relaxed assertions without explanation
- AI1 must **stop and ask** mastermind when unsure about scope, safety, or design
