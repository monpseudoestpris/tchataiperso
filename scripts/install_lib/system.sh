#!/usr/bin/env bash
# Vérification et installation automatique des prérequis système (Docker, Python, Node.js, outils de base).

APT_UPDATED=false

apt_update_once() {
  if [[ "$APT_UPDATED" != true ]]; then
    run_privileged apt-get update -qq
    APT_UPDATED=true
  fi
}

load_nvm_if_present() {
  if ! has_cmd node && [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # shellcheck disable=SC1091
    source "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true
  fi
}

python_version_of() {
  local bin="$1"
  "$bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true
}

python_has_venv() {
  local bin="$1"
  "$bin" -c 'import venv, ensurepip' >/dev/null 2>&1
}

find_local_python() {
  LOCAL_PYTHON_BIN=''
  local candidate=''
  for candidate in python3.13 python3.12 python3; do
    if has_cmd "$candidate"; then
      local ver
      ver="$(python_version_of "$candidate")"
      if [[ -n "$ver" ]] && version_ge "$ver" "3.12"; then
        LOCAL_PYTHON_BIN="$(command -v "$candidate")"
        export LOCAL_PYTHON_BIN
        return 0
      fi
    fi
  done
  # Vérifier aussi un éventuel venv déjà présent avec Python 3.12+
  if [[ -x "${repo_dir:-.}/backend/.venv/bin/python" ]]; then
    local venv_ver
    venv_ver="$(python_version_of "${repo_dir:-.}/backend/.venv/bin/python")"
    if [[ -n "$venv_ver" ]] && version_ge "$venv_ver" "3.12"; then
      LOCAL_PYTHON_BIN="${repo_dir:-.}/backend/.venv/bin/python"
      export LOCAL_PYTHON_BIN
      return 0
    fi
  fi
  return 1
}

ensure_base_tools() {
  local missing_pkgs=()
  has_cmd curl || missing_pkgs+=(curl)
  has_cmd git || missing_pkgs+=(git)
  if [[ "$OS_TYPE" == "linux" ]] && ! has_cmd setfacl; then
    missing_pkgs+=(acl)
  fi

  if [[ ${#missing_pkgs[@]} -eq 0 ]]; then
    log_ok "Outils de base présents (curl, git${OS_TYPE:+, acl})."
    return 0
  fi

  log_warn "Outils système manquants : ${missing_pkgs[*]}"
  if [[ "${INSTALL_SKIP_SYSTEM:-false}" == true ]]; then
    log_warn "Installation système ignorée (--skip-system)."
    return 0
  fi

  if ! confirm "Installer les outils de base (${missing_pkgs[*]}) ?" "y" "y"; then
    log_warn "Installation des outils de base ignorée."
    return 0
  fi

  case "$PKG_MANAGER" in
    apt)
      apt_update_once
      run_privileged apt-get install -y -qq ca-certificates gnupg "${missing_pkgs[@]}"
      ;;
    dnf)
      run_privileged dnf install -y -q ca-certificates "${missing_pkgs[@]}"
      ;;
    pacman)
      run_privileged pacman -Sy --noconfirm --needed ca-certificates "${missing_pkgs[@]}"
      ;;
    zypper)
      run_privileged zypper --non-interactive install ca-certificates "${missing_pkgs[@]}"
      ;;
    brew)
      brew install "${missing_pkgs[@]}"
      ;;
    *)
      log_warn "Gestionnaire de paquets non détecté. Installez manuellement : ${missing_pkgs[*]}"
      ;;
  esac
}

ensure_python_base() {
  if has_cmd python3; then
    local pyver
    pyver="$(python_version_of python3)"
    if [[ -n "$pyver" ]] && version_ge "$pyver" "3.9"; then
      log_ok "Python 3 détecté : $pyver ($(command -v python3))"
      return 0
    fi
  fi

  log_warn "Python 3 (>= 3.9) est requis pour les scripts d'installation."
  if [[ "${INSTALL_SKIP_SYSTEM:-false}" == true ]]; then
    log_err "Python 3 manquant et --skip-system est actif."
    return 1
  fi
  if ! confirm "Installer Python 3 automatiquement ?" "y" "y"; then
    log_err "Python 3 est obligatoire pour continuer."
    return 1
  fi

  case "$PKG_MANAGER" in
    apt)
      apt_update_once
      run_privileged apt-get install -y -qq python3 python3-venv python3-pip
      ;;
    dnf)
      run_privileged dnf install -y -q python3 python3-pip
      ;;
    pacman)
      run_privileged pacman -Sy --noconfirm --needed python python-pip
      ;;
    zypper)
      run_privileged zypper --non-interactive install python3 python3-pip
      ;;
    brew)
      brew install python@3.12
      ;;
    *)
      log_err "Impossible d'installer Python 3 automatiquement sur cet OS."
      return 1
      ;;
  esac
  log_ok "Python 3 installé : $(python_version_of python3)"
}

ensure_python_local() {
  if find_local_python && python_has_venv "$LOCAL_PYTHON_BIN"; then
    log_ok "Python local prêt : $(python_version_of "$LOCAL_PYTHON_BIN") ($LOCAL_PYTHON_BIN)"
    return 0
  fi

  if [[ "${INSTALL_SKIP_SYSTEM:-false}" == true ]]; then
    if [[ -n "${LOCAL_PYTHON_BIN:-}" ]]; then
      log_warn "Python 3.12+ trouvé ($LOCAL_PYTHON_BIN) mais module venv/ensurepip incomplet."
      return 1
    fi
    log_err "Python 3.12+ est requis pour le mode --local (détecté : $(python_version_of python3))."
    return 1
  fi

  log_warn "Le mode local requiert Python 3.12+ avec le module venv."
  if ! confirm "Installer Python 3.12+ (ou uv pour le gérer automatiquement) ?" "y" "y"; then
    log_err "Python 3.12+ avec venv est requis pour le mode local."
    return 1
  fi

  case "$PKG_MANAGER" in
    apt)
      apt_update_once
      if apt-cache show python3.12 >/dev/null 2>&1; then
        run_privileged apt-get install -y -qq python3.12 python3.12-venv python3-pip
      else
        log_info "python3.12 absent des dépôts apt par défaut : installation de uv pour fournir Python 3.12 isolé."
        ensure_uv
        "$UV_BIN" python install 3.12
      fi
      ;;
    dnf)
      run_privileged dnf install -y -q python3.12 python3-pip || run_privileged dnf install -y -q python3 python3-pip
      ;;
    pacman)
      run_privileged pacman -Sy --noconfirm --needed python python-pip
      ;;
    zypper)
      run_privileged zypper --non-interactive install python312 python312-pip || run_privileged zypper --non-interactive install python3 python3-pip
      ;;
    brew)
      brew install python@3.12
      export PATH="$(brew --prefix python@3.12)/bin:$PATH"
      ;;
    *)
      ensure_uv
      "$UV_BIN" python install 3.12
      ;;
  esac

  if find_local_python && python_has_venv "$LOCAL_PYTHON_BIN"; then
    log_ok "Python local prêt : $(python_version_of "$LOCAL_PYTHON_BIN") ($LOCAL_PYTHON_BIN)"
    return 0
  fi

  if has_cmd uv || [[ -x "$HOME/.local/bin/uv" ]]; then
    UV_BIN="${UV_BIN:-$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")}"
    export UV_BIN
    log_ok "Python 3.12 sera provisionné via uv ($UV_BIN)."
    return 0
  fi

  log_err "Python 3.12+ avec venv reste indisponible."
  return 1
}

ensure_uv() {
  if has_cmd uv; then
    UV_BIN="$(command -v uv)"
    export UV_BIN
    return 0
  fi
  if [[ -x "$HOME/.local/bin/uv" ]]; then
    UV_BIN="$HOME/.local/bin/uv"
    export UV_BIN
    return 0
  fi
  curl -fsSL --proto '=https' --tlsv1.2 https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  UV_BIN="$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")"
  export UV_BIN
}

install_docker_apt() {
  apt_update_once
  run_privileged apt-get install -y -qq ca-certificates curl gnupg
  run_privileged install -m 0755 -d /etc/apt/keyrings
  local repo_os='ubuntu'
  if [[ "$DISTRO_ID" == "debian" || "$DISTRO_LIKE" == *debian* && "$DISTRO_ID" != "ubuntu" && "$DISTRO_LIKE" != *ubuntu* ]]; then
    repo_os='debian'
  fi
  local codename="$DISTRO_CODENAME"
  if [[ -z "$codename" ]]; then
    codename="$(lsb_release -cs 2>/dev/null || true)"
  fi
  if [[ -z "$codename" ]]; then
    log_err "Impossible de déterminer le nom de version Debian/Ubuntu pour le dépôt Docker."
    return 1
  fi
  curl -fsSL --proto '=https' --tlsv1.2 "https://download.docker.com/linux/${repo_os}/gpg" \
    | run_privileged tee /etc/apt/keyrings/docker.asc >/dev/null
  run_privileged chmod a+r /etc/apt/keyrings/docker.asc
  local arch
  arch="$(dpkg --print-architecture)"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
    "$arch" "$repo_os" "$codename" \
    | run_privileged tee /etc/apt/sources.list.d/docker.list >/dev/null
  run_privileged apt-get update -qq
  run_privileged apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

ensure_docker() {
  local need_install=false
  if ! has_cmd docker; then
    need_install=true
  elif ! docker compose version >/dev/null 2>&1; then
    need_install=true
  fi

  if [[ "$need_install" == true ]]; then
    log_warn "Docker Engine et/ou Docker Compose v2 ne sont pas installés."
    if [[ "${INSTALL_SKIP_SYSTEM:-false}" == true ]]; then
      log_err "Docker manquant et --skip-system est actif."
      return 1
    fi
    if ! confirm "Installer Docker Engine + Docker Compose v2 automatiquement ?" "y" "y"; then
      log_err "Docker + Compose v2 sont requis pour l'installation Docker (sinon utilisez --local)."
      return 1
    fi

    case "$PKG_MANAGER" in
      apt)
        install_docker_apt
        ;;
      dnf)
        run_privileged dnf -y install dnf-plugins-core
        run_privileged dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo 2>/dev/null \
          || run_privileged dnf config-manager addrepo --from-repofile=https://download.docker.com/linux/fedora/docker-ce.repo
        run_privileged dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        ;;
      pacman)
        run_privileged pacman -Sy --noconfirm --needed docker docker-compose docker-buildx
        ;;
      zypper)
        run_privileged zypper --non-interactive install docker docker-compose docker-buildx
        ;;
      brew)
        log_info "Installation de Docker Desktop via Homebrew..."
        brew install --cask docker
        log_warn "Ouvrez Docker Desktop une fois pour démarrer le daemon Docker, puis relancez ./scripts/install.sh."
        return 1
        ;;
      *)
        log_err "Installation automatique de Docker non prise en charge sur cet OS. Installez Docker Engine + Compose v2 manuellement."
        return 1
        ;;
    esac
  fi

  # Sur Linux : démarrer le service et ajouter l'utilisateur au groupe docker si nécessaire.
  if [[ "$OS_TYPE" == "linux" ]]; then
    if has_cmd systemctl && systemctl list-unit-files docker.service >/dev/null 2>&1; then
      if ! systemctl is-active --quiet docker; then
        log_info "Démarrage du service Docker..."
        run_privileged systemctl enable --now docker
      fi
    elif has_cmd service; then
      run_privileged service docker start >/dev/null 2>&1 || true
    fi

    local current_user="${USER:-$(whoami)}"
    if [[ "${EUID:-$(id -u)}" -ne 0 ]] && getent group docker >/dev/null 2>&1; then
      if ! id -nG "$current_user" 2>/dev/null | grep -qw docker; then
        log_info "Ajout de l'utilisateur '$current_user' au groupe 'docker'..."
        run_privileged usermod -aG docker "$current_user"
        DOCKER_GROUP_ADDED=true
        export DOCKER_GROUP_ADDED
      fi
    fi
  fi

  if ! detect_docker_access; then
    if [[ "$OS_TYPE" == "macos" || "$IS_WSL" == true ]]; then
      log_err "Le daemon Docker ne répond pas. Lancez Docker Desktop puis relancez ./scripts/install.sh."
    else
      log_err "Impossible de contacter le daemon Docker. Vérifiez 'sudo systemctl status docker' puis relancez ./scripts/install.sh."
    fi
    return 1
  fi

  local compose_ver
  compose_ver="$(run_docker_cmd docker compose version --short 2>/dev/null || run_docker_cmd docker compose version 2>/dev/null)"
  log_ok "Docker prêt (Compose $compose_ver, accès : $DOCKER_ACCESS_MODE)."
}

ensure_node() {
  load_nvm_if_present
  local node_ver=''
  if has_cmd node && has_cmd npm; then
    node_ver="$(node -v 2>/dev/null || true)"
    if [[ -n "$node_ver" ]] && version_ge "$node_ver" "20.0.0"; then
      log_ok "Node.js prêt : $node_ver / npm $(npm -v 2>/dev/null)"
      return 0
    fi
    log_warn "Node.js détecté ($node_ver) est trop ancien (Node 20+ requis, 24 recommandé)."
  else
    log_warn "Node.js (20+, recommandé 24) et npm sont requis pour le mode local."
  fi

  if [[ "${INSTALL_SKIP_SYSTEM:-false}" == true ]]; then
    log_err "Node.js 20+ manquant et --skip-system est actif."
    return 1
  fi
  if ! confirm "Installer Node.js 24 LTS + npm automatiquement ?" "y" "y"; then
    log_err "Node.js 20+ et npm sont requis pour le mode local."
    return 1
  fi

  case "$PKG_MANAGER" in
    apt)
      apt_update_once
      run_privileged apt-get install -y -qq ca-certificates curl gnupg
      run_privileged install -m 0755 -d /etc/apt/keyrings
      curl -fsSL --proto '=https' --tlsv1.2 https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | run_privileged gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
      printf 'deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main\n' \
        | run_privileged tee /etc/apt/sources.list.d/nodesource.list >/dev/null
      run_privileged apt-get update -qq
      run_privileged apt-get install -y -qq nodejs
      ;;
    dnf)
      run_privileged dnf install -y -q nodejs npm
      ;;
    pacman)
      run_privileged pacman -Sy --noconfirm --needed nodejs npm
      ;;
    zypper)
      run_privileged zypper --non-interactive install nodejs24 npm24 || run_privileged zypper --non-interactive install nodejs npm
      ;;
    brew)
      brew install node@24 || brew install node
      ;;
    *)
      log_err "Installez Node.js 24 manuellement (https://nodejs.org ou nvm)."
      return 1
      ;;
  esac

  load_nvm_if_present
  if has_cmd node && version_ge "$(node -v)" "20.0.0"; then
    log_ok "Node.js installé : $(node -v) / npm $(npm -v)"
    return 0
  fi
  log_err "Node.js 20+ reste introuvable après installation."
  return 1
}

check_port_status() {
  local port="$1"
  local label="$2"
  local busy=false
  if has_cmd ss; then
    ss -tln 2>/dev/null | grep -qE "[:.]${port}[[:space:]]" && busy=true
  elif has_cmd lsof; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && busy=true
  fi
  if [[ "$busy" == true ]]; then
    log_warn "Port $port ($label) : déjà utilisé"
  else
    log_ok "Port $port ($label) : libre"
  fi
}

run_system_check() {
  log_banner "Diagnostic des prérequis — cLAIr (tchataiperso)"
  log_info "Système      : $OS_TYPE (distro: $DISTRO_ID, gestionnaire: $PKG_MANAGER, WSL: $IS_WSL)"

  log_step "Outils système"
  for cmd in curl git; do
    if has_cmd "$cmd"; then log_ok "$cmd : $(command -v "$cmd")"; else log_warn "$cmd : manquant"; fi
  done
  if [[ "$OS_TYPE" == "linux" ]]; then
    if has_cmd setfacl; then log_ok "setfacl (acl) : présent"; else log_warn "setfacl (acl) : manquant (recommandé pour Google Cloud ADC)"; fi
  fi

  log_step "Python & Node.js"
  if has_cmd python3; then
    log_ok "python3 : $(python_version_of python3) ($(command -v python3))"
  else
    log_warn "python3 : manquant"
  fi
  if find_local_python; then
    log_ok "Python local (>= 3.12) : $(python_version_of "$LOCAL_PYTHON_BIN") ($LOCAL_PYTHON_BIN)"
  else
    log_warn "Python local (>= 3.12) : absent (requis uniquement pour --local / --all)"
  fi
  load_nvm_if_present
  if has_cmd node && has_cmd npm; then
    log_ok "Node.js / npm : $(node -v) / $(npm -v)"
  else
    log_warn "Node.js / npm : absent (requis uniquement pour --local / --all)"
  fi

  log_step "Docker & Compose"
  if has_cmd docker; then
    if detect_docker_access; then
      log_ok "Docker daemon : actif (accès: $DOCKER_ACCESS_MODE)"
      if run_docker_cmd docker compose version >/dev/null 2>&1; then
        log_ok "Docker Compose : $(run_docker_cmd docker compose version --short 2>/dev/null || echo ok)"
      else
        log_warn "Docker Compose v2 : manquant"
      fi
    else
      log_warn "Docker installé mais daemon inaccessible"
    fi
  else
    log_warn "Docker : manquant"
  fi

  log_step "Configuration & assets du projet"
  if [[ -f "$repo_dir/.env" ]]; then
    log_ok ".env : présent"
  else
    log_warn ".env : absent (sera créé automatiquement par ./scripts/install.sh)"
  fi
  local adc_path="$HOME/.config/gcloud/application_default_credentials.json"
  if [[ -d "$adc_path" ]]; then
    log_err "GCP ADC ($adc_path) : est un DOSSIER (créé par Docker, sera réparé par install.sh)"
  elif [[ -f "$adc_path" ]]; then
    log_ok "GCP ADC ($adc_path) : présent"
  else
    log_info "GCP ADC ($adc_path) : absent (un placeholder sera préparé pour Docker)"
  fi
  if has_cmd gcloud; then
    log_ok "gcloud CLI : présent"
  else
    log_info "gcloud CLI : absent (facultatif, uniquement pour Vertex AI OAuth)"
  fi
  local tabler_count=0 undraw_count=0
  [[ -d "$repo_dir/backend/app/assets/svg/tabler" ]] && tabler_count="$(find "$repo_dir/backend/app/assets/svg/tabler" -maxdepth 1 -name '*.svg' 2>/dev/null | wc -l)"
  [[ -d "$repo_dir/backend/app/assets/svg/undraw" ]] && undraw_count="$(find "$repo_dir/backend/app/assets/svg/undraw" -maxdepth 1 -name '*.svg' 2>/dev/null | wc -l)"
  if (( tabler_count > 1000 && undraw_count > 500 )); then
    log_ok "Banques SVG locales : $tabler_count Tabler + $undraw_count unDraw"
  else
    log_info "Banques SVG locales : à télécharger ($tabler_count Tabler, $undraw_count unDraw)"
  fi

  log_step "Ports locaux"
  check_port_status 3001 "Frontend Web"
  check_port_status 8001 "Backend API"
  check_port_status 8080 "SearXNG"
  check_port_status 8642 "Hermes Agent"
}
