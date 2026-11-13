# Relais — 12 novembre 2026

## 1. Project Overview
clAIr : tchat IA francophone, apprentissage, recherche, médias et génération de pages HTML. Frontend Next.js 16.4 / React 19 / TypeScript ; backend FastAPI / SQLAlchemy / PostgreSQL.

## 2. Current Objective
Mettre en place un **système hybride de créativité** et le paramétrage fin des **13 paramètres d'échantillonnage et de réflexion** dans chaque **tchat** et chaque **compétence** :
- `temperature` (Aléatoire et originalité)
- `top_p` (Diversité des tokens possibles)
- `top_k` (Nombre de tokens candidats)
- `min_p` (Élimination des tokens trop improbables)
- `top_a` (Filtrage dynamique des tokens)
- `presence_penalty` (Introduction de nouvelles idées)
- `frequency_penalty` (Réduction des répétitions)
- `repetition_penalty` (Pénalisation des tokens déjà utilisés)
- `logit_bias` (Favoriser ou défavoriser certains tokens)
- `seed` (Variation ou reproductibilité entre générations)
- `reasoning` (Influence indirecte par la profondeur de réflexion)
- `reasoning_effort` (Variante de configuration de l'effort de réflexion)
- `verbosity` (Influence indirecte par le niveau de développement)

Fonctionnement hybride selon les capacités du modèle détectées via OpenRouter :
- **Modèle avec température et autres** : curseur de créativité $\rightarrow$ paramètres numériques supportés (`temperature`, `top_p`, `top_k`/`min_p`, pénalités) **+** instructions de posture cognitive.
- **Modèle sans température (ex. Claude Sonnet 5.5)** : curseur de créativité $\rightarrow$ **instructions adaptées** (sans envoyer `temperature`/`top_p`/`top_k` non supportés), avec prise en charge de `reasoning` et `verbosity`.
- **Garde-fou universel** : cohérence stricte avec l'activité (une analyse scientifique, technique, juridique ou financière peut explorer des hypothèses originales, mais ne doit **jamais inventer de faits, de chiffres ou de sources**).

## 3. Completed Work
- **Backend — Système Hybride & Catalogue des 13 Paramètres (`backend/app/sampling.py`)** :
  - Catalogue `PARAMETER_CATALOG` des 13 paramètres avec leurs rôles exacts, descriptions françaises, conseils et libellés d'indisponibilité (`"Pas de contrôle direct de l'aléatoire"` pour `temperature`, `"Pas de réglage"` pour les autres).
  - `extract_supported_creativity_parameters` : filtre et normalise `supported_parameters` d'OpenRouter vers les 13 paramètres.
  - `build_creativity_instruction(creativity, has_temperature)` : génère les consignes système adaptées au niveau de créativité (distinguant les modèles avec température et les modèles sans température comme Sonnet 5.5) avec le garde-fou explicite interdisant toute invention de faits dans les tâches analytiques/scientifiques.
  - `resolve_effective_sampling` & `format_sampling_for_openrouter_payload` : résout **Message > Conversation > Compétence active > Défaut**, filtre selon `supported_parameters` du modèle cible et formate `reasoning` (`{"effort": ...}` ou `{"enabled": False}`), `reasoning_effort`, `verbosity` et `logit_bias` pour OpenRouter.
- **Backend — Contexte, Schémas & OpenRouter** :
  - **`backend/app/context.py` & `backend/app/routers/messages.py`** : injection de `creativity_instruction` dans `build_context` lors de l'envoi d'un message lorsqu'une créativité est définie sur le message, la conversation ou une compétence active.
  - **`backend/app/openrouter.py`** : ajout automatique de `"reasoning"` dans `supported_parameters` lorsque les métadonnées `reasoning` du modèle l'indiquent.
  - **`backend/app/schemas.py`** : extension de `SamplingParameters` aux 13 paramètres (`min_p`, `top_a`, `logit_bias`, `reasoning`, `reasoning_effort`, `verbosity`).
- **Frontend — Interface `CreativityControl` (`frontend/components/creativity-control.tsx`, `frontend/components/chat-app.tsx` & `frontend/lib/api.ts`)** :
  - Badge d'état hybride en temps réel : `Température + Instructions` (modèle avec `temperature`) ou `Instructions adaptées (sans température)` (modèle type Sonnet 5.5).
  - Affichage des 13 paramètres avec leur rôle exact (`Aléatoire et originalité`, `Influence indirecte par la profondeur de réflexion`, etc.), leur disponibilité par modèle (`Disponible`, `Pas de contrôle direct de l'aléatoire`, `Pas de réglage`) et les contrôles adaptés (champs numériques, sélecteurs pour `reasoning` / `reasoning_effort` / `verbosity`, champ JSON pour `logit_bias`).
  - Défilement vertical (`overflowY: "auto"`, `maxHeight`) activé sur le panneau de créativité du tchat (avec en-tête fixe `sticky`) et sur la liste des 13 paramètres détaillés afin que le bas de la liste (`reasoning`, `reasoning_effort`, `verbosity`) reste toujours accessible.

## 4. Key Decisions
- **Système hybride (Paramètres + Instructions)** : Les modèles sans `temperature` (comme Sonnet 5.5 ou certains modèles de raisonnement) conservent un curseur de créativité pleinement fonctionnel grâce aux instructions adaptées, tandis que les modèles classiques bénéficient de la synergie entre échantillonnage probabiliste et directives de posture.
- **Intégrité factuelle invariante** : Quel que soit le niveau de créativité (même à 95 % « Audacieux »), l'instruction injectée rappelle que l'originalité porte sur les hypothèses, les angles d'approche et la pédagogie, jamais sur l'invention de faits ou de données.

## 5. Modified Files
- `backend/app/sampling.py` : Catalogue des 13 paramètres, filtrage par modèle, formatage OpenRouter et générateur d'instructions hybrides `build_creativity_instruction`.
- `backend/app/context.py` : Paramètre `creativity_instruction` intégré au prompt système dans `build_context`.
- `backend/app/openrouter.py` : Détection de `supported_parameters` enrichie pour les 13 paramètres et l'attribut `reasoning`.
- `backend/app/schemas.py` : Validation Pydantic des 13 paramètres dans `SamplingParameters`.
- `backend/app/routers/messages.py` : Résolution conjointe de `effective_sampling` et `creativity_instruction`.
- `backend/tests/test_api.py` : Mise à jour de `test_creativity_and_sampling_params_for_chats_skills_and_models` incluant un profil `anthropic/claude-sonnet-5.5` (`supported_parameters: ["reasoning", "verbosity"]`).
- `frontend/lib/api.ts` : Types TypeScript `SamplingParameters` et `ModelParameterSpec` étendus aux 13 paramètres.
- `frontend/components/creativity-control.tsx` : Interface hybride et contrôles pour les 13 paramètres.
- `HANDOFF.md` : Mise à jour du journal de continuité.

## 6. Verification
- `python3 -m py_compile` sur l'ensemble des modules backend modifiés : **OK (code 0)**.
- Tests unitaires Python sur `backend/app/sampling.py` (13 paramètres, profil Sonnet 5.5 sans température avec `reasoning` + `verbosity`, instructions hybrides avec garde-fou factuel, `min_p`, `top_a`, `logit_bias`, `reasoning_effort`) : **OK (`HYBRID_SAMPLING_TESTS_OK`)**.
- `npm --prefix frontend run typecheck` & `git diff --check` : lancés et vérifiés.

## 7. Known Issues and Risks
- Fichiers `.env` réels : non inspectés, non modifiés (frontière stricte de sécurité respectée).

## 8. Next Action
Prêt pour utilisation dans l'interface des tchats et des compétences.
