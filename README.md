# Codex 自动化代码交付平台

> AI 自动代码交付平台 — Agent 编排、AI Provider、Patch Sandbox、Sandbox Gate、Review Packet Automation

---

## 版本状态

| 版本 | 状态 |
|------|------|
| v0.1.0 | MVP 候选基线 — 已固化 |
| v0.2.0 | Agent 后端核心 + 审批 + 自动编排 — 已固化 |
| v0.3.0 | AI Provider + Output Governance + TaskDetail Display — 已固化 |
| v0.4 S1-S4 | Patch Sandbox + Sandbox Gate + Review Packet — 已完成 |
| master | `87c5f01e71baa88b4c1371b4dd987d0a0b66c4bb` |

---

## 快速启动

### 环境要求

- Python >= 3.12
- Node.js >= 18
- npm >= 9

### 后端

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 启动开发服务器
uvicorn app.main:app --host 127.0.0.1 --port 8700 --app-dir backend
```

后端默认监听 `http://127.0.0.1:8700`。

### 前端

```bash
# 安装依赖
cd frontend
npm install

# 启动开发服务器
npx vite --host 127.0.0.1 --port 9700
```

前端默认监听 `http://127.0.0.1:9700`，开发模式下自动代理 `/api` 请求到后端 8700 端口。

### Docker

```bash
docker compose up --build -d
```

---

## 项目结构

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
│   │   ├── pages/                # 7 个页面
│   │   ├── components/           # 组件
│   │   ├── router/               # Vue Router
│   │   ├── stores/               # Pinia 状态管理
│   │   └── services/             # Axios API 封装
│   │── index.html
│   ├── vite.config.ts
│   └── package.json
├── docs/
│   ├── releases/
│   │   ├── v0.1.0.md
│   │   ├── v0.2.0.md
│   │   ├── v0.3.0.md
│   │   └── v0.4.0.md
│── docker-compose.yml
└── README.md
```

---

## 核心能力

| 模块 | 说明 |
|------|------|
| **项目管理** | 注册多项目，配置 Git/CI/部署元信息 |
| **任务管理** | 创建/查看/流转/删除任务 |
| **9 态状态机** | draft → ticket_ready → dispatched → result_submitted → reviewing → changes_requested/approved/rejected → archived |
| **AgentProfile** | Agent 注册、配置、启用/禁用 |
| **AgentRun** | Agent 执行记录创建、状态流转、结果回填 |
| **AgentReview** | AI 审查结论记录 |
| **ApprovalPolicy** | 审批策略 CRUD |
| **RiskAssessment** | 启发式风险评估引擎 |
| **Auto-approve** | 低风险自动审批 |
| **自动循环编排** | orchestrator/step + orchestrator/run 自动推进任务状态 |
| **AI Provider Sandbox** | 模拟 AI Provider，无外部依赖完成全链路验证 |
| **OpenAI Minimal Adapter** | GPT-4o-mini 真实调用适配器 |
| **AI Output Governance** | 输出校验、secret 脱敏、禁止路径检测、风险标记 |
| **Code Context** | 上传代码上下文供 AI Provider 使用 |
| **Patch Apply Sandbox** | 沙箱中验证 patch 合法性并预览变更 |
| **Patch Results Display** | 前端展示沙箱变更文件摘要 |
| **Sandbox Approval Gate** | 沙箱应用前安全检查（secret/禁止路径/风险/人工审批） |
| **Review Packet Preview API** | stateless PR review 预览（MockGitHub/MockSonar connector） |

---

## API 概览

所有接口前缀 `/api`，统一返回 `ApiEnvelope` 格式。

### 基础

| 端点 | 说明 |
|------|------|
| `GET /api/health` | 服务健康检查 |

### 项目

| 端点 | 说明 |
|------|------|
| `GET/POST /api/projects` | 项目列表/创建 |
| `GET/PATCH/DELETE /api/projects/{id}` | 项目详情/更新/删除 |

### 任务

| 端点 | 说明 |
|------|------|
| `GET/POST /api/tasks` | 任务列表/创建 |
| `GET/DELETE /api/tasks/{id}` | 任务详情/删除 |
| `POST /api/tasks/{id}/generate-ticket` | 生成执行任务单 |
| `POST /api/tasks/{id}/dispatch` | 分派任务 |
| `POST /api/tasks/{id}/submit-result` | 提交执行结果 |
| `POST /api/tasks/{id}/start-review` | 开始审查 |
| `POST /api/tasks/{id}/approve` | 审查通过 |
| `POST /api/tasks/{id}/reject` | 审查拒绝 |
| `POST /api/tasks/{id}/request-changes` | 要求修改 |
| `POST /api/tasks/{id}/archive` | 归档 |
| `POST/GET /api/tasks/{id}/artifacts` | 产物上传/列表 |
| `POST/GET /api/tasks/{id}/reviews` | 审查提交/列表 |
| `GET /api/tasks/{id}/events` | 审计日志时间线 |

### Code Context

| 端点 | 说明 |
|------|------|
| `POST /api/tasks/{id}/code-context` | 上传代码上下文 |
| `GET /api/tasks/{id}/code-context` | 读取代码上下文 |

### Agent

| 端点 | 说明 |
|------|------|
| `GET/POST /api/agents` | Agent 列表/创建 |
| `GET/PATCH/DELETE /api/agents/{id}` | Agent 详情/更新/删除 |
| `GET/POST /api/tasks/{id}/agent-runs` | AgentRun 列表/创建 |
| `GET/PATCH /api/tasks/{id}/agent-runs/{run_id}` | AgentRun 详情/更新 |
| `POST /api/tasks/{id}/agent-runs/{run_id}/submit-result` | 提交 AgentRun 结果 |
| `GET /api/tasks/{id}/agent-reviews` | AgentReview 列表 |
| `POST /api/tasks/{id}/agent-reviews` | 创建 AgentReview |

### 审批

| 端点 | 说明 |
|------|------|
| `GET/POST /api/approval-policies` | 审批策略列表/创建 |
| `GET/PATCH/DELETE /api/approval-policies/{id}` | 审批策略详情/更新/删除 |
| `POST /api/tasks/{id}/evaluate-approval` | 评估审批风险 |
| `POST /api/tasks/{id}/auto-approve` | 自动审批 |
| `GET /api/tasks/{id}/approval-decisions` | 审批决策列表 |

### 编排

| 端点 | 说明 |
|------|------|
| `GET /api/tasks/{id}/orchestration/status` | 编排状态 |
| `POST /api/tasks/{id}/orchestration/step` | 单步推进 |
| `POST /api/tasks/{id}/orchestration/run` | 全自动循环 |

### Patch Sandbox

| 端点 | 说明 |
|------|------|
| `POST /api/tasks/{id}/agent-runs/{run_id}/sandbox/apply-patch` | 沙箱应用 patch |
| `GET /api/tasks/{id}/sandbox/patch-results` | 沙箱结果列表 |

### Sandbox Gate

| 端点 | 说明 |
|------|------|
| `GET /api/tasks/{id}/sandbox/gate` | 沙箱门禁评估（只读） |
| `POST /api/tasks/{id}/sandbox/evaluate-gate` | 沙箱门禁评估 + 写事件 |

### Review Packet

| 端点 | 说明 |
|------|------|
| `POST /api/review-packets/preview` | Review Packet 预览（stateless） |

完整 API 文档通过 `GET /docs`（Swagger UI）或 `GET /redoc`（ReDoc）查看。

---

## 运行测试

```bash
# 全部 283 项测试
python -m pytest backend/tests/ -v --rootdir backend

# 单文件
python -m pytest backend/tests/test_review_packet.py -v --rootdir backend
```

### 最新测试结果

| 测试项 | 结果 |
|--------|------|
| pytest（后端） | **283 passed** |
| compileall | **通过** |
| SonarCloud Quality Gate | **Passed** |
| Security Hotspots | **0** |
| Duplication on New Code | **0.0%** |

---

## 安全边界

| 规则 | 状态 |
|------|------|
| 不访问 Project.root_path | ✅ |
| 不执行 shell / subprocess / os.system | ✅ |
| 不创建真实 GitHub PR | ✅ |
| 不调用真实 CI | ✅ |
| 不调用真实 Sonar API | ✅ |
| 不部署 | ✅ |
| 不读取 secret_ref | ✅ |
| Browser AI Provider 尚未实现 | ⏳ |
| 后端仅监听 127.0.0.1 | ✅ |

---

## 分支规范

| 分支 | 用途 |
|------|------|
| `master` | 稳定主线，只合入验收通过的代码 |
| `feature/*` | 新功能 |
| `fix/*` | Bug 修复 |
| `test/*` | 测试验证 |
| `docs/*` | 文档 |
| `release/*` | 版本发布 |

---

## 版本历史

- **v0.4.0** (2026-05-20) — Patch Sandbox + Sandbox Gate + Review Packet Preview API
- **v0.3.0** (2026-05-20) — AI Provider + Output Governance + TaskDetail Display
- **v0.2.0** (2026-05-19) — Agent 后端核心 + 审批 + 自动编排
- **v0.1.0** (2025-07-16) — MVP 候选基线
