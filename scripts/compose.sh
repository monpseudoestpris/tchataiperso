#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
export BUILDX_CONFIG="${BUILDX_CONFIG:-$repo_dir/../.cache/buildx}"
compose_files=(-f compose.yaml)
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
  local site_url='http://localhost:3000'
  printf '\ncLAIr — ouvrir le site : '
  if [[ -t 1 ]]; then
    # OSC 8 rend le lien cliquable dans les terminaux compatibles.
    printf '\033]8;;%s\033\\%s\033]8;;\033\\\n' "$site_url" "$site_url"
  else
    printf '%s\n' "$site_url"
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

if [[ "$link_timing" == before ]]; then
  # En mode attaché, conserver les logs et la gestion des signaux de Compose.
  print_site_link
  exec docker compose "${compose_files[@]}" "$@"
fi

docker compose "${compose_files[@]}" "$@"
print_site_link
