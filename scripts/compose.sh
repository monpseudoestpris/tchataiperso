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
exec docker compose "${compose_files[@]}" "$@"
