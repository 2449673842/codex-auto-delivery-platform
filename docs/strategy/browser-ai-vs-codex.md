# Browser AI 与 Codex 的分工

## 1. 结论

Browser AI 不是用来替代 Codex 的。Codex 是主要代码执行引擎，Browser AI 是网页 AI 答案采集器和 evidence provider。

平台也不应该变成弱版 Codex。平台的长期价值是：

```text
保存上下文
沉淀证据
比较多个 AI 输出
生成 Answer Synthesis
提供 handoff packet
形成审计记录和项目记忆
```

## 2. Codex 适合做什么

Codex 适合承担代码执行和本地工程操作：

- 阅读代码库
- 定位 bug
- 修改代码
- 运行测试、build、lint
- 执行固定 SOP
- 运行 Codex skill
- 根据 PR review 或 repair packet 修复问题
- 生成或更新文档和 PR body

这些工作需要本地文件系统、命令执行、代码理解和迭代修复能力。平台不应重新实现一个弱版执行器来和 Codex 竞争。

## 3. Browser AI 适合做什么

Browser AI 适合采集网页 AI 的可见回答：

- 打开用户配置的网页 AI
- 使用用户本地浏览器状态
- 让用户手动处理登录或验证码
- 填写 prompt
- 点击发送
- 等待回答稳定
- 读取 response_selector 的可见回答
- 保存 AgentRun / TaskArtifact
- 自动进入 Answer Synthesis

Browser AI 的核心价值是把网页 AI 中临时、分散、容易丢失的回答保存为平台证据。

## 4. 平台适合做什么

平台适合做长期状态和证据组织：

- Project / Task 管理
- AgentRun 历史
- TaskArtifact 归档
- TaskEvent 审计事件
- Browser AI answer 保存
- Answer Synthesis
- MCP handoff packet
- 未来 Evidence Board / Run Timeline
- 未来 Project Memory

这些能力需要数据库、UI、长期检索和跨任务关联。Skill 或一次性 Codex 会话不适合独立承担这部分。

## 5. 多网页 AI 的价值

用户使用多个网页 AI 时，最大成本通常不是“让 AI 回答”，而是：

```text
反复复制上下文
反复解释项目背景
手动粘贴 prompt
手动等待回答
手动复制结果
手动比较分歧
手动整理下一步
```

Browser AI + Evidence Run 的价值是减少这些重复动作：

```text
一次选择任务和 provider
平台自动采集多个回答
每个回答保存为 artifact
Answer Synthesis 比较共识和分歧
Codex 或用户根据综合结论执行
```

## 6. 为什么不要把 Browser AI 扩成自动代码执行器

网页 AI 的强项是回答问题和给出建议，不是可靠地修改本地仓库。把 Browser AI 扩成自动代码执行器会带来风险：

- 网页 AI 不能直接安全理解本地工作区状态
- 输出 patch 的格式和质量不可控
- 登录、验证码、页面变化会影响稳定性
- 很容易绕过当前平台的安全边界
- 会和 Codex 的核心能力重复

因此 Browser AI 应保持为 evidence provider：采集、保存、展示、综合网页 AI 的回答。

## 7. 为什么不要把平台做成弱版 Codex

弱版 Codex 的典型表现是：

- 平台自己实现复杂代码执行循环
- 平台自己跑任意 shell
- 平台自动修代码、自动重试、自动创建 PR
- 平台试图替代 Codex 的本地工程能力
- 平台缺少 Codex 的上下文、工具和修复迭代能力

这会让项目复杂度上升，但价值不如直接使用 Codex。

更清晰的分工是：

```text
Codex：执行者
Skill：流程 SOP
Browser AI：网页 AI evidence provider
平台：记忆层 / 证据层 / 审计层 / synthesis / handoff
```

## 8. 与 Multi-AI Evidence Run 的关系

Multi-AI Evidence Run 使用 Browser AI 不是为了让网页 AI 自动写代码，而是为了让多个 AI 参与判断：

- 同题多答：比较不同 AI 对同一问题的判断
- 分工协作：让不同 AI 分析不同方面
- 流水线接力：让一个 AI 的输出成为下一个 AI 的输入，先设计不急着实现
- 失败返工：生成 repair packet，交给 Codex 或用户执行

最终动作仍由 Codex 或用户控制。

## 9. 安全边界

Browser AI 和平台必须保持：

- 不自动登录
- 不保存账号 / 密码 / cookie / session
- 不绕过验证码
- 不调用隐藏 API
- 不写真实仓库
- 不创建 PR / CI / Sonar / Deploy
- 不自动 approve / merge
- 不读取 `.env` / `secret_ref`
- 不访问 Project.root_path 做真实修改

## 10. 后续建议

S19 应优先实现 Evidence Run 的 broadcast / routed 能力，并复用 Browser AI provider profiles、AgentRun、TaskArtifact 和 Answer Synthesis。

Pipeline 和 Repair Loop 先设计，不要急于实现。任何执行型能力优先考虑 Codex skill，只有当它需要长期证据留存、UI 展示或跨任务检索时，才进入平台。
