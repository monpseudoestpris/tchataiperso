# Refonte Visuelle Éditoriale du Mode Finance & Lisibilité de la Liste de Suivi

- **Créé le** : 2026-11-25
- **Statut** : TERMINÉ

## Demande & Objectif Vérifiable
1. **Lisibilité de la Liste de Suivi (`Watchlist`)** : rendre les noms complets d'actions parfaitement lisibles en barre latérale compacte et élargie (fin du tronquage à ~37px) tout en conservant suppression directe, réordonnancement (glisser-déposer + `↑`/`↓`), notes et mise en surbrillance de la ligne sélectionnée (`.is-selected`).
2. **Refonte visuelle « Éditorial FinTech » du Mode Finance** : aligner intégralement l'espace Finance (en-tête, 6 onglets principaux, bannière Hero Quote, graphiques, tableaux, dossier institutionnel, experts, MOAT, actus, rapports, Screener, Données & Synchro) sur les 12 palettes de `design-tokens.css` (`Instrument Serif`, `Plus Jakarta Sans`, `JetBrains Mono` en `tabular-nums`, surfaces graduées, bordures `1px`, zéro dégradé néon, zéro `transition: all`, zéro emoji en icône UI).

## Décisions Validées (One-Way Doors)
- Aucun One-Way Door (changements strictement UI/CSS réversibles).
- Direction validée : **Éditorial FinTech** via feuille dédiée `frontend/app/editorial-finance.css` (sans modifier `globals.css`) + tokenisation des modules CSS `finance-screener-panel.module.css` et `finance-sync-panel.module.css`.

## Découpage & Suivi des Tranches
- [x] **T1 — Liste de suivi (`Watchlist`) : Lisibilité intégrale des noms & ergonomie moderne**
  `[Two-Way] · [Runtime] · [~280 lines / 4 files] · [Seams checked: Yes]`
- [x] **T2 — Coque visuelle Éditoriale du Mode Finance (En-tête, Navigation, Hero & Graphiques)**
  `[Two-Way] · [Static] · [~480 lines / 2 files] · [Seams checked: Yes]`
- [x] **T3 — Harmonisation Éditoriale des Panneaux Internes & Nettoyage Emojis**
  `[Two-Way] · [Static] · [~420 lines / 2 files] · [Seams checked: Yes]`
- [x] **T4 — Tokenisation des Modules CSS Screener & Données/Synchro**
  `[Two-Way] · [Static] · [~450 lines / 2 files] · [Seams checked: Yes]`
- [x] **T5 — Vérification Adversariale, Audit CSS, Build & Clôture**
  `[Two-Way] · [Static] · [~30 lines / 2 files] · [Seams checked: Yes]`

## Journal de Preuves
- **Fichiers créés / modifiés** :
  - `frontend/app/editorial-finance.css` (nouvelle feuille éditoriale complète, portée `:root .finance-modal-container` pour garantir la parité Clair / Sombre / 10 Palettes sans toucher `globals.css`).
  - `frontend/app/layout.tsx` (import de `./editorial-finance.css`).
  - `frontend/components/finance-watchlist-table.tsx` & `frontend/components/finance-watchlist-table.module.css` (cellule `Action` sur 2 lignes, nom pleine largeur sur 2 lignes max, actions `↑`/`↓`/`Supprimer` alignées sur la ligne métadonnées, remplacement emoji `⚠️` par `AlertTriangle`).
  - `frontend/components/finance-modal.tsx` (remplacement emojis `⚠️`/`📅` par `AlertTriangle`/`Calendar`, suppression des styles inline Dividendes).
  - `frontend/components/finance-screener-panel.module.css` & `frontend/components/finance-sync-panel.module.css` (tokenisation intégrale sur `design-tokens.css`, suppression des blocs dark codés en dur).
- **Commandes exécutées** :
  - `cd frontend && npm run typecheck && npm test && npx eslint app/layout.tsx components/finance-watchlist-table.tsx --max-warnings 0 && ! rg -n 'transition:\s*all' app/editorial-finance.css components/finance-watchlist-table.module.css components/finance-screener-panel.module.css components/finance-sync-panel.module.css && npm run build` → **PASS** (`tsc 0 error`, `31 passed / 0 failed`, `eslint 0 error / 0 warning`, `0` occurrence `transition: all`, `next build` OK).

## Prochaine Tranche
Aucune — plan `TERMINÉ`.
