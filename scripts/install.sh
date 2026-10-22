#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ ! -f .env ]]; then
  python3 - <<'PY'
from pathlib import Path
import secrets
import os

target = Path('.env')
contents = Path('.env.example').read_text().replace(
    'POSTGRES_PASSWORD=replace-with-random-local-password',
    'POSTGRES_PASSWORD=' + secrets.token_hex(24),
).replace(
  'SEARXNG_SECRET=replace-with-random-searxng-secret',
  'SEARXNG_SECRET=' + secrets.token_hex(32),
)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as handle:
    handle.write(contents)
print('.env créé (mode démo, clés absentes).')
PY
fi

case "${1:-}" in
  --local)
    python3 -m venv backend/.venv
    export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$repo_dir/../.cache/pip}"
    export npm_config_cache="${npm_config_cache:-$repo_dir/../.cache/npm}"
    backend/.venv/bin/python -m pip install --requirement backend/requirements-dev.txt
    npm --prefix frontend ci --no-audit --no-fund
    echo 'Dépendances installées. Démarrage : ./scripts/dev.sh'
    ;;
  '')
    ./scripts/compose.sh version >/dev/null
    docker info >/dev/null
    ./scripts/compose.sh config --quiet
    ./scripts/compose.sh up --detach --wait --wait-timeout 180 clair-db
    ./scripts/compose.sh build clair-api
    ./scripts/compose.sh run --rm --no-deps clair-api python -m app.cli migrate-schema
    initial_admin="${INITIAL_ADMIN_USERNAME:-}"
    if [[ -z "$initial_admin" ]]; then
      read -r -p 'Identifiant du premier administrateur : ' initial_admin
    fi
    if [[ -z "$initial_admin" ]]; then
      echo 'Un identifiant administrateur est obligatoire.' >&2
      exit 2
    fi
    ./scripts/compose.sh run --rm --no-deps clair-api python -m app.cli create-admin --username "$initial_admin"
    read -r -p 'Compte administrateur propriétaire des anciennes données (laisser vide si aucune) : ' legacy_owner
    if [[ -n "$legacy_owner" ]]; then
      ./scripts/compose.sh run --rm --no-deps clair-api python -m app.cli migrate-legacy --owner "$legacy_owner"
    else
      ./scripts/compose.sh run --rm --no-deps clair-api python -m app.cli migrate-legacy
    fi
    ./scripts/compose.sh up --build --detach --wait --wait-timeout 180
    python3 scripts/smoke.py
    ;;
  *)
    echo 'Usage : ./scripts/install.sh [--local]' >&2
    exit 2
    ;;
esac
