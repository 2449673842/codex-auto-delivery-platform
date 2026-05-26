# PR / CI / Sonar Reader Skill SOP

## 1. 目标

这是 S21 的 Codex / OMX skill 草案。它不是平台 API，也不是自动合入器。它的目标是只读读取 GitHub PR、CI checks、SonarCloud summary，并输出固定格式主脑复审报告。

本 SOP 用于验证 PR / CI / Sonar Reader 是否应继续 skill 化，而不是平台化为后端 reader。

## 2. 范围

本 skill 只负责读取和整理，不负责执行合并或部署。

允许：

- 读取 PR metadata
- 读取 PR changed files
- 读取 GitHub checks / workflow runs
- 读取 SonarCloud bot comment / SonarCloud API summary
- 检查 PR body 是否包含必要验收字段
- 比较 claimed verification 与 observed verification
- 检查风险文件
- 输出主脑复审报告

禁止：

- 不创建 PR
- 不 merge
- 不 deploy
- 不 auto approve
- 不改代码
- 不写平台数据库
- 不调用平台 execute
- 不读取 `.env`
- 不读取 `secret_ref`
- 不访问 `Project.root_path` 做真实修改

## 3. 输入

skill 应支持以下输入形式：

```text
PR URL: https://github.com/<owner>/<repo>/pull/<number>
```

或：

```text
repo: <owner>/<repo>
pr_number: <number>
expected_head: <full sha>
expected_base: <full sha>
```

可选输入：

```text
expected_head: <full sha>
expected_base: <full sha>
expected_changed_files: <number>
expected_targeted_pytest: <text>
expected_full_pytest: <text>
expected_frontend_tests: <text>
expected_sonar_quality_gate: Passed
```

## 4. 执行步骤

### 1. 读取 PR 基本信息

推荐：

```bash
gh pr view <number> --repo <owner>/<repo> \
  --json number,url,state,mergeable,mergeCommit,headRefOid,baseRefOid,changedFiles,title,body
```

必须记录：

- PR URL
- PR number
- state
- mergeable
- head commit full SHA
- base commit full SHA
- merge commit，如果 PR 已合入
- changed files count
- title
- body

如果用户提供 `expected_head` / `expected_base`，必须逐字比较 full SHA。短 SHA 不足以验收。

### 2. 读取 changed files

推荐：

```bash
gh pr diff <number> --repo <owner>/<repo> --name-only
```

或：

```bash
gh api repos/<owner>/<repo>/pulls/<number>/files --paginate
```

必须检查：

- changed files 数量是否等于 GitHub 实际值
- 是否出现 out-of-scope 文件
- 是否只有文档 / 前端 / 后端等声明范围内文件
- 风险文件是否需要重点抽查，例如 service、schema、router、migration、workflow、security、auth、CI、deploy 配置

### 3. 读取 GitHub checks

推荐：

```bash
gh pr checks <number> --repo <owner>/<repo>
```

或：

```bash
gh api repos/<owner>/<repo>/commits/<head_sha>/check-runs
```

必须检查：

- checks 是否完成
- 是否有 failure / cancelled / timed_out
- 是否缺少必需检查
- SonarCloud Code Analysis 是否成功

### 4. 读取 SonarCloud bot comment

推荐：

```bash
gh api repos/<owner>/<repo>/issues/<pr_number>/comments \
  --jq '.[] | select(.user.login=="sonarqubecloud[bot]") | {created_at,body}'
```

必须记录：

- Quality Gate
- Security Hotspots
- Duplication on New Code
- New Issues

### 5. 读取 SonarCloud API

如果可访问，读取：

```text
https://sonarcloud.io/api/measures/component?component=<project_key>&pullRequest=<pr_number>&metricKeys=new_duplicated_lines_density,new_violations,security_hotspots
```

以及：

```text
https://sonarcloud.io/api/qualitygates/project_status?projectKey=<project_key>&pullRequest=<pr_number>
https://sonarcloud.io/api/issues/search?componentKeys=<project_key>&pullRequest=<pr_number>&resolved=false&ps=1
```

必须记录：

- SonarCloud Quality Gate
- Security Hotspots
- Duplication on New Code
- New Issues

如果 Sonar 数据暂不可用，报告必须写：

```text
SonarCloud: pending / unavailable
blocked reason: <具体原因>
```

不能猜测为 Passed。

### 6. 检查 PR body

必须检查 PR body 是否包含：

- PR URL
- PR 编号
- head commit
- base commit
- changed files
- targeted backend pytest
- full backend pytest
- compileall
- npm build
- frontend tests
- smoke test
- SonarCloud Quality Gate
- Security Hotspots
- Duplication on New Code
- New Issues
- 安全边界自查

如果是文档 PR，可以接受：

- backend pytest 未运行，只改文档
- npm build 未运行，未改前端
- frontend tests 未运行，未改前端

但必须明确说明原因。

### 7. 比较 claimed verification 与 observed verification

必须交叉检查：

- PR body 的 head 是否等于 GitHub head
- PR body 的 base 是否等于 GitHub base
- PR body 的 changed files 数量和列表是否等于 GitHub 实际值
- PR body 的 SonarCloud 结果是否等于 SonarCloud bot comment / API
- PR body 声称的测试结果是否与用户或 CI 提供的真实输出一致
- 如果无法观察某项验证，报告必须写 `unverified`，不能替用户确认

### 8. 检查风险文件

对风险文件做最小必要抽查：

- service / router / schema 是否仍是可执行代码，不是 placeholder / symlink 文本 / worktree pointer
- 测试文件是否有空测试、`assert True`、过度宽松断言
- 文档 PR 是否真的只改 docs
- 是否新增平台 PR / CI / Sonar / Deploy 能力
- 是否新增自动 approve / merge / deploy 入口
- 是否出现 secret-like fixture

## 5. 输出格式

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
- frontend tests:
- smoke test:

Observed verification:
- GitHub checks:
- SonarCloud bot comment:
- SonarCloud API:

SonarCloud:
- Quality Gate:
- Security Hotspots:
- Duplication on New Code:
- New Issues:

范围检查：
- changed files 是否匹配 PR body:
- 是否存在 out-of-scope 修改:
- 是否只改文档 / 前端 / 后端:

风险文件检查：
- inspected files:
- findings:

安全边界：
- 是否创建 PR:
- 是否 merge:
- 是否 deploy:
- 是否 auto approve:
- 是否读取 .env / secret_ref:
- 是否访问 Project.root_path:
- 是否写真实仓库:

问题：
- <按严重程度列出>

主脑建议：
- 可以合入 / 需要返工 / 暂不批准
```

## 6. Verdict 规则

必须 blocked：

- SonarCloud Quality Gate failed
- Security Hotspots > 0
- New Issues > 0，除非主脑明确接受
- PR body 与 GitHub 实际 changed files / head / test count 不一致
- 出现 out-of-scope 修改
- 关键风险文件被替换成 placeholder / pointer / 非代码内容
- 出现 secret 泄露
- 自动 merge / deploy / approve
- 直接 push master

必须 needs_update：

- Sonar pending，无法判断
- PR body 缺字段
- changed files 列表未展开
- 测试结果写了但没有真实来源
- 文档 PR 未说明为什么不跑测试
- SonarCloud bot comment 与 API 暂时不一致，需要等待刷新

可以 approved：

- GitHub 实际状态与 PR body 一致
- SonarCloud passed
- changed files 符合范围
- 验证结果完整或跳过理由合理
- 安全边界清楚

## 7. Skill 与平台边界

skill 适合完成本流程，因为它是一次性读取和报告生成。

平台暂不需要实现 PR / CI / Sonar Reader，除非出现以下需求：

- 需要长期保存每次 PR 复审结果
- 需要跨 task / project 检索历史 PR 证据
- 需要把 PR / CI / Sonar 状态放入 Task Timeline
- 需要 Evidence Board 展示多次复审差异
- 需要把 review packet 作为 TaskArtifact 保存

如果这些需求变成高频，再考虑平台化。

## 8. 安全边界自检

每次输出必须包含：

- 是否新增 execute：否
- 是否调用 provider：否
- 是否打开 Browser AI：否
- 是否写 AgentRun / TaskArtifact / TaskEvent：否，除非后续平台明确只保存 skill 输出
- 是否写真实仓库：否
- 是否创建 GitHub PR / CI / Sonar / Deploy 平台能力：否
- 是否自动 approve / merge：否
- 是否读取 `.env` / `secret_ref`：否
- 是否访问 `Project.root_path`：否
