"""Adaptateur MCP (JSON-RPC 2.0 sur HTTP) exposant le Tool Registry cLAIr à Hermes Gateway.

Permet au conteneur `clair-hermes` (`nousresearch/hermes-agent`, via `mcp_servers` dans
`~/.hermes/config.yaml`) de découvrir (`tools/list`) et d'exécuter (`tools/call`) les outils
métier cLAIr avec les mêmes règles de validation, permissions utilisateur et réponse
structurée (`ToolResult`) que le moteur `local_autonomous`.
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import get_sessions, get_settings
from ..tool_registry import CLAIR_TOOL_REGISTRY, ToolExecutionContext

router = APIRouter(prefix="/api/hermes", tags=["hermes-mcp"])

_LEASE_TTL_SECONDS = 300.0


@dataclass
class GatewayMissionLease:
    session_id: str
    user_id: str
    allowed_permissions: set[str]
    model: str | None = None
    mission_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    created_pages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)


_ACTIVE_LEASES: dict[str, GatewayMissionLease] = {}


def _prune_expired_leases() -> None:
    now_ts = time.monotonic()
    expired = [sid for sid, lease in _ACTIVE_LEASES.items() if (now_ts - lease.created_at) > _LEASE_TTL_SECONDS]
    for sid in expired:
        _ACTIVE_LEASES.pop(sid, None)


def register_gateway_mission_lease(
    session_id: str,
    user_id: str,
    allowed_permissions: set[str],
    model: str | None = None,
) -> GatewayMissionLease:
    _prune_expired_leases()
    lease = GatewayMissionLease(
        session_id=session_id,
        user_id=user_id,
        allowed_permissions=set(allowed_permissions),
        model=model,
    )
    _ACTIVE_LEASES[session_id] = lease
    return lease


def unregister_gateway_mission_lease(session_id: str) -> list[dict[str, Any]]:
    lease = _ACTIVE_LEASES.pop(session_id, None)
    return list(lease.created_pages) if lease else []


def resolve_gateway_mission_lease(
    session_id: str | None,
    mission_token: str | None = None,
    *,
    require_token: bool = False,
) -> GatewayMissionLease | None:
    """Résout strictement le bail de mission correspondant à `session_id` (aucun repli inter-utilisateur)."""
    _prune_expired_leases()
    clean_sid = (session_id or "").strip()
    if not clean_sid:
        return None
    lease = _ACTIVE_LEASES.get(clean_sid)
    if lease is None:
        return None
    if require_token:
        clean_token = (mission_token or "").strip()
        if not clean_token or not hmac.compare_digest(lease.mission_token, clean_token):
            return None
    return lease


def _verify_mcp_bearer(settings: Settings, authorization: str | None) -> None:
    expected_secret = getattr(settings, "hermes_api_key", None)
    expected = expected_secret.get_secret_value().strip() if expected_secret is not None else ""
    if not expected:
        raise HTTPException(503, "HERMES_API_KEY doit être configuré pour activer le serveur MCP Hermes.")
    raw = (authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(401, "Jeton Bearer manquant pour /api/hermes/mcp.")
    token = raw[7:].strip()
    if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "Jeton Bearer invalide pour /api/hermes/mcp.")


def _rpc_result(rpc_id: Any, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})


def _rpc_error(rpc_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}})


@router.post("/mcp")
@router.post("/mcp/{session_id}")
async def hermes_mcp_endpoint(
    request: Request,
    session_id: str | None = None,
    authorization: str | None = Header(default=None),
    x_hermes_session_id: str | None = Header(default=None),
    x_session_id: str | None = Header(default=None),
    x_clair_mission_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Point d'entrée MCP JSON-RPC 2.0 pour Hermes Gateway."""
    _verify_mcp_bearer(settings, authorization)

    try:
        body = await request.json()
    except ValueError:
        return _rpc_error(None, -32700, "Corps JSON invalide.")

    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return _rpc_error(body.get("id") if isinstance(body, dict) else None, -32600, "Requête JSON-RPC 2.0 invalide.")

    rpc_id = body.get("id")
    method = str(body.get("method") or "").strip()
    params = body.get("params") if isinstance(body.get("params"), dict) else {}

    if method == "initialize":
        return _rpc_result(
            rpc_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "clair-tools-mcp", "version": "1.0.0"},
            },
        )

    if method == "notifications/initialized":
        return JSONResponse({}, status_code=202)

    # Récupération du contexte de mission authentifié (en-têtes, URL ou params._meta)
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    target_session_id = (
        (session_id or "").strip()
        or (x_hermes_session_id or "").strip()
        or (x_session_id or "").strip()
        or str(request.query_params.get("session_id") or "").strip()
    )
    if not target_session_id and meta:
        meta_sid = meta.get("session_id") or meta.get("clair_session_id") or meta.get("nousresearch.hermes/session_id")
        if isinstance(meta_sid, str) and meta_sid.strip():
            target_session_id = meta_sid.strip()

    target_mission_token = (x_clair_mission_token or "").strip()
    if not target_mission_token and meta:
        meta_tok = meta.get("mission_token") or meta.get("clair_mission_token")
        if isinstance(meta_tok, str) and meta_tok.strip():
            target_mission_token = meta_tok.strip()

    lease = resolve_gateway_mission_lease(
        target_session_id,
        target_mission_token,
        require_token=True,
    )

    if method == "tools/list":
        if not target_session_id:
            # Découverte globale authentifiée par Bearer (sans bail de mission) :
            # expose uniquement les schémas d'outils sans accorder aucun droit d'exécution.
            discovery_permissions = {t.required_permission for t in CLAIR_TOOL_REGISTRY._tools.values()}
            return _rpc_result(rpc_id, {"tools": CLAIR_TOOL_REGISTRY.to_mcp_tools(discovery_permissions)})
        allowed_permissions = lease.allowed_permissions if lease else set()
        return _rpc_result(rpc_id, {"tools": CLAIR_TOOL_REGISTRY.to_mcp_tools(allowed_permissions)})

    if method == "tools/call":
        tool_name = str(params.get("name") or "").strip()
        raw_args = params.get("arguments")
        if not tool_name:
            return _rpc_error(rpc_id, -32602, "Paramètre 'name' requis pour tools/call.")

        if lease is None or not (lease.user_id or "").strip():
            return _rpc_result(
                rpc_id,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "success": False,
                                    "tool_name": tool_name,
                                    "error": "Session de mission Hermes absente, expirée ou non reconnue (X-Hermes-Session-Id requis).",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                },
            )

        ctx = ToolExecutionContext(
            settings=settings,
            sessions=sessions,
            user_id=lease.user_id,
            allowed_permissions=lease.allowed_permissions,
            model=lease.model,
            created_pages=lease.created_pages,
        )
        result = await CLAIR_TOOL_REGISTRY.execute(tool_name, raw_args, ctx)
        result_dict = result.model_dump()
        return _rpc_result(
            rpc_id,
            {
                "isError": not result.success,
                "content": [{"type": "text", "text": json.dumps(result_dict, ensure_ascii=False)}],
                "structuredContent": result_dict,
            },
        )

    return _rpc_error(rpc_id, -32601, f"Méthode MCP non supportée : {method}")
