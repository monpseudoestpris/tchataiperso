# Relais — 1 novembre 2026

## 1. Project Overview
cLAIr : application d'apprentissage et de révision didactique, conversation IA avancée, Studio Image et multimédia, Espaces thématiques avec mémoire continue, Studio cLAIr Pages (générateur de documents web HTML5 autonomes), backend FastAPI/SQLAlchemy/Python, frontend Next.js 16/React/TypeScript.

## 2. Current Objective
Ajout d'une archive autonome `.zip` (`backend/app/assets/svg_assets.zip`) et explicitation de l'architecture d'accès/tri des assets par le LLM :
- **Archive zip compacte** : `backend/app/assets/svg_assets.zip` (9,3 Mo compressé) regroupant les 6 943 fichiers SVG (5 203 Tabler Icons + 1 740 unDraw).
- **Extraction automatique hors-ligne** : `ensure_svg_assets()` détecte la présence du `.zip` et l'extrait en 0,4 seconde sans aucune requête réseau.
- **Accès & Tri par le LLM** :
  - Le LLM n'ingère pas 7 000 fichiers dans son contexte (ce qui saturerait la mémoire).
  - Il utilise des **balises déclaratives légères** (`<clair-svg name="undraw/science" />`, `<clair-svg name="tabler/dna" />`).
  - Le tri se fait via la matrice de détection contextuelle de `PAGE_SYSTEM_PROMPT` et la connaissance sémantique pré-entraînée du modèle sur les conventions standard de ces bibliothèques.
  - La substitution dynamique et la teinte CSS (`var(--primary)`) sont opérées à la volée par le backend FastAPI avec cache mémoire instantané.

## 3. Completed Work
- **Génération de l'archive `backend/app/assets/svg_assets.zip`** (9,39 Mo compressé pour 6 943 SVGs).
- **Support de décompression dans `backend/app/svg_assets.py`** :
  - Détection automatique prioritaire du zip local avant tout appel réseau.
  - Extraction instantanée en local testée avec succès (`scripts/download_svg_assets.py --force`).
- **Tests & Validation (`backend/tests/test_pages.py`)** :
  - 5/5 tests validés.
- **Documentation et explications** préparées pour l'utilisateur.

## 4. Key Decisions
- **Archive zip unique de 9,3 Mo** : solution optimale pour transporter ou archiver l'ensemble des bibliothèques de façon 100 % autonome sans dépendre de registries externes.

## 5. Modified Files
- `backend/app/assets/svg_assets.zip` : archive zip compressée des banques vectorielles.
- `backend/app/svg_assets.py` : décompression prioritaire depuis le zip.
- `HANDOFF.md` : journal de relais mis à jour.

## 6. Verification
- `python3 scripts/download_svg_assets.py --force` : extraction réussie depuis l'archive locale en < 0,5s.
- `PYTHONPATH=backend pytest backend/tests/test_pages.py` : 5 passed en 3.73s.
- `docker compose ps` : conteneurs sains (`healthy`).

## 7. Known Issues and Risks
- Aucun problème détecté.

## 8. Next Action
- Poursuivre les évolutions selon les retours de l'utilisateur.
