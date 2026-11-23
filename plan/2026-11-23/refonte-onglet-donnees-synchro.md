# Plan d'Exécution — Refonte Onglet 5 (Cours quotidiens vs Fondamentales progressives) & Épuration ETF du Screener

**Date de création** : 2026-11-23  
**Statut** : TERMINÉ

---

## Demande & Objectif Vérifiable
1. Retirer toute la gestion de données ETF de l'onglet **`4 · Screener`** (`ETFs par bourse`, comptage, référencement et boutons de chargement de cours ETF), tout en conservant le filtre `Tous / Actions / ETFs`, les badges `ETF` et le lien vers l'onglet 5.
2. Refondre l'ergonomie de l'onglet **`5 · Données & Synchro`** autour de la séparation métier claire :
   - **Les Cours (tous les jours)** : liste simple de sources (*Listes de suivi*, *Grands indices*, *Actions par bourse*, *ETFs par bourse*, *Catalogues EUFUND/CC*) avec couverture en base, interrupteur `Cours tous les jours` et action 1-clic `Charger tout de suite`.
   - **Les Données Fondamentales (petit à petit & sur publication)** : conservation du planificateur priorisé sous budget quotidien et calendrier des résultats dans une carte simple et lisible.
   - **En bas** : regroupement compact des informations sur les calls EODHD, de l'état des données synchronisées en base et des actions de maintenance/migration (`Migrer Yahoo → EODHD`, `Tout réactualiser`, `Réindexer`).

---

## Décisions Validées (One-Way Doors)
- **Rétro-compatibilité stricte** : ajout des champs optionnels `stock_price_exchanges`, `fundamentals_watchlists` et `fundamentals_indices` dans `finance_sync_preferences`, sans casser les schémas ni les endpoints existants.
- **Mutualisation des cours quotidiens** : une même bourse cochée en `Actions` et `ETFs` (`stock_price_exchanges` ∪ `full_data_exchanges` ∪ `etf_exchanges`) ne déclenche qu'un seul appel groupé `/api/eod-bulk-last-day/{EXCH}` par jour.

---

## Découpage & Suivi des Tranches
- [x] **T1a — Backend : Séparation Cours quotidiens / Fondamentales progressives & Action 1-clic par source** — `[Two-Way] · [Runtime] · [~290 lines / 6 files] · [Seams checked: Yes]`
- [x] **T1b — Onglet 4 (`Screener`) : Retrait de toute la partie data ETF** — `[Two-Way] · [Runtime] · [~180 lines / 2 files] · [Seams checked: N/A]`
- [x] **T1c — Onglet 5 (`Données & Synchro`) : Nouvelle ergonomie Liste des cours, Fondamentales & Pied de page** — `[Two-Way] · [Runtime] · [~450 lines / 6 files] · [Seams checked: N/A]`
- [x] **T1d — Tests automatisés, Glossaire & Clôture** — `[Two-Way] · [Static] · [~130 lines / 4 files] · [Seams checked: Yes]`

---

## Journal de Preuves
- **T1a** (`backend/app/finance_warehouse.py`, `backend/app/finance_fundamentals_scheduler.py`, `backend/app/finance_sync_sources.py`, `backend/app/finance_funds.py`, `backend/app/finance_eodhd_usage.py`, `backend/app/routers/finance.py`) :
  - Préférences `stock_price_exchanges`, `fundamentals_watchlists`, `fundamentals_indices`, filtrage optionnel `seed_screener_from_exchange_catalogs(db_path, exchange_codes)`, couverture unifiée `get_unified_exchange_sources`, chargement 1-clic `POST /api/finance/sync-preferences/run-source` et mutualisation du bulk quotidien.
  - Vérif : `cd backend && .venv/bin/python -m pytest tests/test_finance*.py -q` → `137 passed, 1 warning in 25.02s`.
- **T1b** (`frontend/components/finance-screener-panel.tsx`, `frontend/components/finance-screener-panel.module.css`) :
  - Suppression du bouton et tiroir *« ETFs par bourse »* (`Compter`, `Charger X ETFs`, `Autre bourse`) et du bouton de lot `Cours N ETF` ; conservation du filtre `Tous / Actions / ETFs`, des badges `ETF` et d'une redirection claire vers `Données & Synchro`.
- **T1c** (`frontend/lib/api.ts`, `frontend/components/finance-sync-panel.module.css`, `frontend/components/finance-fundamentals-plan-card.tsx`, `frontend/components/finance-sync-footer.tsx`, `frontend/components/finance-sync-panel.tsx`, suppression de `frontend/components/finance-etf-sync-card.tsx`) :
  - Refonte de l'onglet 5 en 3 blocs : `1. Les Cours` (liste unifiée + switch `Tous les jours` + `Charger tout de suite`), `2. Données Fondamentales` (progressif & après résultats), `3. Bas de page` (Calls EODHD, état de la base et migration Yahoo → EODHD / réindexation).
- **T1d** (`backend/tests/test_finance_sync_sources.py`, `GLOSSARY.md`, `HANDOFF.md`) :
  - Ajout de 3 tests déterministes hors-ligne (`test_unified_exchange_sources_and_selective_stock_seeding`, `test_run_source_endpoint_loads_stocks_etf_and_validates`, `test_daily_sync_mutualizes_bulk_and_respects_fundamentals_toggles`).
  - Vérif backend finale : `cd backend && .venv/bin/python -m pytest tests/test_finance*.py -q` → `140 passed, 1 warning in 47.75s`.
  - Vérif frontend finale : `cd frontend && npm run typecheck && npx eslint components/finance-screener-panel.tsx components/finance-sync-panel.tsx components/finance-fundamentals-plan-card.tsx components/finance-sync-footer.tsx lib/api.ts lib/finance-api.ts && npm test && npm run build` → `exit 0` (`0` erreur TypeScript, `0` erreur/warning ESLint, `22 passed, 0 failed`, `next build` OK).

---

## Prochaine Tranche
Aucune — plan terminé.
