# External AI Handoff Example

## 用途

本文档给外部 AI 一个最小接管模板。目标是让外部 AI 通过 S18 MCP Bridge 读取任务上下文，而不是让用户复制粘贴大段聊天记录。

当前 S18 MCP Bridge 仍是 REST debug endpoint，不是真正 MCP transport。外部 AI 需要通过 HTTP 调用：

```text
GET  /api/mcp/tools
POST /api/mcp/call
```

## 给下一个 AI 的 Prompt 模板

```text
你正在接手一个已有任务。不要假设你已经知道项目最新状态。

请先通过 MCP Bridge 读取上下文：

1. 调用 get_handoff_packet
   arguments:
   {
     "task_id": <TASK_ID>,
     "budget": 4000
   }

2. 读取并遵守 response.safety_notes。

3. 检查 response.persisted 必须是 false。

4. 如果 response.data.is_truncated=true，不要假设上下文完整。
   需要时继续调用：
   - get_task_brief
   - get_answer_synthesis
   - list_agent_runs
   - list_task_artifacts
   - get_sandbox_status

5. 行动前必须验证当前 master，不要只相信接管包里的历史 commit hint。

硬性安全边界：

- 不读取 .env
- 不读取 secret_ref
- 不返回 API key / cookie / session / password
- 不访问 Project.root_path 做真实扫描或修改
- 不执行 shell / subprocess，除非用户另行明确授权
- 不调用 OpenAI execute
- 不调用 Browser AI execute
- 不打开浏览器
- 不写真实仓库
- 不创建 GitHub PR
- 不调用 CI / Sonar / Deploy
- 不自动 approve / merge

你的输出应包括：

- 你读取到的 task summary
- 当前可用 evidence
- 缺失信息
- 下一步建议
- 你不会执行的危险动作
```

## 示例：读取 Handoff Packet

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_handoff_packet",
    "arguments": {
      "task_id": 123,
      "budget": 4000
    }
  }'
```

外部 AI 应优先检查：

```json
{
  "status": "succeeded",
  "read_only": true,
  "persisted": false,
  "safety_notes": []
}
```

如果 `status` 不是 `succeeded`，外部 AI 不应继续推断上下文，应向用户报告 blocked / failed reason。

## 示例：补充读取证据

### 读取任务摘要

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_task_brief",
    "arguments": {
      "task_id": 123,
      "budget": 2000
    }
  }'
```

### 读取综合结论

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_answer_synthesis",
    "arguments": {
      "task_id": 123,
      "budget": 3000
    }
  }'
```

### 读取运行记录

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "list_agent_runs",
    "arguments": {
      "task_id": 123,
      "budget": 3000
    }
  }'
```

### 读取产物摘要

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "list_task_artifacts",
    "arguments": {
      "task_id": 123,
      "budget": 3000
    }
  }'
```

## 推荐接管输出格式

```text
接管状态：
- MCP status:
- persisted:
- is_truncated:

任务摘要：
- task_id:
- title:
- current status:

已有证据：
- AgentRun:
- TaskArtifact:
- Answer Synthesis:
- Sandbox/Gate:

缺失信息：
-

下一步建议：
-

安全边界确认：
- 未读取 .env / secret_ref
- 未访问 Project.root_path 做真实修改
- 未调用 provider execute
- 未打开 Browser AI 浏览器
- 未写真实仓库
- 未创建 PR / CI / Sonar / Deploy
- 未自动 approve / merge
```

## 外部 AI 不应该做什么

外部 AI 不应把 MCP Bridge 当成执行器。S18 只允许读取上下文和 dry-run：

- 不要请求 execute shell
- 不要请求 create PR
- 不要请求 merge PR
- 不要请求 deploy
- 不要把 dry-run 结果当成真实执行结果
- 不要把 truncated context 当成完整事实

如果需要执行代码修改、验证或 PR 操作，应回到 Codex / human-controlled workflow，并保留人工确认。
