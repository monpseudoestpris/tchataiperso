#!/usr/bin/env bash
# Utilitaires partagés pour scripts/install.sh (affichage, détection OS, confirmations, privilèges).

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_BLUE=$'\033[34m'
  C_CYAN=$'\033[36m'
  C_RESET=$'\033[0m'
else
  C_BOLD='' C_DIM='' C_GREEN='' C_YELLOW='' C_RED='' C_BLUE='' C_CYAN='' C_RESET=''
fi

log_banner() {
  printf '\n%s============================================================%s\n' "$C_BLUE" "$C_RESET"
  printf '%s  %s%s\n' "$C_BOLD" "$1" "$C_RESET"
  printf '%s============================================================%s\n' "$C_BLUE" "$C_RESET"
}

log_step() {
  printf '\n%s▶ %s%s\n' "$C_BOLD$C_CYAN" "$1" "$C_RESET"
}

log_info() {
  printf '  %s•%s %s\n' "$C_BLUE" "$C_RESET" "$1"
}

log_ok() {
  printf '  %s✓%s %s\n' "$C_GREEN" "$C_RESET" "$1"
}

log_warn() {
  printf '  %s!%s %s\n' "$C_YELLOW" "$C_RESET" "$1" >&2
}

log_err() {
  printf '  %s✗%s %s\n' "$C_RED" "$C_RESET" "$1" >&2
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

is_interactive() {
  [[ "${INSTALL_AUTO_YES:-false}" != true && -t 0 && -t 1 ]]
}

# confirm <question> [default_yn=n] [auto_yes_result=same_as_default]
confirm() {
  local prompt="$1"
  local default_yn="${2:-n}"
  local auto_yn="${3:-$default_yn}"

  if [[ "${INSTALL_AUTO_YES:-false}" == true ]]; then
    [[ "$auto_yn" == "y" ]]
    return $?
  fi

  if [[ ! -t 0 ]]; then
    [[ "$default_yn" == "y" ]]
    return $?
  fi

  local hint='[o/N]'
  [[ "$default_yn" == "y" ]] && hint='[O/n]'

  local reply=''
  read -r -p "  $prompt $hint : " reply || reply=''
  reply="${reply,,}"
  if [[ -z "$reply" ]]; then
    [[ "$default_yn" == "y" ]]
    return $?
  fi
  [[ "$reply" == "o" || "$reply" == "oui" || "$reply" == "y" || "$reply" == "yes" ]]
}

# Compare deux versions majeures.mineures (retourne 0 si $1 >= $2).
version_ge() {
  local current="${1#v}"
  local required="${2#v}"
  local c1 c2 c3 r1 r2 r3
  IFS='.' read -r c1 c2 c3 _ <<<"${current%%[^0-9.]*}"
  IFS='.' read -r r1 r2 r3 _ <<<"${required%%[^0-9.]*}"
  c1="${c1:-0}"; c2="${c2:-0}"; c3="${c3:-0}"
  r1="${r1:-0}"; r2="${r2:-0}"; r3="${r3:-0}"
  if (( c1 != r1 )); then (( c1 > r1 )); return $?; fi
  if (( c2 != r2 )); then (( c2 > r2 )); return $?; fi
  (( c3 >= r3 ))
}

detect_os() {
  OS_TYPE='unknown'
  IS_WSL=false
  DISTRO_ID='unknown'
  DISTRO_LIKE=''
  DISTRO_CODENAME=''
  PKG_MANAGER='none'

  case "$(uname -s)" in
    Linux)
      OS_TYPE='linux'
      if [[ -r /proc/version ]] && grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
        IS_WSL=true
      fi
      if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-}"
        DISTRO_CODENAME="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
      fi
      if has_cmd apt-get; then
        PKG_MANAGER='apt'
      elif has_cmd dnf; then
        PKG_MANAGER='dnf'
      elif has_cmd pacman; then
        PKG_MANAGER='pacman'
      elif has_cmd zypper; then
        PKG_MANAGER='zypper'
      fi
      ;;
    Darwin)
      OS_TYPE='macos'
      DISTRO_ID='macos'
      if has_cmd brew; then
        PKG_MANAGER='brew'
      fi
      ;;
  esac
  export OS_TYPE IS_WSL DISTRO_ID DISTRO_LIKE DISTRO_CODENAME PKG_MANAGER
}

run_privileged() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif has_cmd sudo; then
    sudo "$@"
  else
    log_err "Droits administrateur requis (installez 'sudo' ou exécutez en root) : $*"
    return 1
  fi
}

# Exécute une commande Docker en gérant automatiquement le cas où l'utilisateur
# vient d'être ajouté au groupe docker dans cette session (sans reconnexion).
DOCKER_ACCESS_MODE='direct'
DOCKER_GROUP_ADDED=false

detect_docker_access() {
  if ! has_cmd docker; then
    DOCKER_ACCESS_MODE='missing'
    return 1
  fi
  if docker info >/dev/null 2>&1; then
    DOCKER_ACCESS_MODE='direct'
    return 0
  fi
  if [[ "$OS_TYPE" == "linux" ]] && has_cmd sg && id -nG "${USER:-$(whoami)}" 2>/dev/null | grep -qw docker; then
    if sg docker -c 'docker info' >/dev/null 2>&1; then
      DOCKER_ACCESS_MODE='sg'
      return 0
    fi
  fi
  if [[ "$OS_TYPE" == "linux" ]] && [[ "${EUID:-$(id -u)}" -ne 0 ]] && has_cmd sudo; then
    if sudo -n docker info >/dev/null 2>&1; then
      DOCKER_ACCESS_MODE='sudo'
      return 0
    fi
    if [[ "${INSTALL_CHECK_ONLY:-false}" != true ]] && is_interactive && sudo docker info >/dev/null 2>&1; then
      DOCKER_ACCESS_MODE='sudo'
      return 0
    fi
  fi
  DOCKER_ACCESS_MODE='unavailable'
  return 1
}

run_docker_cmd() {
  case "$DOCKER_ACCESS_MODE" in
    direct)
      "$@"
      ;;
    sg)
      local escaped=''
      printf -v escaped '%q ' "$@"
      sg docker -c "$escaped"
      ;;
    sudo)
      run_privileged "$@"
      ;;
    *)
      "$@"
      ;;
  esac
}
