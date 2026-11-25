# HANDOFF.md — Routeur de Session

## 1. Aperçu du Projet
**cLAIr** (`tchataiperso`) est une plateforme de tchat IA multi-fournisseurs (Google Cloud Vertex/Gemini natif, OpenRouter, Mistral OCR/Voxtral, Ideogram, ElevenLabs, EODHD) articulée autour d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite WAL** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`). Les concepts métier et choix d'architecture sont figés dans `GLOSSARY.md` et `docs/adr/0001..0007`.

## 2. Santé de Référence
- **Backend `pytest` complet** (`cd backend && HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 .venv/bin/python -m pytest -q`) : **PASS** (`687 passed, 0 failed`).
- **Frontend `typecheck`** (`cd frontend && npm run typecheck`) : **PASS** (`0 error`).
- **Frontend `lint` ciblé** (`cd frontend && npx eslint components/image-model-modal.tsx components/image-studio-upscale-panel.tsx components/image-studio-svg-panel.tsx lib/api.ts --max-warnings 0`) : **PASS** (`0 error, 0 warning`).
- **Frontend `test`** (`cd frontend && npm test`) : **PASS** (`38 passed, 0 failed`).
- **Frontend `build`** (`cd frontend && npm run build`) : **PASS** (`next build` Turbopack OK).

## 3. Plan Actif
- **Aucun** (`plan/2026-11-25/studio-images-gemini-upscale-svg.md` **TERMINÉ**).

## 4. Travaux Ponctuels Récents
- **Studio Image — Exclusivité Google Cloud Gemini, Upscale Ideogram v2 (8 modèles) & Vecteurs SVG (`plan/2026-11-25/studio-images-gemini-upscale-svg.md`, `TERMINÉ`)** : isolation stricte des modèles d'image `google/*` sur Google Cloud (`vertex_oauth` / `vertex_api_key` / `gemini_api`) sans aucun repli vers OpenRouter + repli régional `locations/global` et `-preview` sur Vertex AI + badges UI `Google Cloud (Vertex AI)` ; ajout des routes `GET /api/images/upscale-models`, `POST /api/images/upscale` (8 modèles officiels : `auto`, `topaz-standard-2`, `topaz-text-refine`, `topaz-wonder-3-5`, `topaz-wonder-4`, `topaz-bloom-2`, `topaz-redefine`, `nano-banana-pro`, plafond sortie `60 Mio`) et `POST /api/images/svg` (`generate` & `vectorize` sur `ideogram-vector-1`) avec sanitizer XML anti-XXE/XSS (`svg_sanitize.py`) et `CSP sandbox` ; panneaux Sprout `ImageStudioUpscalePanel` et `ImageStudioSvgPanel`.
- **Coffre-fort Clés API « Write-Only » dans Paramètres (`plan/2026-11-25/api-key-vault-settings.md`, `ADR-0007`, `TERMINÉ`)** : `api_key_overrides` (`AES-256-GCM`), routes `/api/settings/api-keys*` Admin + Sudo, `SettingsApiKeysSection`.
- **Mode Finance — Refonte visuelle Éditoriale & Lisibilité Watchlist (`plan/2026-11-25/finance-ui-editorial-and-watchlist.md`, `TERMINÉ`)** : `editorial-finance.css`, cellule `Action` 2 lignes, tokenisation Screener & Synchro.

## 5. Risques & Blocages Connus
- **Point d'attention `run_command` sandbox** : `.env.example` déclaré en chemin relatif dans la conf sandbox locale bloque l'exécution standard sans `BypassSandbox`.
- **Dettes préexistantes (hors plan)** : erreurs/warnings ESLint anciens sur `chat-app.tsx` (`24`), `finance-modal.tsx` (`18`), `image-studio-modal.tsx` (`6` préexistants lignes 539–594) et `settings-modal.tsx` (`1` ligne 98) ; fichier vide parasite `--system-prompt=Règle absolue...` ; `OLDPROJECT.md` conservé volontairement.

## 6. Prochaine Action Immédiate
Tester visuellement dans le **Studio Image** : (1) la génération Gemini affichant `Google Cloud (Vertex AI)`, (2) l'onglet **Upscale HD** sur les 8 modèles Ideogram v2, et (3) l'onglet **Vecteur SVG** (`Générer un SVG` et `Image → SVG` + copie du code SVG), puis passer en revue `git status` avant commit.
