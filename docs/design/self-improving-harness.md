# Self-Improving Harness

Self-Improving Harness 的目标不是让平台无人监管地改自己，而是让平台在每次任务后复盘，并提出可审核的改进建议。

## Stages

自我改进分三步推进。

### S22: Run Retrospective

每次任务结束后自动复盘。

输出：

- `run_retrospective.json`
- `task_retrospective.md`
- `failure_summary.md`

复盘内容：

- 任务是否成功
- 失败在哪一步
- 哪个 AI 有用
- 哪个 AI 浪费 token
- 哪个 prompt 太长
- 哪个上下文缺失
- 哪个测试没覆盖
- 哪个安全边界被触发
- 主脑 blocker 是什么
- 修复用了几轮
- 最终 outcome 是什么

### S23: Harness Improvement Suggestions

平台根据复盘提出“下次如何做得更好”。

建议类型：

- 更新 prompt template
- 更新 Project Memory
- 更新 Context Selector 规则
- 更新 AGENTS.md checklist
- 新增测试模板
- 调整 provider routing
- 调整 token budget
- 新增常见失败模式
- 标记某类任务更适合某个 AI

这一阶段只建议，不自动改。

### S24: Controlled Harness Evolution

平台可以生成“改进自身”的 PR，但必须受控。

允许改：

- prompt templates
- project memory
- provider routing policy
- context selector hints
- answer synthesizer prompts
- review checklist
- test helper templates
- docs/harness
- AGENTS.md 流程规则

禁止：

- 不自动放宽安全边界
- 不自动关闭测试
- 不自动绕过 Sonar
- 不自动 approve high risk
- 不自动 approve human_required
- 不自动 merge
- 不自动 deploy
- 不自动读取 secret

## Controlled Flow

```text
Run Retrospective
-> Harness Improvement Suggestions
-> 生成 harness improvement PR
-> 测试
-> 主脑审核
-> 用户确认
-> 合入
```

任何自动进化都必须以 PR 形式出现，且等待主脑审核。

## Scoring Ideas

后续可以记录：

- provider success rate
- task type suitability
- average token cost
- average latency
- reviewer blocker rate
- patch success rate
- sandbox failure reason
- Sonar recurring issue
- prompt reuse effectiveness

这些评分只用于辅助路由和复盘，不应替代用户判断。

## Safety Boundary

Self-Improving Harness 不能成为绕过安全边界的机制。

必须始终遵守：

- 不读取 `.env`
- 不读取 `secret_ref`
- 不保存 API key / cookie / session
- 不自动 merge
- 不自动 deploy
- 不自动 approve high / critical risk
- 不自动 approve human_required
- 不为了通过测试放宽断言
- 不为了通过 Sonar 删除关键逻辑
- 所有真实外部动作必须可审计
