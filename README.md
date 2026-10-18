# clAIr — tchat IA personnel

Une application de tchat en français avec **Next.js / React / Tailwind**, **FastAPI** et **PostgreSQL**. Conversation en streaming, historique persistant, choix du modèle, mémoires personnelles, résumé de conversation, documents joints, recherche web et génération d'images Ideogram.

La première exécution utilise un **mode démo explicitement signalé**. Il produit des réponses locales déterministes pour vérifier l'interface et la persistance ; il ne contacte aucune IA. Les fournisseurs réels se configurent uniquement dans le backend.

## Démarrer avec Docker

Prérequis : Docker Engine avec Compose v2 et Python 3 pour le petit script d'installation.

```bash
./scripts/install.sh
```

Le script crée `.env` s'il n'existe pas, avec un mot de passe PostgreSQL aléatoire, démarre la base et prépare le schéma. Il vous demande l'identifiant du premier administrateur et son mot de passe (saisie masquée); vous choisissez aussi explicitement le propriétaire des anciennes données s'il y en a. Il démarre ensuite les services et exécute un smoke test authentifié. Le mot de passe n'est jamais écrit dans `.env`, qui est conservé s'il existe. Les ports sont liés à l'interface locale : frontend **3000**, backend **8000** ; PostgreSQL reste sur le réseau Docker interne.

```bash
./scripts/compose.sh up --build -d --wait  # démarrer / reconstruire
./scripts/compose.sh logs -f backend     # diagnostiquer le backend
./scripts/compose.sh stop                # arrêter sans supprimer les données
python3 scripts/smoke.py            # vérifier le parcours local sans appel payant
```

Les volumes `postgres_data` et `uploads_data` conservent les données après un redémarrage. `docker compose down -v` les **efface**. Une sauvegarde doit couvrir la base et les fichiers ; les volumes seuls ne constituent pas une sauvegarde.

### Développement avec Docker

Après l'installation initiale, lancez les trois services avec rechargement automatique :

```bash
./scripts/compose.sh dev
```

Le site est accessible sur http://localhost:3000. Les modifications dans `backend/app` relancent FastAPI ; celles du frontend sont prises en compte par Next.js sans reconstruire l'image. `Ctrl+C` arrête les services sans supprimer les données. Après une modification des dépendances ou du `.env`, relancez la commande. Ce mode utilise les mêmes données PostgreSQL et fichiers joints que le lancement Docker normal.

Les routes de données exigent une session. L'inscription est fermée : un administrateur connecté crée une invitation dans le panneau Utilisateurs, puis transmet le lien à usage unique. Les conversations, mémoires et pièces jointes sont cloisonnées par compte dans la base partagée. Derrière HTTPS, configurez `SESSION_COOKIE_SECURE=true` avant de démarrer le backend; ne publiez pas le backend directement.

## Brancher vos API

Modifiez le fichier **`.env` ignoré par Git**, puis recréez le backend :

```dotenv
DEMO_MODE=false
LLM_API_KEY=...
BRAVE_API_KEY=...
MISTRAL_API_KEY=...
IDEOGRAM_API_KEY=...
```

```bash
./scripts/compose.sh up -d --force-recreate backend
```

Seule `LLM_API_KEY` est nécessaire au tchat réel. Les trois autres clés activent leurs outils indépendamment. Ne mettez jamais ces clés dans une variable `NEXT_PUBLIC_*`, un message de tchat ou un fichier suivi par Git. Dans l'environnement cloud, utilisez les paramètres sécurisés de l'environnement ; les variables injectées dans le shell prennent aussi priorité pour les clés dans Compose.

| Fonction | Intégration | Comportement sans clé |
| --- | --- | --- |
| Modèles de tchat et vision | API compatible OpenAI, OpenRouter par défaut | Mode démo, ou message explicite si la démo est désactivée |
| Recherche web | Brave Search API | Bouton désactivé |
| PDF texte, DOCX, texte, Markdown, CSV | Extraction locale Python | Disponible sans fournisseur |
| PDF scannés / OCR | Mistral OCR | Explication si le PDF n'a pas de texte exploitable |
| Images en entrée | Modèle de vision autorisé dans `LLM_MODELS` | La démo n'analyse pas réellement les images |
| Génération d'images | Ideogram | Bouton désactivé |

Les modèles proposés dans `.env.example` sont des exemples d'identifiants OpenRouter. Vérifiez leur disponibilité sur votre compte ; `DEFAULT_MODEL` doit appartenir à la liste `LLM_MODELS`. Pour un fournisseur direct, changez aussi `LLM_BASE_URL`, la clé et les identifiants. Un seul endpoint de conversation est configuré à la fois. Chaque modèle doit annoncer correctement sa capacité `vision`.

Sur une machine standard, le wrapper utilise simplement `compose.yaml` ; `docker compose up --build -d` fonctionne aussi après création du `.env`. Dans un cloud avec proxy TLS, il active `compose.cloud.yaml` si `SSL_CERT_FILE` ou `CLOUD_CA_BUNDLE` désigne un bundle de confiance fourni par la plateforme. Le bundle passe comme secret BuildKit à l'installation et comme montage en lecture seule au backend, avec les paramètres du proxy. TLS et les empreintes des paquets restent vérifiés ; aucun certificat personnalisé n'est embarqué dans Git ou les images.

Les services externes reçoivent les éléments nécessaires à leur fonction : contexte du tchat au LLM, requête à Brave, document à Mistral si l'OCR est utilisé, prompt à Ideogram. La recherche consulte des **titres, URL et extraits** ; elle ne lit pas automatiquement les pages intégrales. Les images Ideogram sont téléchargées depuis les hôtes exacts de `IDEOGRAM_IMAGE_HOSTS` (`ideogram.ai` par défaut), sans redirection ni transmission de la clé au CDN. Si Ideogram retourne un autre hôte, vérifiez-le avant de l'ajouter ici et à la politique réseau du cloud.

Les choix économiques et les alternatives **Tavily, SearXNG, Supabase, PowerSync, pgvector** sont détaillés dans [le comparatif des services](docs/services.md). Les tarifs actuels n'ont pas été vérifiés depuis ce cloud : les sites documentaires étaient bloqués par sa politique réseau.

## Historique et mémoire

- L'historique complet des messages reste dans la base.
- Un résumé progressif condense les échanges anciens et accompagne les messages récents dans le contexte du modèle. Le seuil se règle avec `SUMMARY_EVERY_MESSAGES`.
- Les mémoires personnelles sont des informations que vous ajoutez explicitement, consultables et supprimables dans le panneau Mémoire. Elles sont injectées dans les conversations.
- Les fichiers sont conservés sur un volume privé ; leurs métadonnées et le texte extrait sont enregistrés en base.

Le résumé peut perdre des détails ; ce n'est pas une seconde copie fidèle de l'historique. Les documents et mémoires sont bornés par la limite de contexte, donc tout le contenu stocké n'est pas forcément transmis à chaque tour. Supprimer une mémoire ne réécrit pas les messages et résumés où vous aviez déjà évoqué cette information. Supprimez aussi les conversations concernées si nécessaire. Pas de recherche vectorielle ni de synchronisation hors ligne dans cette première version.

## Développement sans Docker

Prérequis : Python 3.12+, Node.js 24 et npm.

```bash
./scripts/install.sh --local
./scripts/dev.sh
```

Le backend utilise alors SQLite (fichier dans `backend/data`) et le frontend Next en développement. Il s'agit de données distinctes des volumes PostgreSQL Docker. Arrêtez Compose avant de réutiliser les ports 3000/8000. Le script charge le `.env` racine pour le backend ; le proxy Next pointe vers le backend local.

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m app.cli migrate-schema
.venv/bin/python -m app.cli create-admin --username mon-identifiant
.venv/bin/python -m app.cli migrate-legacy --owner mon-identifiant
cd ../frontend
npm run typecheck
npm run build
cd ..
python3 scripts/smoke.py
```

Les commandes de migration/création du compte sont requises avant de démarrer une base locale. Pour une base existante, sauvegardez la base et les fichiers, puis attribuez l'historique à un administrateur explicitement choisi avec `migrate-legacy`. Les tests fournisseurs utilisent des réponses simulées, sans facturation. `smoke.py` vérifie le refus anonyme, vous demande les identifiants, puis exerce le tchat en mode démo et nettoie les données temporaires. En mode réel, il vérifie la connexion et la configuration sans déclencher de génération payante. `SMOKE_USERNAME` et `SMOKE_PASSWORD` permettent d'automatiser cette connexion.

## Organisation

```text
frontend/             Next App Router, composants React, Tailwind, client SSE
backend/app/          API, authentification, modèles SQLAlchemy, contexte et fournisseurs
backend/migrations/   Migrations versionnées et reprise des données existantes
backend/tests/        Tests API, persistance et fournisseurs simulés
compose.yaml          Frontend + backend + PostgreSQL avec contrôles de santé
scripts/install.sh    Installation Docker ou dépendances locales
scripts/compose.sh    Compose avec prise en charge du proxy TLS cloud
scripts/dev.sh        Démarrage local des deux serveurs
scripts/smoke.py      Parcours de validation via le proxy frontend
docs/architecture.md  Flux et décisions techniques
docs/services.md      Services, alternatives et maîtrise du budget
```

## Périmètre de cette version

Cette version prend en charge les comptes sur invitation et l'isolation par compte, mais lie ses ports à l'interface locale. Avant toute exposition, configurez HTTPS, `SESSION_COOKIE_SECURE=true`, des origines autorisées précises et des sauvegardes testées de la base et des fichiers. Les quotas par utilisateur ne sont pas encore appliqués; la configuration fournie n'est pas un déploiement public prêt à l'emploi.

Les véritables appels LLM, Brave, OCR et Ideogram doivent être vérifiés avec vos clés, les domaines autorisés et votre budget. Le mode démo et les tests simulés ne valident pas un abonnement ou un fournisseur distant.
