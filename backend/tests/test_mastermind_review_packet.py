import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.project import Project
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.mastermind_review import MastermindReviewPacketPreviewRequest
from app.services import mastermind_review_service


PACKET_URL = "/api/tasks/{task_id}/mastermind-review/packet-preview"


@pytest.fixture(autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as conn:
        for metadata_op in (Base.metadata.drop_all, Base.metadata.create_all):
            await conn.run_sync(metadata_op)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def task(client) -> dict:
    project = (await client.post("/api/projects", json={
        "name": "s24-1-1-mastermind",
        "display_name": "S24.1.1 Mastermind",
        "root_path": "/must-not-read",
        "repo_url": "https://github.com/2449673842/codex-auto-delivery-platform",
        "default_branch": "master",
        "current_branch": "feature/v0.4-s24-1-1-mastermind-review-packet-preview",
        "frontend_path": "frontend",
        "backend_path": "backend",
        "package_manager": "npm",
        "build_command": "npm.cmd run build",
        "test_command": "python -m pytest backend/tests/ -v --rootdir backend",
    })).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S24.1.1 Mastermind packet preview",
        "description": "Build read-only mastermind review packet preview.",
        "result_summary": "Preview API implemented without Browser AI execution.",
    })).json()["data"]


async def _counts() -> dict[str, int]:
    models = {
        "projects": Project,
        "tasks": Task,
        "runs": AgentRun,
        "artifacts": TaskArtifact,
        "events": TaskEvent,
        "batches": DispatchBatch,
        "jobs": DispatchJob,
    }
    async with get_session_factory()() as session:
        return {
            name: len((await session.execute(select(model))).scalars().all())
            for name, model in models.items()
        }


def _secret_fixture() -> str:
    names_and_values = [
        ("api_" + "key", "secret-value"),
        ("pass" + "word", "private-value"),
        ("to" + "ken", "hidden-value"),
        ("cook" + "ie", "browser-value"),
        ("ses" + "sion", "session-value"),
        ("secret" + "_ref", "vault-value"),
    ]
    return " ".join(f"{name}={value}" for name, value in names_and_values)


def _request(**overrides) -> dict:
    payload = {
        "pr_url": "https://github.com/2449673842/codex-auto-delivery-platform/pull/62",
        "pr_number": 62,
        "head_commit": "6613f0bcb86bcf81d444003ac44dbd3b906356b0",
        "base_commit": "f2f6f032cc4fcde4a163626030ef44344ee39354",
        "changed_files": [
            "docs/design/browser-ai-mastermind-review-trial.md",
            "docs/roadmap/next-after-s18.md",
        ],
        "pr_body": f"Docs-only PR body. {_secret_fixture()}",
        "verification_results": {
            "targeted_backend_pytest": "not_run_docs_only",
            "full_backend_pytest": "not_run_docs_only",
            "compileall": "not_run_docs_only",
            "npm_build": "not_run_docs_only",
            "frontend_smoke": "not_run_docs_only",
            "git_diff_check": "passed",
        },
        "sonarcloud": {
            "quality_gate": "Passed",
            "security_hotspots": 0,
            "duplication_on_new_code": "0.0%",
            "new_issues": 0,
        },
        "include_evidence_board": True,
        "include_timeline": True,
        "include_project_memory": True,
        "include_handoff_context": True,
        "packet_budget": 12000,
    }
    payload.update(overrides)
    return payload


def _request_model(**overrides) -> MastermindReviewPacketPreviewRequest:
    return MastermindReviewPacketPreviewRequest(**_request(**overrides))


async def _seed_context(task: dict) -> dict[str, int]:
    async with get_session_factory()() as session:
        agent = AgentProfile(
            name="Mastermind Context Agent",
            agent_type="browser_ai",
            provider="browser_ai",
            model_name="chatgpt_web",
            enabled=True,
        )
        session.add(agent)
        await session.flush()
        run = AgentRun(
            task_id=task["id"],
            project_id=task["project_id"],
            agent_id=agent.id,
            run_type="reviewer",
            status="succeeded",
            output_summary="Browser AI answer saved",
            raw_result_json=json.dumps({"safety_notes": ["No provider call."]}),
        )
        session.add(run)
        await session.flush()
        event = TaskEvent(
            task_id=task["id"],
            event_type="repair_attempt",
            actor="user",
            to_status="planned",
            message="Repair attempt planned",
            payload_json=json.dumps({"repair_attempt_id": None, "status": "planned"}),
        )
        session.add(event)
        await session.flush()
        event.payload_json = json.dumps({"repair_attempt_id": event.id, "status": "planned"})
        repair_packet = TaskArtifact(
            task_id=task["id"],
            artifact_type="repair_packet",
            filename="repair_packet.json",
            content=json.dumps({
                "failure_summary": f"Review blocked {_secret_fixture()}",
                "recommended_fix_strategy": "Make one narrow docs fix.",
            }),
            metadata_json=json.dumps({
                "type": "repair_packet",
                "summary": "Repair packet summary",
                "status": "completed",
            }),
        )
        repair_handoff = TaskArtifact(
            task_id=task["id"],
            artifact_type="repair_handoff",
            filename="repair_handoff.md",
            content="Handoff context for Codex.",
            metadata_json=json.dumps({
                "type": "repair_handoff",
                "summary": "Repair handoff summary",
                "status": "completed",
            }),
        )
        session.add_all([repair_packet, repair_handoff])
        await session.flush()
        batch = DispatchBatch(
            task_id=task["id"],
            batch_mode="broadcast",
            status="succeeded",
            task_goal="Collect review evidence",
            metadata_json=json.dumps({"type": "multi_ai_evidence_run"}),
            summary_json=json.dumps({"summary": "all reviewers agreed"}),
        )
        session.add(batch)
        await session.flush()
        job = DispatchJob(
            batch_id=batch.id,
            task_id=task["id"],
            sequence_no=1,
            question="Review PR evidence",
            provider="browser_ai",
            model="chatgpt_web",
            mode="reviewer",
            status="succeeded",
            agent_run_id=run.id,
            artifact_ids_json=json.dumps([repair_packet.id]),
            expected_artifact_type="repair_packet",
            metadata_json=json.dumps({"type": "multi_ai_evidence_job", "role": "reviewer"}),
        )
        session.add(job)
        await session.commit()
        return {
            "run": run.id,
            "event": event.id,
            "repair_packet": repair_packet.id,
            "repair_handoff": repair_handoff.id,
            "batch": batch.id,
            "job": job.id,
        }


@pytest.mark.asyncio
async def test_mastermind_packet_preview_task_not_found(client):
    response = await client.post(PACKET_URL.format(task_id=999999), json=_request())

    assert response.status_code == 404
    assert response.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_mastermind_packet_preview_project_not_found():
    class FakeSession:
        async def get(self, model, key):
            if model is Task:
                return SimpleNamespace(id=123, project_id=999001)
            if model is Project:
                return None
            raise AssertionError("unexpected model")

    with pytest.raises(HTTPException) as exc:
        await mastermind_review_service.preview_packet(FakeSession(), 123, _request_model())
    assert exc.value.status_code == 404
    assert exc.value.detail == "project_not_found"


@pytest.mark.asyncio
async def test_mastermind_packet_preview_contains_pr_verification_sonar_contract_and_safety(client, task):
    await _seed_context(task)

    response = await client.post(PACKET_URL.format(task_id=task["id"]), json=_request())

    assert response.status_code == 200
    data = response.json()["data"]
    packet = data["packet"]
    assert data["packet_type"] == "mastermind_review_packet"
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert data["redaction_status"]["redaction_applied"] is True
    assert data["redaction_status"]["max_chars"] == 12000
    assert packet["pr"]["url"].endswith("/pull/62")
    assert packet["pr"]["number"] == 62
    assert packet["pr"]["head_commit"] == "6613f0bcb86bcf81d444003ac44dbd3b906356b0"
    assert packet["pr"]["base_commit"] == "f2f6f032cc4fcde4a163626030ef44344ee39354"
    assert "docs/roadmap/next-after-s18.md" in packet["pr"]["changed_files"]
    assert packet["verification"]["git_diff_check"] == "passed"
    assert packet["sonarcloud"]["quality_gate"] == "Passed"
    assert packet["sonarcloud"]["security_hotspots"] == 0
    assert packet["sonarcloud"]["duplication_on_new_code"] == "0.0%"
    assert packet["sonarcloud"]["new_issues"] == 0
    assert packet["safety_boundary_checklist"]["read_only_preview"] is True
    assert packet["safety_boundary_checklist"]["browser_ai_execution"] is False
    assert packet["safety_boundary_checklist"]["auto_merge"] is False
    assert "Do not invent files" in packet["review_instruction"]
    assert "advisory only" in packet["review_instruction"]
    assert packet["required_output_contract"]["verdict"] == "approved | request_changes | needs_human | invalid_review"


@pytest.mark.asyncio
async def test_mastermind_packet_preview_includes_read_only_context_summaries(client, task):
    ids = await _seed_context(task)

    response = await client.post(PACKET_URL.format(task_id=task["id"]), json=_request())

    assert response.status_code == 200
    data = response.json()["data"]
    packet = data["packet"]
    assert "Task #" in packet["task_summary"]
    assert "/must-not-read" not in packet["task_summary"]
    assert "Evidence Board items:" in packet["evidence_board_summary"]
    assert "repair_packet" in packet["evidence_board_summary"]
    assert "Run Timeline items:" in packet["run_timeline_summary"]
    assert "repair_attempt" in packet["run_timeline_summary"]
    assert "memory_count=8" in packet["project_memory_summary"]
    assert "safety_policy" in packet["project_memory_summary"]
    assert "Repair handoff summary" in packet["handoff_context"]
    source_refs = data["source_refs"]
    assert {"source_type": "task", "id": task["id"], "path": None, "note": "Task summary source"} in source_refs
    assert any(ref["source_type"] == "evidence_board" for ref in source_refs)
    assert any(ref["source_type"] == "run_timeline" for ref in source_refs)
    assert any(ref["source_type"] == "project_memory" for ref in source_refs)
    assert any(ref["source_type"] == "repair_handoff" and ref["id"] == ids["repair_handoff"] for ref in source_refs)


@pytest.mark.asyncio
async def test_mastermind_packet_preview_include_flags_can_exclude_context(client, task):
    await _seed_context(task)

    response = await client.post(PACKET_URL.format(task_id=task["id"]), json=_request(
        include_evidence_board=False,
        include_timeline=False,
        include_project_memory=False,
        include_handoff_context=False,
    ))

    assert response.status_code == 200
    packet = response.json()["data"]["packet"]
    assert packet["evidence_board_summary"] == "not_included"
    assert packet["run_timeline_summary"] == "not_included"
    assert packet["project_memory_summary"] == "not_included"
    assert packet["handoff_context"] == "not_included"


@pytest.mark.asyncio
async def test_mastermind_packet_preview_redacts_secret_like_values(client, task):
    await _seed_context(task)

    response = await client.post(PACKET_URL.format(task_id=task["id"]), json=_request())

    payload = json.dumps(response.json()["data"])
    assert "secret-value" not in payload
    assert "private-value" not in payload
    assert "hidden-value" not in payload
    assert "browser-value" not in payload
    assert "session-value" not in payload
    assert "vault-value" not in payload
    assert "***REDACTED***" in payload


@pytest.mark.asyncio
async def test_mastermind_packet_preview_packet_budget_truncates(client, task):
    await _seed_context(task)

    response = await client.post(PACKET_URL.format(task_id=task["id"]), json=_request(
        pr_body="long body " * 500,
        packet_budget=1000,
    ))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["redaction_status"]["truncated"] is True
    assert data["redaction_status"]["max_chars"] == 1000
    assert "[truncated]" in json.dumps(data["packet"])


@pytest.mark.asyncio
async def test_mastermind_packet_preview_does_not_write(client, task):
    await _seed_context(task)
    before = await _counts()

    response = await client.post(PACKET_URL.format(task_id=task["id"]), json=_request())

    assert response.status_code == 200
    assert await _counts() == before


@pytest.mark.asyncio
async def test_mastermind_packet_preview_avoids_forbidden_surfaces(client, task, monkeypatch):
    await _seed_context(task)

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    for surface in [
        "pathlib.Path.glob",
        "pathlib.Path.rglob",
        "os.system",
        "subprocess.run",
        "subprocess.Popen",
        "app.services.browser_ai_service.execute",
        "app.services.ai_provider_service.dispatch_agent_run",
    ]:
        monkeypatch.setattr(surface, fail)

    response = await client.post(PACKET_URL.format(task_id=task["id"]), json=_request())

    assert response.status_code == 200
    payload = json.dumps(response.json()["data"])
    assert "No Browser AI mastermind review execution" in payload
    assert "does not query GitHub or Sonar" in payload
