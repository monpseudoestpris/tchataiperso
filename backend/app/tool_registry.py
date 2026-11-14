"""Registre d'outils métier partagé entre `local_autonomous` (OpenRouter) et Hermes Gateway (MCP).

Fournit :
- Des schémas d'entrée/sortie Pydantic stricts et une réponse structurée commune (`ToolResult`).
- Le contrôle des permissions utilisateur (`allowed_permissions`), la validation des arguments,
  le timeout d'exécution et une gestion d'erreurs unifiée.
- Deux adaptateurs : `to_openai_tools()` pour OpenRouter et `to_mcp_tools()` pour MCP JSON-RPC.
- L'outil métier `clair_create_page` qui réutilise strictement `page_service.create_draft_web_page`
  (création uniquement en brouillon, sans publication ni écrasement).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import sessionmaker

from . import providers
from .config import Settings
from .page_service import create_draft_web_page

_logger = logging.getLogger("uvicorn.error")

PERMISSION_CREATE_PAGE_DRAFT = "pages:create_draft"


class ToolResult(BaseModel):
    """Réponse structurée commune à tous les outils métier cLAIr."""

    success: bool
    tool_name: str
    draft_id: str | None = None
    title: str | None = None
    slug: str | None = None
    is_published: bool = False
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ClairPageSourceInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(default="", max_length=200)
    url: str = Field(min_length=1, max_length=500)


class ClairCreatePageInput(BaseModel):
    """Schéma d'entrée validé pour la création d'un brouillon cLAIr Page."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=200, description="Titre clair de la page Web brouillon.")
    content: str = Field(
        min_length=10,
        max_length=12000,
        description="Contenu structuré (Markdown ou plan détaillé) à transformer en page cLAIr.",
    )
    sources: list[ClairPageSourceInput | str] = Field(
        default_factory=list,
        max_length=20,
        description="Liste des sources officielles vérifiées (URLs ou objets {title, url}).",
    )
    page_type: str = Field(
        default="educational",
        max_length=40,
        description="Style éditorial : educational, landing, documentation, dashboard.",
    )

    @field_validator("title", "content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le champ ne peut pas être vide.")
        return cleaned

    @field_validator("page_type")
    @classmethod
    def valid_page_type(cls, value: str) -> str:
        allowed = {"educational", "landing", "documentation", "dashboard", "report"}
        cleaned = (value or "educational").strip().lower()
        return cleaned if cleaned in allowed else "educational"


@dataclass
class ToolExecutionContext:
    settings: Settings
    sessions: sessionmaker | None
    user_id: str | None
    allowed_permissions: set[str] = field(default_factory=set)
    model: str | None = None
    sources_acc: list[dict[str, str]] = field(default_factory=list)
    created_pages: list[dict[str, Any]] = field(default_factory=list)


ToolHandler = Callable[[BaseModel, ToolExecutionContext], Awaitable[ToolResult]]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    input_schema: type[BaseModel]
    required_permission: str
    timeout_seconds: float
    handler: ToolHandler


class ToolRegistry:
    """Registre centralisé des outils métier cLAIr."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    @staticmethod
    def normalize_tool_name(name: str) -> str:
        clean = (name or "").strip()
        if clean.startswith("mcp__") and "__" in clean[5:]:
            return clean.split("__", 2)[-1]
        if clean.startswith("mcp_"):
            parts = clean.split("_")
            if len(parts) >= 3 and parts[0] == "mcp":
                return "_".join(parts[2:])
        return clean

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool | None:
        if name in self._tools:
            return self._tools[name]
        normalized = self.normalize_tool_name(name)
        return self._tools.get(normalized)

    def list_authorized(self, allowed_permissions: set[str]) -> list[RegisteredTool]:
        return [t for t in self._tools.values() if t.required_permission in allowed_permissions]

    def to_openai_tools(self, allowed_permissions: set[str]) -> list[dict[str, Any]]:
        """Adaptateur OpenRouter / OpenAI `tools`."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema.model_json_schema(),
                },
            }
            for tool in self.list_authorized(allowed_permissions)
        ]

    def to_mcp_tools(self, allowed_permissions: set[str]) -> list[dict[str, Any]]:
        """Adaptateur MCP `tools/list` pour Hermes Gateway."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema.model_json_schema(),
            }
            for tool in self.list_authorized(allowed_permissions)
        ]

    async def execute(
        self,
        name: str,
        raw_args: str | dict[str, Any] | None,
        ctx: ToolExecutionContext,
    ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, tool_name=name, error=f"Outil inconnu : {name}")

        if tool.required_permission not in ctx.allowed_permissions:
            return ToolResult(
                success=False,
                tool_name=name,
                error=(
                    f"Permission refusée pour `{name}` : l'utilisateur n'a pas autorisé "
                    f"`{tool.required_permission}` pour cette mission."
                ),
            )

        try:
            if isinstance(raw_args, str):
                parsed = json.loads(raw_args) if raw_args.strip() else {}
            elif isinstance(raw_args, dict):
                parsed = raw_args
            else:
                parsed = {}
            if not isinstance(parsed, dict):
                raise ValueError("Les arguments doivent former un objet JSON.")
            validated = tool.input_schema.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"Arguments invalides : {exc}",
            )

        try:
            return await asyncio.wait_for(tool.handler(validated, ctx), timeout=tool.timeout_seconds)
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"Délai d'exécution dépassé ({int(tool.timeout_seconds)} s) pour `{name}`.",
            )
        except HTTPException as exc:
            return ToolResult(success=False, tool_name=name, error=str(exc.detail))
        except providers.ProviderError as exc:
            return ToolResult(success=False, tool_name=name, error=str(exc))
        except Exception as exc:
            _logger.exception("Erreur inattendue de l'outil %s: %s", name, exc)
            return ToolResult(success=False, tool_name=name, error=f"Échec interne de `{name}`.")


def _format_sources_for_page_prompt(sources: list[ClairPageSourceInput | str]) -> str:
    if not sources:
        return ""
    lines = ["## Sources vérifiées à citer"]
    for idx, src in enumerate(sources, start=1):
        if isinstance(src, str):
            clean = src.strip()
            if clean:
                lines.append(f"[{idx}] {clean}")
        else:
            label = src.title.strip() or src.url.strip()
            lines.append(f"[{idx}] {label} — {src.url.strip()}")
    return "\n".join(lines) if len(lines) > 1 else ""


async def _handle_clair_create_page(args: BaseModel, ctx: ToolExecutionContext) -> ToolResult:
    assert isinstance(args, ClairCreatePageInput)
    if ctx.sessions is None or not ctx.user_id:
        return ToolResult(
            success=False,
            tool_name="clair_create_page",
            error="Contexte utilisateur/base indisponible pour créer un brouillon cLAIr Page.",
        )

    sources_block = _format_sources_for_page_prompt(args.sources)
    prompt_parts = [
        f"Crée une page Web cLAIr structurée et soignée intitulée « {args.title} ».",
        "",
        "## Contenu structuré à mettre en page",
        args.content,
    ]
    if sources_block:
        prompt_parts.extend(["", sources_block])
    full_prompt = "\n".join(prompt_parts)

    page_json = await create_draft_web_page(
        settings=ctx.settings,
        sessions=ctx.sessions,
        user_id=ctx.user_id,
        prompt=full_prompt,
        title=args.title,
        model=ctx.model,
        page_type=args.page_type,
    )

    draft_summary = {
        "id": page_json["id"],
        "title": page_json["title"],
        "slug": page_json["slug"],
        "is_published": False,
    }
    ctx.created_pages.append(draft_summary)

    return ToolResult(
        success=True,
        tool_name="clair_create_page",
        draft_id=str(page_json["id"]),
        title=str(page_json["title"]),
        slug=str(page_json["slug"]),
        is_published=False,
        data={
            "page_id": page_json["id"],
            "title": page_json["title"],
            "slug": page_json["slug"],
            "is_published": False,
            "status": "draft",
            "sources_count": len(args.sources),
            "ui_action": "open_pages",
        },
    )


CLAIR_TOOL_REGISTRY = ToolRegistry()
CLAIR_TOOL_REGISTRY.register(
    RegisteredTool(
        name="clair_create_page",
        description=(
            "Crée un NOUVEAU brouillon de page Web dans cLAIr Pages (jamais publié automatiquement, "
            "n'écrase aucune page existante). À utiliser uniquement lorsque l'utilisateur demande "
            "ou autorise la création d'une page Web structurée."
        ),
        input_schema=ClairCreatePageInput,
        required_permission=PERMISSION_CREATE_PAGE_DRAFT,
        timeout_seconds=90.0,
        handler=_handle_clair_create_page,
    )
)


def permissions_from_enabled_tools(enabled_tools: list[str]) -> set[str]:
    """Convertit les options cochées par l'utilisateur en permissions explicites du registre."""
    perms: set[str] = set()
    if "create_page" in enabled_tools:
        perms.add(PERMISSION_CREATE_PAGE_DRAFT)
    return perms
