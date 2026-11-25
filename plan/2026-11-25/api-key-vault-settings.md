# Coffre-fort Clés API « Write-Only » dans les Paramètres (Administration)

- **Créé le** : 2026-11-25
- **Statut** : TERMINÉ

## 1. Demande & Objectif Vérifiable
Permettre à un administrateur de configurer et surcharger à chaud les **8 clés API des fournisseurs externes** directement depuis la modale **Paramètres**, en prenant la priorité sur les valeurs du fichier `.env`, avec un niveau de sécurité maximal :
1. **Zéro secret côté navigateur** : aucune sauvegarde dans `localStorage` / `sessionStorage` / cookies ; champs vidés sitôt enregistrés.
2. **Opacité stricte « Write-Only » (zéro caractère retourné)** : ni les clés du coffre-fort ni celles du `.env` ne sont jamais renvoyées (même tronquées) ; l'API ne retourne que le statut d'origine (`active_vault` | `active_env` | `missing`) et l'horodatage de modification.
3. **Chiffrement fort au repos (`AES-256-GCM`) & séparation clé / base SQL** : table `api_key_overrides` stockant des blobs chiffrés authentifiés (`AAD = key_name`), chiffrés par une clé maîtresse 256 bits (`CLAIR_VAULT_KEY` ou fichier `.vault.key` `0600` hors base SQL) disponible dès le démarrage serveur sans déverrouillage manuel.
4. **Protection Admin « Mode Sudo »** : routes réservées à `require_admin` + ressaisie obligatoire du mot de passe Administrateur (`scrypt` + anti-bruteforce) pour toute écriture ou suppression (bloquant tout abus via session ouverte ou basculement familial `POST /api/family/switch`).
5. **Priorité temps réel & ergonomie complète** : résolution `Coffre-fort > .env > Vide` partout (tchat, studios, tâches de fond comme la synchro quotidienne Finance EODHD), sortie automatique de `DEMO_MODE` lorsqu'une clé LLM est active dans le coffre-fort, bouton « Tester » optionnel côté backend par fournisseur (`5 s` max, réponse aseptisée), et bouton « Revenir au `.env` » (suppression de surcharge).

## 2. Décisions Validées (One-Way Doors)
1. **Stockage** : Coffre-fort chiffré côté serveur en mode **Write-Only** (zéro `localStorage` navigateur) — cf. [ADR-0007](../../docs/adr/0007-coffre-fort-cles-api-write-only.md).
2. **Portée & RBAC** : Globale à l'instance entière (y compris synchros automatiques), visible et modifiable **uniquement par un compte Administrateur**.
3. **Réauthentification (« Sudo »)** : Mot de passe actuel du compte Administrateur exigé (avec anti-bruteforce) à chaque enregistrement ou suppression de clé.
4. **Clé maîtresse** : Persistante hors de la base SQL (`CLAIR_VAULT_KEY` ou fichier `.vault.key` en `0600`, isolé dans `tmp_path` sous `pytest` via `conftest.py`), assurant un démarrage serveur autonome et rendant un dump SQL seul indéchiffrable.
5. **Périmètre exact** : Les **8 clés fournisseurs externes** uniquement (`LLM_API_KEY`, `GOOGLE_API_KEY`, `VERTEX_API_KEY`, `MISTRAL_API_KEY`, `IDEOGRAM_API_KEY`, `ELEVEN_LABS_KEY`, `EOD_HISTORICAL_DATA_KEY`, `BRAVE_API_KEY`). Secrets d'infrastructure (`POSTGRES_PASSWORD`, `SEARXNG_SECRET`, `HERMES_API_KEY`) exclus.
6. **Masquage UI** : **Opacité stricte « Zéro caractère »** (badges d'état uniquement, aucun suffixe de clé).
7. **Validation réseau** : Bouton **« Tester »** optionnel par fournisseur exécuté côté backend sans bloquer la sauvegarde.
8. **Interaction `DEMO_MODE`** : Sortie automatique de `DEMO_MODE` dès qu'au moins une clé LLM (`LLM_API_KEY`, `GOOGLE_API_KEY` ou `VERTEX_API_KEY`) est active dans le coffre-fort, et retour au comportement du `.env` si les surcharges LLM sont supprimées.

## 3. Découpage & Suivi des Tranches
- [x] **T1 — Modèle SQL `ApiKeyOverride`, Migration `0033` & Moteur Cryptographique `AES-256-GCM` (`api_key_vault.py`)**
  `[One-Way] · [Runtime] · [~240 lines / 6 files] · [Seams checked: Yes]`
- [x] **T2 — Résolution Prioritaire dans `Settings`, Sortie Auto `DEMO_MODE`, Testeur Fournisseurs & Routes Admin « Sudo »**
  `[One-Way] · [Runtime] · [~340 lines / 6 files] · [Seams checked: Yes]`
- [x] **T3 — Composant Sprout Admin « Coffre-fort Clés API » dans `SettingsModal` & Rafraîchissement Live**
  `[Two-Way] · [Runtime] · [~320 lines / 4 files] · [Seams checked: Yes]`
- [x] **T4 — Styles Éditoriaux 12 Palettes (`settings-api-keys-section.module.css`), Audit Zéro-Fuite & Clôture**
  `[Two-Way] · [Static] · [~190 lines / 3 files] · [Seams checked: Yes]`

## 4. Journal de Preuves
- **Fichiers créés / modifiés** :
  - Documentation & Architecture : `docs/adr/0007-coffre-fort-cles-api-write-only.md`, `GLOSSARY.md` (#15), `HANDOFF.md`.
  - Backend : `backend/app/models.py` (`ApiKeyOverride`), `backend/migrations/versions/0033_add_api_key_overrides.py`, `backend/app/cli.py`, `backend/app/api_key_vault.py` (`AESGCM` + `AAD` + clé `0600`), `backend/app/api_key_tester.py` (sondes `5 s` `$0`), `backend/app/config.py` (transition `Vault > .env` + `DEMO_MODE`), `backend/app/openrouter.py` (`clear_openrouter_cache`), `backend/app/hermes_agent.py` (bascule `local_autonomous` si surcharge `llm_api_key`), `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/routers/settings.py`, `backend/tests/conftest.py`, `backend/tests/test_api_key_vault.py`, `backend/tests/test_api_keys_routes.py`.
  - Frontend : `frontend/lib/api.ts`, `frontend/components/settings-api-keys-section.tsx`, `frontend/components/settings-api-keys-section.module.css`, `frontend/components/settings-modal.tsx`, `frontend/components/chat-app.tsx`, `frontend/tests/api-key-vault-ui.test.mjs`.
- **Commandes exécutées** :
  - `cd backend && HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 .venv/bin/python -m pytest tests/test_api.py tests/test_api_key_vault.py tests/test_api_keys_routes.py tests/test_settings.py -q` → **PASS** (`77 passed`, complétant les `671 passed` hors `test_api.py` = **`683 passed, 0 failed`** sur la suite complète).
  - `cd frontend && npm run typecheck` → **PASS** (`0 error`).
  - `cd frontend && npx eslint components/settings-api-keys-section.tsx lib/api.ts --max-warnings 0` → **PASS** (`0 error, 0 warning`).
  - `cd frontend && npm test` → **PASS** (`34 passed, 0 failed`, incluant les 3 tests d'invariants sécurité de `api-key-vault-ui.test.mjs`).
  - `cd frontend && npm run build` → **PASS** (`next build` Turbopack OK).

## 5. Prochaine Tranche
Aucune — plan `TERMINÉ`.
