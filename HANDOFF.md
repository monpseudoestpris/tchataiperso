# Relais — 13 novembre 2026

## 1. Project Overview
clAIr : tchat IA francophone, apprentissage, recherche, médias et génération de pages HTML. Frontend Next.js 16.4 / React 19 / TypeScript ; backend FastAPI / SQLAlchemy / PostgreSQL.

## 2. Current Objective
Garantir que la rubrique **Mes blogs** (`backend/app/blog.py`) n'exploite que des **articles complets** (et non des pages d'accueil / rubriques / landing pages remplies de titres ou de descriptions génériques) afin de produire de véritables synthèses factuelles.

## 3. Completed Work
- **Résumé d'en-tête dense en paragraphe substantiel (`backend/app/blog.py`)** :
  - Consigne LLM renforcée pour le champ `summary` : exigence stricte de faits concrets, chiffres, pourcentages, décisions, montants et noms précis d'acteurs/institutions, avec interdiction formelle des généralités vagues (« une série d'évolutions significatives », « les acteurs accélèrent », etc.).
- **Grandes tendances clés en en-tête des blogs (`backend/app/blog.py`, `backend/app/serializers.py`, `frontend/components/blog-modal.tsx`, `frontend/lib/api.ts`, `frontend/app/globals.css`)** :
  - Génération dans le prompt LLM de 3 grandes tendances/dynamiques de fond (`trends`) synthétisant les mouvements transversaux observés dans les articles.
  - Stockage dans le JSON de l'édition et sérialisation via `parse_trends_from_content` dans `blog_post_json`.
  - Affichage direct dans le bandeau d'en-tête de l'édition (`blog-lead-trends`) avec badge `TrendingUp`, numérotation stylisée `#1`, `#2`, `#3` et lisibilité claire sur fond contrasté.
- **Filtrage d'URLs landing / flux vs articles (`backend/app/blog.py`)** :
  - `is_landing_or_index_url` et `looks_like_article_url` rejettent les pages d'accueil, rubriques génériques, tags/catégories, recherches/pagination, ainsi que les pages de flux (ex. `/actualites/news-du-jour`, `fil-info`, `en-direct`, slugs courts/génériques sans date ni identifiant numérique `>= 4` chiffres via `_GENERIC_SLUG_WORDS` et `_FEED_PATH_PATTERNS`), tout en acceptant les URLs d'articles complets (`.html` avec ID, date `/20xx/`, slug spécifique long).
  - `_search_single_query` interroge d'abord `categories="news"` avant de replier sur `"news,general"`.
  - `_prioritize_article_sources` / `search_blog_news` placent les URLs d'articles en tête et marquent les éventuelles landing pages conservées en fin de liste (`_is_landing_candidate`) uniquement pour en extraire les liens d'articles.
- **Validation stricte et extraction d'article complet (`backend/app/blog.py`)** :
  - `_extract_complete_article` refuse immédiatement toute URL de landing/flux et tout titre de flux (`_FEED_TITLE_RE`), cible `<article>`, puis `<main>`, puis `<body>`, rejette les listes multi-brèves (`>= 3` `<article>` courts, ou conteneur `<main>`/`<body>` contenant trop de `<h2>`/`<h3>` ou `> 35 %` de liens via `_looks_like_feed_container`), et n'extrait que les paragraphes `<p>` substantiels (`>= 60` caractères avec ponctuation de phrase, densité de liens `<= 55 %`).
  - `_extract_article_links_from_html` récupère sur une landing page les liens d'articles du même domaine.
  - `_enrich_sources_with_content` utilise un `User-Agent` navigateur standard, suit jusqu'à 4 liens d'articles sur chaque page de landing/flux, ne conserve que les sources validées comme articles complets (avec repli hors-ligne pour les tests mockés), et `generate_blog_edition` filtre/remplace toute URL de landing restante dans les `cards` générées par le LLM.
  - `ensure_minimum_cards` ignore les URLs de landing et utilise `#` au lieu de `https://news.ycombinator.com` comme URL de secours.
- **Tests ajoutés (`backend/tests/test_blogs.py`)** :
  - `test_landing_vs_article_url_detection` (incluant `boursier.com/actualites/news-du-jour` et articles `.html` / datés), `test_extract_complete_article_rejects_landing_page_and_accepts_full_article` (incluant un flux multi-brèves de 6 titres `<h2>` + `<p>`), `test_enrich_sources_follows_article_links_from_landing_page`, et vérification de `parse_trends_from_content`.
- **Travail précédent conservé dans l'arbre de travail** : système hybride de créativité et potentiomètre latéral (`backend/app/sampling.py`, `backend/app/schemas.py`, `backend/tests/test_api.py`, `frontend/components/creativity-control.tsx`, `frontend/components/sidebar-creativity-potentiometer.tsx`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`).

## 4. Key Decisions
- **Rejet des `<h2>`/`<h3>`/`<li>` lors de l'extraction de texte d'article** : sur les pages de rubriques, ces balises contiennent les listes de titres d'autres articles et polluaient la synthèse ; seuls les `<p>` substantiels à faible densité de liens sont désormais retenus.
- **Suivi automatique des liens sur landing page** : lorsqu'un résultat SearXNG pointe malgré tout vers une rubrique, `_enrich_sources_with_content` extrait jusqu'à 2 URLs d'articles du même domaine et ne garde que les articles complets extraits.

## 5. Modified Files
- `backend/app/blog.py` : détection d'URLs landing/article, recherche SearXNG `news` prioritaire, extraction stricte `_extract_complete_article`, suivi de liens `_extract_article_links_from_html`, filtrage dans `_enrich_sources_with_content` et `ensure_minimum_cards`.
- `backend/tests/test_blogs.py` : ajout de 3 tests unitaires pour le filtrage landing/article et l'extraction complète.
- `HANDOFF.md` : mise à jour du relais.

## 6. Verification
- `python3 -m py_compile backend/app/blog.py backend/tests/test_blogs.py` : **OK (code 0)**.
- `git diff --check backend/app/blog.py backend/tests/test_blogs.py` : **OK (code 0)**.
- Script Python autonome validant `is_landing_or_index_url`, `looks_like_article_url`, le rejet de `https://www.boursier.com/actualites/news-du-jour` et d'un flux HTML à 6 brèves dans `<main>`, l'acceptation d'articles `.html` / datés, et le suivi automatique vers l'article complet via `_enrich_sources_with_content` (avec `httpx.MockTransport` et stubs locaux pour `app.config`/`app.providers`/`app.youtube`) : **OK (`BOURSIER_FEED_FILTER_VERIFICATION_OK`)**.
- `pytest` (`backend/tests/test_blogs.py`) : non exécuté sur l'hôte (Python 3.10 système sans `exceptiongroup` pour le venv 3.12).

## 7. Known Issues and Risks
- `pytest` complet à exécuter dans l'environnement Python 3.12 (ou conteneur Docker backend) pour valider la suite complète `backend/tests/test_blogs.py`.
- Les éditions de blogs déjà enregistrées en base ne sont pas régénérées rétroactivement ; utiliser **Actualiser** dans *Mes blogs*.

## 8. Next Action
Exécuter `pytest backend/tests/test_blogs.py` dans l'environnement Docker/Python 3.12 du backend, puis cliquer sur **Actualiser** dans *Mes blogs* pour tester sur des sujets réels.
