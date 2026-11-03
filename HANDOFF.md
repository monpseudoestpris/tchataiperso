# Relais — 3 novembre 2026

## 1. Project Overview
clAIr : tchat IA francophone, apprentissage, recherche, médias et génération de pages HTML. Frontend Next.js 16.4 / React 19 / TypeScript ; backend FastAPI / SQLAlchemy / PostgreSQL.

## 2. Current Objective
Question LAN multi-utilisateur vérifiée : deux PC peuvent utiliser deux comptes distincts simultanément (sessions par cookie, données filtrées par propriétaire). Aucun changement applicatif nécessaire. Quatre tests d’authentification/isolation réussis ; pas de test physique sur deux PC. Invitation créée depuis l’origine courante : utiliser l’IP LAN pour éviter un lien `localhost` inutilisable sur l’autre PC. Ressources et configuration des fournisseurs IA partagées.

Demande implémentée : les pages de **Sortie → Site HTML** sont enregistrées et attachées au tchat, puis retrouvables sans régénération dans **Pages HTML attachées**. Les échecs restent exclus de la sauvegarde. Vérifications backend, migration et build frontend réussies ; table disponible dans le backend actif. Parcours visuel authentifié non exécuté.

## 3. Completed Work
- Génération depuis le tour ou toute la discussion via clAIr Pages : synthèse des informations uniquement, sections, sources utiles, SVG. Aucun échange brut embarqué ; rendu isolé en iframe statique, scripts générés et appels API bloqués.
- Longues discussions : compression par blocs, trois passes maximum ; aucun abandon silencieux de la fin.
- Erreur initiale sur une seule discussion : l’utilisateur a confirmé « La page générée est incomplète ». Une seconde génération plus compacte (quatre sections/600 mots/CSS court/SVG simple) est tentée depuis les données initiales, sans réutiliser ni fermer artificiellement le document tronqué. Échec utilisateur pas encore retesté après cette reprise.
- Diagnostics sûrs : détails assainis conservés (HTTP/délai/HTML incomplet), sans corps fournisseur ni secret. Repli de modèle pour 400/404/422, sans répétition pour 401/402/429.
- Nouvelle table `chat_sites` : instantanés privés immuables, FK discussion avec suppression en cascade et unicité discussion/empreinte d’entrée.
- Réutilisation de l’instantané si contenu/titre/périmètre identiques, y compris entre entrée discussion et entrée message `scope=conversation`. Les nouveaux contenus produisent un nouvel instantané ; liens vers les anciennes pages stables.
- Persistance des seules réussites. Conflit d’unicité concurrent : récupération de l’instantané déjà enregistré après rollback.
- API authentifiée de liste et lecture, contrôles du propriétaire et de l’appartenance page/discussion ; lecture enregistrée sans IA.
- Composant `ChatAttachedSites` sous l’en-tête du tchat : liens datés, périmètre tour/discussion, chargement au montage et au retour sur l’onglet ; protection contre réponses obsolètes et erreurs affichées.
- PDF et présentations inchangés. Téléchargement HTML du résultat affiché via Blob.
- Travail préexistant sur 12 thèmes conservé intégralement, sans modification de ses fichiers.

## 4. Key Decisions
- Instantanés attachés au tchat distincts de la bibliothèque indépendante Pages ; aucune publication.
- Empreinte SHA-256 du titre, périmètre, message ciblé éventuel et rôles/contenus/sources normalisés. Dates de rendu exclues pour réutiliser un même contenu depuis les deux routes.
- Nouvelle génération pour un contenu modifié ; pas de remplacement silencieux des anciens instantanés.
- `generate_chat_site(..., raise_on_failure=True)` pour que la persistance distingue une réussite d’une page d’erreur ; comportement d’affichage par défaut préservé.
- Réutilisation du modèle `PAGE_MODEL`, sans nouvelle dépendance ni variable privée.
- Table créée au démarrage via le `Base.metadata.create_all` existant, avec migration Alembic additive/idempotente `0018_add_chat_sites` et révision reconnue par le CLI.
- Aucun commit, publication, migration destructive ni redémarrage manuel des conteneurs.

## 5. Modified Files
Demande actuelle :
- `backend/app/models.py` : modèle ChatSite et relation de suppression en cascade.
- `backend/app/chat_site_store.py` (nouveau) : empreinte, lecture, génération/persistance et gestion des conflits.
- `backend/app/chat_site.py` : option de propagation des échecs.
- `backend/app/routers/conversations.py`, `backend/app/routers/messages.py` : génération avec sauvegarde ; liste/lecture privées.
- `backend/app/cli.py`, `backend/migrations/versions/0018_add_chat_sites.py` (nouveau) : migration additive.
- `backend/tests/test_chat_site_storage.py` (nouveau), `backend/tests/test_chat_site.py` : persistance, cache, droits, cascade, erreurs, migration et adaptations.
- `frontend/components/chat-attached-sites.tsx` (nouveau), `frontend/components/chat-app.tsx` : pages attachées visibles dans la discussion.
- `README.md`, `HANDOFF.md` : comportement et continuité.
Travail antérieur toujours présent : `backend/app/page_generator.py` (validation/reprise/diagnostics), fichiers frontend des thèmes (`interface-themes.ts`, `interface-theme.tsx`, `interface-theme-sync.tsx`, `interface-themes.css`, layout, paramètres, tests et package.json), sans écrasement.

## 6. Verification
Question LAN : depuis `backend`, `timeout 45s .venv/bin/python -m pytest tests/test_api.py -k 'private_api_requires_authenticated_session or session_cookie_is_http_only_and_same_site or logout_revokes_session_and_login_is_rate_limited or invited_users_cannot_access_another_users_data' -q` : **4 passed, 54 deselected**, avertissement Starlette/httpx existant. Réussite hors sandbox ; première tentative sans `timeout` dans la sandbox interrompue sans sortie (aucun résultat). Tests avec base temporaire, mode démo et `_env_file=None`. Revue de `auth.py`, `deps.py`, routes auth/settings/conversations, panneau admin et documentation LAN. Seul `HANDOFF.md` modifié pour cette question.

Exécuté pour cette demande :
- Depuis `backend` : `.venv/bin/python -m pytest tests/test_chat_site_storage.py tests/test_chat_site.py tests/test_pages.py tests/test_report_integrity.py -q` : **52 tests réussis** après les derniers changements. Avertissement existant Starlette/httpx. Fournisseurs simulés, aucun appel IA payant.
- Migration testée directement via Alembic Operations sur SQLite mémoire : création depuis une table discussion existante, réexécution idempotente, données conservées et contrainte unique présente.
- Depuis `frontend` : `npm run typecheck && ./node_modules/.bin/eslint components/chat-attached-sites.tsx` : succès.
- Depuis `frontend` : `npm run build` : succès (compilation, TypeScript, génération des pages). Exécuté hors sandbox.
- `git diff --check -- . ':!.env*'` : succès.
- Contrôle Docker via `docker exec -i tchataiperso-clair-api-1 python` : import normal de l’application et inspection de schéma uniquement ; `chat_sites_table_available: True`. Aucun contenu utilisateur ni configuration privée affiché.
- Pas de parcours visuel authentifié, suite backend complète ni appel IA réel pour cette demande.
Vérifications antérieures : deux générations réelles sur sujets fictifs avaient réussi avant la reprise compacte ; harnais Chrome avait validé isolation/scripts désactivés avant suppression du volet d’archive. Non réexécutés ici. Vérifications thèmes héritées (cinq tests, typecheck, lint ciblé, build et harnais Chrome) non réexécutées.

## 7. Known Issues and Risks
- Les pages générées avant l’ajout de la persistance ne sont pas récupérables automatiquement ; une nouvelle génération les enregistre désormais.
- Le premier appel peut encore échouer après la reprise compacte : motif assaini affiché et aucune page d’erreur enregistrée. Discussion de l’utilisateur à retester.
- Deux premières générations simultanées identiques peuvent encore appeler l’IA chacune ; l’unicité garantit un seul instantané conservé. Les réouvertures après sauvegarde ne relancent pas l’IA.
- Rafraîchissement de la liste au retour/focus de l’onglet, pas de polling continu si une génération se termine en arrière-plan pendant que le tchat reste actif.
- Fidélité et esthétique restent génératives ; les faits d’un tchat ordinaire ne sont pas certifiés. Les iframes ont leur propre défilement.
- Zones spécialisées frontend : couverture visuelle des 12 thèmes non exhaustive.
- Fichiers privés et vrais `.env` : ne jamais inspecter/modifier. Aucun secret enregistré ici.

## 8. Next Action
Si validation LAN souhaitée : ouvrir l’adresse `http://<IP-du-serveur>:3001` sur deux PC, inviter le second compte via Utilisateurs et vérifier deux discussions distinctes avec une connexion par compte. Aucune implémentation supplémentaire requise pour ce cas.

Générer une page depuis un tchat réel, revenir sur son onglet et vérifier **Pages HTML attachées**, puis recharger la discussion et rouvrir l’instantané. Les tests de persistance passent et la table existe déjà dans le backend actif ; aucune reconstruction de table requise dans cette session.
