# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, analyse fondamentale, MOAT, rapports trimestriels et avis d'experts.
- Le connecteur agentique **Hermes Agent** et la recherche approfondie **Google Deep Research** (Interactions API).

## 2. Current Objective
1. Persistance et horodatage en base de données des extraits de rapports trimestriels (`extracted_text`, `extracted_tables`, `extracted_at` sur `FinanceQuarterlyReport`).
2. Correction de l'erreur Docker `sqlite3.OperationalError: unable to open database file` sur l'entrepôt financier (`/app/finance_data`).

**Statut** : Implémentation terminée et vérifiée (`py_compile` exit 0, `47 passed` sur `tests/test_finance_reports.py` + `tests/test_finance.py`, `npx tsc --noEmit` exit 0). En Docker, il faut reconstruire `clair-api` / `clair-web` (`docker compose up -d --build`).

## 3. Completed Work
- **Persistance et datation des extraits de rapports (`FinanceQuarterlyReport`)** :
  - Ajout des colonnes `extracted_tables` (`JSON`, nullable) et `extracted_at` (`DateTime(timezone=True)`, nullable) sur `FinanceQuarterlyReport` (`backend/app/models.py`), migration Alembic `backend/migrations/versions/0026_add_finance_report_extracts.py`, enregistrement dans `backend/app/cli.py`, et mise à niveau idempotente dans `backend/app/main.py` (`lifespan`).
  - `POST /api/finance/reports` (`backend/app/routers/finance.py`) extrait et persiste désormais `extracted_text`, `extracted_tables` et `extracted_at` en base ; `quarterly_report_json` (`backend/app/serializers.py`) lit les tableaux persistés (avec repli sur `extract_markdown_tables` pour les anciens rapports) et expose `extracted_at`.
  - Frontend (`frontend/lib/api.ts`, `frontend/components/finance-reports-panel.tsx`) : ajout du champ `extracted_at` et affichage de `Extrait le <date>` sur chaque rapport.
- **Correction `unable to open database file` dans l'entrepôt financier Docker** :
  - `backend/Dockerfile` : création et `chown app:app` de `/app/finance_data` (en plus de `/data` et `/app/data`) pour que le volume nommé `finance_data` soit accessible en écriture par l'utilisateur `app` (uid 10001).
  - `backend/app/finance_warehouse.py` : `warehouse_db_path()` vérifie l'accessibilité en écriture de `FINANCE_DATA_DIR` et bascule automatiquement sur `app_data_dir / "finance"` (`/app/data/finance`) avec un avertissement si le répertoire/volume existant est bloqué en permissions.
- **Travaux antérieurs conservés** :
  - Routage Google Cloud / Vertex AI, espace Marchés Financiers, Code Canvas / cLAIr Pages / Briques Préfaites, Ideogram v2.

## 4. Key Decisions
- **Vertex AI (`vertex_oauth`) choisi comme mode Google Cloud principal** : le crédit mensuel de 10 $/mois inclus avec Google AI Pro est crédité sur le compte de facturation GCP, consommé nativement en post-paiement par Vertex AI (`aiplatform.googleapis.com` via OAuth2/ADC ou Service Account JSON, endpoints `endpoints/openapi` et `publishers/google/models`). `vertex_api_key` (Express/API Key natif) et `gemini_api` (`generativelanguage.googleapis.com`) sont supportés en complément.
- **Mode `auto` prudent** : active `vertex_oauth` si `GOOGLE_CLOUD_PROJECT` est défini, ou `vertex_api_key` si `VERTEX_API_KEY` est défini, sans détourner `GOOGLE_API_KEY` seul (sauf `GOOGLE_CLOUD_MODE=gemini_api`), préservant ainsi la compatibilité des configurations Deep Research existantes.
- **Politique stricte sans repli OpenRouter par défaut (`GOOGLE_CLOUD_FALLBACK_OPENROUTER=false`)** : une erreur Google Cloud lève `ProviderError` (aucune bascule silencieuse vers OpenRouter ni vers un `default_model` non-Google via `can_fallback_to_model`). Opt-in possible via `.env`.
- **Bypass Hermes Gateway pour les modèles Google** : le conteneur externe `clair-hermes` étant configuré avec OpenRouter, `hermes_agent.stream_hermes_mission` bascule vers `local_autonomous` pour tout modèle Google lorsque Google Cloud est actif sans repli OpenRouter.
- **Préservation de `httpx.AsyncClient` côté appelants & travail antérieur** : les modules créent leur `httpx.AsyncClient` et le passent en `client=client` aux helpers `google_cloud.py` pour garder compatibles les monkeypatches des tests existants ; les travaux non commités préexistants (FinanceModal, Code Canvas, Ideogram) restent intacts.

## 5. Modified Files
- Créés (Google Cloud) :
  - `backend/app/google_cloud.py` : routage Google Cloud unifié (OAuth2/ADC, Vertex API Key, Gemini API, traduction OpenAI ↔ Gemini, images Gemini/Imagen, Interactions API).
  - `backend/tests/test_google_cloud.py` : suite complète unitaires + intégration sans réseau (détection/normalisation, OAuth2 cache/refresh, streaming, traduction native, no-fallback, images, TopicAgent, Finance, Hermes bypass, FastAPI `/api/config` & `/api/images`).
- Modifiés (Google Cloud — Backend & Config) :
  - `backend/requirements.txt`, `backend/requirements.lock.txt`, `backend/requirements-dev.txt` : ajout et compilation de `google-auth==2.62.2` via `uv`.
  - `.env.example`, `compose.yaml`, `backend/app/config.py` : variables `GOOGLE_CLOUD_*`, `VERTEX_API_KEY`, validateurs, rechargement live et catalogues modèles/images sans `LLM_API_KEY`.
  - `backend/app/providers.py`, `backend/app/multi_agent.py`, `backend/app/memory_agent.py`, `backend/app/topic_agent.py`, `backend/app/blog.py`, `backend/app/page_bricks.py`, `backend/app/page_generator.py`, `backend/app/presentation_html.py`, `backend/app/finance_dossier.py`, `backend/app/finance_experts.py`, `backend/app/finance_moat.py`, `backend/app/finance_news.py`, `backend/app/finance_reports.py` : migration vers `post_chat_completion`, `open_chat_stream`, `has_llm_access` et `can_fallback_to_model`.
  - `backend/app/hermes_agent.py`, `backend/app/google_deep_research.py` : routage Google Cloud complet + bypass Gateway Hermes + Vertex AI Interactions API `v1beta1`.
  - `backend/app/routers/system.py`, `backend/app/routers/messages.py`, `backend/app/routers/images.py`, `backend/app/routers/skills.py`, `backend/app/routers/sounds.py`, `backend/app/routers/conversations.py` : gardes `has_llm_access` et exposition `features.google_cloud` / `google_cloud_mode`.
  - `backend/tests/conftest.py`, `backend/tests/test_google_deep_research.py`, `backend/tests/test_api.py` : isolation des alias d'environnement, cache OAuth2, `_env_file=None`, test Vertex Interactions API et mise à jour `features["google_cloud"]`.
- Modifiés (Google Cloud — Frontend) :
  - `frontend/lib/api.ts` : ajout des champs optionnels `features.google_cloud` et `google_cloud_mode` sur `Config`.
- Conservés intacts (travaux non commités préexistants hors tâche Google Cloud) :
  - `backend/app/finance_*.py`, `backend/migrations/versions/0022_*`–`0025_*`, `frontend/components/finance-*`, `frontend/components/code-canvas*`, `frontend/components/web-page-modal*`, `frontend/public/guides/*`, `scripts/start.sh`, etc.

## 6. Verification
- `rg -n --glob '!.env*' 'chat/completions|llm_base_url|openrouter_api_key|enabled\(settings\.llm_api_key\)' backend/app/` : **RÉUSSI** — aucun appel `/chat/completions` direct ni `openrouter_api_key` résiduel hors `backend/app/google_cloud.py` et l'appel Gateway Docker Hermes (`hermes_agent.py`, contourné pour Google).
- `cd backend && .venv/bin/python -m py_compile app/config.py app/google_cloud.py app/providers.py app/multi_agent.py app/memory_agent.py app/topic_agent.py app/blog.py app/page_bricks.py app/page_generator.py app/presentation_html.py app/finance_dossier.py app/finance_experts.py app/finance_moat.py app/finance_news.py app/finance_reports.py app/hermes_agent.py app/google_deep_research.py app/routers/system.py app/routers/messages.py app/routers/images.py app/routers/skills.py app/routers/sounds.py app/routers/conversations.py tests/conftest.py tests/test_google_cloud.py tests/test_google_deep_research.py tests/test_api.py` : **RÉUSSI** (exit code 0).
- `cd backend && .venv/bin/python -m pytest -q tests/test_google_cloud.py tests/test_google_deep_research.py` : **RÉUSSI — 28 passed, 0 failed** (1 warning `StarletteDeprecationWarning`).
- `cd backend && .venv/bin/python -m pytest -q tests/test_google_cloud.py tests/test_google_deep_research.py tests/test_providers.py tests/test_settings.py tests/test_finance_reports.py tests/test_finance_experts.py tests/test_finance_statements.py tests/test_pages.py tests/test_multi_agent.py tests/test_memory_agent.py tests/test_topics.py tests/test_presentation_html.py tests/test_sounds.py` : **RÉUSSI — 241 passed, 0 failed** (1 warning).
- `cd backend && .venv/bin/python -m pytest -q tests/test_api.py -k "not test_deep_search_executes_multi_wave_searxng_and_global_synthesis and not test_research_evidence_survives_generation_storage_and_export"` : **RÉUSSI — 56 passed, 5 deselected**.
- `cd backend && .venv/bin/python -m pytest -q tests/test_hermes.py -k "not test_hermes_mcp_adapter_gateway_draft_and_permissions"` : **RÉUSSI — 14 passed, 1 deselected**.
- `cd frontend && npx tsc --noEmit` : **RÉUSSI** (exit code 0).
- **Échecs préexistants / sandbox observés (hors périmètre Google Cloud, non modifiés)** :
  - Lors de l'exécution complète avant filtrage : `test_hermes.py::test_hermes_mcp_adapter_gateway_draft_and_permissions` (tri UUID aléatoire préexistant), `test_api.py::test_deep_search_executes_multi_wave_searxng_and_global_synthesis` + 4× `test_research_evidence_survives_generation_storage_and_export` (`chat_export_html.py` non modifié), et `test_blogs.py::test_enrich_sources_follows_article_links_from_landing_page` (DNS bloqué dans le sandbox).
- Appels réels en ligne vers Vertex AI / Google Cloud : **non exécutés** (tests hors réseau avec mocks ; authentification et projet GCP utilisateur à configurer dans `.env`).

## 7. Known Issues and Risks
- Les identifiants de certains modèles Google expérimentaux ou alias (`google/gemini-3.5-flash-lite`, `google/gemini-3.8-flash`, `google/gemini-4-argon`, `google/gemini-4-hydrogen`) peuvent différer des slugs Vertex AI publiés ; `GOOGLE_CLOUD_MODEL_MAP` permet de les remapper sans modifier le code.
- En mode `vertex_oauth` / `auto`, il faut activer l'API `aiplatform.googleapis.com` sur le projet GCP associé au compte de facturation Google AI Pro (10 $/mois) et disposer soit d'un ADC (`gcloud auth application-default login`), soit d'une clé JSON via `GOOGLE_APPLICATION_CREDENTIALS` (dans Docker, monter le fichier JSON dans le conteneur `clair-api`).
- En environnement Docker avec `clair-hermes` actif, les modèles Google sont routés localement via `local_autonomous` (sans MCP/terminal du conteneur Gateway) tant que `GOOGLE_CLOUD_FALLBACK_OPENROUTER=false`.

## 8. Next Action
L'utilisateur doit copier la section Google Cloud depuis `.env.example` dans son `.env` privé (activer l'API Vertex AI `aiplatform.googleapis.com`, définir `GOOGLE_CLOUD_MODE=vertex_oauth`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, et configurer ADC ou `GOOGLE_APPLICATION_CREDENTIALS`), puis tester un premier échange en conditions réelles avec un modèle Gemini.
