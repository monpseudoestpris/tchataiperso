# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, analyse fondamentale, MOAT, rapports trimestriels et avis d'experts.
- Le connecteur agentique **Hermes Agent** et la recherche approfondie **Google Deep Research** (Interactions API).

## 2. Current Objective
1. Corriger les timeouts `« Le fournisseur IA met trop de temps à répondre ; réessayez. »` sur les requêtes volumineuses ou modèles à raisonnement (`stream_chat_events`, étapes de planification/audit DeepSearch & Mode Apprendre, présentations HTML, missions Hermes).
2. Conserver la compatibilité avec les évolutions précédentes de **cLAIr Pages** (Wizard IA + Mode Encyclopédique Multi-Passes) et du routage **Google Cloud / Vertex AI**.

**Statut** : Correctif des timeouts LLM implémenté et vérifié (`yaml.safe_load`, `py_compile`, `175 passed, 1 deselected` sur `test_providers.py` + `test_settings.py` + `test_google_cloud.py` + `test_hermes.py`). En Docker, reconstruire et relancer `clair-api` (`docker compose up -d --build clair-api`) ou toute la pile (`docker compose up -d --build clair-api clair-web`).

## 3. Completed Work
- **Résolution du timeout sur requêtes LLM volumineuses (`backend/app/providers.py`, `config.py`, `google_cloud.py`, `presentation_html.py`, `hermes_agent.py`, `compose.yaml`, `.env.example`)** :
  - Ajout de `LLM_TIMEOUT_SECONDS` (`llm_timeout_seconds: int = 480`, validé entre `30` et `1800` s, rechargé à chaud dans `refresh_from_env_file`) exposé dans `compose.yaml` et documenté dans `.env.example`.
  - `_llm_stream_timeout(settings)` appliqué à `stream_chat_events` et transmis à `open_chat_stream` (`read=480.0s` par défaut au lieu de `_TIMEOUT=60s`), tout en conservant `_TIMEOUT=60s` pour la recherche web.
  - Fin de flux SSE tolérante après `finish_reason` : si le modèle a déjà émis `finish_reason` (`completed=True`) et que le fournisseur garde la connexion ouverte sans `[DONE]` jusqu'au timeout, `stream_chat_events` vide `ThinkTagSplitter.finalize()` et termine sans erreur.
  - Réhaussement des timeouts LLM secondaires sous-dimensionnés : `_RESEARCH_PLAN_TIMEOUT = 120s` (9 appels de décomposition/planification/validation DeepSearch & Mode Apprendre qui utilisaient `15s`), `_SUMMARY_TIMEOUT = 120s`, `_AUDIT_TIMEOUT = 180s`, `_SOURCE_JUDGE_TIMEOUT = 45s`, `_QUERY_REWRITE_TIMEOUT = 25s`, `_DECISION_TIMEOUT = 15s`, défauts `post_chat_completion=120s` / `open_chat_stream=480s` dans `google_cloud.py`, `presentation_html.py` (120s par défaut au lieu de 45s) et `hermes_agent.py` (`_GATEWAY_STREAM_TIMEOUT` / `_MAX_MISSION_SECONDS` portés de 120s à 300s).
  - Ajout de 5 tests unitaires dédiés dans `tests/test_providers.py` et `tests/test_settings.py`.
- **Mode Encyclopédique Multi-Passes & Wizard IA (`cLAIr Pages`, travaux non commités préexistants conservés)** :
  - Génération multi-passes (`backend/app/page_multipass.py`), Wizard (`backend/app/page_wizard.py`), recherche web SearXNG (`backend/app/page_web_search.py`), `frontend/components/web-page-modal.tsx` et `frontend/lib/api.ts`.

## 4. Key Decisions
- **Vertex AI (`vertex_oauth`) choisi comme mode Google Cloud principal** : le crédit mensuel de 10 $/mois inclus avec Google AI Pro est crédité sur le compte de facturation GCP, consommé nativement en post-paiement par Vertex AI (`aiplatform.googleapis.com` via OAuth2/ADC ou Service Account JSON, endpoints `endpoints/openapi` et `publishers/google/models`). `vertex_api_key` (Express/API Key natif) et `gemini_api` (`generativelanguage.googleapis.com`) sont supportés en complément.
- **Mode `auto` prudent** : active `vertex_oauth` si `GOOGLE_CLOUD_PROJECT` est défini, ou `vertex_api_key` si `VERTEX_API_KEY` est défini, sans détourner `GOOGLE_API_KEY` seul (sauf `GOOGLE_CLOUD_MODE=gemini_api`), préservant ainsi la compatibilité des configurations Deep Research existantes.
- **Politique stricte sans repli OpenRouter par défaut (`GOOGLE_CLOUD_FALLBACK_OPENROUTER=false`)** : une erreur Google Cloud lève `ProviderError` (aucune bascule silencieuse vers OpenRouter ni vers un `default_model` non-Google via `can_fallback_to_model`). Opt-in possible via `.env`.
- **Bypass Hermes Gateway pour les modèles Google** : le conteneur externe `clair-hermes` étant configuré avec OpenRouter, `hermes_agent.stream_hermes_mission` bascule vers `local_autonomous` pour tout modèle Google lorsque Google Cloud est actif sans repli OpenRouter.
- **Plafonnement `max_tokens` pour Google Cloud / Vertex AI (`backend/app/google_cloud.py`)** : les modes longs (Code Canvas `131072`, DeepSearch `131072`, Apprendre `98304`) dépassaient la limite de sortie de Vertex AI (`65536` sur Gemini 2.5/3/4, `8192` sur Gemini 1.5/2.0), provoquant un `HTTP 400`. `adapt_openai_payload_for_google` plafonne désormais `max_tokens` et `max_completion_tokens` selon le modèle Google, et `open_chat_stream` journalise l'extrait d'erreur HTTP avant `check_response`.
- **Préservation de `httpx.AsyncClient` côté appelants & travail antérieur** : les modules créent leur `httpx.AsyncClient` et le passent en `client=client` aux helpers `google_cloud.py` pour garder compatibles les monkeypatches des tests existants ; les travaux non commités préexistants (FinanceModal, Code Canvas, Ideogram) restent intacts.

## 5. Modified Files
- Modifiés (Correctif timeouts LLM) :
  - `backend/app/config.py`, `.env.example`, `compose.yaml` : ajout et validation de `LLM_TIMEOUT_SECONDS` (défaut `480`, bornes `30..1800`, rechargement live).
  - `backend/app/providers.py` : `_llm_stream_timeout`, application à `stream_chat_events` / `open_chat_stream`, gestion propre des flux déjà terminés (`completed=True`) en cas de `TimeoutException` avant `[DONE]`, et réhaussement de `_RESEARCH_PLAN_TIMEOUT` (120s), `_SUMMARY_TIMEOUT` (120s), `_AUDIT_TIMEOUT` (180s), `_SOURCE_JUDGE_TIMEOUT` (45s), `_QUERY_REWRITE_TIMEOUT` (25s), `_DECISION_TIMEOUT` (15s).
  - `backend/app/google_cloud.py` : défauts `post_chat_completion` (`120.0`) et `open_chat_stream` (`480.0`).
  - `backend/app/presentation_html.py` : délai par défaut porté à 120s (`min(llm_timeout_seconds, 180.0)`), compatible avec `settings.llm_timeout`.
  - `backend/app/hermes_agent.py` : `_GATEWAY_STREAM_TIMEOUT` et `_MAX_MISSION_SECONDS` portés à `300.0`s.
  - `backend/tests/test_providers.py`, `backend/tests/test_settings.py` : 5 nouveaux tests unitaires sur `llm_timeout_seconds`, fin de flux sans `[DONE]`, erreur avant complétion sans fuite de secret, et timeout de `plan_report_outline`.
- Conservés intacts (travaux non commités préexistants) :
  - `backend/app/page_multipass.py`, `backend/app/page_wizard.py`, `backend/app/page_web_search.py`, `backend/app/page_generator.py`, `backend/app/page_service.py`, `backend/app/routers/pages.py`, `backend/app/schemas.py`, `backend/tests/test_pages.py`, `frontend/components/web-page-modal.tsx`, `frontend/lib/api.ts`.

## 6. Verification
- `cd backend && .venv/bin/python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('../compose.yaml').read_text())" && .venv/bin/python -m py_compile app/config.py app/providers.py app/google_cloud.py app/presentation_html.py app/hermes_agent.py tests/test_providers.py tests/test_settings.py && .venv/bin/python -m pytest -q tests/test_providers.py tests/test_settings.py tests/test_google_cloud.py tests/test_hermes.py -k "not test_hermes_mcp_adapter_gateway_draft_and_permissions"` : **RÉUSSI — 175 passed, 1 deselected** (1 warning `StarletteDeprecationWarning`).
- Non exécutés lors de cette session :
  - `test_hermes_mcp_adapter_gateway_draft_and_permissions` (désélectionné, échec de tri UUID préexistant documenté), autres fichiers de tests backend (`test_api.py`, `test_pages.py`, etc.), `npx tsc --noEmit` (aucune modification frontend effectuée), appels réseau réels vers OpenRouter / Vertex AI.

## 7. Known Issues and Risks
- Les identifiants de certains modèles Google expérimentaux ou alias (`google/gemini-3.5-flash-lite`, `google/gemini-3.8-flash`, `google/gemini-4-argon`, `google/gemini-4-hydrogen`) peuvent différer des slugs Vertex AI publiés ; `GOOGLE_CLOUD_MODEL_MAP` permet de les remapper sans modifier le code.
- En mode `vertex_oauth` / `auto`, il faut activer l'API `aiplatform.googleapis.com` sur le projet GCP associé au compte de facturation Google AI Pro (10 $/mois) et disposer soit d'un ADC (`gcloud auth application-default login`), soit d'une clé JSON via `GOOGLE_APPLICATION_CREDENTIALS` (dans Docker, monter le fichier JSON dans le conteneur `clair-api`).
- En environnement Docker avec `clair-hermes` actif, les modèles Google sont routés localement via `local_autonomous` tant que `GOOGLE_CLOUD_FALLBACK_OPENROUTER=false`.
- Si l'application tourne actuellement dans Docker, le conteneur `clair-api` doit être reconstruit/redémarré pour prendre en compte les nouveaux délais Python et `LLM_TIMEOUT_SECONDS`.

## 8. Next Action
Reconstruire et relancer les services Docker (`docker compose up -d --build clair-api clair-web`) puis tester une grosse demande dans le tchat (ou avec un modèle à raisonnement / DeepSearch / Code Canvas) pour confirmer l'absence de timeout prématuré.
