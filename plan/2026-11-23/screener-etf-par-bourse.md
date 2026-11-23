# Plan d'Exécution — Prise en charge indépendante des ETFs par Bourse dans le Screener

**Date de création** : 2026-11-23  
**Statut** : TERMINÉ

---

## Demande & Objectif Vérifiable
Permettre dans le **Screener Boursier** (`4 · Screener`) de :
1. Différencier explicitement les **Actions** (`asset_type = 'stock'`) et les **ETFs** (`asset_type = 'etf'`), avec leurs noms complets, tickers, devises, pays et bourses d'origine (`PA`, `US`, `XETRA`, `LSE`, `SW`, `AS`, `MI`, etc.).
2. Connaître **avant chargement** le nombre exact d'ETFs disponibles sur chaque bourse d'origine (`etf_catalog_count`, `etf_in_screener_count`, `etf_with_data_count`).
3. Référencer indépendamment les ETFs d'une ou plusieurs bourses dans le Screener (`0` crédit réseau une fois la liste de la bourse synchronisée), puis charger leurs historiques EOD et indicateurs techniques multi-unités (`Jour`, `Semaine`, `Mois`, `3 Mois` + `IsoPressure`) par lots maîtrisés (`1` call EODHD / ETF).

---

## Décisions Validées (One-Way Doors)
- **Two-Way Door compatible** : ajout de la colonne `asset_type TEXT NOT NULL DEFAULT 'stock'` sur `finance_screener_snapshots` dans `finance_warehouse.db` avec `ALTER TABLE` idempotent et rétro-remplissage des ETFs connus ; aucun changement cassant sur les contrats existants.
- **Chargement léger ETF** : les ETFs utilisent par défaut l'hydratation des barres EOD (`1 call / ETF` via `/api/eod/{TICKER}`) pour alimenter performances et indicateurs multi-unités sans imposer `10 calls` fondamentaux par titre.

---

## Découpage & Suivi des Tranches
- [x] **T1a — Entrepôt SQLite : colonne `asset_type`, comptage & référencement ETF par bourse** — `[Two-Way] · [Runtime] · [~170 lines / 1 file] · [Seams checked: Yes]`
- [x] **T1b — Moteur Screener, Chargement EOD par lot & Endpoints API** — `[Two-Way] · [Runtime] · [~230 lines / 4 files] · [Seams checked: Yes]`
- [x] **T1c — Interface Frontend du Screener (`FinanceScreenerPanel`)** — `[Two-Way] · [Runtime] · [~240 lines / 3 files] · [Seams checked: N/A]`
- [x] **T1d — Tests Automatisés, Glossaire & Clôture** — `[Two-Way] · [Static] · [~140 lines / 3 files] · [Seams checked: Yes]`
- [x] **T1e — Carte dédiée ETFs par Bourse dans l'onglet 5 (`Données & Synchro`) + préférence `etf_exchanges`** — `[Two-Way] · [Runtime] · [~280 lines / 5 files] · [Seams checked: Yes]`

---

## Journal de Preuves
- **T1a** (`backend/app/finance_warehouse.py`) :
  - Ajout de `asset_type` sur `finance_screener_snapshots`, migration `init_warehouse`, rétro-remplissage ETF, `resolve_symbol_asset_type`, `get_etf_exchange_catalog_counts`, `seed_etfs_from_exchange_catalog`, filtrage par `asset_type` dans `get_screener_coverage`.
  - Vérif : `cd backend && .venv/bin/python -m pytest tests/test_finance_screener.py tests/test_finance_exchange_full_sync.py -q` → `10 passed in 2.08s`.
- **T1b** (`backend/app/finance_screener.py`, `backend/app/finance_funds.py`, `backend/app/routers/finance.py`, `backend/app/finance_chat_tools.py`) :
  - Ajout du filtre `asset_type`, conservation des métadonnées catalogue dans `build_screener_snapshot_from_warehouse`, `hydrate_screener_bars_batch` + tâche détachée `start_screener_bars_batch_background`, endpoints `/api/finance/screener/etf-exchanges`, `/api/finance/screener/etf-exchanges/load`, `/api/finance/screener/hydrate-bars`, paramètre `asset_type` sur `finance_screener_query`.
  - Vérif : `cd backend && .venv/bin/python -m pytest tests/test_finance_screener.py tests/test_finance_funds.py tests/test_finance_exchange_full_sync.py tests/test_finance_chat_tools.py -q` → `24 passed in 8.60s`.
- **T1c** (`frontend/lib/finance-api.ts`, `frontend/components/finance-screener-panel.tsx`, `frontend/components/finance-screener-panel.module.css`) :
  - Sélecteur `Tous` / `Actions` / `ETFs`, panneau dépliable `ETFs par Bourse d'origine` avec décompte préalable (`Compter (1 call)`), chargement indépendant (`Charger X ETFs (0 call)`), badges `ETF` + bourse, et bouton `Cours N ETF (≈ N calls)`.
  - Vérif : `cd frontend && npm run typecheck && npx eslint components/finance-screener-panel.tsx lib/finance-api.ts lib/api.ts` → `exit 0` (`0` erreur/warning).
  - Vérif : `cd frontend && npm test && npm run build` → `22 passed, 0 failed` et `next build` OK.
- **T1d** (`backend/tests/test_finance_screener.py`, `GLOSSARY.md`, `HANDOFF.md`) :
  - Ajout de `test_screener_etf_counts_by_exchange_independent_seeding_and_bars_hydration` couvrant migration, comptage préalable par bourse, référencement indépendant `PA` / `US`, endpoints API et hydratation EOD `1 call / ETF`.
  - Vérif : `cd backend && .venv/bin/python -m pytest tests/test_finance*.py -q` → `137 passed in 27.75s`.
- **T1e** (`backend/app/finance_warehouse.py`, `backend/app/finance_funds.py`, `frontend/lib/api.ts`, `frontend/components/finance-etf-sync-card.tsx`, `frontend/components/finance-sync-panel.tsx`) :
  - Ajout de `etf_exchanges` aux préférences de synchro quotidienne + référencement automatique des ETFs des bourses cochées lors de `run_daily_sync_now`.
  - Création de `FinanceEtfSyncCard` (Bloc **3 ter** de l'onglet `5 · Données & Synchro`) : comptage préalable (`Compter (1 call)`), coches par bourse, chargement immédiat (`Charger X (0 call)`) et chargement des cours par lot (`1 call / ETF`).
  - Vérif : `cd backend && .venv/bin/python -m pytest tests/test_finance_screener.py tests/test_finance_funds.py tests/test_finance_exchange_full_sync.py -q` → `19 passed in 6.48s`.
  - Vérif : `cd frontend && npm run typecheck && npx eslint components/finance-etf-sync-card.tsx components/finance-sync-panel.tsx lib/api.ts && npm test && npm run build` → `exit 0` (`0` erreur/warning, `22 passed, 0 failed`, `next build` OK).

---

## Prochaine Tranche
Aucune — plan terminé.
