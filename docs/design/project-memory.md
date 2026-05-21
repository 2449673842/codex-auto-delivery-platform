# Project Memory

Project Memory 的目标是减少用户反复解释项目背景，并让平台逐步了解每个项目的规则、命令、风险和偏好。

## Goals

Project Memory 应进入：

- Context Selector
- AI Context Packet
- Prompt Template
- Dispatch Routing
- Answer Synthesizer
- Local Verification Runner
- Run Retrospective
- Harness Improvement Suggestions

## Memory Fields

每个项目建议保存：

- project_name
- technical stack
- startup commands
- test commands
- build commands
- lint / typecheck commands
- ports
- important directories
- forbidden files
- user preferences
- provider preferences
- prompt preferences
- important tests
- common pitfalls
- historical failures
- historical successful fixes
- common Sonar issues
- common PR body issues

示例：

```json
{
  "project_name": "codex-auto-delivery-platform",
  "test_command": "python -m pytest backend/tests/ --rootdir backend",
  "compile_command": "python -m compileall backend/app",
  "frontend_build_command": "npm run build",
  "forbidden_files": [".env", "*.pem", "secret*"],
  "preferences": [
    "PR body 必须中文",
    "Sonar 未通过不能请求合入",
    "不能直接 push master",
    "测试不能放宽断言"
  ]
}
```

## Sources

Project Memory 可以来自：

- 用户手动配置
- AGENTS.md
- README / docs
- 历史 Task
- 历史 AgentRun
- 验证命令结果
- PR review blocker
- Sonar / CI 失败摘要
- Run Retrospective

自动提取的 memory 不应直接覆盖用户配置。高风险或可能改变行为的更新应作为建议，等待用户确认。

## Usage

在 Prompt Template 中：

- 注入项目约束
- 注入常用命令
- 注入禁止事项
- 注入用户偏好

在 Dispatch Routing 中：

- 选择更适合的 provider
- 决定是否需要 reviewer / risk / synthesizer
- 决定需要哪些验证命令

在 Answer Synthesizer 中：

- 对照项目规则判断 AI 回答是否可靠
- 标记违反项目边界的建议
- 给出更贴合项目的下一步动作

## Safety

Project Memory 禁止保存：

- API key
- password
- 明文 cookie
- 明文 session
- private key
- `.env` 内容
- `secret_ref` 内容

如果 AI 输出或验证日志中出现疑似 secret，必须先 redacted，再进入 memory 或 artifact。

## Evolution

Project Memory 应通过 S22/S23 逐步改进：

```text
Run Retrospective
-> Harness Improvement Suggestions
-> 用户确认
-> 更新 Project Memory
```

S24 之后可以生成受控的 harness improvement PR，但仍不得自动合入。
