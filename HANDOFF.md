# HANDOFF.md — Routeur de Session

## 1. Aperçu du Projet
**cLAIr** (`tchataiperso`) est une plateforme de tchat IA multi-fournisseurs (Google Cloud Vertex/Gemini natif, OpenRouter, Mistral OCR/Voxtral, Ideogram, ElevenLabs, EODHD) articulée autour d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite WAL** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`). Les concepts métier et choix d'architecture sont figés dans `GLOSSARY.md` et `docs/adr/0001..0006`.

## 2. Santé de Référence (Baseline)
- **Backend `pytest` Vidéos / Contexte / Docs** (`cd backend && .venv/bin/python -m pytest tests/test_youtube.py tests/test_videos.py tests/test_context.py tests/test_chat_memory.py tests/test_visual_documents.py -q`) : **PASS** (`65 passed, 1 warning` en `11.51s` ; Finance `141 passed` précédemment).
- **Frontend `typecheck`** (`cd frontend && npm run typecheck`) : **PASS** (`0 error`).
- **Frontend `lint` ciblé** (`npx eslint lib/youtube-actions.ts components/chat-url-attach-modal.tsx components/video-library-modal.tsx components/chat-attachment-analysis.tsx components/tools-modal.tsx components/finance-screener-panel.tsx lib/api.ts --max-warnings 0`) : **PASS** (`0 error, 0 warning`).
- **Frontend `test`** (`cd frontend && npm test`) : **PASS** (`23 passed, 0 failed`).
- **Frontend `build`** (`cd frontend && npm run build`) : **PASS** (`next build` standalone OK).

## 3. Plan Actif
- **Aucun** (plan `plan/2026-11-23/import-video-transcript-options.md` **`TERMINÉ`**, tranches `T1a` → `T1e` + annexe `T2` toutes vérifiées).

## 4. Travaux Ponctuels Récents
- **Import vidéo YouTube & Transcript intégral (`T1a`–`T1b`)** : parsing multi-format complet (`XML` avec `itertext`, `srv3`, `json3`, replis `ytInitialPlayerResponse` / InnerTube `WEB`), `youtube_meta`, et levée des troncatures dans `build_context` (budget adapté au `context_length` du modèle jusqu'à 450 000 car.), `chat_memory`, DeepSearch/Apprendre et `visual_doc_links`.
- **Modale d'import enrichie & Espace « Mes Vidéos » (`T1c`–`T1e`)** : nouvelle table `saved_videos` (migration Alembic `0031`), API `/api/videos/*`, 7 options dans `ChatUrlAttachModal` (*Résumer, Analyser, Points clés & Chapitres, Fiche & Quiz, Traduire FR, Consigne libre, Joindre uniquement + lecture/copie/téléchargement `.md`*), enregistrement auto des vidéos et de leurs résumés, et modale dédiée `VideoLibraryModal` accessible depuis `ToolsModal` et la modale d'import.
- **Tâche annexe Screener (`T2`)** : infobulle complète au survol du nom d'action/ETF + colonne « Titre » redimensionnable par glisser-déposer (200–680 px, double-clic réinitialisation, persistée en `localStorage`) dans `FinanceScreenerPanel`.
- **Correctif concurrence SQLite (`finance_warehouse.py`)** : verrou `threading.Lock` (double-checked locking) autour de `init_warehouse`, ajout de `PRAGMA busy_timeout=30000` + `timeout=30.0` dans `init_warehouse` et `_connect`, et exécution de l'`UPDATE finance_screener_snapshots` de backfill `asset_type` uniquement lors de la création initiale de la colonne.
- **Bouton « Quitter proprement » (`QuitAppModal` + `/api/system/prepare-shutdown` / `resume` / `shutdown-status`)** : arrêt coopératif réservé admin qui gèle les nouvelles écritures (`503`), stoppe la synchro Finance, attend la fin des streams actifs, exécute `PRAGMA wal_checkpoint(TRUNCATE)` sur `finance_warehouse.db` (et SQLite principale si applicable, plus dans le `lifespan` à l'extinction), avec option de reprise ou d'arrêt du serveur local hors Docker.

## 5. Risques & Blocages Connus
- **Dettes restantes (hors plan clôturé)** : ~145 problèmes ESLint préexistants sur les anciennes modales frontend, poursuite éventuelle du découpage de `providers.py` / `chat-app.tsx`, convergence Alembic seul, installation de `ruff` hors bac à sable.
- **Hygiène dépôt** : modifications récentes non commitées dans l'arbre de travail ; fichier vide parasite `--system-prompt=Règle absolue...` suivi à la racine ; `OLDPROJECT.md` conservé volontairement.

## 6. Prochaine Action Immédiate
Tester manuellement dans l'UI l'import d'une vidéo YouTube longue (choix d'option dans la modale, consultation dans « Mes Vidéos », vérification de la fin du transcript) ainsi que le survol et le redimensionnement de la colonne « Titre » dans le Screener, puis revoir `git status` avant commit.
