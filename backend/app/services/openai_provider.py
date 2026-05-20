"""OpenAI Provider — calls OpenAI API to generate structured AI outputs.

This provider:
- Calls OpenAI API (chat completions) to generate text
- Reads API key from OPENAI_API_KEY env var ONLY
- Does NOT read AgentProfile.secret_ref
- Does NOT execute shell/subprocess/os.system
- Does NOT access Project.root_path
- Does NOT create git commits/pushes
- Does NOT create GitHub PRs
- Does NOT call CI/Sonar APIs
- Does NOT log or expose the API key
"""

import json
import os
from datetime import timezone, datetime
from typing import Any

from app.models.agent_run import AgentRun
from app.schemas.ai_provider import AgentRunResult
from app.services.ai_provider_base import AiProviderBase
from app.enums import AgentRunType

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"


class OpenAIProvider(AiProviderBase):
    """Real AI provider using OpenAI chat completions API."""

    def __init__(self):
        self.api_key = os.environ.get(OPENAI_API_KEY_ENV)  # NOSONAR
        if not self.api_key:
            raise RuntimeError(
                f"OpenAI provider requires {OPENAI_API_KEY_ENV} environment variable. "
                "Set it before using real AI provider."
            )

    async def execute(self, run: AgentRun, code_context: dict | None = None) -> AgentRunResult:
        ts = datetime.now(timezone.utc).isoformat()
        run_type = run.run_type or AgentRunType.PLAN.value
        prompt = run.input_prompt or "No input provided"

        system_prompt, user_prompt = self._build_prompts(run_type, prompt, ts, code_context)

        try:
            response_text = await self._call_openai(system_prompt, user_prompt)
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {str(e)}") from e

        # Validate response is not empty - empty responses fail the AgentRun
        if not response_text or not response_text.strip():
            raise RuntimeError("AI returned empty response")

        try:
            result = self._parse_response(run_type, response_text, ts)
        except Exception:
            raise RuntimeError("Failed to parse AI response")

        return result

    def _build_prompts(self, run_type: str, prompt: str, ts: str,
                       code_context: dict | None = None) -> tuple[str, str]:
        """Build system and user prompts for the given run type.
        
        v0.4 S1: Includes code context files in EXECUTE prompt when available.
        code_context comes from TaskArtifacts, not from file system.
        """
        base_system = (
            "You are an AI code delivery assistant. "
            "Generate the requested output in a structured format. "
            "Do NOT include any explanations outside the requested format."
        )

        if run_type == AgentRunType.PLAN.value:
            return (
                base_system,
                f"Create an execution plan for the following task, output as markdown:\n\n{prompt}",
            )
        elif run_type == AgentRunType.EXECUTE.value:
            files_text = ""
            if code_context and code_context.get("files"):
                files_text = "\n\nHere are the relevant source files:\n"
                for f in code_context["files"]:
                    path = f.get("path", "unknown")
                    lang = f.get("language", "") or "text"
                    content = f.get("content", "")
                    files_text += f"\n### File: {path}\n```{lang}\n{content}\n```\n"
                files_text += "\nGenerate a unified diff (diff --git format) that modifies these files as needed. "
                files_text += "Output ONLY the diff, no extra commentary."

            user_prompt = (
                f"Generate a code change (as unified diff format) "
                f"for the following requirement:\n\n{prompt}"
            )
            if files_text:
                user_prompt += files_text
            return (base_system, user_prompt)
        elif run_type == AgentRunType.REVIEW.value:
            return (
                base_system,
                f"Review the following code/plan and provide feedback in markdown format, "
                f"including a decision (approved/rejected/changes_requested) and risk level (low/medium/high/critical):\n\n{prompt}",
            )
        else:
            return (
                "You are a code analysis assistant.",
                f"Process the following request and provide structured output:\n\n{prompt}",
            )

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI chat completions API.
        
        Uses OPENAI_API_KEY from environment. Never logs or exposes the key.
        """
        import httpx

        key = os.environ.get(OPENAI_API_KEY_ENV)  # NOSONAR
        if not key:
            raise RuntimeError(f"{OPENAI_API_KEY_ENV} not set")

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, run_type: str, text: str, ts: str) -> AgentRunResult:
        """Parse the AI response into structured AgentRunResult."""
        words = len(text.split())
        summary = text[:200].replace("\n", " ") + ("..." if len(text) > 200 else "")

        if run_type == AgentRunType.PLAN.value:
            return AgentRunResult(
                output_summary=f"AI-generated plan ({words} words): {summary}",
                output_log=f"[{ts}] AI provider generated plan ({words} words)",
                raw_result_json=json.dumps({"plan_md": text}, ensure_ascii=False),
                plan_md=text,
                risk_report={"risk_level": "low", "source": "openai", "summary": summary[:100]},
            )
        elif run_type == AgentRunType.EXECUTE.value:
            return AgentRunResult(
                output_summary=f"AI-generated code ({words} words): {summary}",
                output_log=f"[{ts}] AI provider generated code changes ({words} words)",
                raw_result_json=json.dumps({"patch_diff": text}, ensure_ascii=False),
                patch_diff=text,
            )
        elif run_type == AgentRunType.REVIEW.value:
            return AgentRunResult(
                output_summary=f"AI review ({words} words): {summary}",
                output_log=f"[{ts}] AI provider generated review ({words} words)",
                raw_result_json=json.dumps({"review_md": text}, ensure_ascii=False),
                review_md=text,
            )
        else:
            return AgentRunResult(
                output_summary=f"AI response ({words} words): {summary}",
                output_log=f"[{ts}] AI provider generated response ({words} words)",
                raw_result_json=json.dumps({"raw_response": text}, ensure_ascii=False),
            )
