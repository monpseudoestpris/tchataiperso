#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

usage() {
  cat <<'EOF'
Usage : ./scripts/start.sh [mode] [options]

Modes :
  (aucun)        Démarre l'application en production (Docker, arrière-plan)
  dev            Démarre en mode développement avec hot-reload (même BDD/uploads que la prod)
  local          Démarre API + Web en local sans conteneurs (via scripts/dev.sh)
  stop           Arrête les services sans supprimer les données
  logs [svc]     Suit les logs en direct (ex: logs clair-api)
  status         Affiche l'état des services

Options :
  --lan          Expose l'application sur le réseau local (http://<IP-LAN>:3001)
  -h, --help     Affiche cette aide

Exemples :
  ./scripts/start.sh
  ./scripts/start.sh --lan
  ./scripts/start.sh dev
  ./scripts/start.sh dev --lan
  ./scripts/start.sh stop
EOF
}

mode="prod"
lan_flag=()
extra_args=()

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    --lan)
      lan_flag=(--lan)
      ;;
    prod|dev|local|stop|logs|status)
      if [[ "$mode" != "prod" && "$mode" != "$arg" ]]; then
        echo "Erreur : plusieurs modes spécifiés ($mode et $arg)." >&2
        usage >&2
        exit 2
      fi
      mode="$arg"
      ;;
    *)
      extra_args+=("$arg")
      ;;
  esac
done

case "$mode" in
  prod)
    exec "$repo_dir/scripts/compose.sh" ${lan_flag[@]+"${lan_flag[@]}"} up --build -d --wait ${extra_args[@]+"${extra_args[@]}"}
    ;;
  dev)
    exec "$repo_dir/scripts/compose.sh" ${lan_flag[@]+"${lan_flag[@]}"} dev ${extra_args[@]+"${extra_args[@]}"}
    ;;
  local)
    exec "$repo_dir/scripts/dev.sh" ${lan_flag[@]+"${lan_flag[@]}"} ${extra_args[@]+"${extra_args[@]}"}
    ;;
  stop)
    exec "$repo_dir/scripts/compose.sh" stop ${extra_args[@]+"${extra_args[@]}"}
    ;;
  logs)
    exec "$repo_dir/scripts/compose.sh" logs -f ${extra_args[@]+"${extra_args[@]}"}
    ;;
  status)
    exec "$repo_dir/scripts/compose.sh" ps ${extra_args[@]+"${extra_args[@]}"}
    ;;
esac
