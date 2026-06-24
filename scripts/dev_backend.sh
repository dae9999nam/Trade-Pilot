#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

# macOS can inherit malloc debug flags from Terminal/IDE sessions. Python may
# print noisy allocator diagnostics before the app starts, so keep the backend
# dev process on the normal allocator path unless explicitly launched by hand.
unset MallocStackLogging
unset MallocStackLoggingNoCompact
unset MallocStackLoggingDirectory

cd "$ROOT_DIR/backend"
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host "${BACKEND_HOST:-127.0.0.1}" --port "${BACKEND_PORT:-8000}"
