#!/usr/bin/env bash
# Préparation des identifiants Google Cloud ADC (montage Docker + permissions UID 10001 + auth optionnelle).

GCP_ADC_DIR="$HOME/.config/gcloud"
GCP_ADC_FILE="$GCP_ADC_DIR/application_default_credentials.json"
GCP_CONTAINER_UID=10001

grant_container_read_adc() {
  if [[ ! -f "$GCP_ADC_FILE" ]]; then
    return 0
  fi
  if [[ "$OS_TYPE" == "linux" ]] && has_cmd setfacl; then
    # S'assurer que le dossier parent est traversable par UID 10001 si nécessaire.
    setfacl -m "u:${GCP_CONTAINER_UID}:x" "$HOME/.config" "$GCP_ADC_DIR" 2>/dev/null || true
    if setfacl -m "u:${GCP_CONTAINER_UID}:r" "$GCP_ADC_FILE" 2>/dev/null; then
      log_ok "Droits de lecture ACL accordés à l'UID $GCP_CONTAINER_UID sur le fichier GCP ADC."
      return 0
    fi
  fi
  chmod 644 "$GCP_ADC_FILE" 2>/dev/null || true
  log_ok "Permissions de lecture ajustées sur $GCP_ADC_FILE pour le conteneur clair-api."
}

is_placeholder_adc() {
  [[ ! -f "$GCP_ADC_FILE" ]] && return 0
  local compact
  compact="$(tr -d '[:space:]' < "$GCP_ADC_FILE" 2>/dev/null || true)"
  [[ -z "$compact" || "$compact" == "{}" ]]
}

# Empêche Docker de créer un répertoire appartenant à root lorsque
# ~/.config/gcloud/application_default_credentials.json n'existe pas encore.
prepare_gcp_adc_mount() {
  mkdir -p "$GCP_ADC_DIR"
  chmod 700 "$GCP_ADC_DIR" 2>/dev/null || true

  if [[ -d "$GCP_ADC_FILE" ]]; then
    log_warn "$GCP_ADC_FILE est actuellement un répertoire (créé par un précédent lancement Docker)."
    if rmdir "$GCP_ADC_FILE" 2>/dev/null || run_privileged rmdir "$GCP_ADC_FILE" 2>/dev/null; then
      log_ok "Répertoire erroné supprimé."
    else
      log_err "Impossible de supprimer le répertoire non vide $GCP_ADC_FILE ; vérifiez-le manuellement."
      return 1
    fi
  fi

  if [[ ! -f "$GCP_ADC_FILE" ]]; then
    printf '{}\n' > "$GCP_ADC_FILE"
    chmod 644 "$GCP_ADC_FILE"
    log_info "Placeholder créé pour le montage Docker GCP ADC ($GCP_ADC_FILE)."
  else
    grant_container_read_adc
  fi
}

install_gcloud_cli() {
  case "$PKG_MANAGER" in
    apt)
      if has_cmd snap; then
        run_privileged snap install google-cloud-cli --classic
      else
        apt_update_once
        run_privileged apt-get install -y -qq apt-transport-https ca-certificates gnupg curl
        run_privileged install -m 0755 -d /usr/share/keyrings
        curl -fsSL --proto '=https' --tlsv1.2 https://packages.cloud.google.com/apt/doc/apt-key.gpg \
          | run_privileged gpg --dearmor --yes -o /usr/share/keyrings/cloud.google.gpg
        printf 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main\n' \
          | run_privileged tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
        run_privileged apt-get update -qq
        run_privileged apt-get install -y -qq google-cloud-cli
      fi
      ;;
    brew)
      brew install --cask google-cloud-sdk
      ;;
    *)
      log_warn "Installez Google Cloud CLI manuellement : https://cloud.google.com/sdk/docs/install"
      return 1
      ;;
  esac
}

setup_gcloud_if_needed() {
  local gcp_project="${1:-}"
  local install_mode="${2:-docker}"

  # En mode Docker ou All, le bind-mount de compose.yaml exige que le fichier existe.
  if [[ "$install_mode" == "docker" || "$install_mode" == "all" ]]; then
    prepare_gcp_adc_mount
  fi

  if [[ "${INSTALL_SKIP_GCLOUD:-false}" == true ]]; then
    return 0
  fi

  if [[ -z "$gcp_project" ]]; then
    log_info "Google Cloud Vertex AI non configuré (facultatif — voir README_GOOGLE_CLOUD.md plus tard si besoin)."
    return 0
  fi

  log_info "Projet Google Cloud détecté : $gcp_project"

  if ! has_cmd gcloud; then
    if [[ "${INSTALL_SKIP_SYSTEM:-false}" != true ]] && confirm "Installer Google Cloud CLI (gcloud) pour authentifier Vertex AI ?" "y" "n"; then
      install_gcloud_cli || log_warn "Installation de gcloud non finalisée ; suivez README_GOOGLE_CLOUD.md."
    else
      log_info "gcloud CLI non installé ; consultez README_GOOGLE_CLOUD.md pour activer Vertex AI OAuth."
      return 0
    fi
  fi

  if has_cmd gcloud && is_placeholder_adc && is_interactive; then
    if confirm "Lancer l'authentification Google Cloud (gcloud auth application-default login) maintenant ?" "y" "n"; then
      # Si placeholder {} existait, le retirer avant que gcloud crée le vrai fichier ADC.
      is_placeholder_adc && rm -f "$GCP_ADC_FILE"
      gcloud auth application-default login
      gcloud auth application-default set-quota-project "$gcp_project" || true
      gcloud config set project "$gcp_project" || true
      if confirm "Activer l'API Vertex AI (aiplatform.googleapis.com) sur '$gcp_project' ?" "y" "n"; then
        gcloud services enable aiplatform.googleapis.com --project="$gcp_project" || true
      fi
      grant_container_read_adc
    fi
  elif [[ -f "$GCP_ADC_FILE" ]] && ! is_placeholder_adc; then
    grant_container_read_adc
  fi
}
