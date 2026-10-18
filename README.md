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
DUCKDUCKGO_ENABLED=false
MISTRAL_API_KEY=...
OCR_MODEL=mistral-ocr-4-1
VISION_MODEL=openai/gpt-4o-mini
IDEOGRAM_API_KEY=...
```

```bash
./scripts/compose.sh up -d --force-recreate backend
```

Seule `LLM_API_KEY` est nécessaire au tchat réel. Les trois autres clés activent leurs outils indépendamment. Ne mettez jamais ces clés dans une variable `NEXT_PUBLIC_*`, un message de tchat ou un fichier suivi par Git. Dans l'environnement cloud, utilisez les paramètres sécurisés de l'environnement ; les variables injectées dans le shell prennent aussi priorité pour les clés dans Compose.

| Fonction | Intégration | Comportement sans clé |
| --- | --- | --- |
| Modèles de tchat et vision | API compatible OpenAI, OpenRouter par défaut | Mode démo, ou message explicite si la démo est désactivée |
| Recherche web | Brave Search API, secours DuckDuckGo Instant Answers optionnel | Disponible en mode réel si `DUCKDUCKGO_ENABLED=true`, sinon bouton désactivé |
| DOCX, texte, Markdown, CSV, JSON | Extraction locale Python | Disponible sans fournisseur |
| PDF, même avec texte, et images | Mistral OCR 4.1 avec annotations des figures | `MISTRAL_API_KEY` requise en mode réel |
| Pages et images sans texte | Modèle dédié `VISION_MODEL`, via `LLM_BASE_URL` et `LLM_API_KEY` | Erreur explicite si le secours vision n'est pas configuré |
| Génération d'images | Ideogram | Bouton désactivé |

Les modèles proposés dans `.env.example` sont des exemples d'identifiants OpenRouter. Vérifiez leur disponibilité sur votre compte ; `DEFAULT_MODEL` doit appartenir à la liste `LLM_MODELS`. Pour un fournisseur direct, changez aussi `LLM_BASE_URL`, la clé et les identifiants. Un seul endpoint de conversation est configuré à la fois. Chaque modèle doit annoncer correctement sa capacité `vision`.

### Secours DuckDuckGo

Dans `.env`, activez `DUCKDUCKGO_ENABLED=true` pour autoriser l’API officielle **Instant Answers**, sans clé ni dépendance supplémentaire. Brave reste prioritaire : DuckDuckGo est sollicité une fois si Brave n’est pas configuré, échoue ou ne renvoie aucun résultat. L’option est désactivée par défaut et aucun appel n’est effectué en mode démo.

Instant Answers fournit des résumés, définitions et sujets associés ; sa couverture est plus limitée qu’une recherche web complète, notamment pour l’actualité et les questions précises. Le tchat identifie les sources DuckDuckGo et explique le recours au secours. Si aucune source exploitable n’est trouvée, il affiche une erreur avant d’appeler le modèle ; désactivez Web pour continuer sans recherche.

Après récupération de cette version et modification du `.env`, reconstruisez les services :

```bash
./scripts/compose.sh up -d --build --wait
```

### Lecture des pièces jointes

En mode réel, chaque nouveau PDF ou image est analysé dès l'ajout par `OCR_MODEL` (Mistral OCR 4.1 par défaut). Le texte, les tableaux Markdown et les annotations détaillées des figures sont conservés par page. Chaque page sans texte est décrite par `VISION_MODEL` : pour un PDF, le backend rend la page entière avec PDFium. Ce modèle doit réellement prendre en charge les images ; il est indépendant du modèle de discussion et n'a pas besoin d'être ajouté au sélecteur `LLM_MODELS`.

Ouvrez **Contenu extrait** sous une pièce jointe, avant ou après l'envoi, pour consulter les pages et les descriptions. La transcription OCR brute est affichée par défaut, sans résumé ni reformulation ; le rendu Markdown reste disponible via **Mise en forme**. L'analyse documentaire complémentaire est séparée et repliée : elle ne remplace pas le texte extrait. Les consignes d'annotations demandent une transcription verbatim des textes des figures, dans leur langue originale, et des descriptions détaillées sans recherche de concision. Le secours vision dispose de 8000 tokens de sortie et refuse une réponse signalée comme coupée. Les passages illisibles restent incertains : aucune fidélité parfaite ne peut être garantie par un OCR génératif.

Le résultat est chargé à la demande et accessible uniquement au propriétaire. Le chat et ses résumés réutilisent cette analyse, sans nouvel appel OCR à chaque message. Le chat reçoit le texte OCR et les descriptions, pas une synthèse substituée au document ; il utilise le budget de contexte disponible au lieu d'une coupure fixe à 16000 caractères. Si les pièces jointes dépassent ce budget, des extraits sont répartis entre les pages, avec un avertissement de sélection ; leur extraction complète reste consultable, sans garantie que chaque réponse prenne en compte tous les détails. Joignez à nouveau un ancien document pour bénéficier des nouvelles consignes d'analyse ; aucune réanalyse payante n'est déclenchée automatiquement.

Limites : 300 pages par PDF, lots OCR de 8 pages, 8 Mo par image et `MAX_UPLOAD_MB` par fichier ; résultat structuré limité à 4 Mo, réponse OCR à 8 Mo par lot, délai global de 10 minutes. Les dépassements ou erreurs fournisseur refusent l'ajout au lieu d'enregistrer une analyse prétendument complète. L'OCR, ses annotations et les appels vision peuvent chacun être facturés. Le document est envoyé à Mistral ; les pages/images sans texte sont aussi envoyées au fournisseur LLM configuré. L'annotation documentaire est un relevé complémentaire, pas la transcription ni la description exhaustive des figures : Mistral n'y fournit que les huit premières images du lot.

Avec `DEMO_MODE=true`, aucun OCR ni appel vision n'est effectué : seuls les textes locaux restent disponibles et les PDF sans texte sont refusés. Les anciennes pièces jointes ne sont pas réanalysées automatiquement ; joignez-les à nouveau pour obtenir l'analyse complète.

Pour une base existante, sauvegardez la base et les fichiers, puis appliquez la migration avant de redémarrer : `cd backend && .venv/bin/python -m app.cli migrate-legacy` en local, ou `./scripts/compose.sh run --rm backend python -m app.cli migrate-legacy` avec Docker. Les extractions historiques restent inchangées.

Sur une machine standard, le wrapper utilise simplement `compose.yaml` ; `docker compose up --build -d` fonctionne aussi après création du `.env`. Dans un cloud avec proxy TLS, il active `compose.cloud.yaml` si `SSL_CERT_FILE` ou `CLOUD_CA_BUNDLE` désigne un bundle de confiance fourni par la plateforme. Le bundle passe comme secret BuildKit à l'installation et comme montage en lecture seule au backend, avec les paramètres du proxy. TLS et les empreintes des paquets restent vérifiés ; aucun certificat personnalisé n'est embarqué dans Git ou les images.

Les services externes reçoivent les éléments nécessaires à leur fonction : contexte du tchat au LLM, requête à Brave ou DuckDuckGo selon le fournisseur utilisé, document à Mistral si l'OCR est utilisé, prompt à Ideogram. La recherche consulte des **titres, URL et extraits** ; elle ne lit pas automatiquement les pages intégrales. Les images Ideogram sont téléchargées depuis les hôtes exacts de `IDEOGRAM_IMAGE_HOSTS` (`ideogram.ai` par défaut), sans redirection ni transmission de la clé au CDN. Si Ideogram retourne un autre hôte, vérifiez-le avant de l'ajouter ici et à la politique réseau du cloud.

Les choix économiques et les alternatives **Tavily, SearXNG, Supabase, PowerSync, pgvector** sont détaillés dans [le comparatif des services](docs/services.md). Les tarifs actuels n'ont pas été vérifiés depuis ce cloud : les sites documentaires étaient bloqués par sa politique réseau.

## Historique et mémoire

- L'historique complet des messages reste dans la base.
- Un résumé progressif condense les échanges anciens et accompagne les messages récents dans le contexte du modèle. Réglez `SUMMARY_MODEL` (`openai/gpt-4o-mini`), `SUMMARY_EVERY_MESSAGES` (12), `MAX_SUMMARY_CHARS` (6000), `SUMMARY_TEMPERATURE` (0.2) et `SUMMARY_MAX_TOKENS` (900) dans `.env`.
- Les mémoires personnelles sont des informations que vous ajoutez explicitement, consultables et supprimables dans le panneau Mémoire. Elles sont injectées dans les conversations.
- Les compétences sont des prompts personnels réutilisables, enregistrés en base et sélectionnables par conversation. Le modèle IA configuré peut en proposer une amélioration ; elle reste un brouillon jusqu'à son enregistrement explicite.
- Le budget de contexte se règle avec `MAX_CONTEXT_CHARS` (60000). Pour les réponses du modèle, `LLM_TEMPERATURE` (0.7) et `LLM_MAX_TOKENS` (2048) sont également configurables dans `.env`.
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

Les véritables appels LLM, Brave, DuckDuckGo, OCR et Ideogram doivent être vérifiés avec la configuration nécessaire et les domaines autorisés. Le mode démo et les tests simulés ne valident pas un abonnement ou un fournisseur distant.
