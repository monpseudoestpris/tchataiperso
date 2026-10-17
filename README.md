# cLAIr — tchat IA personnel

Une application de tchat en français avec **Next.js / React / Tailwind**, **FastAPI** et **PostgreSQL**. Conversation en streaming, historique persistant, choix du modèle, mémoires personnelles, résumé de conversation, documents joints, recherche web et génération d'images Ideogram.

La première exécution utilise un **mode démo explicitement signalé**. Il produit des réponses locales déterministes pour vérifier l'interface et la persistance ; il ne contacte aucune IA. Les fournisseurs réels se configurent uniquement dans le backend.

## Démarrer avec Docker

Prérequis : Docker Engine avec Compose v2 et Python 3 pour le petit script d'installation.

```bash
./scripts/install.sh
```

Le script crée `.env` s'il n'existe pas, avec un mot de passe PostgreSQL aléatoire, construit les images, démarre les trois services, attend leur état de santé et exécute un parcours de vérification. Il conserve votre `.env` existant. Les ports sont liés à l'interface locale : frontend **3000**, backend **8000** ; PostgreSQL reste sur le réseau Docker interne.

```bash
./scripts/compose.sh up --build -d --wait  # démarrer / reconstruire
./scripts/compose.sh logs -f backend     # diagnostiquer le backend
./scripts/compose.sh stop                # arrêter sans supprimer les données
python3 scripts/smoke.py            # vérifier le parcours local sans appel payant
```

Les volumes `postgres_data` et `uploads_data` conservent les données après un redémarrage. `docker compose down -v` les **efface**. Une sauvegarde doit couvrir la base et les fichiers ; les volumes seuls ne constituent pas une sauvegarde.

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
cd ../frontend
npm run typecheck
npm run build
cd ..
python3 scripts/smoke.py
```

Les tests fournisseurs utilisent des réponses simulées, sans facturation. `smoke.py` exerce les écritures, le streaming et la relecture d'historique en mode démo, puis nettoie ses conversations et mémoires temporaires. En mode réel, il ne déclenche pas de génération payante.

## Organisation

```text
frontend/             Next App Router, composants React, Tailwind, client SSE
backend/app/          API, modèles SQLAlchemy, contexte et adaptateurs fournisseurs
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

Cette version est destinée à un **usage personnel sur une machine de confiance** et lie ses ports à l'interface locale. L'authentification multiutilisateur, l'isolation par compte, les quotas et le déploiement public avec HTTPS restent à ajouter avant une exposition à Internet. La suppression des données, la récupération après panne et les changements futurs de schéma doivent être accompagnés de sauvegardes et de migrations. La configuration fournie n'est pas un déploiement public prêt à l'emploi.

Les véritables appels LLM, Brave, OCR et Ideogram doivent être vérifiés avec vos clés, les domaines autorisés et votre budget. Le mode démo et les tests simulés ne valident pas un abonnement ou un fournisseur distant.
