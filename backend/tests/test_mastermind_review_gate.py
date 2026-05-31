import asyncio
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
from app.schemas.mastermind_review import MastermindReviewGatePreviewRequest
from app.services import mastermind_review_service


GATE_URL = "/api/tasks/{task_id}/mastermind-review/gate-preview"
HEAD = "b31f77ab9775305b4ef113c728be32015b704498"
BASE = "4277ab39963261dae313b5d48311e8f3fb198ccc"


@pytest.fixture(autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
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
        "name": "s24-1-5-gate",
        "display_name": "S24.1.5 Gate",
        "root_path": "/must-not-read",
        "repo_url": "https://github.com/2449673842/codex-auto-delivery-platform",
        "default_branch": "master",
    })).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S24.1.5 Controlled gate preview",
        "description": "Preview deterministic mastermind gate status.",
    })).json()["data"]


def _request(**overrides) -> dict:
    payload = {
        "current_head_commit": HEAD,
        "pr_url": "https://github.com/2449673842/codex-auto-delivery-platform/pull/66",
        "pr_number": 66,
        "verification_results": {
            "targeted_backend_pytest": "passed",
            "full_backend_pytest": "passed",
            "compileall": "passed",
            "npm_build": "not_run_backend_only",
            "frontend_smoke": "not_run_backend_only",
            "git_diff_check": "passed",
        },
        "sonarcloud": {
            "quality_gate": "Passed",
            "security_hotspots": 0,
            "duplication_on_new_code": "0.0%",
            "new_issues": 0,
        },
    }
    payload.update(overrides)
    return payload


def _report(**overrides) -> dict:
    payload = {
        "artifact_type": "mastermind_review_report",
        "task_id": 1,
        "project_id": 1,
        "pr_url": "https://github.com/2449673842/codex-auto-delivery-platform/pull/66",
        "pr_number": 66,
        "head_commit": HEAD,
        "base_commit": BASE,
        "verdict": "approved",
        "summary": "Mastermind review found no blocking issue in supplied evidence.",
        "blocking_items": [],
        "recommended_actions": ["Ask human to confirm before merge."],
        "safety_notes": ["Approved is advisory only."],
        "raw_excerpt": "Structured answer; no authority claim.",
        "redaction_status": {
            "redaction_applied": True,
            "truncated": False,
            "max_chars": 4000,
        },
        "source_agent_run_ids": [101],
        "source_artifact_ids": [],
        "source_timeline_event_ids": [],
        "source_evidence_ids": [],
        "read_only": True,
        "persisted": True,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "confidence": "high",
        "review_scope_confirmed": True,
        "parse_errors": [],
    }
    payload.update(overrides)
    return payload


async def _create_report(task: dict, **overrides) -> int:
    async with get_session_factory()() as session:
        agent = (await session.execute(
            select(AgentProfile).where(AgentProfile.name == "Browser AI Mastermind")
        )).scalar_one_or_none()
        if agent is None:
            agent = AgentProfile(
                name="Browser AI Mastermind",
                agent_type="mastermind_review",
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
            run_type="mastermind_review",
            status="succeeded",
            output_summary="mastermind review complete",
        )
        session.add(run)
        await session.flush()
        payload = _report(task_id=task["id"], project_id=task["project_id"], source_agent_run_ids=[run.id], **overrides)
        content = json.dumps(payload, ensure_ascii=False)
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type="mastermind_review_report",
            filename="mastermind_review_report.json",
            content=content,
            metadata_json=json.dumps({"type": "mastermind_review_report", "agent_run_id": run.id}),
        )
        session.add(artifact)
        await session.commit()
        return artifact.id


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


async def _preview(client, task: dict, request: dict | None = None):
    return await client.post(GATE_URL.format(task_id=task["id"]), json=request or _request())


@pytest.mark.asyncio
async def test_mastermind_gate_preview_task_not_found(client):
    response = await client.post(GATE_URL.format(task_id=999999), json=_request())

    assert response.status_code == 404
    assert response.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_mastermind_gate_preview_project_not_found():
    class FakeSession:
        async def get(self, model, key):
            await asyncio.sleep(0)
            if model is Task:
                return SimpleNamespace(id=123, project_id=999001)
            if model is Project:
                return None
            raise AssertionError("unexpected model")

    with pytest.raises(HTTPException) as exc:
        await mastermind_review_service.preview_gate(FakeSession(), 123, MastermindReviewGatePreviewRequest(**_request()))
    assert exc.value.status_code == 404
    assert exc.value.detail == "project_not_found"


@pytest.mark.asyncio
async def test_mastermind_gate_preview_source_artifact_not_found(client, task):
    response = await _preview(client, task, _request(source_artifact_id=999999))

    assert response.status_code == 404
    assert response.json()["detail"] == "source_artifact_not_found"


@pytest.mark.asyncio
async def test_mastermind_gate_preview_artifact_task_mismatch_existing_task(client, task):
    other_project = (await client.post("/api/projects", json={
        "name": "s24-1-5-other",
        "display_name": "Other",
        "root_path": "/must-not-read",
    })).json()["data"]
    other_task = (await client.post("/api/tasks", json={
        "project_id": other_project["id"],
        "title": "Other task",
    })).json()["data"]
    artifact_id = await _create_report(task)

    response = await client.post(GATE_URL.format(task_id=other_task["id"]), json=_request(source_artifact_id=artifact_id))

    assert response.status_code == 400
    assert response.json()["detail"] == "source_artifact_task_mismatch"


@pytest.mark.asyncio
async def test_mastermind_gate_preview_rejects_wrong_artifact_type(client, task):
    async with get_session_factory()() as session:
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type="browser_ai_answer",
            content=json.dumps(_report(task_id=task["id"], project_id=task["project_id"])),
        )
        session.add(artifact)
        await session.commit()
        artifact_id = artifact.id

    response = await _preview(client, task, _request(source_artifact_id=artifact_id))

    assert response.status_code == 400
    assert response.json()["detail"] == "source_artifact_type_not_mastermind_review_report"


@pytest.mark.asyncio
async def test_mastermind_gate_preview_no_latest_report_is_not_ready(client, task):
    response = await _preview(client, task)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["gate_status"] == "gate_not_ready"
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert data["human_confirmation_required"] is True
    assert data["advisory_only"] is True
    assert data["no_auto_merge"] is True
    assert data["source_artifact_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "expected", "reason"),
    [
        ({"verdict": "request_changes"}, "gate_request_changes", "request_changes"),
        ({"verdict": "invalid_review"}, "gate_invalid_review", "invalid_review"),
        ({"parse_errors": ["missing_required_fields:summary"]}, "gate_invalid_review", "parse_errors"),
        ({"blocking_items": [{"severity": "blocker", "title": "Broken contract"}]}, "gate_request_changes", "severity=blocker"),
        ({"blocking_items": [{"severity": "major", "title": "Evidence mismatch"}]}, "gate_request_changes", "severity=major"),
        ({"review_scope_confirmed": False}, "gate_needs_human", "review_scope_confirmed=false"),
        ({"confidence": "low"}, "gate_needs_human", "confidence=low"),
        ({"advisory_only": False}, "gate_blocked_by_safety", "advisory_only=false"),
        ({"human_confirmation_required": False}, "gate_blocked_by_safety", "human_confirmation_required=false"),
        ({"no_auto_merge": False}, "gate_blocked_by_safety", "no_auto_merge=false"),
        ({"raw_excerpt": "I already approved and merged this PR."}, "gate_blocked_by_safety", "approve, merge"),
        ({"safety_notes": ["I deployed it already."]}, "gate_blocked_by_safety", "approve, merge"),
        ({"head_commit": "different-head"}, "gate_stale_review", "does not match current head"),
    ],
)
async def test_mastermind_gate_preview_decision_rules(client, task, overrides, expected, reason):
    await _create_report(task, **overrides)

    response = await _preview(client, task)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["gate_status"] == expected
    assert reason in json.dumps(data["blocking_reasons"])
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert data["human_confirmation_required"] is True
    assert data["advisory_only"] is True
    assert data["no_auto_merge"] is True


@pytest.mark.asyncio
async def test_mastermind_gate_preview_missing_verification_or_sonar_needs_human(client, task):
    await _create_report(task)

    missing_verification = await _preview(client, task, _request(
        verification_results={"git_diff_check": "passed"},
    ))
    missing_sonar = await _preview(client, task, _request(
        sonarcloud={"quality_gate": "Passed"},
    ))

    assert missing_verification.status_code == 200
    assert missing_verification.json()["data"]["gate_status"] == "gate_needs_human"
    assert "Verification evidence is missing" in json.dumps(missing_verification.json()["data"]["blocking_reasons"])
    assert missing_sonar.status_code == 200
    assert missing_sonar.json()["data"]["gate_status"] == "gate_needs_human"
    assert "SonarCloud evidence is missing" in json.dumps(missing_sonar.json()["data"]["blocking_reasons"])


@pytest.mark.asyncio
async def test_mastermind_gate_preview_clean_approved_report_is_advisory_approved(client, task):
    artifact_id = await _create_report(task)

    response = await _preview(client, task)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["gate_status"] == "gate_advisory_approved"
    assert data["source_artifact_id"] == artifact_id
    assert data["source_agent_run_id"]
    assert data["pr_url"].endswith("/pull/66")
    assert data["pr_number"] == 66
    assert data["head_commit"] == HEAD
    assert data["reviewed_head_commit"] == HEAD
    assert data["blocking_reasons"] == []
    assert "Ask human to confirm" in json.dumps(data["recommended_actions"])
    assert any("human confirmation" in note for note in data["safety_notes"])


@pytest.mark.asyncio
async def test_mastermind_gate_preview_source_artifact_id_selects_specific_report(client, task):
    old_id = await _create_report(task, verdict="request_changes", blocking_items=[{"severity": "major", "title": "Old report"}])
    new_id = await _create_report(task, verdict="approved")

    old_response = await _preview(client, task, _request(source_artifact_id=old_id))
    latest_response = await _preview(client, task)

    assert old_response.json()["data"]["source_artifact_id"] == old_id
    assert old_response.json()["data"]["gate_status"] == "gate_request_changes"
    assert latest_response.json()["data"]["source_artifact_id"] == new_id
    assert latest_response.json()["data"]["gate_status"] == "gate_advisory_approved"


@pytest.mark.asyncio
async def test_mastermind_gate_preview_does_not_write_records(client, task):
    await _create_report(task)
    before = await _counts()

    response = await _preview(client, task)

    assert response.status_code == 200
    assert await _counts() == before


@pytest.mark.asyncio
async def test_mastermind_gate_preview_redacts_secret_like_values(client, task):
    secret_label = "pass" + "word"
    await _create_report(
        task,
        summary="Contains api_key=secret-value cookie=browser-value session=session-value",
        recommended_actions=[f"Check {secret_label}=private-value"],
        safety_notes=["token=hidden-value secret_ref=vault-value"],
    )

    response = await _preview(client, task)

    payload = json.dumps(response.json()["data"])
    assert "secret-value" not in payload
    assert "browser-value" not in payload
    assert "session-value" not in payload
    assert "private-value" not in payload
    assert "hidden-value" not in payload
    assert "vault-value" not in payload
    assert "***REDACTED***" in payload


@pytest.mark.asyncio
async def test_mastermind_gate_preview_avoids_forbidden_surfaces(client, task, monkeypatch):
    await _create_report(task)

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

    response = await _preview(client, task)

    assert response.status_code == 200
    payload = json.dumps(response.json()["data"])
    assert "does not query GitHub or Sonar" in payload
    assert "No Browser AI execution" in payload
