# HANDOFF.md — État du projet

## 1. Project Overview
Application de chat IA multi-fournisseurs (`tchataiperso`) composée d'un backend **FastAPI / SQLAlchemy 2 / Alembic / SQLite-PostgreSQL** (`backend/`) et d'un frontend **Next.js 16 / React 19 / TypeScript** (`frontend/`), incluant :
- L'éditeur multi-fichiers **Code Canvas** (`CodeCanvas`) avec aperçu HTML/CSS/JS isolé et export `.zip`.
- Le studio **cLAIr Pages** (`WebPageModal`) structuré en **📄 Mes Pages** et **🧩 Mes Apps**, avec système de **Briques Préfaites** (Agent IA).
- L'espace **Marchés Financiers** (`FinanceModal`) avec cotations EODHD/Yahoo, analyse fondamentale, MOAT, rapports trimestriels interactifs (attachables au tchat et au Mode Vocal comme les Documents Illustrés) et avis d'experts.
- Le module **Documents Illustrés (`VisualDocModal`)** pour ingérer un PDF ou une liste ordonnée d'images (règles de jeu, manuels) via **Mistral OCR**, compiler un Markdown enrichi avec schémas WebP et pages originales de secours cliquables `[p. X]`.
- Le module **Voix IA & Mode Vocal Plein Écran** : synthèse vocale **Google Gemini TTS** (`gemini-2.5-flash-tts`, 30 voix, 8 tons + ton libre, `languageCode: "fr-FR"`, repli Cloud TTS `Chirp3-HD`, filtrage Markdown/images/références/guillemets/élisions), dictée vocale **Mistral Voxtral** (`voxtral-mini-latest`, repli Google Gemini Audio), vitesses `0.85×`–`2×`, Pause/Reprise et **Mode Vocal Plein Écran Mains-Libres + Clavier** (`VoiceFullscreenModal`).
- Le connecteur agentique **Hermes Agent** et la recherche approfondie **Google Deep Research** (Interactions API).

## 2. Current Objective
1. **Adjonction à tout moment de Documents complémentaires (FAQ, Errata, Extensions, Aide de jeu, Annexes) ET de Liens Externes (Forums, Sites, Vidéos YouTube) sur un Document Illustré (`visual_doc_links.py` + `VisualDocLinksPanel`)** :
   - Pouvoir adjoindre dès l'ingestion **et à tout moment après coup** :
     - Des **fichiers complémentaires locaux** (`PDF`, `DOCX`, `MD`, `TXT`, `CSV`, `JSON`, `PNG`, `JPEG`, `WebP`) typés (`FAQ / Errata officiel`, `Aide de jeu / Référence`, `Extension / Module`, `Annexe`), extraits via Mistral OCR / parseurs locaux, résumés par l'IA et prioritaires en cas d'erratum officiel.
     - Des **liens externes** (transcription horodatée `[MM:SS]` des vidéos YouTube avec lecteur intégré, fils de forums type BoardGameGeek/Reddit/TricTrac, pages web ou PDF distants), protégés contre le SSRF et résumés automatiquement.
2. **Typologie métier des Documents Illustrés, Raisonnement Déductif & Forums Dédiés (`visual_doc_profiles.py`)** :
   - 9 catégories complètes (`boardgame`, `rpg_lore`, `scientific`, `financial`, `technical`, `legal`, `medical`, `educational`, `general`), raisonnement déductif par recoupement multi-pages obligatoire et recherche automatique sur les forums dédiés (ex. `site:boardgamegeek.com` pour un jeu de société).
3. **Liseuse Livre 3D interactive (`VisualDocBookReader`)** & **Mode Hybride toutes-pages (`450k` car.)**.

**Statut** : Implémenté et vérifié.

## 3. Completed Work
- **Liens complémentaires & Documents complémentaires (FAQ, Errata, Extensions) sur les Documents Illustrés** :
  - Backend : module `backend/app/visual_doc_links.py` + `normalize_unlocked_pdf` dans `backend/app/documents.py` (déverrouillage automatique des PDF d'éditeurs protégés uniquement par permissions InDesign/Acrobat avec `user_password=""` et réécriture d'un flux PDF propre non chiffré pour Mistral OCR, tolérance aux octets avant `%PDF-`, isolation des erreurs CMap/polices page par page et filet de sécurité `pypdfium2`). Chaque document complémentaire PDF/image est désormais compilé intégralement via `ingest_visual_document(..., asset_prefix="supp_<8hex>_")` (pages WebP `supp_<8hex>_page_N.webp`, schémas WebP, Markdown compilé, `pages` et résumé IA) et les fichiers texte/Word/Markdown sont paginés en pages de livre lisibles dans la Liseuse 3D.
  - Frontend : panneau `VisualDocLinksPanel` + **barre de sélection de volume (`volumeBar`)** dans `VisualDocModal` permettant d'ouvrir n'importe quel document complémentaire directement dans **📖 Liseuse 3D** (pages qui se tournent, 5 thèmes, Plein écran), **Schémas extraits**, **Pages originales** et **Markdown compilé** (boutons dédiés « 📖 Lire en Livre 3D » et « 📝 Markdown compilé » sur chaque carte).
  - Frontend : nouveau panneau dédié `frontend/components/visual-doc-links-panel.tsx` (+ `.module.css`) accessible via l'onglet **« 🔗 Sources & Vidéos »** de `VisualDocModal` (ajout multi-URLs à tout moment, lecteur YouTube intégré `youtube-nocookie.com`, résumé IA stylisé sans syntaxe Markdown brute, accordéon pour lire la transcription/texte source complet, actualisation et suppression) + champ d'ajout de liens initiaux dès l'onglet d'ingestion.
- **Typologie des Documents Illustrés, Déduction & Recherche sur Forums Dédiés** :
  - Backend : nouveau module modulaire `backend/app/visual_doc_profiles.py`, colonne `visual_documents.doc_category` (`VARCHAR(40)`), migration Alembic `0029_add_visual_doc_category` (enregistrée dans `cli.py`) + création/backfill idempotent au démarrage dans `main.py` (classant automatiquement les règles existantes en `boardgame` et rapports financiers en `financial`), endpoint `GET /api/visual-docs/categories`, prise en charge dans `POST /api/visual-docs` et `PATCH /api/visual-docs/{doc_id}` (`routers/visual_docs.py`, `routers/finance.py`, `schemas.py`, `serializers.py`).
  - Prompt déductif (`backend/app/context.py`) : consigne explicite `RAISONNEMENT DÉDUCTIF PAR RECOUPEMENT OBLIGATOIRE` + supplément spécialisé par catégorie (`build_category_prompt_supplement`) + distinction claire entre déduction du document `[p. X]` et forums externes `[n]`.
  - Recherche automatique sur forums dédiés (`backend/app/routers/messages.py`) : génération intelligente de 2 requêtes ciblées (`generate_visual_doc_forum_queries`, ex. requête anglaise `site:boardgamegeek.com` + requête FAQ/forums francophones avec nettoyage du titre du jeu via `clean_doc_subject_for_search`), tolérante aux pannes réseau en mode auto.
  - Frontend (`frontend/lib/api.ts`, `frontend/components/visual-doc-modal.tsx`, `visual-doc-modal.module.css`, `visual-doc-book-reader.tsx`) : grille visuelle de sélection des 9 types avec aperçu des forums associés à l'ingestion (auto-détection selon le nom du fichier), badge de catégorie dans la bibliothèque, sélecteur rapide `<select>` dans l'en-tête d'un document existant pour changer sa catégorie à tout moment, et sélection automatique du thème de livre optimal.
- **Liseuse Livre 3D & Thèmes (`frontend/components/visual-doc-book-reader.tsx` + `.module.css`)** :
  - Nouvel onglet par défaut **« 📖 Liseuse 3D »** dans `VisualDocModal` (`frontend/components/visual-doc-modal.tsx`).
  - Animation 3D réaliste de feuille qui se tourne (`rotateY` double-face avec ombre dynamique dans la pliure centrale, coins de page cornés au survol, navigation flèches clavier `←`/`→`, ruban marque-page en bas, bruissement de page synthétisé via Web Audio API activable/désactivable).
  - Bascule **2 pages (Livre ouvert)** / **1 page** et bouton **Plein écran** immersif (`100vw × 100vh`, fermeture via `Échap` ou bouton `Réduire`).
  - 5 thèmes typographiques : `oldbook` (Grimoire & Règles — vélin patiné, `Cinzel` & `EB Garamond`), `report` (Rapport Éditorial — papier financier ivoire, `Playfair Display` & `Crimson Pro`, activé automatiquement pour les rapports financiers), `parchment` (Manuscrit Royal), `nocturne` (Cabinet Nocturne cuir & or), `cyber` (Manuel Holo-Tech).
  - 4 modes de lecture dans la liseuse 3D : **Fac-similé** (planches originales WebP avec loupe HD), **Illustré** (planche originale + texte composé et schémas intégrés), **Éditorial** (mise en page livre avec lettrine sur le premier paragraphe, tableaux stylisés et figures cliquables) et **Markdown & Descriptions** (rendu Markdown richement stylisé sans syntaxe brute `#` ou `**`, avec encadrés de descriptions anatomiques Vision/OCR + miniature WebP cliquable au fil du texte, et bouton optionnel « Code brut » / « Copier »). L'onglet « Markdown compilé » de `VisualDocModal` affiche également un rendu stylisé par défaut avec bascule « Éditer le code source ».
- **Contexte Documents Illustrés (`backend/app/context.py` & `backend/app/visual_documents.py`)** :
  - Plancher de `visual_budget` relevé à `360 000` caractères (plafond `450 000` caractères, soit ~110k tokens) dans `build_context`, permettant aux grosses règles de 40 à 60 pages (avec 150+ schémas décrits) d'être envoyées à 100 % sans aucune coupure.
  - Mode **Hybride toutes-pages (`_compact_page_figure_alts`)** dans `build_visual_docs_context` : si un ouvrage géant (80–150 pages) dépasse le budget, le système conserve **100 % des pages (tout le texte + toutes les URLs WebP `/api/docs/...`)** en gardant les descriptions anatomiques longues (900 car.) sur les pages les plus pertinentes pour la question et en condensant uniquement les légendes `![Titre court](url)` sur les autres pages — aucune page n'est jamais supprimée.
  - Normalisation singulier/pluriel (`dragon` ↔ `dragons`) dans `_tokenize_query` et bonus prioritaire sur les numéros de pages mentionnés (`_extract_explicit_page_numbers`).
- **Voix IA par défaut dans les paramètres** (session précédente conservée) :
  - Colonne `users.default_voice`, migration `0028_add_user_default_voice`, section dédiée dans `SettingsModal`.
- **Installeur complet multi-OS (`scripts/install.sh` + `scripts/install_lib/`)** :
  - `scripts/install_lib/common.sh`, `system.sh`, `env_setup.py`, `gcloud_setup.sh`, `scripts/install.sh`, `.env.example`, `README.md`.
- **Travaux précédents conservés dans l'arbre de travail** (non commités) : Mode Vocal Plein Écran (`VoiceFullscreenModal`) et pont Rapports Financiers → Documents Illustrés interactifs (`compile_finance_report_to_visual_doc`).

## 4. Key Decisions
- **Réutilisation de `VisualDocument` + `ConversationVisualDoc` pour les rapports financiers** : aucune migration de schéma SQL nécessaire, bénéficie immédiatement de `build_visual_docs_context` (sélection intelligente des pages pertinentes), des citations `[p. X]` cliquables et du rendu WebP sécurisé `/api/docs/{slug}/page_N.webp`.
- **Composant `VoiceFullscreenSession` monté conditionnellement** : garantit le nettoyage immédiat des pistes micro (`MediaStream`), `AudioContext` et timers dès la fermeture, sans effet de bord React 19.

## 5. Modified Files
- Créés (session courante) :
  - `backend/app/visual_doc_links.py`, `backend/app/visual_doc_profiles.py`.
  - `backend/migrations/versions/0029_add_visual_doc_category.py`, `backend/migrations/versions/0030_add_visual_doc_links.py`.
  - `frontend/components/visual-doc-links-panel.tsx`, `frontend/components/visual-doc-links-panel.module.css`.
  - `frontend/components/visual-doc-book-reader.tsx`, `frontend/components/visual-doc-book-reader.module.css`.
  - `backend/migrations/versions/0028_add_user_default_voice.py`.
- Modifiés (session courante) :
  - `backend/app/context.py`, `backend/app/visual_documents.py`, `backend/app/routers/visual_docs.py`, `backend/app/routers/messages.py`, `backend/app/routers/finance.py`, `backend/tests/test_visual_documents.py`.
  - `frontend/components/visual-doc-modal.tsx`, `frontend/components/visual-doc-modal.module.css`, `frontend/lib/api.ts`.
  - `backend/app/models.py`, `backend/app/cli.py`, `backend/app/main.py`, `backend/app/voice.py`, `backend/app/schemas.py`, `backend/app/routers/settings.py`, `backend/app/routers/voice.py`, `backend/app/serializers.py`, `backend/tests/test_settings.py`.
  - `frontend/lib/api.ts`, `frontend/components/settings-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`, `frontend/app/interface-themes.css`, `HANDOFF.md`.
- Autres fichiers déjà modifiés/créés dans l'arbre de travail (sessions précédentes — installeur, Mode Vocal Plein Écran & Rapports Financiers) :
  - `scripts/install.sh`, `scripts/install_lib/*`, `.env.example`, `README.md`, `backend/app/voice_sanitize.py`, `backend/app/routers/finance.py`, `backend/app/routers/system.py`, `frontend/components/voice-fullscreen-modal.tsx`, `frontend/components/finance-reports-panel.tsx`, etc.

## 6. Verification
- `cd backend && .venv/bin/python -m pytest tests/test_visual_documents.py tests/test_context.py tests/test_settings.py tests/test_voice.py tests/test_migrations.py -q` : **RÉUSSI**.
- `cd frontend && npx tsc --noEmit` : **RÉUSSI** (0 erreur).
- `cd frontend && npx eslint components/visual-doc-book-reader.tsx components/visual-doc-modal.tsx` : **RÉUSSI** (0 erreur).
- Non exécutés : redémarrage des conteneurs Docker `clair-api` / `clair-web` si l'instance Docker tourne en parallèle.

## 7. Known Issues and Risks
- Sur un PC Windows, exécuter `./scripts/install.sh` depuis **WSL2** (Ubuntu/Debian) avec Docker Desktop actif côté Windows.
- L'accès micro navigateur (`getUserMedia` / `AudioContext`) exige `localhost` / `127.0.0.1` ou HTTPS.

## 8. Next Action
Sur un nouveau PC (ou pour valider sur ce poste), lancer `./scripts/install.sh --check` pour le diagnostic ou `./scripts/install.sh` (ou `--all` / `--local`) pour installer et démarrer toute l'application.
