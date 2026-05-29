# S18 之后路线

## 1. 当前定位

S18 完成后，平台已经从“代码交付平台”转为个人多 AI 编码工作台。

长期分工固定为：

```text
Codex 负责执行
Codex skill 固化执行流程和 SOP
Browser AI 采集网页 AI 证据
平台负责记忆、证据、审计、handoff、synthesis
```

后续路线不再优先建设弱版 Codex 执行器，而是围绕多 AI 证据、长期记忆和交接能力推进。

## 2. 阶段路线

### S18.0.3 — Multi-AI Evidence Run 设计

目标：把 S19 从“多 AI 执行器”定义为“多 AI 证据运行”。

产物：

- `docs/design/multi-ai-evidence-run.md`
- `docs/strategy/browser-ai-vs-codex.md`
- `docs/roadmap/next-after-s18.md`

范围：

- 只做文档
- 不写后端
- 不写前端
- 不新增 API
- 不新增 execute
- 不进入 S19 代码实现

### S19 — Multi-AI Evidence Run MVP

目标：实现第一个多 AI 证据收集闭环。

S19 MVP 做：

- 支持 broadcast
- 支持 routed
- 复用 Browser AI provider profiles
- 复用 AgentRun / TaskArtifact / Answer Synthesis
- 优先复用 DispatchBatch / DispatchJob 作为 EvidenceRun / EvidenceJob
- 支持 bounded concurrency
- 一个 job 失败不影响其他 job
- 成功后自动刷新 Answer Synthesis
- 页面显示每个 job 的 status / error / artifact_id / answer preview

S19 MVP 不做：

- 不自动改代码
- 不写真实仓库
- 不创建 PR
- 不调用 CI / Sonar / Deploy
- 不自动 approve / merge
- 不实现 pipeline 执行
- 不实现 repair loop 执行
- 不绕过 Browser AI 登录或验证码

### S20 — Controlled Repair Loop with Codex 设计

目标：设计受控失败返工，而不是平台无限自动修复。

流程：

```text
sandbox / verification / CI / Sonar / review failed
-> 平台收集失败证据
-> 多 AI evidence run 分析原因
-> 生成 repair packet
-> Codex 或用户执行修复
-> 平台记录 repair attempt 和验证结果
```

S20 先做设计，不直接实现自动修复。

必须明确：

- max_attempts 默认 1
- 用户可停止
- 平台不自动写真实仓库
- 平台不自动创建 PR
- 平台不自动 merge / deploy / approve

细化路线：

- S20：Controlled Repair Loop with Codex 设计
- S20.1：Failure Evidence Packet preview
- S20.2：Repair Packet generation using Multi-AI Evidence Run
- S20.3：Codex / OMX handoff for repair
- S20.4：Repair Attempt Timeline

设计文档：

- `docs/design/controlled-repair-loop-with-codex.md`
- `docs/roadmap/repair-loop-roadmap.md`

### S21 — PR / CI / Sonar Reader skill 真实试跑

目标：验证 PR / CI / Sonar Reader 是否适合继续留在 Codex / OMX skill，而不是先平台化为 reader API。

试跑内容：

- 真实 PR URL / PR number
- PR state
- head / base commit
- changed files
- GitHub checks / workflow runs
- SonarCloud Quality Gate
- Security Hotspots
- Duplication on New Code
- New Issues
- PR body 是否中文、是否包含验证结果
- 输出主脑复审报告

交付物：

- `docs/strategy/pr-ci-sonar-reader-skill-trial.md`
- `docs/skills/pr-ci-sonar-reader-skill.md`

判断：

```text
如果 skill 能覆盖 80% 高频复审需求，平台 PR Reader 暂缓。
如果需要长期记录、UI 展示、跨任务检索，则把证据归档能力放入 Evidence Board / Timeline。
```

S21 不做：

- 不新增后端 API
- 不新增前端页面
- 不新增数据库
- 不实现平台 PR / CI / Sonar Reader
- 不新增平台 PR / CI / Sonar / Deploy 能力

### S22 — Evidence Board / Run Timeline

目标：把任务证据变成长期可读的时间线和证据板。

拆分路线：

- S22.0：Evidence Board / Run Timeline 设计
- S22.1：Evidence Summary API
- S22.2：TaskDetail Timeline UI
- S22.3：Evidence Board filters / details
- S22.4：Skill Review Report artifact import，必要时再做

S22.0 只做设计文档，不新增 API、前端页面、数据库或业务代码。

S22.1 / S22.2 MVP 先做：

- 聚合已有 TaskEvent / AgentRun / TaskArtifact / DispatchBatch / DispatchJob
- 返回 timeline items
- 返回 evidence summaries
- TaskDetail 显示 timeline list
- TaskDetail 显示 evidence board list
- 不新增复杂数据库表
- 不执行外部命令
- 不调用 provider

Run Timeline 应展示：

- task_created
- ai_run_started / ai_run_finished / ai_run_failed
- artifact_created
- browser_ai_answer_saved
- multi_ai_evidence_started / multi_ai_evidence_finished
- synthesis_refreshed
- failure_evidence_previewed
- repair_packet_generated
- repair_handoff_previewed
- repair_attempt_created / repair_attempt_status_changed
- verification_result_imported
- skill_review_report_imported

Evidence Board 应覆盖：

- Task created / updated
- AgentRun
- TaskArtifact
- TaskEvent
- DispatchBatch / DispatchJob
- Browser AI answer artifact
- Multi-AI Evidence Run artifacts
- Answer Synthesis
- Failure Evidence Packet
- Repair Packet
- Codex / OMX Repair Handoff
- Repair Attempt Timeline
- Verification Result artifact
- PR / CI / Sonar Reader skill review report
- Sandbox / Gate artifact
- Patch artifact

价值：

```text
几个月后仍能知道：
当时为什么这样改？
哪个 AI 建议的？
哪些证据支持？
哪个测试失败？
最后为什么继续或停止？
```

S22 不做：

- 不自动执行代码
- 不写真实仓库
- 不读取 `.env` / secret_ref
- 不调用 provider
- 不打开 Browser AI
- 不主动查询 GitHub / Sonar API，S21 已决定 skill 化
- 不创建 GitHub PR / CI / Sonar / Deploy
- 不自动 approve / merge / deploy
- 不替代 Codex / OMX
- 不做无限 repair loop

### S23 — Project Memory

目标：沉淀项目级长期记忆。

内容包括：

- 启动方式
- 常见端口
- 常见失败原因
- 常用测试命令
- 不能乱改的文件
- PR 规范
- Sonar 常见问题
- 用户偏好
- 常用 AI provider
- 常用 routed job 模板

MCP Bridge、Codex skill、Browser AI prompt 都可以读取 Project Memory 的摘要，减少重复解释背景。

拆分路线：

- S23.0：Project Memory 设计文档
- S23.1：Project Memory read-only schema / API
- S23.2：TaskDetail / Project page Memory UI
- S23.3：Memory-backed handoff packet
- S23.4：Memory stale review / update flow design

S23.0 只做设计文档，不新增 API、前端页面、数据库或业务代码。

Project Memory 应覆盖：

- `project_profile`：项目名称、目标、技术栈、repo 信息、主要目录结构
- `runbook`：后端 / 前端启动方式、常用端口、环境变量名称要求、本地服务依赖
- `verification_policy`：targeted pytest、full pytest、compileall、npm build、frontend smoke、Browser AI mock smoke、SonarCloud gate
- `delivery_policy`：每阶段独立 PR、不直接 push master、中文 PR body、主脑复审后合入
- `safety_policy`：不读取 `.env` / `secret_ref`、不回显 secret、不写真实仓库、不自动 merge / deploy
- `known_failure`：Sonar secret false positive、placeholder 文件损坏、Browser AI selector failure、stable response timeout、GitHub TLS / proxy 失败
- `user_preference`：保守阶段推进、平台作为证据层 / 记忆层、不做弱版 Codex
- `handoff_template`：Codex / OMX / PR review / repair handoff / Browser AI provider run 模板

S23 第一版必须保守：

- 不自动扫描仓库生成 memory
- 不读取 `.env`
- 不保存 secret 值
- 不自动相信 AI 输出
- memory 写入需要用户确认或明确来源
- memory 需要 source references、updated_at、confidence、stale 标记

S23.4 继续保持设计优先：

- 只设计 candidate / active / stale / superseded / archived / rejected 生命周期
- 只设计 stale review、confirm、mark-stale、supersede、archive 流程
- 不实现 memory 写入 API
- 不实现 memory UI
- 不新增数据库
- 不自动从 PR body、AI 输出、Evidence Board 或 Timeline 写入 memory
- 不自动修改 `delivery_policy` / `safety_policy`
- 不读取 `.env` / `secret_ref`
- 不扫描 `Project.root_path`

### S24 — Browser AI Mastermind Review Trial / MCP Transport

目标：先验证 Browser AI 主脑复审闭环，再把平台已经沉淀的 memory、evidence、timeline、handoff packet 通过真正外部 AI 可接入的方式导出。

顺序调整原因：

```text
Browser AI Mastermind Review Trial 更贴近“自动审核闭环”：
平台生成 review packet
-> 浏览器 GPT 主脑复审
-> 读取主脑回复
-> 解析 verdict
-> 保存为 evidence
-> 人类决定是否合入

MCP 仍然保留，但它主要解决“外部 AI 读取上下文”，不是直接验证复审闭环。
```

拆分路线：

- S24.0：MCP Transport / Skill Adapter design
- S24.1.0：Browser AI Mastermind Review Trial Design
- S24.1.1：Mastermind Review Packet Preview API
- S24.1.2：Browser AI Mastermind Review Execute
- S24.1.3：TaskDetail Mastermind Review UI + Evidence Board integration
- S24.2：Read-only MCP resources/tools
- S24.3：Codex skill adapter docs/example
- S24.4：Claude Desktop / Cursor local integration example
- S24.5：Optional authenticated HTTP/SSE transport

候选形式：

- Browser AI GPT 主脑复审试跑
- stdio MCP server
- streamable HTTP / SSE MCP transport
- Codex skill adapter
- Claude Desktop / Cursor 接入示例

前提：

```text
S19 / S22 / S23 已证明平台有足够的 evidence 和 memory 价值。
```

不要在主脑复审闭环未验证前优先做复杂 transport。

S24.1.0 只做设计文档，不新增 Browser AI 主脑复审执行、review execute API、artifact 写入、UI、数据库或业务代码。

S24.1.0 Mastermind Review Packet 必须覆盖：

- PR URL
- PR number
- head commit
- base commit
- changed files
- PR body
- verification results
- SonarCloud summary
- security hotspots
- duplication on new code
- new issues
- safety boundary checklist
- relevant Task summary
- relevant Evidence Board summary
- relevant Run Timeline summary
- relevant Project Memory summary
- prior repair / handoff context if available

S24.1.0 verdict taxonomy：

- `approved`
- `request_changes`
- `needs_human`
- `invalid_review`

S24.1.0 明确不做：

- 不实现 Browser AI 主脑复审执行
- 不新增 review execute API
- 不新增 artifact 写入
- 不新增 UI
- 不自动 approve
- 不自动 merge
- 不自动 deploy
- 不自动返工
- 不创建 PR
- 不运行 CI / Sonar
- 不调用 provider
- 不执行 shell / subprocess
- 不写真实仓库
- 不读取 `.env`
- 不读取 `secret_ref`
- 不保存账号 / 密码 / cookie / session
- 不绕过登录 / 验证码
- 不把网页 AI 回复当作不可质疑事实

S24.0 只做设计文档，不新增 MCP server、stdio transport、HTTP / SSE transport、Codex skill adapter、后端 API、前端 UI、数据库或业务代码。

S24 第一版只读：

- 只读 Project Memory
- 只读 Project Memory summary
- 只读 Evidence Board
- 只读 Run Timeline
- 只读 AI Handoff preview
- 只读 Repair Handoff preview
- 只读 TaskArtifact summary
- 只读 recent Repair Attempts

S24 MVP read-only tools 草案：

- `get_project_memory`
- `get_project_memory_summary`
- `get_task_timeline`
- `get_task_evidence_board`
- `preview_ai_handoff`
- `preview_repair_handoff`
- `get_task_artifacts_summary`
- `get_recent_repair_attempts`

S24 MVP 明确不包含：

- `execute_code`
- `write_repository`
- `create_pr`
- `merge_pr`
- `approve_pr`
- `deploy`
- `run_shell`
- `read_env`
- `read_secret_ref`
- `browser_ai_execute`

## 3. 四种多 AI 工作形态

后续所有多 AI 设计固定为四类：

1. Broadcast / 同题多答
   - 多个 AI 回答同一个问题
   - 用于独立判断、共识和分歧比较

2. Routed / 分工协作
   - 多个 AI 按 role 处理不同子任务
   - 例如 backend、frontend、config、test、risk、summary

3. Pipeline / 流水线接力
   - 一个 AI 输出作为下一个 AI 输入
   - 例如 planner -> reviewer -> risk_checker -> final_synthesizer
   - 先设计，不急着实现

4. Repair Loop / 受控失败返工
   - 失败后收集证据、生成 repair packet
   - Codex 或用户执行修复
   - 平台记录 attempt 和验证结果
   - 不无限自动修复

## 4. 暂缓内容

暂缓：

- Multi-AI 复杂 pipeline 执行
- Repair Loop 自动实现
- PR Creation Adapter
- Verification Runner 平台版
- 真实 MCP execute
- general agent runtime
- 复杂自动执行器

不做：

- 自动 merge
- 自动 deploy
- 自动 approve
- 平台无限自动改代码
- 平台绕过登录 / 验证码
- 平台保存账号 / 密码 / cookie / session
- 任意 shell 执行器
- 通用 Agent Runtime

## 5. 下一步交付规则

每个后续 PR 都必须说明：

- 用户入口是什么
- 用户点击什么
- 后端真实执行什么
- 数据保存在哪里
- 页面显示什么
- 失败时用户能否看懂
- 是否扩大安全边界

S18.0.3 是文档 PR，因此验证方式是：

- changed files 只包含 docs
- 不需要 backend pytest
- 不需要 compileall
- 不需要 npm build
- 不需要 frontend tests
- PR body 必须说明未改代码和未扩大安全边界
