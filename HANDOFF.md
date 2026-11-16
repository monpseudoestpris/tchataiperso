# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant un espace **Marchés Financiers** (`FinanceModal`) avec données boursières (EODHD / Yahoo Finance), analyse technique (`lightweight-charts`, `technicalindicators`), veille d'actualités et analyse de documents.

## 2. Current Objective
Extension de la modale **Marchés Financiers** (`FinanceModal`) selon le plan validé dans `implementation_plan.md` + ajout de l'onglet **MOAT** :
1. Tableau de suivi d'actions personnalisé avec variations **1J, 1S, 1M, 3M, 1A** et ouverture directe du graphique + indicateurs au clic sur une ligne.
2. Créateur/éditeur d'indicateurs techniques personnalisés façon TradingView (formules sans `eval`, persistance par utilisateur).
3. Recherche, synthèse IA Markdown et archivage en base des actualités par action.
4. Importation de rapports trimestriels (PDF, DOCX, TXT/MD/CSV ou texte collé), extraction textuelle, analyse/résumé structuré IA et stockage en base.
5. Onglet **MOAT** par action : signaux financiers objectifs (marges, ROE/ROA, croissance CA, levier), analyse IA (« Analyste en Investissement Stratégique » Buffett/Dalio/McKinsey) sur les 7 types de MOAT (`Cost Advantage`, `Switching Costs`, `Network Effects`, `Brand Power`, `Regulatory Moat`, `Intangible Assets`, `Efficient Scale`) avec facteurs favorables vs défavorables, cartographie PESTEL/Interne en deux tableaux Risques & FCS (priorité Élevée/Moyenne), analyse compétitive, valorisation et persistance en base.

**Statut** : Implémentation terminée et vérifiée par build TypeScript/Next.js et suite de tests backend.

## 3. Completed Work
- **Modèles SQLAlchemy & Migrations Alembic** : Tables `finance_watchlist_items`, `finance_custom_indicators`, `finance_stock_news`, `finance_quarterly_reports`, `finance_stock_moats` ajoutées dans `backend/app/models.py`, migrations idempotentes `0020_add_finance_workspace.py` et `0021_add_finance_moat.py`, révisions enregistrées dans `backend/app/cli.py`.
- **Services backend & API REST (`/api/finance/...`)** :
  - `backend/app/finance_watchlist.py` : `compute_period_returns`, `resolve_watchlist_instrument`, `fetch_watchlist_quotes`, 6 actions par défaut (`DEFAULT_WATCHLIST_SEEDS`).
  - `backend/app/finance_news.py` : collecte Yahoo Finance + `providers.search_web` et synthèse Markdown LLM (avec repli hors-ligne/démo).
  - `backend/app/finance_reports.py` : `extract_report_text` (PDF via `pypdf`, DOCX via `python-docx`, TXT/MD/CSV, plafond `MAX_REPORT_EXTRACTED_CHARS = 120000`) et `analyze_quarterly_report` (résumé Markdown + `key_metrics` JSON).
  - `backend/app/finance_moat.py` : `compute_moat_quantitative_signals`, `analyze_and_build_stock_moat` (croisant fondamentaux, derniers rapports trimestriels et actualités stockés pour le titre, avec repli quantitatif hors-ligne/démo).
  - `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/routers/finance.py` : endpoints CRUD watchlist, indicateurs personnalisés, recherche/historique news, import/téléchargement/suppression rapports trimestriels et analyse/historique MOAT (`/api/finance/moat*`).
- **Moteur d'indicateurs & UI Frontend** :
  - `frontend/lib/custom-indicators.ts` : parseur/évaluateur AST sécurisé (sans `eval` ni `new Function`), présets (`CUSTOM_INDICATOR_PRESETS`), validation de formule (`validateCustomFormula`).
  - `frontend/components/finance-watchlist-table.tsx` : tableau triable 1J/1S/1M/3M/1A, ajout/suppression, clic ligne ouvrant la vue `"Analyse technique"`.
  - `frontend/components/finance-custom-indicator-modal.tsx` : assistant rapide + mode formule libre avec aperçu et lignes guides.
  - `frontend/components/finance-tv-chart.tsx` : rendu des indicateurs personnalisés en overlay ou panneaux oscillateurs séparés, bouton `+ Créer un indicateur`, édition et suppression.
  - `frontend/components/finance-moat-panel.tsx`, `frontend/components/finance-news-panel.tsx` & `frontend/components/finance-reports-panel.tsx` : onglets « MOAT », « Actualités & Veille » et « Rapports trimestriels » intégrés dans `frontend/components/finance-modal.tsx`.
  - `frontend/lib/api.ts` & `frontend/app/globals.css` : types, appels API et styles clair/sombre/responsive.

## 4. Key Decisions
- **Persistance SQLite par utilisateur** plutôt que `localStorage` seul, afin d'aligner l'espace Finance sur le reste de l'application ; seul le marqueur d'amorçage initial `clair_watchlist_seeded_v1` est conservé en `localStorage` pour ne pas réinjecter les valeurs par défaut si l'utilisateur vide volontairement son suivi.
- **Parseur arithmétique/AST dédié** (`frontend/lib/custom-indicators.ts`) au lieu d'une évaluation dynamique JS pour éliminer tout risque d'exécution de code arbitraire sur les formules saisies.
- **Conservation des modifications non commitées antérieures** (fonctionnalités Ideogram v2 dans `images.py`, `providers.py`, `openrouter.py`, `image-*.tsx`, etc.) laissées intactes dans l'arbre de travail.

## 5. Modified Files
- Créés (backend) :
  - `backend/migrations/versions/0020_add_finance_workspace.py`
  - `backend/migrations/versions/0021_add_finance_moat.py`
  - `backend/app/finance_watchlist.py`
  - `backend/app/finance_news.py`
  - `backend/app/finance_reports.py`
  - `backend/app/finance_moat.py`
- Modifiés (backend) :
  - `backend/app/models.py`
  - `backend/app/cli.py`
  - `backend/app/schemas.py`
  - `backend/app/serializers.py`
  - `backend/app/routers/finance.py`
  - `backend/tests/test_finance.py`
- Créés (frontend) :
  - `frontend/lib/custom-indicators.ts`
  - `frontend/components/finance-watchlist-table.tsx`
  - `frontend/components/finance-custom-indicator-modal.tsx`
  - `frontend/components/finance-moat-panel.tsx`
  - `frontend/components/finance-news-panel.tsx`
  - `frontend/components/finance-reports-panel.tsx`
- Modifiés (frontend) :
  - `frontend/lib/api.ts`
  - `frontend/components/finance-tv-chart.tsx`
  - `frontend/components/finance-modal.tsx`
  - `frontend/app/globals.css`

## 6. Verification
- `npm --prefix frontend run typecheck && npm --prefix frontend run build` : **RÉUSSI** (exécuté après la dernière édition frontend ; 0 erreur TypeScript, build Next.js 16.4.2 réussi).
- `npx --prefix frontend eslint --config frontend/eslint.config.mjs --max-warnings 0 frontend/components/finance-moat-panel.tsx` : **RÉUSSI** (0 erreur, 0 warning sur le panneau MOAT).
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_finance.py backend/tests/test_finance_statements.py backend/tests/test_migrations.py -v` : **RÉUSSI — 43 passed, 1 warning** (couvre `compute_period_returns`, `compute_moat_quantitative_signals`, extraction `.txt`/`.pdf`, CRUD complet `/api/finance/*` y compris `/moat*` et migration Alembic `0021_add_finance_moat`).
- `npm --prefix frontend run lint` (global) : **ÉCHOUÉ** lors d'un passage antérieur en raison d'erreurs préexistantes dans le dépôt et de règles `react-hooks/set-state-in-effect` / `react/no-unescaped-entities` / `@typescript-eslint/no-unused-vars` dans certains autres fichiers.
- Vérification visuelle interactive dans un navigateur réel : **non exécutée**.

## 7. Known Issues and Risks
- Le calcul des indicateurs personnalisés avec périodes longues (ex. `sma(close, 200)`) dépend du nombre de barres chargées pour la durée sélectionnée (`timeframe` par défaut `1m` ; passer à `3m`/`1y`/`5y` dans l'interface pour obtenir plus d'historique).
- Des règles ESLint strictes (`react-hooks/set-state-in-effect` introduite par React 19 ESLint plugin, ainsi que quelques imports/entités dans `finance-modal.tsx`) restent signalées au lint même si `tsc --noEmit` et `next build` passent sans erreur.
- L'arbre Git contient également des modifications non commitées antérieures liées à Ideogram v2 (hors périmètre de cette tâche).

## 8. Next Action
Effectuer un test manuel en navigateur sur l'interface (`/`) dans la modale **Marchés Financiers** (ajout/suppression dans le suivi, clic sur une ligne, création d'un indicateur personnalisé, recherche d'actualités et import d'un PDF trimestriel) puis nettoyer si souhaité les avertissements ESLint restants avant commit.
