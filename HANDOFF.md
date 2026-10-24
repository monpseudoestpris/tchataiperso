# Relais — 24 octobre 2026 (Ajustements DeepSearch : qualité des requêtes 4-6 mots avec guillemets, garde-fous stricts backend et alignement UI modale)

- Réalisé :
  - **Qualité orthographique et encodage des requêtes pour scrapers / moteurs web** (`backend/app/providers.py`) :
    - *Règle des 4 à 6 mots-clés percutants* : interdiction des requêtes de 10-12 mots diluées provoquant un OR implicite sur SearXNG ; obligation de formuler des requêtes denses de 4 à 6 mots-clés.
    - *Verrouillage des concepts exacts par guillemets* : consignes impératives d'utiliser des guillemets doubles droits (`"..."`) sur les expressions exactes clés (ex: `"active recall"`, `"spaced repetition"`, `"Dunlosky"`, `"charge cognitive"`, `"learning styles"`).
    - *Contrôle qualité orthographique strict* : consigne d'élimination de toute coquille typographique ou troncature de syllabe (ex: "élèves" et non "éélves" ou "ail élèves").
    - *Robustesse du parser de requêtes (`_parse_query_list`)* : normalisation des guillemets typographiques (`“`, `”`, `«`, `»` -> `"`), suppression des ponctuations résiduelles (`[,;.]`), préservation des expressions exactes entre guillemets internes.
  - **Garde-fous stricts côté backend contre boucles infinies et explosion de tokens** (`backend/app/deep_search.py`) :
    - Plafond d'itérations en dur infranchissable : `HARD_MAX_ITERATIONS = 5` (forcé via `min(max(1, max_iterations), 5)`).
    - Plafond absolu de requêtes exécutées : `HARD_MAX_TOTAL_QUERIES = 24` ; arrêt immédiat vers la synthèse si atteint.
    - Plafond absolu de sources collectées : `HARD_MAX_SOURCES = 120` ; arrêt immédiat vers la synthèse si atteint.
    - Application de ces plafonds dans `should_continue`, `evaluate_node`, et `execute_deep_search`.
  - **Amélioration UX / UI de la modale Deep Search** (`frontend/components/deep-search-modal.tsx`, `frontend/app/globals.css`) :
    - Intitulé clair et aligné au-dessus de la liste : bloc structuré avec icône `ListFilter`, titre net `Requêtes planifiées` et badge dédié `({validQueriesCount})`, éliminant les textes orphelins ou mal alignés.
    - Sous-titre explicatif : `4 à 6 mots-clés denses avec guillemets · Factuelles, critiques et internationales`.
    - Placeholders indicatifs sur les champs de saisie (`Ex: "active recall" "spaced repetition" Dunlosky meta-analysis...`).
    - Libellé rassurant sur le badge d'en-tête : `Exploration continue bornée (max 5 vagues)`.
- Fichiers modifiés :
  - `backend/app/providers.py`, `backend/app/deep_search.py`, `backend/tests/test_deep_search.py`, `backend/tests/test_providers.py`, `frontend/components/deep-search-modal.tsx`, `frontend/app/globals.css`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : **234/234 tests réussis à 100%** (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Build de production Next.js : **succès** (`npm --prefix frontend run build`).
  - Statut des conteneurs : `healthy` (API 8001 et Web 3001 opérationnels).
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch pour observer la netteté des requêtes (4-6 mots avec guillemets), la lisibilité de l'en-tête « Requêtes planifiées (8) » et les garde-fous de fin de recherche.

---

# Relais — 24 octobre 2026 (Délégation des modèles DeepSearch : Fable 5.1 pour la planification, Gemini 3.8 Flash pour les choix, la traduction et la synthèse)

- Réalisé :
  - **Délégation stricte des modèles pour le Deep Search** (`backend/app/config.py`, `backend/app/providers.py`, `backend/app/routers/messages.py`, `compose.yaml`, `.env.example`) :
    - `anthropic/claude-fable-5.1` (`deep_search_plan_model`) est réservé **strictement et exclusivement** à la Phase 1 de planification stratégique (`plan_deep_search_queries`).
    - Un modèle économique, rapide et performant (`google/gemini-3.8-flash` via `deep_search_synthesis_model`) est désormais déployé pour toutes les étapes suivantes :
      - Phase 4 de réévaluation et choix de sous-requêtes contradictoires (`plan_deep_search_followup`).
      - Traduction des extraits multilingues (`translate_deep_search_sources`).
      - Synthèse finale, rapport technique et grounding en streaming (`backend/app/routers/messages.py` bascule automatiquement le modèle vers `deep_search_synthesis_model` si Fable 5.1 ou aucun modèle spécifique n'est imposé par la requête).
    - Configuration de la variable d'environnement `DEEP_SEARCH_SYNTHESIS_MODEL` (défaut : `google/gemini-3.8-flash`) dans `compose.yaml` et `.env.example`.
  - **Actualisation des suites de tests** (`backend/tests/test_providers.py`) :
    - Ajout du champ `deep_search_synthesis_model` dans les fixtures de test.
    - Assertions confirmant que `plan_deep_search_queries` cible `deep_search_plan_model` (Fable 5.1) et que `plan_deep_search_followup` ainsi que `translate_deep_search_sources` ciblent `deep_search_synthesis_model` (Gemini 3.8 Flash).
- Fichiers modifiés :
  - `backend/app/config.py`, `backend/app/providers.py`, `backend/app/routers/messages.py`, `compose.yaml`, `.env.example`, `backend/tests/test_providers.py`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : **233/233 tests réussis à 100%** (`docker exec tchataiperso-clair-api-1 env -i PATH=/home/app/.local/bin:/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Statut du conteneur API : `healthy` (127.0.0.1:8001 opérationnel).
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch pour observer la planification Fable 5.1 et la suite de l'exploration/synthèse opérée par Gemini 3.8 Flash.

---

# Relais — 24 octobre 2026 (Protocole opérationnel DeepSearch en 5 phases : Décomposition 5 axes, Retrieval différencié, Extraction atomique `findings`, Audit contradictoire & Grounding)

- Réalisé :
  - **Intégration intégrale du Protocole Opérationnel en 5 phases (« Deep Search Agent »)** (`backend/app/providers.py`, `backend/app/deep_search.py`, `backend/app/context.py`, `frontend/components/deep-search-modal.tsx`) :
    - **PHASE 1 : DÉCOMPOSITION & PLANIFICATION INITIALE** (`plan_deep_search_queries` dans `backend/app/providers.py`, `DeepSearchModal`) :
      1. Identification des entités, acronymes, technologies, acteurs et périmètre temporel/matériel.
      2. Découpage selon les **5 axes obligatoires** :
         - *Axe Entités / Définitions* (composants, versions, standards impliqués)
         - *Axe Temporel* (état de l'art actuel, changements et benchmarks récents)
         - *Axe Technique & Causal* (mécanismes internes, architectures, métriques objectives)
         - *Axe Contradictoire* (goulots d'étranglement, limitations, failles, avis opposés, Thèse vs Antithèse)
         - *Axe Périmètre & Contraintes* (spécifications d'environnement, conditions aux limites)
      3. Matrice de recherche initiale (3 à 5 sous-questions prioritaires).
      4. Affichage visuel des 5 axes obligatoires dans l'en-tête de la modale de planification (`frontend/components/deep-search-modal.tsx`).
    - **PHASE 2 : GÉNÉRATION DE REQUÊTES & RETRIEVAL MULTI-SOURCES** (`plan_deep_search_queries`, `_authority_score` dans `backend/app/deep_search.py`) :
      1. Requêtes différenciées : *Requête Factuelle / Directe* (benchmarks, doc technique), *Requête Contradictoire / Critique* (« bottlenecks », « issues », « vs », « tradeoffs »), *Requête en anglais* (documentation primaire internationale).
      2. Priorisation automatique des sources d'autorité (`github.com`, `arxiv.org`, `huggingface.co`, `docs.`, `ieee.org`, `.gov`, `.edu`, présence de métriques chiffrées) et éviction des URLs publicitaires/spam.
    - **PHASE 3 : EXTRACTION, PARSING & FILTRAGE DU CONTENU** (`_clean_source_snippet`, `_extract_date_hint`, `search_node` dans `backend/app/deep_search.py`) :
      1. Nettoyage du boilerplate HTML, barres de navigation et bannières cookies/RGPD.
      2. Extraction factuelle sélective consignée dans `findings` en associant systématiquement : l'URL source exacte (`URL:`), la date de publication/modification détectée (`Date:`) et le contexte technique (`Contexte:`).
    - **PHASE 4 : CROISEMENT, AUDIT CONTRADICTOIRE & RÉÉVALUATION (RE-THINKING)** (`plan_deep_search_followup` dans `backend/app/providers.py`, `evaluate_node` dans `backend/app/deep_search.py`) :
      1. Détection des contradictions entre sources (identification de la cause : environnement de test, version obsolète, condition implicite) et déclenchement de requêtes vers la source primaire.
      2. Test de complétude sur les 5 axes : rebouclage vers la Phase 2 tant qu'une dimension manque de preuves solides, ou clôture (`[]`) vers la Phase 5 lorsque les preuves sont convergentes et complètes.
    - **PHASE 5 : SYNTHÈSE TECHNIQUE & TRAÇABILITÉ (GROUNDING)** (`DEEP_SEARCH_PROMPT` dans `backend/app/context.py`) :
      1. Structure obligatoire du livrable : Vue d'ensemble / Réponse directe (2-3 phrases), Analyse détaillée par composant selon les 5 axes, Matrice comparative / Données chiffrées en tableaux Markdown, Limites, risques et compromis (Trade-offs).
      2. Règles strictes de traçabilité : zéro assertion non sourcée (`[1]`, `[2]`), mention explicite des zones d'incertitude ou d'absence de données recoupées.
- Fichiers modifiés :
  - `backend/app/providers.py`, `backend/app/deep_search.py`, `backend/app/context.py`, `frontend/components/deep-search-modal.tsx`, `backend/tests/test_providers.py`, `backend/tests/test_deep_search.py`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : **233/233 tests réussis à 100%** (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch pour observer l'exécution complète du protocole en 5 phases.

---

# Relais — 24 octobre 2026 (Suppression du plafond 100 sources DeepSearch, recherche continue jusqu'à complétude & fiabilisation de la modale)

- Réalisé :
  - **Suppression du plafond de 100 sources & recherche continue jusqu'à complétude** (`backend/app/deep_search.py`, `backend/app/providers.py`, `backend/app/routers/messages.py`, `backend/app/context.py`) :
    - Élimination de la limite rigide de 100 sources (`max_sources: int | None = None`, `max_total: int | None = None`).
    - Évaluation dynamique de la complétude dans `plan_deep_search_followup` et `evaluate_node` : analyse critique sur l'ensemble des sources collectées (jusqu'à 60-100 sources analysées).
    - Condition d'arrêt pilotée par l'exhaustivité de l'investigation :
      - Si l'investigation est complète (socle conceptuel, état de l'art, mécanismes techniques/métriques, confrontation contradictoire thèse/antithèse, retours d'expérience et contraintes réelles tous solidement documentés sans zone d'ombre) -> arrêt immédiat et passage à la synthèse globale.
      - Si l'investigation est incomplète -> poursuite automatique par vagues successives (`max_iterations` porté à 5) en formulant de nouvelles requêtes chirurgicales pour combler les manques.
    - Élargissement du budget contextuel des sources injectées (`source_limit` porté à 250 000 caractères) pour accueillir l'ensemble des sources web sans troncation prématurée.
  - **Correction des disparitions intempestives de la modale DeepSearch** (`frontend/components/deep-search-modal.tsx`, `frontend/components/chat-app.tsx`) :
    - *Cause racine 1 (Fermeture accidentelle au clic/glisser sur le backdrop)* : lors de la sélection de texte ou d'un clic près du bord de la modale, le relâchement du clic sur l'overlay déclenchait `onClick` et fermait la modale. Corrigé avec `overlayMouseDownRef` : la fermeture ne se déclenche que si le `mousedown` et le `mouseup` ont tous deux pris naissance sur l'overlay.
    - *Cause racine 2 (Fermeture prématurée de la modale en cas de flux occupé ou texte vide)* : lors du lancement, `handleConfirmPlan` fermait la modale avant que `send()` n'ait pu démarrer, laissant l'utilisateur sans retour en cas de flux occupé. Rendu asynchrone avec état de chargement `isLaunching`, gestion des erreurs dans la modale sans fermeture si l'envoi échoue, et repli automatique sur la première requête si le texte du brouillon est vide.
    - *Cause racine 3 (Gestion de la touche Entrée)* : autofocus immédiat sur le premier champ de saisie des requêtes dès l'ouverture et écoute de la touche Entrée sur chaque champ pour valider et lancer le plan directement.
  - **Actualisation des libellés UI** (`frontend/components/chat-app.tsx`, `frontend/components/deep-search-modal.tsx`) :
    - Remplacement des mentions « jusqu'à 100 sources » par « Exploration exhaustive sans limite de sources » et recherche continue jusqu'à complétude.
  - **Tests et validation** :
    - Actualisation des tests unitaires backend (`backend/tests/test_deep_search.py`, `backend/tests/test_providers.py`, `backend/tests/test_api.py`).
    - Suite de tests complète backend : **233/233 tests réussis à 100%**.
    - Validation TypeScript frontend : **0 erreur**.
    - Compilation de production Next.js : **succès**.
    - Redémarrage des conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` : statuts sains (`healthy`).
- Fichiers modifiés :
  - `backend/app/deep_search.py`, `backend/app/providers.py`, `backend/app/routers/messages.py`, `backend/app/context.py`, `backend/tests/test_deep_search.py`, `backend/tests/test_providers.py`, `backend/tests/test_api.py`, `frontend/components/deep-search-modal.tsx`, `frontend/components/chat-app.tsx`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 233/233 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Statut des conteneurs : `healthy` (API 8001 et Web 3001 opérationnels).
  - Vérification Git : absence de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch pour observer la collecte approfondie sans plafond arbitraire et l'approfondissement itératif jusqu'à complétude.

---

# Relais — 24 octobre 2026 (Résolution du blocage DeepSearch : keepalive SSE continu, parallélisation et suppression du goulot d'étranglement de traduction)

- Réalisé :
  - **Diagnostic complet de l'incident (« ça se lance, ça s'arrête et ne sort rien »)** :
    - En base de données, la génération allait en réalité jusqu'au bout (rapports de 20 453 et 13 345 caractères enregistrés dans Postgres), mais prenait plus de 4 minutes.
    - Cause racine 1 : `translate_deep_search_sources` traduisait séquentiellement 80 sources par blocs de 20 via l'IA, introduisant 2 minutes de silence complet sans aucune émission d'octets.
    - Cause racine 2 : absence de battement de cœur (keepalive) SSE. Les proxys et navigateurs (Chrome/Firefox) coupaient la connexion au bout de 60-90 secondes d'inactivité réseau apparente, déclenchant l'annulation côté frontend.
    - Cause racine 3 : sur le frontend, en cas de coupure réseau, la réinitialisation effaçait le message assistant en cours.
  - **Maintien de connexion actif et permanent (SSE Heartbeat / Keepalive)** (`backend/app/routers/messages.py`, `backend/app/deep_search.py`) :
    - Émission continue de commentaires `: keepalive\n\n` toutes les 2 secondes dès qu'aucune donnée n'est produite (pendant les recherches web, l'évaluation et l'attente du premier token LLM).
    - Maintien de la connexion TCP 100% active et vivante sans aucun risque de timeout proxy ou navigateur.
  - **Parallélisation des recherches web SearXNG** (`backend/app/deep_search.py`) :
    - Exécution concurrente des requêtes via `asyncio.Semaphore(3)` et `asyncio.gather` au lieu d'une boucle séquentielle. Temps de collecte divisé par 4 (de 35s à ~7s).
  - **Suppression du goulot d'étranglement de traduction** (`backend/app/providers.py`) :
    - Traduction ciblée sur les premières sources avec timeout strict de 15s (le modèle de synthèse final effectuant déjà la traduction directe dans la langue cible).
  - **Résilience frontend** (`frontend/components/chat-app.tsx`) :
    - Transmission fiable du texte de question depuis la modale et interrogation de secours si la réponse est en cours de finalisation côté serveur.
  - **Tests et validation** :
    - Suite de tests complète backend : **233/233 tests réussis à 100%**.
    - Typecheck TypeScript frontend (0 erreur) et compilation de production Next.js réussie.
- Fichiers modifiés :
  - `backend/app/routers/messages.py`, `backend/app/deep_search.py`, `backend/app/providers.py`, `frontend/components/chat-app.tsx`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite complète backend : 233/233 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/home/app/.local/bin:/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation Next.js : succès (`npm --prefix frontend run build`).
  - Vérification Git : absence de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch et observer le flux rapide et ininterrompu.

---

# Relais — 24 octobre 2026 (Décomposition DeepSearch en 5 axes et analyse contradictoire Thèse / Antithèse)

- Réalisé :
  - **Décomposition en sous-problèmes et confrontation Thèse / Antithèse** (`backend/app/providers.py`, `backend/app/context.py`) :
    - Intégration systématique d'une démarche contradictoire selon la nature de la question (faisabilité, controverse, arbitrage technique, viabilité opérationnelle) :
      - *Thèse* : conditions de faisabilité, gains attendus, cas d'usage nominaux, arguments favorables.
      - *Antithèse* : limites intrinsèques, dégradations qualitatives, goulots d'étranglement, failles, contre-exemples et retours d'expérience négatifs.
  - **Structuration rigoureuse en 5 axes d'investigation orthogonaux** (`backend/app/providers.py`) :
    1. *L'axe des entités et des concepts (Quoi / Qui)* : socle terminologique, définitions formelles, acronymes, composants, bibliothèques, acteurs clés, variantes linguistiques.
    2. *L'axe temporel et dynamique (Quand)* : état de l'art actuel, benchmarks récents, élimination de l'obsolescence, évolution historique et feuilles de route.
    3. *L'axe technique et causal (Comment / Pourquoi)* : fonctionnement interne, protocoles, flux de données, métriques objectives (latence, débit, consommation mémoire / VRAM, coût).
    4. *L'axe contradictoire et comparatif (La confrontation / Thèse vs Antithèse)* : casser le biais de confirmation des moteurs, recherche active de limites, failles, retours d'expérience négatifs et post-mortems en production.
    5. *L'axe du périmètre et des contraintes (Où / Dans quel cadre)* : environnement matériel/logiciel (OS, GPU/CPU, local vs cloud), contraintes d'échelle et cadre légal/normatif.
  - **Exemple de référence appliqué inclus dans le prompt** :
    - Cas canonique intégré (faisabilité de modèles de raisonnement 32B en local sur machine de bureau) illustrant les requêtes denses par axe.
  - **Alignement du prompt de suivi (`plan_deep_search_followup`) et du synthétiseur (`DEEP_SEARCH_PROMPT`)** :
    - Analyse des sources acquises avec détection des manques sur les 5 axes et tests d'hypothèses adverses.
    - Cadrage du grand rapport final pour structurer le développement selon ces 5 dimensions avec confrontation thèse/antithèse.
  - **Tests et validation** :
    - Actualisation de `backend/tests/test_providers.py` avec assertions vérifiant la présence des 5 axes, de la démarche thèse/antithèse et de l'exemple de référence.
    - Suite de tests complète backend : **233/233 tests réussis à 100%**.
    - Validation TypeScript frontend : **0 erreur**.
- Fichiers modifiés :
  - `backend/app/providers.py`, `backend/app/context.py`, `backend/tests/test_providers.py`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite complète backend : 233/233 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Healthcheck API conteneur : statut `ok`.
  - Vérification Git : absence de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : lancer une question de faisabilité ou d'arbitrage technologique dans le chat avec DeepSearch activé pour observer le découpage automatique en 5 axes et thèse / antithèse dans la modale de validation.

---

# Relais — 24 octobre 2026 (Modèle puissant de planification DeepSearch et prompt de décomposition intelligente)

- Réalisé :
  - **Modèle puissant dédié à la planification DeepSearch** (`backend/app/config.py`, `backend/app/providers.py`, `.env.example`) :
    - Configuration du modèle de planification DeepSearch : `deep_search_plan_model: str = "anthropic/claude-fable-5.1"` (flagship d'Anthropic pour les flux agentiques, le raisonnement poussé et l'investigation complexe).
    - Mécanisme de repli automatique robuste (`fallback_model`) : bascule transparente sur le modèle secondaire si le modèle principal est indisponible ou non crédité.
  - **Prompt expert de décomposition multidimensionnelle (Arbre de recherche)** (`backend/app/providers.py`) :
    - Découpage orthogonal en 4 piliers d'investigation clés :
      1. *Fondations & Taxonomie* (principes fondamentaux, architecture de référence, mécanismes exacts).
      2. *État de l'art & Chiffres récents* (avancées 2025-2026, benchmarks officiels, données quantitatives).
      3. *Analyse critique & Limites* (goulots d'étranglement, controverses, contre-hypothèses, risques).
      4. *Déploiement réel & Écosystème* (acteurs de pointe, retours d'expérience concrets en production).
    - Optimisation pour moteurs de recherche (SearXNG / Brave) : requêtes denses en mots-clés, élimination du verbiage conversationnel, respect strict des acronymes, noms propres et versions.
    - Équilibre multilingue rigoureux : 50% de requêtes en français et 50% en anglais technique pour capter les sources primaires internationales.
    - Amélioration symétrique du prompt de suivi (`plan_deep_search_followup`) pour cibler les zones d'ombre et chercher les publications sources directes.
  - **Mise à jour du schéma CLI Alembic** (`backend/app/cli.py`) :
    - Enregistrement de la révision `0009_add_deep_search_reports` dans les révisions valides de `prepare_schema`.
  - **Tests et validation** :
    - Ajout de `test_plan_deep_search_queries_uses_powerful_model_and_falls_back` dans `backend/tests/test_providers.py`.
    - Suite complète backend : **233/233 tests réussis à 100%**.
    - Typecheck TypeScript frontend : **0 erreur**.
- Fichiers modifiés :
  - `backend/app/config.py`, `backend/app/providers.py`, `backend/app/cli.py`, `.env.example`, `backend/tests/test_providers.py`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 233/233 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Vérification Git : absence de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch pour observer la décomposition stratégique de la question par Claude Fable 5.1 en axes d'investigation orthogonaux.

---



- Réalisé :
  - **Générateur de page HTML publication classe façon blog** (`backend/app/deep_search_html.py`) :
    - Rendu Markdown vers HTML riche, sécurisé et typographiquement soigné (Inter, Lora/Georgia, Fira Code).
    - Sommaire interactif dynamique (TOC) avec ancres normalisées (slugs ASCII sans accents).
    - Puces de citations de sources `[1]`, `[2]` liées directement aux cartes bibliographiques `#source-X`.
    - Encarts de blocs de code avec coloration syntaxique et bouton « Copier ».
    - En-tête éditorial avec badges, temps de lecture estimé, métadonnées et statut de vérification multi-sources.
    - Grille bibliographique complète avec domaines, résumés d'extraits et liens directs vers les sources originales.
    - Barre de navigation supérieure (bascule thème sombre/clair, copie complète, bouton « Imprimer / PDF » avec styles `@media print` dédiés).
  - **Modèle et persistance automatique des rapports DeepSearch** (`backend/app/models.py`, `backend/app/serializers.py`, `backend/migrations/versions/0009_add_deep_search_reports.py`) :
    - Table `DeepSearchReport` (`id`, `user_id`, `conversation_id`, `message_id`, `title`, `topic`, `markdown_content`, `html_content`, `sources`, `created_at`).
    - Enregistrement automatique du rapport lors de la finalisation d'un flux DeepSearch dans `send_message` (`backend/app/routers/messages.py`) et émission du `deep_search_report_id` dans l'événement SSE `done`.
  - **Endpoints API dédiés** (`backend/app/routers/messages.py`) :
    - `GET /api/deep-search/reports` : liste ordonnée des rapports de l'utilisateur avec compteurs de sources et dates.
    - `GET /api/deep-search/reports/{id}` : détail complet JSON avec contenu Markdown et HTML.
    - `GET /api/deep-search/reports/{id}/html` : consultation directe de la page HTML autonome (`Content-Type: text/html; charset=utf-8`) avec support de téléchargement direct (`?download=1`).
    - `DELETE /api/deep-search/reports/{id}` : suppression d'un rapport archivé.
    - `POST /api/deep-search/reports/from-message/{message_id}` : génération ou récupération à la volée d'un rapport pour les messages DeepSearch historiques.
  - **Lecteur dédié et archive dans la modale DeepSearch** (`frontend/components/deep-search-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/lib/api.ts`, `frontend/app/globals.css`) :
    - Onglets dans `DeepSearchModal` : « Nouveau plan » et « Mes Rapports » avec compteur en badge.
    - Vue liste « Mes Rapports » : barre de recherche instantanée par titre ou question, badges de sources, bouton d'ouverture dans le lecteur intégré, ouverture HTML plein écran, téléchargement `.html` et suppression.
    - **Mode Lecture Blog (« mode spécifique (type les blogs) »)** :
      - En-tête d'article soigné avec rappels des métadonnées et question posée.
      - Rendu Markdown haute qualité avec support KaTeX et GFM.
      - Cartes détaillées des sources web analysées avec extraits et liens sortants.
      - Barre d'actions rapides : « Page HTML plein écran », « Exporter .html », « Copier Markdown ».
    - Accès immédiat depuis le flux de discussion :
      - Bouton « Consulter le Grand Rapport HTML » intégré directement dans l'en-tête des sources des messages assistants DeepSearch.
      - Bouton « Mes Rapports » dans le bandeau compositeur DeepSearch et raccourci dans la barre latérale.
  - **Tests et validation** :
    - Tests unitaires du générateur HTML dans `backend/tests/test_deep_search.py` (`test_deep_search_html_generator`).
    - Tests d'intégration API dans `backend/tests/test_api.py` (persistance, détail, HTML autonome, téléchargement ASCII, suppression, conversion depuis message).
    - Suite de tests complète backend : **232/232 tests réussis à 100%**.
    - Typecheck TypeScript frontend (0 erreur) et compilation de production Next.js réussie.
    - Conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` redémarrés et sains (`healthy`).
- Fichiers modifiés / créés :
  - Créés : `backend/app/deep_search_html.py`, `backend/migrations/versions/0009_add_deep_search_reports.py`.
  - Modifiés : `backend/app/models.py`, `backend/app/serializers.py`, `backend/app/routers/messages.py`, `backend/tests/test_deep_search.py`, `backend/tests/test_api.py`, `frontend/components/deep-search-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/lib/api.ts`, `frontend/app/globals.css`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 232/232 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Statut des conteneurs : `healthy` (API 8001 et Web 3001 opérationnels).
  - Vérification Git : absence de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : lancer un DeepSearch ou ouvrir « Mes Rapports » dans la modale pour visualiser la page HTML en mode blog plein écran et dans le lecteur intégré.

---



- Réalisé :
  - **Endpoints de génération préalable du plan de recherche** (`backend/app/schemas.py`, `backend/app/routers/messages.py`) :
    - Création des schémas Pydantic `PlanDeepSearch` et `DeepSearchPlanResponse`.
    - Ajout du champ optionnel `deep_search_queries: list[str] | None` dans `SendMessage` avec assainissement et validation.
    - Ajout des endpoints `POST /api/conversations/{conversation_id}/deep-search/plan` (prenant en compte le contexte et résumé de la conversation) et `POST /api/deep-search/plan` (direct pour les nouveaux échanges).
    - Prise en charge des requêtes personnalisées dans `backend/app/deep_search.py` : `plan_node` adopte directement les requêtes validées par l'utilisateur lorsqu'elles sont fournies dans `SearchState`, tout en conservant la génération automatique en repli.
  - **Modale interactive de validation du plan dans l'interface utilisateur** (`frontend/components/deep-search-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`, `frontend/lib/api.ts`) :
    - Création du composant `DeepSearchModal` :
      - Rappel visuel de la question cible avec badge de statut.
      - Liste interactive des requêtes formulées : chaque angle dispose d'un numéro d'ordre, d'un champ de saisie directement éditable et d'un bouton de suppression.
      - Bouton « + Ajouter un angle ou une sous-requête » pour enrichir l'investigation manuellement.
      - Bouton « Régénérer le plan » pour solliciter l'IA sur une nouvelle décomposition stratégique.
      - Raccourcis clavier (Échap pour fermer, Entrée pour lancer).
    - Déclenchement automatique et ergonomique :
      - Lors de l'envoi d'un message avec DeepSearch activé, la modale s'ouvre pour permettre à l'utilisateur de relire et modifier le plan avant tout appel web.
      - Bouton d'accès rapide « Ajuster le plan » intégré au bandeau DeepSearch du compositeur.
      - Bouton de lancement explicite avec compteur de requêtes (« Lancer DeepSearch (X requêtes) »).
  - **Tests et validation** :
    - Ajout de tests dans `backend/tests/test_deep_search.py` (exécution de `execute_deep_search` avec `initial_queries` personnalisées de l'utilisateur).
    - Ajout de tests dans `backend/tests/test_api.py` (`test_deep_search_plan_endpoints_and_custom_queries` testant les endpoints de plan et l'exécution de requêtes custom sans régénération).
    - Suite complète backend : **231/231 tests réussis à 100%**.
    - Validation TypeScript frontend (0 erreur) et compilation de production Next.js réussie.
    - Conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` redémarrés et sains (`healthy`).
- Fichiers modifiés / créés :
  - Créés : `frontend/components/deep-search-modal.tsx`.
  - Modifiés : `backend/app/schemas.py`, `backend/app/deep_search.py`, `backend/app/routers/messages.py`, `backend/tests/test_deep_search.py`, `backend/tests/test_api.py`, `frontend/lib/api.ts`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 231/231 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Statut des conteneurs : `healthy` (API 8001 et Web 3001 opérationnels).
  - Vérification Git : absence de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : activer le mode DeepSearch, saisir un sujet et constater l'ouverture de la modale interactive pour ajuster les angles d'exploration avant lancement.

---

# Relais — 24 octobre 2026 (refonte DeepSearch en agent par graphe d'états StateGraph itératif)

- Réalisé :
  - **Refonte architecturale de DeepSearch en agent par graphe d'états (StateGraph)** (`backend/app/deep_search.py`, `backend/app/routers/messages.py`, `backend/app/context.py`) :
    - Implémentation d'un moteur `StateGraph` asynchrone natif, léger et typé (`SearchState`, `EvaluationOutput`, `START`, `END`, transitions conditionnelles).
    - Mise en œuvre des 5 étapes fondamentales de recherche approfondie :
      1. **Planification & Décomposition (`plan_node`)** : déconstruction du sujet en sous-questions, identification des entités clés, du cadre temporel, des contraintes et des points aveugles. Formule l'arbre de recherche initial (requêtes locales + requêtes internationales).
      2. **Génération dynamique & Web Retrieval (`search_node`)** : exécution ciblée via SearXNG / Brave, filtrage sémantique, déduplication et fusion intelligente via `merge_web_sources` (jusqu'à 100 sources).
      3. **Mémoire de travail & Scratchpad (`SearchState.findings`)** : extraction continue des faits saillants, chiffres et données clés pour constituer un carnet de déductions factuelles vérifiées (Context Scratchpad).
      4. **Raisonnement itératif & Re-thinking (`evaluate_node`)** : analyse critique des faits réunis, détection de contradictions ou zones d'ombres, évaluation de complétude (`is_sufficient: bool`) et formulation de 1 à 3 requêtes très précises pour combler les manques ou trouver la source primaire.
      5. **Routage conditionnel & Synthèse sourcée (`should_continue`, `synthesize_node`)** : boucle de rétroaction vers `search` tant que non suffisant et dans la limite des quotas, puis traduction multilingue et transmission au modèle de chat du rapport d'analyse complet avec ancrage strict (`[1]`, `[2]`) et injection du scratchpad de travail.
  - **Intégration fluide au flux SSE** :
    - Émission temps réel des statuts d'investigation (`Planification`, `Exploration`, `Analyse et croisement`, `Approfondissement`, `Traduction`, `Synthèse globale`).
    - Injection de la mémoire de travail (`findings`) dans `build_context(..., findings=...)`.
  - **Tests et validation** :
    - Création de `backend/tests/test_deep_search.py` : tests du schéma d'état, routage conditionnel `should_continue`, compilation et exécution du StateGraph, pipeline complet asynchrone.
    - Suite complète backend : **229/229 tests réussis à 100%**.
    - Validation TypeScript frontend (0 erreur).
    - Conteneur `tchataiperso-clair-api-1` redémarré et sain (`healthy`).
- Fichiers modifiés / créés :
  - Créés : `backend/app/deep_search.py`, `backend/tests/test_deep_search.py`.
  - Modifiés : `backend/app/routers/messages.py`, `backend/app/context.py`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 229/229 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Statut conteneur API : sain (`healthy`).
  - Vérification Git : absence de fuite de clé ou secret.
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch complexe dans l'interface pour observer la décomposition, les vagues itératives d'approfondissement et le grand rapport d'analyse sourcé.

---

# Relais — 24 octobre 2026 (augmentation de la limite DeepSearch à 100 sources)

- Réalisé :
  - **Passage du plafond de sources DeepSearch de 40 à 100 sources uniques** :
    - Mise à jour du pipeline SSE de messages (`backend/app/routers/messages.py`) : arrêt de la boucle d'exploration et d'approfondissement porté à 100 sources (`len(sources) >= 100`, `sources < 100`).
    - Mise à jour de la déduplication et fusion (`backend/app/providers.py`) : `merge_web_sources(..., max_total: int = 100)`.
    - Planification étendue des sous-requêtes multilingues :
      - Pistes initiales portées de 6 à 8 requêtes (`max_queries: int = 8` dans `plan_deep_search_queries`).
      - Requêtes d'approfondissement complémentaires portées de 3 à 4 requêtes (`max_queries: int = 4` dans `plan_deep_search_followup`), analysant jusqu'à 30 sources déjà collectées.
    - Élargissement du budget contextuel des sources injectées (`backend/app/context.py`) :
      - `source_limit` augmenté de 40 000 à 100 000 caractères pour accueillir l'ensemble des 100 sources sans troncation prématurée.
      - Directives du prompt DeepSearch actualisées pour exploiter jusqu'à 100 sites en langues locale et étrangère.
      - Budget de référence ajusté pour le mode DeepSearch.
  - **Interface utilisateur** (`frontend/components/chat-app.tsx`) :
    - Libellé du mode DeepSearch actualisé : « Mode DeepSearch · Exploration internationale jusqu’à 100 sites via SearXNG, traduction et grand rapport d’analyse approfondi ».
  - **Tests et validation** :
    - Mise à jour de `backend/tests/test_providers.py` (test du plafond de fusion porté à 100 sites sur 120 générés).
    - Mise à jour de `backend/tests/test_context.py` (test d'injection et respect du budget de contexte avec 100 sources et vérification de `EXTRAIT_100`).
    - Suite complète backend : **225/225 tests réussis à 100%**.
    - Validation TypeScript frontend (0 erreur) et compilation de production Next.js réussie.
    - Conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` redémarrés et sains.
- Fichiers modifiés :
  - `backend/app/routers/messages.py`, `backend/app/providers.py`, `backend/app/context.py`.
  - `backend/tests/test_context.py`, `backend/tests/test_providers.py`.
  - `frontend/components/chat-app.tsx`.
  - `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 225/225 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /tmp/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Redémarrage des conteneurs : statut sain (`healthy`).
  - Vérification Git : absence totale de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch dans l'interface et observer la collecte jusqu'à 100 sources.

---

# Relais — 23 octobre 2026 (récupération dynamique des modèles OpenRouter, filtrage chat, calcul des tarifs et modale de sélection)

- Réalisé :
  - **Récupération dynamique des modèles OpenRouter & filtrage chat spécialisé** (`backend/app/openrouter.py`, `backend/app/config.py`, `backend/app/routers/system.py`, `backend/app/deps.py`) :
    - Création du module `backend/app/openrouter.py` pour interroger l'API OpenRouter (`/models`) en direct avec httpx, muni d'un cache mémoire (TTL 15 minutes) et d'un repli (fallback) transparent vers `LLM_MODELS` en cas d'indisponibilité ou en mode démo.
    - Filtrage intelligent `is_chat_model` excluant :
      - Les files de traitement asynchrones batch (`:batch`).
      - Les générateurs de son, musique et audio (Lyria, GPT-Audio, ElevenLabs, Whisper, Suno, etc.).
      - Les modèles purement vidéo ou embeddings / rerankers.
      - Préservation stricte des modèles de chat et raisonnement phares (GPT-6 Astra, GPT-6 Luna, GPT-6.1 Sol, Claude Opus/Sonnet/Haiku 5.5, Gemini 3.8 Flash, DeepSeek V4.1 Flash, Mistral Large 4, etc. avec 390 modèles éligibles).
    - Calcul et normalisation des tarifs en dollars par million de tokens (`prompt_price_1m`, `completion_price_1m`, `input_cache_read_price_1m`), longueur de contexte, support de la vision et du raisonnement.
    - Ajout de l'endpoint FastAPI `GET /api/models?refresh={true|false}` permettant l'actualisation à la demande, en plus de l'intégration dans `/api/config`.
    - Résilience de `check_model` dans `deps.py` validant les modèles dynamiques OpenRouter tout en préservant le fallback `configured_models`.
  - **Modale complète de sélection des modèles & refonte du sélecteur en topbar** (`frontend/components/model-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`, `frontend/lib/api.ts`) :
    - Remplacement du simple `<select>` HTML par un bouton interactif moderne `.model-selector-btn` affichant : pastille de statut, nom du modèle actif, badge `Vision` (si compatible image) et badge de tarif au million de tokens (ex: `Gratuit`, `$0.15/M`), ouvrant la modale au clic.
    - Création de `ModelModal` :
      - Recherche instantanée par nom, ID (ex: `astra`, `gpt-6`, `opus`), fournisseur ou description.
      - Onglets de filtrage rapide : `Tous`, `👁️ Vision`, `🎁 Gratuits`, `🧠 Raisonnement`, et fournisseurs (`OpenAI`, `Anthropic`, `Google`, `DeepSeek`, `Mistral`, `Meta Llama`, `xAI`, `Qwen`, `Kimi`).
      - Tri multicritères : Recommandés & populaires, prix croissant, prix décroissant, fenêtre de contexte (tokens max), nom alphabétique.
      - Cartes détaillées de modèles : badge fournisseur coloré, ID technique en code pill, badges de capacités (Vision, Raisonnement, Contexte en tokens k/M), bloc tarifaire lisible (Prompt / Complétion / Cache), extrait de description et bouton de sélection direct.
      - Pagination fluide (blocs de 60 modèles) pour une réactivité maximale à l'affichage.
      - Bouton « Actualiser » dans l'en-tête pour forcer la mise à jour depuis OpenRouter.
  - **Tests et validation** :
    - Création de `backend/tests/test_openrouter.py` (tests du filtrage, formatage des prix, mise en cache et endpoint `/api/models`).
    - Suite complète backend : **225/225 tests réussis à 100%**.
    - Validation TypeScript frontend (0 erreur) et compilation de production Next.js réussie.
    - Conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` redémarrés et sains (200 OK).
- Fichiers modifiés / créés :
  - Créés : `backend/app/openrouter.py`, `backend/tests/test_openrouter.py`, `frontend/components/model-modal.tsx`.
  - Modifiés : `backend/app/config.py`, `backend/app/routers/system.py`, `backend/app/deps.py`, `frontend/lib/api.ts`, `frontend/components/chat-app.tsx`, `frontend/app/globals.css`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 225/225 tests passés avec succès (`docker exec tchataiperso-clair-api-1 pytest /app/tests /tmp/test_openrouter.py`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Test en direct de l'API `/api/config` et `/api/models?refresh=true` : 390 modèles filtrés, présence de `openai/gpt-6-astra` avec tarifs calculés et context length.
  - Test en direct frontend dans le conteneur web : 200 OK.
  - Vérification Git : absence de fuite de secret.
- Problèmes connus : aucun.
- Prochaine action : cliquer sur le bouton de modèle dans la barre supérieure du chat pour explorer la modale, rechercher un modèle ou filtrer par prix/fournisseur.

---

# Relais — 23 octobre 2026 (sorties longues type grand rapport pour le mode DeepSearch)

- Réalisé :
  - **Refonte des directives du mode DeepSearch en format « Grand Rapport d’analyse »** (`backend/app/context.py`) :
    - Remplacement de la simple consigne de « synthèse » par un cadrage éditorial d'enquête et de recherche approfondie : titre principal explicite (`#`), résumé exécutif / cadrage stratégique, chapitres thématiques détaillés (`##` et `###`) avec paragraphes complets, tableaux comparatifs et chronologies en Markdown, analyse critique avec confrontation des consensus et controverses, limites documentaires et perspectives d'avenir.
    - Consigne explicite d'exhaustivité et de non-abréviation des explications pour exploiter pleinement les données des sources web.
    - Élargissement de la longueur des extraits sources injectés (`_format_source`) de 700 à 850 caractères, et hausse de la fenêtre de traduction des sources (`translate_deep_search_sources`) de 600 à 800 caractères pour fournir un matériau documentaire plus riche au modèle.
  - **Rehaussement du plafond de génération de tokens pour DeepSearch** (`backend/app/config.py`, `backend/app/providers.py`, `compose.yaml`, `.env`) :
    - Introduction du paramètre configurable `deep_search_max_tokens: int = 12288` dans `Settings` avec validation Pydantic (1 à 100 000 tokens).
    - Routage dynamique dans `stream_chat` appliquant `max_tokens = max(settings.llm_max_tokens, getattr(settings, "deep_search_max_tokens", 12288))` lorsque `is_deep_search` est actif, permettant la génération de rapports denses de 10 à 15 pages.
    - Transmission de `DEEP_SEARCH_MAX_TOKENS` via `compose.yaml` et `.env`.
    - Ajustement du libellé de statut SSE : « DeepSearch · Synthèse globale et rapport approfondi (N sources)… ».
  - **Actualisation des libellés UI dans le frontend** (`frontend/components/chat-app.tsx`) :
    - En-tête des sources : « Rapport DeepSearch · N sources croisées ».
    - Bandeau et infobulle du mode DeepSearch : mise en avant de la production d'un grand rapport d'analyse approfondi.
  - **Tests et validation** :
    - Ajout du test unitaire `test_chat_stream_raises_max_tokens_in_deep_search_mode` dans `backend/tests/test_providers.py`.
    - Suite de tests backend complète : **221/221 tests réussis à 100%**.
    - Validation TypeScript frontend (0 erreur) et build de production Next.js validé.
    - Conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` redémarrés et sains (healthchecks 200 OK).
- Fichiers modifiés :
  - `backend/app/context.py`, `backend/app/config.py`, `backend/app/providers.py`, `backend/app/routers/messages.py`.
  - `compose.yaml`, `.env`.
  - `backend/tests/test_providers.py`.
  - `frontend/components/chat-app.tsx`.
  - `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests complète backend : 221/221 tests passés avec succès (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /app/tests`).
  - Vérification TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Redémarrage des conteneurs `clair-api` et `clair-web` : santé validée, `/api/health` 200 OK.
  - Vérification Git : absence de fuite de clé ou secret.
- Problèmes connus : aucun.
- Prochaine action : lancer une recherche DeepSearch dans l'interface et observer le rapport d'analyse complet et détaillé généré.

---

# Relais — 23 octobre 2026 (refactorisation modulaire FastAPI : découpage de main.py en APIRouter)

- Réalisé :
  - **Refactorisation et découpage complet de `main.py` (de 1 503 lignes à 128 lignes)** :
    - Extraction des sérialiseurs et helpers JSON dans `backend/app/serializers.py` (`conversation_json`, `message_json`, `attachment_json`, `generated_image_json`, `blog_json`, `blog_post_json`, `skill_json`, `user_json`, `stamp`, `sse`, `extract_mentioned_skills`).
    - Centralisation des dépendances et injections FastAPI dans `backend/app/deps.py` (`get_settings`, `get_sessions`, `get_db`, `get_upload_dir`, `current_user`, `require_admin`, `get_conversation`, `check_model`, `claim`, `get_lock`).
    - Création du module `backend/app/routers/` avec 10 routeurs spécialisés :
      - `system.py` : `/api/health`, `/api/config`.
      - `auth.py` : `/api/auth/login`, `/api/auth/session`, `/api/auth/logout`, `/api/auth/register`.
      - `admin.py` : `/api/admin/users`, `/api/admin/invitations`, `/api/admin/users/{user_id}`.
      - `conversations.py` : CRUD conversations, filtrage/recherche, classification globale et unitaire.
      - `messages.py` : `/api/conversations/{id}/messages` (pipeline complet SSE, extraction URLs web, finances EODHD/Yahoo, DeepSearch, web search SearXNG/Brave, synthèses, génération Canvas Code).
      - `skills.py` : CRUD compétences, `/api/skills/improve`, compétences actives par conversation.
      - `memories.py` : CRUD souvenirs utilisateurs.
      - `attachments.py` : upload fichiers, extraction URL/YouTube, consultation extractions et téléchargement.
      - `images.py` : Studio d'images IA multi-modèles (Ideogram, Google Imagen, FLUX, OpenAI), amélioration de prompts avec Luna, génération dans les conversations.
      - `blogs.py` : CRUD blogs d'actualités, actualisation et suppression d'éditions.
    - Simplification drastique de `backend/app/main.py` : initialisation de `FastAPI`, gestion du `lifespan` (schéma, intégrité admin, migrations), middlewares CORS et origines, et enregistrement unifié via `app.include_router()`.
    - Préservation d'exports de compatibilité dans `main.py` pour éviter toute régression sur les imports externes.
- Fichiers modifiés / créés :
  - Créés : `backend/app/serializers.py`, `backend/app/deps.py`, `backend/app/routers/__init__.py`, `backend/app/routers/system.py`, `backend/app/routers/auth.py`, `backend/app/routers/admin.py`, `backend/app/routers/conversations.py`, `backend/app/routers/messages.py`, `backend/app/routers/skills.py`, `backend/app/routers/memories.py`, `backend/app/routers/attachments.py`, `backend/app/routers/images.py`, `backend/app/routers/blogs.py`.
  - Modifiés : `backend/app/main.py`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/tests/*.py`).
  - Suite de tests backend complète : **220/220 tests réussis à 100%** (`docker exec tchataiperso-clair-api-1 env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=/app pytest /app/tests`).
  - Redémarrage à chaud du conteneur API `tchataiperso-clair-api-1` validé : logs sains, uvicorn actif, endpoints `/api/health` et `/api/config` opérationnels (200 OK).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
- Problèmes connus : aucun.
- Prochaine action : continuer le développement sur une base modulaire et lisible.

---

# Relais — 23 octobre 2026 (correction de l'erreur d'hydratation HTML <button> imbriqué dans BlogModal)

- Réalisé :
  - **Correction de la violation HTML / erreur d'hydratation React dans `BlogModal`** :
    - Résolution de l'erreur `In HTML, <button> cannot be a descendant of <button>. This will cause a hydration error.` signalée dans les logs de `clair-web-1`.
    - Dans `frontend/components/blog-modal.tsx`, le bouton de suppression `<button className="blog-item-delete-btn">` était imbriqué à l'intérieur du bouton de sélection du blog `<button className="blog-nav-item">`.
    - Désimbrication des boutons : les deux boutons sont désormais frères directs au sein de `<li className="blog-nav-item-row">`.
    - Ajustement des styles CSS dans `frontend/app/globals.css` :
      - `.blog-nav-item-row` positionné en `relative`.
      - `.blog-item-delete-btn` positionné en `absolute` en haut à droite avec `z-index: 2` et opacité contrôlée sur hover de la ligne.
      - `.blog-nav-item-top` doté d'un `padding-right: 22px` pour éviter tout chevauchement avec le bouton corbeille sur les titres longs.
  - **Audit global de l'arborescence frontend** :
    - Analyse AST complète via l'API TypeScript sur l'ensemble des fichiers `.tsx` du projet pour vérifier l'absence d'autres éléments interactifs illégaux imbriqués (`button` dans `button`, `a` dans `a`, `button` dans `a`, `a` dans `button`). Résultat : 0 autre anomalie détectée.
- Fichiers modifiés :
  - `frontend/components/blog-modal.tsx`, `frontend/app/globals.css`, `HANDOFF.md`.
- Vérifications exécutées :
  - Analyse AST TypeScript JSX : 0 bouton ou lien imbriqué sur tout le frontend.
  - Vérification des types frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Hot reload dans le conteneur en direct `tchataiperso-clair-web-1` : recompilation immédiate validée (`✓ Compiled in 380ms`).
- Problèmes connus : aucun.
- Prochaine action : ouvrir la modale « Mes Blogs d’actualités » dans le navigateur et constater la disparition de l'erreur d'hydratation dans les logs.

---

# Relais — 23 octobre 2026 (analyse et assainissement des logs SearXNG / Web Search)

- Réalisé :
  - **Diagnostic des logs SearXNG** :
    - Confirmation que les requêtes web aboutissent bien (statut 200 OK côté API, plus de 130 résultats agrégés sur la recherche Elden Ring).
    - Identification de l'erreur `ERROR:searx.botdetection: X-Forwarded-For nor X-Real-IP header is set!` liée à l'absence d'en-tête client transmis par httpx vers SearXNG.
    - Identification des warnings SearXNG : SearXNG étant un méta-moteur interrogeant 50 moteurs en parallèle, plusieurs moteurs externes (Google, Qwant, DuckDuckGo) bloquent périodiquement les scrapers (CAPTCHA/403) et sont temporairement suspendus sans impacter les autres (Bing, Yahoo, Seznam, Yep, etc.). Certains moteurs étaient par ailleurs définitivement en erreur (AndiSearch avec token obligatoire, Gabanza avec certificat SSL expiré, Sogou avec AttributeError, Tusksearch en 401).
  - **Corrections et optimisations** :
    - Ajout de l'en-tête `X-Forwarded-For: 127.0.0.1` dans `backend/app/providers.py` et `backend/app/blog.py` lors des requêtes vers SearXNG, éliminant totalement l'erreur de botdetection.
    - Désactivation des moteurs obsolètes / cassés dans `searxng/settings.yml` (`andisearch`, `fastbot`, `fireball`, `gabanza`, `resulthunter`, `searchmysite`, `sogou`, `tusksearch`, `wolframalpha`).
    - Redémarrage des conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-searxng-1`.
- Fichiers modifiés :
  - `backend/app/providers.py`, `backend/app/blog.py`, `searxng/settings.yml`, `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/tests/*.py`).
  - Test en direct de recherche SearXNG depuis l'API sur `bugs invocations elden ring convergence 3.0.3` : 3 sources extraites avec succès en sous-seconde.
  - Inspection des logs `docker logs tchataiperso-clair-searxng-1` : disparition complète de l'erreur `searx.botdetection` et des erreurs sur les moteurs désactivés.
- Problèmes connus : aucun.
- Prochaine action : continuer les recherches web dans le chat.

---

# Relais — 23 octobre 2026 (génération d'images multi-modèles : Ideogram, Google Imagen & OpenRouter)

- Réalisé :
  - **Prise en charge multi-modèles de génération d'images** (`backend/app/config.py`, `backend/app/providers.py`, `backend/app/schemas.py`, `backend/app/main.py`) :
    - Définition des modèles de génération d'images supportés (`DEFAULT_IMAGE_MODELS`) : Ideogram v2 (sélection auto), Google Gemini 3 Pro Image (Imagen 3), Google Gemini 3.1 Flash Image, Google Gemini 2.5 Flash Image, FLUX 3 Image & Klein (Black Forest Labs), OpenAI GPT Image 2.5 (Sunburst & Flare), ByteDance Seedream 5.0 Flash, Recraft v4.1 Flash.
    - Routage automatique dans `providers.generate_image` :
      - Si `model == "ideogram"` : appel direct vers l'API Ideogram (`/v2/image/generate/auto`) avec `IDEOGRAM_API_KEY`.
      - Si `model != "ideogram"` : appel vers l'endpoint Images d'OpenRouter (`/images`) avec `LLM_API_KEY`, décodage `b64_json` ou flux HTTP `url`, et détection sécurisée du format d'image.
    - Ajout du champ `model` dans le schéma `CreateImage` avec assainissement.
    - Exposition dynamique dans `/api/config` des `image_models` filtrés selon les clés API configurées (`has_ideogram`, `has_openrouter`), et activation de la fonctionnalité `image_generation` si au moins un fournisseur est actif.
    - Préfixage des fichiers sauvegardés selon le modèle sélectionné (ex: `ideogram-xxxx`, `gemini-3-pro-image-xxxx`, `flux-3-image-xxxx`).
  - **Interface utilisateur du Studio Image** (`frontend/components/image-studio-modal.tsx`, `frontend/app/globals.css`, `frontend/lib/api.ts`) :
    - Ajout du type `ImageModel` et mise à jour de `Config` dans `frontend/lib/api.ts`.
    - Sélecteur de modèle dédié pour la génération d'images affichant le badge fournisseur (Ideogram API ou OpenRouter API).
    - Transmission du modèle sélectionné (`generationModel`) lors de la génération.
    - Bouton de génération dynamique affichant le modèle actif (« Générer avec Google Gemini 3 Pro Image », « Générer avec Ideogram v2 », etc.).
    - Entête actualisé en « STUDIO CRÉATIF · MULTI-MODÈLES ».
  - **Déploiement et tests** :
    - 220/220 tests unitaires et d'intégration validés (avec tests spécifiques d'image OpenRouter en base64 et tests d'API multi-modèles).
    - Validation TypeScript frontend (0 erreur) et compilation de production Next.js réussie.
    - Conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` redémarrés et sains.
    - Tests directs en conditions réelles validés avec succès sur `google/gemini-2.5-flash-image` (1.56 Mo PNG) et `google/gemini-3-pro-image` (1.82 Mo PNG en format 16:9).
- Fichiers modifiés :
  - `backend/app/config.py`, `backend/app/schemas.py`, `backend/app/providers.py`, `backend/app/main.py`.
  - `backend/tests/test_api.py`, `backend/tests/test_providers.py`.
  - `frontend/lib/api.ts`, `frontend/components/image-studio-modal.tsx`, `frontend/app/globals.css`.
  - `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/tests/*.py`).
  - Suite complète backend : 220/220 tests passés avec succès (`docker exec ... pytest /home/app/tests`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Test en direct avec Google Gemini 2.5 Flash Image : statut 200 OK, image PNG de 1 565 198 octets générée.
  - Test en direct avec Google Gemini 3 Pro Image (Imagen 3) : statut 200 OK, image PNG de 1 821 284 octets générée en 16:9.
  - Absence totale de secrets/clés API dans le diff Git.
- Problèmes connus : aucun.
- Prochaine action : ouvrir le Studio Image, sélectionner dans la liste déroulante un modèle Google Imagen (ou FLUX, OpenAI, Ideogram), entrer un prompt et générer votre création.

---

# Relais — 23 octobre 2026 (Ideogram auto selection /v2/image/generate/auto & prompt négatif)

- Réalisé :
  - **Migration vers la sélection automatique de modèle Ideogram** (`backend/app/providers.py`) :
    - Remplacement de l'endpoint vers `https://api.ideogram.ai/v2/image/generate/auto` (spécification officielle Ideogram pour la sélection automatique du meilleur modèle selon le contenu du prompt).
    - Transmission de `prompt`, `aspect_ratio` et du paramètre optionnel `negative_prompt`.
  - **Prise en charge du prompt négatif (éléments à exclure)** :
    - Ajout du champ `negative_prompt: str | None = Field(default=None, max_length=2000)` dans `CreateImage` et `ImproveImagePrompt` (`backend/app/schemas.py`).
    - Prise en charge dans les endpoints `/api/images`, `/api/conversations/{id}/images` et `/api/images/improve` (`backend/app/main.py`).
    - Intégration de la consigne d'exclusion dans `improve_image_prompt` (`backend/app/providers.py`) afin que GPT-6 Luna éloigne également la description positive des éléments rejetés.
    - Transmission directe de `negative_prompt` au générateur Ideogram lors de la génération.
  - **Interface utilisateur du Studio Image** (`frontend/components/image-studio-modal.tsx`, `frontend/app/globals.css`) :
    - Ajout d'une section dédiée ambrée « Prompt négatif (ce qu'on ne veut pas) » avec icône d'interdiction `Ban`, champ de saisie libre et bouton d'effacement.
    - Suggestions rapides d'exclusions cliquables : `flou & basse qualité`, `texte & filigrane`, `mauvaise anatomie`, `membres déformés`, `visage asymétrique`, `bruit excessif`, `grain lourd`, `couleurs ternes`.
    - Transmission de `negative_prompt` lors de la génération et de l'amélioration de prompt.
  - **Déploiement et tests** :
    - Fichiers backend synchronisés et conteneurs redémarrés.
    - Validation directe en conditions réelles de l'endpoint Ideogram `/v2/image/generate/auto` (avec `dry_run=true`, réponse 200 OK avec devis tarifaire validé).
    - 218/218 tests unitaires et d'intégration validés.
- Fichiers modifiés :
  - `backend/app/schemas.py`, `backend/app/providers.py`, `backend/app/main.py`.
  - `backend/tests/test_providers.py`, `backend/tests/test_api.py`.
  - `frontend/components/image-studio-modal.tsx`, `frontend/app/globals.css`.
  - `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python : 0 erreur (`python3 -m py_compile backend/app/*.py backend/tests/*.py`).
  - Suite complète backend : 218/218 tests passés avec succès (`docker exec ... pytest tests/`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Test en direct avec la clé Ideogram sur `https://api.ideogram.ai/v2/image/generate/auto?dry_run=true` : statut 200 OK (`price_quote`).
  - Vérification de l'absence totale de secrets/clés API dans le diff Git.
- Problèmes connus : aucun.
- Prochaine action : ouvrir le Studio Image, saisir un sujet et des éléments indésirables dans le « Prompt négatif », puis générer l'image avec la sélection automatique Ideogram.

---

# Relais — 23 octobre 2026 (mots-clés de style & guidage d'amélioration d'image avec GPT-6 Luna)

- Réalisé :
  - **Prise en charge des mots-clés de style & d'ambiance dans l'amélioration de prompt d'image** :
    - Mise à jour du schéma backend `ImproveImagePrompt` (`backend/app/schemas.py`) avec le champ facultatif `style_keywords: str | None = Field(default=None, max_length=500)` et assainissement.
    - Transmission de `style_keywords` dans l'endpoint `/api/images/improve` (`backend/app/main.py`).
    - Intégration prioritaire dans les directives système de `providers.improve_image_prompt` (`backend/app/providers.py`) : directive majeure exigeant d'incarner fidèlement les mots-clés (ex: familial pour une affiche, vaporeux, terrifiant, rouge...) dans la composition, les dominantes de couleur, la lumière et l'émotion de la scène.
    - Ajout de tests unitaires dédiés (`backend/tests/test_providers.py`, `backend/tests/test_api.py`) validant l'intégration des mots-clés et leur transmission.
  - **Interface utilisateur dédiée aux mots-clés de style dans le Studio Image** (`frontend/components/image-studio-modal.tsx`, `frontend/app/globals.css`) :
    - Ajout d'une section stylisée « Mots-clés de style & ambiance (guidage IA) » avec champ de saisie libre (`placeholder` suggérant les exemples demandés).
    - Bouton rapide d'effacement (« Effacer ») lorsque du texte est saisi.
    - Badges cliquables / suggestions rapides : `familial (pour une affiche)`, `vaporeux`, `terrifiant`, `rouge`, `cinématique`, `sombre & dramatique`, `lumineux & solaire`, `rétrofuturiste`, `cyberpunk`, `aquarelle`, `pastel doux`, `minimaliste`, `vintage 70s`.
    - Clic interactif pour activer/désactiver ou ajouter/retirer un mot-clé de la liste séparée par des virgules.
    - Envoi synchronisé de `style_keywords` lors du clic sur « Améliorer le prompt ».
  - **Déploiement et tests** :
    - Build de production Next.js regénéré et déployé dans `tchataiperso-clair-web-1`.
    - Fichiers backend synchronisés et conteneurs redémarrés.
    - Test direct en conditions réelles avec GPT-6 Luna : validation de l'intégration simultanée de « familial (pour une affiche) », « vaporeux » et « rouge » dans une description riche de 1492 caractères.
- Fichiers modifiés :
  - `backend/app/schemas.py`, `backend/app/providers.py`, `backend/app/main.py`.
  - `backend/tests/test_providers.py`, `backend/tests/test_api.py`.
  - `frontend/components/image-studio-modal.tsx`, `frontend/app/globals.css`.
  - `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python sans erreur (`python3 -m py_compile backend/app/*.py backend/tests/*.py`).
  - Suite complète backend : 218/218 tests passés avec succès (`docker exec ... pytest tests/`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Test en direct avec GPT-6 Luna combinant « groupe d'aventuriers dans une forêt » avec les mots-clés `familial (pour une affiche), vaporeux, rouge` (1492 caractères, directives respectées).
  - Absence de tout secret ou clé API dans le diff Git.
- Problèmes connus : aucun.
- Prochaine action : ouvrir le Studio Image, saisir un sujet ainsi que des mots-clés de style (ou cliquer sur les badges rapides), puis cliquer sur « Améliorer le prompt » pour visualiser la composition générée par GPT-6 Luna.

---

# Relais — 23 octobre 2026 (amélioration des prompts studio image & modèle GPT-6 Luna)

- Réalisé :
  - **Refonte de l'amélioration de prompt dans le Studio Image** (`backend/app/providers.py`) :
    - Élaboration de directives système expertes pour générer des prompts complets, denses et exhaustifs (100 à 250 mots) décrivant systématiquement : sujet principal et matières, environnement et arrière-plan immersifs, cadrage cinématographique et composition, éclairage volumétrique et ombres, palette de couleurs et textures, style artistique et rendu technique (photographique 35mm f/1.4, 3D Octane / Unreal Engine 5, piqué 8k), ainsi que la préservation stricte entre guillemets du texte souhaité.
    - Hausse du plafond de complétion (`max_tokens: 1400`) et ajustement de la température (`0.7`) pour une description visuelle riche et vivante.
    - Nettoyage automatique des préambules (« Voici le prompt... ») et balises superflues.
    - Mécanisme de secours (fallback) automatique vers `default_model` en cas d'erreur statut (400, 404, 422) sur le modèle sélectionné.
  - **Intégration du modèle dédié GPT-6 Luna (`openai/gpt-6-luna`)** :
    - Ajout du paramètre `image_prompt_model: str = "openai/gpt-6-luna"` dans `backend/app/config.py`, `.env` et `compose.yaml`.
    - Support du modèle configurable dans `ImproveImagePrompt` (`backend/app/schemas.py`) et transmission dynamique via `backend/app/main.py`.
    - Exposition de `image_prompt_model` dans l'endpoint `/api/config`.
  - **Sélecteur de modèle et expérience utilisateur dans le Studio Image** (`frontend/components/image-studio-modal.tsx`, `frontend/app/globals.css`, `frontend/lib/api.ts`) :
    - Intégration d'un sélecteur de modèle dédié à côté du bouton « Améliorer le prompt », pré-sélectionnant automatiquement GPT-6 Luna tout en permettant de basculer vers un autre modèle de la configuration.
    - Bulle d'aide contextualisée indiquant le modèle actif utilisé pour l'amélioration.
  - **Déploiement et tests** :
    - Validation directe en conditions réelles avec `openai/gpt-6-luna` sur OpenRouter via `improve_image_prompt` (génération d'un prompt complet et soigné de 1468 caractères).
    - Fichiers backend synchronisés et conteneurs `tchataiperso-clair-api-1` et `tchataiperso-clair-web-1` mis à jour et sains.
- Fichiers modifiés :
  - `backend/app/config.py`, `backend/app/main.py`, `backend/app/providers.py`, `backend/app/schemas.py`.
  - `compose.yaml`, `.env`.
  - `frontend/components/image-studio-modal.tsx`, `frontend/lib/api.ts`, `frontend/app/globals.css`.
  - `HANDOFF.md`.
- Vérifications exécutées :
  - Compilation Python sans erreur (`python3 -m py_compile backend/app/*.py backend/tests/*.py`).
  - Suite complète backend : 217/217 tests passés avec succès (`docker exec ... pytest tests/`).
  - Validation TypeScript frontend : 0 erreur (`npm --prefix frontend run typecheck`).
  - Compilation de production Next.js : succès (`npm --prefix frontend run build`).
  - Test en direct de l'API avec GPT-6 Luna : validation de l'amélioration d'un prompt court (« un petit robot jardinier » -> description visuelle complète de 1468 caractères).
  - Vérification de l'absence totale de secrets/clés API dans le diff Git.
- Problèmes connus : aucun.
- Prochaine action : ouvrir le Studio Image, saisir un sujet et cliquer sur « Améliorer le prompt » pour constater le prompt complet généré par GPT-6 Luna.

---

# Relais — 22 octobre 2026 (correction mode finances, Air Liquide, EODHD & Yahoo Finance)

- Réalisé :
  - **Correction de la détection et recherche d'entités financières** (`backend/app/finance.py`, `backend/app/main.py`, `backend/app/providers.py`) :
    - Élargissement des variantes de recherche (`query_variants`) : quand une requête contient du bruit (ex. « en détail air liquide »), recherche automatique par fenêtres glissantes (« en détail air liquide » -> « air liquide »).
    - Enrichissement des stopwords et regex de nettoyage : suppression des préfixes (« en détail », « en profondeur », « complète ») et suffixes de politesse (« stp », « svp »).
    - Détection contextuelle multi-tours assistée par LLM (`extract_finance_targets`) : sur les questions de relance du type « analyse les données financières stp » ou « et ses résultats ? », résolution automatique de l'actif concerné via l'historique de la conversation et les actifs déjà étudiés (`AI.PA` / Air Liquide).
    - Activation automatique des APIs financières lorsque la compétence mentionnée ou active est orientée finance/bourse (ex. `@expert-finances`), en plus du commutateur manuel `finance_mode`.
    - Propagation cohérente des métadonnées `provider` (`eodhd` vs `yahoo_finance`) et `source_label` dans les extractions et pièces jointes.
  - **Résilience face aux réponses vides du modèle LLM** (`backend/app/main.py`) :
    - Gestion des cas où un modèle de raisonnement (ex. `gemini-3.8-flash`) consomme son tour en pensée pure et clôt le flux sans contenu visible : relance automatique immédiate avec consigne de complétion directe explicite, évitant l'erreur brutale « Le fournisseur a retourné une réponse vide ».
  - **Gros bandeau/badge visuel pour les données live EOD / Yahoo Finance** (`frontend/components/chat-app.tsx`, `frontend/app/globals.css`) :
    - Ajout d'une bannière très visible en tête de réponse (`.finance-live-banner`) : fond dégradé vert émeraude, icône `TrendingUp`, affichage des tickers analysés et badges de provenance bien visibles (`EOD Historical Data` en vert forêt, `Yahoo Finance` en violet).
    - Attribution et liens de consultation directe adaptés sous les sources pour chaque fournisseur (`eodhd.com` et `finance.yahoo.com`).
- Décision : l'analyse automatique financière s'exécute quand `finance_mode` est actif, quand une compétence boursière est invoquée, ou quand une requête contient une intention financière nette, avec repli transparent EODHD -> Yahoo Finance.
- Fichiers modifiés :
  - `backend/app/finance.py`, `backend/app/main.py`, `backend/app/providers.py`, `backend/app/context.py`.
  - `frontend/components/chat-app.tsx`, `frontend/app/globals.css`.
  - `backend/tests/test_finance.py`.
  - `HANDOFF.md`.
- Vérifications exécutées :
  - 28/28 tests unitaires validés dans `test_finance.py`.
  - Suite complète backend : 217 tests passés avec succès (`docker run ... pytest tests/`).
  - Validation TypeScript frontend `npm --prefix frontend run typecheck` (0 erreur).
  - Build de production Next.js `npm --prefix frontend run build` (succès).
  - Déploiement et test live en conteneur : récupération effective d'Air Liquide (`AI.PA`, 173.58 EUR) via l'API EOD Historical Data, puis résolution du tour de suivi « analyse les données financières stp ».
- Problèmes connus : aucun.
- Prochaine action : poser une question dans l'interface (ex. « @expert-finances analyse air liquide » ou avec le bouton Finances activé) et vérifier l'apparition du gros bandeau vert émeraude avec les cotations en direct.

---

# Relais — 22 octobre 2026 (mode réseau local)

- Réalisé : option `--lan` pour accéder au site depuis une autre machine via `http://<IP>:3001`, en plus de localhost.
  - `scripts/lan.sh` (nouveau) : détecte l'IP (`ip route get`, repli `hostname -I`, forçable via `LAN_IP`), exporte `WEB_BIND=0.0.0.0`, `ALLOWED_DEV_ORIGINS=<IP>` et `CORS_ORIGINS` enrichi de l'origine LAN (fusion avec l'env ou `.env`).
  - `scripts/compose.sh` : accepte `--lan` à n'importe quelle position, affiche aussi l'URL LAN.
  - `scripts/dev.sh --lan` : Next sur `0.0.0.0`; uvicorn reste sur 127.0.0.1.
  - `compose.yaml` : port web `${WEB_BIND:-127.0.0.1}:3001`, `CORS_ORIGINS` interpolé (défaut = valeur `.env`), `ALLOWED_DEV_ORIGINS` passé à `clair-web`. API toujours sur 127.0.0.1:8001.
  - `frontend/next.config.ts` : `allowedDevOrigins` lu depuis `ALLOWED_DEV_ORIGINS` (HMR Next 16 depuis le LAN).
  - `README.md` : section « Accès depuis une autre machine du réseau local ».
- Décision : seule l'origine du frontend est exposée; le proxy Next relaie `/api`. HTTP clair → réseau de confiance uniquement.
- Vérifications exécutées : `bash -n` des 3 scripts; `enable_lan_mode` avec `LAN_IP=192.168.1.50` (origines fusionnées OK); `docker compose config` en mode défaut (web 127.0.0.1, CORS inchangé) et LAN (web 0.0.0.0, origine LAN ajoutée); `npm --prefix frontend run typecheck` OK.
- Non vérifié : accès réel depuis une seconde machine; détection d'IP dans le sandbox (pas de réseau, renvoyait vide).
- Prochaine action : `./scripts/compose.sh up --build -d --wait --lan`, ouvrir le port 3001 au pare-feu si besoin, tester depuis un autre poste (connexion + envoi d'un message).

---

# Relais — 22 octobre 2026

- Réalisé :
  - **Intégration de l'API EOD Historical Data (EODHD) via `EOD_HISTORICAL_DATA_KEY`** :
    - Prise en charge de la variable `EOD_HISTORICAL_DATA_KEY` dans `backend/app/config.py` (`SecretStr`, assainissement, rechargement à chaud) et transmission via `compose.yaml`.
    - Implémentation du client EODHD dans `backend/app/finance.py` :
      - Recherche de ticker intelligent avec pondération (`search_eodhd_ticker`) : correspondances exactes, actions ordinaires, bourses prioritaires (PA, US).
      - Récupération des cours en temps réel (`fetch_eodhd_realtime`) : dernier cours, variation jour, clôture précédente, volume, fourchette.
      - Récupération des barres historiques EOD (`fetch_eodhd_historical_eod`) : tableau récapitulatif des dernières séances de bourse.
      - Récupération des fondamentaux EODHD (`fetch_eodhd_fundamentals`).
      - Enrichissement croisé automatique avec Yahoo Finance (`fetch_yahoo_quote_summary`) pour les ratios de valorisation et le profil d'entreprise quand applicable.
      - Mécanisme de repli (fallback) transparent et sans coupure vers Yahoo Finance si EODHD est indisponible ou si la clé n'est pas configurée.
    - Prise en charge des URLs directes EODHD (`https://eodhd.com/financial-summary/{ticker}`) dans `backend/app/web.py` et `backend/app/finance.py`.
  - **Cartes et indicateurs d'attribution mis à jour dans le frontend** :
    - Étiquette de source dynamique dans la carte financière (`EOD Historical Data API` / `Yahoo Finance API`).
    - Bouton externe adapté : lien direct vers `https://eodhd.com/financial-summary/{ticker}` ou `https://finance.yahoo.com/quote/{ticker}`.
    - Badge du message assistant unifié : `<TrendingUp size={11} /> Finances & Bourse`.
    - Bandeau du mode finances dans le compositeur clarifié avec mention d'EOD Historical Data et Yahoo Finance.
    - Extension de l'interface TypeScript `finance_meta` (`frontend/lib/api.ts`).
  - **Déploiement et tests** :
    - Build de production Next.js généré et déployé dans `tchataiperso-clair-web-1`.
    - Fichiers backend synchronisés dans `tchataiperso-clair-api-1` et conteneurs redémarrés.
    - Test direct en conditions réelles avec `EOD_HISTORICAL_DATA_KEY` sur Stellantis : récupération réussie de la cotation `STLAP.PA` via EOD Historical Data.
    - 22/22 tests unitaires validés dans `test_finance.py` (incluant recherche EODHD, temps réel, historique EOD, génération markdown, et fallback Yahoo Finance).
    - Suite de tests complète validée : 212 tests passés avec succès (68 sur finance/api + 144 sur context/blogs/web/youtube/providers/migrations).
    - Validation TypeScript frontend `npm --prefix frontend run typecheck` (**0 erreur**).

- Fichiers modifiés :
  - Backend : `backend/app/config.py`, `backend/app/finance.py`, `backend/app/web.py`, `backend/app/main.py`, `backend/app/context.py`, `backend/app/schemas.py`.
  - Configuration : `compose.yaml`.
  - Tests backend : `backend/tests/test_finance.py`.
  - Frontend : `frontend/components/chat-app.tsx`, `frontend/lib/api.ts`, `frontend/app/globals.css`.
  - Suivi : `HANDOFF.md`.

- Vérifications exécutées :
  - Compilation Python sans erreur (`python3 -m py_compile backend/app/*.py backend/tests/*.py`).
  - Test en direct avec la clé `EOD_HISTORICAL_DATA_KEY` : validation du téléchargement de `📈 Stellantis NV (STLAP.PA) · EOD Historical Data`.
  - Exécution des tests `test_finance.py` (22/22 réussis) et `test_api.py` (46/46 réussis).
  - Exécution complète des tests restants (144/144 réussis). Total : 212 tests passés.
  - Typecheck TypeScript (`npm --prefix frontend run typecheck`) : 0 erreur.
  - Vérification de l'absence de tout secret / clé API dans git diff.

- Problèmes connus :
  - Aucun.

- Prochaine action :
  - Poser une question boursière ou financière dans le chat (ex: `analyse stellantis`, `cours TotalEnergies`, `Apple`, etc.) pour observer les données en direct téléchargées via l'API EOD Historical Data.
