# Relais — 12 novembre 2026

## 1. Project Overview
clAIr : tchat IA francophone, apprentissage, recherche, médias et génération de pages HTML. Frontend Next.js 16.4 / React 19 / TypeScript ; backend FastAPI / SQLAlchemy / PostgreSQL.

## 2. Current Objective
Gestion des modèles favoris (étoile) dans toutes les zones de sélection de modèles IA avec remontée automatique en tête de liste et synchronisation temps réel.

## 3. Completed Work
- **Module centralisé `frontend/lib/model-favorites.ts`** :
  - Support de 2 catégories indépendantes et persistées localement (`clair_favorite_models` pour LLM / texte, `clair_favorite_image_models` pour Image Studio).
  - Gestion sécurisée de `localStorage` (avec repli gracieux et tolérance aux pannes JSON / SSR).
  - Synchronisation réactive temps réel inter-onglets et inter-composants via `useSyncExternalStore` et `CustomEvent` (`clair-model-favorites-changed`).
  - Fonction utilitaire `sortModelsWithFavorites` qui garantit le placement des modèles favoris en tête de liste (« en tête »).
- **Intégration dans toutes les zones de choix de modèles** :
  - **Modale principale de choix de modèles (`ModelModal`)** :
    - Bouton favori (étoile dorée) sur chaque carte de modèle et dans la bannière du modèle actif.
    - Tri dynamique plaçant systématiquement les modèles favoris au tout début de la liste.
    - Nouvel onglet de filtrage dédié « ⭐ Favoris (N) » permettant d'isoler en un clic ses modèles préférés.
    - Badge visuel « Favori » sur les spécifications de la carte.
  - **Modale de sélection clAIr Pages (`ModelPickerModal`)** :
    - Étoile interactive sur chaque carte pour ajouter / retirer des favoris.
    - Classement automatique des favoris en tête de la modale.
    - Badge visuel distinctif « ⭐ Favori » sur la carte.
  - **Modale Studio d'images (`ImageModelModal` & `ImageStudioModal`)** :
    - Favoris d'image avec bouton étoile sur chaque carte et dans la bannière supérieure.
    - Nouvel onglet de filtre rapide « ⭐ Favoris (N) » pour les modèles de génération d'image (Ideogram, Flux, Recraft, etc.).
    - Badge étoilé sur le sélecteur déclencheur de l'atelier d'images.
  - **Atelier Multi-Agents (`MultiAgentModal`)** :
    - Regroupement `<optgroup label="⭐ Modèles favoris">` tout en haut du menu déroulant de chaque agent.
    - Bouton étoile immédiat à droite du `<select>` pour basculer en favori le modèle assigné à un agent sans quitter l'interface.
  - **Pipeline d'analyse multi-étapes (`StageModelsModal`)** :
    - Indicateur étoilé doré sur chaque étape configurée avec un modèle favori.
    - Ouverture de `ModelModal` pour le changement de modèle, bénéficiant des favoris en tête.
  - **Topbar de discussion principale (`ChatApp`)** :
    - Pastille visuelle dorée avec étoile sur le sélecteur de modèle lorsque le modèle en cours fait partie des favoris.
- **Styles et accessibilité (`globals.css` & `model-picker-modal.module.css`)** :
  - Styles adaptés pour mode clair et tous les thèmes clAIr (`interface-themes.css`).
  - Étoile dorée `#f59e0b` avec animation au survol et gestion clavier/accessibilité (`aria-label`, `title`).
- **Tests unitaires et typage** :
  - Création de la suite de tests `frontend/tests/model-favorites.test.mjs` (6 tests unitaires réussis).
  - Script npm `"test:favorites"` ajouté à `package.json`.
  - Typecheck `tsc --noEmit` à 0 erreur.

## 4. Key Decisions
- Utilisation de `useSyncExternalStore` dans `model-favorites.ts` pour se conformer aux standards React 19 / Next.js 16 et éviter tout problème de cascade de rendus ou linting `react-hooks/set-state-in-effect`.
- Séparation étanche des favoris texte/LLM et des favoris de génération visuelle d'images.

## 5. Modified Files
- `frontend/lib/model-favorites.ts` : Nouveau module de gestion des favoris et hook `useModelFavorites`.
- `frontend/tests/model-favorites.test.mjs` : Tests unitaires du module de favoris.
- `frontend/package.json` : Ajout du script `test:favorites`.
- `frontend/components/model-modal.tsx` : Intégration étoiles, tri en tête, onglet favoris, bannière active.
- `frontend/components/model-picker-modal.tsx` : Intégration étoiles et tri en tête dans clAIr Pages.
- `frontend/components/model-picker-modal.module.css` : Styles CSS des favoris pour la modale clAIr Pages.
- `frontend/components/image-model-modal.tsx` : Modale modèles image avec favoris et tri en tête.
- `frontend/components/image-studio-modal.tsx` : Indicateur de modèle favori sur le déclencheur d'image.
- `frontend/components/multi-agent-modal.tsx` : Optgroup favoris en tête et bouton étoile sur chaque agent.
- `frontend/components/stage-models-modal.tsx` : Indicateur étoile sur les modèles d'étapes.
- `frontend/components/chat-app.tsx` : Pastille étoile dans la topbar si le modèle actif est favori.
- `frontend/app/globals.css` : Règles CSS complètes des boutons et badges favoris.
- `HANDOFF.md` : Mise à jour du journal de relais.

## 6. Verification
- `npm run test:favorites` (6/6 tests passés).
- `npm run test:themes` (5/5 tests passés).
- `npm run test:research` (2/2 tests passés).
- `npm run typecheck` (tsc --noEmit : 0 erreur).
- `npx eslint lib/model-favorites.ts components/model-picker-modal.tsx` (0 erreur, 0 avertissement).
- `PYTHONPATH=backend pytest backend/tests/test_pages.py` (11/11 tests passés).
- `git diff --check` (0 anomalie).

## 7. Known Issues and Risks
- Fichiers `.env` réels : non inspectés, non modifiés (respect strict de la frontière de sécurité).

## 8. Next Action
Prêt pour utilisation directe par l'utilisateur.
