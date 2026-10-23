#!/usr/bin/env bash
# Mode réseau local (option --lan) : à sourcer depuis compose.sh ou dev.sh.
# Expose le frontend (port 3001) sur toutes les interfaces et autorise
# l'origine http://<IP-LAN>:3001. L'API reste liée à 127.0.0.1 : le proxy Next
# lui transmet les requêtes. LAN_IP permet de forcer l'adresse annoncée.

detect_lan_ip() {
  local ip=''
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
  fi
  if [[ -z "$ip" ]] && command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s' "$ip"
}

enable_lan_mode() {
  LAN_IP="${LAN_IP:-$(detect_lan_ip)}"
  if [[ -z "$LAN_IP" ]]; then
    echo "Adresse IP locale introuvable; définissez LAN_IP=192.168.x.y." >&2
    exit 1
  fi
  LAN_URL="http://$LAN_IP:3001"
  # Ajoute l'origine LAN aux origines déjà configurées (environnement ou .env).
  CORS_ORIGINS="$(python3 - "$LAN_URL" <<'PY'
import json
import os
import sys
from pathlib import Path

raw = os.environ.get('CORS_ORIGINS')
if raw is None and Path('.env').is_file():
    for line in Path('.env').read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip() == 'CORS_ORIGINS':
            raw = value
value = (raw or '').strip()
if len(value) >= 2 and value[0] == value[-1] and value[0] in '\'"':
    value = value[1:-1].strip()
origins = json.loads(value) if value.startswith('[') else [item.strip() for item in value.split(',') if item.strip()]
origins = origins or ['http://localhost:3001', 'http://127.0.0.1:3001']
if sys.argv[1] not in origins:
    origins.append(sys.argv[1])
print(json.dumps(origins))
PY
)"
  export LAN_IP LAN_URL CORS_ORIGINS
  export WEB_BIND=0.0.0.0
  export ALLOWED_DEV_ORIGINS="$LAN_IP"
}

