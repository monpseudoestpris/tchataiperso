# ADR 0006 — Isolation Sandbox (origine opaque `null`) pour les aperçus HTML et les pages publiques `/p/{token}`

- **Statut** : Accepté (`OWD-1`, implémenté dans `T1b`)
- **Date** : 2026-11-23

## Contexte
L'application **cLAIr** exécute du HTML/CSS/JavaScript généré par LLM dans deux surfaces servies sur la même origine que l'application authentifiée (`localhost:3001` ou hôte LAN) :
1. Les aperçus `<iframe srcDoc>` de **Code Canvas** (`CodeCanvas`) et **cLAIr Pages** (`WebPageModal`).
2. Les pages publiées servies par `/p/{token}` et `/api/pages/public/{token}` via le rewrite Next.js.

Combiner `allow-scripts` et `allow-same-origin` dans une iframe `srcDoc`, ou servir `/p/{token}` avec `script-src 'unsafe-inline'` sans directive CSP `sandbox` ni `form-action 'none'`, permettait à un script généré d'accéder au `localStorage` parent, à `window.parent` ou aux routes `/api/*` avec le cookie de session `tchat_session`.

## Décision
1. **Origine opaque `null` obligatoire** : retirer `allow-same-origin` des `<iframe srcDoc>` (`sandbox="allow-scripts allow-forms allow-modals allow-downloads"`) et ajouter `sandbox allow-scripts allow-forms allow-popups allow-downloads; form-action 'none'; frame-ancestors 'none';` dans la CSP de `/p/{token}`.
2. **Communication Briques IA par `postMessage`** : conserver le pont `CLAIR_BRICK_CALL` / `CLAIR_BRICK_RESULT` vérifié par `event.source === iframeWin` (compatible sans `allow-same-origin`).
3. **Repli mémoire `Storage`** : injecter de façon idempotente en tête de `<head>` (`page_runtime.py` et `frontend/lib/code-canvas.ts`) un shim mémoire transparent sur `localStorage` et `sessionStorage` lorsque l'accès natif lève `SecurityError` sous origine opaque `null`.

## Conséquences
- **Positives** : Fermeture complète de l'évasion Sandbox / XSS Same-Origin sans nécessiter de sous-domaine séparé en déploiement local ou LAN ; compatibilité préservée avec les mini-apps utilisant `localStorage` ou les Briques IA.
- **Contraintes** : Le `localStorage` d'une mini-app prévisualisée ou publiée sur `/p/{token}` est éphémère en mémoire (réinitialisé au rechargement de la page), sauf si l'utilisateur exporte et ouvre le fichier HTML localement hors sandbox.
