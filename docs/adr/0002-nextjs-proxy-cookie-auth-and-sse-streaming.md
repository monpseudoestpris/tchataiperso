# ADR 0002 — Proxy d'API Next.js même-origine, sessions par cookies HttpOnly révocables et streaming SSE sur POST

- **Statut** : Accepté (en production dans le dépôt)
- **Date** : 2026-11-23

## Contexte
L'application doit pouvoir être utilisée sur `localhost` ou exposée sur un réseau local de confiance (`--lan`) sans jamais exposer les clés API des fournisseurs externes au navigateur, tout en diffusant en temps réel des flux complexes (pensées `<think>`, étapes de recherche web/DeepSearch, appels d'outils Finance, deltas Markdown).

## Décision
1. **Proxy même-origine Next.js** : Le navigateur communique exclusivement avec `clair-web` (port `3001`), qui proxifie `/api/*` vers `clair-api` (FastAPI, port `8001` lié à `127.0.0.1` en local). Aucune clé secrète n'est placée dans `NEXT_PUBLIC_*`.
2. **Sessions révocables par cookie `HttpOnly` & contrôle d'origine** : Authentification via le cookie `tchat_session` (`HttpOnly`, `SameSite=Lax`), dont seul le hash SHA-256 est stocké dans la table `auth_sessions` avec date d'expiration et de révocation. Un middleware HTTP dans `backend/app/main.py` vérifie que l'en-tête `Origin` de toute requête `POST`, `PATCH` ou `DELETE` appartient à `CORS_ORIGINS` (exception faite du point d'entrée serveur-à-serveur `/api/hermes/mcp`).
3. **Streaming par Server-Sent Events (SSE) sur `POST`** : L'envoi de messages (`POST /api/conversations/{id}/messages`) et les missions Hermes (`POST /api/hermes/run`) utilisent `StreamingResponse` (`text/event-stream`) consommé côté client par `fetch` + `ReadableStream` (`streamMessage` dans `frontend/lib/api.ts`) avec un contrat d'événements typés (`meta`, `status`, `thought`, `research_activity`, `delta`, `done`, `error`).

## Conséquences
- **Positives** : Surface d'attaque réduite (zéro secret client, protection CSRF par validation d'origine + cookie `SameSite=Lax`), absence de complexité WebSocket, traversée transparente du proxy Next.js.
- **Contraintes** : Toute nouvelle fonctionnalité temps réel dans le flux de conversation doit émettre ses mises à jour via le format SSE (`serializers.sse`) et être déclarée dans l'union discriminée `StreamEvent` de `frontend/lib/api.ts`.
