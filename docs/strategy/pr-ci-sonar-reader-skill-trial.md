# S21 PR / CI / Sonar Reader Skill Trial

## 1. 目标

S21 先验证 Codex / OMX skill 是否能承担 PR / CI / Sonar Reader 和主脑复审 SOP，而不是先在平台里新增完整 reader API。

本阶段只做文档和真实试跑记录：

- 不新增后端 API
- 不新增前端页面
- 不新增数据库
- 不实现平台 PR / CI / Sonar Reader
- 不新增 execute
- 不自动 approve / merge

## 2. 为什么先做 skill 试跑

PR / CI / Sonar 复审的核心工作是一次性读取外部状态、对照 PR body、判断是否可以合入。它更像 Codex / OMX 的 SOP，而不是平台长期运行时能力。

先做 skill 试跑有三个原因：

1. 读取 GitHub PR metadata、changed files、checks 和 SonarCloud comment 已经可以用 `gh` 和 SonarCloud API 完成。
2. 复审判断依赖当前 PR 的真实状态，Codex / OMX 更适合做即时检查、风险识别和固定格式报告。
3. 平台当前更应该沉淀证据、记忆、审计、handoff 和 synthesis，不应该急着变成弱版 PR/CI/Sonar 平台。

因此 S21 的判断标准是：如果 skill 能稳定覆盖 80% 高频复审需求，平台 reader 暂缓；平台只在后续 Evidence Board / Timeline 需要长期保存时接收 skill 输出结果。

## 3. Codex / OMX Skill 适合承担什么

skill 适合承担：

- 读取 PR metadata：state、mergeable、head、base、changed files
- 展开 changed files 列表并检查范围
- 读取 PR body 并对照实际 GitHub 状态
- 读取 GitHub checks / check-runs
- 读取 SonarCloud bot comment 或 SonarCloud API
- 检查验证结果声明是否可信
- 检查安全边界声明是否完整
- 输出固定格式主脑复审报告

skill 不负责：

- 不改代码
- 不写平台数据库
- 不创建平台 reader API
- 不创建 PR / CI / Sonar / Deploy 能力
- 不自动 approve / merge / deploy
- 不读取 `.env` / `secret_ref`
- 不访问 `Project.root_path` 做真实修改

## 4. 平台后续应该沉淀什么

平台不需要复制一套完整 PR reader，除非出现长期证据需求。后续平台更适合沉淀：

- skill 输出的复审报告
- PR number、head、base、changed files 摘要
- SonarCloud summary
- check-run summary
- blocker / approved / needs_update verdict
- 与 Task / Repair Attempt / Evidence Board 的关联

这些内容可以作为 TaskArtifact 或 TaskEvent 进入 Evidence Board，而不是变成平台主动查询和判定所有外部系统的执行器。

## 5. 真实 PR 复审试跑记录

本次试跑对象：PR #51，S20.4 Repair Attempt Timeline。

### 5.1 输入

```text
repo: 2449673842/codex-auto-delivery-platform
pr_number: 51
expected_head: 2043644e111c1407f36580759df42791060f2dd5
expected_base: 94732ddcc225c333b8074b03d1edc44a0645aefc
```

### 5.2 读取 PR metadata

命令：

```bash
gh pr view 51 --repo 2449673842/codex-auto-delivery-platform \
  --json number,state,mergeCommit,headRefOid,baseRefOid,changedFiles,files,body,title,url
```

结果：

- PR URL: `https://github.com/2449673842/codex-auto-delivery-platform/pull/51`
- PR number: `#51`
- title: `S20.4 Repair Attempt Timeline`
- state: `MERGED`
- head: `2043644e111c1407f36580759df42791060f2dd5`
- base: `94732ddcc225c333b8074b03d1edc44a0645aefc`
- merge commit: `f5dbb60058c2dce610093d82ac5cf6e7404cfd8f`
- changed files: `8`

### 5.3 Changed files

命令：

```bash
gh pr diff 51 --repo 2449673842/codex-auto-delivery-platform --name-only
```

结果：

- `backend/app/routers/repair_loop.py`
- `backend/app/schemas/repair_loop.py`
- `backend/app/services/repair_loop_service.py`
- `backend/tests/test_repair_loop_attempts.py`
- `frontend/src/pages/TaskDetailPage.vue`
- `frontend/src/services/agentService.ts`
- `frontend/src/types/agent.ts`
- `frontend/tests/s4-display.cjs`

范围判断：这些文件符合 S20.4 Repair Attempt Timeline 的后端、前端和测试范围。

### 5.4 PR body claims

PR body 声明：

- targeted backend pytest: `8 passed`
- S20.4 + related backend pytest: `35 passed`
- full backend pytest: `524 passed`
- compileall: passed
- extra import check: `hasattr(repair_loop_service, 'create_repair_attempt')` returned `True`
- npm build: passed
- frontend display smoke: `356 passed, 0 failed`
- SonarCloud Quality Gate: Passed
- Security Hotspots: `0`
- Duplication on New Code: `1.8%`
- New Issues: `0`

PR body 同时声明：

- 不执行 repair
- 不自动改代码
- 不写真实仓库
- 不调用 provider
- 不打开 Browser AI
- 不执行 shell / subprocess 作为平台业务能力
- 不执行 verification command，只导入结果
- 不创建 GitHub PR / CI / Sonar / Deploy 平台能力
- 不自动 approve / merge / deploy
- 不自动创建下一轮 attempt
- 不实现自动 repair loop
- 不读取 `.env` / `secret_ref`
- 不访问 `Project.root_path`

### 5.5 Checks / SonarCloud

命令：

```bash
gh pr checks 51 --repo 2449673842/codex-auto-delivery-platform
```

结果：

- SonarCloud Code Analysis: `pass`

SonarCloud bot comment 记录：

- Quality Gate: passed
- New issues: `0`
- Accepted issues: `0`
- Security Hotspots: `0`
- Coverage on New Code: `0.0%`
- Duplication on New Code: `1.8%`

SonarCloud API 记录：

```text
projectStatus.status: OK
new_violations: 0
security_hotspots: 0
new_duplicated_lines_density: 1.8281535648994516
issues.total: 0
```

### 5.6 复审发现

发现 1：PR #51 曾经在旧 head `73d134e0d3824d5db3de7f768fd151da6c519856` 出现过严重不一致，`backend/app/services/repair_loop_service.py` 和 `frontend/src/types/agent.ts` 被错误写成单行 placeholder。该问题在最终 head `2043644e111c1407f36580759df42791060f2dd5` 前已修复。

发现 2：最终 head 的 changed files 数量和 PR body 一致，均为 `8`。

发现 3：最终 SonarCloud 数据与 PR body 一致：

- Quality Gate Passed
- Security Hotspots 0
- Duplication on New Code 1.8%
- New Issues 0

发现 4：本次复审中，最有价值的检查不是单纯读取 Sonar，而是对照 PR body 与 GitHub 真实 diff。旧 head 的 placeholder 问题说明 skill 必须读取实际 changed files 和关键风险文件，而不能只信 PR body。

### 5.7 试跑复审报告

```text
复审结论：approved

PR:
- URL: https://github.com/2449673842/codex-auto-delivery-platform/pull/51
- 编号: #51
- state: MERGED
- head: 2043644e111c1407f36580759df42791060f2dd5
- base: 94732ddcc225c333b8074b03d1edc44a0645aefc
- merge commit: f5dbb60058c2dce610093d82ac5cf6e7404cfd8f
- changed files: 8

changed files:
- backend/app/routers/repair_loop.py
- backend/app/schemas/repair_loop.py
- backend/app/services/repair_loop_service.py
- backend/tests/test_repair_loop_attempts.py
- frontend/src/pages/TaskDetailPage.vue
- frontend/src/services/agentService.ts
- frontend/src/types/agent.ts
- frontend/tests/s4-display.cjs

验证结果：
- targeted backend pytest: 8 passed
- S20.4 + related backend pytest: 35 passed
- full backend pytest: 524 passed
- compileall: passed
- import check: create_repair_attempt exists
- npm build: passed
- frontend display smoke: 356 passed, 0 failed

SonarCloud:
- Quality Gate: Passed
- Security Hotspots: 0
- Duplication on New Code: 1.8%
- New Issues: 0

范围检查：
- changed files 与 PR body 一致
- 修改范围符合 S20.4
- 未发现 out-of-scope 平台 PR/CI/Sonar/Deploy 能力

安全边界：
- 未执行 repair
- 未自动改代码
- 未写真实仓库
- 未调用 provider
- 未打开 Browser AI
- 未创建平台 PR / CI / Sonar / Deploy 能力
- 未自动 approve / merge / deploy

主脑建议：
- 可以合入 master
```

## 6. Skill 输出格式

S21 建议固定输出以下结构：

```text
复审结论：approved / needs_update / blocked

PR:
- URL:
- 编号:
- state:
- mergeable:
- head:
- base:
- merge commit:
- changed files:

changed files:
- <path>

PR body claims:
- targeted backend pytest:
- related backend pytest:
- full backend pytest:
- compileall:
- npm build:
- frontend tests / smoke:
- SonarCloud:

Observed verification:
- GitHub checks:
- SonarCloud bot comment:
- SonarCloud API:

Risk review:
- risk files inspected:
- body vs diff consistency:
- validation claim consistency:
- safety boundary consistency:

Blockers:
- <none or list>

Safety boundary:
- no execute:
- no provider call:
- no Browser AI open:
- no repository writes:
- no PR / CI / Sonar / Deploy platform capability:
- no auto approve / merge:

Recommendation:
- approve / request changes / wait
```

## 7. 平台化判断标准

继续 skill 化，如果：

- 复审只需要一次性读取当前 PR
- 输出只给主脑当下决策
- 不需要长期保存
- 不需要跨 Task / Project 检索
- 不需要 UI 展示历史趋势

考虑平台化，如果：

- 每次复审报告都需要进入 Task Timeline
- PR / CI / Sonar evidence 需要长期保存为 TaskArtifact
- 需要跨多个 PR 比较 Sonar / CI 趋势
- 需要 Evidence Board 展示 PR 证据链
- 外部 AI 需要通过 MCP 读取历史复审记录

混合方案：

```text
Codex / OMX skill 负责读取和判断
平台只保存 skill 输出结果、关键 metadata 和证据摘要
Evidence Board / Timeline 负责长期展示
```

## 8. 结论

S21 试跑结论：继续 skill 化，平台 reader 暂缓。

理由：

- PR #51 的 metadata、changed files、checks、SonarCloud comment、SonarCloud API、PR body claim 都可以通过 skill SOP 读取和交叉验证。
- 旧 head placeholder 问题证明，skill 必须检查真实 diff 和风险文件，而不是只读 PR body。
- 当前高频需求是“主脑复审前快速确认 PR 是否可合入”，Codex / OMX skill 足够承担。
- 平台后续只需要在 S22 Evidence Board / Run Timeline 中保存 skill 输出结果，不需要立即实现完整 PR / CI / Sonar Reader API。
