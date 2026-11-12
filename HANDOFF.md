# Relais — 12 novembre 2026

## 1. Project Overview
clAIr : tchat IA francophone, apprentissage, recherche, médias et génération de pages HTML. Frontend Next.js 16.4 / React 19 / TypeScript ; backend FastAPI / SQLAlchemy / PostgreSQL.

## 2. Current Objective
Configuration d'un modèle d'excellence (Gemini Argon / `google/gemini-4-argon`) pour l'amélioration et la structuration des prompts de compétences (skills) et pour l'amélioration visuelle des prompts dans le studio de génération d'images.

## 3. Completed Work
- **Backend & Configuration** :
  - **`backend/app/config.py`** :
    - Définition de `image_prompt_model = "google/gemini-4-argon"` (remplaçant l'ancien défaut `openai/gpt-6-luna`).
    - Ajout du paramètre dédié `skill_prompt_model = "google/gemini-4-argon"` dans les paramètres globaux.
    - Ajout de `skill_prompt_model` à `str_fields` pour rechargement dynamique via variable d'environnement `SKILL_PROMPT_MODEL`.
  - **`backend/app/routers/system.py`** :
    - Exposition de `skill_prompt_model` dans la réponse `/api/config` aux côtés de `image_prompt_model`.
  - **`backend/app/schemas.py`** :
    - Évolution de `ImproveSkillPrompt` avec champ optionnel `model: str | None = Field(default=None, max_length=150)` et assainissement.
  - **`backend/app/routers/skills.py`** :
    - Résolution de modèle prioritaire `body.model or settings.skill_prompt_model or "google/gemini-4-argon" or settings.default_model`.
  - **`backend/app/routers/images.py`** :
    - Résolution de modèle prioritaire `body.model or settings.image_prompt_model or "google/gemini-4-argon" or settings.default_model`.
  - **`backend/app/providers.py`** :
    - Ajout d'une tolérance de panne avec repli automatique vers `default_model` en cas d'erreur 400/404/422 dans `improve_skill_prompt` (symétrique à `improve_image_prompt`).
  - **`compose.yaml` & `.env.example`** :
    - Mise à jour et documentation de `IMAGE_PROMPT_MODEL=google/gemini-4-argon` et `SKILL_PROMPT_MODEL=google/gemini-4-argon`.
- **Frontend** :
  - **`frontend/lib/api.ts`** :
    - Ajout de `skill_prompt_model?: string` dans le type `Config`.
  - **`frontend/components/skills-panel.tsx`** :
    - Envoi explicite du modèle d'excellence (`config?.skill_prompt_model || "google/gemini-4-argon"`) lors du clic sur « Améliorer avec l’IA ».
    - Infobulle descriptive sur le bouton d'amélioration indiquant le nom du modèle utilisé (« Gemini Argon »).
  - **`frontend/components/image-studio-modal.tsx`** :
    - Mise à jour du modèle par défaut pour l'amélioration de prompt vers `google/gemini-4-argon` (Gemini Argon).
    - Infobulle actualisée avec le libellé « Gemini Argon ».
- **Tests** :
  - Mise à jour de `backend/tests/test_api.py::test_skill_improvement_is_unsaved_and_requires_real_provider` pour vérifier l'utilisation de `google/gemini-4-argon` par défaut et le support d'un modèle personnalisé dans le corps de requête.

## 4. Key Decisions
- Utilisation de `google/gemini-4-argon` comme référence de pointe commune pour la reformulation de prompt, alignée avec le planificateur DeepSearch et l'Atelier Multi-Agents.
- Préservation de mécanismes de repli gracieux (`fallback`) vers le modèle par défaut de l'application en cas d'indisponibilité temporaire chez le fournisseur.

## 5. Modified Files
- `backend/app/config.py` : Configuration de `image_prompt_model` et `skill_prompt_model` à `"google/gemini-4-argon"`.
- `backend/app/routers/system.py` : Exposition de `skill_prompt_model` dans `/api/config`.
- `backend/app/schemas.py` : Champ optionnel `model` dans `ImproveSkillPrompt`.
- `backend/app/routers/skills.py` : Prise en charge du modèle dédié d'amélioration de compétences.
- `backend/app/routers/images.py` : Prise en charge de `google/gemini-4-argon` pour les images.
- `backend/app/providers.py` : Tolérance de panne et repli 400/404/422 sur `improve_skill_prompt`.
- `backend/tests/test_api.py` : Test de validation du modèle d'amélioration de compétences.
- `compose.yaml` : Variables d'environnement `IMAGE_PROMPT_MODEL` et `SKILL_PROMPT_MODEL`.
- `.env.example` : Documentation des deux variables.
- `frontend/lib/api.ts` : Typage TypeScript pour `skill_prompt_model`.
- `frontend/components/skills-panel.tsx` : Intégration du modèle et infobulle d'amélioration de compétence.
- `frontend/components/image-studio-modal.tsx` : Intégration de Gemini Argon pour l'amélioration d'image.
- `HANDOFF.md` : Mise à jour du journal de relais.

## 6. Verification
- `npm run test:favorites` (6/6 tests passés).
- `npm run test:themes` (5/5 tests passés).
- `npm run test:research` (2/2 tests passés).
- `npm run typecheck` (`tsc --noEmit` : 0 erreur).
- `PYTHONPATH=backend ./backend/.venv/bin/pytest backend/tests/test_api.py -k "skill or image"` (12/12 tests passés).
- `PYTHONPATH=backend ./backend/.venv/bin/pytest backend/tests/test_providers.py -k "improve"` (3/3 tests passés).
- `PYTHONPATH=backend ./backend/.venv/bin/pytest backend/tests/test_pages.py` (11/11 tests passés).
- `git diff --check` (0 anomalie).

## 7. Known Issues and Risks
- Fichiers `.env` réels : non inspectés, non modifiés (frontière stricte de sécurité).

## 8. Next Action
Prêt pour utilisation directe par l'utilisateur.
