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
    fgroup = module.get("files", {})
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


def _parse_goal(task_goal: str) -> set:
    if not task_goal:
        return set()
    return set(task_goal.lower().strip().split())


def _match_by_module_name(modules: list[dict], module_name: str) -> list[dict]:
    if not module_name:
        return []
    target = module_name.lower()
    for m in modules:
        if m.get("name", "").lower() == target:
            return [m]
    return []


def _find_module_by_look_at(modules: list[dict], look_at: str) -> list[dict]:
    found = []
    low = look_at.lower()
    for m in modules:
        if low in m.get("name", "").lower():
            found.append(m)
            continue
        for path_list in m.get("files", {}).values():
            if isinstance(path_list, list) and any(low in p.lower() for p in path_list):
                found.append(m)
                break
    return found


def _match_by_task_type(
    modules: list[dict], hints: list[dict], task_type: str,
) -> tuple[list[dict], list[str]]:
    matched = []
    used_hints = []
    if not task_type:
        return matched, used_hints
    low = task_type.lower()
    for h in hints:
        if h.get("task_type", "").lower() == low:
            used_hints.append(h["task_type"])
            for look_at in h.get("look_at", []):
                matched.extend(_find_module_by_look_at(modules, look_at))
    return matched, used_hints


def _keyword_match(module: dict, tokens: set) -> bool:
    name = module.get("name", "").lower()
    desc = module.get("description", "").lower()
    apis = " ".join(module.get("api", [])).lower()
    name_parts = set(name.replace("_", " ").split())
    if tokens & name_parts:
        return True
    if tokens & set(name.split()):
        return True
    return any(t in desc or t in apis for t in tokens)


def _match_by_task_goal(modules: list[dict], tokens: set) -> list[dict]:
    if not tokens:
        return []
    return [m for m in modules if _keyword_match(m, tokens)]


def _deduplicate(modules: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for m in modules:
        n = m.get("name", "")
        if n not in seen:
            seen.add(n)
            result.append(m)
    return result


def _collect_hints(hints: list[dict], task_type: str, tokens: set) -> list[str]:
    used = set()
    for h in hints:
        ht = h.get("task_type", "").lower()
        if task_type and ht == task_type.lower():
            used.add(ht)
        if tokens and any(t in ht for t in tokens):
            used.add(ht)
    return sorted(used)


def _build_response(
    modules: list[dict], hints: list[dict], used_hints: list[str],
    body: ContextSelectorRequest, tokens: set,
) -> ContextSelectorResponse:
    all_files = []
    all_tests = []
    all_apis = []
    all_safety = []
    for m in modules:
        all_files.extend(_get_all_files(m))
        all_tests.extend(_get_tests(m))
        all_apis.extend(m.get("api", []))
        all_safety.extend(m.get("safety_notes", []))

    matched_schemas = [
        ContextSelectorMatch(
            name=m.get("name", ""),
            module_type=m.get("type", ""),
            description=m.get("description", ""),
            files=m.get("files", {}),
            api=m.get("api", []),
            safety_notes=m.get("safety_notes", []),
        )
        for m in modules
    ]

    all_hints_used = sorted(set(used_hints + _collect_hints(hints, body.task_type, tokens)))
    warnings = []
    if not modules:
        warnings.append("no_project_map_match")

    return ContextSelectorResponse(
        matched_modules=matched_schemas,
        recommended_files=sorted(set(all_files)),
        recommended_tests=sorted(set(all_tests)),
        recommended_api=sorted(set(all_apis)),
        safety_notes=sorted(set(all_safety)),
        task_hints_used=all_hints_used,
        confidence="high" if modules else "low",
        warnings=warnings,
    )


def preview(body: ContextSelectorRequest) -> ContextSelectorResponse:
    data = _load_repository_map()
    modules = data.get("modules", [])
    hints = data.get("task_hints", [])
    tokens = _parse_goal(body.task_goal)

    matched = _match_by_module_name(modules, body.module_name)
    task_matched, used = _match_by_task_type(modules, hints, body.task_type)
    matched.extend(m for m in task_matched if m not in matched)

    if not body.module_name and tokens:
        goal_matched = _match_by_task_goal(modules, tokens)
        matched.extend(m for m in goal_matched if m not in matched)

    unique = _deduplicate(matched)
    return _build_response(unique, hints, used, body, tokens)
