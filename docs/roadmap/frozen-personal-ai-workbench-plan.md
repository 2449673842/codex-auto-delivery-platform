# 后续开发冻结计划：个人多 AI 编码工作台

## 0. 当前状态

截至本计划冻结时，PR #43 已合入 master，merge commit 为：

```text
ab4b7aeb3f6e5da6c9232731ec8acdf96b712b8b
```

PR #43 完成了 S18.0.1：

- MCP Bridge quickstart
- 外部 AI handoff 示例
- Skill vs Platform 路线评估文档

S18.0.1 已明确：

- S18 当前是 REST debug endpoint，不是真正 MCP transport
- 平台后续不做弱版 Codex
- 平台定位为记忆层、审计层、证据板、handoff 出口
- Codex / skill / sub-agent 负责主要执行流程

PR #44 已创建为 S18.0.2：

```text
S18.0.2 — PR / CI / Sonar Reader Skill Experiment Docs
```

因此，本冻结计划将 Multi-AI Evidence Run 设计顺延为：

```text
S18.0.3 — Multi-AI Evidence Run 设计文档
```

这样可以避免 S18.0.2 编号与已创建 PR #44 冲突。

## 1. 最终产品定位

本项目不再做“弱版 Codex”，也不再回到重企业交付平台。

最终定位是：

```text
个人多 AI 编码工作台
多 AI 证据收集器
Browser AI 回答采集器
任务记忆层
审计层
Handoff / MCP 上下文出口
Codex / Skill 的增强后端
```

一句话：

```text
Codex 负责执行。
平台负责记住、整理、比较、证明、交接。
```

这与 S18.0.1 的 Skill vs Platform 评估一致。

## 2. 多 AI 四种工作形态

后续所有多 AI 设计统一围绕四种形态。

### 2.1 Broadcast：同题多答

多个 AI 回答同一个问题。

适合：

```text
这个方案有没有风险？
这个 PR 能不能合？
这个 bug 可能原因是什么？
这个 patch 是否安全？
```

输出：

```text
一致结论
分歧点
风险点
推荐下一步
```

### 2.2 Routed：分工协作

多个 AI 处理不同子任务。

示例：

```text
AI A：后端启动链路
AI B：前端构建链路
AI C：配置和端口
AI D：测试日志
AI E：最终综合
```

输出：

```text
各子任务结论
缺失信息
冲突点
最终行动建议
```

### 2.3 Pipeline：流水线接力

一个 AI 的输出作为下一个 AI 的输入。

示例：

```text
Planner
-> Reviewer
-> Risk Checker
-> Final Synthesizer
```

第一版只设计，不急着实现。

### 2.4 Repair Loop：受控失败返工

失败后自动组织证据、多 AI 分析、生成 repair packet，由 Codex 或用户执行修复。

它不是平台无限自动改代码。

流程：

```text
sandbox / verification / CI / Sonar failed
-> 平台收集失败证据
-> 多 AI 分析原因
-> Answer Synthesis 生成 repair packet
-> Codex 执行修复
-> 平台记录 repair attempt
-> 再验证
```

边界：

```text
max_attempts 默认 1
用户可停止
不自动 merge
不自动 deploy
不自动 approve
不自动写真实仓库
```

## 3. 近期开发原则

从现在开始：

```text
少做执行器
多做证据层
少做自动改代码
多做多 AI 分析和交接
少做平台替代 Codex
多做平台增强 Codex
```

每个功能必须回答：

```text
用户点了什么？
系统真实做了什么？
结果保存在哪里？
页面显示什么？
失败时用户能不能看懂？
有没有扩大安全边界？
```

## 4. 与现有项目的对齐和调整建议

### 4.1 编号调整

原计划把 Multi-AI Evidence Run 设计称为 S18.0.2，但 PR #44 已经使用 S18.0.2 做 PR / CI / Sonar Reader skill 实验文档。

冻结后采用：

```text
S18.0.2: PR / CI / Sonar Reader Skill Experiment Docs
S18.0.3: Multi-AI Evidence Run 设计文档
```

后续文档和 PR 不再复用已占用编号。

### 4.2 S19 优先复用现有模型

现有项目已经有：

- DispatchBatch
- DispatchJob
- AgentRun
- TaskArtifact
- TaskEvent
- Answer Synthesis
- Browser AI provider profiles

因此 S19 MVP 优先复用：

```text
DispatchBatch ~= EvidenceRun
DispatchJob ~= EvidenceJob
```

不要一开始新增 EvidenceRun / EvidenceJob，除非复用 DispatchBatch / DispatchJob 出现明显模型阻塞。

### 4.3 Browser AI 不是白搭

Browser AI 的价值不是替代 Codex，而是采集网页 AI 的可见回答并纳入平台证据链。

Codex 擅长：

- 读代码
- 改代码
- 跑测试
- 修复 PR review
- 执行 skill / sub-agent

Browser AI 擅长：

- 使用用户本地浏览器访问网页 AI
- 利用用户手动登录后的网页会话
- 自动填 prompt、发送、等待回答稳定
- 读取可见回答
- 保存 AgentRun / TaskArtifact
- 进入 Answer Synthesis

因此 Browser AI 继续保留，但定位为 evidence provider，不是主执行器。

### 4.4 S19 并发需要保守

Browser AI 与 API provider 不同。网页 AI 可能需要用户登录、页面状态、验证码、人机验证、速率限制。

S19 MVP 并发策略建议：

```text
concurrency_limit 默认 2
同一个 provider 默认不并发
同一个 browser user data dir 默认不并发
不同 provider 可以有限并发
一个 job 失败不影响其他 job
每个 job 独立 status / error / artifact_id
```

如果并发实现复杂，MVP 可以先支持顺序执行，但数据结构保留 concurrency_limit。

### 4.5 Evidence Board 不要抢在 S19 前重做

S19 MVP 可以先复用现有 TaskDetail：

- AgentRuns 列表
- Artifacts 区域
- Answer Synthesis 区域
- Browser AI 面板
- Multi-AI Workspace 现有展示

Evidence Board / Run Timeline 放到 S22 做系统化整理，避免 S19 一次性过大。

### 4.6 PR / CI / Sonar Reader 先 skill 化

PR #44 已经把 PR / CI / Sonar Reader 设计为 Codex skill 实验。

冻结后，平台不优先做 S19 平台版 PR Reader。后续改为：

```text
先做 skill 真实试跑
如果 skill 足够，平台 PR Reader 暂缓
如果需要长期记录 / Evidence Board / Timeline，再把证据存储平台化
```

## 5. 后续阶段计划

### S18.0.3 — Multi-AI Evidence Run 设计文档

目标：

```text
把后续 S19 从“多 AI 执行器”重新定义为“多 AI 证据运行 / Multi-AI Evidence Run”。
```

它不是自动写代码，而是：

```text
向多个 AI 收集意见
保存证据
比较分歧
生成综合结论
交给 Codex 或用户执行
```

新增文档：

```text
docs/design/multi-ai-evidence-run.md
docs/strategy/browser-ai-vs-codex.md
docs/roadmap/next-after-s18.md
```

文档必须说明：

- Broadcast / Routed / Pipeline / Repair Loop 四种工作形态
- Browser AI 为什么不是白搭
- Codex 和 Browser AI 的分工
- 平台为什么不是弱版 Codex
- S19 MVP 范围
- 受控并发模型
- 用户流程
- 后端流程
- 前端流程
- 数据模型复用方案
- 安全边界

验收标准：

```text
只改文档
不新增 execute
不调用 provider
不打开浏览器
不写库
不创建 PR / CI / Sonar / Deploy
不自动 approve / merge
```

### S19 — Multi-AI Evidence Run MVP

目标：

实现第一个真正的多 AI 协作闭环。

它不是自动改代码，而是：

```text
TaskDetail
-> 创建 Multi-AI Evidence Run
-> 选择多个 provider
-> 选择模式 broadcast / routed
-> 平台执行多个 AI evidence job
-> 保存每个结果
-> 自动 Answer Synthesis
-> 页面展示一致点 / 分歧点 / 风险 / 下一步
```

MVP 支持：

```text
broadcast
routed
```

暂不实现：

```text
pipeline
repair loop
自动代码修改
自动 PR
自动 merge
自动 deploy
```

Provider 范围：

```text
ChatGPT Web
Claude Web
Gemini Web
DeepSeek Web
Kimi Web
Custom
```

可选：

```text
OpenAI API review mode
```

并发要求：

```text
concurrency_limit 默认 2
同一个 provider 默认不并发
不同 provider 可以受控并发
一个 job 失败不影响其他 job
每个 job 独立 status / error / artifact_id
```

数据模型：

```text
优先复用 DispatchBatch / DispatchJob / AgentRun / TaskArtifact / AnswerSynthesis / TaskEvent
```

前端：

```text
TaskDetail 新增 Multi-AI Evidence Run 面板
```

页面展示：

```text
mode: broadcast / routed
provider list
job status
answer preview
artifact_id
error_message
overall_status
synthesis result
```

### S20 — Controlled Repair Loop with Codex 设计

目标：

保留自动重修价值，但不让平台自己无限改代码。

设计方向：

```text
平台收集失败证据
多 AI 分析失败原因
平台生成 repair packet
Codex 执行修复
平台记录 repair attempt
用户最终确认
```

新增文档：

```text
docs/design/controlled-repair-loop-with-codex.md
```

必须说明：

- 什么失败会触发 repair
- failure evidence 包含什么
- 如何调用 broadcast / routed / pipeline 分析失败
- repair packet 格式
- Codex 如何作为执行者
- 平台如何记录 repair attempt
- max_attempts 默认 1
- 用户如何停止

明确禁止：

```text
平台自动写真实仓库
平台无限 repair loop
平台自动创建 PR
平台自动 merge
平台自动 deploy
```

### S21 — PR / CI / Sonar Reader Skill 原型试跑

PR #44 已完成 skill 原型文档。

S21 不再重复写平台功能，而是做真实 skill 试跑和结论确认。

目标：

```text
验证 PR / CI / Sonar Reader 是否更适合做 Codex skill，而不是平台功能。
```

输入：

```text
PR URL / PR number / repo
```

输出：

```text
主脑复审报告
```

必查：

- PR state
- head / base commit
- changed files
- GitHub checks
- Sonar Quality Gate
- Security Hotspots
- Duplication on New Code
- New Issues
- PR body 是否包含验证结果

判断标准：

```text
如果 skill 满足 80% 高频需求，平台版 PR Reader 继续暂缓。
如果暴露长期记录、跨任务检索、证据留存、UI 展示痛点，再沉淀为 Evidence Board / Timeline 功能。
```

### S22 — Evidence Board / Run Timeline

目标：

把当前所有任务证据变成时间线和证据板。

页面应展示：

```text
Task created
AI run started / finished / failed
Browser AI answer saved
Artifact created
Sandbox applied
Sandbox gate passed / blocked
Answer Synthesis refreshed
MCP handoff generated
Repair attempt created
Verification result imported
PR status imported
```

价值：

```text
让用户几个月后还能知道：
当时为什么这样改？
哪个 AI 建议的？
哪个测试失败？
最后为什么决定合入或不合入？
```

### S23 — Project Memory

目标：

沉淀项目级长期记忆。

包括：

- 怎么启动项目
- 常见端口
- 常见失败原因
- 常用测试命令
- 不能乱改的文件
- PR 规范
- Sonar 坑
- 用户偏好
- 常用 AI provider
- 常用 routed job 模板

与 MCP 的关系：

```text
外部 AI / Codex skill 可以通过 MCP Bridge 读取 Project Memory。
```

### S24 — 真正 MCP Transport / Skill Adapter

目标：

把当前 REST debug endpoint 升级成真正可接入外部 AI 的形式。

候选路线：

```text
真正 MCP transport
Codex skill adapter
Claude Desktop / Cursor 配置示例
```

前提：

```text
S18 REST MCP Bridge 已经验证可用。
Project Memory / Evidence Board 已经有足够上下文价值。
```

## 6. 暂缓或不做的内容

### 暂缓

```text
复杂 Multi-AI Real Batch execute
Repair Loop 自动实现
PR Creation Adapter
Verification Runner 平台版
真实 MCP execute
```

### 不做

```text
自动 merge
自动 deploy
自动 approve
平台无限自动改代码
平台绕过登录 / 验证码
平台保存账号 / 密码 / cookie / session
任意 shell 执行器
通用 Agent Runtime
```

## 7. 推荐顺序

最终推荐顺序：

```text
S18.0.2 PR / CI / Sonar Reader Skill Experiment Docs
S18.0.3 Multi-AI Evidence Run 设计
S19 Multi-AI Evidence Run MVP
S20 Controlled Repair Loop with Codex 设计
S21 PR / CI / Sonar Reader Skill 原型试跑
S22 Evidence Board / Run Timeline
S23 Project Memory
S24 真正 MCP Transport / Skill Adapter
```

## 8. 下一步执行指令

下一步直接进入：

```text
S18.0.3 — Multi-AI Evidence Run 设计文档
```

只做设计文档，不写代码。

目标是把下面四种形态正式写进项目设计：

```text
Broadcast
Routed
Pipeline
Repair Loop
```

然后再进入 S19 MVP。

## 9. 冻结结论

本路线冻结后，后续不再反复切换“平台做执行器”或“平台替代 Codex”的方向。

固定原则：

```text
Codex 负责执行。
Skill 固化流程。
Browser AI 采集网页 AI 证据。
平台负责记忆、审计、证据、综合、交接。
```
