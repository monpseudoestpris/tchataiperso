# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA avec modèle, prompt, entrées et sorties attendues).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, indicateurs personnalisés, actualités, rapports trimestriels et onglet **MOAT** (travaux antérieurs non committés conservés).

## 2. Current Objective
Intégration des applications **Code Canvas** dans **cLAIr Pages (« Mes Apps »)**, système de **Briques Préfaites** (12 modèles prêts à l'emploi) et **Éditeur de Diagramme d'Architecture d'Application** (`🗺️ Diagramme`) :
1. Permettre l'intégration en 1 clic d'une application générée dans **Code Canvas** vers **cLAIr Pages** sous l'onglet dédié **🧩 Mes Apps** (avec conservation des fichiers sources multi-fichiers `canvas_files` et réouverture dans le Canvas).
2. Permettre de concevoir l'application visuellement dans un **Diagramme d'Architecture** (`ui_input` ↔ `ai_brick` ↔ `ui_output`) avant ou pendant la génération du code, de façon à ce que les agents IA propulsent directement les composants propres de l'interface (bulles, jauges, scores) sans bulle flottante superposée (`show_widget: false` par défaut).

**Statut** : Implémentation terminée et vérifiée par build TypeScript/Next.js, ESLint ciblé et tests pytest backend.

## 3. Completed Work
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
  - `backend/tests/test_pages.py`
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

## 6. Verification
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_pages.py backend/tests/test_migrations.py -v` : **RÉUSSI — 20 passed, 1 warning** (inclut `test_canvas_app_integration_and_ai_bricks`, `test_execute_brick_with_mocked_llm_json_schema`, `test_chatbot_brick_with_history_and_widget_style`, `test_propose_app_diagram_and_default_internal_brick`, `test_diagram_interview_selects_bricks_and_asks_questions` et `test_finance_eod_brick_execution_and_interview`).
- `npx --prefix frontend eslint --config frontend/eslint.config.mjs --max-warnings 0 frontend/lib/canvas-bricks.ts frontend/lib/canvas-diagram.ts frontend/components/canvas-bricks-modal.tsx` : **RÉUSSI** (0 erreur, 0 warning).
- `npm --prefix frontend run typecheck && npm --prefix frontend run build` : **RÉUSSI** (0 erreur TypeScript, build Next.js 16.4.2 réussi après les dernières éditions frontend).
- Vérification interactive manuelle en navigateur : **non exécutée**.

## 7. Known Issues and Risks
- Les pages publiques partagées (`/p/{token}`) restent servies en CSP stricte hors authentification : les briques Agent IA nécessitent d'être exécutées depuis l'environnement authentifié (**Aperçu Code Canvas** ou **cLAIr Pages → Mes Apps**).
- Le lint ESLint global (`npm --prefix frontend run lint`) n'a pas été relancé sur l'ensemble des anciens fichiers du dépôt (erreurs préexistantes documentées précédemment).

## 8. Next Action
Tester le parcours bout-en-bout en navigateur : générer une application web dans le tchat en mode **Code · Canvas**, lui adjoindre une brique **Agent IA** (modèle, prompt, entrées, sorties JSON), la câbler ou la tester via le widget intégré, puis cliquer sur **« Intégrer à Mes Apps »** pour vérifier l'ouverture directe dans **cLAIr Pages → Mes Apps**.
