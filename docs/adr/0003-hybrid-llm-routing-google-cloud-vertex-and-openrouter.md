# ADR 0003 — Routage LLM hybride : Google Cloud (Vertex AI / Gemini natif) en direct pour `google/*` et OpenRouter pour les autres fournisseurs

- **Statut** : Accepté (en production dans le dépôt)
- **Date** : 2026-11-23

## Contexte
L'utilisateur dispose de crédits mensuels Google Cloud (Vertex AI) pour les modèles Google (`google/*`, `gemini-*`, Gemini TTS, Google Deep Research) tout en souhaitant accéder à un large catalogue multi-fournisseurs (OpenAI, Anthropic, Mistral, Perplexity Sonar, Ideogram, ElevenLabs) sans dépendre d'un framework lourd (ni LangChain, ni LlamaIndex) et sans qu'une erreur de configuration Google Cloud ne consomme silencieusement des crédits OpenRouter.

## Décision
1. **Adaptateurs HTTP directs via `httpx`** : Tous les appels fournisseurs sont gérés par des modules dédiés (`backend/app/providers.py`, `google_cloud.py`, `openrouter.py`, `voice.py`) sans SDK d'orchestration tiers.
2. **Routage prioritaire `google/*` vers Google Cloud** : Lorsque `GOOGLE_CLOUD_MODE` est actif (`vertex_oauth` via fichier ADC monté en UID `10001`, `vertex_api_key` ou `gemini_api`), tout modèle identifié comme Google est routé directement vers Vertex AI / Gemini API. `google_cloud.py` assure la traduction bidirectionnelle entre le format OpenAI Chat Completions et l'API Gemini native (`contents`, `systemInstruction`, `functionDeclarations`, `generationConfig`, `thinkingConfig`), y compris la préservation de `thoughtSignature` lors des boucles d'outils multi-tours et le remapping d'identifiants à chaud via `GOOGLE_CLOUD_MODEL_MAP`.
3. **Isolation budgétaire stricte** : `GOOGLE_CLOUD_FALLBACK_OPENROUTER` est fixé à `false` par défaut afin qu'un échec Vertex AI remonte une erreur explicite au lieu de basculer en douce sur OpenRouter.

## Conséquences
- **Positives** : Exploitation directe des fonctionnalités natives Gemini (fenêtre 1M tokens, synthèse vocale `gemini-2.5-flash-tts` 30 voix, pensée signée sur appels d'outils, Interactions API Deep Research) et maîtrise exacte des coûts par fournisseur.
- **Contraintes** : Toute évolution du format d'appel d'outils ou de streaming dans le tchat doit être maintenue de façon symétrique pour le protocole OpenAI/OpenRouter et pour le traducteur Gemini natif dans `backend/app/google_cloud.py`.
