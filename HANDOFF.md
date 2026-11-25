# HANDOFF.md — Routeur de Session

## 1. Aperçu du Projet
**cLAIr** (`tchataiperso`) est une plateforme de tchat IA multi-fournisseurs (Google Cloud Vertex/Gemini natif, OpenRouter, Mistral OCR/Voxtral, Ideogram, ElevenLabs, EODHD) articulée autour d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite WAL** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`). Les concepts métier et choix d'architecture sont figés dans `GLOSSARY.md` et `docs/adr/0001..0006`.

## 2. Santé de Référence (Baseline)
- **Backend `pytest` Finance (Dividendes, Watchlist, Core & Replay)** (`cd backend && .venv/bin/python -m pytest tests/test_finance_dividends.py tests/test_finance_watchlist_reorder.py tests/test_finance.py tests/test_finance_game.py -q`) : **PASS** (`51 passed, 1 warning`).
- **Backend `pytest` Blogs & Thèmes JSON** (`cd backend && .venv/bin/python -m pytest tests/test_blogs.py -q`) : **PASS** (`18 passed, 1 warning` précédemment ; non modifié).
- **Frontend `typecheck`** (`cd frontend && npm run typecheck`) : **PASS** (`0 error`).
- **Frontend `lint` ciblé** (`npx eslint lib/bar-aggregation.ts lib/chart-dividends.ts lib/finance-api.ts components/finance-tv-chart.tsx components/finance-watchlist-table.tsx --max-warnings 0`) : **PASS** (`0 error, 0 warning`).
- **Frontend `test`** (`cd frontend && npm test`) : **PASS** (`31 passed, 0 failed`).

## 3. Plan Actif
- **Aucun** (`plan/2026-11-25/finance-dividends-and-watchlist.md` **`TERMINÉ`**, tranches `T1` → `T4` toutes vérifiées).

## 4. Travaux Ponctuels Récents
- **Mode Finance — Dividendes sur la courbe & Listes de suivi (`plan/2026-11-25/finance-dividends-and-watchlist.md`, `T1`–`T4`)** : service `finance_dividends.py` + `GET /api/finance/dividends` (cache entrepôt `payload_type="dividends"` partagé, 0 crédit EODHD tant que non activé), projection multi-unités `chart-dividends.ts` (Jour/Semaine/Mois/3 Mois), toggle optionnel `Dividendes` mémorisé par onglet graphique (`FinanceTvChart` marqueurs + détail crosshair et `InteractivePriceChart` SVG + hover pill) ; endpoint `PATCH /api/finance/watchlists/{list_id}/reorder` (DB principale + miroir entrepôt), suppression directe toujours visible sans scroll horizontal et réordonnancement glisser-déposer + `↑`/`↓` dans `FinanceWatchlistTable`.
- **Support `.env` externe (`CLAIR_ENV_FILE`)** : helper canonique `scripts/env_file.sh`, garde `os.access(..., os.R_OK)` dans `backend/app/config.py`.
- **Catégories de Thèmes & Sources Spécialisées JSON dans le Blog Auto (`plan/2026-11-24/blog-theme-categories-sources.md`)** : catalogue 26 thèmes `blog_theme_sources.json`, `blog_themes.py`, Alembic `0032`, `BlogThemeCategoryPicker`.
- **Modernisation UI Éditoriale (`plan/2026-11-24/modernisation-ui-editoriale.md`)** : `design-tokens.css` (12 palettes), `editorial-shell.css`, `editorial-modals.css`, `QuickThemeToggle`, `SidebarCreativityPotentiometer`.
- **Jeu « Trading Replay » dans le Mode Finance (`plan/2026-11-24/finance-trading-replay-game.md`)** : moteur local `finance_game.py`, API `/api/finance/game/*`, onglet `6 · Défi Replay`.

## 5. Risques & Blocages Connus
- **Dettes restantes (hors plan clôturé)** : problèmes ESLint préexistants sur `chat-app.tsx` (`24` dont `10` erreurs), `finance-modal.tsx` (`18` anciens warnings/erreurs) et anciennes modales ; poursuite éventuelle du découpage de `providers.py` / `chat-app.tsx`.
- **Hygiène dépôt** : modifications récentes non commitées dans l'arbre de travail ; fichier vide parasite `--system-prompt=Règle absolue...` ; `OLDPROJECT.md` conservé volontairement.

## 6. Prochaine Action Immédiate
Vérifier visuellement dans l'application locale le Mode Finance : (1) activer le bouton **Dividendes** sur une valeur à dividendes (ex. `AI.PA` / `TTE.PA` / `AAPL.US`) en vue **Analyse technique** et **Courbe** sur plusieurs unités (Jour / Semaine / Mois / 3 Mois) et thèmes Clair/Sombre ; (2) tester la suppression directe et le réordonnancement (glisser-déposer + `↑`/`↓`) dans les **Listes de suivi** en barre latérale compacte et élargie, puis revoir `git status` avant commit.
