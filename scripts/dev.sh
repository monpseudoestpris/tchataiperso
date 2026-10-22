#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
if [[ ! -x backend/.venv/bin/uvicorn || ! -d frontend/node_modules ]]; then
  echo 'Exécutez ./scripts/install.sh --local au préalable.' >&2
  exit 1
fi
backend_pid=''
frontend_pid=''
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
(
  cd backend
  exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --env-file "$repo_dir/.env"
) &
backend_pid=$!
(
  cd frontend
  export BACKEND_URL=http://127.0.0.1:8001
  exec node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3001
) &
frontend_pid=$!
wait -n "$backend_pid" "$frontend_pid"
