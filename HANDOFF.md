# Relais — 31 octobre 2026

## 1. Project Overview
cLAIr : application d'apprentissage et de révision didactique, conversation IA avancée, backend FastAPI/SQLAlchemy/Python, frontend Next.js 16/React/TypeScript.

## 2. Current Objective
Suppression intégrale des questions méta-méthodologiques ("Quel est le piège à éviter avec...", "Quelle démarche adopter...", etc.) et garantie d'une génération de questions, flashcards et quizz portant à 100% sur le contenu concret du cours fourni (définitions, théorèmes, formules LaTeX, calculs de coordonnées, relation de Chasles, colinéarité).

## 3. Completed Work
- **Identification de la cause racine** :
  1. Les modèles LLM écrivant des formules LaTeX dans des réponses JSON omettaient le doublement de l'antislash (ex: `\vec`, `\sqrt`, `\alpha`). `json.loads` standard levait alors `JSONDecodeError: Invalid \escape`, provoquant silencieusement un repli vers `fallback_study_material`.
  2. L'ancien `fallback_study_material` contenait des templates statiques de méthodologie générale ("Piège fréquent : Quel est le piège ou l'erreur courante à éviter avec : [sujet] ?", "Méthodologie", "Règle d'or"), qui se retrouvaient affichés aux élèves.
  3. L'ancien prompt LLM suggérait des axes méta ("Méthode", "Piège à éviter") au lieu d'interdire les questions de méthodologie.
- **Résolution & Améliorations (`backend/app/providers.py`)** :
  - **Désensibilisation et réparation JSON des antislashs LaTeX** : `re.sub(r"(?<!\\)\\(?![\\\"/])", r"\\\\", candidate)` répare automatiquement toute notation LaTeX non échappée sans altérer les séquences JSON valides (`\"`, `\\`).
  - **Refonte intégrale de `fallback_study_material`** :
    - Élimination complète de tous les templates de méthodologie générique.
    - Analyseur syntaxique multi-passes extrayant les définitions numérotées/puces, termes en gras au sein des phrases, sections du cours, formules mathématiques et règles de calcul directement depuis le texte.
    - Génération de questions factuelles et disciplinaires ciblées ("Que désigne ou définit précisément...", "Concernant [Concept], qu'énonce le cours ?", etc.).
    - Filtre de sécurité `_is_methodology_study_item` éliminant tout énoncé méta résiduel.
  - **Durcissement des Prompts LLM (`generate_study_material`)** :
    - Interdiction formelle et explicite de toute question méta, de démarche d'étude ou d'attitude de l'élève.
    - Consigne stricte : 100% des questions doivent porter exclusivement sur le cours (notions, formules, théorèmes, règles, exemples).
    - Obligation de notations LaTeX KaTeX entre dollars simples `$ ... $`.
    - Catégories exclusivement disciplinaires ('Définition', 'Formule', 'Théorème', 'Propriété', 'Calcul', 'Règle', 'Application').
    - Remplacement de tout élément méta détecté dans le retour LLM par une unité de cours vérifiée.
- **Tests & Vérifications** :
  - `backend/tests/test_study_material.py` : test de régression ajouté `test_study_material_no_generic_methodology_on_vectors_course` (5/5 passés).
  - Suite complète backend : **391 tests passés** avec succès.
  - Test en direct sur le conteneur `tchataiperso-clair-api` avec la conversation réelle sur les vecteurs : 10 cartes générées avec succès par le modèle IA, 100% axées sur le cours de vecteurs (caractéristiques, égalité, Chasles, colinéarité, coordonnées, parallélisme).

## 4. Key Decisions
- **Réparation transparente des échappements LaTeX dans les flux JSON** : permet au LLM d'utiliser naturellement les délimiteurs mathématiques LaTeX sans faire échouer le parsing JSON.
- **Ancrage textuel strict** : le fallback comme le prompt privilégient toujours les concepts concrets extraits du cours.

## 5. Modified Files
- `backend/app/providers.py` : réparation JSON LaTeX, prompts durcis sans méthodologie, nouvelle extraction de cours et suppression des templates méta.
- `backend/tests/test_study_material.py` : ajout de tests de non-régression validant l'absence de questions méta et la présence de contenu disciplinaire.
- `HANDOFF.md` : mise à jour de la documentation d'étape.

## 6. Verification
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_study_material.py` : 5 passés.
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests` : 391 passés.
- `docker compose build clair-api && docker compose up -d clair-api` : conteneur reconstruit et opérationnel (`healthy`).
- Test d'exécution réelle sur la conversation des vecteurs niveau seconde : 10 cartes de cours pures obtenues.

## 7. Known Issues and Risks
- Aucun problème connu.

## 8. Next Action
Prêt pour test utilisateur dans le navigateur sur [http://localhost:3001](http://localhost:3001).
