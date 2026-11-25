# Plan : Catégories de Thèmes Préréglées, Sources JSON & Amélioration de Prompt (Blog Auto)

- **Créé le** : 2026-11-24
- **Statut** : `TERMINÉ`

## 1. Demande & Objectif Vérifiable
Ajouter dans le Blog Auto (`BlogModal` / `backend/app/blog.py`) :
1. Un catalogue JSON exhaustif (`backend/app/blog_theme_sources.json`) de 26 catégories de thèmes très larges configurant pour chaque thème ses sources principales/portails (`primary`), ses journaux/magazines (`journal`) et ses blogs/sites experts (`blog`) — ex. Cinéma & Séries (Écran Large, IMDb, AlloCiné, Première, Variety…), Jeux Vidéo (JeuxVideo.com, IGN, Gamekult, Gameblog, PC Gamer…), Finance & Bourse, Économie, Crypto, IA & Data, Tech & Hardware, Dév & Cyber, Sciences & Espace, Santé, Géopolitique, Manga/Anime/BD, Musique, Littérature & Arts, Sport, Auto & Mobilités, Cuisine & Gastronomie, Voyage, Environnement & Énergie, Immobilier & Architecture, Mode & Luxe, Droit & Fiscalité, Éducation & Carrière, Histoire & Archéologie, Psychologie & Philosophie, Maison/Jardin/Maker.
2. Le choix d'une catégorie de thème (`topic_category`) combiné à un prompt libre lors de la création ou de l'édition d'un blog, avec ciblage SearXNG (`site:`) et surclassement des sources du thème.
3. Un bouton et endpoint « ✨ Améliorer le prompt » (`POST /api/blogs/improve-prompt`) enrichissant le prompt saisi en fonction de la catégorie thématique sélectionnée.

## 2. Décisions Validées (One-Way Doors)
- **Colonne `blogs.topic_category`** (`VARCHAR(60)`, défaut `"general"`, migration Alembic `0032_add_blog_topic_category` + `db_bootstrap.py`) rétrocompatible et distincte de `blogs.categories` (qui conserve les types d'encarts `news`, `facts`, `images`, `videos`, etc.).
- **Extraction Sprout** : `backend/app/blog_theme_sources.json` + `backend/app/blog_themes.py` côté backend ; `frontend/components/blog-theme-category-picker.tsx` côté frontend.

## 3. Découpage & Suivi des Tranches
- [x] **`T1a` — Catalogue JSON exhaustif & Moteur thématique (`blog_theme_sources.json`, `blog_themes.py`)**
  `[Two-Way] · [Runtime] · [~650 lines / 2 files] · [Seams checked: Yes]`
- [x] **`T1b` — Schéma DB (`0032`), routes API (`/api/blogs/theme-categories`, `/api/blogs/improve-prompt`), pipeline `blog.py` & tests backend**
  `[One-Way] · [Runtime] · [~260 lines / 8 files] · [Seams checked: Yes]`
- [x] **`T2` — Composant UI `BlogThemeCategoryPicker`, bouton « Améliorer le prompt » dans `BlogModal` & vérifications frontend**
  `[Two-Way] · [Runtime] · [~480 lines / 3 files] · [Seams checked: N/A]`

## 4. Journal de Preuves
- **`T1a` & `T1b`** :
  - Fichiers créés/modifiés : `backend/app/blog_theme_sources.json`, `backend/app/blog_themes.py`, `backend/migrations/versions/0032_add_blog_topic_category.py`, `backend/app/cli.py`, `backend/app/db_bootstrap.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/blog.py`, `backend/app/routers/blogs.py`, `backend/tests/test_blogs.py`.
  - Commande exécutée : `cd backend && .venv/bin/python -m pytest tests/test_blogs.py -q` → **PASS** (`18 passed, 1 warning`).
- **`T2`** :
  - Fichiers créés/modifiés : `frontend/lib/api.ts`, `frontend/components/blog-theme-category-picker.tsx`, `frontend/components/blog-modal.tsx`.
  - Commandes exécutées :
    - `cd frontend && npm run typecheck` → **PASS** (`0 error`).
    - `cd frontend && npx eslint components/blog-theme-category-picker.tsx lib/api.ts --max-warnings 0` → **PASS** (`0 error, 0 warning`).
    - `cd frontend && npm test` → **PASS** (`28 passed, 0 failed`).

## 5. Prochaine Tranche
Aucune (`TERMINÉ`).
