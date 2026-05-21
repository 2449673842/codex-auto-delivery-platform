# Multi-AI Task Routing

后续设计必须支持三种多 AI 协作模式：Broadcast、Routed、Pipeline。

## Broadcast Mode

Broadcast Mode 是同一个问题问多个 AI。

适用场景：

- 方案比较
- 架构设计
- 风险判断
- 多 AI 互相验证
- 让不同模型给独立意见

示例：

```text
问题：这个 PR 有没有合入风险？

同时发给：
- OpenAI API
- ChatGPT Web
- Claude Web
- Gemini
- 本地模型

最后由 Answer Synthesizer 汇总。
```

Broadcast 的重点是独立意见，而不是分工。

## Routed Mode

Routed Mode 是一个大任务拆成不同子问题，不同子问题分派给不同 AI。

这是个人工作台的重点模式，因为用户真正需要的是像管理一个小团队一样分派不同问题。

示例：

```text
大任务：帮我判断 PR #24 能不能合入。

AI A：检查 PR body 和 changed files 是否一致
AI B：审查后端实现风险
AI C：审查测试覆盖
AI D：查外部类似项目做法
AI E：总结最终结论
Rule Gate：检查硬规则
```

Routed 的重点是任务拆分、上下文差异和结果汇总。

## Pipeline Mode

Pipeline Mode 是多个 AI 或 rule provider 串成流水线。

示例：

```text
Planner AI
-> Coder AI
-> Reviewer AI
-> Risk AI
-> Synthesizer AI
-> Sandbox Gate
-> Human Decision
```

Pipeline 适合自动开发链路，但必须保留用户最终判断。

## Core Objects

S12 开始建议引入：

- DispatchBatch
- DispatchJob

示例结构：

```json
{
  "dispatch_batch_id": 1,
  "task_id": 1,
  "mode": "routed",
  "jobs": [
    {
      "dispatch_job_id": 1,
      "question": "检查 PR body 是否准确",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "mode": "review",
      "status": "queued",
      "prompt_hash": "...",
      "context_packet_hash": "..."
    }
  ]
}
```

## Routing Inputs

路由决策应使用：

- task goal
- project memory
- context packet
- selected files
- risk level
- provider availability
- token budget
- previous failures
- user preference
- required verification

## Routing Outputs

每个 DispatchJob 至少应明确：

- question
- provider
- model
- mode
- context packet hash
- prompt hash
- expected artifact type
- safety boundary
- whether it may generate patch
- whether human confirmation is required

## Safety Boundary

多 AI 调度不得绕过现有安全边界：

- 不读取 `.env`
- 不读取 `secret_ref`
- 不保存 API key / cookie / session
- 不自动 merge
- 不自动 deploy
- 不自动 approve high / critical risk
- 不自动 approve human_required
- 不为了通过测试放宽断言
- 不为了通过 Sonar 删除关键逻辑

所有真实外部动作必须可审计，并由用户确认。
