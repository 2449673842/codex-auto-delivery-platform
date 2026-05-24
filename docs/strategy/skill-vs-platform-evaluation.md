# Skill vs Platform Evaluation

## 背景

路线调整后，本项目不再优先和 Codex / Skills / MCP / sub-agent 拼执行能力。

Codex 已经能覆盖大量当下执行型流程：

- 读代码
- 修改代码
- 跑测试
- 调工具
- 使用 skill
- 调 sub-agent
- 创建 PR
- 根据 review 返工

因此，后续能力需要先判断：哪些应该 skill 化，哪些才值得继续平台化。

新的产品定位：

```text
Codex / 外部 AI 负责执行流程
平台负责记忆、证据、审计、handoff、对比、复盘
```

## A. 适合 Codex Skill 的能力

这类能力偏“当下怎么执行”。它们通常可以通过固定 prompt、工具调用顺序、输出模板和安全检查清单解决，不一定需要平台长期状态。

### PR / CI / Sonar Reader

适合 skill 化。

原因：

- 多数步骤是读取 GitHub / CI / Sonar 当前状态
- 输出是一次性的 review packet 或复审报告
- Codex 已经能通过 `gh` / API / 浏览器工具完成大量读取动作
- 不一定需要平台数据库参与

建议先做 Codex skill，而不是马上做平台 S19。

### 生成 Review Packet

适合 skill 化。

原因：

- 本质是固定模板整理
- 输入来自 PR body、changed files、test output、Sonar summary
- 输出通常是主脑复审报告或 PR body 更新建议

### 跑固定验证命令

适合 skill 化。

原因：

- Codex 已经能在用户授权下运行命令
- skill 可以定义允许命令、禁止命令、输出摘要格式
- 平台不必急着实现 Verification Runner

注意：如果需要长期保存验证结果，再考虑平台侧 Verification Result Importer。

### 生成 Handoff Prompt

适合 skill 化，也适合平台辅助。

原因：

- skill 负责把当前上下文整理成 prompt
- 平台负责提供结构化 task / run / artifact / synthesis 数据

最佳形态是：

```text
Skill 调 MCP Bridge 读取上下文
Skill 生成 handoff prompt
平台保存历史 handoff packet
```

### 比较两个 AI 回答

适合 skill 化。

原因：

- 如果只是一次性比较，可以由 skill 读取两个回答并输出差异表
- 不需要复杂 UI

如果要长期沉淀多 AI evidence，则进入平台能力。

### 按 SOP 返工检查

适合 skill 化。

原因：

- SOP 是流程规则
- Codex skill 可以强制检查项、输出 pass / blocked / needs_update
- 不需要平台实现复杂 Repair Loop

### 输出主脑复审报告

适合 skill 化。

原因：

- 输出格式固定
- 输入是 PR、验证结果、安全边界、Sonar 数据
- skill 可以减少人工复制粘贴

## B. 适合平台保留的能力

这类能力需要数据库、UI、长期状态、跨任务检索或审计记录。单个 skill 可以临时模拟，但如果 skill 自己维护数据库和 UI，最终又会变成平台。

### 长期任务数据库

适合平台保留。

原因：

- 任务状态、历史决策、运行记录需要长期保存
- 多个 AI / 多次任务之间需要关联
- 几个月后仍要能复盘

### AgentRun / Artifact / TaskEvent 结构化记录

适合平台保留。

原因：

- 这是项目证据链的基础
- 每次 AI 输出、patch、review、错误、blocked reason 都应该可追溯
- skill 不适合承担长期审计数据库职责

### 多 AI 结果证据板

适合平台保留。

原因：

- 需要把多个 AgentRun / Artifact / Answer Synthesis 放在同一 UI 中比较
- 需要跨 run 追踪来源、状态、可信度、风险

### Run Timeline

适合平台保留。

原因：

- 时间线需要聚合 TaskEvent、AgentRun、Artifact、PR、CI、Sonar、verification result
- UI 价值高
- 是“为什么最后这么决策”的复盘入口

### Project Memory

适合平台保留。

原因：

- 项目 SOP、约束、历史坑、架构决策、常用验证方式需要长期沉淀
- 外部 AI 可以通过 MCP Bridge 读取 memory，而不是每次重新解释

### Handoff Packet 历史

适合平台保留。

原因：

- handoff packet 不只是一次性 prompt
- 历史 packet 能说明每次任务交接时的上下文和安全边界
- 适合作为外部 AI 接入时的审计记录

### 多项目检索

适合平台保留。

原因：

- 需要跨项目、跨任务、跨 artifact 搜索
- skill 可以临时搜索文件，但不适合维护结构化索引和 UI

### 安全审计记录

适合平台保留。

原因：

- 哪次调用 read-only，哪次 dry-run，哪次 blocked，都需要可追溯
- 平台可以保存明确的安全边界记录

## C. 暂缓或降级的能力

这类能力容易和 Codex 执行能力重叠，或者风险较高。短期不继续大开发。

### Multi-AI Real Batch

暂缓。

原因：

- Codex / sub-agent / skill 已经能调度多个执行者
- 平台如果做真实 batch execute，容易变成弱版 Codex runtime

降级建议：

- 先做 Multi-AI Evidence Comparison
- 不急着做 Multi-AI Real Batch execute

### Repair Loop MVP

暂缓。

原因：

- Codex 已经擅长根据失败测试返工
- 平台自动 repair 容易引入复杂执行与安全风险

降级建议：

- 用 skill 做返工检查和修复建议
- 平台只保存 repair evidence / timeline

### PR Creation Adapter

暂缓。

原因：

- Codex / `gh` 已经能在人类确认后创建 PR
- 平台实现真实 PR 创建会增加权限、token、审计复杂度

降级建议：

- 先做 PR evidence import / reader
- 真实创建 PR 继续由 Codex 或人工执行

### 复杂自动执行器

暂缓。

原因：

- 和 Codex 的核心能力高度重叠
- 风险高，容易扩大 shell / repo / deploy 权限

降级建议：

- 平台不做“超级 agent”
- 平台保存结果、证据、审计和上下文

## 后续决策建议

### 平台保留为记忆层 / 审计层 / 证据板 / handoff 出口

平台最值得继续做的是：

- 长期任务数据库
- AgentRun / Artifact / TaskEvent
- Evidence Board
- Run Timeline
- Project Memory
- Handoff Packet 历史
- Answer Synthesis 证据来源
- MCP Bridge 上下文出口

### Codex Skill 负责执行流程 / PR 检查 / 验证命令 / 固定 SOP

适合 skill 化的优先事项：

- PR / CI / Sonar Reader skill
- Review Packet 生成 skill
- Verification command SOP skill
- Mastermind review report skill
- Handoff prompt skill
- AI answer comparison skill

### 不再优先开发弱版 Codex 执行器

后续不优先做：

- 通用 agent runtime
- 复杂多 agent execute
- 自动 repair loop
- 自动 PR creation / merge / deploy
- 任意 shell 执行器

如果某个能力只是“让 AI 去执行一串步骤”，先做 skill。只有当它需要长期状态、结构化证据、跨任务 UI 或审计链时，才进入平台。

## 推荐下一步

先验证 skill 化路线：

```text
S18.0.2: Codex Skill 版 PR / CI / Sonar Reader 原型
```

验收目标：

- 能读取 PR URL / PR number
- 能整理 changed files、checks、Sonar summary
- 能输出主脑复审格式
- 不写平台数据库
- 不创建 PR / merge / deploy

如果 skill 原型满足 80% 高频需求，则 S19 平台 PR Reader 暂缓。

如果 skill 原型暴露出明显痛点，例如缺少历史记录、证据检索、跨任务复盘，再把这些痛点沉淀为平台功能。
