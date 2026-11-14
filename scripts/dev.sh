#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
if [[ ! -x backend/.venv/bin/uvicorn || ! -d frontend/node_modules ]]; then
  echo 'Exécutez ./scripts/install.sh --local au préalable.' >&2
  exit 1
fi
if command -v docker >/dev/null 2>&1; then
  # Libère les ports 8001/3001 si la stack Docker complète tournait, puis démarre DB + SearXNG + Hermes.
  ./scripts/compose.sh stop clair-api clair-web >/dev/null 2>&1 || true
  ./scripts/compose.sh up --detach --wait --wait-timeout 120 clair-db clair-searxng clair-hermes
fi
web_host=127.0.0.1
if [[ "${1:-}" == --lan ]]; then
  # shellcheck source=scripts/lan.sh
  source "$repo_dir/scripts/lan.sh"
  enable_lan_mode
  web_host=0.0.0.0
  printf 'Local : http://localhost:3001 — Réseau local : %s\n' "$LAN_URL"
fi
backend_pid=''
frontend_pid=''
mcp_bridge_pid=''
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$mcp_bridge_pid" ]] || kill "$mcp_bridge_pid" 2>/dev/null || true
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
if command -v docker >/dev/null 2>&1; then
  docker_gw="$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || docker network inspect tchataiperso_default -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)"
  if [[ -n "$docker_gw" && "$docker_gw" != "127.0.0.1" ]]; then
    (
      exec "$repo_dir/backend/.venv/bin/python" -c "
import asyncio, sys
gw = sys.argv[1]
async def pipe(r, w):
    try:
        while chunk := await r.read(65536):
            w.write(chunk)
            await w.drain()
    except Exception:
        pass
    finally:
        w.close()
async def handle(cr, cw):
    try:
        sr, sw = await asyncio.open_connection('127.0.0.1', 8001)
    except Exception:
        cw.close()
        return
    await asyncio.gather(pipe(cr, sw), pipe(sr, cw))
async def main():
    srv = await asyncio.start_server(handle, gw, 8001)
    async with srv:
        await srv.serve_forever()
asyncio.run(main())
" "$docker_gw"
    ) &
    mcp_bridge_pid=$!
  fi
fi
(
  cd backend
  exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --env-file "$repo_dir/.env"
) &
backend_pid=$!
(
  cd frontend
  export BACKEND_URL=http://127.0.0.1:8001
  exec node node_modules/next/dist/bin/next dev --hostname "$web_host" --port 3001
) &
frontend_pid=$!
wait -n "$backend_pid" "$frontend_pid"
