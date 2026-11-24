# HANDOFF.md — Routeur de Session

## 1. Aperçu du Projet
**cLAIr** (`tchataiperso`) est une plateforme de tchat IA multi-fournisseurs (Google Cloud Vertex/Gemini natif, OpenRouter, Mistral OCR/Voxtral, Ideogram, ElevenLabs, EODHD) articulée autour d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite WAL** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`). Les concepts métier et choix d'architecture sont figés dans `GLOSSARY.md` et `docs/adr/0001..0006`.

## 2. Santé de Référence (Baseline)
- **Backend `pytest` Vidéos / Contexte / Docs** (`cd backend && .venv/bin/python -m pytest tests/test_youtube.py tests/test_videos.py tests/test_context.py tests/test_chat_memory.py tests/test_visual_documents.py -q`) : **PASS** (`65 passed, 1 warning` précédemment ; non modifié depuis).
- **Frontend `typecheck`** (`cd frontend && npm run typecheck`) : **PASS** (`0 error`).
- **Frontend `lint` ciblé** (`npx eslint app/layout.tsx lib/interface-themes.ts components/quick-theme-toggle.tsx components/interface-theme.tsx components/sidebar-creativity-potentiometer.tsx components/tools-modal.tsx components/model-modal.tsx components/auth-panel.tsx components/skills-panel.tsx --max-warnings 0`) : **PASS** (`0 error, 0 warning`).
- **Frontend `test`** (`cd frontend && npm test`) : **PASS** (`24 passed, 0 failed`).
- **Frontend `build`** (`cd frontend && npm run build`) : **PASS** (`next build` Turbopack OK).

## 3. Plan Actif
- **Aucun** (plan `plan/2026-11-24/modernisation-ui-editoriale.md` **`TERMINÉ`**, tranches `T1a` → `T1e` toutes vérifiées).

## 4. Travaux Ponctuels Récents
- **Modernisation UI Éditoriale (`plan/2026-11-24/modernisation-ui-editoriale.md`, `T1a`–`T1e`)** : création du design system canonique `design-tokens.css` (Albâtre chaud `#FAF9F6`, Anthracite profond `#141311`, accent cuivre `#B4532A` / `#DE8A62`, parité 12 palettes, polices `Instrument Serif` + `Plus Jakarta Sans` + `JetBrains Mono`), coque éditoriale `editorial-shell.css`, modales unifiées `editorial-modals.css`, tokenisation de `ToolsModal` et `ModelModal` (remplacement emojis par icônes Lucide), fusion de la double barre supérieure (`56px`), allègement du pied de sidebar, `SidebarCreativityPotentiometer` compact/dépliable et bouton rapide Clair ↔ Sombre (`QuickThemeToggle`).
- **Import vidéo YouTube & Transcript intégral** : table `saved_videos` (Alembic `0031`), API `/api/videos/*`, 7 options dans `ChatUrlAttachModal` et modale dédiée `VideoLibraryModal`.
- **Tâche annexe Screener & SQLite** : infobulle complète et colonne « Titre » redimensionnable dans `FinanceScreenerPanel`, verrou `init_warehouse` + `busy_timeout=30000`, et bouton « Quitter proprement » (`QuitAppModal`).

## 5. Risques & Blocages Connus
- **Dettes restantes (hors plan clôturé)** : problèmes ESLint préexistants sur `chat-app.tsx` (`24` dont `10` erreurs sur les lignes `< 2560`) et anciennes modales frontend, poursuite éventuelle du découpage de `providers.py` / `chat-app.tsx`, convergence Alembic seul, installation de `ruff` hors bac à sable.
- **Hygiène dépôt** : modifications récentes non commitées dans l'arbre de travail ; fichier vide parasite `--system-prompt=Règle absolue...` ; `OLDPROJECT.md` conservé volontairement.

## 6. Prochaine Action Immédiate
Lancer le frontend en local et contrôler visuellement l’interface sur les thèmes Clair, Sombre et palettes personnalisées (desktop `1280px+` et mobile `375px` : topbar fusionnée, potentiomètre dépliable, modales Outils/Modèles/Paramètres, lecture Markdown), puis revoir `git status` avant commit.
