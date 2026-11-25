# Plan — Mode Finance : Dividendes sur la courbe & Listes de suivi

- **Créé le** : 2026-11-25
- **Statut** : TERMINÉ

## Demande & Objectif Vérifiable
1. **Dividendes optionnels sur la courbe du cours** (onglet `3 · Cours & Indicateurs`) :
   - Endpoint `GET /api/finance/dividends?symbol=...&refresh=false` adossé au cache `finance_warehouse.db` (`payload_type="dividends"`), partagé avec `finance_dossier.py` (0 crédit EODHD tant que l'option n'est pas activée).
   - Bouton-pilule optionnel « Dividendes » mémorisé par onglet graphique (`ChartTabConfig.showDividends`, défaut `false`).
   - Affichage compatible multi-unités (`day` / `week` / `month` / `quarter`) sur **Analyse technique** (`FinanceTvChart`, marqueurs + détail crosshair) et **Courbe** simple (`InteractivePriceChart` SVG + hover pill).
2. **Listes de suivi (`Watchlist`)** :
   - Suppression d'une action toujours accessible sans scroll horizontal (même en barre latérale compacte).
   - Réordonnancement des actions dans une liste (glisser-déposer + boutons `↑`/`↓`), persisté via `PATCH /api/finance/watchlists/{list_id}/reorder` (DB principale + miroir `finance_warehouse.db`).

## Décisions Validées (One-Way Doors)
- Aucun One-Way Door (aucune migration DB : `FinanceWatchlistItem.position` et `finance_raw_snapshots` `payload_type="dividends"` existaient déjà).
- Option `showDividends` désactivée par défaut et mémorisée par onglet graphique.
- Bascule automatique de label marqueur (`D 3,30` si `<= 16` versements visibles, `D` au-delà, montant complet au survol).

## Découpage & Suivi des Tranches
- [x] **T1 — Backend dividendes partagé & endpoint dédié**
  `[Two-Way] · [Runtime] · [~160 lines / 3 files] · [Seams checked: Yes]`
- [x] **T2 — Logique pure frontend & affichage dividendes sur les 2 vues de courbe**
  `[Two-Way] · [Runtime] · [~280 lines / 5 files] · [Seams checked: Yes]`
- [x] **T3 — Backend réordonnancement des listes de suivi**
  `[Two-Way] · [Runtime] · [~90 lines / 3 files] · [Seams checked: Yes]`
- [x] **T4 — Frontend listes de suivi : suppression directe & réordonnancement (Drag & Drop + ↑/↓)**
  `[Two-Way] · [Runtime] · [~220 lines / 4 files] · [Seams checked: Yes]`

## Journal de Preuves
- **Fichiers créés / modifiés** :
  - Backend : `backend/app/finance_dividends.py`, `backend/app/schemas.py`, `backend/app/routers/finance.py`, `backend/tests/test_finance_dividends.py`, `backend/tests/test_finance_watchlist_reorder.py`.
  - Frontend : `frontend/lib/bar-aggregation.ts`, `frontend/lib/chart-dividends.ts`, `frontend/lib/finance-api.ts`, `frontend/lib/api.ts`, `frontend/components/finance-tv-chart.tsx`, `frontend/components/finance-modal.tsx`, `frontend/components/finance-watchlist-table.tsx`, `frontend/components/finance-watchlist-table.module.css`, `frontend/tests/chart-dividends.test.mjs`.
- **Commandes exécutées** :
  - `cd backend && .venv/bin/python -m pytest tests/test_finance_dividends.py tests/test_finance_watchlist_reorder.py tests/test_finance.py tests/test_finance_game.py -q` → **PASS (`51 passed, 1 warning`)**.
  - `cd frontend && npm run typecheck && npm test && npx eslint lib/bar-aggregation.ts lib/chart-dividends.ts lib/finance-api.ts components/finance-tv-chart.tsx components/finance-watchlist-table.tsx --max-warnings 0` → **PASS (`tsc 0 error`, `31 passed / 0 failed`, `eslint 0 error / 0 warning`)**.

## Prochaine Tranche
Aucune — plan `TERMINÉ`.
