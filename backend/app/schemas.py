import re

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=48)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,47}", normalized):
            raise ValueError("Identifiant invalide")
        return normalized


class AcceptInvitation(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    username: str = Field(min_length=3, max_length=48)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,47}", normalized):
            raise ValueError("Identifiant invalide")
        return normalized


class AdminUpdateUser(BaseModel):
    active: bool


class CreateConversation(BaseModel):
    title: str = Field(default="Nouvelle conversation", min_length=1, max_length=200)
    model: str | None = None


class UpdateConversation(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = None


class SendMessage(BaseModel):
    content: str = Field(default="", max_length=20000)
    model: str | None = None
    web_search: bool = False
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("attachment_ids")
    @classmethod
    def no_duplicate_attachments(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Pièces jointes dupliquées")
        return values


class CreateMemory(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CreateImage(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    aspect_ratio: str = "1:1"
