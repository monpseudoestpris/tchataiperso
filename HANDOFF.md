# Relais — 2 novembre 2026

## 1. Project Overview
cLAIr : application d'apprentissage et de révision didactique, conversation IA avancée, Studio Image et multimédia, Espaces thématiques avec mémoire continue, Studio cLAIr Pages (générateur de documents web HTML5 autonomes), backend FastAPI/SQLAlchemy/Python, frontend Next.js 16/React/TypeScript.

## 2. Current Objective
Résolution des retours de recherche web aberrants (YouTube, YouTube Music, calculatrices génériques) lors de discussions didactiques ou administratives (ex: retraite CNRACL).

## 3. Completed Work
- **Diagnostic de la cause racine** :
  1. Lors de requêtes reformulées contenant des chiffres personnels ou des pourcentages (`80% 2300 euros net 52 ans`), le moteur Bing dans SearXNG ne trouvait aucun résultat direct et renvoyait sa section de repli HTML (« trending / populaires ») contenant des pages d'accueil génériques (YouTube, YouTube Music, Play Store, calculatrice.fr).
  2. SearXNG n'activait pas SafeSearch (`safe_search: 0` par défaut) et n'avait pas de langue par défaut fixée.
  3. Dans `filter_irrelevant_web_sources`, si aucune source ne correspondait aux termes d'ancrage (`kept == []`), la fonction retombait sur `return sources` au lieu de purger les résultats hors sujet, laissant passer 100 % des liens parasites.
  4. L'absence de filtrage sur les domaines racines et plateformes multimédias empêchait l'élimination des pages d'accueil (`youtube.com/`, `music.youtube.com`, `play.google.com/store/apps`).
  5. Ce faux succès de SearXNG empêchait le déclenchement du repli vers Brave Search API (qui est configuré et fournit des résultats institutionnels impeccables).
- **Correctifs apportés** :
  - `searxng/settings.yml` : désactivation de Bing texte dans SearXNG, activation de `wikipedia`, configuration de `safe_search: 1` et `default_lang: fr-FR`.
  - `backend/app/providers.py` :
    - Ajout de `_is_junk_web_source` filtrant les domaines adultes/spam, les plateformes musicales (`music.youtube.com`, `spotify`, etc.) hors contexte musical, les boutiques d'applications et les pages d'accueil racine sans chemin d'article (`youtube.com/`, `amazon.fr/`).
    - Élimination des sites de calculatrices génériques (`calculatrice.fr`, `okcalc.com`, etc.) pour les requêtes qui ne portent pas expressément sur un calcul mathématique.
    - Refonte de `filter_irrelevant_web_sources` : élimination stricte des sources ne contenant aucun terme d'ancrage thématique, soft-match pour les sources approchantes, et retour `[]` lorsque les sources sont manifestement hors sujet (permettant le repli transparent vers Brave Search API ou la réponse interne du LLM).
    - Optimisation du prompt `rewrite_smart_search_queries` : exclusion explicite des montants exacts et âges de l'utilisateur dans les requêtes de recherche pour privilégier les barèmes, décrets et formules institutionnelles.
  - `backend/tests/test_providers.py` : ajout de tests unitaires dédiés au rejet des plateformes parasites et des sources non ancrées.
- **Vérifications** :
  - `PYTHONPATH=backend pytest backend/tests/test_providers.py backend/tests/test_api.py` : 188 passés (100 %).
  - Recompilation et redémarrage des conteneurs `clair-searxng` et `clair-api` avec succès.
  - Test réel en conteneur sur la requête surcotisation retraite : 5 sources officielles CNRACL / Service Public retournées, 0 lien YouTube/Music/Calculatrice.

## 4. Key Decisions
- **Rendu via l'iframe déjà calculée** : capture le document exactement tel qu'il est rendu à l'écran avec tous les SVGs, polices et styles appliqués, sans reflow supplémentaire.
- **Résolution 2x Retina** : garantit des graphiques SVG et des typographies vectorielles ultra-précis même sur écran 4K ou à l'impression.

## 5. Modified Files
- `searxng/settings.yml` : safe_search à 1, default_lang à fr-FR, désactivation de Bing texte, ajout de Wikipedia.
- `backend/app/providers.py` : filtrage des domaines parasites/root portals/musique hors contexte, élimination des calculatrices pour les requêtes non mathématiques, correction du fallback dans `filter_irrelevant_web_sources` et affinage de la reformulation de requêtes.
- `backend/tests/test_providers.py` : tests de non-régression pour le filtrage des parasites et sources non ancrées.
- `HANDOFF.md` : mise à jour du relais.

## 6. Verification
- `PYTHONPATH=backend pytest backend/tests/test_providers.py backend/tests/test_api.py` : 188 passés (100 %).
- `docker compose ps` : conteneurs sains (`healthy`).
- Test réel de recherche en conteneur : résultats pertinents institutionnels CNRACL / Service Public, 0 déchet.

## 7. Known Issues and Risks
- Aucun.

## 8. Next Action
- Poursuivre les échanges dans le chat et vérifier la pertinence des sources web citées.

## Ajout — Blogs multi-catégories & Images web SearXNG (News, Faits, Images, Astuces, Stats, Citations, Concepts)
- **Objectif** : Permettre d'avoir plusieurs catégories de contenu dans les blogs (Actualités, Faits de culture générale « Le saviez-vous ? », Galerie & Visuels documentés, Astuces pratiques, Chiffres clés & Records, Citations marquantes, Vulgarisation de concepts) et composer un magazine mixte combinant plusieurs types, avec des images réelles issues du web via SearXNG (aucune génération IA).
- **Articles Visuels / Images Web SearXNG & Lightbox Plein Écran** :
  - Les articles de type image mettent en valeur le visuel en grand format avec ratio élégant (190px en carte), badge de rubrique et superposition au survol.
  - **Visionneuse Lightbox Plein Écran** : clic sur n'importe quel article visuel pour ouvrir l'image en pleine résolution, avec titre, explication, lien vers la source et bouton de téléchargement direct (`Download`).
  - **Recherche & Sélecteur d'images web SearXNG** : modal interactive permettant de rechercher en direct des images web réelles via SearXNG (`GET /api/blogs/search-images?q=...`), de prévisualiser les vignettes et d'associer en 1 clic une image à n'importe quel article (`PATCH /api/blogs/{blog_id}/posts/{post_id}`).
  - **Garantie backend SearXNG** (`backend/app/blog.py`) : toute carte de type `images` ou article illustré charge des images web directes (`img_src` / `thumbnail_src`) issues de l'instance locale SearXNG (`search_web_images`).
- **Backend** :
  - `backend/app/models.py` : colonne `categories: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["news"])` sur le modèle `Blog`.
  - `backend/migrations/versions/0017_add_blog_categories.py` : migration Alembic.
  - `backend/app/main.py` : auto-migration au démarrage dans `lifespan` garantissant la présence de `categories`.
  - `backend/app/cli.py` : enregistrement de la révision `0017_add_blog_categories`.
  - `backend/app/schemas.py` : validation de `categories` pour `CreateBlog` et `UpdateBlog`.
  - `backend/app/serializers.py` : inclusion de `categories` dans `blog_json`.
  - `backend/app/routers/blogs.py` : prise en compte de `categories` à la création, à la mise à jour et lors de l'actualisation (`refresh`) ; ajout de `GET /api/blogs/search-images` et `PATCH /api/blogs/{blog_id}/posts/{post_id}`.
  - `backend/app/blog.py` : refonte de `generate_blog_edition` et `ensure_minimum_cards` supportant les 7 catégories, recherche d'images web réelles via `search_web_images` SearXNG pour la galerie visuelle et prompt journalistique/encyclopédique adapté aux rubriques choisies.
  - Tests unitaires `backend/tests/test_blogs.py` : 8 tests validés avec succès (catégories simples, mix, CRUD et refresh).
- **Frontend** :
  - `frontend/lib/api.ts` : types `BlogCard` (avec `category` et `image_url`), `Blog` (`categories`), `createBlog`, `updateBlog`, `searchBlogImages` et `updateBlogPostCards`.
  - `frontend/components/blog-modal.tsx` :
    - Formulaire de création avec sélection par cases à cocher des rubriques (`BLOG_CATEGORIES`), raccourcis en 1 clic (*Tout cocher / Mixte*, *News*, *Faits*, *Images*).
    - Suggestions adaptées configurant le sujet et les rubriques recommandées.
    - En-tête du lecteur affichant les badges de rubriques actives et bouton d'édition inline des rubriques.
    - Barre d'onglets de filtrage par catégorie dans le visualiseur (*Tout*, *Actualités*, *Faits*, *Images*, etc.).
    - Rendu enrichi des cartes avec médias visuels (`image_url`), badges de rubrique avec emoji et source.
    - Modale visionneuse Lightbox plein écran avec téléchargement et source.
    - Modale de recherche et sélecteur d'images web SearXNG en direct avec affichage en grille et association immédiate.
    - Rendu Markdown mis à jour avec le type de carte et l'image éventuelle.
  - `frontend/app/globals.css` : styles complets pour la grille de cases à cocher, les puces de filtres, l'éditeur inline, le rendu des images des cartes, la modale Lightbox plein écran et la modale de recherche d'images SearXNG.
- **Vérifications** :
  - `PYTHONPATH=backend pytest backend/tests/test_blogs.py` : 8 passés (100 %).
  - `npm run typecheck --prefix frontend` : code 0.
  - `npm run build --prefix frontend` : code 0 (Next.js Turbopack).
  - Conteneurs Docker `clair-api` et `clair-web` reconstruits et sains (`healthy`).

## Addendum — Blogs auto (style + mobile)
- `frontend/components/blog-modal.tsx` : sélecteur de style visuel (mêmes `VISUAL_STYLES_LIST` que les pages web), mémorisé par blog dans localStorage (`blog-vstyle:<id>`), appliqué via `data-vstyle`.
- `frontend/app/globals.css` (fin de fichier) : variables par style + correctifs mobile (grille de cartes, en-tête, popover thème, sidebar).
- Vérifié : `npm run typecheck` (code 0). Non exécuté : build, test visuel sur téléphone réel.
- Limite : le style n'est pas persisté côté serveur (pas de migration).


## Ajout — Durée d'affichage Finance
- Sélecteur 1 J / 1 Sem. / 1 Mois / 3 Mois / 6 Mois / 1 An / 2 Ans / 5 Ans / Max dans `finance-modal.tsx`; paramètre `range` sur `GET /api/finance/details`; mapping dans `backend/app/finance_ranges.py` (Yahoo chart : 1J=5m, 1Sem=30m, 5 ans=hebdo, Max=mensuel). Plage par défaut 1m = comportement historique (EODHD).
- Vérifié : `npm run typecheck --prefix frontend` OK ; `pytest tests/test_finance.py` 32 OK. Non exécuté : test manuel UI/Yahoo réel, pas de test dédié aux nouvelles plages, conteneurs non reconstruits.

## Ajout — États financiers & analyse technique
- Backend : `backend/app/finance_statements.py` + `GET /api/finance/statements?symbol=` (Yahoo fundamentals-timeseries, UA "Mozilla/5.0" requis sinon 429) : compte de résultat, bilan, flux de trésorerie (annuel/trimestriel) + 14 ratios dérivés. Tests : `backend/tests/test_finance_statements.py`.
- Frontend : `finance-statements.tsx` (onglet Bilan & Trésorerie), `finance-tv-chart.tsx` (lightweight-charts, nouvelle dépendance prod) + `lib/indicators.ts` (SMA, EMA, Bollinger, RSI, MACD, volume). Bouton « Analyse technique » dans la modale.
- Vérifié : pytest test_finance + test_finance_statements (36 OK), typecheck et build frontend OK, appel Yahoo réel sur AI.PA OK. Non vérifié : rendu visuel navigateur ; trimestriel Yahoo souvent partiel.

- Indicateurs étendus (`lib/indicators.ts`, code maison sans lib de calcul ; lightweight-charts ne fait que le dessin) : SMA 20/50/200, EMA 20/50, Bollinger, VWAP, SAR, Volume + oscillateurs RSI, MACD, Stochastique, Williams %R, CCI, ROC, ATR, ADX/DI, OBV. Vérifié : typecheck OK + test numérique ad hoc (valeurs plausibles, pas de NaN). Pas de test unitaire permanent ni de rendu navigateur.

- Indicateurs : `lib/indicators.ts` est désormais un adaptateur de la dépendance `technicalindicators` (VWAP reste maison). Valeurs identiques aux anciennes implémentations maison (RSI, MACD, ADX, CCI, SAR, ROC). Build OK, conteneur clair-web reconstruit (`up -d -V`). Stochastique = version rapide (%K brut, %D=SMA3). `npm audit` : 4 low liées à katex (préexistant).

## Correctif UI — Bannière Finance (Nom, Tickers & Consensus)
- `frontend/components/finance-modal.tsx` :
  1. Ajout dans `finance-hero-left` de l'identité complète de l'action : nom d'entreprise (`data.long_name || data.short_name`), tickers (`data.symbol`, `data.yahoo_symbol`), place boursière (`data.exchange`) et code ISIN.
  2. Refonte de `finance-analyst-badge-hero` : carte structurée et aérée pour éviter le texte agglutiné ("Consensus AnalystesNONEObj. : N/A CAD"). Fonction `formatAnalystRecommendation` traduisant et colorant la recommandation (Achat, Conserver, Vente, ou "Non disponible" au lieu de "NONE"), masquage propre de l'objectif quand il vaut "N/A" ou est absent.
- `frontend/app/globals.css` : styles complets pour `.finance-hero-identity`, `.finance-analyst-badge-hero`, pilules de recommandation thématiques et puces de potentiel.
- Vérifié : `npm run typecheck --prefix frontend` (code 0) et tests pytest (36 passés).

## Correctif — Effet de bord dans le reducer de SkillsPanel
- **Problème** : `onSkillsChange?.(next)` (qui appelle le `setSkills` du composant parent `ChatApp`) était exécuté directement à l'intérieur du callback de mise à jour d'état `setSkills(current => ...)` dans `frontend/components/skills-panel.tsx`. En React 19 / Next.js, déclencher un `setState` externe au sein d'une fonction de mise à jour d'état pure est strictement interdit et provoque une erreur de rendu en cascade.
- **Résolution** : calcul de `next` avant d'appeler `setSkills(next)` et invocation propre de `onSkillsChange?.(next)` en dehors du cycle d'évaluation du state updater (pour `saveSkill` et `deleteSkill`).
- **Vérification** : `npm run typecheck --prefix frontend` (code 0) et `npm run build --prefix frontend` (code 0).

## Correctif — Recherche Web & Images SearXNG (`TypeError` & `ValidationException`)
- **Problème 1 (`merge_web_sources`)** : `merge_web_sources()` dans `backend/app/providers.py` ne déclarait que le paramètre `max_total`, mais était appelé avec l'argument nommé `limit=8` dans `backend/app/routers/messages.py` (lignes 668 et 692) et `limit=limit` dans `providers.py` (ligne 4432), provoquant un `TypeError: merge_web_sources() got an unexpected keyword argument 'limit'` qui interrompait le stream de messages lors de requêtes web multi-recherches.
- **Résolution 1** : ajout de l'argument optionnel `limit: int | None = None` dans la signature de [merge_web_sources](file:///home/chabert/Projets/tchataiperso/backend/app/providers.py#L3927) avec report automatique sur `max_total`.
- **Problème 2 (`ValidationException: Invalid value: "['images']"`)** : le fichier `searxng/settings.yml` contenait une clause `use_default_settings.engines.keep_only` qui ne listait aucun moteur d'images, privant SearXNG de la catégorie `images` et provoquant une exception de validation ainsi que 0 image retournée lors des requêtes d'illustrations web. Une ligne orpheline `disabled: true` en fin de fichier a également été nettoyée.
- **Résolution 2** : activation des moteurs d'images (`bing images`, `duckduckgo images`, `google images`, `qwant images`, `unsplash`) dans `keep_only` et la section `engines:` de `searxng/settings.yml`.
- **Vérification** : 
  - Tests unitaires `pytest backend/tests/test_providers.py` : 128 passés (dont test de limitation avec `limit=8`).
  - Test d'intégration SearXNG : recherche d'images opérationnelle via `search_web_images` retournant des images complètes (source, résolution, thumbnail) sans exception.
  - Conteneurs `clair-searxng` et `clair-api` redémarrés et sains.

## Ajout — Catégorie Vidéos dans les Blogs (Lecteur intégré, Lien externe & Recherche SearXNG)
- **Objectif** : Ajouter la rubrique vidéo (« Vidéos documentaires » / 🎬) dans le système de blogs multi-catégories avec affichage de la miniature, bouton de lecture, lecteur iframe intégré responsive dans l'encart, lien direct externe vers la plateforme source (YouTube / web), modale de visionnage plein écran et recherche / remplacement de vidéos web en direct via SearXNG.
- **Backend** :
  - `backend/app/schemas.py` : `"videos"` intégré dans `VALID_BLOG_CATEGORIES`.
  - `backend/app/blog.py` :
    - Configuration de rubrique `"videos"` dans `BLOG_CATEGORIES_CONFIG` (label: « Vidéos documentaires », emoji: « 🎬 », tag: « 🎬 Vidéo »).
    - `search_web_videos(settings, query, limit=6)` : interrogation du moteur `youtube` de SearXNG, extraction de l'identifiant YouTube avec `extract_youtube_video_id` et normalisation des URLs de lecture (`watch`), d'embed sécurisé (`youtube-nocookie.com/embed/...`) et des miniatures HD (`i.ytimg.com/vi/.../hqdefault.jpg`).
    - `ensure_minimum_cards` : support de l'injection d'encarts de vidéos complémentaires documentés.
    - `_cards_to_markdown` : ajout de la ligne Markdown cliquable `[🎬 Voir la vidéo en ligne](...)`.
  - `backend/app/routers/blogs.py` :
    - Route `GET /api/blogs/search-videos?q=...` positionnée avant les routes avec paramètre d'URL dynamique `{blog_id}` (évite l'interception en 404).
    - Repositionnement identique pour `GET /api/blogs/search-images`.
  - `searxng/settings.yml` : activation du moteur `youtube` (`engine: youtube_noapi`) sous la catégorie vidéos.
- **Frontend** :
  - `frontend/lib/api.ts` :
    - Mise à jour du type `BlogCard` avec `category?: ... | "videos"`, `video_url?: string`, `video_embed_url?: string`.
    - Type `SearxngVideoResult` et méthode client `searchBlogVideos(query: string)`.
  - `frontend/components/blog-modal.tsx` :
    - Définition de `"videos"` dans `BLOG_CATEGORIES` et suggestion en 1 clic « Documentaires & Vidéos ».
    - Ajout du raccourci rapide `🎬 Vidéos` dans le formulaire de création de blog.
    - Rendu des encarts de type vidéo :
      - Miniature cliquable avec superposition sombre translucide, bouton rond Play rouge (`#ef4444`) et label « Lire la vidéo ».
      - Lecteur intégré inline dans l'encart (iframe 16:9 responsive) activable/masquable en un clic avec bouton de fermeture.
      - Bouton d'action « Voir la vidéo » avec lien direct externe vers la source.
      - Bouton d'ouverture du lecteur vidéo grand format (modale lightbox).
      - Bouton de recherche et remplacement de la vidéo via SearXNG (`handleOpenSearxngVideoSearch`).
    - Modale visionneuse plein écran pour la vidéo (`videoModalCard`).
    - Modale de recherche et sélection de vidéos SearXNG en direct (`searxngVideoModal`) avec grille de résultats, vignettes et association immédiate à l'encart.
  - `frontend/app/globals.css` : styles pour `.blog-card.is-video-card`, `.blog-card-video-thumb-wrap`, `.blog-card-play-overlay`, `.blog-card-play-btn`, `.blog-card-video-player-wrap`, `.blog-card-video-iframe`, `.blog-card-video-player-close`, `.blog-video-lightbox-content`, `.blog-lightbox-video-wrap` et les badges de résultat SearXNG.
- **Vérifications** :
  - `pytest backend/tests/test_blogs.py backend/tests/test_api.py backend/tests/test_providers.py` : 199 passés (100 %).
  - `npm run typecheck --prefix frontend` : code 0.
  - `npm run build --prefix frontend` : code 0 (Next.js Turbopack).
  - Conteneurs `clair-searxng`, `clair-db`, `clair-api` et `clair-web` reconstruits et opérationnels (`healthy`).
