# Personal User Flow

个人多 AI 编码工作台的目标流程是让用户只做最终判断，平台负责上下文、分派、记录、验证和汇总。

## Target Flow

```text
1. 用户打开工作台
2. 选择一个项目
3. 输入任务目标
4. 平台生成 Project Map / Context Selector / AI Context Packet / Prompt Preview
5. 平台建议任务拆分
6. 用户选择 AI / provider / mode
7. 平台创建 DispatchBatch 和 DispatchJob
8. 多个 AI 并行或串行执行
9. 每个 AI 的回答保存为 Artifact
10. 平台自动汇总一致结论、分歧点、风险和推荐动作
11. 如果生成 patch，进入 Governance / Patch Sandbox / Sandbox Gate / Local Verification
12. 用户最终选择继续追问、采纳、丢弃、创建 PR、返工或收口
```

## Example Tasks

用户可以输入：

- “帮我判断这个 PR 能不能合入”
- “帮我修这个报错”
- “帮我设计下一阶段路线”
- “让不同 AI 分别审查这几个问题”
- “把这个任务拆给多个 AI 看看”
- “跑完验证后告诉我风险”

## Workbench Layout

S13 的前端页面建议分为三栏。

左侧：

- task goal
- project memory summary
- context packet summary
- selected files
- safety notes
- token budget

中间：

- DispatchJob 卡片
- 每个 AI 的回答
- provider / model / mode
- status / duration
- artifact list
- errors / warnings

右侧：

- answer synthesis
- recommended actions
- sandbox result
- gate result
- verification result
- next steps

## Decision Actions

用户最终可以选择：

- 继续追问
- 采纳
- 丢弃
- 让另一个 AI 审查
- 生成 patch
- 进入自动返工
- 创建 GitHub PR
- 生成 release notes / tag 建议

任何真实外部动作都必须明确展示影响范围，并等待用户确认。

## Minimum Useful Loop

优先完成的最短闭环：

```text
用户输入任务
-> 平台拆分多个子问题
-> 多个 AI 分工回答
-> 保存回答
-> 自动汇总结论
-> 自动验证
-> 用户决策
```

Browser AI、GitHub PR Adapter、CI/Sonar Read Adapter、Auto Repair Loop 都应在这个闭环稳定后再推进。

## UX Principles

- 用户不应重复解释项目背景
- 用户不应手动复制粘贴上下文
- 用户不应手动汇总多个 AI 的回答
- 用户不应手动判断哪些验证命令需要运行
- 平台必须清晰展示 AI 的分歧和不确定性
- 平台不能把 Synthesizer 结论伪装成最终审批
- 平台必须保留人工最终判断
