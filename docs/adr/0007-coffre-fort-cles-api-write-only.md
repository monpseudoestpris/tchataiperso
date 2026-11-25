# ADR-0007 — Coffre-fort Clés API Chiffré en Mode « Write-Only »

- **Statut** : Accepté
- **Date** : 2026-11-25

## Contexte
Les administrateurs souhaitent pouvoir renseigner ou surcharger les clés API des fournisseurs externes directement depuis l'interface **Paramètres**, avec priorité sur le fichier `.env`, sans exposer ces secrets dans le navigateur (`localStorage` vulnérable aux XSS/extensions et incompatible avec les tâches serveur autonomes comme la synchro quotidienne Finance EODHD) ni permettre leur relecture en cas de session laissée ouverte ou de basculement via groupe familial (`POST /api/family/switch`).

## Décision
1. **Flux strictement « Write-Only » et zéro secret navigateur** : les 8 clés fournisseurs externes (`LLM_API_KEY`, `GOOGLE_API_KEY`, `VERTEX_API_KEY`, `MISTRAL_API_KEY`, `IDEOGRAM_API_KEY`, `ELEVEN_LABS_KEY`, `EOD_HISTORICAL_DATA_KEY`, `BRAVE_API_KEY`) ne sont jamais stockées côté client ni renvoyées (même partiellement masquées) par l'API ; seul l'état d'origine (`active_vault`, `active_env`, `missing`) est exposé aux administrateurs.
2. **Chiffrement `AES-256-GCM` avec séparation physique clé / base SQL** : la table `api_key_overrides` stocke uniquement les textes chiffrés authentifiés (`AAD = key_name`), tandis que la clé maîtresse 256 bits est lue depuis `CLAIR_VAULT_KEY` ou générée automatiquement hors de la base SQL en permissions strictes `0600` (`.vault.key`).
3. **Contrôle d'accès Admin + Mode « Sudo »** : toute écriture ou suppression de surcharge exige `require_admin` **et** la vérification du mot de passe actuel de l'administrateur (`scrypt` + limitation anti-bruteforce).
4. **Résolution canonique** : `Coffre-fort Paramètres > .env / environnement > Vide` dans `Settings`, avec désactivation automatique de `DEMO_MODE` tant qu'une clé LLM est active dans le coffre-fort.

## Conséquences
- Un dump SQL seul est inexploitable sans la clé maîtresse, et le redémarrage serveur reste 100 % autonome pour les tâches de fond.
- Il est formellement interdit d'ajouter un endpoint de lecture de secret déchiffré, de journaliser une clé entrante, d'afficher des caractères de clé (même les derniers), ou d'exposer dans l'UI les secrets internes d'infrastructure (`POSTGRES_PASSWORD`, `SEARXNG_SECRET`, `HERMES_API_KEY`).
