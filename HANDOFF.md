# Relais — 14 novembre 2026

## 1. Project Overview
clAIr : tchat IA francophone, apprentissage, recherche, médias, génération de pages HTML et orchestration d'agents autonomes. Frontend Next.js 16.4 / React 19 / TypeScript ; backend FastAPI / SQLAlchemy / PostgreSQL (SQLite en dev).

## 2. Current Objective
Intégration complète et sécurisée de l'outil `clair_create_page` entre cLAIr (`local_autonomous` & Hermes Gateway) et le conteneur `clair-hermes` via MCP HTTP (`params._meta` authentifié par jeton de mission) — **objectif atteint et vérifié en conditions réelles**.

## 3. Completed Work
- **Propagation authentifiée du contexte de mission (`backend/app/hermes_agent.py`, `backend/app/routers/hermes_mcp.py`)** :
  - Chaque `GatewayMissionLease` génère un `mission_token` aléatoire unique (`secrets.token_urlsafe(32)`), transmis uniquement par en-tête HTTP transport (`X-Clair-Mission-Token`) vers Hermes Gateway (jamais dans `system_prompt`, `messages`, `tools` ou arguments LLM).
  - `hermes_mcp.py` exige à la fois un `session_id` valide et un `mission_token` correspondant (`hmac.compare_digest`), extraits de `params._meta` ou des en-têtes HTTP, et refuse tout appel avec contexte absent, expiré, inconnu ou usurpé (ainsi que toute tentative via `params.arguments`).
- **Patch reproductible du runtime Hermes (`hermes/apply_mission_context_patch.py`, `hermes/Dockerfile`, `compose.yaml`)** :
  - `api_server_openai_routes.py` capture `X-Hermes-Session-Id` et `X-Clair-Mission-Token` dans un `contextvars.ContextVar` isolé par tâche HTTP et propagé au thread worker (`contextvars.copy_context().run`).
  - `tools/mcp_tool_handlers.py` lit ce `ContextVar` sur le thread de l'agent avant bascule sur la boucle MCP et le transmet via `server.session.call_tool(..., meta=mission_meta)` dans `params._meta`.
- **Correction de configuration Docker Compose (`compose.yaml`, `backend/app/config.py`)** :
  - `HERMES_API_URL: http://clair-hermes:8642` dans `compose.yaml` et retrait de `"hermes_api_url"` de `str_fields` dans `Settings.refresh_from_env_file()` afin que le `.env` local (`127.0.0.1:8642`) n'écrase pas la cible interne Docker.
- **Script de vérification bout-en-bout (`scripts/verify_hermes_e2e.sh`)** :
  - Exécute les tests unitaires (`pytest backend/tests/test_hermes.py`) puis un appel réel `POST /api/hermes/run` (`execution_mode="gateway"`) → `clair-hermes` → MCP `tools/call` (`params._meta`) → `clair_create_page` → PostgreSQL (`is_published=False`).

## 4. Key Decisions
- **Double barrière d'authentification MCP** : le Bearer global (`HERMES_API_KEY`) protège le canal Hermes ↔ cLAIr, tandis que `(session_id, mission_token)` dans `params._meta` authentifie individuellement chaque mission et garantit l'isolation stricte entre utilisateurs concurrents.
- **Séparation découverte / exécution** : `tools/list` sans session (Bearer valide) expose les schémas pour la découverte globale au démarrage d'Hermes sans accorder aucun droit d'exécution.

## 5. Modified Files
- `backend/app/config.py` : retrait de `hermes_api_url` de `refresh_from_env_file()`.
- `backend/app/hermes_agent.py` : transmission de `X-Clair-Mission-Token` dans les en-têtes HTTP vers Gateway.
- `backend/app/routers/hermes_mcp.py` : ajout de `mission_token` sur `GatewayMissionLease`, validation stricte `hmac.compare_digest` via `params._meta` / en-têtes, suppression du repli `params.arguments`.
- `hermes/apply_mission_context_patch.py` & `hermes/Dockerfile` : patch minimal et reproductible du runtime Hermes (`ContextVar` → `params._meta`).
- `compose.yaml` : `build: ./hermes` pour `clair-hermes` et `HERMES_API_URL: http://clair-hermes:8642` pour `clair-api`.
- `backend/tests/test_hermes.py` : tests d'isolation multi-utilisateurs avec usurpation de `session_id` sans/mauvais `mission_token` et vérification de non-fuite du secret vers le LLM.
- `scripts/verify_hermes_e2e.sh` : script unique de vérification unitaire + bout-en-bout réel.

## 6. Verification
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_hermes.py -v` : **15 passed** en 9.51s.
- `./scripts/verify_hermes_e2e.sh` : exécuté contre la pile Docker Compose active (`clair-api`, `clair-hermes`, `clair-db`).

## 7. Known Issues and Risks
- Lors de l'activation de `compose.cloud.yaml` (si `SSL_CERT_FILE` est défini dans le shell hôte), `docker compose build` avec Bake peut demander `--allow=fs.read=/etc/ssl/certs/ca-certificates.crt` ; construire directement via `docker compose -f compose.yaml build` contourne ce blocage local.

## 8. Next Action
Ouvrir `http://localhost:3001` et tester une mission utilisateur complète avec l'outil `cLAIr Pages` en mode `Gateway Hermes`.
