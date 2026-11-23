# Plan d'exécution — Import vidéo, transcript intégral, espace « Mes Vidéos » & Screener

- **Date de création** : 2026-11-23
- **Statut** : TERMINÉ

## 1. Demande & Objectif Vérifiable
1. **Options dans la modale d'import vidéo (`ChatUrlAttachModal`)** : proposer 7 options claires sur quoi faire du transcript (*Résumer, Analyser, Points clés & Chapitres, Fiche & Quiz, Traduire en français, Consigne libre, Joindre uniquement + lecture/copie/téléchargement*), partagées avec `AttachmentAnalysis` et `transcript-modal`.
2. **Récupération et transmission 100 % intégrales du transcript** : supporter tous les formats YouTube (`XML` avec sous-balises, `srv3`, `json3`, replis `ytInitialPlayerResponse` / client `WEB`) et lever les troncatures silencieuses dans `build_context`, `chat_memory`, DeepSearch/Apprendre et `visual_doc_links`.
3. **Espace dédié « Mes Vidéos » (`SavedVideo`)** : conserver durablement les vidéos de l'utilisateur (titre visible dans la liste, lien YouTube, métadonnées, transcript intégral, résumé et analyses) avec consultation, recherche, génération de résumé/analyse et renvoi instantané vers le tchat.
4. **Tâche annexe (`T2`)** : dans le Screener boursier, afficher le nom complet des actions/ETFs au survol et rendre la colonne « Titre » redimensionnable.

## 2. Décisions Validées (One-Way Doors)
- **Table `saved_videos` + Migration `0031_add_saved_videos`** : table dédiée scopée par `user_id` avec contrainte unique `(user_id, video_id)` (upsert sur ré-import), stockant `transcript_markdown`, `summary_markdown`, `summary_action`, `summary_model` et l'historique `analyses` (JSON, max 10 entrées).
- **API dédiée `/api/videos/*`** : `GET /api/videos`, `GET /api/videos/{id}`, `POST /api/videos`, `POST /api/videos/{id}/generate`, `PATCH /api/videos/{id}`, `POST /api/videos/{id}/attach`, `DELETE /api/videos/{id}`.
- **Options de la modale d'import** : 7 options canoniques (`summarize` par défaut pour YouTube, `analyze`, `key_points`, `study`, `translate_fr`, `custom`, `attach_only`), avec sauvegarde automatique dans « Mes Vidéos » activée par défaut.

## 3. Découpage & Suivi des Tranches
- `[x]` **`T1a`** — Extraction intégrale & multi-format YouTube (`youtube.py`, `serializers.py`, `test_youtube.py`) — `[Two-Way] · [Runtime] · [~220 lignes / 2 fichiers prod] · [Seams checked: Yes]`
- `[x]` **`T1b`** — Transmission intégrale du transcript au LLM sans troncature (`context.py`, `routers/messages.py`, `visual_doc_links.py`, `test_context.py`) — `[Two-Way] · [Runtime] · [~110 lignes / 3 fichiers prod] · [Seams checked: Yes]`
- `[x]` **`T1c`** — Backend & Persistance « Mes Vidéos » (`models.py`, `0031_add_saved_videos.py`, `saved_videos.py`, `routers/videos.py`, `routers/attachments.py`, `schemas.py`, `main.py`, `test_videos.py`) — `[One-Way] · [Runtime] · [~450 lignes / 7 fichiers prod] · [Seams checked: Yes]`
- `[x]` **`T1d`** — Options dans la modale d'import vidéo + sauvegarde auto du résumé (`youtube-actions.ts`, `chat-url-attach-modal.tsx`, `chat-attachment-analysis.tsx`, `chat-app.tsx`, `api.ts`, `globals.css`, `youtube-actions.test.mjs`) — `[Two-Way] · [Runtime] · [~460 lignes / 6 fichiers prod] · [Seams checked: Yes]`
- `[x]` **`T1e`** — Espace « Mes Vidéos » (`video-library-modal.tsx`, `video-library-modal.module.css`, `tools-modal.tsx`, `chat-app.tsx`, `GLOSSARY.md`) — `[Two-Way] · [Runtime] · [~480 lignes / 4 fichiers prod] · [Seams checked: Yes]`
- `[x]` **`T2`** *(Annexe)* — Survol complet + colonne « Titre » redimensionnable dans le Screener (`finance-screener-panel.tsx`, `finance-screener-panel.module.css`) — `[Two-Way] · [Runtime] · [~95 lignes / 2 fichiers prod] · [Seams checked: N/A]`

## 4. Journal de Preuves
- **`T1a`–`T1c` (Backend)** : `cd backend && .venv/bin/python -m pytest tests/test_youtube.py tests/test_videos.py tests/test_context.py tests/test_chat_memory.py tests/test_visual_documents.py -q` → **PASS (`65 passed, 1 warning` en `11.51s`)**.
- **`T1d`–`T1e` + `T2` (Frontend)** :
  - `cd frontend && npm run typecheck` → **PASS (`0 error`)**.
  - `cd frontend && npx eslint lib/youtube-actions.ts components/chat-url-attach-modal.tsx components/video-library-modal.tsx components/chat-attachment-analysis.tsx components/tools-modal.tsx components/finance-screener-panel.tsx lib/api.ts --max-warnings 0` → **PASS (`0 error, 0 warning`)**.
  - `cd frontend && npm test` → **PASS (`23 passed, 0 failed`)**.
  - `cd frontend && npm run build` → **PASS (`next build` standalone OK)**.

## 5. Prochaine Tranche
Aucune — chantier terminé.
