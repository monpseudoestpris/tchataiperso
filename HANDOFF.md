# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite-PostgreSQL** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, analyse fondamentale, MOAT, rapports trimestriels interactifs (attachables au tchat et au Mode Vocal comme les Documents Illustrés) et avis d'experts.
- Le module **Documents Illustrés (`VisualDocModal`)** pour ingérer un PDF ou une liste ordonnée d'images (règles de jeu, manuels) via **Mistral OCR**, compiler un Markdown enrichi avec schémas WebP et pages originales de secours cliquables `[p. X]`.
- Le module **Voix IA & Mode Vocal Plein Écran** : synthèse vocale **Google Gemini TTS** (`gemini-2.5-flash-tts`, 30 voix, 8 tons + ton libre, `languageCode: "fr-FR"`, repli Cloud TTS `Chirp3-HD`, filtrage Markdown/images/références/guillemets/élisions), dictée vocale **Mistral Voxtral** (`voxtral-mini-latest`, repli Google Gemini Audio), vitesses `0.85×`–`2×`, Pause/Reprise et **Mode Vocal Plein Écran Mains-Libres + Clavier** (`VoiceFullscreenModal`).
- Le connecteur agentique **Hermes Agent** et la recherche approfondie **Google Deep Research** (Interactions API).

## 2. Current Objective
Fournir un **script d'installation complet et idempotent** dans `scripts/` (`./scripts/install.sh` + modules `scripts/install_lib/`) capable de préparer et installer intégralement l'application sur un nouveau PC (prérequis système, `.env` sécurisé, Google Cloud ADC, assets SVG, stack Docker et/ou environnement dev local, migrations BDD et compte admin).

**Statut** : Implémenté et vérifié (`bash -n`, `py_compile`, `./scripts/install.sh --help`, `./scripts/install.sh --check`, tests unitaires isolés `env_setup.py` + `version_ge` + `prepare_gcp_adc_mount` tous réussis).

## 3. Completed Work
- **Installeur complet multi-OS (`scripts/install.sh` + `scripts/install_lib/`)** :
  - `scripts/install_lib/common.sh` : affichage structuré, détection OS/distro/WSL/gestionnaire de paquets (`apt`, `dnf`, `pacman`, `zypper`, `brew`), confirmations interactives / `--yes`, comparaison de versions, accès Docker tolérant au nouvel ajout au groupe `docker` (`direct` / `sg` / `sudo`).
  - `scripts/install_lib/system.sh` : vérification et installation automatique des prérequis (`curl`, `git`, `acl`, Python 3 / 3.12+ avec repli `uv` sur distros anciennes, Docker Engine + Compose v2 + activation service + groupe `docker`, Node.js 24/20+ & npm avec détection `nvm`) + mode diagnostic `--check`.
  - `scripts/install_lib/env_setup.py` : création atomique (`0600`) de `.env` depuis `.env.example`, génération cryptographique de `POSTGRES_PASSWORD`, `SEARXNG_SECRET`, `HERMES_API_KEY`, assistant interactif facultatif à saisie masquée (`getpass`), gestion automatique `DEMO_MODE` / `GOOGLE_APPLICATION_CREDENTIALS`, préservation idempotente d'un `.env` existant.
  - `scripts/install_lib/gcloud_setup.sh` : prévention du piège bind-mount Docker (création placeholder `{}` pour `~/.config/gcloud/application_default_credentials.json`, réparation d'un répertoire erroné), droits UID `10001` (`setfacl` / `chmod 644`), installation et authentification optionnelle `gcloud` + activation `aiplatform.googleapis.com`.
  - `scripts/install.sh` : modes `--docker` (défaut), `--local` (initialise désormais aussi SQLite + admin), `--all`/`--full`, `--check`, options `--lan`, `--skip-system`, `--skip-gcloud`, `--skip-smoke`, `--yes`, détection idempotente d'un admin existant et des données orphelines.
- **Nettoyage `.env.example` & `README.md`** : suppression des doublons `FINANCE_EXCHANGE_*` et `GOOGLE_CLOUD_*`, retrait de l'ID de projet personnel codé en dur, ajout de `EOD_HISTORICAL_DATA_KEY=`, défaut sûr `DEMO_MODE=true`, documentation des options dans `README.md`.
- **Travaux précédents conservés dans l'arbre de travail** (non commités par la session précédente) : Mode Vocal Plein Écran (`VoiceFullscreenModal`) et pont Rapports Financiers → Documents Illustrés interactifs (`compile_finance_report_to_visual_doc`).

## 4. Key Decisions
- **Réutilisation de `VisualDocument` + `ConversationVisualDoc` pour les rapports financiers** : aucune migration de schéma SQL nécessaire, bénéficie immédiatement de `build_visual_docs_context` (sélection intelligente des pages pertinentes), des citations `[p. X]` cliquables et du rendu WebP sécurisé `/api/docs/{slug}/page_N.webp`.
- **Composant `VoiceFullscreenSession` monté conditionnellement** : garantit le nettoyage immédiat des pistes micro (`MediaStream`), `AudioContext` et timers dès la fermeture, sans effet de bord React 19.

## 5. Modified Files
- Créés (session courante — installeur complet) :
  - `scripts/install_lib/common.sh`, `scripts/install_lib/system.sh`, `scripts/install_lib/gcloud_setup.sh`, `scripts/install_lib/env_setup.py`.
- Modifiés (session courante) :
  - `scripts/install.sh`, `.env.example`, `README.md`, `HANDOFF.md`.
- Autres fichiers déjà modifiés/créés dans l'arbre de travail (session précédente — Mode Vocal Plein Écran & Rapports Financiers) :
  - `backend/app/voice_sanitize.py`, `backend/app/voice.py`, `backend/app/routers/voice.py`, `backend/tests/test_voice.py`, `backend/app/visual_documents.py`, `backend/app/routers/finance.py`, `backend/app/routers/system.py`, `backend/tests/test_visual_documents.py`.
  - `frontend/lib/api.ts`, `frontend/lib/voice-api.ts`, `frontend/components/voice-settings-menu.tsx`, `frontend/components/voice-fullscreen-modal.tsx`, `frontend/components/voice-fullscreen-modal.module.css`, `frontend/components/finance-reports-panel.tsx`, `frontend/components/finance-modal.tsx`, `frontend/components/visual-doc-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`.

## 6. Verification
- `bash -n scripts/install.sh scripts/install_lib/*.sh` : **RÉUSSI**.
- `python3 -m py_compile scripts/install_lib/env_setup.py` : **RÉUSSI**.
- `./scripts/install.sh --help` et `./scripts/install.sh --check` : **RÉUSSI** (sortie propre sans prompt `sudo`).
- Tests unitaires isolés (en répertoire temporaire, sans toucher le `.env` réel) de `env_setup.py` (création `0600`, génération secrets, idempotence, mode `--local`, `--get-gcp-project`), `version_ge` et `prepare_gcp_adc_mount` (création placeholder `{}` + récupération d'un dossier erroné) : **RÉUSSI**.
- Non exécutés : exécution complète de `./scripts/install.sh` sur un OS vierge (Docker/apt/dnf/pacman/brew) car hors périmètre sandbox.

## 7. Known Issues and Risks
- Sur un PC Windows, exécuter `./scripts/install.sh` depuis **WSL2** (Ubuntu/Debian) avec Docker Desktop actif côté Windows.
- L'accès micro navigateur (`getUserMedia` / `AudioContext`) exige `localhost` / `127.0.0.1` ou HTTPS.

## 8. Next Action
Sur un nouveau PC (ou pour valider sur ce poste), lancer `./scripts/install.sh --check` pour le diagnostic ou `./scripts/install.sh` (ou `--all` / `--local`) pour installer et démarrer toute l'application.
