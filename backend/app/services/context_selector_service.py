"""Context Selector Service — matches task descriptions to project modules.

Read-only service that consumes docs/project-map/repository-map.json.
No file system scanning, no Project.root_path access, no external calls.
"""

import json
from pathlib import Path

from fastapi import HTTPException

from app.schemas.context_selector import (
    ContextSelectorRequest,
    ContextSelectorMatch,
    ContextSelectorResponse,
)

_REPOSITORY_MAP_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs" / "project-map" / "repository-map.json"
)

_cache: dict | None = None


def _load_repository_map() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        raw = _REPOSITORY_MAP_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="repository-map.json not found")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"repository-map.json malformed: {e}")
    if "modules" not in data or not isinstance(data["modules"], list):
        raise HTTPException(status_code=500, detail="repository-map.json missing modules array")
    _cache = data
    return data


def _clear_cache():
    global _cache
    _cache = None


def _get_all_files(module: dict) -> list[str]:
    files = []
    for key in ("files",):
        fgroup = module.get(key, {})
        if isinstance(fgroup, dict):
            for path_list in fgroup.values():
                if isinstance(path_list, list):
                    files.extend(p for p in path_list if isinstance(p, str))
    return sorted(set(files))


def _get_tests(module: dict) -> list[str]:
    tests = []
    fgroup = module.get("files", {})
    if isinstance(fgroup, dict):
        for path_list in fgroup.values():
            if isinstance(path_list, list):
                tests.extend(p for p in path_list if isinstance(p, str) and "/tests/" in p)
    return sorted(set(tests))


def preview(body: ContextSelectorRequest) -> ContextSelectorResponse:
    data = _load_repository_map()
    modules = data.get("modules", [])
    hints = data.get("task_hints", [])
    goal_lower = body.task_goal.lower().strip() if body.task_goal else ""
    goal_tokens = set(goal_lower.split()) if goal_lower else set()

    matched_module_objs: list[dict] = []
    used_hints: list[str] = []

    # 1. Exact module_name match
    if body.module_name:
        for m in modules:
            if m.get("name", "").lower() == body.module_name.lower():
                matched_module_objs.append(m)
                break

    # 2. task_type match against task_hints
    if body.task_type:
        for h in hints:
            if h.get("task_type", "").lower() == body.task_type.lower():
                used_hints.append(h["task_type"])
                for look_at in h.get("look_at", []):
                    for m in modules:
                        m_name = m.get("name", "").lower()
                        if look_at.lower() in m_name:
                            if m not in matched_module_objs:
                                matched_module_objs.append(m)
                            continue
                        for path_list in m.get("files", {}).values():
                            if not isinstance(path_list, list):
                                continue
                            if any(look_at.lower() in p.lower() for p in path_list):
                                if m not in matched_module_objs:
                                    matched_module_objs.append(m)

    # 3. task_goal keyword matching
    if goal_tokens and not body.module_name:
        for m in modules:
            name = m.get("name", "").lower()
            desc = m.get("description", "").lower()
            apis = " ".join(m.get("api", [])).lower()
            name_parts = set(name.replace("_", " ").split())
            if goal_tokens & name_parts:
                if m not in matched_module_objs:
                    matched_module_objs.append(m)
                continue
            if goal_tokens & set(name.split()):
                if m not in matched_module_objs:
                    matched_module_objs.append(m)
                continue
            if any(t in desc or t in apis for t in goal_tokens):
                if m not in matched_module_objs:
                    matched_module_objs.append(m)

    # 4. Deduplicate by name
    seen = set()
    unique_modules: list[dict] = []
    for m in matched_module_objs:
        n = m.get("name", "")
        if n not in seen:
            seen.add(n)
            unique_modules.append(m)

    # Build response
    all_files: list[str] = []
    all_tests: list[str] = []
    all_apis: list[str] = []
    all_safety: list[str] = []

    for m in unique_modules:
        all_files.extend(_get_all_files(m))
        all_tests.extend(_get_tests(m))
        all_apis.extend(m.get("api", []))
        all_safety.extend(m.get("safety_notes", []))

    matched_schemas = [
        ContextSelectorMatch(
            name=m.get("name", ""),
            type=m.get("type", ""),
            description=m.get("description", ""),
            files=m.get("files", {}),
            api=m.get("api", []),
            safety_notes=m.get("safety_notes", []),
        )
        for m in unique_modules
    ]

    # Also look for task_hints for task_type or goal
    for h in hints:
        ht = h.get("task_type", "").lower()
        if body.task_type and ht == body.task_type.lower():
            if ht not in used_hints:
                used_hints.append(ht)
        if goal_tokens and any(t in ht for t in goal_tokens):
            if ht not in used_hints:
                used_hints.append(ht)

    warnings: list[str] = []
    confidence = "high" if unique_modules else "low"

    if not unique_modules:
        warnings.append("no_project_map_match")

    response = ContextSelectorResponse(
        matched_modules=matched_schemas,
        recommended_files=sorted(set(all_files)),
        recommended_tests=sorted(set(all_tests)),
        recommended_api=sorted(set(all_apis)),
        safety_notes=sorted(set(all_safety)),
        task_hints_used=sorted(set(used_hints)),
        confidence=confidence,
        warnings=warnings,
    )

    return response
