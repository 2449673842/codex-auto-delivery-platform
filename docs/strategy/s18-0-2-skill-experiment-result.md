# S18.0.2 Skill Experiment Result

## 实验目标

S18.0.2 的目标不是实现平台 S19 PR / CI / Sonar Reader，而是验证这类能力是否可以先做成 Codex skill。

要验证的问题：

```text
PR / CI / Sonar Reader 是执行型流程，还是需要平台长期状态？
```

如果它主要是读取当前 PR 状态、整理 checks、解析 Sonar、输出主脑复审报告，那么 skill 足够。

如果它需要长期保存、跨任务检索、证据留存、UI 展示，那么平台才有必要继续做。

## 本 skill 原型验证什么

### 1. 是否能稳定读取 PR 状态

需要验证：

- PR URL / number 是否可解析
- PR state 是否可读取
- mergeable 是否可读取
- head / base commit 是否可读取
- changed files count 是否可读取
- changed files list 是否可读取

判断：

- 如果 `gh pr view` 和 `gh pr diff` 能稳定完成，skill 足够。
- 如果需要长期保存每次 PR 状态变化，则进入平台 Evidence Board / Timeline。

### 2. 是否能稳定读取 CI checks

需要验证：

- GitHub checks 是否可读取
- workflow run 状态是否可读取
- failure / pending / cancelled 是否可识别
- check output 是否能整理成人类可读 summary

判断：

- 如果只需要当前状态，skill 足够。
- 如果需要长期追踪 CI 波动趋势，平台化。

### 3. 是否能稳定读取 SonarCloud

需要验证：

- SonarCloud Code Analysis check 是否可读取
- Quality Gate 是否可判断
- Security Hotspots 是否可读取
- Duplication on New Code 是否可读取
- New Issues 是否可读取

判断：

- 如果 check-run output 足够，skill 足够。
- 如果需要持久化 Sonar 指标、趋势对比、按任务复盘，平台化。

### 4. 是否能输出主脑复审报告

需要验证：

- 是否能按固定中文模板输出
- 是否能检查 PR body 与 GitHub 实际状态一致性
- 是否能区分 approved / needs_update / blocked
- 是否能明确缺失信息
- 是否能保持安全边界

判断：

- 如果输出稳定，skill 足够。
- 如果报告需要入库、被外部 AI 读取、进入 Evidence Board，则平台化。

## 判断标准

### S19 平台 PR Reader 暂缓条件

如果 skill 能稳定完成以下 80% 高频复审需求，则 S19 平台 PR Reader 暂缓：

- 读取 PR state / head / base / changed files
- 读取 GitHub checks
- 读取 SonarCloud Quality Gate
- 读取 Security Hotspots
- 读取 Duplication on New Code
- 读取 New Issues
- 检查 PR body 是否中文、是否包含验证结果
- 输出主脑复审报告
- 在 pending / missing / failed 时给出 blocked reason
- 不创建 PR、不 merge、不 deploy、不自动 approve

### 进入平台 Evidence Board / Timeline 的条件

如果出现以下需求，则不应继续塞进 skill，而应进入平台：

- 长期记录每次 PR 复审结果
- 将 PR / CI / Sonar 结果关联到 Task
- 将复审报告保存为 TaskArtifact
- 在 Run Timeline 展示 PR 状态变化
- 跨任务检索历史复审记录
- 对比多个 PR 的 Sonar / CI 趋势
- 让外部 AI 通过 MCP 读取历史 evidence
- 在 UI 中展示证据链和决策理由

## 实验结论

初步结论：

```text
PR / CI / Sonar Reader 的“读取当前状态 + 输出复审报告”部分适合 Codex skill。
```

原因：

- 它是当下执行型流程
- Codex 已经能调用 GitHub CLI / API
- 输出模板固定
- 不需要新增平台数据库
- 不需要新增 API
- 不需要新增前端
- 安全边界更简单

平台不应优先开发一个弱版 PR Reader 后端。

## 后续路线建议

### 1. 先做真正 Codex skill

建议下一步不是做平台 S19，而是创建 Codex skill：

```text
pr-ci-sonar-reader
```

skill 文件应包含：

- 触发语义
- 输入格式
- 工具调用顺序
- GitHub / Sonar 读取方法
- blocked / needs_update / approved 规则
- 中文输出模板
- 安全边界

### 2. 用真实 PR 试跑

至少用以下类型 PR 验证：

- 只改文档 PR
- 后端代码 PR
- 前端代码 PR
- Sonar failed PR
- checks pending PR
- PR body 缺字段 PR
- changed files 不一致 PR

### 3. 决定是否平台化

如果 skill 能覆盖 80% 复审需求：

```text
S19 平台 PR / CI / Sonar Reader 暂缓
```

如果 skill 暴露出长期记录和复盘需求：

```text
只把 evidence storage / timeline / artifact 归档平台化
```

不要把“读取当前 PR 并输出一次报告”平台化。

## 推荐平台后续方向

平台继续保留为：

- 记忆层
- 审计层
- 证据板
- Run Timeline
- Handoff 出口
- MCP context source

Codex skill 负责：

- PR 检查
- CI / Sonar 读取
- 验证命令执行 SOP
- 主脑复审报告
- 固定流程检查

## 安全边界结论

S18.0.2 不新增任何执行能力：

- 不新增 execute
- 不调用 provider
- 不写平台数据库
- 不新增 API
- 不改前端
- 不读取 `.env`
- 不读取 `secret_ref`
- 不访问 `Project.root_path` 做真实修改
- 不创建 PR / CI / Sonar / Deploy
- 不自动 approve / merge

本阶段只提供 skill 原型设计和评估依据。
