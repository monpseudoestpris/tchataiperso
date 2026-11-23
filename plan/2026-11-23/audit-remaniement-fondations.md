# Plan d'Exécution — Remaniement Fondations, Sécurité & Démantèlement des Monolithes

- **Date de création** : 2026-11-23
- **Statut** : `TERMINÉ`

## 1. Demande & Objectif Vérifiable
Suite à l'audit strict du dépôt `tchataiperso` (cLAIr), assainir les fondations d'ingénierie, la sécurité des frontières de confiance et la maintenabilité des modules monolithiques par petites sous-tranches indépendantes :
1. **Zéro fuite `.env` / DB locale dans les tests** et suites `pytest` + `npm test` 100 % vertes et déterministes hors-ligne.
2. **Fermeture des vecteurs SSRF par rebond et d'évasion Sandbox/CSP Same-Origin** (`CodeCanvas`, `WebPageModal`, `/p/{token}`) sans régression fonctionnelle sur les Briques IA ou `localStorage`.
3. **Extraction *Leaf-First* progressive** des monolithes backend (`providers.py`, `routers/messages.py`) et frontend (`lib/api.ts`, `chat-app.tsx`) en préservant 100 % des contrats HTTP/SSE et des coutures `monkeypatch`.
4. **Réduction par cliquet (*Dirty-Baseline Ratchet*)** des `except Exception` silencieux et des 216 problèmes ESLint / React 19.

## 2. Décisions Validées (One-Way Doors)
- **OWD-1 (Sandbox Iframe & CSP `/p/{token}`)** : **Option A validée** — retrait de `allow-same-origin` sur les `<iframe srcDoc>`, ajout de `sandbox` + `form-action 'none'` + `frame-ancestors 'none'` sur `/p/{token}`, et injection d'un shim mémoire `try/catch` sur `localStorage`/`sessionStorage` dans `page_runtime.py`.
- **OWD-2 (Migrations DB)** : **Option B à court terme validée** — extraction propre du bootstrap DDL idempotent dans un module dédié sans casser le démarrage local SQLite, avant convergence ultérieure vers Alembic seul.
- **OWD-3 (État Finance en RAM)** : **Option A validée** — persistance de l'avancement de synchro (`_DAILY_SYNC_PROGRESS`) et du compteur quotidien EODHD dans `finance_warehouse.db` (SQLite WAL), et purge bornée de `app.state.locks`.
- **OWD-4 (Linter Python `ruff`)** : **Validé en dépendance de dev uniquement** (`requirements-dev.in`), installation différée à un environnement disposant d'un accès réseau PyPI.
- **Glossaire métier** : `GLOSSARY.md` (14 concepts) validé en l'état comme référentiel ubiquitaire.

## 3. Découpage & Suivi des Tranches

### Phase 0 — Mémoire Projet & Remise au Vert Hermétique
- `[x]` **`T0a` — Initialisation du plan actif et mise en conformité de `HANDOFF.md` (~50 lignes)**
  `[Two-Way] · [Static] · [~120 lines / 2 files] · [Seams checked: N/A]`
- `[x]` **`T0b` — Isolation hermétique `.env`/DB sous `pytest`, correction des régressions de contrat (`blog.py`, `documents.py`, `get_message_html`) et script `npm test` unifié**
  `[Two-Way] · [Runtime] · [~95 lines / 5 prod files + 5 test files] · [Seams checked: Yes]`

### Phase 1 — Durcissement Sécurité (SSRF & Sandbox Same-Origin)
- `[x]` **`T1a` — Validation SSRF saut par saut & plafonds d'octets en streaming (`web.py`, `blog.py`, `providers.py`)**
  `[Two-Way] · [Runtime] · [~180 lines / 3 prod files + 3 test files] · [Seams checked: Yes]`
- `[x]` **`T1b` — Durcissement Sandbox Iframe (`CodeCanvas`, `WebPageModal`) & CSP `/p/{token}` + shim `localStorage` (`page_runtime.py`)**
  `[One-Way] · [Runtime] · [~115 lines / 5 prod files + 2 test files] · [Seams checked: Yes]`

### Phase 2 — Démantèlement *Leaf-First* des Monolithes Backend
- `[x]` **`T2a` — Extraction feuille Audio/ElevenLabs hors de `providers.py` (`providers_audio.py`) + création ADR `0006`**
  `[Two-Way] · [Static] · [~439 lines / 2 prod files + ADR 0006] · [Seams checked: Yes]`
- `[x]` **`T2b` — Extraction feuille Matériel d'Étude hors de `providers.py` (`providers_study.py`)**
  `[Two-Way] · [Static] · [~666 lines / 2 prod files] · [Seams checked: Yes]`
- `[x]` **`T2c` — Extraction feuille Images Ideogram/OpenRouter hors de `providers.py` (`providers_images.py`)**
  `[Two-Way] · [Static] · [~645 lines / 2 prod files] · [Seams checked: Yes]`
- `[x]` **`T2d` — Extraction des routes Rapports DeepSearch / Mode Apprendre / Exports hors de `routers/messages.py` (`routers/research_reports.py`)**
  `[Two-Way] · [Static] · [~953 lines / 3 prod files] · [Seams checked: Yes]`
- `[x]` **`T2e` — Catégorisation explicite des erreurs opérationnelles à la place des `except Exception` silencieux (`providers.py`, `finance.py`)**
  `[Two-Way] · [Runtime] · [~90 lines / 2 prod files + 1 test file] · [Seams checked: Yes]`

### Phase 3 — Hygiène Frontend, Découpage UI & État Finance
- `[x]` **`T3a` — Correction d'un premier lot statique ESLint (≤ 40 erreurs : entités JSX, `any`, CJS tests)**
  `[Two-Way] · [Static] · [~75 lines / 6 files] · [Seams checked: N/A]`
- `[x]` **`T3b` — Correction des erreurs ESLint *Runtime* React 19 (`renders` / `exhaustive-deps`) sur les modales**
  `[Two-Way] · [Runtime] · [~140 lines / 4 files] · [Seams checked: N/A]`
- `[x]` **`T3c` — Extraction feuille des types et clients Finance hors de `frontend/lib/api.ts` (`lib/finance-api.ts`)**
  `[Two-Way] · [Static] · [~441 lines / 3 files] · [Seams checked: N/A]`
- `[x]` **`T3d` — Extraction feuille de `AttachmentAnalysis` et de la modale YouTube hors de `chat-app.tsx`**
  `[Two-Way] · [Static] · [~420 lines / 2 prod files] · [Seams checked: N/A]`
- `[x]` **`T3e` — Persistance SQLite de l'avancement Synchro & Quota EODHD + extraction `db_bootstrap.py` + purge `app.state.locks`**
  `[One-Way] · [Runtime] · [~370 lines / 6 prod files + 1 test file] · [Seams checked: Yes]`

## 4. Journal de Preuves
- **`T0a` (2026-11-23)** : Création de `plan/2026-11-23/audit-remaniement-fondations.md` et condensation de `HANDOFF.md` en routeur de session (37 lignes, 6 sections canoniques) après audit complet de référence (`next build` OK, `tsc --noEmit` OK, `eslint` 216 problèmes, `node --test` 18/19, `pytest` 625/636).
- **`T0b` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/config.py`, `backend/app/documents.py`, `backend/app/routers/messages.py`, `backend/app/blog.py`, `backend/tests/conftest.py`, `backend/tests/test_api.py`, `backend/tests/test_deep_search.py`, `backend/tests/test_finance_funds.py`, `backend/tests/test_hermes.py`, `frontend/package.json`, `frontend/tests/visual-doc-markdown.test.mjs`.
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest -q --tb=short` → **`636 passed, 1 warning in 140.01s`** (0 échec, isolation complète des vrais `.env` tout en préservant les coutures `monkeypatch.chdir(tmp_path)` et `_REPO_ENV_FILE`).
    - `cd frontend && npm test && npm run typecheck` → **`19 passed, 0 fail`** + **`tsc --noEmit` 0 erreur**.
- **`T1a` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/web.py`, `backend/app/blog.py`, `backend/app/providers.py`, `backend/tests/test_web.py`, `backend/tests/test_blogs.py`, `backend/tests/test_providers.py`.
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest tests/test_web.py tests/test_blogs.py tests/test_providers.py tests/test_youtube.py tests/test_visual_documents.py -q --tb=short` → **`190 passed, 1 warning in 16.65s`** (incluant 4 nouveaux tests de régression SSRF saut intermédiaire + plafond 413, avec `prohibit_dns` préservé).
- **`T1b` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/page_runtime.py`, `backend/app/routers/pages.py`, `frontend/lib/code-canvas.ts`, `frontend/components/code-canvas.tsx`, `frontend/components/web-page-modal.tsx`, `backend/tests/test_pages.py`, `frontend/tests/code-canvas-sandbox.test.mjs`.
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest tests/test_pages.py tests/test_chat_site.py tests/test_hermes.py -q --tb=short` → **`60 passed, 1 warning in 22.13s`**.
    - `cd frontend && npm test && npm run typecheck && npx eslint lib/code-canvas.ts components/code-canvas.tsx tests/code-canvas-sandbox.test.mjs` → **`22 pass, 0 fail`**, **`tsc --noEmit` 0 erreur**, **`eslint` ciblé 0 erreur / 0 warning**.
- **`T2a` (2026-11-23)** :
  - *Fichiers touchés* : `docs/adr/0006-sandbox-isolation-for-generated-html-and-public-pages.md`, `backend/app/providers_audio.py`, `backend/app/providers.py` (`6 586 L` → `6 190 L`).
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest tests/test_sounds.py tests/test_providers.py -q --tb=short` → **`147 passed, 1 warning in 3.80s`** (toutes les coutures `monkeypatch` sur `providers.*` et `httpx.AsyncClient` préservées).
- **`T2b` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/providers_study.py`, `backend/app/providers.py` (`6 190 L` → `5 546 L`).
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest tests/test_study_material.py tests/test_providers.py -q --tb=short` → **`147 passed, 1 warning in 3.00s`**.
- **`T2c` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/providers_images.py` (`645 L`), `backend/app/providers.py` (`5 546 L` → `4 969 L`).
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest tests/test_providers.py tests/test_api.py tests/test_google_cloud.py -q --tb=short` → **`217 passed, 1 warning in 34.99s`** (coutures `monkeypatch` sur `providers._IDEOGRAM_POLL_INTERVAL`, `providers.generate_image`, `providers.improve_image_prompt`, `providers._detect_image_mime` et `httpx.AsyncClient` préservées).
- **`T2d` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/routers/research_reports.py` (`953 L`, 18 routes), `backend/app/routers/messages.py` (`2 579 L` → `1 647 L`), `backend/app/main.py`.
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest tests/test_deep_search.py tests/test_learn_mode.py tests/test_chat_site.py tests/test_api.py tests/test_multi_agent.py tests/test_finance_chat_agent.py -q --tb=short` → **`113 passed, 1 warning in 50.58s`**.
- **`T2e` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/providers.py` (`12` → `0` `except Exception`), `backend/app/finance.py` (`18` → `0` `except Exception`), `backend/tests/test_finance.py` (`httpx.ReadTimeout` réaliste dans `test_eodhd_fallback_to_yahoo_on_error`).
  - *Preuves d'exécution* :
    - `rg -c 'except Exception|except:' backend/app/providers.py backend/app/finance.py` → **`0`** occurrence.
    - `cd backend && .venv/bin/python -m pytest tests/test_providers.py tests/test_finance.py tests/test_finance_funds.py tests/test_finance_chat_agent.py tests/test_deep_search.py -q --tb=short` → **`205 passed, 1 warning in 12.01s`**.
- **`T3a` (2026-11-23)** :
  - *Fichiers touchés* : `frontend/eslint.config.mjs` (override `**/*.cjs`), `frontend/lib/api.ts`, `frontend/components/skills-panel.tsx`, `frontend/components/image-model-modal.tsx`, `frontend/components/multi-agent-modal.tsx`, `frontend/components/web-page-modal.tsx`.
  - *Preuves d'exécution* :
    - `cd frontend && npm run typecheck && npm test` → **`tsc --noEmit` 0 erreur**, **`22 pass, 0 fail`**.
    - `cd frontend && npx eslint lib/api.ts components/skills-panel.tsx components/image-model-modal.tsx tests/research-activity.test.cjs tests/thought.test.cjs` → **0 erreur / 0 warning**.
    - Cliquet global `eslint .` : **`216` (`117e / 99w`) → `163` (`77e / 86w`)** (**-40 erreurs, -13 warnings**).
- **`T3b` (2026-11-23)** :
  - *Fichiers touchés* : `frontend/components/multi-agent-modal.tsx`, `frontend/components/web-page-modal.tsx`, `frontend/components/finance-modal.tsx`, `frontend/components/deep-search-modal.tsx`.
  - *Preuves d'exécution* :
    - `cd frontend && npm run typecheck && npm test` → **`tsc --noEmit` 0 erreur**, **`22 pass, 0 fail`**.
    - `cd frontend && npx eslint components/multi-agent-modal.tsx components/web-page-modal.tsx` → **0 erreur / 0 warning**.
    - `react-hooks/*` sur `components/finance-modal.tsx` et `components/deep-search-modal.tsx` → **0 problème**.
    - Cliquet global `eslint .` : **`163` (`77e / 86w`) → `145` (`65e / 80w`)** (**-12 erreurs, -6 warnings**).
- **`T3c` (2026-11-23)** :
  - *Fichiers touchés* : `frontend/lib/api-client.ts` (`33 L`), `frontend/lib/finance-api.ts` (`408 L`), `frontend/lib/api.ts` (`3 691 L` → `3 263 L`, ré-export acyclique).
  - *Preuves d'exécution* :
    - `cd frontend && npm run typecheck && npm test && npx eslint lib/api.ts lib/api-client.ts lib/finance-api.ts` → **`tsc --noEmit` 0 erreur**, **`22 pass, 0 fail`**, **`eslint` ciblé 0 erreur / 0 warning**.
- **`T3d` (2026-11-23)** :
  - *Fichiers touchés* : `frontend/components/chat-attachment-analysis.tsx` (`792 L`, incluant `AttachmentAnalysis`, `AttachmentView`, `ChatUrlAttachModal` et les helpers Markdown/KaTeX partagés), `frontend/components/chat-app.tsx` (`4 947 L` → `4 614 L`).
  - *Preuves d'exécution* :
    - `cd frontend && npm run typecheck && npm test && npx eslint components/chat-attachment-analysis.tsx` → **`tsc --noEmit` 0 erreur**, **`22 pass, 0 fail`**, **`eslint` 0 erreur / 0 warning** (`chat-app.tsx` maintenu à `10e/14w`, 0 nouveau problème).
- **`T3e` (2026-11-23)** :
  - *Fichiers touchés* : `backend/app/db_bootstrap.py` (`252 L`), `backend/app/main.py` (`340 L` → `156 L`), `backend/app/deps.py` (purge bornée `_MAX_CONVERSATION_LOCKS = 512`), `backend/app/finance_warehouse.py` (tables `finance_eodhd_daily_usage` & `finance_sync_runtime_state`), `backend/app/finance_eodhd_usage.py`, `backend/app/finance_funds.py`, `backend/tests/test_finance_eodhd_usage.py` (+3 tests de persistance/purge).
  - *Preuves d'exécution* :
    - `cd backend && .venv/bin/python -m pytest tests/test_finance_eodhd_usage.py tests/test_finance_funds.py tests/test_finance_fundamentals_scheduler.py tests/test_finance.py tests/test_api.py -q --tb=short` → **`118 passed, 1 warning in 44.94s`**.

## 5. Prochaine Tranche
- **Plan terminé (`T0a` → `T3e` toutes `[x]`).** Suites optionnelles : poursuite du cliquet ESLint frontend (`145` problèmes restants), convergence Alembic seul, installation de `ruff` hors bac à sable (`OWD-4`).
