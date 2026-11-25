#!/usr/bin/env bash
# Résolution canonique du fichier d'environnement cLAIr (externalisé hors du dépôt).
# Défaut : $HOME/.secrets/.env (surchargeable via CLAIR_ENV_FILE).

resolve_clair_env_file() {
  if [[ -z "${CLAIR_ENV_FILE:-}" ]]; then
    CLAIR_ENV_FILE="$HOME/.secrets/.env"
  fi
  export CLAIR_ENV_FILE
}
