# PR / CI / Sonar Reader Skill Prototype

## 目标

设计一个 Codex skill，用于只读读取 GitHub PR、CI checks、SonarCloud summary，并输出主脑复审报告。

本 skill 原型用于验证：PR / CI / Sonar Reader 是否更适合 skill 化，而不是继续平台化为 S19 后端功能。

## 范围

本 skill 只负责读取和整理，不负责执行合并或部署。

允许：

- 读取 PR metadata
- 读取 PR changed files
- 读取 GitHub checks / workflow runs
- 读取 SonarCloud summary
- 检查 PR body 是否包含必要验收字段
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

## 输入

skill 应支持以下输入形式：

```text
PR URL: https://github.com/<owner>/<repo>/pull/<number>
```

或：

```text
repo: <owner>/<repo>
pr_number: <number>
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

## 推荐工具调用顺序

### 1. 读取 PR 基本信息

推荐：

```bash
gh pr view <number> --repo <owner>/<repo> \
  --json number,url,state,mergeable,headRefOid,baseRefOid,changedFiles,title,body
```

必须记录：

- PR URL
- PR number
- state
- mergeable
- head commit full SHA
- base commit full SHA
- changed files count
- title
- body

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

### 4. 读取 SonarCloud summary

优先使用 GitHub check-run output，因为它通常包含：

- Quality Gate
- Security Hotspots
- Duplication on New Code
- New Issues

可选读取 SonarCloud API：

```text
https://sonarcloud.io/api/measures/component?component=<project_key>&pullRequest=<pr_number>&metricKeys=new_duplicated_lines_density,new_violations,security_hotspots
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

### 5. 检查 PR body

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

## 输出：主脑复审报告模板

```text
复审结论：approved / needs_update / blocked

PR:
- URL:
- 编号:
- state:
- mergeable:
- head:
- base:
- changed files:

验证结果：
- targeted backend pytest:
- full backend pytest:
- compileall:
- npm build:
- frontend tests:
- smoke test:

SonarCloud：
- Quality Gate:
- Security Hotspots:
- Duplication on New Code:
- New Issues:

范围检查：
- changed files 是否匹配 PR body:
- 是否存在 out-of-scope 修改:
- 是否只改文档 / 前端 / 后端:

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

## blocked / needs_update 规则

必须 blocked：

- SonarCloud Quality Gate failed
- Security Hotspots > 0
- New Issues > 0，除非主脑明确接受
- PR body 与 GitHub 实际 changed files / head / test count 不一致
- 出现 out-of-scope 修改
- 出现 secret 泄露
- 自动 merge / deploy / approve
- 直接 push master

必须 needs_update：

- Sonar pending，无法判断
- PR body 缺字段
- changed files 列表未展开
- 测试结果写了但没有真实来源
- 文档 PR 未说明为什么不跑测试

可以 approved：

- GitHub 实际状态与 PR body 一致
- SonarCloud passed
- changed files 符合范围
- 验证结果完整或跳过理由合理
- 安全边界清楚

## Skill 与平台边界

skill 适合完成本流程，因为它是一次性读取和报告生成。

平台暂不需要实现 S19 PR Reader，除非出现以下需求：

- 需要长期保存每次 PR 复审结果
- 需要跨 task / project 检索历史 PR 证据
- 需要把 PR / CI / Sonar 状态放入 Task Timeline
- 需要 Evidence Board 展示多次复审差异
- 需要把 review packet 作为 TaskArtifact 保存

如果这些需求变成高频，再考虑平台化。
