# Repair Loop Roadmap

## 1. 总原则

Repair Loop 后续路线必须保持当前产品定位：

```text
Codex / OMX 负责执行修复
平台负责失败证据、repair packet、审计记录、handoff 和 synthesis
```

Repair Loop 不是平台自动写代码，也不是无限自动返工。

## 2. S20 — Controlled Repair Loop with Codex 设计

状态：设计文档阶段。

产物：

- `docs/design/controlled-repair-loop-with-codex.md`
- `docs/roadmap/repair-loop-roadmap.md`

范围：

- 设计 failure evidence packet
- 设计 repair packet
- 设计 repair attempt 记录
- 设计 human confirmation
- 设计 Codex / OMX handoff
- 明确安全边界

不做：

- 不写后端
- 不写前端
- 不新增 API
- 不新增数据库
- 不新增 execute
- 不实现自动返工

## 3. S20.1 — Failure Evidence Packet preview

目标：让平台能从已有记录中预览失败证据。

输入来源：

- Task
- AgentRun
- TaskArtifact
- TaskEvent
- DispatchBatch / DispatchJob
- Sandbox apply result
- Sandbox Gate result
- Answer Synthesis
- Multi-AI Evidence Run

输出：

- `failure_type`
- `failed_step`
- `failed_command_summary`
- stdout / stderr excerpt
- blocked reasons
- related run / artifact / dispatch ids
- safety notes
- redaction status

边界：

- preview 默认 read-only
- 不调用 provider
- 不打开 Browser AI
- 不执行 shell / subprocess
- 不读取 `.env` / `secret_ref`
- 不扫描或修改 `Project.root_path`

## 4. S20.2 — Repair Packet generation using Multi-AI Evidence Run

目标：用 S19 的 Multi-AI Evidence Run 分析失败原因，生成 repair packet。

可用形态：

- Broadcast：多个 AI 分析同一个失败
- Routed：按日志、配置、前端、后端、测试、风险分工
- Pipeline：先诊断，再复审，再生成 repair packet，先设计不急着实现

输出：

- failure summary
- suspected root causes
- evidence by source
- multi AI findings
- disagreements
- recommended fix strategy
- files likely involved
- commands to verify
- risks
- Codex handoff prompt
- do_not_do

边界：

- 不自动修改代码
- 不写真实仓库
- 不创建 PR
- 不自动 merge / deploy / approve

## 5. S20.3 — Codex / OMX handoff for repair

目标：把 repair packet 交给 Codex / OMX 或用户执行。

handoff 内容：

- 当前 task 摘要
- failure evidence packet
- repair packet
- safety rules
- recommended verification commands
- max_attempts
- stop condition
- current master verification requirement

Codex / OMX 执行前必须：

- 读取 AGENTS.md
- 验证当前 master
- 确认安全边界
- 只做 narrow fix
- 运行验证命令
- 回报结果和剩余风险

平台只负责导出 handoff，不直接执行修复。

## 6. S20.4 — Repair Attempt Timeline

目标：把 repair attempt 变成可审计的任务时间线。

Timeline 事件：

- failure evidence generated
- repair packet generated
- Codex / OMX handoff exported
- repair attempt started
- verification result imported
- repair attempt passed
- repair attempt failed
- repair loop stopped by user

Evidence Board 应展示：

- attempt_no
- failure_type
- repair_packet_artifact_id
- executor
- status
- verification result
- human decision

## 7. 暂缓

暂缓：

- 平台自动写真实仓库
- 自动 PR creation
- 自动调用 CI / Sonar / Deploy
- 自动多轮 repair execution
- pipeline repair executor

这些能力容易把平台重新做成弱版 Codex，必须等 Evidence Board / Timeline / Project Memory 价值稳定后再评估。

## 8. 禁止

禁止：

- 自动 merge
- 自动 deploy
- 自动 approve
- 无限 repair loop
- 绕过测试
- 读取 `.env`
- 读取 `secret_ref`
- 保存账号 / 密码 / cookie / session
- 绕过 Browser AI 登录 / 验证码
- 调用隐藏 API

