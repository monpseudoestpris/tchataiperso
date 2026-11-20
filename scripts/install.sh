#!/usr/bin/env bash
# Script d'installation complet et idempotent pour cLAIr (tchataiperso).
# Prépare un PC neuf de bout en bout : prérequis système, .env, GCP ADC,
# assets SVG, dépendances Docker et/ou locales, migrations BDD et compte admin.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

# shellcheck source=scripts/install_lib/common.sh
source "$repo_dir/scripts/install_lib/common.sh"
# shellcheck source=scripts/install_lib/system.sh
source "$repo_dir/scripts/install_lib/system.sh"
# shellcheck source=scripts/install_lib/gcloud_setup.sh
source "$repo_dir/scripts/install_lib/gcloud_setup.sh"

usage() {
  cat <<'EOF'
Usage : ./scripts/install.sh [mode] [options]

Prépare et installe l'application cLAIr de zéro sur un nouveau PC (ou met à jour
une installation existante sans écraser .env ni les données).

Modes :
  --docker         Installation complète avec Docker Compose (défaut, recommandé)
  --local          Installation locale sans conteneurs app (Python 3.12+ venv + Node.js)
  --all, --full    Installe TOUT : Docker Compose + environnement dev local
  --check          Vérifie les prérequis et l'état du système sans rien modifier

Options :
  --lan            Démarre avec exposition sur le réseau local (http://<IP-LAN>:3001)
  --skip-system    Ne tente pas d'installer les paquets système (Docker, Python, Node, acl)
  --skip-gcloud    Ignore l'installation / authentification optionnelle Google Cloud CLI
  --skip-smoke     Ignore le smoke test final (scripts/smoke.py)
  -y, --yes        Mode non-interactif (accepte les installations système par défaut)
  -h, --help       Affiche cette aide

Variables d'environnement utiles en mode automatisé :
  INITIAL_ADMIN_USERNAME   Identifiant du premier administrateur
  SMOKE_USERNAME           Identifiant pour scripts/smoke.py
  SMOKE_PASSWORD           Mot de passe pour scripts/smoke.py
  LAN_IP                   Force l'IP annoncée en mode --lan

Exemples :
  ./scripts/install.sh                  # Nouveau PC : installe Docker, .env, BDD, admin et démarre
  ./scripts/install.sh --all            # Nouveau PC : installe Docker + environnement local dev
  ./scripts/install.sh --local          # Développement local pur (SQLite + Next.js dev)
  ./scripts/install.sh --lan            # Installe et rend accessible sur le réseau local
  ./scripts/install.sh --check          # Diagnostic rapide sans rien modifier
EOF
}

INSTALL_MODE='docker'
INSTALL_CHECK_ONLY=false
INSTALL_LAN=false
INSTALL_SKIP_SYSTEM=false
INSTALL_SKIP_GCLOUD=false
INSTALL_SKIP_SMOKE=false
INSTALL_AUTO_YES=false
mode_explicit=false

set_mode() {
  local requested="$1"
  if [[ "$mode_explicit" == true && "$INSTALL_MODE" != "$requested" ]]; then
    log_err "Modes incompatibles spécifiés (--$INSTALL_MODE et --$requested)."
    exit 2
  fi
  INSTALL_MODE="$requested"
  mode_explicit=true
}

for arg in "$@"; do
  case "$arg" in
    --docker) set_mode docker ;;
    --local) set_mode local ;;
    --all|--full) set_mode all ;;
    --check) INSTALL_CHECK_ONLY=true ;;
    --lan) INSTALL_LAN=true ;;
    --skip-system) INSTALL_SKIP_SYSTEM=true ;;
    --skip-gcloud) INSTALL_SKIP_GCLOUD=true ;;
    --skip-smoke) INSTALL_SKIP_SMOKE=true ;;
    -y|--yes) INSTALL_AUTO_YES=true ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log_err "Option inconnue : $arg"
      usage >&2
      exit 2
      ;;
  esac
done

export INSTALL_SKIP_SYSTEM INSTALL_SKIP_GCLOUD INSTALL_AUTO_YES

detect_os

if [[ "$INSTALL_CHECK_ONLY" == true ]]; then
  run_system_check
  exit 0
fi

# ---------------------------------------------------------------------------
# Helpers d'initialisation de base (Docker et Local)
# ---------------------------------------------------------------------------
DB_CHECK_PY='
from pathlib import Path
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
import app
from app.config import Settings
from app.models import Attachment, Conversation, Memory, User

env_candidates = (
    Path("/app/.env"),
    Path(app.__file__).resolve().parents[2] / ".env",
    Path(".env"),
)
env_file = next((p for p in env_candidates if p.is_file()), None)
settings = Settings(_env_file=env_file) if env_file else Settings()
engine = create_engine(settings.db_url, pool_pre_ping=True)
sessions = sessionmaker(engine)
try:
    with sessions() as db:
        has_admin = 1 if db.scalar(select(User.id).where(User.is_admin.is_(True))) else 0
        unowned = sum(
            db.scalar(select(func.count()).select_from(m).where(m.user_id.is_(None))) or 0
            for m in (Conversation, Memory, Attachment)
        )
    print(f"{has_admin} {unowned}")
finally:
    engine.dispose()
'

prepare_repo_layout() {
  log_step "1/6 — Vérification du dépôt et des permissions"
  local required_files=(compose.yaml .env.example searxng/settings.yml hermes/config.yaml)
  for f in "${required_files[@]}"; do
    if [[ ! -f "$repo_dir/$f" ]]; then
      log_err "Fichier essentiel introuvable : $f"
      exit 1
    fi
  done

  chmod +x "$repo_dir"/scripts/*.sh "$repo_dir"/scripts/*.py 2>/dev/null || true
  chmod +x "$repo_dir"/scripts/install_lib/*.sh "$repo_dir"/scripts/install_lib/*.py 2>/dev/null || true
  mkdir -p "$repo_dir/data" "$repo_dir/backend/data" "$repo_dir/backend/data/finance"
  log_ok "Structure du dépôt validée et scripts rendus exécutables."
}

prepare_system_prerequisites() {
  log_step "2/6 — Prérequis système ($OS_TYPE / $DISTRO_ID)"
  ensure_base_tools
  ensure_python_base
  if [[ "$INSTALL_MODE" == "docker" || "$INSTALL_MODE" == "all" ]]; then
    ensure_docker
  fi
  if [[ "$INSTALL_MODE" == "local" || "$INSTALL_MODE" == "all" ]]; then
    ensure_python_local
    ensure_node
  fi
}

prepare_env_and_gcloud() {
  log_step "3/6 — Configuration de l'environnement (.env & Google Cloud)"
  local env_args=(--repo-dir "$repo_dir" --mode "$INSTALL_MODE")
  if is_interactive; then
    env_args+=(--interactive)
  fi
  python3 "$repo_dir/scripts/install_lib/env_setup.py" "${env_args[@]}"

  local gcp_project=''
  gcp_project="$(python3 "$repo_dir/scripts/install_lib/env_setup.py" --repo-dir "$repo_dir" --get-gcp-project || true)"
  setup_gcloud_if_needed "$gcp_project" "$INSTALL_MODE"
}

prepare_svg_assets() {
  log_step "4/6 — Banques vectorielles SVG locales (cLAIr Pages)"
  if ! python3 "$repo_dir/scripts/download_svg_assets.py"; then
    log_warn "Téléchargement des banques SVG incomplet (mode hors-ligne ?) : le repli en mémoire reste actif."
  fi
}

install_local_stack() {
  local init_sqlite="$1"
  log_step "Installation de l'environnement local (Python venv + Node.js)"

  export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$repo_dir/../.cache/pip}"
  export npm_config_cache="${npm_config_cache:-$repo_dir/../.cache/npm}"

  if [[ ! -x "$repo_dir/backend/.venv/bin/python" ]]; then
    if [[ -n "${LOCAL_PYTHON_BIN:-}" ]] && python_has_venv "$LOCAL_PYTHON_BIN"; then
      log_info "Création du virtualenv backend/.venv avec $LOCAL_PYTHON_BIN..."
      "$LOCAL_PYTHON_BIN" -m venv "$repo_dir/backend/.venv"
    elif [[ -n "${UV_BIN:-}" ]]; then
      log_info "Création du virtualenv backend/.venv (Python 3.12) avec uv..."
      "$UV_BIN" venv --python 3.12 --seed "$repo_dir/backend/.venv"
    else
      log_err "Impossible de créer backend/.venv (Python 3.12+ indisponible)."
      exit 1
    fi
  else
    log_ok "Virtualenv existant détecté : backend/.venv ($("$repo_dir/backend/.venv/bin/python" --version 2>&1))"
  fi

  log_info "Installation des dépendances Python backend (requirements-dev.txt)..."
  "$repo_dir/backend/.venv/bin/python" -m pip install --quiet --upgrade pip
  "$repo_dir/backend/.venv/bin/python" -m pip install --requirement "$repo_dir/backend/requirements-dev.txt"
  log_ok "Dépendances Python installées."

  log_info "Installation des dépendances frontend (npm ci)..."
  npm --prefix "$repo_dir/frontend" ci --no-audit --no-fund
  log_ok "Dépendances frontend installées."

  if [[ "$init_sqlite" == true ]]; then
    log_info "Initialisation de la base SQLite locale..."
    (
      cd "$repo_dir/backend"
      .venv/bin/python -m app.cli migrate-schema
      local db_state has_admin unowned
      db_state="$(.venv/bin/python -c "$DB_CHECK_PY" 2>/dev/null || echo '0 0')"
      read -r has_admin unowned <<<"$db_state"

      if [[ "${has_admin:-0}" == "0" ]]; then
        local initial_admin="${INITIAL_ADMIN_USERNAME:-}"
        if [[ -z "$initial_admin" ]]; then
          read -r -p '  Identifiant du premier administrateur : ' initial_admin
        fi
        if [[ -z "$initial_admin" ]]; then
          log_err "Un identifiant administrateur est obligatoire."
          exit 2
        fi
        .venv/bin/python -m app.cli create-admin --username "$initial_admin"
      else
        log_ok "Un compte administrateur existe déjà dans la base locale."
      fi

      if [[ "${unowned:-0}" != "0" ]]; then
        local legacy_owner=''
        read -r -p "  $unowned éléments historiques sans propriétaire — identifiant admin propriétaire : " legacy_owner
        .venv/bin/python -m app.cli migrate-legacy --owner "$legacy_owner"
      else
        .venv/bin/python -m app.cli migrate-legacy
      fi
    )
    log_ok "Base SQLite locale prête."
  fi
}

install_docker_stack() {
  log_step "Installation et démarrage de la stack Docker"
  run_docker_cmd "$repo_dir/scripts/compose.sh" version >/dev/null
  run_docker_cmd "$repo_dir/scripts/compose.sh" config --quiet

  log_info "Démarrage de PostgreSQL (clair-db)..."
  run_docker_cmd "$repo_dir/scripts/compose.sh" up --detach --wait --wait-timeout 180 clair-db

  log_info "Construction de l'image backend (clair-api)..."
  run_docker_cmd "$repo_dir/scripts/compose.sh" build clair-api

  log_info "Préparation du schéma PostgreSQL..."
  run_docker_cmd "$repo_dir/scripts/compose.sh" run --rm --no-deps clair-api python -m app.cli migrate-schema

  local db_state has_admin unowned
  db_state="$(run_docker_cmd "$repo_dir/scripts/compose.sh" run --rm --no-deps -T clair-api python -c "$DB_CHECK_PY" 2>/dev/null | tail -n 1 || echo '0 0')"
  read -r has_admin unowned <<<"$db_state"

  if [[ "${has_admin:-0}" == "0" ]]; then
    local initial_admin="${INITIAL_ADMIN_USERNAME:-}"
    if [[ -z "$initial_admin" ]]; then
      read -r -p '  Identifiant du premier administrateur : ' initial_admin
    fi
    if [[ -z "$initial_admin" ]]; then
      log_err "Un identifiant administrateur est obligatoire."
      exit 2
    fi
    run_docker_cmd "$repo_dir/scripts/compose.sh" run --rm --no-deps clair-api python -m app.cli create-admin --username "$initial_admin"
  else
    log_ok "Un compte administrateur existe déjà dans PostgreSQL (conservation)."
  fi

  if [[ "${unowned:-0}" != "0" ]]; then
    local legacy_owner=''
    read -r -p "  $unowned éléments historiques sans propriétaire — identifiant admin propriétaire : " legacy_owner
    if [[ -n "$legacy_owner" ]]; then
      run_docker_cmd "$repo_dir/scripts/compose.sh" run --rm --no-deps clair-api python -m app.cli migrate-legacy --owner "$legacy_owner"
    else
      run_docker_cmd "$repo_dir/scripts/compose.sh" run --rm --no-deps clair-api python -m app.cli migrate-legacy
    fi
  else
    run_docker_cmd "$repo_dir/scripts/compose.sh" run --rm --no-deps clair-api python -m app.cli migrate-legacy
  fi

  log_info "Construction et démarrage de tous les services (clair-db, clair-searxng, clair-api, clair-web, clair-hermes)..."
  local compose_extra=()
  [[ "$INSTALL_LAN" == true ]] && compose_extra+=(--lan)
  run_docker_cmd "$repo_dir/scripts/compose.sh" ${compose_extra[@]+"${compose_extra[@]}"} up --build --detach --wait --wait-timeout 240
  log_ok "Tous les services Docker sont démarrés et opérationnels."

  if [[ "$INSTALL_SKIP_SMOKE" != true ]]; then
    if [[ -n "${SMOKE_USERNAME:-}" && -n "${SMOKE_PASSWORD:-}" ]] || confirm "Lancer le test de vérification (scripts/smoke.py) maintenant ?" "y" "n"; then
      python3 "$repo_dir/scripts/smoke.py"
    else
      log_info "Test de vérification ignoré (relançable à tout moment : python3 scripts/smoke.py)."
    fi
  fi
}

print_summary() {
  log_step "6/6 — Installation terminée !"
  printf '\n'
  if [[ "$INSTALL_MODE" == "docker" || "$INSTALL_MODE" == "all" ]]; then
    log_ok "Application accessible sur : http://localhost:3001"
    if [[ "$INSTALL_LAN" == true ]]; then
      log_info "Mode LAN actif : si un pare-feu est activé, ouvrez le port 3001 (ex. sudo ufw allow 3001/tcp)."
    fi
  fi
  if [[ "$INSTALL_MODE" == "local" ]]; then
    log_ok "Environnement local prêt. Démarrez avec : ./scripts/start.sh local (ou ./scripts/dev.sh)"
  fi

  printf '\n  %sCommandes utiles :%s\n' "$C_BOLD" "$C_RESET"
  printf '    ./scripts/start.sh              Démarrer en production (Docker)\n'
  printf '    ./scripts/start.sh --lan        Démarrer avec accès réseau local\n'
  printf '    ./scripts/start.sh dev          Démarrer en développement (Docker hot-reload)\n'
  printf '    ./scripts/start.sh local        Démarrer sans conteneurs app (venv + Next dev)\n'
  printf '    ./scripts/start.sh status       État des services\n'
  printf '    ./scripts/start.sh logs         Logs en direct\n'
  printf '    ./scripts/start.sh stop         Arrêter sans supprimer les données\n'
  printf '    ./scripts/install.sh --check    Vérifier les prérequis à tout moment\n'

  if [[ "$DOCKER_GROUP_ADDED" == true ]]; then
    printf '\n'
    log_warn "Votre utilisateur vient d'être ajouté au groupe 'docker'."
    log_warn "Ouvrez un nouveau terminal (ou exécutez 'newgrp docker') pour utiliser Docker sans sudo."
  fi
  printf '\n  %sNote :%s Pour modifier vos clés API plus tard, éditez .env puis exécutez ./scripts/start.sh\n\n' "$C_DIM" "$C_RESET"
}

main() {
  log_banner "Installation de cLAIr (mode : $INSTALL_MODE)"
  prepare_repo_layout
  prepare_system_prerequisites
  prepare_env_and_gcloud
  prepare_svg_assets

  log_step "5/6 — Déploiement des composants ($INSTALL_MODE)"
  case "$INSTALL_MODE" in
    docker)
      install_docker_stack
      ;;
    local)
      install_local_stack true
      ;;
    all)
      install_local_stack false
      install_docker_stack
      ;;
  esac

  print_summary
}

main
