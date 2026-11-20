# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite-PostgreSQL** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, analyse fondamentale, MOAT, rapports trimestriels et avis d'experts.
- Le module **Documents Illustrés (`VisualDocModal`)** pour ingérer un PDF ou une liste ordonnée d'images (règles de jeu, manuels) via **Mistral OCR**, compiler un Markdown enrichi avec schémas WebP et pages originales de secours cliquables `[p. X]`.
- Le module **Voix IA** : synthèse vocale **Google Gemini TTS** (`gemini-2.5-flash-preview-tts`, filtrage Markdown/images/références) et dictée vocale **Mistral Voxtral** (`voxtral-mini-latest`) avec repli **Google Gemini Audio**.
- Le connecteur agentique **Hermes Agent** et la recherche approfondie **Google Deep Research** (Interactions API).

## 2. Current Objective
Épurer la barre basse du tchat (garder uniquement Pièces jointes, URL, **Web**, **DeepSearch**, **Code · Canvas**, **Relances**, plus **Voix** et **Micro**) et ajouter la synthèse vocale Google TTS (avec filtrage du contenu non parlé) ainsi que la dictée vocale au micro (Mistral Voxtral / Google Gemini Audio).

**Statut** : Implémenté et vérifié (`11 passed` sur `test_voice.py` + `test_visual_documents.py`, `tsc --noEmit` 0 erreur, `eslint --max-warnings 0` sur les nouveaux modules frontend). En Docker, reconstruire et relancer `clair-api` et `clair-web` (`docker compose up -d --build clair-api clair-web`).

## 3. Completed Work
- **Épuration de la barre basse du tchat** (`frontend/components/chat-app.tsx`) :
  - Retrait des boutons déjà présents dans **Outils** (`Docs OCR`, `Apprendre`, `Finances`, `Courbe & Stats`, `Conseil IA`, `Hermes`, `Studio Image`, `Sons & Musique`, `Réviser`).
  - Conservation sur une seule ligne de : `Paperclip`, `Link2`, `Web`, `DeepSearch`, `Code · Canvas`, `Relances` à gauche ; `VoiceSettingsMenu`, `VoiceRecorderButton`, `↵ pour envoyer` et `Envoyer/Stop` à droite.
- **Synthèse vocale Google TTS + Filtrage intelligent** (`backend/app/voice_sanitize.py`, `backend/app/voice.py`, `backend/app/routers/voice.py`, `backend/app/config.py`, `backend/app/routers/system.py`, `backend/app/main.py`) :
  - Filtrage pur dans `prepare_text_for_speech` : supprime images Markdown/HTML (`/api/docs/.../pN_figM.webp`, `<figure>`, `<img>`), citations `[p. X]`, `[1, 2]`, `[^1]`, URLs, blocs de code (remplacés par une courte mention), tableaux Markdown, LaTeX et balises Markdown.
  - Découpage propre par phrases (`split_speech_chunks`) et encapsulation PCM 24 kHz → WAV standard (`pcm_to_wav`, stdlib `wave`, zéro nouvelle dépendance).
  - 7 voix Google préconfigurées (`Aoede`, `Kore`, `Leda`, `Puck`, `Charon`, `Fenrir`, `Orus`), réutilisation directe de `GOOGLE_API_KEY` (avec repli Vertex AI OAuth2/API Key).
- **Dictée vocale Micro STT** (`backend/app/voice.py`, `backend/app/routers/voice.py`, `frontend/components/voice-recorder-button.tsx`) :
  - Priorité **Mistral Voxtral** (`POST https://api.mistral.ai/v1/audio/transcriptions`, `voxtral-mini-latest`) quand `MISTRAL_API_KEY` est configurée, avec repli automatique **Google Gemini Audio** (`gemini-2.5-flash`).
  - Validation stricte MIME audio et limite de taille 15 Mo côté backend ; enregistrement navigateur via `MediaRecorder` avec chronomètre, annulation et nettoyage des pistes micro.
- **UI Voix** (`frontend/lib/voice-api.ts`, `frontend/components/voice-settings-menu.tsx`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`) :
  - Bouton **Écouter / Arrêter** sur chaque réponse assistant (cache client `ObjectURL` borné à 15 pistes), menu compact de choix de voix + toggle **Lecture automatique** (persistés en `localStorage`).
- **Travaux précédents conservés intacts** : Module Documents Illustrés (`VisualDocModal`), correctif timeouts LLM, cLAIr Pages, routage Google Cloud / Vertex AI.

## 4. Key Decisions
- **Zéro nouvelle dépendance Python ou JS** : encapsulation PCM→WAV via `wave` (stdlib Python) et appels REST `httpx` existants.
- **Réutilisation transparente des clés existantes** : `GOOGLE_API_KEY` (ou Google Cloud Vertex) pour le TTS, `MISTRAL_API_KEY` (Voxtral) prioritaire pour le STT avec secours Google Gemini Audio ; aucune modification obligatoire de `.env`.
- **Modulaire (1 fichier = 1 fonctionnalité)** : `voice_sanitize.py` (filtrage), `voice.py` (clients TTS/STT), `routers/voice.py` (API), `voice-api.ts`, `voice-recorder-button.tsx`, `voice-settings-menu.tsx`.

## 5. Modified Files
- Créés (Voix IA) :
  - `backend/app/voice_sanitize.py` : nettoyage Markdown/images/références/code/URLs + découpage en phrases.
  - `backend/app/voice.py` : clients Google Gemini TTS (PCM→WAV) et Mistral Voxtral / Google Gemini Audio STT.
  - `backend/app/routers/voice.py` : endpoints authentifiés `POST /api/voice/tts` et `POST /api/voice/transcribe`.
  - `backend/tests/test_voice.py` : 6 tests unitaires et d'intégration (filtrage, WAV, priorité STT, endpoints démo et réels mockés).
  - `frontend/lib/voice-api.ts` : helpers fetch typés `synthesizeSpeech` et `transcribeAudio`.
  - `frontend/components/voice-recorder-button.tsx` : bouton micro avec `MediaRecorder`, timer et annulation.
  - `frontend/components/voice-settings-menu.tsx` : popover choix de voix Google + toggle lecture automatique.
- Modifiés (Voix IA & épuration composer) :
  - `backend/app/config.py`, `backend/app/routers/system.py`, `backend/app/main.py`, `.env.example`.
  - `frontend/lib/api.ts`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`.
- Conservés intacts (travaux non commités préexistants) : Documents Illustrés (`visual_docs*`, `visual-doc-modal*`, `0027_add_visual_documents.py`), `google_cloud.py`, `compose.yaml`, etc.

## 6. Verification
- `cd backend && .venv/bin/python -m pytest -q tests/test_voice.py tests/test_visual_documents.py` : **RÉUSSI — 11 passed** (1 warning `StarletteDeprecationWarning`).
- `cd frontend && npm run typecheck` : **RÉUSSI — 0 erreur TypeScript**.
- `cd frontend && npx eslint --max-warnings 0 lib/voice-api.ts components/voice-recorder-button.tsx components/voice-settings-menu.tsx` : **RÉUSSI — 0 erreur, 0 warning**.
- Non exécutés : appels réseau réels vers Google TTS (`gemini-2.5-flash-preview-tts`) et Mistral Voxtral (`voxtral-mini-latest`), et rebuild Docker (`docker compose up -d --build clair-api clair-web`).

## 7. Known Issues and Risks
- L'accès navigateur au microphone (`navigator.mediaDevices.getUserMedia`) nécessite **HTTPS** ou **`localhost` / `127.0.0.1`** (les navigateurs bloquent le micro sur HTTP en IP LAN non sécurisée).
- Les clés `GOOGLE_API_KEY` (TTS) et `MISTRAL_API_KEY` (STT Voxtral) doivent être valides dans `.env` côté serveur ; en Docker, reconstruire et redémarrer `clair-api` et `clair-web` pour activer `/api/voice/*` et la nouvelle barre du tchat.

## 8. Next Action
Reconstruire et relancer la pile Docker (`docker compose up -d --build clair-api clair-web`), puis tester en direct le bouton **Écouter** sur une réponse illustrée (vérifier que les schémas `[p. X]` et liens sont bien ignorés à l'oral) et la dictée vocale via le bouton **Micro**.
