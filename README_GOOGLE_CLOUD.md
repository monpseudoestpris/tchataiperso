# Configuration Google Cloud (Vertex AI) pour les modèles Google

Ce guide explique comment configurer le routage de tous les modèles Google (`google/*`, `gemini-*`, `imagen-*`, `gemma-*`, Google Deep Research) vers **Google Cloud (Vertex AI)** afin d'utiliser votre crédit mensuel Google Cloud (ex. \$10/mois inclus avec **Google AI Pro / Google Developer Program**).

Les modèles non-Google (OpenAI, Anthropic, Mistral, Ideogram, etc.) continuent d'utiliser OpenRouter ou leurs fournisseurs natifs.

---

## 1. Prérequis dans Google Cloud Console

1. Connectez-vous sur [console.cloud.google.com](https://console.cloud.google.com/) et sélectionnez (ou créez) votre projet GCP (ex. `votre-project-id`).
2. Vérifiez dans **Menu ☰ → Facturation** que ce projet est bien rattaché au compte de facturation qui porte votre crédit mensuel de **\$10**.
   - Si le crédit n'apparaît pas encore dans **Facturation → Crédits**, activez l'avantage sur [developers.google.com/program](https://developers.google.com/program) avec votre compte Google AI Pro.
3. Notez l'**ID du projet** (colonne *Identifiant*, en minuscules avec tirets — pas le nom d'affichage).

---

## 2. Installer et authentifier `gcloud` (Linux)

### 2.1 Installer Google Cloud CLI
```bash
sudo snap install google-cloud-cli --classic
```
*(L'option `--classic` est requise par `google-cloud-cli`.)*

### 2.2 Créer les identifiants ADC (Application Default Credentials)
Ces identifiants sont ceux utilisés par le backend Python (`google-auth`) :
```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project votre-project-id
```
Le fichier généré est enregistré dans :
`~/.config/gcloud/application_default_credentials.json`

### 2.3 Connecter la CLI `gcloud`, activer Vertex AI et vérifier la facturation
```bash
gcloud auth login
gcloud config set project votre-project-id
gcloud services enable aiplatform.googleapis.com --project=votre-project-id
gcloud billing projects describe votre-project-id
```
La dernière commande doit afficher `billingEnabled: true`.

---

## 3. Permissions pour Docker (`clair-api`)

Dans [compose.yaml](compose.yaml), le fichier ADC de l'hôte est monté en lecture seule dans le conteneur `clair-api` :
```yaml
- ~/.config/gcloud/application_default_credentials.json:/run/secrets/gcp-adc.json:ro
```
Comme le conteneur `clair-api` s'exécute sous l'utilisateur **`app` (UID `10001`)** (voir [backend/Dockerfile](backend/Dockerfile)), le fichier créé en mode `600` par `gcloud` doit être lisible par l'UID `10001` :

```bash
setfacl -m u:10001:r ~/.config/gcloud/application_default_credentials.json 2>/dev/null || chmod 644 ~/.config/gcloud/application_default_credentials.json
```

> **Alternative sans expiration (Compte de service JSON)** :
> Dans Google Cloud Console → **IAM et administration → Comptes de service**, créez un compte de service avec le rôle **Utilisateur Vertex AI** (`roles/aiplatform.user`), générez une clé JSON, placez-la hors du dépôt (ex. `~/.config/gcloud/clair-vertex-sa.json`), donnez-lui les droits de lecture pour l'UID `10001` et montez-la dans `compose.yaml` vers `/run/secrets/gcp-sa.json:ro`.

---

## 4. Configuration du fichier `.env`

Référez-vous à [.env.example](.env.example).

### En Docker (`./scripts/start.sh` ou `./scripts/start.sh dev`)
```env
GOOGLE_CLOUD_MODE=vertex_oauth
GOOGLE_CLOUD_PROJECT=votre-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-adc.json
VERTEX_API_KEY=
GOOGLE_CLOUD_FALLBACK_OPENROUTER=false
```

### En local sans Docker (`./scripts/start.sh local`)
Laissez `GOOGLE_APPLICATION_CREDENTIALS=` vide (`google-auth` lit automatiquement `~/.config/gcloud/application_default_credentials.json`) :
```env
GOOGLE_CLOUD_MODE=vertex_oauth
GOOGLE_CLOUD_PROJECT=votre-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_APPLICATION_CREDENTIALS=
VERTEX_API_KEY=
GOOGLE_CLOUD_FALLBACK_OPENROUTER=false
```

### Options complémentaires
- **Mode clé API Vertex (`vertex_api_key`)** : si vous préférez une simple clé API au lieu d'ADC/OAuth2, définissez `GOOGLE_CLOUD_MODE=vertex_api_key` et renseignez `VERTEX_API_KEY=...` (note : *Google Deep Research* nécessite `vertex_oauth` ou `GOOGLE_API_KEY`).
- **Remapping de noms de modèles (`GOOGLE_CLOUD_MODEL_MAP`)** : si un modèle du catalogue (ex. modèle preview/alias) renvoie une erreur `404` sur Vertex AI, réécrivez-le sans modifier le code :
  ```env
  GOOGLE_CLOUD_MODEL_MAP={"google/gemini-4-argon":"gemini-2.5-pro"}
  ```
- **Repli OpenRouter (`GOOGLE_CLOUD_FALLBACK_OPENROUTER`)** : `false` par défaut pour garantir qu'aucun appel Google ne bascule silencieusement sur OpenRouter (et ne consomme de crédit OpenRouter) en cas d'erreur.

---

## 5. Redémarrage et vérifications

### Redémarrer la pile Docker (si vous utilisez Docker)
```bash
docker compose up -d --build clair-api
# ou selon votre mode habituel :
./scripts/start.sh dev
```

### Vérifier la configuration détectée par l'API
```bash
curl -s http://127.0.0.1:8001/api/config | grep -o '"google_cloud[^}]*'
```
Résultat attendu :
```json
"google_cloud_mode":"vertex_oauth","features":{"chat":true,"google_cloud":true,...
```

### Vérifier que les appels partent bien sur Google Cloud
1. Envoyez un message dans le tchat avec `google/gemini-2.5-flash`.
2. Vérifiez dans **OpenRouter → Activity** qu'aucune requête Gemini n'y apparaît.
3. Vérifiez dans **Google Cloud Console → API et services → Vertex AI API → Métriques** et **Facturation → Rapports / Crédits** (délai de quelques minutes pour l'affichage).

---

## 6. Dépannage rapide

| Erreur | Cause probable | Solution |
|---|---|---|
| `Authentification Google Cloud impossible ; configurez GOOGLE_APPLICATION_CREDENTIALS...` | Le conteneur (`UID 10001`) n'a pas les droits de lecture sur `application_default_credentials.json`, ou le fichier ADC n'a pas été généré | Exécuter `gcloud auth application-default login` puis `setfacl -m u:10001:r ~/.config/gcloud/application_default_credentials.json 2>/dev/null \|\| chmod 644 ~/.config/gcloud/application_default_credentials.json` |
| `Le fichier GOOGLE_APPLICATION_CREDENTIALS est introuvable` | Chemin `/run/secrets/gcp-adc.json` utilisé en mode `./scripts/start.sh local` (hors Docker) ou volume manquant dans `compose.yaml` | Vider `GOOGLE_APPLICATION_CREDENTIALS=` en local, ou vérifier le montage dans `compose.yaml` et redémarrer Docker |
| `Configurez GOOGLE_CLOUD_PROJECT` | `GOOGLE_CLOUD_PROJECT` vide dans `.env` ou projet sans quota ADC | Renseigner `GOOGLE_CLOUD_PROJECT=votre-project-id` dans `.env` |
| `HTTP 401/403` sur Vertex AI | API Vertex AI désactivée, compte de facturation non lié, ou token ADC expiré/révoqué | Activer `aiplatform.googleapis.com`, vérifier `gcloud billing projects describe`, ou relancer `gcloud auth application-default login` |
| `HTTP 404` sur un modèle | Identifiant du modèle différent sur Vertex AI | Ajouter un mapping dans `GOOGLE_CLOUD_MODEL_MAP` dans `.env` |
