# Relais — 31 octobre 2026

## 1. Project Overview
cLAIr : application de conversation IA avancée, backend FastAPI/SQLAlchemy/Python, frontend Next.js 16/React/TypeScript. DeepSearch et Mode Apprendre effectuent des investigations web approfondies, capturent les sources avec rigueur, génèrent des visualisations graphiques et produisent des rapports structurés archivés et exportables en formats web (HTML), documents éditoriaux (PDF) et présentations PowerPoint générées par IA.

## 2. Current Objective
Sélection explicite du mode d'analyse lors de l'ajout d'une pièce jointe dans le tchat (Option A) :
1. **Document (Mistral OCR)** : extraction textuelle et structurelle fidèle (PDF, Word, scans, textes, tableaux).
2. **Image (Vision IA détaillée)** : analyse visuelle exhaustive et détaillée de l'image (photos, infographies, schémas, graphiques) directement par le modèle de vision multimodale (`VISION_MODEL`), sans passer par le filtre de l'OCR.
3. **Correction d'affichage & ergonomie du popover** :
   - Suppression du `overflow: hidden` sur `.composer` qui rognait la moitié supérieure du popover flottant.
   - Positionnement en `overflow: visible; position: relative; z-index: 1000`.
   - Sécurisation du clic via `stopPropagation()` sur `mousedown` et déclenchement direct du sélecteur de fichiers.

## 3. Completed Work
- **Backend FastAPI** :
  - `backend/app/routers/attachments.py` : acceptation du paramètre de formulaire `mode: str = Form("auto")` dans `POST /api/attachments`.
  - `backend/app/documents.py` : implémentation du mode explicite `"vision"` :
    - Vérification du type d'image/PDF et normalisation de résolution.
    - Appel direct à `providers.describe_image` avec timeout dédié.
    - Structuration dans `DocumentExtraction` avec `method="vision"` et transcription visuelle détaillée enregistrée dans `extracted_text`.
    - Mode `"ocr"` / `"document"` conservé avec Mistral OCR.
  - `backend/app/serializers.py` : exposition du champ `analysis_mode` (`"ocr" | "vision" | "local" | "finance"`) dans le JSON de l'attachement.
  - `backend/tests/test_api.py` : test unitaire `test_explicit_vision_and_ocr_modes` vérifiant l'appel direct sans OCR en mode vision, le comportement OCR et le rejet propre des formats non compatibles vision (ex: `.txt`).
- **Frontend Next.js** :
  - `frontend/lib/api.ts` : ajout de `analysis_mode?: "ocr" | "vision" | "local" | "finance"` dans le type `Attachment`.
  - `frontend/components/chat-app.tsx` :
    - Popover Option A au clic sur le bouton trombone 📎 proposant les deux choix avec icônes, libellés et descriptions détaillées.
    - Deux inputs `file` séparés (`docInputRef` et `visionInputRef`) avec filtres d'extensions appropriés.
    - Statut d'upload dynamique ("Importation et analyse visuelle (Vision IA)" vs "documentaire (Mistral OCR)").
    - Badges visuels distincts sur les pièces jointes : `👁️ Vision IA` (violet) et `📄 Mistral OCR` (bleu).
    - Panneau accordéon `AttachmentAnalysis` adapté (titre "Analyse visuelle détaillée (Modèle Vision)" et affichage de la description visuelle).
    - Fix d'événements de clic et propagation sur le menu déroulant.
  - `frontend/app/globals.css` :
    - Remplacement de `overflow: hidden` sur `.composer` par `overflow: visible; position: relative;`.
    - Élévation du `z-index` à 1000 et espacement `bottom: calc(100% + 12px)`.
    - Styles complets et animations du popover de sélection et des badges de mode (thèmes clair et sombre).
- **Tests & Déploiement** :
  - Suite complète backend `test_api.py`, `test_document_validation.py`, `test_context.py`, `test_presentation_html.py`, `test_report_integrity.py` : **115 passed en 26.76s**.
  - Build Next.js 16 validé (0 erreur TypeScript, compilation en 2.4s).
  - Images Docker reconstruites et conteneurs opérationnels (`healthy`).

## 4. Key Decisions
- **Option A (Menu Popover au clic sur le trombone)** : préserve la sobriété de la barre d'outils tout en offrant un guidage explicite et deux parcours distincts selon le besoin de l'utilisateur.
- **Routage direct Vision sans passage par Mistral OCR** : en mode "Image (Vision)", l'image n'est plus traitée par l'OCR, ce qui évite qu'une photo avec un petit texte ne soit tronquée et garantit un compte-rendu visuel exhaustif.
- **`overflow: visible` sur le composer** : permet aux popovers et menus de la barre d'outils de flotter naturellement au-dessus du champ de saisie sans être rognés par le bord de la boîte.

## 5. Modified Files
- `backend/app/routers/attachments.py` : paramètre `mode: str = Form("auto")`.
- `backend/app/documents.py` : routage conditionnel `mode="vision"` vers `describe_image`.
- `backend/app/serializers.py` : ajout de `analysis_mode` dans `attachment_json`.
- `backend/tests/test_api.py` : test `test_explicit_vision_and_ocr_modes`.
- `frontend/lib/api.ts` : champ `analysis_mode` sur `Attachment`.
- `frontend/components/chat-app.tsx` : popover Option A, gestion des modes d'upload, badges, stopPropagation et gestion du clic.
- `frontend/app/globals.css` : `overflow: visible` sur `.composer`, styles du popover (z-index: 1000) et badges de mode.
- `HANDOFF.md` : mise à jour de l'état du projet.

## 6. Verification
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_api.py -k test_explicit_vision_and_ocr_modes` : **1 passed**.
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_api.py backend/tests/test_document_validation.py backend/tests/test_context.py backend/tests/test_presentation_html.py backend/tests/test_report_integrity.py` : **115 passed en 26.76s**.
- `npm --prefix frontend run build` : **succès, 0 erreur TypeScript**.
- `docker compose build clair-api clair-web && docker compose up -d clair-api clair-web` : **succès**.
- `docker compose ps` : conteneurs `clair-api` (healthy sur 8001) et `clair-web` (healthy sur 3001).

## 7. Known Issues and Risks
- Aucun problème connu.

## 8. Next Action
Prêt pour test utilisateur dans le navigateur sur [http://localhost:3001](http://localhost:3001).
