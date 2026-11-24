# Modernisation UI Éditoriale de cLAIr

Créé le : 2026-11-24 · Statut : TERMINÉ

## 1. Demande & Objectif Vérifiable
Moderniser l’interface graphique de **cLAIr** selon une direction **Éditorial & Luxe discret** (style Claude / Apple / Notion) couvrant l’expérience principale complète (Design System, 12 thèmes, Coque Chat, Connexion, Modales clés) avec une ergonomie épurée et aérée :
- Typographie éditoriale (`Instrument Serif` + `Plus Jakarta Sans` + `JetBrains Mono`) avec `tabular-nums`.
- Profondeur par surfaces graduées et bordures fines `1px`, zéro gradient néon, zéro `transition: all`, zéro emoji en icône UI.
- Parité sur les 12 thèmes (`Clair` Albâtre, `Sombre` Anthracite, et 10 palettes existantes) avec contraste WCAG AA.
- Topbar unique fusionnée (`56px`), sidebar allégée avec potentiomètre compact/dépliable, et bascule rapide Clair ↔ Sombre.
- Vérification complète : `npm run typecheck`, `npm test`, `eslint --max-warnings 0` sur fichiers touchés, `npm run build` à 0 erreur.

## 2. Décisions Validées (One-Way Doors)
1. **Direction esthétique** : Éditorial & Luxe discret — fond albâtre chaud (`#FAF9F6`), anthracite profond (`#141311`), encre profonde (`#1C1917` / `#F4F1EA`) et accent cuivre/terre de Sienne (`#B4532A` / `#DE8A62`).
2. **Périmètre** : Expérience principale complète (Design System, Coque Chat, Connexion, Admin, Outils, Paramètres, Modèles, Mémoire & Compétences), sans altérer les grands studios spécialisés ni `globals.css`.
3. **Ergonomie** : Double barre supérieure fusionnée en une seule topbar, suppression des doublons sidebar/topbar, potentiomètre de créativité compact par défaut, bouton rapide Clair ↔ Sombre.
4. **Polices** : Chargement CSS via `@import url(...)` Google Fonts (`display=swap`) dans `design-tokens.css` + `preconnect` dans `layout.tsx` (sans `next/font/google`) pour garantir des builds hors-ligne reproductibles sans nouvelle dépendance npm ni warning ESLint.

## 3. Découpage & Suivi des Tranches
- [x] **T1a** — Fondation Design System, Polices & 12 Thèmes Éditoriaux
  `[Two-Way] · [Static] · [~423 lines / 5 files] · [Seams checked: Yes]`
- [x] **T1b** — Coque Visuelle Éditoriale (`editorial-shell.css`)
  `[Two-Way] · [Static] · [~1775 lines / 2 files] · [Seams checked: Yes]`
- [x] **T1c** — Ergonomie Épurée : Topbar Fusionnée, Sidebar Allégée & Bascule Thème Rapide
  `[Two-Way] · [Runtime] · [~280 lines / 4 files] · [Seams checked: Yes]`
- [x] **T1d** — Uniformisation des Modales & Panneaux Clés
  `[Two-Way] · [Static] · [~908 lines / 6 files] · [Seams checked: Yes]`
- [x] **T1e** — Tests, Vérification Adversariale & Clôture
  `[Two-Way] · [Static] · [~60 lines / 3 files] · [Seams checked: Yes]`

## 4. Journal de Preuves
- **T1a** : création de `frontend/app/design-tokens.css` (423 L, tokens canoniques + 12 palettes + pont legacy), mise à jour de `frontend/app/layout.tsx`, `frontend/lib/interface-themes.ts` (`getOppositeModeTheme`), `frontend/app/interface-themes.css`, `frontend/public/mark.svg`.
  - `cd frontend && npm run typecheck && npm run test:themes` → **PASS** (`0` erreur TS, `5/5` tests thèmes).
- **T1b** : création de `frontend/app/editorial-shell.css` (1 775 L) + import dans `frontend/app/layout.tsx`.
- **T1c** : création de `frontend/components/quick-theme-toggle.tsx` (34 L), refonte compacte/dépliable et tokenisée de `frontend/components/sidebar-creativity-potentiometer.tsx`, fusion de la double barre et épuration sidebar/topbar dans `frontend/components/chat-app.tsx`.
  - `cd frontend && npm run typecheck && npx eslint components/quick-theme-toggle.tsx components/sidebar-creativity-potentiometer.tsx --max-warnings 0` → **PASS** (`0` erreur, `0` warning).
- **T1d** : création de `frontend/app/editorial-modals.css` (908 L), tokenisation complète de `frontend/components/tools-modal.module.css` & `frontend/components/tools-modal.tsx`, remplacement des emojis par des icônes Lucide et suppression de 3 imports inutilisés dans `frontend/components/model-modal.tsx`, nettoyage inline dans `frontend/components/skills-panel.tsx` et `frontend/components/auth-panel.tsx`.
- **T1e** : ajout du test `getOppositeModeTheme` dans `frontend/tests/interface-themes.test.mjs`, puis validation finale après dernière édition :
  - `cd frontend && npm run typecheck` → **PASS** (`0` erreur).
  - `cd frontend && npm test` → **PASS** (`24 passed, 0 failed` en `6.63s`).
  - `cd frontend && npx eslint app/layout.tsx lib/interface-themes.ts components/quick-theme-toggle.tsx components/interface-theme.tsx components/sidebar-creativity-potentiometer.tsx components/tools-modal.tsx components/model-modal.tsx components/auth-panel.tsx components/skills-panel.tsx --max-warnings 0` → **PASS** (`0` erreur, `0` warning).
  - Audit CSS (`! rg -n 'transition:\s*all' app/design-tokens.css app/editorial-shell.css app/editorial-modals.css components/tools-modal.module.css`) → **PASS** (`0` occurrence).
  - `cd frontend && npm run build` → **PASS** (`next build` Turbopack OK, routes `/` et `/api/conversations/[id]/messages`).
  - `cd frontend && npx eslint components/chat-app.tsx` → `24 problems (10 errors, 14 warnings)` exclusivement sur des lignes préexistantes (`<= 2555`), zéro problème sur les zones modifiées (`51`, `137`, `>= 2969`).

## 5. Prochaine Tranche
Aucune — plan `TERMINÉ`. Vérifier visuellement dans le navigateur les thèmes Clair/Sombre/palettes, la largeur mobile (`375px`) et desktop (`1280px+`).
