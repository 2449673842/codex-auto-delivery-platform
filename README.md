# Codex 自动化代码交付平台

> 多项目自动化代码交付平台 MVP — AI 任务拆解、代码执行结果管理、Review、CI/部署集成预留

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
│   │   ├── enums.py              # 9 态状态机 + 跃迁白名单
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
│   │   ├── pages/                # 6 个页面
│   │   ├── components/           # 6 个组件
│   │   ├── router/               # Vue Router
│   │   ├── stores/               # Pinia 状态管理
│   │   └── services/             # Axios API 封装
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
├── docs/
│   ├── MVP设计方案.md
│   └── releases/
│       └── v0.1.0.md
├── docker-compose.yml
└── README.md
```

---

## 核心功能

| 模块 | 说明 |
|------|------|
| **项目管理** | 注册多项目，配置 Git/CI/部署元信息 |
| **任务管理** | 创建/查看/流转/删除任务 |
| **9 态状态机** | draft → ticket_ready → dispatched → result_submitted → reviewing → changes_requested/approved/rejected → archived |
| **审计日志** | TaskEvent 自动记录所有关键操作 |
| **产物管理** | 上传/查看 Diff、日志等执行产物 |
| **审查记录** | ReviewRecord 记录审查结论 |
| **外部集成 Stub** | PR / CI / 部署接口预留，返回友好提示 |

---

## API 概览

所有接口前缀 `/api`，统一返回 `ApiEnvelope` 格式。

| 端点 | 说明 |
|------|------|
| `GET /api/health` | 服务健康检查 |
| `GET/POST /api/projects` | 项目列表/创建 |
| `GET/PATCH/DELETE /api/projects/{id}` | 项目详情/更新/删除 |
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

完整 API 文档通过 `GET /docs`（Swagger UI）或 `GET /redoc`（ReDoc）查看。

---

## 运行测试

```bash
# 全部 28 项测试
python -m pytest backend/tests/ -v --rootdir backend

# 单文件
python -m pytest backend/tests/test_mvp_full.py -v --rootdir backend
```

---

## 安全边界

- 不读写 Project.root_path
- 不执行 shell / subprocess / os.system
- 不做真实 Git / PR / CI / 部署（所有外部集成点为 Stub）
- 不存 token / secret / API key
- 后端仅监听 127.0.0.1

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

- **v0.1.0** (2025-07-16) — MVP 候选基线
