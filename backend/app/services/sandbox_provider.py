"""Sandbox AI Provider — generates simulated AI outputs without external calls.

This provider:
- Does NOT call external AI APIs
- Does NOT read secret_ref
- Does NOT execute shell/subprocess/os.system
- Does NOT access Project.root_path
- Does NOT write to project directories
- Does NOT create git commits/pushes
- Does NOT create GitHub PRs
- Does NOT call CI/Sonar APIs
"""

import json
from datetime import datetime, timezone
from app.models.agent_run import AgentRun
from app.schemas.ai_provider import AgentRunResult
from app.services.ai_provider_base import AiProviderBase
from app.enums import AgentRunType


class SandboxProvider(AiProviderBase):
    """Simulated AI provider that generates template-based outputs."""

    async def execute(self, run: AgentRun) -> AgentRunResult:
        ts = datetime.now(timezone.utc).isoformat()
        run_type = run.run_type or AgentRunType.PLAN.value
        prompt = run.input_prompt or "No input provided"
        title = f"Task #{run.task_id}"
        agent_name = f"Agent #{run.agent_id}"

        if run_type == AgentRunType.PLAN.value:
            return self._plan_result(prompt, title, agent_name, ts)
        elif run_type == AgentRunType.EXECUTE.value:
            return self._execute_result(prompt, title, agent_name, ts)
        elif run_type == AgentRunType.REVIEW.value:
            return self._review_result(prompt, title, agent_name, ts)
        elif run_type == AgentRunType.TEST.value:
            return self._test_result(prompt, title, agent_name, ts)
        else:
            return self._default_result(prompt, title, agent_name, ts)

    def _plan_result(self, prompt: str, title: str, agent: str, ts: str) -> AgentRunResult:
        plan_md = (
            f"# 执行计划: {title}\n\n"
            f"## 任务描述\n{prompt}\n\n"
            f"## 执行步骤\n"
            f"1. 分析需求\n"
            f"2. 设计实现方案\n"
            f"3. 编写代码\n"
            f"4. 运行测试\n"
            f"5. 提交审查\n\n"
            f"*由 {agent} 生成 · {ts}*"
        )
        risk_report = {"risk_level": "low", "risk_factors": [], "summary": "No risk factors identified"}
        return AgentRunResult(
            output_summary=f"Execution plan generated for: {prompt[:60]}",
            output_log="[Step 1/5] Analyzing requirements...\n[Step 2/5] Designing solution...\n[Step 3/5] Plan generated successfully.",
            raw_result_json=json.dumps({"plan_md": plan_md, "risk_report": risk_report}, ensure_ascii=False),
            plan_md=plan_md,
            risk_report=risk_report,
        )

    def _execute_result(self, prompt: str, title: str, agent: str, ts: str) -> AgentRunResult:
        patch_diff = (
            "diff --git a/src/example.py b/src/example.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/src/example.py\n"
            "@@ -0,0 +1,10 @@\n"
            "+def add(a: int, b: int) -> int:\n"
            "+    \"\"\"Add two numbers.\"\"\"\n"
            "+    return a + b\n"
        )
        return AgentRunResult(
            output_summary=f"Execution completed: {prompt[:60]}",
            output_log="[Step 1/5] Setting up environment...\n[Step 2/5] Writing code...\n[Step 3/5] Code written successfully.",
            raw_result_json=json.dumps({"patch_diff": patch_diff, "files_changed": ["src/example.py"]}, ensure_ascii=False),
            patch_diff=patch_diff,
        )

    def _review_result(self, prompt: str, title: str, agent: str, ts: str) -> AgentRunResult:
        review_md = (
            f"# 审查报告: {title}\n\n"
            f"## 审查结论\n**决策**: Approved\n**风险等级**: Low\n\n"
            f"## 审查意见\n"
            f"- 代码结构清晰\n"
            f"- 逻辑正确\n"
            f"- 无安全风险\n\n"
            f"*由 {agent} 审查 · {ts}*"
        )
        return AgentRunResult(
            output_summary=f"Review completed for: {prompt[:60]}",
            output_log="[Step 1/3] Loading code...\n[Step 2/3] Analyzing...\n[Step 3/3] Review completed.",
            raw_result_json=json.dumps({"decision": "approved", "risk_level": "low", "issues": []}, ensure_ascii=False),
            review_md=review_md,
        )

    def _test_result(self, prompt: str, title: str, agent: str, ts: str) -> AgentRunResult:
        return AgentRunResult(
            output_summary=f"Tests completed: all passed",
            output_log="[Step 1/3] Running tests...\n[Step 2/3] All 12 tests passed.\n[Step 3/3] Test coverage: 85%",
            raw_result_json=json.dumps({"tests_passed": True, "total": 12, "passed": 12, "failed": 0, "coverage": 85.0}, ensure_ascii=False),
        )

    def _default_result(self, prompt: str, title: str, agent: str, ts: str) -> AgentRunResult:
        return AgentRunResult(
            output_summary=f"Agent executed: {prompt[:60]}",
            output_log=f"[{ts}] AgentRun started\n[{ts}] Completed",
            raw_result_json=json.dumps({"status": "completed", "run_type": "unknown"}, ensure_ascii=False),
        )
