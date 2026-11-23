# ADR 0005 — Pipeline financier EODHD-first, Screener 2 passes multi-unités et file budgétée des fondamentaux

- **Statut** : Accepté (en production dans le dépôt)
- **Date** : 2026-11-23

## Contexte
Les données Yahoo Finance souffrent d'instabilité et d'une couverture incomplète des fondamentaux hors États-Unis. L'API professionnelle **EODHD** offre une couverture mondiale fiable (actions, indices `.INDX`, fonds `EUFUND`, bulk EOD), mais applique un barème de crédits strict par appel (`eod` = 1, `news` = 5, `fundamentals` = 10, `eod-bulk-last-day` = 100) avec un quota quotidien de compte à ne jamais dépasser.

## Décision
1. **Priorité stricte EODHD & Référencement catalogue à coût zéro** : Toute la chaîne (`finance_provider.py`, `finance_warehouse.py`, `finance_dossier.py`, `finance_indices.py`) privilégie exclusivement `source = 'eodhd'` dès qu'il est disponible (avec repli `ETF_Data::Holdings` pour les indices restreints comme le Russell 2000). Toutes les actions ordinaires (`Common Stock`) des catalogues de bourses synchronisés sont référencées gratuitement dans le Screener (`seed_screener_from_exchange_catalogs`) sans appel réseau de cours.
2. **Mise à jour Bulk des cours & File budgétée des fondamentaux (`finance_fundamentals_queue`)** :
   - Les cours des bourses complètes sont rafraîchis en 1 seul appel `/api/eod-bulk-last-day/{EXCH}` (100 crédits/bourse) pour les titres déjà présents en base.
   - Le chargement des états financiers est piloté par la table `finance_fundamentals_queue` (`finance_fundamentals_scheduler.py`), qui calcule la prochaine échéance `next_due_at` d'après la saison habituelle de publication (`Earnings::History`) et le calendrier `/api/calendar/earnings`, priorise les titres (`0` coup de pouce Screener, `1–3` watchlists/indices/bourses complètes, `99` consulté) et s'arrête dès que le budget quotidien (`fundamentals_budget_pct`, défaut 10 %) ou la réserve de sécurité (`fundamentals_quota_safety_pct`, défaut 15 %) du quota `/api/user` est atteint.
3. **Screener 2 passes multi-unités & Outils Tchat 100 % locaux** :
   - Un moteur technique Python pur (`finance_technicals.py`) pré-calcule les indicateurs (dont **IsoPressure**) sur 4 unités (`day`, `week`, `month`, `quarter`) dans `finance_screener_technicals`, joints en Passe 1 SQL whitelistée à `finance_screener_snapshots` (qui embarque les 31 scores Uncle Stock dans `scores_json`), suivie d'une Passe 2 Python extensible (`finance_screener.py`).
   - 8 outils Finance en lecture seule (`finance_chat_tools.py`, orchestrés par `finance_chat_agent.py`) exposent l'entrepôt et le Screener directement dans le Tchat et le Mode Vocal sans appel réseau par défaut (plafond de 2 chargements live par tour si un ticker demandé est totalement absent).

## Conséquences
- **Positives** : Couverture boursière très large avec une consommation quotidienne de crédits EODHD prévisible et bornée ; interrogation instantanée du Screener et des dossiers depuis le tchat en langage naturel.
- **Contraintes** : Les actions nouvellement référencées depuis un catalogue de bourse apparaissent initialement comme « titres sans données » (`missing_data_count`) jusqu'à leur passage dans la file budgétée, un clic sur « Compléter » (`boost`) ou l'ouverture directe de leur fiche.
