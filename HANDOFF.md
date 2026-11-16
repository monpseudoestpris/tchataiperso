# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA avec modèle, prompt, entrées et sorties attendues).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, indicateurs personnalisés, actualités, rapports trimestriels et onglet **MOAT** (travaux antérieurs non committés conservés).

## 2. Current Objective
En mode **Conseil IA (Multi-Agents)**, utiliser par défaut le modèle IA sélectionné dans le tchat (tout en conservant la possibilité de personnaliser un modèle par agent si souhaité).

**Statut** : Implémentation terminée et vérifiée par `pytest` (`test_multi_agent.py`) et `tsc --noEmit`.

## 3. Completed Work
- **Conseil IA aligné sur le modèle sélectionné (`backend/app/schemas.py`, `backend/app/multi_agent.py`, `backend/app/routers/messages.py`, `backend/tests/test_multi_agent.py`, `frontend/lib/api.ts`, `frontend/components/multi-agent-modal.tsx`, `frontend/components/chat-app.tsx`)** :
  - Ajout de `use_selected_model` sur `MultiAgentConfig` (`False` par défaut côté schéma API pour compatibilité rétroactive, `true` par défaut côté UI).
  - `resolve_model` accepte désormais `fallback_model` (le modèle sélectionné de la requête/conversation) avant de se replier sur `settings.default_model`, et `_effective_agent_model` applique le modèle sélectionné à tous les agents (modes `synthesis`, `debate`, `dialectic`/`contradictory` et mode démo) lorsque `use_selected_model` est actif.
  - Dans `MultiAgentModal`, les agents initiaux, les équipes prédéfinies et la génération de persona IA utilisent par défaut `defaultModel` (le modèle sélectionné dans le tchat), avec une case à cocher *« Utiliser le modèle IA sélectionné dans le tchat (…) pour tous les agents »* (qui se décoche automatiquement si l'utilisateur choisit manuellement un modèle différent pour un agent).
  - Dans `chat-app.tsx`, l'envoi du message synchronise les modèles des agents sur le modèle actif du tchat tant que `use_selected_model !== false`.
  - **Reprise d'historique en cours de conversation (`backend/app/routers/messages.py`, `backend/app/multi_agent.py`, `backend/tests/test_multi_agent.py`)** : transmission de `history[:-1]` (tous les tours non résumés, y compris `extracted_text` des pièces jointes) et de `conversation.summary` via `_format_conversation_context` (plafonné à 24 000 car.) à tous les agents, au synthétiseur en mode `synthesis`, et à tous les intervenants en modes `debate` et `dialectic`/`contradictory`.
  - **Sauvegarde des personnalités & Panel de sélection (`backend/app/models.py`, `backend/migrations/versions/0023_add_agent_personas.py`, `backend/app/cli.py`, `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/routers/agent_teams.py`, `backend/app/multi_agent.py`, `frontend/lib/api.ts`, `frontend/components/multi-agent-modal.tsx`)** :
    - Table `agent_personas` + endpoints `POST /api/agent-teams/personas`, `DELETE /api/agent-teams/personas/{id}` et inclusion dans `GET /api/agent-teams`.
    - Enrichissement de `DEFAULT_AGENT_TEMPLATES` avec des catégories (`science`, `politique`, `créatif`, `métier`, `philosophie`) et ajout de 13 nouvelles personnalités (Marie Curie, Richard Feynman, Alan Turing, Ada Lovelace, Nikola Tesla, Simone Veil, Nelson Mandela, Nicolas Machiavel, Robert Badinter, Salvador Dalí, Hayao Miyazaki, Jules Verne, Frida Kahlo).
    - Nouvel onglet **« Panel de Personnalités »** dans `MultiAgentModal` avec filtres par catégorie, recherche, ajout/retrait/remplacement en 1 clic dans le conseil actif, sauvegarde automatique lors de la génération IA et bouton *« Sauver »* sur chaque carte d'agent.
- **Schéma SQLAlchemy & Migration Alembic (`0022_add_webpage_apps_and_bricks`)** :
  - Ajout des colonnes `kind` (`"page"` | `"app"`) et `bricks` (`JSON`) sur `web_pages`, et `canvas_files` (`JSON`) sur `web_page_versions` dans `backend/app/models.py`, `backend/migrations/versions/0022_add_webpage_apps_and_bricks.py`, `backend/app/cli.py` et initialisation idempotente au démarrage dans `backend/app/main.py`.
- **Service Backend des Briques Préfaites & Diagramme IA (`backend/app/page_bricks.py`)** :
  - `normalize_bricks` (`show_widget=False` par défaut, support `finance_data_enabled` / `finance_eod_agent`), `build_bricks_prompt_context`, `execute_page_brick` (collecte des données boursières réelles EODHD / Yahoo Finance, calcul des indicateurs techniques `SMA20`, `SMA50`, `RSI14`, `MACD` et signaux MOAT quantitatifs via `_fetch_brick_finance_context` / `_compute_technical_indicators_summary`, prise en charge de `_history` multi-tours, recherche web SearXNG optionnelle), `propose_app_diagram`, `interview_app_diagram`, `build_bricks_runtime_js` et `inject_bricks_runtime_html`.
- **API REST & Services Pages (`backend/app/`)** :
  - Extension de `schemas.py`, `serializers.py`, `page_runtime.py`, `page_service.py`, `routers/pages.py` et `context.py` (`CODE_MODE_PROMPT` interdisant les réponses IA simulées en dur) pour supporter `kind`, `html_content`, `canvas_files`, `bricks`, `POST /api/pages/bricks/execute`, `POST /api/pages/diagram/propose` et `POST /api/pages/diagram/interview`.
- **Frontend Canvas, Diagramme, Briques & Mes Apps (`frontend/`)** :
  - `frontend/lib/canvas-diagram.ts` : types `AppDiagram` / `DiagramNode` / `DiagramEdge`, presets (`DIAGRAM_PRESETS` dont *Bot de l'App + Jauge & Score type NiaisBot* et *Cockpit Boursier EOD & Indicateurs*), synchronisation bidirectionnelle `Diagram <-> PageBrick[]` et compilateur `buildAppPromptFromDiagram`.
  - `frontend/components/canvas-diagram-editor.tsx` (+ `.module.css`) : éditeur visuel interactif (génération de diagramme par IA, glisser-déposer des blocs, flèches SVG avec variables d'entrée/sortie, inspecteur modèle/prompt/entrées/sorties, bouton **« Générer l'App depuis ce Diagramme »** / **« Câbler ce diagramme dans l'App »**).
  - `frontend/lib/canvas-bricks.ts` : types `PageBrick`, catalogue de **16 briques prêtes à l'emploi** (`PREMADE_BRICK_TEMPLATES` incluant 4 briques **Finance & Bourse** : Cotation EOD & Indicateurs, Analyste Fondamental Bourse, Évaluateur MOAT Boursier, Veille Boursière & Catalyseurs), `injectBrickIntoCanvasHtml`, `buildBrickWiringPrompt` et runtime client `buildBricksClientRuntimeScript`.
  - `frontend/lib/code-canvas.ts` & `frontend/lib/api.ts` : injection du runtime des briques dans `buildCanvasPreviewHtml` et ajout de `executePageBrick` + `proposeAppDiagram`.
  - `frontend/components/canvas-bricks-modal.tsx` (+ `.module.css`) : galerie filtrable par catégorie des 12 briques prêtes à l'emploi, choix du style de widget, configurateur complet, test en direct, insertion directe et câblage assisté par IA.
  - `frontend/components/code-canvas.tsx` & `frontend/app/globals.css` : onglet **`🗺️ Diagramme`** (actif par défaut quand le Canvas est vide) aux côtés d'**Éditeur** et **Aperçu**, synchronisation avec les briques, boutons **« Briques IA »** et **« Intégrer à Mes Apps »**, écouteur `postMessage`.
  - `frontend/components/web-page-modal.tsx` (+ `.module.css`) & `frontend/components/chat-app.tsx` : onglets **📄 Mes Pages** / **🧩 Mes Apps**, gestion des briques, bouton **« Ouvrir dans Canvas »**, lancement direct depuis le diagramme via `onRunPrompt` et persistance de session Canvas via `canvasSessionKey`.
- **Relances en fin de message (`backend/app/context.py`, `backend/app/base_prompt.py`, `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/routers/messages.py`, `frontend/lib/api.ts`, `frontend/components/chat-app.tsx`)** :
  - Ajout du paramètre `followup_questions` (`bool = False` par défaut) côté schéma API, `build_context` et routeur `/messages`, avec bouton toggle **« Relances »** dans la barre d'outils du chat (désactivé par défaut).
  - Lorsqu'il est activé, injection de `FOLLOWUP_QUESTIONS_PROMPT` demandant au moins 5 pistes de relance (5 à 6 puces) panachant **questions** et **affirmations / réponses courtes** rédigées **à la 1re personne du point de vue de l'utilisateur** répondant à l'agent ; lorsqu'il est désactivé, injection de `NO_FOLLOWUP_QUESTIONS_PROMPT`, suppression des blocs `### 💡 Questions connexes` des messages assistants de l'historique transmis au LLM (anti-mimétisme) et conditionnement de la réponse démo dans `routers/messages.py`. Retrait également de la consigne automatique de `SYSTEM_PROMPT`, `BASE_USER_PROMPT` et des `users.system_prompt` existants via nettoyage SQL au démarrage.
- **Plafond de sortie en mode Code Canvas (`backend/app/config.py`, `backend/app/providers.py`, `.env.example`, `backend/tests/test_providers.py`)** :
  - Ajout de `code_mode_max_tokens: int = 131072` (`CODE_MODE_MAX_TOKENS=131072` dans `.env.example`) et remplacement du plafond fixe `8192` dans `stream_chat_events` pour éviter la troncature des fichiers générés (notamment `.js`) avec les modèles à réflexion (ex. Gemini Hydrogen).
- **Aperçu Code Canvas & visibilité des fichiers Canvas par le LLM (`frontend/lib/code-canvas.ts`, `frontend/components/code-canvas.tsx`, `frontend/components/web-page-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/lib/api.ts`, `backend/app/schemas.py`, `backend/app/context.py`, `backend/app/routers/messages.py`, `backend/tests/test_context.py`)** :
  - Refonte de `buildCanvasPreviewHtml` pour injecter les feuilles CSS et scripts JS **à leur emplacement exact** dans `index.html` (respect de l'ordre des `<script src>`, gestion des `<script defer>` dans `<head>`, échappement `</script>`, replacers `() => ...`, et `importmap` pour les modules ES).
  - Ajout de `allow-same-origin allow-downloads` sur les iframes `sandbox` de `CodeCanvas` et `allow-downloads` sur `WebPageModal` (évite les blocages `localStorage` et export/téléchargement dans l'aperçu).
  - Transmission des fichiers actifs du Canvas (`canvas_files` dans `SendMessage` / `streamMessage`, y compris éditions manuelles et apps ouvertes depuis *Mes Apps* sans réinitialiser `canvasImportedApp` lors des mises à jour) et injection dédiée dans `build_context` (jusqu'à 160 000 car.) pour que le LLM voie toujours l'état courant du Canvas même après résumé de l'historique.

## 4. Key Decisions
- **Moteur interne de l'App par défaut (`show_widget: false`)** : les briques IA ne superposent plus de bouton flottant sur l'interface de l'app par défaut ; elles servent de cerveau appelé par les contrôles natifs de l'application (`window.clair.runBrick`), avec option explicite *« Bulle flottante de test »* si souhaitée.
- **Conception visuelle par Diagramme (`AppDiagram`)** : permet de définir en amont les composants UI d'entrée, les nœuds Agent IA (modèle, prompt, entrées, sorties JSON) et les sorties UI (bulles, jauges, scores) avant de compiler une spécification stricte interdisant les fausses réponses simulées en dur.
- **Pont `postMessage` parent ↔ iframe (`CLAIR_BRICK_CALL` / `CLAIR_BRICK_RESULT`)** : évite toute exposition de clés API ou de jetons d'authentification dans le code HTML généré.
- **Conservation des modifications non commitées antérieures** (travaux `FinanceModal`/MOAT et `Ideogram v2`) intactes dans l'arbre de travail.

## 5. Modified Files
- Créés (backend) :
  - `backend/migrations/versions/0022_add_webpage_apps_and_bricks.py`
  - `backend/app/page_bricks.py`
- Modifiés (backend) :
  - `backend/app/cli.py`
  - `backend/app/models.py`
  - `backend/app/main.py`
  - `backend/app/schemas.py`
  - `backend/app/serializers.py`
  - `backend/app/page_runtime.py`
  - `backend/app/page_service.py`
  - `backend/app/routers/pages.py`
  - `backend/app/context.py`
  - `backend/app/config.py`
  - `backend/app/providers.py`
  - `backend/tests/test_pages.py`
  - `backend/tests/test_providers.py`
  - `.env.example`
- Créés (frontend) :
  - `frontend/lib/canvas-bricks.ts`
  - `frontend/lib/canvas-diagram.ts`
  - `frontend/components/canvas-bricks-modal.tsx`
  - `frontend/components/canvas-bricks-modal.module.css`
  - `frontend/components/canvas-diagram-editor.tsx`
  - `frontend/components/canvas-diagram-editor.module.css`
- Modifiés (frontend) :
  - `frontend/lib/code-canvas.ts`
  - `frontend/lib/api.ts`
  - `frontend/components/code-canvas.tsx`
  - `frontend/components/web-page-modal.tsx`
  - `frontend/components/web-page-modal.module.css`
  - `frontend/components/chat-app.tsx`
  - `frontend/app/globals.css`

- Modifiés (scripts) :
  - `scripts/start.sh` : point d'entrée unifié (`prod`, `dev`, `local`, `stop`, `logs`, `status`, `--lan`) partageant la même BDD PostgreSQL et les mêmes uploads entre `dev` et `prod`.

## 6. Verification
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_multi_agent.py -v` : **RÉUSSI — 6 passed, 1 warning**.
- `python3 -m py_compile backend/app/schemas.py backend/app/multi_agent.py backend/app/routers/messages.py` : **RÉUSSI**.
- `npm --prefix frontend run typecheck` : **RÉUSSI** (0 erreur TypeScript).
- `python3 -m py_compile backend/app/config.py backend/app/providers.py` : **RÉUSSI**.
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_providers.py -k "code_canvas_mode or deep_search_mode" -v` : **RÉUSSI — 2 passed, 135 deselected**.
- `npm --prefix frontend run typecheck` : **RÉUSSI** (0 erreur TypeScript après mise à jour de `chat-app.tsx`).
- `python3 -m py_compile backend/app/base_prompt.py backend/app/context.py backend/app/main.py` : **RÉUSSI**.
- `backend/.venv/bin/pytest` : **non exécuté dans le sandbox** (l'interpréteur Python du `.venv` pointe vers `/home/chabert/.local/share/uv/python/...` hors workspace).
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_pages.py backend/tests/test_migrations.py -v` (session précédente) : **RÉUSSI — 20 passed, 1 warning**.
- `npx --prefix frontend eslint --config frontend/eslint.config.mjs --max-warnings 0 frontend/lib/canvas-bricks.ts frontend/lib/canvas-diagram.ts frontend/components/canvas-bricks-modal.tsx` : **RÉUSSI** (0 erreur, 0 warning).
- `npm --prefix frontend run typecheck && npm --prefix frontend run build` : **RÉUSSI** (0 erreur TypeScript, build Next.js 16.4.2 réussi après les dernières éditions frontend).
- Vérification interactive manuelle en navigateur : **non exécutée**.

## 7. Known Issues and Risks
- Les pages publiques partagées (`/p/{token}`) restent servies en CSP stricte hors authentification : les briques Agent IA nécessitent d'être exécutées depuis l'environnement authentifié (**Aperçu Code Canvas** ou **cLAIr Pages → Mes Apps**).
- Le lint ESLint global (`npm --prefix frontend run lint`) n'a pas été relancé sur l'ensemble des anciens fichiers du dépôt (erreurs préexistantes documentées précédemment).

## 8. Next Action
Tester le parcours bout-en-bout en navigateur : générer une application web dans le tchat en mode **Code · Canvas**, lui adjoindre une brique **Agent IA** (modèle, prompt, entrées, sorties JSON), la câbler ou la tester via le widget intégré, puis cliquer sur **« Intégrer à Mes Apps »** pour vérifier l'ouverture directe dans **cLAIr Pages → Mes Apps**.
