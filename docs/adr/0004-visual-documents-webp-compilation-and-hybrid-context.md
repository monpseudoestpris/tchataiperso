# ADR 0004 — Pipeline de compilation des Documents Illustrés (Mistral OCR + WebP) et injection de contexte hybride toutes-pages

- **Statut** : Accepté (en production dans le dépôt)
- **Date** : 2026-11-23

## Contexte
Les ouvrages visuels denses (règles de jeux de société de 40 à 100+ pages, manuels illustrés, rapports financiers trimestriels) nécessitent un raisonnement déductif croisant simultanément plusieurs pages, tableaux et schémas. Un découpage RAG vectoriel classique perd la structure globale du livret et dissocie le texte des figures.

## Décision
1. **Compilation en actifs WebP et Markdown structuré à l'ingestion (`visual_documents.py`)** :
   - Les PDF protégés par permissions éditeur (mot de passe utilisateur vide) sont déverrouillés et normalisés (`normalize_unlocked_pdf`).
   - Mistral OCR 4.1 extrait le Markdown et les coordonnées des figures page par page ; chaque planche complète (`page_N.webp`) et chaque figure détourée (`pX_figY.webp`) sont rendues en WebP haute lisibilité et enrichies de descriptions anatomiques par le modèle Vision.
   - Le même modèle `VisualDocument` (et la liaison `ConversationVisualDoc`) est réutilisé pour les **Rapports Financiers** (`compile_finance_report_to_visual_doc`) et pour les **Documents complémentaires / Volumes** (`asset_prefix="supp_<8hex>_"` dans `visual_doc_links.py`), servis via `/api/docs/{slug}/{asset}` et lus dans la **Liseuse Livre 3D** (`VisualDocBookReader`).
2. **Contexte hybride toutes-pages sans perte (`build_visual_docs_context` dans `context.py`)** :
   - Le budget dédié aux Documents Illustrés est porté à `360 000–450 000` caractères (~110k tokens).
   - Si un ouvrage géant dépasse ce budget, le mode hybride (`_compact_page_figure_alts`) **ne supprime aucune page** : il conserve 100 % du texte et 100 % des URLs d'images WebP de toutes les pages, maintient les descriptions anatomiques longues (900 car.) sur les pages les mieux classées par rapport à la question, et condense uniquement les légendes `![Titre court](url)` sur les autres pages.

## Conséquences
- **Positives** : Zéro dépendance à une base vectorielle (`pgvector`), recoupement multi-pages exact avec citations cliquables `[p. X]` et insertion directe des schémas WebP authentiques du livret dans les réponses du tchat.
- **Contraintes** : Consommation élevée de tokens d'entrée sur les très gros ouvrages, rendant recommandée l'utilisation des modèles à grande fenêtre de contexte (1M tokens, ex. gamme Gemini 3.8 / 4 sur Google Cloud) proposés dans le sélecteur dédié de `VisualDocModal`.
