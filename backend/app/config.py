import json
import ipaddress
import re
from pathlib import Path

from dotenv import dotenv_values
from pydantic import PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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
        env_arg = values.get("_env_file", (".env", str(_REPO_ENV_FILE)))
        explicit = {k for k in values if not k.startswith("_")}
        super().__init__(**values)
        self._explicit_fields = explicit
        self._watch_env = not (has_env_arg and env_arg is None)
        if self._watch_env:
            self.refresh_from_env_file(force=True)

    app_data_dir: Path = Path("./data")
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
    cors_origins: str = "http://localhost:3001,http://127.0.0.1:3001"
    session_cookie_name: str = "tchat_session"
    session_cookie_secure: bool = False
    session_days: int = 14
    invitation_days: int = 2
    max_upload_mb: int = 20
    max_context_chars: int = 60000
    summary_every_messages: int = 12
    max_summary_chars: int = 6000
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    summary_temperature: float = 0.2
    summary_max_tokens: int = 900
    summary_model: str = "openai/gpt-4o-mini"
    search_query_model: str = "mistralai/mistral-small-3.2-24b-instruct"
    blog_model: str = "google/gemini-3.5-flash-lite"

    @field_validator("llm_api_key", "brave_api_key", "mistral_api_key", "ideogram_api_key", mode="before")
    @classmethod
    def sanitize_secret_keys(cls, value):
        if isinstance(value, SecretStr):
            return SecretStr(_clean_api_key(value))
        if isinstance(value, str):
            return _clean_api_key(value)
        return value

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

    @field_validator("llm_max_tokens", "summary_max_tokens")
    @classmethod
    def valid_max_tokens(cls, value: int) -> int:
        if not 1 <= value <= 100000:
            raise ValueError("Le nombre maximal de tokens doit être compris entre 1 et 100000")
        return value

    @field_validator("summary_model", "search_query_model")
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

    @property
    def models(self) -> list[dict]:
        try:
            values = json.loads(self.llm_models)
            if not isinstance(values, list) or not values:
                raise ValueError()
            result = []
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
                    raise ValueError()
                result.append({"id": item["id"], "name": str(item.get("name", item["id"])), "vision": bool(item.get("vision", False))})
            if self.default_model not in {item["id"] for item in result}:
                raise ValueError()
            return result
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("LLM_MODELS doit être un tableau JSON de modèles; DEFAULT_MODEL doit être présent") from exc

    @property
    def origins(self) -> list[str]:
        if self.cors_origins.strip().startswith("["):
            return json.loads(self.cors_origins)
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.app_data_dir.resolve() / 'chat.db'}"

    def refresh_from_env_file(self, force: bool = False) -> None:
        if not self._watch_env:
            return
        candidates = [Path(".env"), _REPO_ENV_FILE]
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
        secret_fields = ("llm_api_key", "brave_api_key", "mistral_api_key", "ideogram_api_key")
        for field_name in secret_fields:
            if field_name in self._explicit_fields:
                continue
            env_name = field_name.upper()
            if env_name in parsed and parsed[env_name] is not None:
                cleaned = _clean_api_key(parsed[env_name])
                if cleaned or force is False:
                    setattr(self, field_name, SecretStr(cleaned))
        str_fields = ("llm_base_url", "ocr_model", "vision_model", "default_model", "llm_models", "summary_model", "search_query_model", "blog_model")
        for field_name in str_fields:
            if field_name in self._explicit_fields:
                continue
            env_name = field_name.upper()
            raw_val = parsed.get(env_name)
            if isinstance(raw_val, str) and raw_val.strip():
                setattr(self, field_name, raw_val.strip())
        if "demo_mode" not in self._explicit_fields and isinstance(parsed.get("DEMO_MODE"), str):
            val = parsed["DEMO_MODE"].strip().lower()
            if val in ("true", "1", "yes", "false", "0", "no"):
                self.demo_mode = val in ("true", "1", "yes")
        if "duckduckgo_enabled" not in self._explicit_fields and isinstance(parsed.get("DUCKDUCKGO_ENABLED"), str):
            val = parsed["DUCKDUCKGO_ENABLED"].strip().lower()
            if val in ("true", "1", "yes", "false", "0", "no"):
                self.duckduckgo_enabled = val in ("true", "1", "yes")

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
