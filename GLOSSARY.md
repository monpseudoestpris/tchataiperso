# GLOSSARY.md — Langage Ubiquitaire & Correspondances (UI / Front / Back / DB)

Ce glossaire fige les termes métier canoniques du projet **cLAIr** (`tchataiperso`) et documente leurs correspondances exactes entre l'interface utilisateur (français), le frontend (`frontend/`), le backend (`backend/app/`) et les deux bases de données (`DATABASE_URL` PostgreSQL/SQLite vs `finance_warehouse.db` SQLite WAL).

---

## 1. Documents, Médias & Édition Web

### 1. Document Illustré *(et ses Volumes / Compléments)*
- **Définition métier** : Ouvrage visuel multi-pages (livret de règles de jeu, manuel technique, bande dessinée ou rapport financier compilé) ingéré via Mistral OCR 4.1 + descriptions anatomiques Vision, dont chaque planche (`page_N.webp`) et chaque schéma (`pX_figY.webp`) sont découpés en WebP et consultables dans la Liseuse Livre 3D ou attachables à une conversation.
- **DB Principale (`models.py`)** : Table `visual_documents` (`VisualDocument`) + table de liaison `conversation_visual_docs` (`ConversationVisualDoc`). Les fichiers complémentaires et liens externes sont stockés en JSON dans la colonne `visual_documents.external_links`.
- **Backend** :
  - Routes CRUD : `/api/visual-docs` (`routers/visual_docs.py`, `visual_documents.py`, `visual_doc_profiles.py`, `visual_doc_links.py`).
  - Route de service des fichiers WebP : `/api/docs/{slug}/{asset}` (incluant `cover.webp` et le préfixe `supp_<8hex>_` pour les documents complémentaires).
- **Frontend** : `VisualDocModal`, `VisualDocGallery`, `VisualDocBookReader`, `VisualDocLinksPanel`, types `VisualDocSummary` / `VisualDocDetail` (`lib/api.ts`).
- **Règle d'alignement** :
  - Dans la colonne JSON `external_links`, une entrée avec `link_type == "document"` et `asset_prefix == "supp_<8hex>_"` est exposée par le sérialiseur sous `supplementary_docs` et affichée dans l'UI sous le nom de **« Volume »** (barre de sélection de volume de la Liseuse 3D) ou **« Document complémentaire »** (FAQ, Errata, Extension).
  - Ne jamais citer un nom de fichier brut `.webp` entre crochets dans le tchat ; utiliser les citations de page `[p. X]` et les images Markdown `/api/docs/{slug}/...`.

### 2. Pièce jointe (`Attachment`)
- **Définition métier** : Fichier unitaire (PDF, image, DOCX, texte, CSV) ou ressource URL (transcription intégrale de vidéo YouTube, cotation boursière ponctuelle) attaché directement à un message de tchat.
- **DB Principale (`models.py`)** : Table `attachments` (`Attachment`, colonne `extracted_text` + JSON structuré `extraction` par page, rattachée à `message_id`).
- **Backend** : `/api/attachments` (`routers/attachments.py`, `documents.py`, `youtube.py`).
- **Frontend** : Type `Attachment`, composant `AttachmentAnalysis` (`components/chat-attachment-analysis.tsx`), modale d'import `ChatUrlAttachModal` (`components/chat-url-attach-modal.tsx`), registre `YOUTUBE_TRANSCRIPT_ACTIONS` (`lib/youtube-actions.ts`), avec `analysis_mode: "ocr" | "vision" | "local" | "finance"` et détection YouTube (`isYoutube`, `youtube_meta`).
- **Règle d'alignement** : Ne jamais confondre une **Pièce jointe** (`Attachment`, portée par un `Message` unique) avec un **Document Illustré** (`VisualDocument`, bibliothèque persistante rattachée à une `Conversation` entière via `ConversationVisualDoc`) ni avec une **Vidéo Sauvegardée** (`SavedVideo`, bibliothèque persistante de vidéos YouTube de l'utilisateur). Un **Rapport Trimestriel Financier** (`FinanceQuarterlyReport`) peut être promu en `VisualDocument` via `compile_finance_report_to_visual_doc`.

### 2 bis. Vidéo Sauvegardée (`SavedVideo` / « Mes Vidéos »)
- **Définition métier** : Fiche persistante par utilisateur conservant une vidéo YouTube importée : titre (renommable), lien canonique, chaîne, durée, langue des sous-titres, **transcription 100 % intégrale** (`transcript_markdown`), **résumé principal** (`summary_markdown`) et historique des analyses IA générées (`analyses`).
- **DB Principale (`models.py`)** : Table `saved_videos` (`SavedVideo`, contrainte `UNIQUE (user_id, video_id)`, migration Alembic `0031_add_saved_videos`).
- **Backend** : `/api/videos/*` (`routers/videos.py`, `saved_videos.py`, `youtube.py`), alimenté automatiquement lors de `POST /api/attachments/url` (`save_to_library=True`) ou par import direct `POST /api/videos`, et rattachable instantanément au tchat via `POST /api/videos/{id}/attach`.
- **Frontend** : Modale bibliothèque `VideoLibraryModal` (`components/video-library-modal.tsx`), types `SavedVideoSummary` / `SavedVideoDetail` (`lib/api.ts`), accessible depuis `ToolsModal` (« Mes Vidéos ») et `ChatUrlAttachModal`.

### 3. cLAIr Pages : Page, App & Briques IA *(vs Site HTML de conversation)*
- **Définition métier** :
  - **cLAIr Pages (`WebPage`)** : Studio autonome de création, d'édition multi-versions et de publication (`public_token`) de pages éditoriales (**« 📄 Mes Pages »**, `kind = "page"`) et de mini-applications interactives (**« 🧩 Mes Apps »**, `kind = "app"`) assemblant des **Briques Préfaites IA** (`bricks`).
  - **Site HTML de conversation (`ChatSite`)** : Instantané HTML éditorial privé, immuable et sans JavaScript actif, généré à partir d'un tour ou d'une discussion complète (**« Sortie → Site HTML »**).
- **DB Principale (`models.py`)** :
  - Studio : Tables `web_pages` (`WebPage`, colonnes `kind`, `bricks`, `public_token`, `is_published`) et `web_page_versions` (`WebPageVersion`, colonnes `html_content`, `canvas_files`).
  - Instantané de tchat : Table `chat_sites` (`ChatSite`, colonnes `conversation_id`, `input_hash`, `scope`, `html_content`).
- **Backend** : `/api/pages/*` (`routers/pages.py`, `page_generator.py`, `page_bricks.py`, `page_wizard.py`) **vs** `/api/conversations/{id}/sites` (`chat_site.py`, `chat_site_store.py`).
- **Frontend** : `WebPageModal` (`web-page-modal.tsx`, types `WebPage`, `WebPageVersion`, `PageBrick`, `AppDiagram`) **vs** `ChatAttachedSites` (`chat-attached-sites.tsx`).
- **Règle d'alignement** : `ChatSite` et `WebPage` ont des cycles de vie strictement séparés (un `ChatSite` est supprimé avec sa conversation et n'apparaît jamais dans la bibliothèque `/api/pages`).

### 4. Code Canvas (`CanvasFile`)
- **Définition métier** : Ensemble de fichiers sources multi-langages (`{ path, language, content }`) éditables et prévisualisables dans un bac à sable HTML/CSS/JS isolé avec export `.zip`.
- **DB Principale (`models.py`)** : Colonne JSON `web_page_versions.canvas_files` (pour les Apps cLAIr Pages) ou blocs de code extraits des messages (`messages.content`) en mode `code_mode`.
- **Backend** : Champ `canvas_files` dans `routers/messages.py` et `routers/pages.py`.
- **Frontend** : Composant `CodeCanvas` (`components/code-canvas.tsx`), types `CanvasFile` (`lib/code-canvas.ts`) et `WebPageCanvasFile` (`lib/api.ts`).

---

## 2. Marchés Financiers & Entrepôt Boursier

### 5. Identifiant d'instrument boursier (`symbol` canonique vs `eod_ticker` vs `yahoo_symbol`)
- **Définition métier** : Code identifiant une action, un ETF, un fonds (`EUFUND`) ou un indice (`.INDX`).
- **DB Principale & Entrepôt (`finance_warehouse.db`)** :
  - `symbol` : Clé primaire canonique interne dans `finance_instruments`, `finance_eod_bars`, `finance_fundamental_facts`, `finance_screener_snapshots`, `finance_screener_technicals`, `finance_user_watchlist_items`.
  - `eod_ticker` : Identifiant complet EODHD au format `CODE.EXCHANGE` (ex. `AI.PA`, `SAP.XETRA`, `AAPL.US`).
  - `yahoo_symbol` : Identifiant Yahoo Finance (ex. `AI.PA`, `SAP.DE`, `^FCHI`).
  - `isin` : Code international ISIN (ex. `FR0000120073`).
- **Backend** : Toujours résoudre un ticker entrant via `resolve_canonical_symbol(db_path, symbol)` (`finance_warehouse.py`) et `resolve_candidate_eod_tickers` (`finance_provider.py`, qui gère les équivalences `.DE` $\leftrightarrow$ `.XETRA/.F`, `.L` $\leftrightarrow$ `.LSE`, `.T` $\leftrightarrow$ `.TSE`).
- **Frontend** : Paramètre `symbol` ou `query` dans `lib/api.ts`, liens internes cliquables `clair-finance://ticker/SYMBOL` dans le tchat.
- **Règle d'alignement** : Lors de l'insertion dans le Screener (`upsert_screener_snapshots`), toute ligne « catalogue » créée sous un alias (ex. `SAP.XETRA`) qui doublonne un instrument déjà indexé sous une autre clé canonique (ex. `SAP.DE`) doit être dédoublonnée.

### 6. Liste de suivi (`Watchlist`)
- **Définition métier** : Liste nommée et ordonnée de valeurs boursières suivies par un utilisateur, avec note personnelle par ligne.
- **DB Principale (`models.py`)** : Tables ORM `finance_watchlists` (`FinanceWatchlist`) et `finance_watchlist_items` (`FinanceWatchlistItem`, contrainte `UNIQUE (list_id, symbol)`).
- **Entrepôt Finance (`finance_warehouse.db`)** : Tables miroir SQLite `finance_user_watchlists` et `finance_user_watchlist_items`.
- **Backend** : `/api/finance/watchlists` (`routers/finance.py`, `finance_watchlist.py`), outil tchat `finance_get_watchlists` (`finance_chat_tools.py`).
- **Frontend** : `FinanceWatchlistTable` (`finance-watchlist-table.tsx`), `FinanceFullscreenTickerSwitcher`.
- **Règle d'alignement (Double écriture)** : Toute mutation sur `FinanceWatchlist` / `FinanceWatchlistItem` dans la DB principale doit appeler `sync_user_watchlists_to_warehouse` pour maintenir le miroir SQLite à jour (utilisé par les filtres `watchlist_id` du Screener et les outils Finance du Tchat). Toujours filtrer par `user_id`.

### 7. Dossier Boursier / Fiche Valeur (`FinanceDossier` vs `FinancialDashboardData`)
- **Définition métier** : Vue complète d'une action combinant cotation, historique OHLCV, états financiers pluriannuels normalisés, valorisation intrinsèque, scores de qualité et calendrier de publication.
- **Entrepôt Finance (`finance_warehouse.db`)** : Assemblé depuis `finance_instruments`, `finance_eod_bars`, `finance_fundamental_facts`, `finance_raw_snapshots` et `finance_fundamentals_queue`.
- **Backend** :
  - `/api/finance/details` (`get_financial_dashboard_data` dans `finance.py`) : Cotations + barres EOD pour le graphique + statistiques résumées (`FinancialStats`).
  - `/api/finance/dossier` (`get_financial_dossier` dans `finance_dossier.py`) : Dossier fondamental profond multi-années, ratios, scores Uncle Stock, calcul intrinsèque et `fundamentals_schedule`.
  - Outil tchat : `finance_get_stock_dossier` (`finance_chat_tools.py`).
- **Frontend** : `FinancialDashboardData` (graphique principal TradingView `FinanceTvChart` et en-tête de `FinanceModal`) **vs** `FinanceDossier` (`FinanceDossierPanel`, sous-onglet **« Fiche Complète »**).

### 8. Analyses IA Finance (`MOAT`, `Avis d'experts`, `Analyse Dossier`, `Rapports Trimestriels`, `Actualités`)
- **Définition métier** : Synthèses et évaluations structurées générées par IA sur une valeur boursière et archivées en base.
- **DB Principale (`models.py` — scopées par `user_id`)** :
  - `finance_stock_moats` (`FinanceStockMoat` : `moat_rating`, `moat_score`, `pillars`).
  - `finance_quarterly_reports` (`FinanceQuarterlyReport` : PDF/texte importé, `extracted_tables`, `key_metrics`, `summary_markdown`).
  - `finance_stock_news` (`FinanceStockNews` : synthèse d'actualités sauvegardée).
- **Entrepôt Finance (`finance_warehouse.db` — partagées par `symbol`)** :
  - `finance_ai_analyses` : Archive unifiée (`kind = 'dossier' | 'expert' | 'moat'`, `expert_id`, `verdict`, `conviction`, `horizon`, `markdown`, `content_html`).
- **Backend** : `finance_moat.py`, `finance_experts.py`, `finance_dossier.py`, `finance_reports.py`, `finance_news.py`. Outil tchat : `finance_get_saved_analyses` (qui interroge à la fois `finance_ai_analyses` dans l'entrepôt et `FinanceStockMoat` / `FinanceQuarterlyReport` pour le `user_id` courant).
- **Frontend** : Sous-onglets `FinanceMoatPanel`, `FinanceExpertsPanel`, `FinanceDossierPanel`, `FinanceReportsPanel`, `FinanceNewsPanel` (gardés montés en mémoire `hidden` dans `FinanceModal` pour ne jamais interrompre une génération asynchrone).

### 9. Screener Boursier, Unités de temps (`timeframe`), `IsoPressure` & Lignes Catalogue
- **Définition métier** : Moteur de filtrage et de tri multi-critères sur l'univers d'actions et d'ETFs de l'entrepôt, combinant type d'actif (`stock` vs `etf`), géographie/marchés (`PA`, `US`, `XETRA`, `LSE`…), ratios fondamentaux, 31 scores Uncle Stock et indicateurs techniques multi-unités.
- **Entrepôt Finance (`finance_warehouse.db`)** :
  - `finance_screener_snapshots` : 1 ligne par `symbol` (`asset_type = 'stock' | 'etf'`, fondamentaux, performances, `market_zone`, `country`, `scores_json`, indicateurs techniques jour).
  - `finance_screener_technicals` : Indicateurs techniques pré-calculés par unité de temps (`PRIMARY KEY (symbol, timeframe) WITHOUT ROWID` où `timeframe IN ('day', 'week', 'month', 'quarter')`), incluant l'indicateur propriétaire **IsoPressure** (`isopressure_raw`, `p5`, `p20`, `p50`, `p100`, `p200`, `isopressure_20_50_diff`, `isopressure_20_50_dir`, croisements).
- **Backend** : `finance_screener.py` (Passe 1 SQL whitelistée avec `LEFT JOIN` multi-unités + Passe 2 Python extensible via `register_post_filter_evaluator` + hydratation EOD légère `hydrate_screener_bars_batch`), `finance_technicals.py`, `finance_geography.py`, `finance_scores.py`, `finance_warehouse.py` (`get_etf_exchange_catalog_counts`, `seed_etfs_from_exchange_catalog`). Outil tchat : `finance_screener_query`.
- **Frontend** : `FinanceScreenerPanel` (onglet `4 · Screener` de `FinanceModal`, lien tchat `clair-finance://screener` ; le chargement des cours et catalogues ETF s'effectue dans l'onglet `5 · Données & Synchro`, avec bouton de redirection lorsque des ETFs manquent).
- **Règle d'alignement** :
  - Le terme UI **« Unité »** (`Jour · Semaine · Mois · 3 Mois`) correspond à `timeframe` (`day` / `week` / `month` / `quarter`) en DB et dans l'API.
  - Une **« ligne catalogue »** (ou **« titre sans données »**, filtrable via `only_missing_data` / comptée par `missing_data_count`) est soit une action ordinaire (`Common Stock`) insérée depuis `finance_exchange_symbols` par `seed_screener_from_exchange_catalogs` (filtrable par `exchange_codes`), soit un ETF (`type = 'ETF'`) référencé bourse par bourse (`PA`, `US`, `XETRA`, etc.) via `seed_etfs_from_exchange_catalog` avec `price IS NULL` et `bars_count = 0` en attendant son chargement.

### 10. File Budgétée des Fondamentaux & Synchro Quotidienne EODHD
- **Définition métier** : Séparation entre la mise à jour quotidienne des **Cours** (cotations, historiques EOD et indicateurs techniques 4 unités via interrupteur `Tous les jours` ou action 1-clic `Charger tout de suite` par source) et le chargement progressif des **Données Fondamentales** (étalement sous budget quotidien et rafraîchissement automatique après publication des résultats).
- **Entrepôt Finance (`finance_warehouse.db`)** :
  - `finance_fundamentals_queue` : File persistante (`symbol`, `priority` de `0` = coup de pouce à `99` = simple consultation, `next_due_at`, `reported_pending`, `typical_report_days`, `stale_retries`).
  - `finance_sync_preferences` : Configuration JSON séparant les cours quotidiens (`watchlists`, `major_indices_constituents`, `index_codes`, `exchanges`, `stock_price_exchanges`, `etf_exchanges`) et les fondamentaux progressifs (`screener_fundamentals`, `fundamentals_watchlists`, `fundamentals_indices`, `full_data_exchanges`, `fundamentals_budget_pct`, `fundamentals_quota_safety_pct`, `fundamentals_priority_order`).
- **Backend** : `finance_sync_sources.py` (`get_unified_exchange_sources`, `execute_single_sync_source`, `run_daily_bulk_and_missing_bars_sync` + route `POST /api/finance/sync-preferences/run-source`), `finance_fundamentals_queue.py`, `finance_fundamentals_scheduler.py`, `finance_exchange_full_sync.py` (`/api/eod-bulk-last-day/{EXCH}` mutualisé), `finance_eodhd_usage.py` (compteur `record_eodhd_call` + quota `/api/user`), `finance_funds.py`.
- **Frontend** : Onglet `5 · Données & Synchro` (`FinanceSyncPanel` en 3 blocs : liste des sources **Cours**, carte **Fondamentaux** `FinanceFundamentalsPlanCard`, pied de page **Calls / Base / Migration** `FinanceSyncFooter`), bouton **« Compléter »** (`boost`) pour les actions dans `FinanceScreenerPanel`.

---

## 3. Tchat, Mémoires, Recherche & Agents

### 11. Espace Thématique (`TopicSpace` / Projet)
- **Définition métier** : Dossier thématique transversal (`learning`, `project`, `interest`, `personal`) regroupant plusieurs conversations autour d'un objectif commun, avec son propre contexte de reprise, ses jalons et ses faits mémorisés.
- **DB Principale (`models.py`)** : Tables `topic_spaces` (`TopicSpace`), `topic_memories` (`TopicMemory`), `topic_events` (`TopicEvent`), `topic_resources` (`TopicResource`) et clé étrangère `conversations.topic_space_id`.
- **Backend** : `/api/topics` (`routers/topics.py`, `topic_agent.py`), événement SSE `done.data.topic_space_update`.
- **Frontend** : `TopicModal` (`components/topic-modal.tsx`), types `TopicSpace`, `TopicMemory`, `TopicEvent`, `TopicResource` (`lib/api.ts`).

### 12. Les 3 Niveaux de Mémoire (`Memory` vs `Conversation.summary` vs `TopicMemory`)
- **Définition métier & Correspondances** :
  1. **Mémoire Personnelle (`Memory`, table `memories`)** : Faits durables propres à l'utilisateur (`user_id`), ajoutés manuellement ou extraits automatiquement (`memory_agent.py` quand `users.auto_memory_enabled == True`), injectés dans toutes les conversations.
  2. **Résumé de Conversation (`Conversation.summary` + `summary_through`, table `conversations`)** : Synthèse glissante des anciens messages d'une conversation unique (`chat_memory.py`), recalculée périodiquement pour tenir dans la fenêtre de contexte sans perdre le fil.
  3. **Mémoire d'Espace Thématique (`TopicMemory`, table `topic_memories`)** : Connaissance ou compétence suivie au sein d'un `TopicSpace` précis, dotée d'un statut de progression (`discussed`, `in_progress`, `needs_review`, `provisional_mastery`, `validated`) et d'un score de confiance.

### 13. Compétence (`Skill`) vs Équipe Multi-Agents (`AgentTeam` / `AgentPersona`) vs `Hermes Agent`
- **Définition métier & Correspondances** :
  1. **Compétence (`Skill`, tables `skills` & `conversation_skills`)** : Prompt système réutilisable (avec son propre réglage optionnel `creativity` / `sampling_params`), activable sur une conversation ou invoqué à la volée dans un message via `@slug` (`extract_mentioned_skills`, `SkillsPanel`).
  2. **Persona & Équipe Multi-Agents (`AgentPersona` / `AgentTeam`, tables `agent_personas` & `agent_teams`)** : Orchestration interne au tchat (`multi_agent.py`, `MultiAgentModal`) faisant collaborer ou débattre plusieurs personas/modèles selon 4 modes (`synthesis`, `debate`, `dialectic`, `contradictory`).
  3. **Hermes Agent (`hermes_agent.py`, `hermes_tools.py`, conteneur `clair-hermes`)** : Agent autonome outillé doté d'un `soul_prompt`, exécutant des missions multi-étapes (via la passerelle `http://clair-hermes:8642` ou la boucle locale autonome, et connecté en retour à l'application via le serveur MCP `/api/hermes/mcp`).

### 14. Recherche Approfondie (`DeepSearch`) vs Mode Apprendre (`Learn`) & Potentiomètre de Créativité (`Creativity`)
- **Définition métier & Correspondances** :
  - **DeepSearch (`DeepSearchReport`, table `deep_search_reports`)** : Investigation web multi-sources avec rapport HTML/PDF archivé (`deep_search.py`, `deep_search_html.py`), exécutée soit via Perplexity Sonar (`DEEP_SEARCH_ENGINE=sonar`), soit via Google Deep Research (`google_deep_research.py`), soit via le pipeline interne vérifié par registre de preuves (`evidence_ledger.py`, `fact_verifier.py`, `claim_semantics.py`). Suivi en direct via l'événement SSE `research_activity` (`ResearchActivityModal`).
  - **Mode Apprendre (`LearnReport`, table `learn_reports`)** : Génération de cours interactifs complets (`learn_mode.py`, `learn_html.py`, `LearnModal`, `StudyModal`) intégrant cartes mémoire (`Flashcard`), QCM (`QuizQuestion`) et textes à trous (`ClozeTestItem`).
  - **Créativité & Paramètres d'échantillonnage (`creativity` & `sampling_params`)** : `creativity` est un curseur normalisé `0.0–1.0` (`SidebarCreativityPotentiometer`, `CreativityControl`) qui calcule dynamiquement (`sampling.py`) les `sampling_params` (`temperature`, `top_p`, `min_p`, `reasoning_effort`, etc.) en filtrant strictement selon les `supported_parameters` du modèle cible.
