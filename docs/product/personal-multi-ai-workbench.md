# Personal Multi-AI Coding Workbench

本项目的产品定位从“AI 自动代码交付平台”校准为“个人多 AI 编码工作台”。

核心目标不是让 AI 自动把代码交付到生产，而是减少个人开发者在多个 AI 工具之间进行人工调度的成本。用户只输入目标，平台负责组织上下文、分派 AI、保存回答、比较结论、生成 patch、沙盒验证、读取 PR/CI/Sonar 信号、自动复盘并提出改进建议；用户只做最终判断。

## Core Pain Points

当前用户的主要痛点包括：

- 在多个 AI 工具之间反复复制粘贴
- 每次都要重新解释项目背景
- 反复纠正 AI 忘记项目规则和安全边界
- 等待单个 AI 回答，无法并行推进
- 手动比较多个 AI 的答案
- 手动运行测试、整理 PR body、读取 CI/Sonar 结果
- 手动汇总风险、结论和下一步动作

因此，平台的目标是把用户从“人工调度员”转变为“最终决策者”。

## Product Role

平台应该负责：

- 组织项目上下文
- 生成 AI Context Packet
- 生成 Prompt Template Preview
- 管理 token budget 和 safety boundary
- 分派不同 AI / provider / mode
- 保存 AI 回答和 artifact
- 比较多个 AI 的结论
- 汇总一致点、分歧点和风险
- 生成 patch 并进入 sandbox 验证
- 读取验证结果和质量信号
- 给出下一步建议

用户只负责最终判断：继续追问、采纳、丢弃、返工、创建 PR、合入、tag 或 release。

## Existing Foundation

已有模块不废弃，而是作为个人工作台底座继续演进：

- Project / Task
- AgentRun
- Code Context
- Context Selector
- AI Context Packet
- Prompt Template
- TaskArtifact
- AI Output Governance
- Patch Sandbox
- Sandbox Gate
- Review Packet
- ApprovalDecision
- AGENTS.md / Harness
- Release notes / reports

这些能力的叙事从“企业交付流水线”调整为“个人多 AI 调度、上下文复用、自动验证、项目记忆、自动复盘”。

## Priority

第一优先级不是 Browser AI，也不是自动创建 PR，而是打通个人工作台的最短闭环：

```text
用户输入任务
-> 平台拆分问题
-> 多个 AI 分工回答
-> 保存回答
-> 自动汇总结论
-> 自动验证
-> 用户决策
```

因此 S12-S15 应优先完成：

1. Dispatch Batch / Routed Jobs
2. Multi-AI Answer Workspace
3. Answer Synthesizer
4. Project Memory
5. Local Verification Runner

Browser AI、GitHub PR Adapter、Auto Repair、自我进化应作为后续增强能力，在核心闭环稳定后再推进。

## Non-Goals

个人工作台不是无人值守生产交付系统。默认不做：

- 不自动 merge
- 不自动 deploy
- 不自动 approve high / critical risk
- 不自动 approve human_required
- 不绕过 CI/Sonar
- 不为了通过测试放宽断言
- 不为了通过 Sonar 删除关键逻辑
- 不保存 API key、cookie、password、session

所有真实外部动作必须可审计，并由用户确认。
