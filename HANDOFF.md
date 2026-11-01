# Relais — 1 novembre 2026

## 1. Project Overview
cLAIr : application d'apprentissage et de révision didactique, conversation IA avancée, Studio Image et multimédia, Espaces thématiques avec mémoire continue, Studio cLAIr Pages (générateur de documents web HTML5 autonomes), backend FastAPI/SQLAlchemy/Python, frontend Next.js 16/React/TypeScript.

## 2. Current Objective
Implémentation complète et personnalisation avancée de **cLAIr Pages** (moteur de génération de pages web HTML-first autonomes) :
- **Architecture UX épurée du premier niveau (5-6 réglages clés)** :
  1. **Type de page** : Détermine l'organisation du contenu (Auto intelligent, Fiche de révision & mémos, Guide didactique, Article éditorial, Tableau de bord métriques, Rapport formel).
  2. **Public cible** : Adapte vocabulaire, exemples et complexité (Grand public, Débutant & Scolaire, Étudiant & Académique, Professionnel & Expert).
  3. **Liberté créative** : Paramètre distinctif modulant consignes graphiques et audace CSS/SVG :
     * 🛡️ *Faible* : Sections classiques, sobre, disposition prévisible.
     * ⚖️ *Moyenne* : Compositions équilibrées, schémas harmonieux, couleurs travaillées.
     * 🚀 *Élevée* : Formes organiques, compositions asymétriques, SVG immersifs, animations douces.
  4. **Orientation** : 📱 *Portrait* (lecture verticale fluide, 960px) vs 🖥️ *Paysage* (écran large, colonnes côte à côte, 1300px).
  5. **Niveau de détail (Densité)** : Contrôle le volume et la concision de l'information (1 à 10).
  6. **Style visuel** : Sélecteur avec option "Auto-adapté au sujet" + catalogue des 11 styles esthétiques.
  7. **Interactivité** : Auto (JS léger lorsque pertinent), Forte (simulateurs, curseurs, quiz), Statique pure (zéro JS).
  8. **Illustrations SVG** : Avec ou Sans schémas vectoriels.
- **Détection intelligente des composants par l'IA** :
  * Matrice de détection contextuelle intégrée dans le prompt système : frise chronologique pour l'histoire, cartes comparatives/tableaux pour les confrontations de notions, schémas SVG explicatifs pour la science, étapes numérotées pour les tutoriels, graphiques chiffrés pour les statistiques, encadrés et quiz pour les révisions, citations et analogies pour la vulgarisation.
- **Préconfigurations UX (Presets en 1 clic)** :
  * ⚡ *Mode Automatique* (recommandé par défaut : cLAIr déduit tout).
  * 🎯 *Fiche de Révision* (scolaire, mémos, quiz, style carnet).
  * 📰 *Article Éditorial* (presse, mise en page magazine, sobre).
  * 🔬 *Exploration Interactive* (forte créativité, simulateurs, SVG).
  * 📊 *Tableau de Bord* (orientation paysage, indicateurs chiffrés).
- **Modale dédiée de sélection des modèles (`ModelPickerModal`)** :
  * Interface soignée présentant chaque modèle avec provider, forces spécifiques, badges (« Recommandé pour cLAIr Pages », « Rapide », « Raisonnement ») et recherche.
- **Possibilité de changer les réglages après génération** :
  * Bouton « ⚙️ Réglages » dans le visualiseur pour recharger les paramètres de la page et régénérer une nouvelle version sans repartir du chat initial.
- **Correction du défilement et visibilité immédiate du champ de saisie** :
  * Correction du bug CSS `justify-content: center` qui poussait le haut du formulaire (titre, préconfigurations, champ de saisie du sujet) en coordonnées négatives non atteignables par la barre de défilement. Remplacé par `justify-content: flex-start; margin: 0 auto;` garantissant une visibilité et une saisie immédiates dès l'ouverture.
  * Puces de suggestions d'inspiration condensées sur une seule ligne défilable horizontalement sous la zone de texte.
- Portabilité totale : document unique HTML5 + CSS3 + SVG inline + JavaScript vanilla sans CDN ni compilation, 100 % autonome et hors-ligne.

## 3. Completed Work
- **Modèle de données & Versionnage (`backend/app/models.py`, `backend/app/schemas.py`, `backend/app/serializers.py`)** :
  - `WebPage` : identifiant, `user_id`, `title`, `slug`, `public_token` (token aléatoire URL-safe), `is_published`, timestamps.
  - `WebPageVersion` : `id`, `page_id`, `version_number`, `prompt_used`, `html_content`, timestamps.
  - Schémas Pydantic (`CreateWebPage`, `RefineWebPage`, `UpdateWebPage`) et sérialiseurs JSON.
- **Moteur de génération HTML autonome (`backend/app/page_generator.py`)** :
  - Prompts système spécialisés avec contraintes strictes : interdiction formelle de ressources CDN ou distantes, typographie système moderne, CSS variables, schémas vectoriels SVG natifs, scripts vanilla légers (quiz, onglets, accordéons, switchers).
  - Générateur de démonstration didactique hors-ligne (fallback garanti pour tests et mode démo).
  - Extraction robuste du HTML et du titre, gestion de l'affinage itératif.
- **Routeur FastAPI (`backend/app/routers/pages.py`, `backend/app/main.py`)** :
  - `GET /api/pages` : liste des pages de l'utilisateur.
  - `POST /api/pages` : création de page depuis un prompt libre ou depuis l'historique d'une conversation cLAIr existante.
  - `GET /api/pages/{id}` : détail de la page avec toutes ses versions.
  - `PATCH /api/pages/{id}` : renommage et bascule de publication publique (`is_published`).
  - `DELETE /api/pages/{id}` : suppression d'une page et de ses versions en cascade.
  - `POST /api/pages/{id}/refine` : modification itérative créant la version `v+1`.
  - `POST /api/pages/{id}/versions/{version_id}/restore` : restauration d'une version passée.
  - `GET /p/{token}` & `GET /api/pages/public/{token}` : service public de la page HTML brute avec en-têtes CSP stricts (`default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: blob:;`).
- **Client API & Configuration Frontend (`frontend/lib/api.ts`, `frontend/next.config.ts`)** :
  - Types TypeScript (`WebPage`, `WebPageVersion`) et méthodes complètes CRUD/refine/restore.
  - Règle de réécriture Next.js pour acheminer les requêtes `/p/:path*` directement vers le backend FastAPI.
- **Interface Utilisateur & Modal cLAIr Pages (`frontend/components/web-page-modal.tsx`, `frontend/components/web-page-modal.module.css`)** :
  - Optimisation de l'agencement vertical : réduction drastique de la hauteur de la barre inférieure d'itération (~60px) pour allouer plus de 85 % de la hauteur à l'iframe d'aperçu.
  - Défilement horizontal compact (`suggestionsScroll`) pour les puces d'inspiration, empêchant tout empilement vertical.
  - Bouton de bascule de la barre latérale gauche (masquer/afficher la liste) pour étendre l'aperçu à 100 % de la largeur.
  - Bouton plein écran (agrandir/réduire) pour maximiser l'espace d'affichage.
  - Sélecteurs compacts pour les versions et le modèle IA.
  - Tiroir latéral avec liste des pages et bouton création.
  - Écran de création avec options (prompt direct ou injection du tchat courant, suggestions).
  - Visualiseur responsive avec bascule Desktop (PC) / Mobile (smartphone 390px) et bascule Aperçu / Code source HTML.
  - Iframe sandboxée isolée pour exécution sécurisée des composants interactifs (quiz, onglets).
  - Téléchargement instantané du fichier `.html` autonome via Blob.
  - Bouton « Publier » et partage du lien public copiable en un clic.
  - Barre d'itération conversationnelle avec puces d'inspiration rapides pour faire évoluer la page en version supérieure.
  - Sélecteur de version pour naviguer ou restaurer une version précédente.
- **Intégration Globale dans l'application (`frontend/components/tools-modal.tsx`, `frontend/components/chat-app.tsx`)** :
  - Carte dédiée **cLAIr Pages** dans la boîte à outils générale (`ToolsModal`).
  - Bouton d'accès rapide dans la barre latérale gauche (`sidebar-quick-tools`).
  - Bouton d'action directe dans l'en-tête de la discussion courante : **« Page Web »** pour synthétiser le tchat en un clic.
- **Tests & Validation (`backend/tests/test_pages.py`)** :
  - Tests unitaires des helpers (slugify, extract_html, extract_title, fallback).
  - Tests d'intégration du cycle complet (création, consultation, publication, affinage v2, restauration v1, suppression).
  - Test de création de page web alimentée par une conversation cLAIr.
  - 406/406 tests pytest réussis.
  - Compilation Next.js (Turbopack) réussie avec code 0.
  - Conteneur Docker `clair-api` reconstruit et redémarré avec succès (`healthy`).

## 4. Key Decisions
- **Moteur HTML-first sans React ni compilation pour l'export** : le document produit est un fichier HTML5 unique avec CSS inline, JS vanilla et SVG inline, sans aucune dépendance externe, assurant une lecture hors-ligne éternelle.
- **Sécurité de prévisualisation** : `iframe` avec `sandbox="allow-scripts allow-forms allow-modals"` (sans `allow-same-origin`) interdisant tout accès aux cookies de session ou au DOM parent.
- **Publication légère** : FastAPI sert directement le HTML statique sous le préfixe `/p/{public_token}` avec des en-têtes `Content-Security-Policy` stricts.

## 5. Modified Files
- `backend/app/models.py` : ajout des entités `WebPage` et `WebPageVersion`.
- `backend/app/page_generator.py` : nouveau module de génération et d'affinage de pages web HTML/CSS/SVG/JS autonomes.
- `backend/app/schemas.py` : ajout de `CreateWebPage`, `RefineWebPage`, `UpdateWebPage`.
- `backend/app/serializers.py` : ajout de `web_page_json` et `web_page_version_json`.
- `backend/app/routers/pages.py` : nouveau routeur API pour la gestion, l'itération et la publication de pages.
- `backend/app/main.py` : enregistrement du routeur `pages`.
- `backend/tests/test_pages.py` : suite de tests unitaires et d'intégration pour cLAIr Pages.
- `frontend/lib/api.ts` : types et appels API pour les pages web.
- `frontend/next.config.ts` : réécriture de `/p/:path*` vers le backend.
- `frontend/components/web-page-modal.module.css` : styles du studio cLAIr Pages.
- `frontend/components/web-page-modal.tsx` : composant modal complet cLAIr Pages.
- `frontend/components/tools-modal.tsx` : ajout de la carte cLAIr Pages dans la boîte à outils.
- `frontend/components/chat-app.tsx` : intégration du déclencheur, du bouton d'en-tête de chat et de la modal.
- `HANDOFF.md` : mise à jour de la documentation de relais.

## 6. Verification
- `pytest tests/test_pages.py` : 3/3 passés.
- `pytest backend/tests/` : 406/406 passés à 100 %.
- `npm run build --prefix frontend` : code 0 (compilation Turbopack réussie).
- `docker compose build clair-api && docker compose up -d clair-api` : conteneur reconstruit et opérationnel (`healthy`).
- `curl -s http://127.0.0.1:8001/api/health` : `HTTP 200 {"status":"ok"}`.

## 7. Known Issues and Risks
- Aucun problème détecté.

## 8. Next Action
- Tester en conditions réelles la génération d'une page web à partir d'un tchat didactique et son affinage conversationnel via l'interface.
