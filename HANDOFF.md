# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, analyse fondamentale, MOAT, rapports trimestriels et avis d'experts.
- Le connecteur agentique **Hermes Agent** et la recherche approfondie **Google Deep Research** (Interactions API).

## 2. Current Objective
Routage unifié de **tous les appels aux modèles Google** (`google/*`, `gemini-*`, `imagen-*`, `gemma-*`) vers **Google Cloud** (Vertex AI OAuth2/ADC par défaut, plus `vertex_api_key` et `gemini_api` en option) afin de consommer le crédit mensuel Google Cloud de 10 $/mois inclus avec l'abonnement Google AI Pro, tout en conservant les modèles non-Google sur OpenRouter / leurs fournisseurs natifs.

**Statut** : Implémentation et suite de tests complètes **terminées et vérifiées** (`py_compile` exit 0, `241 passed` sur le cœur + `test_google_cloud.py` / `test_google_deep_research.py`, `56 passed` ciblés sur `test_api.py`, `14 passed` ciblés sur `test_hermes.py`, `npx tsc --noEmit` exit 0). Rappel : la configuration manuelle du `.env` local (projet GCP, activation API `aiplatform.googleapis.com`, ADC ou compte de service JSON) reste à effectuer par l'utilisateur.

## 3. Completed Work
- **Module central Google Cloud (`backend/app/google_cloud.py`)** :
  - Détection & normalisation des IDs Google (`is_google_model`, `normalize_google_model_id` avec support `:free`/`:thinking`, `GOOGLE_CLOUD_MODEL_MAP` et rejet des traversées de chemin).
  - Authentification Vertex AI OAuth2 / ADC via `google-auth==2.62.2` (`_HttpxAuthRequest` sans dépendance `requests`, cache thread-safe avec rafraîchissement automatique avant expiration).
  - Routage unifié (`post_chat_completion`, `open_chat_stream` via `AsyncExitStack`), adaptation des charges OpenAI (suppression `cache_control`, champs OpenRouter et en-têtes `HTTP-Referer`/`X-Title`, conversion `reasoning` → `reasoning_effort`) et traduction complète OpenAI ↔ Gemini natif (`openai_to_gemini_native_request`, `gemini_native_to_openai_dict`, `iter_gemini_sse_as_openai_data`) pour le mode `vertex_api_key`.
  - Génération d'images Google Cloud (`generate_google_cloud_image` : Gemini `:generateContent` avec `responseModalities: ["IMAGE"]` + `imageConfig.aspectRatio`, Imagen `:predict`, validation de signature MIME et limite 10 Mio).
  - Helpers Interactions API (`resolve_interactions_config`, `get_interactions_request_params`, `build_interaction_url`) pour Google Deep Research sur Vertex AI `v1beta1` (OAuth2 Bearer rafraîchi à chaque appel/polling) et Gemini Developer API.
  - Politique stricte sans repli OpenRouter par défaut (`GOOGLE_CLOUD_FALLBACK_OPENROUTER=false`, vérifiée aussi dans `can_fallback_to_model`).
- **Configuration, dépendances & conteneurs (`backend/app/config.py`, `.env.example`, `compose.yaml`, `backend/requirements*.txt`)** :
  - Ajout de `google-auth==2.62.2` et recompilation des lockfiles via `uv` (`requirements.lock.txt`, `requirements-dev.txt`).
  - Ajout dans `Settings` de `google_cloud_mode` (`auto` | `vertex_oauth` | `vertex_api_key` | `gemini_api` | `disabled`), `google_cloud_project`, `google_cloud_location`, `google_application_credentials`, `vertex_api_key`, `google_cloud_fallback_openrouter`, `google_cloud_model_map`, validateurs stricts, rechargement live tolérant (`refresh_from_env_file`) avec alias (`VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `GOOGLE_CLOUD_API_KEY`, `GEMINI_API_KEY`) et exposition du catalogue Google même sans `LLM_API_KEY`.
- **Migration intégrale des moteurs, agents auxiliaires, routeurs & frontend** :
  - `providers.py` (streaming SSE avec extraction `extra_content.google.thought`, 32 appels non-streaming, génération d'images et garde-fous de repli), `multi_agent.py`, `memory_agent.py`, `topic_agent.py` (correction du bug `openrouter_api_key` + URL codée en dur), `blog.py`, `page_bricks.py`, `page_generator.py`, `presentation_html.py`, `finance_dossier.py`, `finance_experts.py`, `finance_moat.py`, `finance_news.py`, `finance_reports.py`.
  - `hermes_agent.py` : support streaming Google Cloud dans `_run_openrouter_turn`, auto-apprentissage et contournement automatique du Gateway Docker externe `clair-hermes` vers `local_autonomous` lorsqu'un modèle Google est utilisé avec Google Cloud actif et sans repli OpenRouter.
  - `google_deep_research.py` : support Vertex AI OAuth2 Interactions API (`locations/global/interactions`) et conservation de `GOOGLE_API_KEY`.
  - Routeurs (`routers/system.py`, `messages.py`, `images.py`, `skills.py`, `sounds.py`, `conversations.py`) et type frontend (`frontend/lib/api.ts`) autorisant l'usage exclusif de Google Cloud sans `LLM_API_KEY` et exposant `features.google_cloud` et `google_cloud_mode`.
- **Travaux antérieurs non commités préservés** :
  - Espace **Marchés Financiers** (`FinanceModal`, MOAT, 31 scores Uncle Stock, valeurs intrinsèques, catalogue EODHD, rapports PDF-OCR Mistral Map-Reduce), **Code Canvas / cLAIr Pages / Briques Préfaites**, et **Ideogram v2** intactement conservés dans l'arbre de travail.

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
