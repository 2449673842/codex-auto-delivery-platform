# Personal Workbench Roadmap

本路线图以 `master@a64eb7649b772a1c6ba10fb8f15088d76873a3c2` 之后的项目方向为基准。项目后续按“个人多 AI 编码工作台”推进，而不是只按“企业交付平台”推进。

## Completed Foundation

已完成：

- S8: Context Selector from Project Map
- S9: AI Context Packet Builder
- S10: Prompt Template Preview API
- S11: AI Dispatch + OpenAI Provider + Sandbox Auto Pipeline MVP

S11 完成后，已有主链路为：

```text
Prompt Template Preview
-> AI Dispatch
-> OpenAI Provider
-> AgentRunResult
-> Governance
-> TaskArtifact
-> Patch Sandbox
-> Sandbox Gate
```

## S11.5: Roadmap Docs

目标：通过纯文档 PR 统一产品定位、路线图、设计边界和后续阶段顺序。

范围：

- 只改文档
- 不改后端
- 不改前端
- 不改数据库
- 不新增 API
- 不新增真实外部调用

## S12: Dispatch Batch / Routed Jobs

目标：从单次 Dispatch 扩展为一个任务下多个 DispatchJob，避免系统被锁死为“一个 Task 只能调一个 AI”。

新增概念：

- DispatchBatch
- DispatchJob

第一版 API：

- `POST /api/dispatch-batches/preview`
- `POST /api/dispatch-batches/execute`
- `GET /api/tasks/{task_id}/dispatch-batches`

第一版支持：

- broadcast
- routed
- pipeline 的初始数据结构

## S13: Multi-AI Answer Workspace

目标：在 Task 页面中展示多个 AI 回答卡片，让用户不用在多个 AI 网页或 CLI 之间切换和复制粘贴。

每个回答卡片展示：

- provider
- model
- mode
- question
- status
- started_at / finished_at / duration
- token usage
- prompt_hash / context_packet_hash
- output summary
- artifact list
- errors / warnings
- 是否可继续追问

## S14: Answer Synthesizer

目标：自动汇总多个 AI 的回答。

输出：

- `answer_synthesis.md`
- `answer_synthesis.json`

内容：

- 一致结论
- 分歧点
- 主要风险
- 推荐动作
- 哪个 AI 的回答最有用
- 哪些回答冲突
- 是否需要继续追问
- 是否建议生成 patch
- 是否建议创建 PR
- 下一条给 AI 的指令

Synthesizer 不是最终裁决，只辅助用户判断。

## S15: Project Memory

目标：减少用户反复解释项目背景。

每个项目保存：

- 技术栈
- 启动命令
- 测试命令
- 构建命令
- 端口
- 重要目录
- 常见坑
- 禁止修改文件
- 用户偏好
- provider 偏好
- prompt 偏好
- 历史失败原因
- 历史成功修复

Project Memory 进入 Context Selector、AI Context Packet、Prompt Template、Dispatch Routing、Answer Synthesizer 和 Run Retrospective。

## S16: Browser AI / CLI Agent Adapter

目标：减少用户在网页 AI 和 CLI AI 工具之间复制粘贴。

Provider 分类：

- API Provider: OpenAI、Claude API、Gemini API、DeepSeek、Local model
- Browser Provider: ChatGPT Web、Claude Web、Gemini Web、Perplexity
- CLI Provider: Codex CLI、Claude Code、Gemini CLI、Aider、Cline
- Rule Provider: Governance、Sandbox Gate、Review Packet、Sonar Read Adapter、CI Read Adapter

第一版必须强调授权、审计和不保存明文 session。

## S17: Local Verification Runner

目标：自动跑验证，不再让 AI 只说“建议你运行测试”。

支持：

- pytest
- compileall
- npm build
- lint
- typecheck
- API health check
- frontend smoke test
- 页面截图
- 端口检查

命令必须来自 Project Memory 或用户配置，并需要用户确认。

## S18: GitHub PR Adapter

目标：当 sandbox 和 gate 通过后，经用户确认，一键创建真实 PR。

第一版允许：

- 创建 PR
- 更新 PR body
- 附带 Review Packet
- 附带 Sandbox Report
- 附带 AI Summary

第一版禁止：

- 不自动 merge
- 不自动 approve
- 不自动 deploy
- 不绕过 gate

## S19: CI / Sonar Read Adapter

目标：读取真实 PR 的检查结果，自动整理给用户。

读取：

- GitHub Checks
- GitHub Actions status
- SonarCloud Quality Gate
- Security Hotspots
- Duplication
- Coverage
- New Issues
- 失败日志摘要

第一版只读，不伪造状态、不绕过 Quality Gate、不主动 deploy。

## S20: Auto Repair Loop

目标：PR / CI / Sonar 失败后，自动进入返工循环。

流程：

```text
CI/Sonar failed
-> 生成失败摘要
-> AI Dispatch 生成修复方案
-> 生成 patch
-> Patch Sandbox
-> Sandbox Gate
-> 用户确认或自动更新 PR
-> 再读 CI/Sonar
```

禁止为了过测试放宽断言，禁止为了过 Sonar 删除关键逻辑。

## S21: Release / Tag / Docs Automation

目标：PR 合入后辅助收口。

支持：

- 生成 release notes
- 更新 README
- 更新 roadmap
- 更新 changelog
- 建议 tag
- 生成下一阶段任务

不自动发布生产，不自动 tag，除非用户确认。

## S22: Run Retrospective

目标：每次任务结束后自动复盘。

输出：

- `run_retrospective.json`
- `task_retrospective.md`
- `failure_summary.md`

复盘内容包括任务是否成功、失败在哪一步、哪个 AI 有用、哪个 prompt 太长、哪个上下文缺失、哪个安全边界被触发、主脑 blocker 是什么。

## S23: Harness Improvement Suggestions

目标：平台自动提出“下次如何做得更好”。

建议类型：

- 更新 prompt template
- 更新 Project Memory
- 更新 Context Selector 规则
- 更新 AGENTS.md checklist
- 新增测试模板
- 调整 provider routing
- 调整 token budget
- 新增常见失败模式

这一阶段只建议，不自动改。

## S24: Controlled Harness Evolution

目标：平台可以生成“改进自身”的 PR，但必须受控。

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

禁止放宽安全边界、关闭测试、绕过 Sonar、自动 merge 或自动 deploy。

## S25: Self-Improving Personal Workbench

最终形态：平台使用越多，越懂项目、用户偏好、AI 可靠性和常见失败模式。

平台最终能做到：

- 自动分派
- 自动汇总
- 自动验证
- 自动返工
- 自动复盘
- 自动提出改进 PR
- 用户最终确认
