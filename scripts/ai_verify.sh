#!/usr/bin/env bash
# ai_verify.sh — Lightweight local verification entry for AI agent changes.
#
# Usage:
#   bash scripts/ai_verify.sh          # run all checks
#   bash scripts/ai_verify.sh --dry    # dry-run (show commands only)
#
# Safety:
#   - Does NOT access Project.root_path
#   - Does NOT read secret_ref / .env / tokens
#   - Does NOT execute dangerous commands
#   - Does NOT git push / commit / clone
#   - Does NOT call CI / Sonar / Deploy APIs
#   - Does NOT create PRs
#
# This is a LOCAL helper only. It is NOT a CI pipeline.

set -euo pipefail

DRY=false
if [[ "${1:-}" == "--dry" ]]; then
    DRY=true
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

run() {
    if $DRY; then
        echo "[DRY] $*"
    else
        echo "[RUN] $*"
        "$@"
    fi
}

echo "========================================"
echo " AI Verify — v0.4.0"
echo " Root: $ROOT_DIR"
echo " Mode: $($DRY && echo DRY || echo LIVE)"
echo "========================================"
echo ""

# 1. compileall — backend syntax check
echo "--- compileall (backend/app) ---"
run python -m compileall backend/app
echo ""

# 2. pytest — backend tests (quiet mode)
echo "--- pytest (backend/tests) ---"
run python -m pytest backend/tests/ -q --rootdir backend
echo ""

# 3. Frontend build hint (if frontend exists)
if [[ -d frontend ]]; then
    echo "--- frontend build ---"
    if $DRY; then
        echo "[DRY] cd frontend && npm install && npx vite build"
    else
        echo "[SKIP] Run manually: cd frontend && npm install && npx vite build"
    fi
    echo ""
fi

echo "========================================"
echo " Verify complete."
echo "========================================"
