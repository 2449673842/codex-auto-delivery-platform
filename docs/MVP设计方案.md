# 自动化代码交付平台 — MVP 设计方案（用户确认修订版）

> 版本：v0.3 · 修订日期：2025-07-16
> 状态：用户已确认，可进入项目骨架搭建
> 目标层级：多项目自动化代码交付平台（非单项目任务流转小工具）

---

## 1. 项目目标

构建一个面向 **多项目** 的自动化代码交付平台 MVP，将「需求→任务单→AI 执行→Review→PR→CI→部署」流程做标准化管理。

**核心目标（MVP 可达）**：
- 注册和管理多个项目及其 Git / 构建 / 部署元信息
- 创建任务 → 生成结构化的执行任务单给 AI Executor
- 粘贴执行结果（日志 + Diff）并持久化
- 记录 Reviewer 审核结论
- 完整的状态流转追踪
- 全程审计日志

**基础设施目标（MVP 铺路，不实现）**：
- GitHub PR 自动创建 / 更新
- CI 状态轮询与展示
- SonarQube 扫描结果集成
- Docker 部署触发

---

## 2. 使用场景

| 场景 | 描述 |
|------|------|
| **修复 Bug** | 用户描述 bug → 平台生成任务单 → Executor AI 改代码 → 粘贴结果 → Review → 生成 PR 建议 |
| **添加小功能** | 需求描述 → 拆解为任务 → Executor 实现 → Review → Approve → PR |
| **多项目管理** | 在同一平台管理量化交易后端、前端、数据流水线三个项目的任务与交付 |
| **AI Review 辅助** | Executor 提交代码后，Reviewer AI 自动检查代码规范、安全隐患 |
| **交付追溯** | 通过 TaskEvent 审计日志查看「谁在什么时候做了什么决策」 |

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Vue3)                   │
│                    Port 9700                         │
│  Dashboard | TaskList | TaskDetail | ProjectConfig  │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP / REST (JSON)
                  │ CORS 127.0.0.1
┌─────────────────▼───────────────────────────────────┐
│                 Backend (FastAPI)                     │
│                 Port 8700                             │
│                                                       │
│  Routers → Services → SQLAlchemy ORM → SQLite        │
│                                                       │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐   │
│  │ TaskEngine │  │ TicketGen  │  │ AuditLogger  │   │
│  └────────────┘  └────────────┘  └──────────────┘   │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐   │
│  │ PRBuilder  │  │ CIClient   │  │ DeployHook   │   │
│  │ (stub)     │  │ (stub)     │  │ (stub)       │   │
│  └────────────┘  └────────────┘  └──────────────┘   │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│                  SQLite (data/codex_platform.db)      │
│  Project | Task | TaskArtifact | TaskEvent            │
│             + ReviewRecord                             │
└─────────────────────────────────────────────────────┘
```

> **注意**：图中 Agent 未建表。AgentProfile 表为后续版本预留，MVP 不实现。

**分层原则**：
- Router 只做 HTTP 路由 + 参数提取，不写业务逻辑
- Service 层聚合业务规则，不直接依赖 Request/Response
- 所有 Stub 模块（PRBuilder / CIClient / DeployHook）有接口定义但返回 `NotImplementedError`，MVP 不接通

---

## 4. 多项目模型

### 4.1 Project 表

平台第一公民。所有任务都属于某个项目。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK AUTO | 自增主键 |
| `name` | TEXT NOT NULL UNIQUE | 项目名称（如 `trading-backend`） |
| `display_name` | TEXT | 中文展示名（如「量化回测后端」） |
| `root_path` | TEXT NOT NULL | 项目根目录绝对路径 |
| `repo_url` | TEXT | Git 远程仓库地址（如 `https://github.com/xxx/trading.git`） |
| `default_branch` | TEXT DEFAULT `main` | 默认分支名 |
| `current_branch` | TEXT DEFAULT `main` | 当前工作分支 |
| `frontend_path` | TEXT | 前端子目录（如 `frontend/`），null 表示纯后端项目 |
| `backend_path` | TEXT | 后端子目录（如 `backend/`），null 表示纯前端项目 |
| `package_manager` | TEXT | `npm` / `pnpm` / `pip` / `poetry` / `go mod` 等 |
| `dev_command` | TEXT | 本地开发启动命令 |
| `build_command` | TEXT | 构建命令 |
| `test_command` | TEXT | 测试命令 |
| `docker_compose_path` | TEXT | docker-compose.yml 相对路径 |
| `ci_provider` | TEXT | CI 类型（预留：`github_actions` / `jenkins` / `none`） |
| `ci_url` | TEXT | CI 仪表盘地址（预留） |
| `deploy_provider` | TEXT | 部署方式（预留：`docker` / `k8s` / `manual` / `none`） |
| `deploy_url` | TEXT | 部署环境地址（预留） |
| `is_active` | BOOLEAN DEFAULT `1` | 是否启用 |
| `created_at` | DATETIME DEFAULT now | 创建时间 |
| `updated_at` | DATETIME DEFAULT now | 最后更新时间 |

### 4.2 项目相关预留接口

MVP 阶段 Projects API 只做 CRUD + 配置管理，不涉及真实 Git/CI 操作：

| 方法 | 路径 | MVP 行为 |
|------|------|----------|
| `GET` | `/api/projects` | 列表 |
| `POST` | `/api/projects` | 创建（记录元信息） |
| `GET` | `/api/projects/{id}` | 详情 |
| `PATCH` | `/api/projects/{id}` | 更新配置 |
| `DELETE` | `/api/projects/{id}` | 删除（仅无可关联任务时） |
| `GET` | `/api/projects/{id}/branches` | 返回 `default_branch` + `current_branch`（预留远程查询） |
| `POST` | `/api/projects/{id}/sync-git-info` | Stub：返回 `{"message": "git info sync not implemented in MVP"}` |

---

## 5. 角色分工

平台定义四种角色，MVP 阶段由人工指定（字符串字段），不涉及认证系统。

| 角色 | 标识符 | 职责 | MVP 实现方式 |
|------|--------|------|-------------|
| **Planner** | `planner` | 编写需求描述、拆解任务、审核任务单 | Task 表的 `planner` 字段，用户创建任务时填写 |
| **Executor AI** | `executor` | 接收任务单、编写/修改代码、输出 diff + log | Task 表的 `executor` 字段；平台不调用 AI，只生成任务单供外部读取 |
| **Reviewer** | `reviewer` | 代码审查、安全扫描、质量门禁 | ReviewRecord 表的 `reviewer` 字段；意见人工粘贴或后续集成 |
| **Human Approver** | `human_approver` | 最终批准/拒绝上线 | Task 表的 `human_approver` 字段；Approve/Reject 按钮 |

**数据落地**：Task 表新增四个字段：

```
planner         TEXT        — 规划者标识
executor        TEXT        — 执行者标识
reviewer        TEXT        — 审查者标识
human_approver  TEXT        — 最终批准人标识
```

**MVP 阶段不做独立 AgentProfile 表**。四个角色字段直接存储为 Task 表的字符串字段，无需关联外键。独立的 AgentProfile 表（含 agent 复用、权限级别、默认项目等）属于后续版本扩展，不在 MVP 建表计划内。

---

## 6. 权限边界

第一版无用户系统，权限通过以下设计保障：

### 6.1 网络边界

| 层级 | 规则 |
|------|------|
| 监听地址 | `127.0.0.1` 仅本地访问，不绑定 `0.0.0.0` |
| CORS | 仅允许 `http://127.0.0.1:9700` |
| 端口 | 后端 `8700`，前端 `9700` — 避让实盘交易系统 |

### 6.2 数据边界

| 项目 | 规则 |
|------|------|
| 敏感信息 | 不存储任何明文 token / API key / 密码 |
| Secret 读取 | 仅通过环境变量注入，不在数据库或 UI 中展示 |
| 项目路径 | Project 表记录路径仅用于展示，平台不读写该路径下的文件 |
| 日志 | 不记录用户输入中的疑似敏感字符串 |

### 6.3 操作边界

| 操作 | 规则 |
|------|------|
| 执行代码 | 永不！平台不 executor 沙箱、不 runner、不 shell |
| Git 操作 | MVP 不 clone、不 fetch、不 push、不 merge |
| 自动合并 | 禁止自动 merge main |
| 自动部署 | 禁止无确认部署 |
| 文件删除 | 禁止删除项目目录或任何磁盘文件 |
| 高危命令 | 未来集成命令执行时，`rm -rf` / `git reset --hard` / `git checkout main` / `drop database` 必须人工确认 |
| 所有操作 | 全部写入 TaskEvent 审计日志 |
| root_path 访问 | 平台不主动访问 Project.root_path；不调用 `os.path.exists()`；不扫描目录；不读取文件；不执行该路径下任何命令。路径仅用于展示和任务单上下文填充 |
| validate-path 接口 | 后续预留，MVP 不做 |

---

## 7. MVP 功能范围

### ✅ 包含（In Scope）

| 模块 | 功能 |
|------|------|
| **项目管理** | CRUD 项目 + 配置 Git/CI/部署元信息 |
| **任务管理** | 创建 / 查看 / 列表 / 删除任务；状态流转全链路 |
| **任务单生成** | 根据任务描述 + 项目配置，生成 Markdown 任务单供 Executor AI 读取 |
| **执行结果** | 粘贴 Executor AI 的执行日志和代码 Diff |
| **Review** | 提交 / 查看 Review 结果；Approve / Reject 决策 |
| **审计日志** | 所有状态变更和关键操作写入 TaskEvent |
| **产物管理** | Diff / Log 等存入 TaskArtifact 独立表，支持多轮执行 |
| **角色标记** | Task 上标记 Planner / Executor / Reviewer / Human Approver |

### ❌ 不包含（Not in MVP — 详见第 8 节）

Git 操作、CI 集成、Sonar、部署、用户认证、WebSocket、LLM 调用、代码执行

---

## 8. 暂不做功能

| 功能 | 原因 | 预留方式 |
|------|------|----------|
| 用户认证 / JWT | MVP 无多用户场景 | 项目已预留 `actor` 字段，后续加认证只需替换中间件 |
| WebSocket 实时推送 | 手动刷新已够 | 后续可加 `/ws/task/{id}` |
| GitHub API 真实调用 | 需要 token 管理 + webhook 注册 | 预留 `repo_url`、`ci_url`、`deploy_url`、`PRBuilder` stub |
| CI 集成 | 需要 webhook 接收 + 状态回写 | 预留 `ci_provider`、`ci_url`、stub service |
| SonarQube 扫描 | 需要扫描服务 | 预留 `sonar_passed` 字段 |
| Docker 部署触发 | 需要对接 Docker daemon | 预留 `deploy_provider`、`deploy_url`、stub service |
| AI 大模型 API 调用 | 平台不做 executor | 只生成任务单文本，不调 LLM |
| 代码执行沙箱 | 安全风险高 | 永不 |
| 文件上传 | 文本粘贴已覆盖 MVP | 后续可加 |
| 自动归档 / 清理 | MVP 数据量小 | 后续可加 |
| 数据库迁移（Alembic） | SQLite 直接在代码建表 | 迁移到 PG 时引入 |
| 多轮返工工作流 | MVP 只支持单次执行 → Review | 状态机预留 `changes_requested` 字段支持返回 |

---

## 9. 后端目录结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口，注册路由 + CORS + 中间件
│   ├── config.py                # 配置（端口、DB 路径、环境变量名常量等）
│   ├── database.py              # SQLAlchemy async engine + session + 建表
│   ├── enums.py                 # TaskStatus、ArtifactType、EventType 枚举
│   │
│   ├── models/                  # SQLAlchemy ORM 模型
│   │   ├── __init__.py
│   │   ├── project.py           # Project
│   │   ├── task.py              # Task
│   │   ├── task_artifact.py     # TaskArtifact
│   │   ├── task_event.py        # TaskEvent（审计日志）
│   │   └── review_record.py     # ReviewRecord
│   │
│   ├── schemas/                 # Pydantic 模型（API 请求/响应）
│   │   ├── __init__.py
│   │   ├── common.py            # ApiEnvelope[T], Pagination
│   │   ├── project.py           # ProjectCreate/Response/List
│   │   ├── task.py              # TaskCreate/Response/List, StatusTransition
│   │   ├── artifact.py          # ArtifactCreate/Response
│   │   ├── event.py             # EventResponse
│   │   └── review.py            # ReviewCreate/Response
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py            # GET /api/health
│   │   ├── projects.py          # /api/projects CRUD
│   │   ├── tasks.py             # /api/tasks 全流程
│   │   ├── artifacts.py         # /api/tasks/{id}/artifacts
│   │   ├── events.py            # /api/tasks/{id}/events（只读）
│   │   └── reviews.py           # /api/tasks/{id}/review
│   │
│   └── services/
│       ├── __init__.py
│       ├── project_service.py   # 项目 CRUD + 校验
│       ├── task_service.py      # 任务全生命周期 + 状态机
│       ├── ticket_renderer.py   # 根据 Project + Task 生成 Markdown 任务单
│       ├── artifact_service.py  # 产物存储
│       ├── event_service.py     # 审计日志写入
│       ├── review_service.py    # Review 提交 + 决策
│       ├── pr_builder.py        # STUB — PR 构建器接口定义
│       ├── ci_client.py         # STUB — CI 客户端接口定义
│       └── deploy_hook.py       # STUB — 部署触发接口定义
│
├── data/                        # SQLite DB 文件
│   └── .gitkeep
│
├── tests/                       # pytest
│   ├── conftest.py
│   ├── test_task_lifecycle.py   # 完整流程测试
│   └── test_state_machine.py    # 状态跃迁白名单测试
│
├── requirements.txt
└── Dockerfile
```

---

## 10. 前端目录结构

```
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   │
│   ├── router/
│   │   └── index.ts             # 路由配置
│   │
│   ├── stores/
│   │   ├── projectStore.ts      # 项目列表 + 当前项目
│   │   └── taskStore.ts         # 任务列表 + 当前任务
│   │
│   ├── services/
│   │   └── api.ts               # Axios 实例 + 所有 API 函数
│   │
│   ├── pages/
│   │   ├── DashboardPage.vue    # 概览（多项目卡片 + 全局统计）
│   │   ├── ProjectListPage.vue  # 项目列表
│   │   ├── ProjectConfigPage.vue# 项目配置表单（Git/CI/部署元信息）
│   │   ├── TaskListPage.vue     # 当前项目的任务列表
│   │   ├── TaskCreatePage.vue   # 新建任务
│   │   └── TaskDetailPage.vue   # 任务详情（完整工作流面板）
│   │
│   ├── components/
│   │   ├── ProjectCard.vue      # 项目卡片
│   │   ├── TaskCard.vue         # 任务卡片
│   │   ├── StatusBadge.vue      # 状态标签
│   │   ├── DiffViewer.vue       # Diff 只读对比组件
│   │   ├── ReviewPanel.vue      # Review 结果展示 + 操作
│   │   ├── TicketPreview.vue    # 任务单 Markdown 渲染
│   │   ├── EventTimeline.vue    # 审计日志时间线
│   │   └── ArtifactTab.vue      # 产物切换标签（Diff / Log / CI-Log）
│   │
│   └── styles/
│       └── base.css
│
├── index.html
├── package.json
├── vite.config.ts
└── tsconfig.json
```

---

## 11. SQLite 数据模型

### 11.1 Project

见第 4 节，不再重复。

### 11.2 Task

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK AUTO | 自增主键 |
| `project_id` | INTEGER FK → Project.id | 所属项目 **（NOT NULL）** |
| `title` | TEXT NOT NULL | 任务标题 |
| `description` | TEXT | 详细需求描述（Markdown） |
| `status` | TEXT NOT NULL | 状态机：见第 14 节 |
| `priority` | TEXT DEFAULT `medium` | `low` / `medium` / `high` |
| `source` | TEXT DEFAULT `manual` | 创建来源 |
| `planner` | TEXT | 规划者标识 |
| `executor` | TEXT | 执行者标识 |
| `reviewer` | TEXT | 审查者标识 |
| `human_approver` | TEXT | 最终批准人标识 |
| `ticket_content` | TEXT | 生成的执行任务单（Markdown） |
| `result_summary` | TEXT | 执行结果摘要 |
| `pr_url` | TEXT | PR 链接（预留） |
| `ci_url` | TEXT | CI 构建链接（预留） |
| `deploy_url` | TEXT | 部署环境链接（预留） |
| `target_branch` | TEXT | 目标分支（预留） |
| `created_at` | DATETIME DEFAULT now | 创建时间 |
| `updated_at` | DATETIME DEFAULT now | 最后更新时间 |

### 11.3 TaskArtifact

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK AUTO | |
| `task_id` | INTEGER FK → Task.id | 关联任务 |
| `artifact_type` | TEXT NOT NULL | `execution_log` / `diff` / `review_note` / `ci_log` / `screenshot` |
| `storage_type` | TEXT DEFAULT `sqlite` | `sqlite`（内容存 content 字段）或 `file`（内容存 file_path 指向的外部文件） |
| `content` | TEXT | 文本内容。`storage_type=sqlite` 时使用；`storage_type=file` 时可为空 |
| `file_path` | TEXT | 外部文件路径。`storage_type=file` 时指向 `data/artifacts/{task_id}/` 下的文件；`storage_type=sqlite` 时为空 |
| `filename` | TEXT | 可选原始文件名 |
| `size_bytes` | INTEGER | 产物大小（字节） |
| `sha256` | TEXT | 内容 SHA-256 哈希 |
| `is_truncated` | BOOLEAN DEFAULT `0` | 内容是否因过大被截断 |
| `metadata_json` | TEXT | 额外元信息（JSON，如行数、语言） |
| `created_at` | DATETIME DEFAULT now | |

**存储策略**：
- MVP 实现仅使用 `storage_type=sqlite` + `content` 字段
- 当单次任务产物超过 100MB 时，后续版本可迁移到 `storage_type=file`，文件落盘 `data/artifacts/{task_id}/` 目录
- 模型从设计上不锁定为 `content` 唯一路径

### 11.4 TaskEvent（审计日志）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK AUTO | |
| `task_id` | INTEGER FK → Task.id | 关联任务 |
| `event_type` | TEXT NOT NULL | `status_changed` / `artifact_uploaded` / `review_submitted` / `ticket_generated` / `note_added` |
| `actor` | TEXT | 操作人标识 |
| `from_status` | TEXT | 变更前状态（状态变更事件） |
| `to_status` | TEXT | 变更后状态（状态变更事件） |
| `message` | TEXT | 人类可读描述 |
| `payload_json` | TEXT | 结构化负载（JSON） |
| `created_at` | DATETIME DEFAULT now | |

**MVP 每个关键操作必须写 Event**：
- 创建任务 → `status_changed` (null → draft)
- 生成任务单 → `ticket_generated`
- 分派 → `status_changed`
- 提交结果 → `artifact_uploaded` + `status_changed`
- 提交 Review → `review_submitted`
- Approve / Reject → `status_changed`

### 11.5 ReviewRecord

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK AUTO | |
| `task_id` | INTEGER FK → Task.id | 关联任务 |
| `reviewer` | TEXT | 审查者标识 |
| `decision` | TEXT NOT NULL | `approved` / `rejected` / `changes_requested` |
| `comments` | TEXT | 审查意见 |
| `issues` | TEXT (JSON) | `[{severity, file, line, message}]` |
| `linter_passed` | BOOLEAN | 是否通过 lint |
| `sonar_passed` | BOOLEAN | 预留 |
| `ci_passed` | BOOLEAN | 预留 |
| `created_at` | DATETIME DEFAULT now | |

### 11.6 ER 关系

```
Project 1──N Task
Task    1──N TaskArtifact
Task    1──N TaskEvent
Task    1──N ReviewRecord
```

---

## 12. API 路由设计

所有路由前缀 `/api`。全部返回 `ApiEnvelope<T>`。

### 12.1 Health

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 服务状态 |

### 12.2 Projects

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/projects` | 项目列表 |
| `POST` | `/api/projects` | 创建项目 |
| `GET` | `/api/projects/{id}` | 项目详情 |
| `PATCH` | `/api/projects/{id}` | 更新项目配置 |
| `DELETE` | `/api/projects/{id}` | 删除（仅无关联任务时） |
| `GET` | `/api/projects/{id}/tasks` | 该项目下的任务列表（支持 `?status=` 过滤） |

### 12.3 Tasks

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tasks` | 全局任务列表（支持 `?project_id=&status=&page=&size=`） |
| `POST` | `/api/tasks` | 创建任务（body 含 `project_id`） |
| `GET` | `/api/tasks/{id}` | 任务详情（含关联 artifacts / review / events 概览） |
| `DELETE` | `/api/tasks/{id}` | 删除（仅 `draft` 状态可删） |

### 12.4 Task 流程操作

| 方法 | 路径 | 状态跃迁 | 说明 |
|------|------|----------|------|
| `POST` | `/api/tasks/{id}/generate-ticket` | → `ticket_ready` | 生成执行任务单 |
| `POST` | `/api/tasks/{id}/dispatch` | → `dispatched` | 标记已分派给 Executor |
| `POST` | `/api/tasks/{id}/submit-result` | → `result_submitted` | 提交执行结果（body 含 summary, 后续 artifacts 独立上传） |
| `POST` | `/api/tasks/{id}/start-review` | → `reviewing` | 进入审查 |
| `POST` | `/api/tasks/{id}/approve` | → `approved` | 审查通过 |
| `POST` | `/api/tasks/{id}/reject` | → `rejected` | 审查拒绝 |
| `POST` | `/api/tasks/{id}/request-changes` | → `changes_requested` | 要求修改 |
| `POST` | `/api/tasks/{id}/archive` | → `archived` | 归档 |

### 12.5 Artifacts

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks/{id}/artifacts` | 上传产物（type + content） |
| `GET` | `/api/tasks/{id}/artifacts` | 产物列表 |
| `GET` | `/api/tasks/{id}/artifacts/{aid}` | 产物详情 |
| `DELETE` | `/api/tasks/{id}/artifacts/{aid}` | 删除产物 |

### 12.6 Events（审计日志）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tasks/{id}/events` | 获取任务事件时间线（按 created_at 升序） |

### 12.7 Reviews

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tasks/{id}/reviews` | 审查记录列表（支持多轮） |
| `POST` | `/api/tasks/{id}/reviews` | 提交审查结论 |

### 12.8 Stub 端点（预留，返回固定消息）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks/{id}/create-pr` | Stub — 返回 `"PR creation not implemented"` |
| `POST` | `/api/tasks/{id}/trigger-ci` | Stub — 返回 `"CI trigger not implemented"` |
| `POST` | `/api/tasks/{id}/trigger-deploy` | Stub — 返回 `"Deploy not implemented"` |

---

## 13. 页面设计

共 **6 个页面**。

### 13.1 DashboardPage `/`

| 区块 | 内容 |
|------|------|
| 项目快速切换 | 顶部 Project 下拉选择器（全局状态存储在 projectStore） |
| 统计卡片 | 4 张：总任务 / 待处理 / Review 中 / 已通过 |
| 项目概览 | 每个项目一张小卡片：名称、分支、CI 状态（预留） |
| 最近活动 | 最近 10 条 TaskEvent（全局） |

### 13.2 ProjectListPage `/projects`

- 项目卡片网格
- 每张卡片显示：名称、Git 分支、构建命令摘要
- 点击进入 ProjectConfigPage

### 13.3 ProjectConfigPage `/projects/:id`

- 表单编辑所有 Project 字段
- 分 Tab：基本信息 / Git 配置 / 构建命令 / CI & 部署（预留）
- 底部「查看项目任务」按钮跳转到 TaskListPage（带 `?project_id=`）

### 13.4 TaskListPage `/tasks?project_id=xxx`

- 顶部显示当前项目名称
- 状态过滤 tabs（9 态）
- 搜索框
- 任务卡片列表
- 「新建任务」按钮

### 13.5 TaskCreatePage `/tasks/new?project_id=xxx`

- 标题（必填）
- 描述（textarea，Markdown）
- 优先级
- Planner / Executor 标识
- 目标分支（可选）
- 提交 → 跳转 TaskDetailPage

### 13.6 TaskDetailPage `/tasks/:id`

从上到下分区：

| 区域 | 内容 |
|------|------|
| **Header** | 标题 + 项目名 + 状态 Badge + 优先级 + 角色标签 |
| **操作栏** | 根据状态显示可用按钮（generate-ticket / dispatch / submit-result / start-review / approve / reject / request-changes / archive） |
| **描述区** | 只读 Markdown 渲染 |
| **任务单** | TicketPreview 组件（生成后可见） |
| **产物 Tab** | ArtifactTab 组件：切换查看 Diff / Log / CI Log |
| **Review 面板** | ReviewPanel 展示审查结论 + 问题列表 + 操作按钮 |
| **审计时间线** | EventTimeline 组件：从创建到当前的所有事件 |
| **预留集成区** | 灰色占位：PR 链接 · CI 状态 · 部署状态（仅占位） |

---

## 14. 任务状态流转

> 共 **9 态**。

### 14.1 状态定义

```
draft              新建，未生成任务单
ticket_ready       任务单已生成，待分派
dispatched         已分派给 Executor AI
result_submitted   Executor 提交了执行结果
reviewing          进入审查
changes_requested  审查要求修改，返回 dispatched
approved           审查通过
rejected           审查拒绝
archived           归档，终态
```

**archived 终态规则**：进入 archived 后禁止一切修改操作——禁止编辑 Task 字段、禁止上传 Artifact、禁止修改 Review、禁止状态跃迁。仅允许查看（GET 请求）。

### 14.2 完整状态图

```
                        ┌──────────────────────────┐
                        │        draft              │
                        └──────────┬───────────────┘
                                   │ generate-ticket
                        ┌──────────▼───────────────┐
                        │     ticket_ready          │
                        └──────────┬───────────────┘
                                   │ dispatch
                        ┌──────────▼───────────────┐
                        │      dispatched           │
                        └──────────┬───────────────┘
                                   │ submit-result
                        ┌──────────▼───────────────┐
                        │   result_submitted        │
                        └──────────┬───────────────┘
                                   │ start-review
                        ┌──────────▼───────────────┐
                        │       reviewing           │
                        └──┬───────┬───────┬───────┘
                           │       │       │
                  approve  │  reject│  request-changes
                           │       │       │
                    ┌──────▼──┐ ┌──▼───┐ ┌─▼──────────────┐
                    │ approved│ │reject│ │changes_requested│
                    └────┬────┘ └──┬───┘ └────────┬───────┘
                         │        │               │
                         │        │        (返回 dispatched)
                    ┌────▼────┐   │
                    │archived │   │
                    └─────────┘   │
                          ┌──────▼──────┐
                          │   archived  │
                          └─────────────┘
```

### 14.3 状态跃迁白名单（代码级校验）

```python
ALLOWED_TRANSITIONS = {
    "draft":               ["ticket_ready"],
    "ticket_ready":        ["dispatched"],
    "dispatched":          ["result_submitted"],
    "result_submitted":    ["reviewing"],
    "reviewing":           ["approved", "rejected", "changes_requested"],
    "changes_requested":   ["dispatched"],   # 返工重新分派
    "approved":            ["archived"],
    "rejected":            ["archived"],
    "archived":            [],               # 终态，不可再变更
}
```

非法跃迁返回 `409 Conflict` + 错误消息。

---

## 15. Git / PR / CI / 部署集成规划

### 15.1 设计原则

- MVP 阶段**全部 Stub**，有接口定义和路由，但返回固定消息
- 每个集成点对应一个 `services/stub` 模块，后续替换为真实实现不影响业务层
- Project 表已预留所有字段

### 15.2 Git 集成规划

| 能力 | MVP | 后续 |
|------|-----|------|
| 记录仓库地址 | ✅ Project.repo_url | — |
| 记录当前分支 | ✅ Project.current_branch | 真实 git status |
| 生成 PR 标题+描述 | ✅ 在任务单中包含 | 自动创建 PR |
| 创建 PR | ❌ Stub | POST /api/tasks/{id}/create-pr |
| 获取分支列表 | ❌ Stub | 调用 GitHub API |

### 15.3 CI 集成规划

| 能力 | MVP | 后续 |
|------|-----|------|
| 记录 CI 类型 | ✅ Project.ci_provider | — |
| 记录 CI 地址 | ✅ Project.ci_url | — |
| 触发 CI | ❌ Stub | POST /api/tasks/{id}/trigger-ci |
| 轮询状态 | ❌ Stub | Task.ci_url 链接跳转 |
| 展示结果 | ⬜ ReviewRecord.ci_passed 字段 | 自动回写 |

### 15.4 部署集成规划

| 能力 | MVP | 后续 |
|------|-----|------|
| 记录部署方式 | ✅ Project.deploy_provider | — |
| 记录部署地址 | ✅ Project.deploy_url | — |
| 触发部署 | ❌ Stub | POST /api/tasks/{id}/trigger-deploy |

### 15.5 API Stub 设计

所有 Stub 端点的返回格式：

```json
{
  "success": false,
  "data": null,
  "message": "[集成名称] not implemented in MVP. See Project.deploy_provider / .ci_provider for planned provider."
}
```

---

## 16. 安全策略

### 16.1 敏感信息

| 规则 | 说明 |
|------|------|
| 不存明文 token | 数据库任何表都不设 `api_key` / `token` / `secret` 字段 |
| Secret 只读环境变量 | 平台需要的外部服务 token 通过后端环境变量读取，不落盘、不展示 |
| 不日志敏感串 | TaskEvent 的 `payload_json` 在写入前做敏感字段脱敏（预留） |

### 16.2 操作安全

| 规则 | 说明 |
|------|------|
| 禁止自动 merge main | 不留任何自动合并的代码路径 |
| 禁止无确认部署 | Stub 本身不执行部署；后续真实实现必须有人工确认步骤 |
| 禁止删除项目目录 | 平台不执行任何文件系统写操作 |
| 禁止危险命令 | 即使后续扩展命令执行能力，`rm -rf` / `git reset --hard` / `git checkout main` / `drop` / `truncate` 必须硬编码拦截 + 人工确认 |
| 所有操作审计 | 每个状态变更、产物上传、Review 提交都写入 TaskEvent |

### 16.3 网络安全

| 规则 | 说明 |
|------|------|
| 本地监听 | `127.0.0.1` 不暴露到局域网 |
| CORS 严格白名单 | 仅允许前端 `127.0.0.1:9700` |
| 无外部回调接收 | MVP 不开放 Webhook 接收端口 |

### 16.4 内容安全

| 规则 | 说明 |
|------|------|
| 产物纯文本 | Diff / Log 只做文本展示，不渲染 HTML |
| Markdown 消毒 | 任务单和描述的 Markdown 在前端渲染前剥离 script 标签 |
| 禁止文件上传 | MVP 不接受文件上传，仅文本粘贴 |

---

## 17. 开发里程碑

### M1 — 项目骨架 + 数据层（Week 1）

| Step | 内容 | 验证标准 |
|------|------|----------|
| 1.1 | 目录结构搭建 + requirements.txt + package.json | `uvicorn app.main:app` 启动，`/api/health` 返回 200 |
| 1.2 | `config.py` + `database.py`（SQLite async + WAL mode） | 启动自动建 5 张表 |
| 1.3 | ORM 模型：Project / Task / TaskArtifact / TaskEvent / ReviewRecord | 表结构符合数据模型设计 |
| 1.4 | 枚举 + 状态机白名单 | 非法状态跃迁返回 409 |

### M2 — 核心 API（Week 1–2）

| Step | 内容 | 验证标准 |
|------|------|----------|
| 2.1 | Projects CRUD | curl 创建 / 查询 / 更新 / 删除 |
| 2.2 | Tasks CRUD + 关联 Project | 创建时必须指定 project_id |
| 2.3 | 完整状态流转 9 个端点 | 走通 draft → ticket_ready → dispatched → result_submitted → reviewing → approved |
| 2.4 | Artifacts 上传 / 列表 | 上传一段 diff 文本并回读 |
| 2.5 | TaskEvent 自动写入 | 每个操作在 `/events` 中查到对应记录 |
| 2.6 | Reviews 提交 + 查询 | 提交审查结论 + 问题列表 |

### M3 — 任务单引擎（Week 2）

| Step | 内容 | 验证标准 |
|------|------|----------|
| 3.1 | ticket_renderer 生成 Markdown 任务单 | 输出包含：项目信息 / 任务描述 / 执行步骤 / 分支建议 / 角色分配 |
| 3.2 | POST generate-ticket | 调用后 task.ticket_content 有内容，状态变为 ticket_ready |

### M4 — 前端（Week 2–3）

| Step | 内容 | 验证标准 |
|------|------|----------|
| 4.1 | Router + Pinia store + Axios API 封装 | 接口层覆盖所有后端端点 |
| 4.2 | DashboardPage + ProjectListPage + ProjectConfigPage | 项目 CRUD 在前端跑通 |
| 4.3 | TaskListPage + TaskCreatePage | 创建任务 → 列表展示 → 状态过滤 |
| 4.4 | TaskDetailPage 完整面板 | 全流程操作按钮按状态显示 / 隐藏 |
| 4.5 | EventTimeline + ReviewPanel + ArtifactTab | 组件可视化 |

### M5 — 端到端验收（Week 3–4）

| Step | 内容 | 验证标准 |
|------|------|----------|
| 5.1 | 创建项目 → 创建任务 → 生成任务单 → 分派 → 粘贴结果 → Review → Approve | 全链路跑通 |
| 5.2 | Stub 端点可用但不报错 | 点击 PR/CI/部署按钮返回友好提示 |
| 5.3 | 非法操作被拒绝 | 从 approved 点 dispatch 返回 409 |
| 5.4 | Dockerfile + docker-compose.yml | docker-compose up 一键启动 |

---

## 18. 验收标准

平台达到以下条件视为 MVP 验收通过：

| # | 验收项 | 验证方式 |
|---|--------|----------|
| 1 | **能创建项目** | 通过 API 或前端填写项目名、路径、Git 地址、命令配置，返回成功 |
| 2 | **能创建任务** | 指定项目，填写标题+描述，创建成功 |
| 3 | **能生成执行任务单** | 调用 generate-ticket，返回 Markdown 文档 |
| 4 | **能粘贴执行结果** | 上传一份 Diff 和一份 Log，在 Artifact 列表可查看 |
| 5 | **能记录 Review** | 提交审查结论（通过/拒绝/返工），Review 列表可查 |
| 6 | **状态流转完整** | 从 draft 到 approved 经历全部合法状态，每个变迁有 Event 记录 |
| 7 | **审计日志完备** | 关键操作在 Event 时间线中可追溯 |
| 8 | **非法操作被拒绝** | 尝试非法状态跃迁返回 409 |
| 9 | **多项目隔离** | 项目 A 的任务不会出现在项目 B 的列表中 |
| 10 | **角色字段有效** | 任务详情展示 Planner / Executor / Reviewer / Human Approver |
| 11 | **Stub 友好降级** | 点击 PR / CI / 部署按钮展示"未实现"但不崩溃 |

---

## 19. 风险点

| 风险 | 级别 | 说明 | 缓解措施 |
|------|------|------|----------|
| **范围膨胀 → 想加 executor** | 🔴 | 用户或团队会想"既然有平台了，为什么不让它直接跑代码？" | README + 文档写死「永不 executor」；PR Review 时守住边界 |
| **SQLite 并发写入** | 🟡 | FastAPI 多 worker 写 SQLite 可能锁库 | 单 worker + WAL mode；如果瓶颈到，换 PostgreSQL 只需改 database.py |
| **Diff 内容过大** | 🟡 | 单次任务可能产生数万行 diff | TaskArtifact.content 用 TEXT；前端默认折叠 + 按需展开 |
| **状态机逻辑遗漏** | 🟡 | 新增需求导致状态跃迁复杂化 | 所有跃迁走 `ALLOWED_TRANSITIONS` 字典，加单元测试 |
| **前端无实时更新** | 🟢 | 用户不习惯手动刷新 | MVP 接受；后续加 WebSocket |
| **路径中文编码** | 🟢 | 项目路径含中文可能导致跨平台问题 | `config.py` 用 `pathlib` + `os.getenv`；README 提示 |
| **无用户认证** | 🟡 | actor 字段靠自觉填写 | MVP 声明不做；后续加 JWT 中间件 + 从 token 自动提取 actor |

---

## 20. 下一步任务拆解

验收后，以下任务是后续阶段的候选方向：

| 优先级 | 任务 | 前置条件 | 预估工期 |
|--------|------|----------|----------|
| P0 | **接入 SQLite → PostgreSQL 迁移** | MVP 数据量增长到瓶颈 | 1d |
| P0 | **接入用户认证（JWT）** | 多用户协作需求 | 2d |
| P1 | **GitHub PR 自动创建** | 完成 PRBuilder 真实实现 + token 环境变量 | 2d |
| P1 | **CI 状态轮询与展示** | CIClient 实现 + Webhook 接收端点 | 3d |
| P2 | **SonarQube 结果集成** | ReviewRecord.sonar_passed 字段已预留 | 2d |
| P2 | **WebSocket 实时推送** | 前端手动刷新体验瓶颈 | 2d |
| P2 | **多轮返工工作流** | 状态机已预留 changes_requested | 1d |
| P3 | **Docker 部署触发** | DeployHook 实现 | 2d |
| P3 | **Webhook 接收（GitHub Push / PR event）** | 外部事件驱动的自动创建任务 | 3d |

---

## 修改记录

| 版本 | 日期 | 主要修正 |
|------|------|----------|
| v0.1 | 2025-07-16 | 初版 — 单项目、窄边界、缺少模型 |
| **v0.2** | **2025-07-16** | **返工版 — 完整 20 章、多项目模型、5 张表、8 态状态机、审计日志、产物独立、角色模型、Stub 集成规划** |
| **v0.3** | **2025-07-16** | **用户确认修订 — 8→9 态 + archived 终态规则 + Artifact 扩展字段(storage_type/file_path/size_bytes/sha256/is_truncated) + 移除 Agent 图例 + root_path 安全规则 + 删除确认问题章节** |

（本文档 4 项确认问题已于 2025-07-16 由用户确认，见 v0.3 修改记录）
