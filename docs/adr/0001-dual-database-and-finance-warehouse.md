# ADR 0001 — Architecture à double base de données : DB applicative (ORM) et Entrepôt Finance (`finance_warehouse.db` SQLite WAL)

- **Statut** : Accepté (en production dans le dépôt)
- **Date** : 2026-11-23

## Contexte
L'application **cLAIr** combine deux charges de travail aux profils incompatibles :
1. Des données transactionnelles multi-utilisateurs (comptes, sessions, groupes familiaux, conversations, messages, pièces jointes, documents illustrés, pages web) nécessitant une intégrité référentielle stricte.
2. Un entrepôt analytique boursier stockant des dizaines de milliers d'instruments, des millions de barres journalières OHLCV (`finance_eod_bars`), des séries historiques de faits fondamentaux normalisés (`finance_fundamental_facts`), des payloads JSON bruts compressés avec `zlib` (`finance_raw_snapshots`), un index plein texte FTS5 et des tables matérialisées multi-unités pour le Screener.

## Décision
Séparer la persistance en deux moteurs distincts :
1. **Base applicative principale (`DATABASE_URL`)** : gérée via **SQLAlchemy 2 + Alembic** (`backend/app/models.py`, PostgreSQL 17 en Docker sur le volume `postgres_data`, SQLite en développement local), complétée par des vérifications et ajouts de colonnes idempotents au démarrage (`lifespan` dans `backend/app/main.py`).
2. **Entrepôt Finance dédié (`finance_warehouse.db`)** : base **SQLite en mode `WAL`** (`PRAGMA synchronous=NORMAL`, `busy_timeout=15000`, `mmap_size=268435456`, tables `WITHOUT ROWID`, écritures par micro-lots) isolée dans `FINANCE_DATA_DIR` (volume Docker `finance_data`) et pilotée en SQL paramétré direct par `backend/app/finance_warehouse.py`.

## Conséquences
- **Positives** : Requêtes du Screener boursier, recherches FTS5 et appels des 8 outils Finance du tchat exécutés 100 % localement en quelques millisecondes sans saturer PostgreSQL ni l'ORM ; portabilité immédiate du volume `finance_data`.
- **Contraintes** : Aucune clé étrangère SQL inter-bases n'étant possible, les listes de suivi personnelles (`FinanceWatchlist` / `FinanceWatchlistItem`) modifiées dans la DB principale doivent être systématiquement répliquées vers `finance_user_watchlists` / `finance_user_watchlist_items` via `sync_user_watchlists_to_warehouse`, et toute lecture de données personnelles dans l'entrepôt doit filtrer explicitement par `user_id`.
