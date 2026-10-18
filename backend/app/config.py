import json
import ipaddress
import re
from pathlib import Path

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_data_dir: Path = Path("./data")
    database_url: str = ""
    demo_mode: bool = False
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_models: str = '[{"id":"openai/gpt-4o-mini","name":"GPT-4o mini","vision":true},{"id":"mistralai/mistral-small-3.2-24b-instruct","name":"Mistral Small 3.2","vision":true}]'
    default_model: str = "openai/gpt-4o-mini"
    brave_api_key: SecretStr = SecretStr("")
    mistral_api_key: SecretStr = SecretStr("")
    ideogram_api_key: SecretStr = SecretStr("")
    ideogram_image_hosts: str = "ideogram.ai"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    session_cookie_name: str = "tchat_session"
    session_cookie_secure: bool = False
    session_days: int = 14
    invitation_days: int = 2
    max_upload_mb: int = 20
    max_context_chars: int = 60000
    summary_every_messages: int = 12
    max_summary_chars: int = 6000

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

    def enabled(self, key: SecretStr) -> bool:
        return not self.demo_mode and bool(key.get_secret_value())
