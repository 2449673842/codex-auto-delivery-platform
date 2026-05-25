# S20 Controlled Repair Loop with Codex 设计

## 1. 定位

Controlled Repair Loop 不是平台自动修代码，也不是无限返工器。它的定位是：

```text
平台收集失败证据
-> 多 AI 分析失败原因
-> 平台生成 repair packet
-> Codex / OMX 或用户执行修复
-> 平台记录 repair attempt 和验证结果
-> 用户保留最终确认权
```

这延续当前产品分工：

```text
Codex / OMX 负责执行
平台负责证据、记忆、审计、handoff、synthesis
Browser AI / Multi-AI Evidence Run 负责补充外部 AI 证据
```

S20 只做设计文档，不新增后端、前端、API、数据库、execute 或自动返工能力。

## 2. 为什么不完全舍弃自动重修

失败后的人工成本主要不是“改一行代码”，而是整理证据：

- 哪个步骤失败
- 失败命令是什么
- stdout / stderr 哪段最关键
- 哪个 AgentRun 或 artifact 产生了风险
- 哪个 sandbox gate / CI / Sonar / review 结论拦住了合入
- 多个 AI 对原因是否一致
- 下一次修复应该验证什么

这些工作适合平台做，因为平台已经保存 Task、AgentRun、TaskArtifact、TaskEvent、DispatchBatch、DispatchJob、Answer Synthesis、Sandbox/Gate、MCP handoff 和 Multi-AI Evidence Run 的结构化记录。

因此，repair loop 的价值是自动整理失败上下文和修复建议，而不是让平台自己无限改代码。

## 3. 为什么不能做平台无限自动 repair

无限自动 repair 会扩大风险边界：

- 可能反复修改真实仓库
- 可能绕过用户对风险的判断
- 可能把测试失败误判成应该继续改代码
- 可能制造更大的 diff 或隐藏安全问题
- 可能诱导自动 PR / merge / deploy
- 可能把 Codex 已经擅长的执行能力在平台里重复实现成弱版

所以 Repair Loop 必须受控：

```text
max_attempts 默认 1
每次 attempt 都有 repair packet
每次 attempt 都有验证结果
用户可以停止
平台不自动写真实仓库
平台不自动创建 PR
平台不自动 approve / merge / deploy
```

## 4. Codex / OMX 的角色

Codex / OMX 是 repair loop 的执行者，而不是平台内部的子模块。

职责：

- 读取 repair packet
- 验证当前 master / base commit
- 读取 AGENTS.md 和项目约束
- 定位代码问题
- 修改代码
- 运行验证命令
- 汇报修复结果、失败原因和剩余风险
- 按用户或主脑要求创建或更新 PR

执行前必须：

- 验证当前 master，不信任旧 handoff hint
- 不读取 `.env`
- 不读取 `secret_ref`
- 不访问 `Project.root_path` 做未授权真实修改
- 不自动 merge / approve / deploy

## 5. 平台的角色

平台是 repair loop 的证据层和审计层。

职责：

- 从已有 Task / Run / Artifact / Event 中收集 failure evidence
- 组织 Multi-AI Evidence Run 分析失败
- 生成 repair packet
- 保存 repair attempt 记录
- 保存验证结果导入记录
- 在 Timeline / Evidence Board 中展示每一次 attempt
- 为 Codex / OMX / 外部 AI 输出 handoff prompt

平台不负责：

- 自动修改代码
- 写真实仓库
- 自动创建 PR
- 自动调用 CI / Sonar / Deploy
- 自动 approve / merge
- 绕过 Browser AI 登录或验证码

## 6. Browser AI / Multi-AI Evidence Run 的角色

Browser AI 是 evidence provider。它可以把 ChatGPT Web、Claude Web、Gemini Web、DeepSeek Web、Kimi Web 或 Custom 网页 AI 的回答采集成 AgentRun / TaskArtifact。

Multi-AI Evidence Run 是失败分析的组织方式：

- Broadcast：多个 AI 都分析同一个失败，比较一致结论和分歧
- Routed：不同 AI 分别分析日志、配置、前端、后端、测试、风险
- Pipeline：先诊断，再复审，再生成 repair packet
- Repair Loop：失败后组织证据和修复建议，由 Codex / 用户执行

S20 只设计这些关系，不实现自动 pipeline 或 repair execution。

## 7. 可触发 Repair Loop 的失败类型

第一版建议支持这些 failure_type：

- `sandbox_failed`
- `sandbox_gate_blocked`
- `verification_failed`
- `ci_failed`
- `sonar_failed`
- `review_blocked`
- `browser_ai_failed`
- `multi_ai_evidence_partial`

触发来源可以是：

- Patch Sandbox apply 失败
- Sandbox Gate blocked
- 本地验证命令失败
- CI 状态导入失败
- SonarCloud Quality Gate / issues / duplication / hotspots 异常
- 主脑或 AI review blocked
- Browser AI run failed / login required / selector failed
- Multi-AI Evidence Run partial / failed

注意：触发 repair loop 不等于自动执行修复。触发只意味着平台可以生成 failure evidence packet。

## 8. Failure Evidence Packet 格式

建议结构：

```json
{
  "task_id": 123,
  "project_id": 1,
  "failure_type": "sandbox_gate_blocked",
  "failed_step": "sandbox_gate",
  "failed_command_summary": "pytest backend/tests/test_x.py",
  "stdout_excerpt": "short redacted stdout excerpt",
  "stderr_excerpt": "short redacted stderr excerpt",
  "blocked_reasons": ["risk_high", "manual_review_required"],
  "related_agent_run_ids": [301],
  "related_artifact_ids": [401, 402],
  "related_dispatch_batch_id": 201,
  "related_dispatch_job_ids": [501, 502],
  "source_commit_hint": "verify_current_master_before_acting",
  "safety_notes": [
    "Do not read .env.",
    "Do not read secret_ref.",
    "Do not write the real repository from the platform."
  ],
  "redaction_status": {
    "redaction_applied": true,
    "truncated": true,
    "max_chars": 8000
  }
}
```

Rules：

- stdout / stderr 必须截断
- secrets 必须脱敏
- 不包含 cookie / session / password / API key
- 不包含未授权真实文件内容
- 不扫描 `Project.root_path`
- source commit 只是 hint，Codex / OMX 执行前必须重新验证当前 master

## 9. Repair Packet 格式

Repair packet 是给 Codex / OMX / 用户的可执行修复交接包，但它本身不执行代码。

建议结构：

```json
{
  "failure_summary": "Sandbox gate blocked because risk_high and missing verification evidence.",
  "suspected_root_causes": [
    "patch artifact lacks expected test coverage",
    "selector failure caused one Browser AI source to be missing"
  ],
  "evidence_by_source": [
    {
      "source": "sandbox_gate",
      "summary": "risk_high",
      "artifact_ids": [401]
    },
    {
      "source": "multi_ai_evidence_run",
      "summary": "2 providers agreed missing verification is the main risk",
      "dispatch_batch_id": 201
    }
  ],
  "multi_ai_findings": [
    "common finding 1",
    "common finding 2"
  ],
  "disagreements": [
    "Claude suspects frontend config; Gemini suspects backend fixture"
  ],
  "recommended_fix_strategy": "Make the smallest targeted patch and rerun backend pytest plus frontend smoke.",
  "files_likely_involved": [
    "backend/app/services/example.py",
    "backend/tests/test_example.py"
  ],
  "commands_to_verify": [
    "python -m pytest backend/tests/test_example.py -q --rootdir backend",
    "npm.cmd run build"
  ],
  "risks": [
    "Do not broaden scope into unrelated refactor.",
    "Do not weaken assertions."
  ],
  "human_decision_required": true,
  "codex_handoff_prompt": "Read AGENTS.md. Verify current master. Use this repair packet to make one narrow fix.",
  "max_attempts": 1,
  "do_not_do": [
    "do not read .env",
    "do not read secret_ref",
    "do not auto merge",
    "do not auto deploy",
    "do not bypass tests"
  ]
}
```

## 10. Repair Attempt 记录格式

Repair attempt 是审计记录，记录“这次返工如何被执行和验证”。第一版可设计为 TaskEvent + TaskArtifact，后续如需要再新增专门模型。

建议字段：

```json
{
  "repair_attempt_id": 1,
  "task_id": 123,
  "project_id": 1,
  "attempt_no": 1,
  "initiator": "user|codex|omx|system_preview",
  "executor": "codex",
  "failure_evidence_artifact_id": 801,
  "repair_packet_artifact_id": 802,
  "status": "planned|handoff_created|in_progress|verification_failed|verification_passed|stopped",
  "started_at": "2026-05-25T00:00:00Z",
  "finished_at": null,
  "verification_result_artifact_ids": [],
  "summary": "Codex received repair packet; user has not approved execution yet.",
  "safety_notes": [
    "max_attempts=1",
    "no automatic repository writes by platform"
  ]
}
```

Timeline 应展示：

- failure evidence generated
- repair packet generated
- Codex handoff copied / exported
- attempt started
- verification result imported
- attempt stopped / passed / failed

## 11. max_attempts 设计

默认：

```text
max_attempts = 1
```

原因：

- 防止平台形成无限自动返工
- 强制用户在第一次修复后重新判断风险
- 保持每个 attempt 可审计
- 避免失败后不断扩大 diff

后续可以允许用户显式设置更高值，但必须满足：

- 每次 attempt 前有人类确认
- 每次 attempt 后保存验证结果
- 用户可以随时停止
- 高风险 / critical 风险必须停止并等待人工判断

## 12. Human Confirmation 设计

用户确认点：

1. 是否根据 failure evidence 生成 repair packet
2. 是否把 repair packet 交给 Codex / OMX
3. Codex / OMX 修复后，是否导入验证结果
4. 是否允许下一次 attempt
5. 是否进入 PR / review 流程

页面文案必须避免暗示自动修复：

```text
Generate repair packet
Copy Codex handoff
Import verification result
Stop repair loop
```

不要出现：

```text
Auto fix repository
Auto create PR
Auto merge
Auto deploy
```

## 13. 安全边界

S20 和后续实现必须明确：

- 不实现自动代码修改
- 不写真实仓库
- 不创建 PR / CI / Sonar / Deploy
- 不自动 approve / merge / deploy
- 不读取 `.env`
- 不读取 `secret_ref`
- 不访问 `Project.root_path` 做真实修改
- 不保存账号 / 密码 / cookie / session
- 不绕过 Browser AI 登录 / 验证码
- 不调用隐藏 API
- 不做无限 repair loop
- `max_attempts` 默认 1
- 用户必须能停止 repair loop
- Codex / OMX 执行修复前必须验证当前 master

## 14. S21 / S22 后续落地建议

### S20.1 Failure Evidence Packet preview

先做只读 preview：

- 从已有 Task / AgentRun / Artifact / Dispatch / Sandbox / Synthesis 读取失败证据
- 返回 redacted / truncated packet
- 不写库或只允许显式保存为 artifact
- 不调用 provider
- 不执行 shell

### S20.2 Repair Packet generation using Multi-AI Evidence Run

用 S19 的 Broadcast / Routed 组织多 AI 分析失败：

- Broadcast：多个 provider 独立判断 root cause
- Routed：日志 / 配置 / 前端 / 后端 / 测试 / 风险分工
- 输出进入 Answer Synthesis
- 生成 repair packet artifact

### S20.3 Codex / OMX handoff for repair

输出 Codex handoff prompt：

- 当前 task
- failure evidence
- repair packet
- safety rules
- verification commands
- stop condition
- 必须验证当前 master

### S20.4 Repair Attempt Timeline

把 repair attempt 接入 Evidence Board / Run Timeline：

- attempt_no
- status
- executor
- packet artifacts
- verification result
- human decision

## 15. 非目标

S20 不做：

- 后端实现
- 前端实现
- API
- 数据库迁移
- execute
- 自动修复
- 自动 PR
- 自动 merge / deploy / approve

