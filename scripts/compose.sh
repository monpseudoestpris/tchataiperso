#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
export BUILDX_CONFIG="${BUILDX_CONFIG:-$repo_dir/../.cache/buildx}"
export CLAIR_MCP_URL="${CLAIR_MCP_URL:-http://clair-api:8001/api/hermes/mcp}"
if [[ -f .env && ( -z "${SEARXNG_SECRET:-}" || -z "${HERMES_API_KEY:-}" ) ]]; then
  python3 - <<'PY'
from pathlib import Path
import secrets

target = Path('.env')
contents = target.read_bytes()
newline = b'\r\n' if b'\r\n' in contents else b'\n'
lines = contents.splitlines(keepends=True)
changed = False

def ensure_secret(key_name: bytes, token_bytes: int, placeholders: tuple[bytes, ...] = ()) -> None:
  global contents, lines, changed
  for index, line in enumerate(lines):
    key, separator, value = line.partition(b'=')
    if separator and key.strip() == key_name:
      clean = value.strip().strip(b"'\"")
      if clean and clean not in placeholders:
        return
      ending = b'\r\n' if line.endswith(b'\r\n') else b'\n'
      lines[index] = key_name + b'=' + secrets.token_hex(token_bytes).encode() + ending
      changed = True
      return
  if lines and not lines[-1].endswith((b'\n', b'\r')):
    lines[-1] += newline
  lines.append(key_name + b'=' + secrets.token_hex(token_bytes).encode() + newline)
  changed = True

ensure_secret(b'SEARXNG_SECRET', 32)
ensure_secret(b'HERMES_API_KEY', 24, placeholders=(b'replace-with-hermes-gateway-key',))
if changed:
  target.write_bytes(b''.join(lines))
PY
fi
lan_mode=false
args=()
for arg in "$@"; do
  if [[ "$arg" == --lan ]]; then lan_mode=true; else args+=("$arg"); fi
done
set -- ${args[@]+"${args[@]}"}
if [[ "$lan_mode" == true ]]; then
  # shellcheck source=scripts/lan.sh
  source "$repo_dir/scripts/lan.sh"
  enable_lan_mode
fi
compose_files=(-f compose.yaml)
if [[ "${1:-}" == dev ]]; then
  compose_files+=(-f compose.dev.yaml)
  shift
  set -- up --build --renew-anon-volumes "$@"
fi
if [[ -z "${CLOUD_CA_BUNDLE:-}" && -n "${SSL_CERT_FILE:-}" ]]; then
  export CLOUD_CA_BUNDLE="$SSL_CERT_FILE"
fi
if [[ -n "${CLOUD_CA_BUNDLE:-}" ]]; then
  if [[ ! -r "$CLOUD_CA_BUNDLE" ]]; then
    echo 'Le bundle CA configuré est introuvable ou illisible.' >&2
    exit 1
  fi
  # Certains clouds ne publient le nom du proxy que dans le réseau de l'hôte.
  # Ne transmet que son hostname et son IP aux entrées hosts des conteneurs.
  if [[ -n "${HTTPS_PROXY:-${HTTP_PROXY:-}}" && -z "${CLOUD_PROXY_IP:-}" ]]; then
    read -r CLOUD_PROXY_HOST CLOUD_PROXY_IP < <(python3 - <<'PY'
import os
import socket
from urllib.parse import urlsplit

host = urlsplit(os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY', '')).hostname
if host:
    print(host, socket.gethostbyname(host))
PY
)
    export CLOUD_PROXY_HOST CLOUD_PROXY_IP
  fi
  compose_files+=(-f compose.cloud.yaml)
fi
print_site_link() {
  local site_url='http://localhost:3001'
  printf '\ncLAIr — ouvrir le site : '
  if [[ -t 1 ]]; then
    # OSC 8 rend le lien cliquable dans les terminaux compatibles.
    printf '\033]8;;%s\033\\%s\033]8;;\033\\\n' "$site_url" "$site_url"
  else
    printf '%s\n' "$site_url"
  fi
  if [[ -n "${LAN_URL:-}" ]]; then
    printf 'Réseau local (autres machines) : %s\n' "$LAN_URL"
  fi
  printf 'Ctrl+clic sur le lien pour ouvrir le navigateur.\n'
}

link_timing=after
case "${1:-}" in
  up)
    link_timing=before
    for arg in "$@"; do
      case "$arg" in
        -d|--detach|--detach=true|--wait|--wait=true) link_timing=after ;;
      esac
    done
    ;;
  start|restart)
    for arg in "$@"; do
      case "$arg" in
        -a|--attach|--attach=true) link_timing=before ;;
      esac
    done
    ;;
  *) exec docker compose "${compose_files[@]}" "$@" ;;
esac

for arg in "$@"; do
  case "$arg" in
    -h|--help) exec docker compose "${compose_files[@]}" "$@" ;;
  esac
done

if [[ "${1:-}" == up ]]; then
  docker compose "${compose_files[@]}" down --remove-orphans
fi

if [[ "$link_timing" == before ]]; then
  # En mode attaché, conserver les logs et la gestion des signaux de Compose.
  print_site_link
  exec docker compose "${compose_files[@]}" "$@"
fi

docker compose "${compose_files[@]}" "$@"
print_site_link
