"""Patch Apply Sandbox Service — applies unified diffs in-memory only.

This service:
- Parses unified diff format
- Applies patches on virtual (in-memory) file content from code context
- Generates changed files summary, before/after previews, sha256 checksums
- Creates TaskArtifacts for results
- No writes to real file system
- No shell execution or OS commands
- No git operations
- No external API calls (CI, Sonar, Deploy)
"""

import hashlib
import json
import re
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.task import Task
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.schemas.patch_sandbox import (
    ChangedFileEntry, PatchApplyReport, PatchApplyResult,
)
from app.services.event_service import create_event
from app.services.ai_output_governance_service import (
    validate_agent_run_result, redact_secrets,
    MAX_PATCH_SIZE_BYTES,
)

# ─── Unified Diff Parser ─────────────────────────────────

class HunkLine:
    def __init__(self, line_type: str, content: str, old_ln: int | None = None, new_ln: int | None = None):
        self.line_type = line_type  # ' ', '+', '-'
        self.content = content
        self.old_ln = old_ln
        self.new_ln = new_ln

class Hunk:
    def __init__(self, old_start: int, old_count: int, new_start: int, new_count: int):
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines: list[HunkLine] = []

class DiffFile:
    def __init__(self, old_path: str, new_path: str):
        self.old_path = old_path
        self.new_path = new_path
        self.hunks: list[Hunk] = []


def parse_unified_diff(diff_text: str) -> list[DiffFile]:
    """Parse a unified diff string into DiffFile objects."""
    files = []
    current_file = None
    current_hunk = None

    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            current_file = _parse_diff_git_line(line)
            current_hunk = None
            files.append(current_file)
        elif line.startswith("@@") and " @@" in line:
            if current_file is None:
                continue
            current_hunk = _parse_hunk_header(line)
            if current_hunk:
                current_file.hunks.append(current_hunk)
        elif current_hunk is not None:
            if line.startswith("+") or line.startswith("-") or line.startswith(" "):
                hunk_line = HunkLine(
                    line_type=line[0],
                    content=line[1:] if len(line) > 1 else "",
                )
                current_hunk.lines.append(hunk_line)
            # No-ops: ---, +++, new file mode, etc.

    return files


def _parse_diff_git_line(line: str) -> DiffFile:
    parts = line.split()
    old_path = parts[2][2:] if len(parts) > 2 else ""
    new_path = parts[3][2:] if len(parts) > 3 else ""
    return DiffFile(old_path, new_path)


def _parse_hunk_header(line: str) -> Hunk | None:
    m = re.match(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)  # NOSONAR - patch size limited to 500KB, low ReDoS risk
    if not m:
        return None
    old_start = int(m.group(1))
    old_count = int(m.group(2)) if m.group(2) else 1
    new_start = int(m.group(3))
    new_count = int(m.group(4)) if m.group(4) else 1
    return Hunk(old_start, old_count, new_start, new_count)


# ─── Patch Applicator ────────────────────────────────────

def _load_file_content(files: list[dict], path: str) -> str | None:
    """Find file content from code context by path."""
    for f in files:
        if f.get("path") == path or f.get("path") == f"b/{path}" or f.get("path") == f"a/{path}":
            return f.get("content", "")
    return None


def _apply_hunk(content_lines: list[str], hunk: Hunk) -> list[str]:
    """Apply a single hunk to content lines. Raises ValueError on context/deletion mismatch."""
    result = list(content_lines)

    pos = hunk.old_start - 1  # 0-indexed
    if pos < 0:
        pos = 0
    if pos > len(result):
        pos = len(result)

    result_final = list(result[:pos])
    content_idx = pos

    for hl in hunk.lines:
        if hl.line_type == " ":
            if content_idx < len(result) and result[content_idx] == hl.content:
                result_final.append(result[content_idx])
                content_idx += 1
            else:
                actual = result[content_idx] if content_idx < len(result) else "EOF"
                raise ValueError(
                    f"Context mismatch at line {content_idx}: "
                    f"expected '{hl.content}', got '{actual}'"
                )
        elif hl.line_type == "-":
            if content_idx < len(result) and result[content_idx] == hl.content:
                content_idx += 1
            else:
                actual = result[content_idx] if content_idx < len(result) else "EOF"
                raise ValueError(
                    f"Deletion mismatch at line {content_idx}: "
                    f"expected '{hl.content}', got '{actual}'"
                )
        elif hl.line_type == "+":
            result_final.append(hl.content)

    result_final.extend(result[content_idx:])
    return result_final


def _sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─── Public API ──────────────────────────────────────────

async def apply_patch_in_sandbox(
    db: AsyncSession, task_id: int, run_id: int,
) -> PatchApplyResult:
    """Apply patch.diff from an AgentRun onto code context in-memory.

    This is the main entry point. It:
    1. Loads the AgentRun and validates it
    2. Loads the latest code context for the task
    3. Parses the patch.diff from the AgentRun
    4. Applies each file diff to the corresponding virtual file
    5. Generates before/after content, sha256, and diff stats
    6. Creates TaskArtifacts for results
    7. Does NOT write any files, does NOT call git/CI/PR APIs
    """
    run = await db.get(AgentRun, run_id)
    if not run or run.task_id != task_id:
        raise HTTPException(status_code=404, detail="AgentRun not found for this task")
    if run.status != "succeeded":
        raise HTTPException(
            status_code=409,
            detail=f"AgentRun status is '{run.status}'; must be 'succeeded' to apply patch",
        )

    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(status_code=409, detail="Cannot apply patch to archived task")

    # Load patch.diff from the agent run's artifacts
    patch_diff = await _load_patch_diff(db, run)
    if not patch_diff:
        await create_event(
            db, task_id=task_id, event_type="patch_sandbox_failed",
            actor=f"patch_sandbox:run_{run_id}",
            message="No patch.diff found in AgentRun artifacts",
        )
        return PatchApplyResult(
            success=False,
            report=PatchApplyReport(
                applied=False, errors=["No patch.diff found in AgentRun artifacts"]
            ),
            message="No patch.diff available",
        )

    # Validate patch via governance
    validation = validate_agent_run_result(
        output_summary=run.output_summary or "",
        output_log=run.output_log or "",
        raw_result_json=run.raw_result_json,
        patch_diff=patch_diff,
    )
    if not validation.valid:
        await create_event(
            db, task_id=task_id, event_type="patch_sandbox_failed",
            actor=f"patch_sandbox:run_{run_id}",
            message="Patch failed governance validation",
        )
        return PatchApplyResult(
            success=False,
            report=PatchApplyReport(
                applied=False, errors=validation.errors, warnings=validation.warnings
            ),
            message="Patch failed governance validation",
        )

    if len(patch_diff.encode("utf-8")) > MAX_PATCH_SIZE_BYTES:
        await create_event(
            db, task_id=task_id, event_type="patch_sandbox_failed",
            actor=f"patch_sandbox:run_{run_id}",
            message="Patch too large",
        )
        return PatchApplyResult(
            success=False,
            report=PatchApplyReport(
                applied=False, errors=[f"Patch exceeds {MAX_PATCH_SIZE_BYTES} bytes"]
            ),
            message="Patch too large",
        )

    # Load code context
    result = await db.execute(
        select(TaskArtifact)
        .where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.artifact_type == "code_context_bundle",
        )
        .order_by(TaskArtifact.id.desc())
        .limit(1)
    )
    cc_artifact = result.scalar_one_or_none()
    code_context_files = []
    if cc_artifact and cc_artifact.content:
        try:
            bundle = json.loads(cc_artifact.content)
            code_context_files = bundle.get("files", [])
        except (json.JSONDecodeError, TypeError):
            pass

    # Build virtual file system
    virtual_fs: dict[str, str] = {}
    for f in code_context_files:
        path = f.get("path", "")
        if path:
            virtual_fs[path] = f.get("content", "")

    # Parse and apply diff
    try:
        diff_files = parse_unified_diff(patch_diff)
    except Exception:
        await create_event(
            db, task_id=task_id, event_type="patch_sandbox_failed",
            actor=f"patch_sandbox:run_{run_id}",
            message="Malformed patch.diff",
        )
        return PatchApplyResult(
            success=False,
            report=PatchApplyReport(
                applied=False, errors=["Failed to parse unified diff"]
            ),
            message="Malformed patch.diff",
        )

    if not diff_files:
        await create_event(
            db, task_id=task_id, event_type="patch_sandbox_failed",
            actor=f"patch_sandbox:run_{run_id}",
            message="No file diffs found in patch",
        )
        return PatchApplyResult(
            success=False,
            report=PatchApplyReport(
                applied=False, errors=["No file diffs found in patch"]
            ),
            message="Empty patch",
        )

    changed_files = []
    before_after_previews = {}
    apply_warnings = []
    apply_errors = []

    for df in diff_files:
        target_path = df.new_path if df.new_path and df.new_path != "/dev/null" else df.old_path
        if not target_path or target_path == "/dev/null":
            continue

        # Check for forbidden paths
        from app.services.ai_output_governance_service import _matches_forbidden
        if _matches_forbidden(target_path):
            apply_errors.append(f"Refusing to apply patch to forbidden path: {target_path}")
            continue

        # Get original content (or empty string for new files)
        orig_content = virtual_fs.get(target_path, "")
        orig_lines = orig_content.split("\n") if orig_content else []

        before_sha = _sha256_of_text(orig_content)

        # Apply all hunks for this file
        working_lines = list(orig_lines) if orig_lines else []
        all_hunks_applied = True
        for hunk in df.hunks:
            try:
                working_lines = _apply_hunk(working_lines, hunk)
            except Exception as e:
                all_hunks_applied = False
                apply_warnings.append(
                    f"Hunk @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@ "
                    f"failed to apply to {target_path}: {e}"
                )
                break

        if not all_hunks_applied:
            apply_errors.append(f"Hunk application failed for {target_path}")
            continue

        new_content = "\n".join(working_lines) if working_lines else ""
        after_sha = _sha256_of_text(new_content)

        # Calculate stats
        old_lines_set = set(orig_lines)
        new_lines_set = set(working_lines)
        additions = len(new_lines_set - old_lines_set)
        deletions = len(old_lines_set - new_lines_set)

        changed_files.append(ChangedFileEntry(
            path=target_path,
            status="modified" if orig_content else "added",
            additions=additions,
            deletions=deletions,
            before_sha256=before_sha,
            after_sha256=after_sha,
        ))

        # Store before/after (truncated for preview)
        before_after_previews[target_path] = {
            "before": orig_content,
            "after": new_content,
        }

    if not changed_files:
        await create_event(
            db, task_id=task_id, event_type="patch_sandbox_failed",
            actor=f"patch_sandbox:run_{run_id}",
            message="No changes applied in sandbox",
        )
        return PatchApplyResult(
            success=False,
            report=PatchApplyReport(
                applied=False, errors=apply_errors or ["No files were changed"],
                warnings=apply_warnings,
            ),
            message="No changes applied",
        )

    report = PatchApplyReport(
        applied=True,
        changed_files=changed_files,
        warnings=apply_warnings,
        errors=apply_errors,
    )

    # Create artifacts — sha256/size_bytes 基于 redacted content
    report_content = json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
    redacted_report = redact_secrets(report_content)
    report_sha = _sha256_of_text(redacted_report)

    art_report = TaskArtifact(
        task_id=task_id, artifact_type="patch_apply_report",
        content=redacted_report,
        filename=f"patch_apply_report_run_{run_id}.json",
        size_bytes=len(redacted_report.encode("utf-8")), sha256=report_sha,
    )
    db.add(art_report)

    summary_json = json.dumps({
        "changed_files": [
            {
                "path": cf.path, "status": cf.status,
                "additions": cf.additions, "deletions": cf.deletions,
            }
            for cf in changed_files
        ],
        "total_additions": sum(cf.additions for cf in changed_files),
        "total_deletions": sum(cf.deletions for cf in changed_files),
    }, ensure_ascii=False)
    redacted_summary = redact_secrets(summary_json)
    art_summary = TaskArtifact(
        task_id=task_id, artifact_type="changed_files_summary",
        content=redacted_summary,
        filename=f"changed_files_summary_run_{run_id}.json",
        size_bytes=len(redacted_summary.encode("utf-8")),
        sha256=_sha256_of_text(redacted_summary),
    )
    db.add(art_summary)

    for cf in changed_files:
        path = cf.path
        if path in before_after_previews:
            preview = before_after_previews[path]
            preview_content = json.dumps(preview, ensure_ascii=False)
            redacted_preview = redact_secrets(preview_content)
            art_preview = TaskArtifact(
                task_id=task_id, artifact_type="changed_file_preview",
                content=redacted_preview,
                filename=f"changed_file_preview_{path.replace('/', '_')}_run_{run_id}.json",
                size_bytes=len(redacted_preview.encode("utf-8")),
                sha256=_sha256_of_text(redacted_preview),
                metadata_json=json.dumps({"file_path": path, "status": cf.status}),
            )
            db.add(art_preview)

    await db.flush()
    await create_event(
        db, task_id=task_id, event_type="patch_sandbox_applied",
        actor=f"patch_sandbox:run_{run_id}",
        message=f"Patch sandbox applied: {len(changed_files)} file(s) changed",
    )

    return PatchApplyResult(
        success=True,
        report=report,
        message=f"Patch applied to {len(changed_files)} file(s) in sandbox",
        before_after_previews=before_after_previews,
    )


async def _load_patch_diff(db: AsyncSession, run: AgentRun) -> str | None:
    """Load patch.diff from AgentRun artifacts or output fields."""
    if run.output_diff:
        return run.output_diff

    result = await db.execute(
        select(TaskArtifact)
        .where(
            TaskArtifact.task_id == run.task_id,
            TaskArtifact.artifact_type.in_(["diff", "agent_output_diff"]),
            TaskArtifact.filename.like(f"%_run_{run.id}_%"),
        )
        .order_by(TaskArtifact.id.desc())
        .limit(1)
    )
    artifact = result.scalar_one_or_none()
    if artifact and artifact.content:
        return artifact.content

    if run.raw_result_json:
        try:
            parsed = json.loads(run.raw_result_json)
            patch = parsed.get("patch_diff") or parsed.get("output_diff")
            if patch:
                return patch
        except (json.JSONDecodeError, TypeError):
            pass

    return None


async def get_sandbox_results(
    db: AsyncSession, task_id: int
) -> list[dict]:
    """Retrieve all sandbox apply artifacts for a task."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(TaskArtifact)
        .where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.artifact_type.in_([
                "patch_apply_report", "changed_files_summary", "changed_file_preview",
            ]),
        )
        .order_by(TaskArtifact.created_at.desc())
    )
    artifacts = result.scalars().all()
    output = []
    for art in artifacts:
        output.append({
            "id": art.id,
            "artifact_type": art.artifact_type,
            "filename": art.filename,
            "content": art.content,
            "size_bytes": art.size_bytes,
            "sha256": art.sha256,
            "metadata_json": art.metadata_json,
            "created_at": art.created_at.isoformat() if art.created_at else None,
        })
    return output
