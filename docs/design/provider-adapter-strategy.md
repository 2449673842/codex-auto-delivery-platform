# Provider Adapter Strategy

个人多 AI 编码工作台需要支持多类 provider，但应按阶段推进，不能过早把 Browser AI、CLI Agent、PR Adapter、CI Adapter 混进核心路径。

## Provider Categories

### API Provider

通过正式 API 调用模型。

候选：

- OpenAI
- Claude API
- Gemini API
- DeepSeek
- Local model

API Provider 的输出统一转成 AgentRunResult、TaskArtifact 和 DispatchJob output。

### Browser Provider

通过用户授权的网页 AI 工具读取回答。

候选：

- ChatGPT Web
- Claude Web
- Gemini Web
- Perplexity

第一版安全边界：

- 用户主动授权登录
- 不保存明文 cookie / password / session
- 不绕过 CAPTCHA / 2FA / rate limit
- 不调用隐藏接口作为正式主线
- 只读取可见网页回答
- 回答转成 Artifact
- 所有操作可审计

Browser Provider 不应在 S12-S15 阶段成为主线依赖。

### CLI Provider

通过本地 CLI Agent 执行受控任务。

候选：

- Codex CLI
- Claude Code
- Gemini CLI
- Aider
- Cline

第一版安全边界：

- 命令白名单
- 用户确认执行
- 不自动运行危险命令
- 不自动 deploy
- 不读取 secret
- 日志脱敏
- 输出转成 Artifact

### Rule Provider

不调用 LLM，而是执行确定性规则或只读适配器。

候选：

- Governance
- Sandbox Gate
- Review Packet
- Local Verification Runner
- Sonar Read Adapter
- CI Read Adapter

Rule Provider 的结果也应作为 DispatchJob 或 synthesis 输入，以便统一展示。

## Unified Output

不同 provider 的输出应统一进入：

- DispatchJob status
- AgentRun 或后续等价运行记录
- TaskArtifact
- token usage 或 cost metadata
- raw provider trace 的 redacted 版本
- safety / governance result

## Adapter Contract

每个 provider adapter 至少应返回：

- provider
- model 或 tool name
- mode
- prompt_hash
- context_packet_hash
- status
- output_summary
- artifact references
- token usage 或 unavailable reason
- started_at / finished_at
- error_message
- redaction_applied

## Phased Adoption

建议顺序：

1. S11: OpenAI API Provider
2. S12: DispatchBatch / DispatchJob 数据结构
3. S13: 多回答工作台
4. S14: Answer Synthesizer
5. S15: Project Memory
6. S16: Browser AI / CLI Agent Adapter
7. S17: Local Verification Runner
8. S18-S19: GitHub PR / CI / Sonar 只读或受控 adapter

## Safety Defaults

所有 provider 默认遵守：

- 不读取 `.env`
- 不读取 `secret_ref`
- 不保存 API key / cookie / session
- 不访问真实项目目录进行写入，除非后续阶段单独设计并确认
- 不自动 merge
- 不自动 approve
- 不自动 deploy
- 所有真实外部动作必须可审计
