# Services, bibliothèques et maîtrise du budget

Choix pour cette première version : Next.js/React/Tailwind, FastAPI, PostgreSQL dans Docker, API de conversation compatible OpenAI avec OpenRouter par défaut, recherche Brave à la demande, extraction locale des documents texte et Mistral OCR pour les PDF/images en mode réel. Ideogram utilise votre propre clé, conservée côté serveur.

Vérification documentaire tentée le **17 octobre 2026** : les requêtes HTTPS vers les sources officielles listées ci-dessous ont été refusées par le proxy de cet environnement (`Tunnel connection failed: 403 Forbidden`). Les liens sont fournis pour vérification ; leurs pages et leurs tarifs n'ont donc pas pu être consultés ici. Aucun montant actuel, quota gratuit ou classement du « moins cher » n'est garanti. Aucun appel payant n'a été effectué.

## Conversation et choix du modèle

| Solution | Intérêt pour ce projet | Coût et limites à vérifier |
| --- | --- | --- |
| **OpenRouter** | Une API et un compte pour essayer plusieurs familles de modèles ; bon point de départ pour le sélecteur de modèles. | Tarifs par modèle, frais éventuels de paiement, règles de routage, conservation des données et disponibilité. Les modèles gratuits peuvent avoir des quotas, des conditions et une disponibilité variables. |
| **Gemini en direct** | Intéressant pour comparer des modèles rapides et multimodaux sans intermédiaire. | Tarifs entrée/sortie, cache, quotas, disponibilité régionale et usage des données selon le niveau de service. Un quota gratuit n'est pas une garantie de production. |
| **Mistral en direct** | Conversation et OCR chez un même fournisseur ; modèles légers à comparer pour le résumé. | Prix de chaque modèle et de l'OCR, limites de fichiers, résidence des données, quotas. |
| **OpenAI en direct** | API et modèles multimodaux ; une autre option compatible avec le protocole HTTP utilisé. | Prix du modèle précis, tokens en entrée/sortie, éventuels outils facturés séparément. |

L'intégration fournie utilise `httpx` pour les appels HTTP et le flux SSE d'une API de conversation compatible OpenAI. Le SDK Python `openai` est une autre option, mais n'est pas une dépendance de cette version. La compatibilité ne signifie pas que tous les paramètres, outils, formats d'image et noms de modèles sont interchangeables. Le serveur autorise une liste explicite de modèles ; leurs capacités doivent être testées chez le fournisseur choisi. L'intégration configure un seul fournisseur de conversation à la fois ; ajouter simultanément des comptes directs nécessite une table de routage côté serveur.

Pour commencer, choisir un petit modèle pour les échanges ordinaires et le résumé ; réserver le modèle plus puissant aux demandes qui le nécessitent. Comparer ensuite sur quelques conversations réelles. Il n'est pas nécessaire d'ajouter LangChain ou LlamaIndex pour ce périmètre : des adaptateurs explicites avec `httpx` suffisent. Ces frameworks deviennent utiles pour des chaînes d'outils ou une ingestion documentaire plus complexe.

Sources officielles à consulter : [OpenRouter, démarrage](https://openrouter.ai/docs/quickstart), [tarifs Gemini](https://ai.google.dev/gemini-api/docs/pricing), [tarifs OpenAI](https://openai.com/api/pricing/), [documentation Mistral](https://docs.mistral.ai/), [tarifs Mistral](https://mistral.ai/pricing).

## Recherche web : Brave au départ

| Solution | À choisir si… | Points de vigilance |
| --- | --- | --- |
| **Brave Search API** | Vous voulez une recherche classique avec titres, URL et extraits, puis laisser votre modèle rédiger une réponse sourcée. C'est l'intégration de cette version. | Vérifier prix par requête, crédits éventuels, limites et conditions d'utilisation. La recherche et la rédaction par le LLM sont deux coûts distincts. |
| **Tavily** | Vous préférez une API orientée applications IA avec davantage d'options de recherche et d'extraction. | Vérifier le nombre de crédits consommés par chaque opération et chaque profondeur de recherche ; les options avancées peuvent changer le coût. Non intégré dans cette version. |
| **SearXNG auto-hébergé** | Vous souhaitez administrer votre propre métamoteur et acceptez sa maintenance. | Logiciel libre ne signifie pas recherches illimitées ou sans coût : hébergement, moteurs amont, blocages, conditions et maintenance restent à votre charge. Ce n'est pas une API gérée équivalente. Non intégré ici. |

Brave est un choix de simplicité, pas une affirmation de prix minimal actuel. Pour limiter la facture : recherche activée explicitement par l'utilisateur, une requête par message, quelques résultats, extraits courts et liens conservés avec la réponse. Ajouter des quotas avant toute ouverture multiutilisateur.

**Les extraits de recherche ne constituent pas une lecture exhaustive des pages.** Une réponse doit rester prudente si la source ne fournit qu'un extrait. Une future fonction de lecture de pages demandera une extraction distincte, les autorisations appropriées et une protection contre les requêtes vers les réseaux privés. Les contenus web doivent être traités comme des données non fiables : ils ne peuvent pas modifier les instructions système ni autoriser des actions.

Sources officielles : [Brave Search API](https://api.search.brave.com/app/documentation/web-search/get-started), [crédits Tavily](https://docs.tavily.com/documentation/api-credits), [tarifs Tavily](https://www.tavily.com/pricing), [documentation SearXNG](https://docs.searxng.org/).

## Pièces jointes, OCR et images

| Type de fichier | Traitement conseillé | Ce qu'il faut savoir |
| --- | --- | --- |
| Texte, Markdown | Lecture locale avec limite de taille. | Pas d'appel OCR nécessaire. |
| PDF, avec ou sans texte | Mistral OCR 4.1, toutes les pages, annotations des figures. | `pypdf` valide le PDF ; PDFium rend les pages sans texte pour le secours vision. En démo seulement, extraction de texte locale limitée. |
| DOCX | `python-docx` localement. | Extraction de texte ; ce n'est pas un moteur complet de rendu bureautique. Les anciens fichiers `.doc` nécessitent un autre outil. |
| Photo de document | Mistral OCR 4.1 avec annotations. | Texte et descriptions enregistrés dès l'ajout ; document envoyé à Mistral, consommation facturée. |
| Image ou page sans texte | `VISION_MODEL`, modèle vision dédié configurable. | Description détaillée via `LLM_BASE_URL` et `LLM_API_KEY`, même avec un modèle de discussion sans vision. Appel supplémentaire facturable. |
| Image à générer | Ideogram, avec votre clé existante. | Coût par génération, options et quotas selon votre compte. La génération reste une action explicite. |

`pypdf` **n'effectue pas d'OCR**. En mode réel, l'analyse externe est systématique pour les PDF/images afin de conserver aussi les illustrations des PDF textuels. `OCR_MODEL=mistral-ocr-4-1` est la valeur par défaut ; OCR 4.0 est déprécié selon la documentation consultée le 18 octobre 2026. Les schémas `bbox_annotation_format` demandent des descriptions exhaustives et une transcription verbatim de tous les textes des figures, sans traduction ni correction. `document_annotation_format` demande un relevé détaillé complémentaire, dont la couverture visuelle est limitée aux huit premières figures du lot. Ce relevé ne remplace jamais la transcription OCR, affichée brute par défaut et transmise au chat dans le budget de contexte disponible. Les descriptions par figure restent distinctes. Le secours vision peut produire jusqu'à 8000 tokens ; une sortie coupée est refusée. Ces descriptions plus détaillées peuvent augmenter le coût et la latence. Les détails illisibles doivent être signalés, pas inventés.

L'analyse est conservée par page et consultable depuis **Contenu extrait** sans nouvel appel payant. Limites applicatives : 300 pages, lots OCR de 8 pages, 4 Mo d'extraction structurée, 8 Mo de réponse par lot et 10 minutes au total. Le secours vision analyse une image normalisée à 2048 pixels de côté maximum ; le texte et les détails très fins peuvent rester incertains. Les pages sont traitées séquentiellement, sans réanalyse automatique des anciens fichiers. Si le secours vision requis n'est pas configuré ou échoue, l'ajout échoue explicitement. En démo, aucun fournisseur n'est appelé.

Prévoir les coûts cumulés d'OCR, d'annotations et de description vision, ainsi que le transfert du document à Mistral et des pages/images sans texte au fournisseur vision. Les appels réels et tarifs du compte n'ont pas été testés ; seuls les contrats HTTP simulés et le rendu local sont vérifiés.

Limiter taille, formats acceptés et quantité de texte injectée dans le contexte. Conserver les fichiers hors des répertoires publics du frontend. Une extraction intégrale envoyée à chaque tour peut coûter davantage que l'extraction elle-même ; le futur besoin de recherche dans de gros documents justifiera un système RAG, avec citations et récupération de passages.

Sources officielles : [Mistral Document AI/OCR](https://docs.mistral.ai/capabilities/document_ai/basic_ocr/), [extraction de texte pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html), [python-docx](https://python-docx.readthedocs.io/en/latest/), [API Ideogram](https://developer.ideogram.ai/).

## Base de données : PostgreSQL, sans couche de synchronisation initiale

| Solution | Rôle | Recommandation |
| --- | --- | --- |
| **PostgreSQL + SQLAlchemy** | Base serveur pour conversations, messages, modèles choisis, résumés, mémoires explicites et métadonnées des fichiers. | Choix du Docker Compose. Pas de fournisseur de base imposé ; prévoir sauvegardes et volume persistant. |
| **SQLite** | Base légère en fichier, pratique pour développement local et tests. | Adaptée à un usage simple ; PostgreSQL est préférable pour la cible Docker et les accès concurrents. |
| **Supabase** | PostgreSQL géré avec services supplémentaires, notamment authentification et stockage. | Option d'hébergement ultérieure si ces services font gagner du temps. Vérifier stockage, trafic, sauvegardes, suspension éventuelle et coût du plan. Ne pas exposer une clé privilégiée au navigateur. |
| **PowerSync** | Synchronisation d'une base locale du client, souvent SQLite, avec une base serveur. | Ce n'est pas le remplacement de la base serveur. À ajouter si le fonctionnement hors ligne et la synchronisation multiappareils deviennent un vrai besoin ; inutile pour le tchat connecté initial. |
| **pgvector** | Extension PostgreSQL pour recherche vectorielle. | À ajouter pour rechercher des passages de documents ou des souvenirs par similarité. Pas nécessaire pour enregistrer l'historique ou un résumé. |

Un volume Docker protège contre la suppression d'un conteneur ; **ce n'est pas une sauvegarde**. Les fichiers joints et les images générées doivent aussi être sauvegardés ou stockés dans un stockage objet privé si l'application est hébergée durablement.

Sources officielles : [PostgreSQL](https://www.postgresql.org/docs/current/), [PowerSync](https://docs.powersync.com/intro/how-it-works), [Supabase](https://supabase.com/docs/guides/database), [tarifs Supabase](https://supabase.com/pricing), [pgvector](https://github.com/pgvector/pgvector).

## Mémoire du tchat et budget

Conserver tout l'historique en base, mais envoyer au modèle un résumé progressif et les messages récents, dans une limite de contexte définie. Le résumé est recalculé périodiquement avec le modèle de conversation sélectionné dans cette version ; choisir un modèle économique réduit donc aussi ce coût. Un modèle dédié au résumé pourrait être ajouté ultérieurement. Le résumé reste une synthèse imparfaite ; l'historique enregistré reste la référence.

Séparer ce résumé des **mémoires personnelles explicites**, que l'utilisateur peut consulter et supprimer : préférences, contraintes ou informations qu'il demande de retenir. Il n'est pas nécessaire d'utiliser une base vectorielle ni un service de mémoire payant pour cette première version. Si une information est supprimée, penser aussi aux résumés et copies qui pourraient encore la contenir ; supprimer seulement le message d'origine ne suffit pas à l'effacer du contexte synthétisé.

La facture s'estime ainsi, avec les tarifs réels de chaque fournisseur :

```text
LLM = tokens d'entrée / 1 000 000 × tarif d'entrée
    + tokens de sortie / 1 000 000 × tarif de sortie
total = LLM + résumés + recherches + OCR + images + hébergement/stockage
```

Le cache, les images, les outils et la classification des tokens peuvent modifier ce calcul selon le fournisseur. Enregistrer l'usage renvoyé par les API, fixer des limites chez les fournisseurs et revoir le choix du modèle avec les consommations réelles. Une clé API doit rester dans les variables du backend, jamais dans une variable `NEXT_PUBLIC_*` ni dans Git.

## Accès réseau à prévoir pour les appels réels

Les domaines nécessaires dépendent des services activés : `openrouter.ai`, `api.search.brave.com`, `api.mistral.ai` et `api.ideogram.ai`. Pour un autre fournisseur direct : `api.openai.com` ou `generativelanguage.googleapis.com`. Les téléchargements d'images peuvent nécessiter un domaine de stockage supplémentaire fourni par Ideogram ; vérifier l'URL réellement retournée et sa politique d'accès avant de l'autoriser.

Cette liste explique les besoins ; elle ne modifie aucune règle réseau. Les clés existantes doivent être renseignées dans les paramètres sécurisés de l'environnement ou dans le fichier local ignoré prévu par le projet. Les modes sans fournisseur et les tests locaux ne prouvent pas le fonctionnement d'une API distante. La validation de bout en bout reste à effectuer avec une clé, l'accès réseau et un budget autorisé.
