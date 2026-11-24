# Plan — Jeu « Trading Replay » dans le Mode Finance

- **Créé le** : 2026-11-24
- **Statut** : TERMINÉ

## 1. Demande & Objectif Vérifiable
Ajouter dans le Mode Finance un jeu **« Trading Replay »** 100 % local (zéro crédit EODHD, alimenté par `finance_warehouse.db`) qui place l'utilisateur sur une action réelle arrêtée à une date historique $T_0$ et lui permet de :
- Analyser le graphique complet (`FinanceTvChart` avec indicateurs natifs et personnalisés).
- Jouer en **Mode Aveugle** par défaut (nom, ticker et vraies dates masqués côté serveur jusqu'au verdict final) ou en mode visible.
- Choisir l'univers (`Entrepôt`, `Indice`, `Watchlist`, `Action précise`), l'unité (`Jour`, `Semaine`, `Mois`) et l'horizon (`1 sem`, `1 mois`, `3 mois`, `6 mois`, `1 an`).
- Ouvrir une position **Achat (Long)** ou **Vendre à découvert (Short)** avec mise en `%` et **Stop-Loss / Take-Profit** optionnels, piloter l'avancement bougie par bougie (`+1`, `+5`, `Play/Pause`, `Clôturer`, `Aller à la fin` / `Passer`), puis consulter la révélation complète comparée au Buy & Hold.
- Suivre son portefeuille virtuel (`10 000 €` de départ, PnL cumulé, taux de réussite, séries, profit factor) et l'historique des manches persistés par `user_id`.

## 2. Décisions Validées (One-Way Doors)
- **Persistance SQLite Warehouse (`finance_warehouse.db`)** : ajout de `finance_game_profiles` et `finance_game_rounds` filtrés systématiquement par `user_id` (ADR 0001), sans toucher à la base applicative principale.
- **Anti-triche serveur** : tant que `status == 'active'`, aucune barre future ni identité ni vraie date (en `blind_mode=True`) n'est envoyée au client.
- **Règles SL/TP intrabar** : exécution au prix d'`open` en cas de gap ; si SL et TP sont tous les deux touchés dans une même bougie sans gap, le **Stop-Loss prime**.
- **1 trade principal par manche** : clôture possible à tout moment ou sur SL/TP/fin d'horizon, avec possibilité de continuer à observer la suite jusqu'à la révélation finale sans modifier le PnL.

## 3. Découpage & Suivi des Tranches
- [x] **T1 — Backend : Entrepôt, Moteur Trading Replay & API**
  `[One-Way (schéma/API)] · [Runtime] · [~490 lines / 4 prod files + 1 test] · [Seams checked: Yes]`
  - `finance_warehouse.py` (`finance_game_profiles`, `finance_game_rounds`), `finance_game.py`, `routers/finance_game.py`, `main.py`, `tests/test_finance_game.py`.
- [x] **T2 — Frontend Socle : Client API, Helpers & Extension `FinanceTvChart`**
  `[Two-Way] · [Runtime] · [~220 lines / 2 prod files + 1 test] · [Seams checked: Yes]`
  - `finance-game-api.ts`, `finance-game-helpers.ts`, `finance-tv-chart.tsx` (props optionnelles `priceLines`, `markers`, `blindCutoffIndex`, `disableDrawingsPersistence`), `tests/finance-game-helpers.test.mjs`.
- [x] **T3 — Frontend UI : Arène Trading Replay & Intégration Mode Finance**
  `[Two-Way] · [Runtime] · [~500 lines / 6 prod files] · [Seams checked: Yes]`
  - `finance-game-hud.tsx`, `finance-game-panel.tsx`, `finance-game-panel.module.css`, `finance-modal.tsx`, `globals.css`, `chat-app.tsx`.
- [x] **T4 — Suivi, Vérification Adversariale & Clôture**
  `[Two-Way] · [Static/Verify] · [~80 lines / 2 docs] · [Seams checked: N/A]`
  - Exécution complète `pytest`, `typecheck`, `eslint`, `npm test`, `npm run build` et mise à jour `HANDOFF.md`.

## 4. Journal de Preuves
- **T1 (Backend)** : `backend/app/finance_warehouse.py`, `backend/app/finance_game.py`, `backend/app/routers/finance_game.py`, `backend/app/main.py`, `backend/tests/test_finance_game.py`.
  - Commande : `cd backend && .venv/bin/python -m pytest tests/test_finance_game.py tests/test_finance_screener.py tests/test_finance.py -q` → **53 passed, 1 warning in 8.24s**.
- **T2 & T3 (Frontend)** : `frontend/lib/finance-game-api.ts`, `frontend/lib/finance-game-helpers.ts`, `frontend/tests/finance-game-helpers.test.mjs`, `frontend/components/finance-tv-chart.tsx`, `frontend/components/finance-game-hud.tsx`, `frontend/components/finance-game-panel.tsx`, `frontend/components/finance-game-panel.module.css`, `frontend/components/finance-modal.tsx`, `frontend/app/globals.css`, `frontend/components/chat-app.tsx`.
  - Commandes :
    - `cd frontend && npm run typecheck` → **0 error**.
    - `cd frontend && npx eslint lib/finance-game-api.ts lib/finance-game-helpers.ts components/finance-game-panel.tsx components/finance-game-hud.tsx components/finance-tv-chart.tsx --max-warnings 0` → **0 error, 0 warning**.
    - `cd frontend && npm test` → **27 passed, 0 failed**.
    - `cd frontend && npm run build` → **next build Turbopack OK**.

## 5. Prochaine Tranche
- **Aucune** (plan terminé).
