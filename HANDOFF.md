# Relais — 15 novembre 2026

## 1. Project Overview
clAIr : tchat IA francophone, apprentissage, recherche, médias, génération de pages HTML autonomes (`cLAIr Pages`) et orchestration d'agents (Hermes Agent / NousResearch). Frontend Next.js 16.4 / React 19 / TypeScript ; backend FastAPI / SQLAlchemy / PostgreSQL (SQLite en dev/tests).

## 2. Current Objective
Résolution du blocage Hermes Gateway / MCP lors de la création de brouillons cLAIr Pages (`Délai dépassé de 90 s côté serveur` / faux signalement de panne serveur par Hermes Agent) et support de l'injection directe de contenu HTML pré-généré sans régénération LLM — **terminé et vérifié**.

## 3. Completed Work
- **Diagnostic de la cause racine** :
  - Hermes Agent invoquait l'outil MCP `clair_create_page` exposé par cLAIr.
  - L'outil imposait un `timeout_seconds=90.0` hardcodé dans `backend/app/tool_registry.py` alors que la génération de page HTML par LLM (`page_generator.py`) applique un délai `_TIMEOUT=180.0s`.
  - Lors d'une génération dense (ex: tableau de 20 figures de style, 3 exemples par ligne) ou avec un modèle distant volumineux (OpenRouter / Hermes 405B), la génération dépassait 90s, déclenchant un `asyncio.TimeoutError` traduit en `"Délai d'exécution dépassé (90 s) pour clair_create_page"`. Hermes interprétait cette coupure comme un serveur en panne.
  - De plus, Hermes avait déjà rédigé et calibré localement les fichiers HTML/PDF dans son conteneur (`/opt/data/`), mais `clair_create_page` ne permettait pas de sauvegarder directement du HTML pré-généré, forçant une 2nde génération LLM inutile.
- **Support HTML direct et extension du timeout (`backend/app/tool_registry.py` & `backend/app/page_service.py`)** :
  - `ClairCreatePageInput` : ajout des champs optionnels `html_content` (jusqu'à 500k caractères) et `layout_style` (ex: `a4_1p`), avec validation exigeant au moins `content` ou `html_content`.
  - `tool_registry.py` : augmentation du timeout d'exécution de `clair_create_page` de 90s à 180s pour s'aligner avec le timeout LLM de `page_generator.py`.
  - `page_service.py` : `create_draft_web_page` détecte `html_content`, extrait le titre si omis via `extract_title_from_html`, applique la sécurisation et le runtime A4 via `sanitize_and_enhance_html`, et enregistre immédiatement le brouillon en base en quelques millisecondes sans appel LLM.
- **Consignes système Hermes (`backend/app/hermes_agent.py`)** :
  - Mise à jour du prompt système transmis à Hermes l'invitant à passer `html_content` et `layout_style` directement lorsqu'il a déjà composé le HTML complet.
- **Tests unitaires et d'intégration (`backend/tests/test_hermes.py`)** :
  - Validation du nouveau timeout à 180s.
  - Test d'enregistrement direct d'un brouillon A4 avec `html_content` via l'adaptateur MCP (`tools/call`), vérifiant l'insertion en base sans appel à `generate_page_html`.

## 4. Key Decisions
- **Sauvegarde immédiate si `html_content` est présent** : évite tout gaspillage de tokens et tout risque de timeout en réutilisant le HTML déjà calibré par Hermes. Le code passe tout de même par `sanitize_and_enhance_html` pour fermer les balises orphelines, sécuriser les liens (`target="_blank"`, `rel="noopener"`) et greffer le runtime A4 clAIr.
- **Alignement du timeout à 180s** : si l'agent ne fournit que du markdown dans `content`, le délai d'attente du registry correspond désormais au plafond réseau httpx du générateur de page.

## 5. Modified Files
- `backend/app/tool_registry.py` (schéma `ClairCreatePageInput`, passage de `html_content`/`layout_style`, timeout à 180s)
- `backend/app/page_service.py` (prise en charge directe de `html_content` via `sanitize_and_enhance_html`)
- `backend/app/hermes_agent.py` (directive système pour renseigner `html_content`)
- `backend/tests/test_hermes.py` (tests du timeout et de la création directe par `html_content`)
- `HANDOFF.md`

## 6. Verification
- `npm --prefix frontend run build` : **passé (exit 0)** — Next.js 16.4 Turbopack & TypeScript sans erreur.
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_hermes.py -v` : **15 passed, 1 warning (exit 0)**.
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_pages.py -v` : **12 passed, 1 warning (exit 0)**.

## 7. Known Issues and Risks
- Les fichiers générés lors de la session précédente d'Hermes (`fiche-figures-de-style-A4.*`) se trouvent dans le volume Docker `hermes_data` du conteneur `clair-hermes` sous `/opt/data/`. Ils peuvent être extraits sur l'hôte via `docker compose cp clair-hermes:/opt/data/... ./`.

## 8. Next Action
Informer l'utilisateur du diagnostic, lui donner la commande Docker pour récupérer immédiatement ses fichiers prêts, et lui expliquer les correctifs appliqués.