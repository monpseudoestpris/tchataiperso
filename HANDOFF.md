# Relais — 31 octobre 2026

## 1. Project Overview
cLAIr : application d'apprentissage et de révision didactique, conversation IA avancée, Studio Image et multimédia, backend FastAPI/SQLAlchemy/Python, frontend Next.js 16/React/TypeScript.

## 2. Current Objective
Garantir la présence prioritaire permanente d'Ideogram v2 dans la modale de sélection de modèle du Studio Image (`ImageModelModal`), avec son onglet dédié, son positionnement en tête de liste et sa compatibilité immédiate avec les modèles OpenRouter.

## 3. Completed Work
- **Positionnement prioritaire d'Ideogram v2 (`backend/app/config.py`)** :
  - `ideogram` est désormais injecté en tête de liste de manière inconditionnelle avec `_rank = -1` et `is_top = True`.
  - Maintien des ratios d'aspect spécifiques à Ideogram (1x1, 16x9, 9x16, 4x3, 3x4, 3x2, 2x3, 10x16, 16x10, 1x3, 3x1).
- **Interface & Modale (`frontend/components/image-model-modal.tsx`)** :
  - Onglet dédié `Ideogram v2` placé parmi les premiers onglets de sélection rapide.
  - Tri prioritaire dans `sortedModels` garantissant qu'Ideogram reste en tête de liste tant sur l'onglet `Tous` que sur `⭐ Top Collection`.
  - Onglet par défaut initialisé sur `Tous` pour que l'utilisateur visualise immédiatement l'ensemble des modèles d'image disponibles dès l'ouverture.
- **Tests & Recompilation** :
  - Tests unitaires et d'intégration validés (391 tests passés).
  - Compilation Next.js validée sans avertissement ni erreur TypeScript.
  - Conteneurs `clair-api` et `clair-web` recompilés et opérationnels sur [http://localhost:3001](http://localhost:3001).

## 4. Key Decisions
- **Inclusion inconditionnelle d'Ideogram** : Permet à l'utilisateur de sélectionner et d'utiliser Ideogram v2 à tout moment dans le Studio Image, en complément de tous les modèles d'images dynamiques d'OpenRouter.

## 5. Modified Files
- `backend/app/config.py` : injection permanente prioritaire d'Ideogram v2.
- `frontend/components/image-model-modal.tsx` : onglet dédié, tri prioritaire et affichage par défaut complet.
- `HANDOFF.md` : journalisation de la mise à jour.

## 6. Verification
- `curl -s "http://127.0.0.1:8001/api/images/models" | jq '.[0]'` : renvoie bien `ideogram` en position 0 avec `_rank: -1` et `is_top: true`.
- `npm run build --prefix frontend` : compilation réussie.
- `docker compose ps` : conteneurs `clair-api` et `clair-web` opérationnels et sains.

## 7. Known Issues and Risks
- Aucun problème connu.

## 8. Next Action
Prêt pour test utilisateur dans le Studio Image sur [http://localhost:3001](http://localhost:3001).
