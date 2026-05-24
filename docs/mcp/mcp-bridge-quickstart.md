# S18 MCP Bridge Quickstart

## 当前定位

S18 MCP Bridge 是一个 **REST debug endpoint**，用于先验证 MCP tool contract、安全边界和返回结构。

它还不是真正的 MCP transport。也就是说，当前版本不是 stdio / SSE / streamable HTTP MCP server；外部 AI 需要先通过 HTTP 调用平台提供的 REST endpoint。真正 MCP transport 留到后续阶段评估。

## Endpoint

```text
GET  /api/mcp/tools
POST /api/mcp/call
```

统一返回结构：

```json
{
  "tool": "get_task_brief",
  "status": "succeeded",
  "data": {},
  "error_message": "",
  "read_only": true,
  "persisted": false,
  "safety_notes": []
}
```

所有 S18 tool 都必须满足：

- read-only 或 dry-run only
- `persisted=false`
- 不调用 OpenAI provider
- 不打开 Browser AI 浏览器
- 不创建 AgentRun / TaskArtifact / TaskEvent
- 不写真实仓库
- 不创建 GitHub PR / CI / Sonar / Deploy
- 不自动 approve / merge
- 不返回 API key / cookie / session / password
- 不读取 `.env` / `secret_ref`
- 不访问 `Project.root_path` 做真实扫描或修改

## 查看工具列表

```bash
curl http://127.0.0.1:8700/api/mcp/tools
```

当前 S18 tools：

- `get_workspace_status`
- `get_project_summary`
- `list_tasks`
- `get_task_brief`
- `get_handoff_packet`
- `get_answer_synthesis`
- `list_agent_runs`
- `list_task_artifacts`
- `get_sandbox_status`
- `ai_dispatch_dry_run`
- `browser_ai_dry_run`

## 调用示例

### get_task_brief

读取任务摘要，支持 `budget` 截断。

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_task_brief",
    "arguments": {
      "task_id": 1,
      "budget": 2000
    }
  }'
```

### get_handoff_packet

生成给下一个 AI 的接管包预览。该调用是 stateless preview，不写库。

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_handoff_packet",
    "arguments": {
      "task_id": 1,
      "budget": 4000
    }
  }'
```

### get_answer_synthesis

读取 rule-based Answer Synthesis preview，不调用 provider。

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_answer_synthesis",
    "arguments": {
      "task_id": 1,
      "budget": 3000
    }
  }'
```

### list_agent_runs

读取 AgentRun 摘要。不会返回完整 prompt 原文 secret。

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "list_agent_runs",
    "arguments": {
      "task_id": 1,
      "budget": 3000
    }
  }'
```

### list_task_artifacts

读取 artifact 摘要，不无限返回完整大内容。

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "list_task_artifacts",
    "arguments": {
      "task_id": 1,
      "budget": 3000
    }
  }'
```

### ai_dispatch_dry_run

只做 AI Dispatch dry-run，不调用 OpenAI provider，不写 AgentRun / TaskArtifact / TaskEvent。

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "ai_dispatch_dry_run",
    "arguments": {
      "task_goal": "Review the current task plan.",
      "module_name": "backend",
      "task_type": "review",
      "mode": "review"
    }
  }'
```

### browser_ai_dry_run

只做 Browser AI safety gate / prompt hash dry-run，不打开浏览器，不写库。

```bash
curl -X POST http://127.0.0.1:8700/api/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "browser_ai_dry_run",
    "arguments": {
      "project_id": 1,
      "task_id": 1,
      "provider": "custom",
      "target_url": "http://127.0.0.1:9999/mock-browser-ai",
      "prompt_source": "task_goal",
      "input_selector": "textarea[name=\"prompt\"]",
      "send_selector": "button[data-send]",
      "response_selector": "[data-answer]"
    }
  }'
```

## Token Budget

以下 tools 支持 `budget`：

- `get_task_brief`
- `get_handoff_packet`
- `get_answer_synthesis`
- `list_agent_runs`
- `list_task_artifacts`

当返回内容超过 budget 时，响应会包含：

```json
{
  "is_truncated": true,
  "truncated_reason": "response exceeded budget=4000"
}
```

外部 AI 不应假设返回内容完整。需要更多上下文时，应按 task / run / artifact 维度分次读取摘要。

## 安全检查清单

调用方在使用 MCP Bridge 结果前必须检查：

- `read_only=true`
- `persisted=false`
- `status` 是否为 `succeeded`
- `safety_notes`
- `is_truncated`
- `truncated_reason`

S18 的目标是给外部 AI 提供安全上下文出口，而不是提供执行入口。
