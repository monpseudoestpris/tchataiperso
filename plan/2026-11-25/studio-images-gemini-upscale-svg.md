# Studio Image — Verrouillage Gemini Google Cloud, Upscale Ideogram v2 (8 modèles) & Vecteurs SVG

- **Créé le** : 2026-11-25
- **Statut** : TERMINÉ

## 1. Demande & Objectif Vérifiable
1. **Modèles d'image Gemini sur Google Cloud exclusivement** : garantir qu'aucune génération d'image Gemini (`google/*`, `gemini-*`, `imagen-*`) dans le Studio Image ne passe par OpenRouter (même si `LLM_API_KEY` est active), gérer le repli automatique `région -> global` et `-preview` sur Vertex AI, et afficher explicitement le routage `Google Cloud (Vertex AI)` / `Google Gemini API` dans l'UI.
2. **Upscale d'images Ideogram v2 (8 modèles)** : intégrer tous les modèles de `https://developer.ideogram.ai/v2/api-reference/images/upscale` (`auto`, `topaz-standard-2`, `topaz-text-refine`, `topaz-wonder-3-5`, `topaz-wonder-4`, `topaz-bloom-2`, `topaz-redefine`, `nano-banana-pro`) avec leurs paramètres officiels, validation des limites (`8192 px` / `100 MP`) et téléchargement jusqu'à `60 Mio`.
3. **Vecteurs Ideogram Vector 1.0 (`generate-svg` & `image-to-svg`)** : intégrer `POST /v2/svg/generate/ideogram-vector-1` et `POST /v2/svg/vectorize/ideogram-vector-1` avec polling asynchrone, sanitization XML anti-XSS/XXE à l'ingestion et en-tête `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` à la diffusion.

## 2. Décisions Validées (One-Way Doors & Arbitrages)
- **Isolation stricte Gemini vers Google Cloud (Vertex AI prioritaire)** : tout modèle d'image Google dans le Studio Image passe exclusivement par Google Cloud (`vertex_oauth` > `vertex_api_key` > `gemini_api`) sans aucun repli vers OpenRouter `/images`. Si Google Cloud n'est pas configuré ou échoue, une erreur claire est retournée (zéro consommation OpenRouter).
- **Périmètre SVG** : `Ideogram Vector 1.0` conformément aux deux endpoints demandés (`vectors/generate-svg` et `vectors/image-to-svg`).
- **Stockage sans migration DB** : réutilisation de la table `generated_images` existante (`mime_type="image/svg+xml"` pour `.svg`).

## 3. Découpage & Suivi des Tranches
- [x] **T1 — Audit, verrouillage et badges Google Cloud pour les images Gemini**
  `[Two-Way] · [Runtime] · [~160 lines / 6 files] · [Seams checked: Yes]`
- [x] **T2 — Backend Ideogram v2 : Upscale (8 modèles), Vecteurs SVG (`generate-svg` & `image-to-svg`) & Sanitization SVG**
  `[Two-Way] · [Runtime] · [~390 lines / 6 files] · [Seams checked: Yes]`
- [x] **T3 — Interface Studio Image : Panneaux Sprout `Upscale HD` & `Vecteur SVG` + Visualiseur SVG**
  `[Two-Way] · [Runtime] · [~460 lines / 5 files] · [Seams checked: Yes]`

## 4. Journal de Preuves
- **T1** : `google_cloud.py`, `config.py`, `providers_images.py`, `routers/images.py`, `frontend/lib/api.ts`, `image-studio-modal.tsx`, `image-model-modal.tsx`. Commandes : `pytest tests/test_google_cloud.py tests/test_providers.py tests/test_api.py -q` (`217 passed`), `npm run typecheck` (`0 error`).
- **T2** : `svg_sanitize.py`, `ideogram_upscale_svg.py`, `providers_images.py`, `providers.py`, `schemas.py`, `routers/images.py`, `routers/attachments.py`, `tests/test_ideogram_upscale_svg.py`. Commande : `pytest tests/test_ideogram_upscale_svg.py -q` (`4 passed`).
- **T3 & Vérification finale** : `image-studio-upscale-panel.tsx`, `image-studio-svg-panel.tsx`, `image-studio-ext.module.css`, `image-studio-modal.tsx`, `tests/image-studio-gemini-upscale-svg.test.mjs`.
  - Backend complet hors-ligne (`HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 .venv/bin/python -m pytest -q`) : **`687 passed, 0 failed`**.
  - Frontend (`npm run typecheck && npx eslint components/image-model-modal.tsx components/image-studio-upscale-panel.tsx components/image-studio-svg-panel.tsx lib/api.ts --max-warnings 0 && npm test && npm run build`) : **`0 error, 0 warning`, `38 passed, 0 failed`, `next build` OK**.

## 5. Prochaine Tranche
Aucune — plan terminé.
