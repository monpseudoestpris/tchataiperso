Mode audit strict (aucune modification du code source, ni de .env).
Lis AGENTS.md, inspecte le dépôt et git status, exécute les checks existants (build/typecheck/lint/tests) pour mesurer l'état initial, puis :
1. Crée HANDOFF.md avec le diagnostic factuel et le résultat exact des commandes exécutées.
2. Liste les incohérences de nommage métier (DB / back / front) pour qu'on définisse GLOSSARY.md ensemble.
3. Identifie les 5 hotspots prioritaires (couplage fort, fichiers monolithiques ou micro-fichiers éparpillés, manque de gestion d'erreurs ou failles de sécurité) et propose un plan de remaniement découpé en petites tranches indépendantes, en séparant clairement les Two-Way Doors (refactoring interne) des One-Way Doors (schéma DB, contrats d'API, auth).
Attends ma validation avant toute création de GLOSSARY.md ou modification de code.