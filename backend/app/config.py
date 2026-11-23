import json
import ipaddress
import re
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_ISOLATED_ENV_PATHS: frozenset[Path] = frozenset()


IDEOGRAM_IMAGE_MODELS: list[dict[str, Any]] = [
    {
        "id": "ideogram-4-5",
        "name": "Ideogram 4.5 (Dernière génération)",
        "provider": "ideogram",
        "pricing_text": "Ideogram API",
        "description": "Dernier modèle phare d'Ideogram : photoréalisme avancé, typographie ultra-précise et édition chirurgicale Precise Edit jusqu'en 8K.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "10:16", "16:10", "1:3", "3:1"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": True,
        "is_top": True,
    },
    {
        "id": "ideogram-4",
        "name": "Ideogram 4.0",
        "provider": "ideogram",
        "pricing_text": "Ideogram API",
        "description": "Génération haute fidélité, mise en page structurée, typographie soignée et mode Remix avancé.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "10:16", "16:10", "1:3", "3:1"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": True,
        "is_top": True,
    },
    {
        "id": "ideogram-3",
        "name": "Ideogram 3.0",
        "provider": "ideogram",
        "pricing_text": "Ideogram API",
        "description": "Génération, Remix et Inpainting dédié au pinceau avec contrôle précis des styles et palettes.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "10:16", "16:10", "1:3", "3:1"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": True,
        "is_top": False,
    },
    {
        "id": "ideogram-3-transparent",
        "name": "Ideogram 3.0 Transparent (PNG détouré)",
        "provider": "ideogram",
        "pricing_text": "Ideogram API",
        "description": "Génération directe d'images, logos, stickers et sujets isolés sur fond transparent (PNG avec canal alpha).",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "10:16", "16:10", "1:3", "3:1"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "ideogram",
        "name": "Ideogram Auto (Sélection intelligente)",
        "provider": "ideogram",
        "pricing_text": "Ideogram API",
        "description": "Laisse l'API Ideogram sélectionner automatiquement le modèle le plus adapté à votre demande.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "10:16", "16:10", "1:3", "3:1"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": True,
        "is_top": True,
    },
]

DEFAULT_IMAGE_MODELS: list[dict[str, Any]] = [
    *IDEOGRAM_IMAGE_MODELS,
    {
        "id": "google/gemini-3.1-flash-image",
        "name": "Google: Nano Banana 2 (Gemini 3.1 Flash Image)",
        "provider": "openrouter",
        "pricing_text": "$0.50/M in · $60/M out",
        "description": "Modèle phare de Google alliant qualité Pro et vitesse Flash. Compréhension contextuelle poussée et créations nettes.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["512", "1K", "2K", "4K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "openai/gpt-image-2.5-sunburst",
        "name": "OpenAI: GPT Image 2.5 Sunburst",
        "provider": "openrouter",
        "pricing_text": "$8/M in · $30/M out",
        "description": "Précision artistique et fidélité de composition maximale pour créations graphiques exigeantes via l'Images API.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["1K", "2K", "4K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "google/gemini-nano-banana-2.1",
        "name": "Google: Nano Banana 2.1",
        "provider": "openrouter",
        "pricing_text": "$1.50/M in · $30/M out",
        "description": "Teintes de peau photoréalistes, éclairage et textures détaillés, haute fidélité visuelle.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["1K", "2K", "4K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "bytedance-seed/seedream-5-0-flash",
        "name": "ByteDance Seed: Seedream 5.0 Flash",
        "provider": "openrouter",
        "pricing_text": "$0.018/img",
        "description": "Génération ultra-rapide et économique à faible latence, idéale pour la production visuelle continue.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "meta/muse-image",
        "name": "Meta: Muse Image",
        "provider": "openrouter",
        "pricing_text": "$0.01/img",
        "description": "Modèle agentique avec chaîne de pensée avant rendu, recherche web intégrée et cohérence de style.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "google/gemini-2.5-flash-image",
        "name": "Google: Nano Banana (Gemini 2.5 Flash Image)",
        "provider": "openrouter",
        "pricing_text": "$0.30/M in · $30/M out",
        "description": "Génération d'image polyvalente avec forte compréhension du contexte textuel.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        "supported_resolutions": ["1K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "google/gemini-3.1-flash-lite-image",
        "name": "Google: Nano Banana 2 Lite (Gemini 3.1 Flash Lite Image)",
        "provider": "openrouter",
        "pricing_text": "$0.25/M in · $30/M out",
        "description": "Le modèle image le plus rapide et économique de Google (génération en ~4s), idéal pour l'exploration visuelle.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["1K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "openai/gpt-image-2.5-flare",
        "name": "OpenAI: GPT Image 2.5 Flare",
        "provider": "openrouter",
        "pricing_text": "$8/M in · $30/M out",
        "description": "Palier haute vitesse de la gamme GPT Image 2.5, adapté au prototypage rapide et à l'illustration quotidienne.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "openai/gpt-image-2",
        "name": "OpenAI: GPT Image 2",
        "provider": "openrouter",
        "pricing_text": "$8/M in · $30/M out",
        "description": "Génération d'images haute fidélité d'OpenAI via l'Images API.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "tencent/hy-image-v3.5-preview",
        "name": "Tencent: Hy Image 3.5 Preview",
        "provider": "openrouter",
        "pricing_text": "$1.60/M out",
        "description": "Composition fidèle au prompt, cohérence du sujet et rendu bilingue jusqu'en 4K.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        "supported_resolutions": ["1K", "1.5K", "2K", "4K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "openai/gpt-5.4-image-2",
        "name": "OpenAI: GPT-5.4 Image 2",
        "provider": "openrouter",
        "pricing_text": "$8/M in · $30/M out",
        "description": "Combine le raisonnement multimodal poussé de GPT-5.4 avec la génération visuelle haute définition.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "google/gemini-3-pro-image",
        "name": "Google: Nano Banana Pro (Gemini 3 Pro Image)",
        "provider": "openrouter",
        "pricing_text": "$2/M in · $120/M out",
        "description": "Modèle le plus avancé de Google sur base Gemini 3 Pro. Rendu de texte long, haute fidélité visuelle et sorties 4K.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["1K", "2K", "4K"],
        "supports_image_editing": False,
        "is_top": True,
    },
    {
        "id": "black-forest-labs/flux-3-image-klein",
        "name": "Black Forest Labs: FLUX 3 Image Klein",
        "provider": "openrouter",
        "pricing_text": "$0.008-$0.036/img",
        "description": "FLUX 3 ultra-rapide et abordable, excellent équilibre de photoréalisme et esthétique moderne.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["768", "1K", "1.5K", "2K", "4K"],
        "supports_image_editing": False,
        "is_top": False,
    },
    {
        "id": "black-forest-labs/flux-3-image",
        "name": "Black Forest Labs: FLUX 3 Image",
        "provider": "openrouter",
        "pricing_text": "$0.041-$0.607/img",
        "description": "Rendu visuel d'exception, éclairages cinématiques et fidélité de composition du studio Black Forest Labs.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "supported_resolutions": ["768", "1K", "1.5K", "2K", "4K"],
        "supports_image_editing": False,
        "is_top": False,
    },
    {
        "id": "recraft/recraft-v4.1-flash",
        "name": "Recraft: Recraft V4.1 Flash",
        "provider": "openrouter",
        "pricing_text": "$0.007/img",
        "description": "Spécialisé en design vectoriel, logos, icônes, illustrations et typographie nette.",
        "supported_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
        "supported_resolutions": ["1K", "2K"],
        "supports_image_editing": False,
        "is_top": False,
    },
]


DEFAULT_GOOGLE_CLOUD_MODELS: list[dict[str, Any]] = [
    {
        "id": "google/gemini-2.5-flash-lite",
        "name": "Google: Gemini 2.5 Flash Lite (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": False,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed"],
    },
    {
        "id": "google/gemini-2.5-flash",
        "name": "Google: Gemini 2.5 Flash (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": True,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed", "reasoning_effort"],
    },
    {
        "id": "google/gemini-2.5-pro",
        "name": "Google: Gemini 2.5 Pro (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": True,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed", "reasoning_effort"],
    },
    {
        "id": "google/gemini-3.5-flash-lite",
        "name": "Google: Gemini 3.5 Flash Lite (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": False,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed"],
    },
    {
        "id": "google/gemini-3.8-flash",
        "name": "Google: Gemini 3.8 Flash (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": True,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed", "reasoning_effort"],
    },
    {
        "id": "google/gemini-4-argon",
        "name": "Google: Gemini 4 Argon (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": True,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed", "reasoning_effort"],
    },
    {
        "id": "google/gemini-4-hydrogen",
        "name": "Google: Gemini 4 Hydrogen (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": True,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed", "reasoning_effort"],
    },
    {
        "id": "google/gemini-4-neon",
        "name": "Google: Gemini 4 Neon (Google Cloud)",
        "vision": True,
        "provider": "google",
        "reasoning": True,
        "context_length": 1000000,
        "supported_parameters": ["temperature", "top_p", "seed", "reasoning_effort"],
    },
]


_GOOGLE_CLOUD_MODES = {"auto", "vertex_oauth", "vertex_api_key", "gemini_api", "disabled"}
_GCP_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,29}$")
_GCP_LOCATION_RE = re.compile(r"^[a-z0-9-]{2,40}$")


def _clean_api_key(value: str | SecretStr | None) -> str:
    if isinstance(value, SecretStr):
        raw = value.get_secret_value()
    elif isinstance(value, str):
        raw = value
    else:
        return ""
    cleaned = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        cleaned = cleaned[1:-1].strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    return cleaned


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", str(_REPO_ENV_FILE)), extra="ignore")

    _watch_env: bool = PrivateAttr(default=True)
    _env_mtime_ns: int = PrivateAttr(default=0)
    _explicit_fields: set[str] = PrivateAttr(default_factory=set)

    def __init__(self, **values):
        has_env_arg = "_env_file" in values
        default_env_files = tuple(
            str(p)
            for p in (Path(".env"), _REPO_ENV_FILE)
            if p.resolve() not in _ISOLATED_ENV_PATHS
        )
        env_arg = values.get("_env_file", default_env_files)
        explicit = {k for k in values if not k.startswith("_")}
        init_values = dict(values)
        if not has_env_arg:
            init_values["_env_file"] = default_env_files or None
        super().__init__(**init_values)
        self._explicit_fields = explicit
        self._watch_env = not (has_env_arg and env_arg is None)
        if self._watch_env:
            self.refresh_from_env_file(force=True)

    app_data_dir: Path = Path("./data")
    finance_data_dir: Path | None = None
    finance_quote_ttl_seconds: int = 300
    finance_fundamentals_ttl_hours: int = 360
    finance_exchange_catalog_ttl_hours: int = 24
    finance_exchange_auto_sync_enabled: bool = True
    finance_exchange_auto_sync_codes: str = ""
    database_url: str = ""
    demo_mode: bool = False
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_models: str = '[{"id":"openai/gpt-4o-mini","name":"GPT-4o mini","vision":true},{"id":"mistralai/mistral-small-3.2-24b-instruct","name":"Mistral Small 3.2","vision":true}]'
    default_model: str = "openai/gpt-4o-mini"
    searxng_url: str = ""
    brave_api_key: SecretStr = SecretStr("")
    duckduckgo_enabled: bool = False
    mistral_api_key: SecretStr = SecretStr("")
    ocr_model: str = "mistral-ocr-4-1"
    vision_model: str = ""
    ideogram_api_key: SecretStr = SecretStr("")
    ideogram_image_hosts: str = "ideogram.ai"
    eod_historical_data_key: SecretStr = SecretStr("")
    eleven_labs_key: SecretStr = SecretStr("")
    eleven_labs_model_id: str = "eleven_text_to_sound_v2"
    tts_model: str = "gemini-2.5-flash-tts"
    tts_default_voice: str = "Aoede"
    stt_provider: str = "auto"
    stt_mistral_model: str = "voxtral-mini-latest"
    stt_google_model: str = "gemini-2.5-flash"
    google_api_key: SecretStr = SecretStr("")
    google_cloud_mode: str = "auto"
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    google_application_credentials: str = ""
    vertex_api_key: SecretStr = SecretStr("")
    google_cloud_fallback_openrouter: bool = False
    google_cloud_model_map: str = ""
    cors_origins: str = "http://localhost:3001,http://127.0.0.1:3001"
    session_cookie_name: str = "tchat_session"
    session_cookie_secure: bool = False
    session_days: int = 14
    invitation_days: int = 2
    max_upload_mb: int = 40
    max_context_chars: int = 60000
    context_window_tokens: int = 12000
    summary_trigger_ratio: float = 0.8
    summary_target_ratio: float = 0.4
    summary_min_recent_tokens: int = 2500
    summary_every_messages: int = 12
    max_summary_chars: int = 6000
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2048
    llm_timeout_seconds: int = 480
    summary_temperature: float = 0.1
    summary_max_tokens: int = 900
    deep_search_max_tokens: int = 131072
    learn_mode_max_tokens: int = 98304
    code_mode_max_tokens: int = 131072
    summary_model: str = "openai/gpt-4o-mini"
    search_query_model: str = "google/gemini-3.8-flash"
    web_search_decision_model: str = "google/gemini-3.5-flash-lite"
    deep_search_plan_model: str = "google/gemini-4-argon"
    deep_search_synthesis_model: str = "google/gemini-3.8-flash"
    deep_search_audit_model: str = "openai/gpt-6-astra"
    deep_search_engine: str = "sonar"
    deep_search_model: str = "perplexity/sonar-deep-research"
    blog_model: str = "google/gemini-3.5-flash-lite"
    page_model: str = "google/gemini-2.5-flash"
    presentation_model: str = "google/gemini-2.5-flash-lite"
    image_prompt_model: str = "google/gemini-4-argon"
    skill_prompt_model: str = "google/gemini-4-argon"
    image_models: str = ""
    default_image_model: str = "ideogram-4-5"
    auto_web_search: bool = True
    hermes_enabled: bool = True
    hermes_api_url: str = "http://127.0.0.1:8642"
    hermes_api_key: SecretStr = SecretStr("")
    hermes_default_model: str = "nousresearch/hermes-3-llama-3.1-405b"
    hermes_max_cost_usd: float = 0.25

    @field_validator("llm_api_key", "brave_api_key", "mistral_api_key", "ideogram_api_key", "eod_historical_data_key", "eleven_labs_key", "google_api_key", "vertex_api_key", "hermes_api_key", mode="before")
    @classmethod
    def sanitize_secret_keys(cls, value):
        if isinstance(value, SecretStr):
            return SecretStr(_clean_api_key(value))
        if isinstance(value, str):
            return _clean_api_key(value)
        return value

    @field_validator("google_cloud_mode")
    @classmethod
    def valid_google_cloud_mode(cls, value: str) -> str:
        norm = (value or "auto").strip().lower() or "auto"
        if norm not in _GOOGLE_CLOUD_MODES:
            raise ValueError(
                "GOOGLE_CLOUD_MODE doit être auto, vertex_oauth, vertex_api_key, gemini_api ou disabled"
            )
        return norm

    @field_validator("google_cloud_project")
    @classmethod
    def valid_google_cloud_project(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if cleaned and not _GCP_PROJECT_ID_RE.fullmatch(cleaned):
            raise ValueError("GOOGLE_CLOUD_PROJECT doit être un ID de projet GCP valide (ex. mon-projet-123)")
        return cleaned

    @field_validator("google_cloud_location")
    @classmethod
    def valid_google_cloud_location(cls, value: str) -> str:
        cleaned = (value or "global").strip().lower() or "global"
        if not _GCP_LOCATION_RE.fullmatch(cleaned):
            raise ValueError("GOOGLE_CLOUD_LOCATION doit être une région GCP valide (ex. global, europe-west1, us-central1)")
        return cleaned

    @field_validator("google_application_credentials")
    @classmethod
    def valid_google_application_credentials(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if any(ch in cleaned for ch in ("\r", "\n", "\x00")):
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS contient des caractères interdits")
        return cleaned

    @field_validator("google_cloud_model_map")
    @classmethod
    def valid_google_cloud_model_map(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            return ""
        try:
            parsed = json.loads(cleaned)
        except ValueError as exc:
            raise ValueError("GOOGLE_CLOUD_MODEL_MAP doit être un objet JSON clé->modèle valide") from exc
        if not isinstance(parsed, dict) or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
            for k, v in parsed.items()
        ):
            raise ValueError("GOOGLE_CLOUD_MODEL_MAP doit être un dictionnaire JSON {source: cible} de chaînes non vides")
        return cleaned

    @model_validator(mode="after")
    def valid_auth_lifetimes(self):
        if not 1 <= self.session_days <= 90:
            raise ValueError("SESSION_DAYS doit être compris entre 1 et 90")
        if not 1 <= self.invitation_days <= 7:
            raise ValueError("INVITATION_DAYS doit être compris entre 1 et 7")
        return self

    @field_validator("cors_origins")
    @classmethod
    def no_wildcard_cors_origins(cls, value: str) -> str:
        origins = json.loads(value) if value.strip().startswith("[") else value.split(",")
        if not isinstance(origins, list) or any(not isinstance(origin, str) or origin.strip() == "*" for origin in origins):
            raise ValueError("CORS_ORIGINS doit lister des origines explicites; le wildcard est interdit avec les sessions")
        return value

    @field_validator("ideogram_image_hosts")
    @classmethod
    def valid_ideogram_image_hosts(cls, value: str) -> str:
        hosts = list(dict.fromkeys(host.strip().lower() for host in value.split(",") if host.strip()))
        if not hosts or len(hosts) > 20:
            raise ValueError("IDEOGRAM_IMAGE_HOSTS doit contenir entre 1 et 20 noms DNS exacts séparés par des virgules")
        for host in hosts:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError("IDEOGRAM_IMAGE_HOSTS refuse les adresses IP")
            if (len(host) > 253 or "." not in host or host.endswith((".localhost", ".local", ".internal"))
                    or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split("."))):
                raise ValueError("IDEOGRAM_IMAGE_HOSTS accepte uniquement des noms DNS publics exacts sans wildcard, schéma, chemin ou port")
        return ",".join(hosts)

    @field_validator("hermes_api_url")
    @classmethod
    def valid_hermes_api_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if cleaned and not cleaned.startswith(("http://", "https://")):
            raise ValueError("HERMES_API_URL doit commencer par http:// ou https://")
        return cleaned

    @field_validator("hermes_max_cost_usd")
    @classmethod
    def valid_hermes_max_cost_usd(cls, value: float) -> float:
        if not 0.0 <= value <= 50.0:
            raise ValueError("HERMES_MAX_COST_USD doit être compris entre 0 et 50 USD")
        return float(value)

    @field_validator("max_upload_mb")
    @classmethod
    def valid_upload_limit(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("MAX_UPLOAD_MB doit être compris entre 1 et 100")
        return value

    @field_validator("max_context_chars")
    @classmethod
    def valid_context_limit(cls, value: int) -> int:
        if not 10000 <= value <= 200000:
            raise ValueError("MAX_CONTEXT_CHARS doit être compris entre 10000 et 200000")
        return value

    @field_validator("llm_temperature", "summary_temperature")
    @classmethod
    def valid_temperature(cls, value: float) -> float:
        if not 0 <= value <= 2:
            raise ValueError("Les températures doivent être comprises entre 0 et 2")
        return value

    @field_validator("llm_max_tokens", "summary_max_tokens", "deep_search_max_tokens", "learn_mode_max_tokens", "code_mode_max_tokens")
    @classmethod
    def valid_max_tokens(cls, value: int) -> int:
        if not 1 <= value <= 200000:
            raise ValueError("Le nombre maximal de tokens doit être compris entre 1 et 200000")
        return value

    @field_validator("llm_timeout_seconds")
    @classmethod
    def valid_llm_timeout_seconds(cls, value: int) -> int:
        if not 30 <= value <= 1800:
            raise ValueError("LLM_TIMEOUT_SECONDS doit être compris entre 30 et 1800 secondes")
        return value

    @field_validator("summary_model", "search_query_model", "web_search_decision_model", "deep_search_plan_model", "presentation_model")
    @classmethod
    def valid_auxiliary_model(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 200:
            raise ValueError("Les identifiants de modèles doivent contenir entre 1 et 200 caractères")
        return value

    @field_validator("ocr_model", "vision_model")
    @classmethod
    def valid_document_models(cls, value: str, info) -> str:
        value = value.strip()
        if len(value) > 200 or (info.field_name == "ocr_model" and not value):
            raise ValueError("Le modèle OCR doit être renseigné ; les identifiants sont limités à 200 caractères")
        return value

    @field_validator("summary_every_messages")
    @classmethod
    def valid_summary_interval(cls, value: int) -> int:
        if not 8 <= value <= 100:
            raise ValueError("SUMMARY_EVERY_MESSAGES doit être compris entre 8 et 100")
        return value

    @field_validator("max_summary_chars")
    @classmethod
    def valid_summary_limit(cls, value: int) -> int:
        if not 1000 <= value <= 10000:
            raise ValueError("MAX_SUMMARY_CHARS doit être compris entre 1000 et 10000")
        return value

    @field_validator("context_window_tokens")
    @classmethod
    def valid_context_tokens(cls, value: int) -> int:
        if not 2000 <= value <= 2000000:
            raise ValueError("CONTEXT_WINDOW_TOKENS doit être compris entre 2000 et 2000000")
        return value

    @field_validator("summary_trigger_ratio")
    @classmethod
    def valid_trigger_ratio(cls, value: float) -> float:
        if not 0.5 <= value <= 0.95:
            raise ValueError("SUMMARY_TRIGGER_RATIO doit être compris entre 0.5 et 0.95")
        return value

    @field_validator("summary_target_ratio")
    @classmethod
    def valid_target_ratio(cls, value: float) -> float:
        if not 0.1 <= value <= 0.7:
            raise ValueError("SUMMARY_TARGET_RATIO doit être compris entre 0.1 et 0.7")
        return value

    @field_validator("summary_min_recent_tokens")
    @classmethod
    def valid_min_recent_tokens(cls, value: int) -> int:
        if not 500 <= value <= 30000:
            raise ValueError("SUMMARY_MIN_RECENT_TOKENS doit être compris entre 500 et 30000")
        return value

    @property
    def configured_models(self) -> list[dict]:
        from .sampling import DEFAULT_SUPPORTED_PARAMETERS, extract_supported_creativity_parameters
        try:
            values = json.loads(self.llm_models)
            if not isinstance(values, list) or not values:
                raise ValueError()
            result = []
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
                    raise ValueError()
                raw_sup = item.get("supported_parameters")
                sup_params = (
                    extract_supported_creativity_parameters(raw_sup)
                    if raw_sup is not None
                    else list(DEFAULT_SUPPORTED_PARAMETERS)
                )
                result.append({
                    "id": item["id"],
                    "name": str(item.get("name", item["id"])),
                    "vision": bool(item.get("vision", False)),
                    "provider": item["id"].split("/")[0] if "/" in item["id"] else "custom",
                    "supported_parameters": sup_params,
                })
            if self.default_model not in {item["id"] for item in result}:
                raise ValueError()
            return result
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("LLM_MODELS doit être un tableau JSON de modèles; DEFAULT_MODEL doit être présent") from exc

    def get_model_supported_parameters(self, model_id: str, force_refresh: bool = False) -> list[str]:
        from .sampling import DEFAULT_SUPPORTED_PARAMETERS
        mid = (model_id or "").strip()
        if not mid:
            return list(DEFAULT_SUPPORTED_PARAMETERS)
        if not force_refresh:
            for item in self.models:
                if item.get("id") == mid and item.get("supported_parameters") is not None:
                    return list(item["supported_parameters"])
        if self.demo_mode or not self.enabled(self.llm_api_key):
            candidates = list(self.configured_models)
            if not self.demo_mode and self.google_cloud_enabled:
                candidates.extend(DEFAULT_GOOGLE_CLOUD_MODELS)
            for item in candidates:
                if item.get("id") == mid and item.get("supported_parameters") is not None:
                    return list(item["supported_parameters"])
            return list(DEFAULT_SUPPORTED_PARAMETERS)
        from .openrouter import fetch_openrouter_model_parameters
        key = _clean_api_key(self.llm_api_key)
        return fetch_openrouter_model_parameters(
            model_id=mid,
            api_key=key,
            base_url=self.llm_base_url,
            force_refresh=force_refresh,
        )

    def get_models(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        self.refresh_from_env_file()
        fallback = self.configured_models
        if self.demo_mode:
            return fallback
        has_openrouter = self.enabled(self.llm_api_key)
        has_gc = self.google_cloud_enabled
        if not has_openrouter:
            if has_gc:
                merged = [dict(item) for item in DEFAULT_GOOGLE_CLOUD_MODELS]
                seen = {m["id"] for m in merged}
                for item in fallback:
                    if item["id"] not in seen:
                        merged.append(item)
                        seen.add(item["id"])
                return merged
            return fallback

        from .openrouter import fetch_openrouter_models
        key = _clean_api_key(self.llm_api_key)
        dynamic = fetch_openrouter_models(api_key=key, base_url=self.llm_base_url, force_refresh=force_refresh)
        if dynamic:
            known_ids = {m["id"] for m in dynamic}
            if has_gc:
                for item in DEFAULT_GOOGLE_CLOUD_MODELS:
                    if item["id"] not in known_ids:
                        dynamic.append(dict(item))
                        known_ids.add(item["id"])
            if self.default_model and self.default_model not in known_ids:
                fallback_entry = next((m for m in fallback if m["id"] == self.default_model), None)
                if fallback_entry:
                    dynamic.insert(0, fallback_entry)
            return dynamic
        if has_gc:
            merged = [dict(item) for item in DEFAULT_GOOGLE_CLOUD_MODELS]
            seen = {m["id"] for m in merged}
            for item in fallback:
                if item["id"] not in seen:
                    merged.append(item)
                    seen.add(item["id"])
            return merged
        return fallback

    @property
    def models(self) -> list[dict]:
        return self.get_models(force_refresh=False)

    def get_image_models(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        self.refresh_from_env_file()
        if self.demo_mode:
            return []
        has_ideogram = self.enabled(self.ideogram_api_key)
        has_openrouter = self.enabled(self.llm_api_key)
        has_google_cloud = self.google_cloud_enabled

        # Check explicit custom override in env first
        if self.image_models.strip():
            try:
                parsed = json.loads(self.image_models)
                if isinstance(parsed, list) and parsed:
                    filtered = []
                    for item in parsed:
                        prov = item.get("provider", "openrouter")
                        is_google_img = str(item.get("id", "")).lower().startswith("google/")
                        if prov == "ideogram" and not has_ideogram:
                            continue
                        if prov == "openrouter" and not has_openrouter and not (has_google_cloud and is_google_img):
                            continue
                        entry = {
                            "id": str(item["id"]),
                            "name": str(item.get("name", item["id"])),
                            "provider": prov,
                            "pricing_text": str(item.get("pricing_text", "Tarif standard")),
                            "description": str(item.get("description", "")),
                            "supported_aspect_ratios": item.get("supported_aspect_ratios", []),
                            "supported_resolutions": item.get("supported_resolutions", []),
                            "supports_image_editing": prov == "ideogram",
                            "is_top": bool(item.get("is_top", False)),
                        }
                        if has_google_cloud and is_google_img:
                            entry["routed_via"] = "google_cloud"
                        filtered.append(entry)
                    return filtered
            except Exception:
                pass

        results: list[dict[str, Any]] = []

        # 1. Modèles Ideogram (4.5, 4.0, 3.0, Auto) inclus en tête de liste
        for idx, item in enumerate(IDEOGRAM_IMAGE_MODELS):
            results.append({**item, "_rank": -len(IDEOGRAM_IMAGE_MODELS) + idx})

        # 2. Dynamic OpenRouter image models if enabled
        if has_openrouter:
            from .openrouter import fetch_openrouter_image_models
            key = _clean_api_key(self.llm_api_key)
            dynamic = fetch_openrouter_image_models(
                api_key=key,
                base_url=self.llm_base_url,
                force_refresh=force_refresh,
            )
            if dynamic:
                if has_google_cloud:
                    results.extend(
                        {**m, "routed_via": "google_cloud"}
                        if str(m.get("id", "")).lower().startswith("google/")
                        else m
                        for m in dynamic
                    )
                else:
                    results.extend(dynamic)
                return results

        # 3. Fallback to default catalog if dynamic fetch is empty or offline
        for item in DEFAULT_IMAGE_MODELS:
            prov = item.get("provider", "openrouter")
            if prov == "ideogram":
                continue
            is_google_img = str(item.get("id", "")).lower().startswith("google/")
            if prov == "openrouter" and not has_openrouter and not (has_google_cloud and is_google_img):
                continue
            if has_google_cloud and is_google_img:
                results.append({**item, "routed_via": "google_cloud"})
            else:
                results.append(item)

        return results

    @property
    def available_image_models(self) -> list[dict[str, Any]]:
        return self.get_image_models(force_refresh=False)

    @property
    def effective_default_image_model(self) -> str:
        models = self.available_image_models
        ids = {m["id"] for m in models}
        if self.default_image_model in ids:
            return self.default_image_model
        return models[0]["id"] if models else self.default_image_model

    @property
    def origins(self) -> list[str]:
        if self.cors_origins.strip().startswith("["):
            return json.loads(self.cors_origins)
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.app_data_dir.resolve() / 'chat.db'}"

    @property
    def resolved_finance_data_dir(self) -> Path:
        return (self.finance_data_dir or (self.app_data_dir / "finance")).resolve()

    def refresh_from_env_file(self, force: bool = False) -> None:
        if not self._watch_env:
            return
        candidates = [
            p for p in (Path(".env"), _REPO_ENV_FILE)
            if p.resolve() not in _ISOLATED_ENV_PATHS
        ]
        env_path = next((path for path in candidates if path.is_file()), None)
        if env_path is None:
            return
        try:
            mtime_ns = env_path.stat().st_mtime_ns
        except OSError:
            return
        if not force and mtime_ns == self._env_mtime_ns:
            return
        self._env_mtime_ns = mtime_ns
        parsed = dotenv_values(env_path)
        secret_fields = (
            "llm_api_key",
            "brave_api_key",
            "mistral_api_key",
            "ideogram_api_key",
            "eod_historical_data_key",
            "eleven_labs_key",
            "google_api_key",
            "vertex_api_key",
            "hermes_api_key",
        )
        for field_name in secret_fields:
            if field_name in self._explicit_fields:
                continue
            env_name = field_name.upper()
            raw_val = parsed.get(env_name)
            if field_name == "eleven_labs_key" and raw_val is None:
                raw_val = parsed.get("ELEVENLABS_API_KEY") or parsed.get("ELEVEN_LABS_API_KEY")
            elif field_name == "google_api_key" and raw_val is None:
                raw_val = parsed.get("GOOGLE_API_KEY") or parsed.get("GEMINI_API_KEY")
            elif field_name == "vertex_api_key" and raw_val is None:
                raw_val = parsed.get("VERTEX_API_KEY") or parsed.get("GOOGLE_CLOUD_API_KEY")
            if raw_val is not None:
                cleaned = _clean_api_key(raw_val)
                if cleaned or force is False:
                    setattr(self, field_name, SecretStr(cleaned))
        str_fields = (
            "llm_base_url",
            "ocr_model",
            "vision_model",
            "default_model",
            "llm_models",
            "summary_model",
            "search_query_model",
            "web_search_decision_model",
            "deep_search_plan_model",
            "deep_search_synthesis_model",
            "deep_search_engine",
            "deep_search_model",
            "blog_model",
            "page_model",
            "presentation_model",
            "image_prompt_model",
            "skill_prompt_model",
            "image_models",
            "default_image_model",
            "hermes_default_model",
            "google_cloud_mode",
            "google_cloud_project",
            "google_cloud_location",
            "google_application_credentials",
            "google_cloud_model_map",
            "tts_model",
            "tts_default_voice",
            "stt_provider",
            "stt_mistral_model",
            "stt_google_model",
        )
        clearable_fields = {"google_cloud_project", "google_application_credentials", "google_cloud_model_map"}
        for field_name in str_fields:
            if field_name in self._explicit_fields:
                continue
            env_name = field_name.upper()
            raw_val = parsed.get(env_name)
            if field_name == "google_cloud_project" and raw_val is None:
                raw_val = parsed.get("VERTEX_PROJECT_ID")
            elif field_name == "google_cloud_location" and raw_val is None:
                raw_val = parsed.get("VERTEX_LOCATION")
            if isinstance(raw_val, str):
                val = raw_val.strip()
                if not val and (field_name not in clearable_fields or force):
                    continue
                try:
                    if field_name == "google_cloud_mode":
                        val = self.valid_google_cloud_mode(val)
                    elif field_name == "google_cloud_project":
                        val = self.valid_google_cloud_project(val)
                    elif field_name == "google_cloud_location":
                        val = self.valid_google_cloud_location(val)
                    elif field_name == "google_application_credentials":
                        val = self.valid_google_application_credentials(val)
                    elif field_name == "google_cloud_model_map":
                        val = self.valid_google_cloud_model_map(val)
                except ValueError:
                    continue
                setattr(self, field_name, val)
        if "demo_mode" not in self._explicit_fields and isinstance(parsed.get("DEMO_MODE"), str):
            val = parsed["DEMO_MODE"].strip().lower()
            if val in ("true", "1", "yes", "false", "0", "no"):
                self.demo_mode = val in ("true", "1", "yes")
        if "duckduckgo_enabled" not in self._explicit_fields and isinstance(parsed.get("DUCKDUCKGO_ENABLED"), str):
            val = parsed["DUCKDUCKGO_ENABLED"].strip().lower()
            if val in ("true", "1", "yes", "false", "0", "no"):
                self.duckduckgo_enabled = val in ("true", "1", "yes")
        if "auto_web_search" not in self._explicit_fields and isinstance(parsed.get("AUTO_WEB_SEARCH"), str):
            val = parsed["AUTO_WEB_SEARCH"].strip().lower()
            if val in ("true", "1", "yes", "false", "0", "no"):
                self.auto_web_search = val in ("true", "1", "yes")
        if "hermes_enabled" not in self._explicit_fields and isinstance(parsed.get("HERMES_ENABLED"), str):
            val = parsed["HERMES_ENABLED"].strip().lower()
            if val in ("true", "1", "yes", "false", "0", "no"):
                self.hermes_enabled = val in ("true", "1", "yes")
        if "google_cloud_fallback_openrouter" not in self._explicit_fields and isinstance(parsed.get("GOOGLE_CLOUD_FALLBACK_OPENROUTER"), str):
            val = parsed["GOOGLE_CLOUD_FALLBACK_OPENROUTER"].strip().lower()
            if val in ("true", "1", "yes", "false", "0", "no"):
                self.google_cloud_fallback_openrouter = val in ("true", "1", "yes")
        if "hermes_max_cost_usd" not in self._explicit_fields and isinstance(parsed.get("HERMES_MAX_COST_USD"), str):
            try:
                budget = float(parsed["HERMES_MAX_COST_USD"].strip())
                if 0.0 <= budget <= 50.0:
                    self.hermes_max_cost_usd = budget
            except ValueError:
                pass
        if "llm_timeout_seconds" not in self._explicit_fields and isinstance(parsed.get("LLM_TIMEOUT_SECONDS"), str):
            try:
                timeout_s = int(parsed["LLM_TIMEOUT_SECONDS"].strip())
                if 30 <= timeout_s <= 1800:
                    self.llm_timeout_seconds = timeout_s
            except ValueError:
                pass

    @property
    def active_google_cloud_mode(self) -> str | None:
        self.refresh_from_env_file()
        if self.demo_mode:
            return None
        mode = (self.google_cloud_mode or "auto").strip().lower()
        if mode == "disabled":
            return None
        if mode in {"vertex_oauth", "vertex_api_key", "gemini_api"}:
            return mode
        if mode == "auto":
            if (self.google_cloud_project or "").strip():
                return "vertex_oauth"
            if _clean_api_key(self.vertex_api_key):
                return "vertex_api_key"
        return None

    @property
    def google_cloud_enabled(self) -> bool:
        return not self.demo_mode and self.active_google_cloud_mode is not None

    def has_llm_for_model(self, model: str | None = None) -> bool:
        from .google_cloud import has_llm_access
        return has_llm_access(self, model)

    def enabled(self, key: SecretStr) -> bool:
        self.refresh_from_env_file()
        return not self.demo_mode and bool(_clean_api_key(key))

    @property
    def web_search_enabled(self) -> bool:
        self.refresh_from_env_file()
        return not self.demo_mode and (
            bool(self.searxng_url.strip())
            or self.enabled(self.brave_api_key)
            or self.duckduckgo_enabled
        )
