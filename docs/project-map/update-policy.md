# Project Map Update Policy

> Rules for when and how to update `codebase-index.md` and `repository-map.json`.

---

## 1. Must Update

The Project Map **must** be updated when a PR introduces:

| Change | What to update |
|--------|---------------|
| New router file (`backend/app/routers/*.py`) | Add module entry with router path + API endpoints |
| New service file (`backend/app/services/*.py`) | Add module entry with service path |
| New schema file (`backend/app/schemas/*.py`) | Add module entry with schema path |
| New model file (`backend/app/models/*.py`) | Add module entry with model path |
| New test file (`backend/tests/*.py`) | Add to module's `tests` list |
| New API endpoint in existing router | Add to module's `api` list |
| New artifact type in `enums.py` | Update module's safety_notes or description |
| New event type in `enums.py` | Update module's description |
| New task status in `enums.py` | Update core module entries |
| New provider in `enums.py` | Add provider module entry |
| New frontend page (`frontend/src/pages/*.vue`) | Add frontend module entry |
| New frontend component (`frontend/src/components/*.vue`) | Add to module's components list |
| New frontend service (`frontend/src/services/*.ts`) | Add frontend module entry |
| New frontend store (`frontend/src/stores/*.ts`) | Add frontend module entry |
| New design doc (`docs/design/*.md`) | Add docs module entry |
| Safety boundaries updated in `AGENTS.md` | Update safety_boundary_files |
| Core module file deleted or renamed | Update or remove module entry |

---

## 2. Should Update (good practice)

| Change | Why |
|--------|-----|
| Significant modification to existing service logic | Description may need refresh |
| New task_hint discovered | Makes AI more efficient |
| Missing `file_roles` entries discovered | Improves coverage |

---

## 3. Not Required

| Change | Reason |
|--------|--------|
| Pure bugfix with no new file | No structural change |
| Typo fix | No structural change |
| Comment-only change | No structural change |
| Existing test file modified (no new test file) | No structural change |
| Frontend style-only change | No structural change |
| Dependency version bump | No structural change |
| Documentation typo fix | No structural change |

---

## 4. How to Update

### Adding a new module

1. Add entry to `repository-map.json` under `modules`:
   ```json
   {
     "name": "feature_name",
     "type": "backend_feature",
     "description": "What this module does",
     "files": { "router": [...], "service": [...], "schema": [...], "tests": [...] },
     "api": ["METHOD /path"],
     "safety_notes": [...]
   }
   ```

2. Add entry to `codebase-index.md` under the appropriate section.

### Updating an existing module

- Edit the `repository-map.json` module entry
- Update the `codebase-index.md` section

### Removing a module

- Remove from `repository-map.json` `modules` list
- Remove from `codebase-index.md` section

### Adding file roles

```json
"file_roles": {
  "backend/app/routers/new_feature.py": ["new feature endpoints"]
}
```

### Adding task hints

```json
{
  "task_type": "what kind of task",
  "look_at": ["paths or module names"],
  "what_to_do": ["brief guidance"]
}
```

---

## 5. PR Body Check

Every PR body must include:

```
Project Map updated: yes / no / not_needed
```

- `yes` — Project Map was updated as part of this PR
- `no` — Project Map should have been updated but was not (blocked by mastermind)
- `not_needed` — PR does not trigger any Must Update rule
