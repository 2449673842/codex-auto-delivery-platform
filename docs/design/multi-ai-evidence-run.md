# S18.0.3 Multi-AI Evidence Run 设计

## 1. 定位

Multi-AI Evidence Run 不是多 AI 执行器，也不是自动代码修改器。它的定位是：

```text
向多个 AI 收集意见
保存每个回答作为证据
比较一致点和分歧点
生成 Answer Synthesis
交给 Codex 或用户执行下一步
```

这符合当前项目的新定位：Codex / skill 负责执行，平台负责记忆、证据、审计、handoff 和 synthesis。

## 2. 为什么 Browser AI 不是白搭

Codex 已经能读代码、改代码、跑测试和执行 skill，但 Codex 不能替用户稳定保存多个网页 AI 的可见回答，也不能自动把这些回答沉淀进平台的任务证据链。

Browser AI 已经完成：

- provider profiles：Custom / ChatGPT Web / Claude Web / Gemini Web / DeepSeek Web / Kimi Web
- custom selector
- run steps 可视化
- stable response capture
- 登录辅助提示
- 成功后创建 AgentRun / TaskArtifact
- 自动刷新 Answer Synthesis

Browser AI 的价值是 evidence provider：它把网页 AI 的回答从“浏览器里的一段临时文本”变成可检索、可比较、可交接的任务证据。

## 3. 和 Codex 执行器的区别

### Codex 负责

- 读代码和定位问题
- 修改代码
- 跑测试 / build / lint
- 执行 skill SOP
- 根据 repair packet 做修复
- 准备或更新 PR 内容

### Multi-AI Evidence Run 负责

- 组织多个 AI 参与同一任务分析
- 调用 Browser AI / API AI / 未来 MCP provider 收集回答
- 记录每个 job 的状态、错误和产物
- 保存 AgentRun / TaskArtifact
- 触发 Answer Synthesis
- 展示 common findings、risks、recommended actions、next questions

### 明确不负责

- 不自动改代码
- 不写真实仓库
- 不创建 PR
- 不调用 CI / Sonar / Deploy
- 不自动 approve / merge
- 不绕过 Browser AI 登录或验证码

## 4. 四种多 AI 工作形态

### 4.1 Broadcast / 同题多答

多个 AI 回答同一个问题，用于收集独立判断、比较一致点和分歧点。

适合：

```text
这个方案有没有风险？
这个 PR 能不能合？
这个 bug 可能原因是什么？
这个 patch 是否安全？
```

输出：

- common findings
- disagreements
- risks
- recommended actions
- next questions

S19 MVP 支持 broadcast。

### 4.2 Routed / 分工协作

多个 AI 按 role 处理不同子任务，例如：

```text
backend
frontend
config
test
risk
summary
```

每个 routed job 有独立 prompt、provider、status、error、artifact_id 和 answer preview。

S19 MVP 支持 routed。

### 4.3 Pipeline / 流水线接力

一个 AI 的输出作为下一个 AI 的输入，例如：

```text
planner -> reviewer -> risk_checker -> final_synthesizer
```

Pipeline 对状态、输入截断、失败恢复和引用来源要求更高。S19 只设计，不实现。

### 4.4 Repair Loop / 受控失败返工

当 sandbox / verification / CI / Sonar / review 失败时，平台收集失败证据，触发 broadcast / routed / pipeline 分析，生成 repair packet，由 Codex 或用户执行修复，平台记录 repair attempt 和验证结果。

Repair Loop 不是无限自动修复：

```text
max_attempts 默认 1
用户可停止
平台不自动写真实仓库
平台不自动 merge / deploy / approve
```

S19 只设计 Repair Loop，不实现。

## 5. S19 MVP 范围

### 5.1 S19 MVP 做

- 支持 broadcast
- 支持 routed
- 复用 Browser AI provider profiles
- 复用 AgentRun / TaskArtifact / Answer Synthesis
- 优先复用 DispatchBatch / DispatchJob 作为 EvidenceRun / EvidenceJob
- 支持 bounded concurrency
- 一个 job 失败不影响其他 job
- 成功后自动刷新 Answer Synthesis
- 页面显示每个 job 的 status / error / artifact_id / answer preview

### 5.2 S19 MVP 不做

- 不实现 pipeline 执行
- 不实现 repair loop 执行
- 不自动改代码
- 不写真实仓库
- 不创建 PR
- 不调用 CI / Sonar / Deploy
- 不自动 approve / merge
- 不做无限 repair loop
- 不绕过 Browser AI 登录 / 验证码

## 6. 受控并发模型

Browser AI 与 API provider 不同。网页 AI 可能受登录状态、验证码、人机验证、速率限制和页面状态影响，所以并发必须保守。

建议模型：

```text
concurrency_limit 默认 2
同一个 provider 默认不并发
同一个 browser user data dir 默认不并发
不同 provider 可以有限并发
一个 job 失败不影响其他 job
每个 job 独立 status / error / artifact_id
```

如果实现复杂，S19 MVP 可以先顺序执行，但数据结构保留 `concurrency_limit`，避免以后重做 API 和 UI。

## 7. 用户流程

Broadcast：

```text
TaskDetail
-> Multi-AI Evidence Run
-> 选择 mode=broadcast
-> 选择 providers
-> 输入或选择 prompt
-> Run
-> 查看每个 job 的状态和回答预览
-> Answer Synthesis 自动刷新
-> 用户或 Codex 根据 synthesis 执行下一步
```

Routed：

```text
TaskDetail
-> Multi-AI Evidence Run
-> 选择 mode=routed
-> 添加 roles: backend / frontend / config / test / risk / summary
-> 为每个 role 选择 provider 和 prompt
-> Run
-> 查看每个 role 的结果
-> Answer Synthesis 自动生成综合结论
```

失败时：

```text
某个 job failed
-> 该 job 显示 failed step / error_message
-> 其他 job 继续
-> synthesis 标记缺失来源或失败来源
```

## 8. 后端流程

建议优先复用已有服务，不新增一套 agent runtime。

```text
TaskDetail request
-> create DispatchBatch(type=evidence_run, mode=broadcast|routed)
-> create DispatchJob for each provider/role
-> execute each job through existing Browser AI / AI dispatch service boundary
-> each successful job creates AgentRun
-> each successful job creates TaskArtifact(kind=browser_ai_answer or ai_answer)
-> each job stores status / error / artifact_id
-> refresh Answer Synthesis preview
```

第一版可以顺序执行；并发调度作为受控扩展。

## 9. 前端流程

TaskDetail 新增或扩展 Multi-AI Evidence Run 面板：

- mode：broadcast / routed
- provider list
- role list（routed）
- prompt source
- concurrency_limit 显示或高级设置
- Run 按钮
- job status list
- error_message
- artifact_id
- answer preview
- synthesis refreshed 状态

不要新增 Create PR / Deploy / Merge 入口。

## 10. 数据模型复用方案

优先复用：

```text
DispatchBatch ~= EvidenceRun
DispatchJob ~= EvidenceJob
AgentRun
TaskArtifact
TaskEvent
Answer Synthesis
Browser AI provider profiles
```

建议字段映射：

```text
DispatchBatch.mode = broadcast | routed | pipeline | repair_loop_design
DispatchBatch.status = pending | running | succeeded | failed | partial
DispatchJob.role = backend | frontend | config | test | risk | summary | general
DispatchJob.provider = chatgpt_web | claude_web | gemini_web | deepseek_web | kimi_web | custom | openai_api
DispatchJob.status = pending | running | succeeded | failed | blocked
DispatchJob.artifact_id = successful output artifact
DispatchJob.error_message = redacted failure reason
```

只有当 DispatchBatch / DispatchJob 无法表达 evidence semantics 时，才新增 EvidenceRun / EvidenceJob。

## 11. Evidence metadata

S18.0.3 之后的 S19 设计应让每个 job 至少保留：

- provider
- mode
- role
- prompt summary 或 prompt hash
- status
- failed step / error_message
- agent_run_id
- artifact_id
- included_in_synthesis
- created_at / finished_at

Skill-first 报告也应该尽量按类似结构输出，未来才能无痛导入 TaskArtifact 或 Timeline。

## 12. 安全边界

S19 Evidence Run 必须保持：

- 不自动改代码
- 不写真实仓库
- 不创建 PR
- 不调用 CI / Sonar / Deploy
- 不自动 approve / merge
- 不读取 `.env`
- 不读取 `secret_ref`
- 不保存账号 / 密码 / cookie / session
- Browser AI 不绕过登录或验证码
- 不调用隐藏 API
- 不访问 Project.root_path 做真实修改

## 13. 后续扩展

### MCP provider

当真正 MCP transport 完成后，外部 AI 可以作为 read-only / dry-run evidence provider 参与 Evidence Run。

### Codex skill provider

Codex skill 可以输出结构化复审报告、验证报告或 repair packet。平台可以把这些报告作为 TaskArtifact 或 Timeline evidence 保存。

### Local model provider

本地模型可作为低成本 reviewer 或 summarizer，但仍应遵守同样的 evidence metadata、状态记录和安全边界。
