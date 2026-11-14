"""Connecteur et moteur d'exécution hybride pour NousResearch Hermes Agent.

Prend en charge :
1. Le mode Gateway natif (`hermes gateway run` sur le port 8642) via `/health`,
   `/v1/models` et `/v1/chat/completions` avec continuité `X-Hermes-Session-Id`.
2. Le mode Autonome Local de repli (boucle d'outils SearXNG, mémoire `USER.md` /
   `MEMORY.md`, auto-génération de compétences `SKILL.md`) via OpenRouter.
3. Le mode Démonstration (`DEMO_MODE=true`) pour tester le workflow sans clé API.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx

from . import hermes_tools, providers
from .config import Settings
from .routers.hermes_mcp import (
    register_gateway_mission_lease,
    resolve_gateway_mission_lease,
    unregister_gateway_mission_lease,
)
from .tool_registry import CLAIR_TOOL_REGISTRY, ToolExecutionContext, permissions_from_enabled_tools

_logger = logging.getLogger("uvicorn.error")

_GATEWAY_PROBE_TIMEOUT = httpx.Timeout(2.5, connect=1.5, pool=1.5)
_GATEWAY_STREAM_TIMEOUT = httpx.Timeout(120.0, connect=10.0, pool=10.0)
_LEARNING_TIMEOUT = httpx.Timeout(30.0, connect=5.0, pool=5.0)
_GENERATION_COST_TIMEOUT = httpx.Timeout(3.0, connect=1.5, pool=1.5)
_MAX_LLM_CALLS = 15
_MAX_TOOL_CALLS = 10
_MAX_MISSION_SECONDS = 120.0

DEFAULT_HERMES_SOUL = (
    "Tu es Hermes Agent (inspiré de NousResearch/hermes-agent), un agent autonome méthodique "
    "orienté résolution de problèmes. Tu exploites tes outils (`github_inspect`, `fetch_url`, `web_search`) "
    "avant d'affirmer, tu t'appuies sur la mémoire persistante de l'utilisateur (USER.md / MEMORY.md) "
    "et tu capitalises chaque mission en compétences réutilisables (SKILL.md). "
    "RÈGLE DE VÉRITÉ : n'invente jamais une date, un hash de commit, une release, un chiffre ou une URL "
    "absent des sorties de tes outils ; si une donnée n'est pas vérifiable, dis-le explicitement. "
    "Réponds toujours en français clair, structuré et actionnable."
)

HERMES_TOOLS_CATALOG: list[dict[str, str]] = [
    {
        "id": "web_search",
        "name": "Recherche Web & Veille",
        "description": "Interroge SearXNG / Brave pour collecter des sources vérifiables en temps réel.",
        "hermes_ref": "search_web / web_extract",
    },
    {
        "id": "memory",
        "name": "Mémoire Persistante",
        "description": "Consulte et enrichit les préférences et faits durables (USER.md / MEMORY.md).",
        "hermes_ref": "memory",
    },
    {
        "id": "skills",
        "name": "Auto-Amélioration (Skills)",
        "description": "Formalise automatiquement la méthode apprise en compétence @skill réutilisable.",
        "hermes_ref": "skills_list / skill_manage",
    },
    {
        "id": "code_execution",
        "name": "Analyse & Sandbox",
        "description": "Structure l'architecture, vérifie le code et prépare les commandes via le Gateway isolé.",
        "hermes_ref": "terminal / execute_code",
    },
    {
        "id": "create_page",
        "name": "Création de Page (Brouillon)",
        "description": "Crée un brouillon cLAIr Page (non publié) à partir d'un titre, contenu structuré et sources.",
        "hermes_ref": "clair_create_page (MCP)",
    },
]

HERMES_MISSION_PRESETS: list[dict[str, Any]] = [
    {
        "id": "tech_watch",
        "title": "Veille technique & Synthèse",
        "description": "Recherche multi-sources, tri critique et création d'une compétence de veille.",
        "prompt": (
            "Analyse les dernières évolutions autour des agents autonomes MCP et propose un plan "
            "d'architecture pragmatique adapté à notre stack FastAPI + Next.js."
        ),
        "tools": ["web_search", "memory", "skills"],
    },
    {
        "id": "code_audit",
        "title": "Audit Architecture & Sécurité",
        "description": "Revue structurée des risques, invariants de sécurité et plan de remédiation.",
        "prompt": (
            "Établis une grille d'audit sécurité et maintenabilité pour un endpoint SSE FastAPI "
            "communiquant avec un conteneur agent externe, puis génère une checklist réutilisable."
        ),
        "tools": ["memory", "skills", "code_execution"],
    },
    {
        "id": "skill_forge",
        "title": "Forge de Compétence (@skill)",
        "description": "Transforme un besoin métier en instruction système experte prête à l'emploi.",
        "prompt": (
            "Conçois une méthodologie complète de revue de code rigoureuse (lisibilité, failles XSS/SQLi, "
            "tests de régression) et synthétise-la en compétence réutilisable."
        ),
        "tools": ["memory", "skills", "code_execution"],
    },
    {
        "id": "research_brief",
        "title": "Note de Décision Rapide",
        "description": "Collecte factuelle, comparaison d'options et recommandation tranchée.",
        "prompt": (
            "Compare les approches de persistance de mémoire d'agent (fichiers Markdown vs base relationnelle "
            "vs index vectoriel) avec leurs compromis opérationnels."
        ),
        "tools": ["web_search", "memory", "skills"],
    },
]


def _gateway_headers(settings: Settings, session_id: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    key_secret = getattr(settings, "hermes_api_key", None)
    key = key_secret.get_secret_value().strip() if key_secret is not None else ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id
        headers["X-Hermes-Session-Key"] = session_id
    return headers


def _extract_gateway_models(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    models: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            models.append(item["id"].strip())
    return models


async def probe_hermes_gateway(settings: Settings) -> dict[str, Any]:
    """Vérifie si le Gateway externe `nousresearch/hermes-agent` répond."""
    gateway_url = (getattr(settings, "hermes_api_url", "") or "").strip().rstrip("/")
    hermes_enabled = bool(getattr(settings, "hermes_enabled", True))
    has_llm = settings.enabled(settings.llm_api_key)
    llm_base_url = (getattr(settings, "llm_base_url", "") or "").strip()
    provider = "openrouter" if "openrouter.ai" in llm_base_url.lower() else "openai_compatible"

    if settings.demo_mode:
        return {
            "enabled": hermes_enabled,
            "reachable": False,
            "mode": "demo",
            "provider": provider,
            "llm_base_url": llm_base_url,
            "gateway_url": gateway_url,
            "gateway_models": [],
        }

    if not hermes_enabled:
        return {
            "enabled": False,
            "reachable": False,
            "mode": "disabled",
            "provider": provider,
            "llm_base_url": llm_base_url,
            "gateway_url": gateway_url,
            "gateway_models": [],
        }

    if gateway_url:
        headers = _gateway_headers(settings)
        try:
            async with httpx.AsyncClient(timeout=_GATEWAY_PROBE_TIMEOUT, follow_redirects=False) as client:
                health_resp = await client.get(f"{gateway_url}/health", headers=headers)
                if health_resp.is_success:
                    models: list[str] = []
                    try:
                        models_resp = await client.get(f"{gateway_url}/v1/models", headers=headers)
                        if models_resp.is_success:
                            models = _extract_gateway_models(models_resp.json())
                    except (httpx.HTTPError, ValueError):
                        pass
                    return {
                        "enabled": True,
                        "reachable": True,
                        "mode": "gateway",
                        "provider": provider,
                        "llm_base_url": llm_base_url,
                        "gateway_url": gateway_url,
                        "gateway_models": models,
                    }
        except (httpx.HTTPError, ValueError) as exc:
            _logger.debug("Gateway Hermes injoignable (%s): %s", gateway_url, exc)

    return {
        "enabled": True,
        "reachable": False,
        "mode": "local_autonomous" if has_llm else "offline",
        "provider": provider,
        "llm_base_url": llm_base_url,
        "gateway_url": gateway_url,
        "gateway_models": [],
    }


def _build_hermes_system_prompt(
    soul_prompt: str,
    user_memories: list[str],
    user_skills: list[dict[str, str]],
    enabled_tools: list[str],
    sources: list[dict[str, str]],
) -> str:
    sections: list[str] = [
        "# SOUL.md — Identité & Directives Hermes",
        soul_prompt.strip() or DEFAULT_HERMES_SOUL,
        f"Outils activés pour cette mission : {', '.join(enabled_tools) if enabled_tools else 'aucun'}.",
    ]
    if "memory" in enabled_tools and user_memories:
        mem_lines = "\n".join(f"- {m.strip()}" for m in user_memories[-15:] if m.strip())
        if mem_lines:
            sections.append(f"# USER.md / MEMORY.md — Mémoire persistante utilisateur\n{mem_lines}")
    if "skills" in enabled_tools and user_skills:
        skill_lines = "\n".join(
            f"- @{s['name']}: {s['prompt'][:220].strip()}"
            for s in user_skills[:10]
            if s.get("name")
        )
        if skill_lines:
            sections.append(f"# Compétences déjà disponibles dans cLAIr\n{skill_lines}")
    if sources:
        src_lines = "\n".join(
            f"[{idx}] {s.get('title', 'Source')} ({s.get('url', '')})\n{s.get('snippet', '')}"
            for idx, s in enumerate(sources, start=1)
        )
        sections.append(
            "# Sources Web collectées par SearXNG\n"
            "Cite les sources pertinentes avec [1], [2], etc.\n" + src_lines
        )
    instructions = [
        "# Consigne d'exécution et de vérification",
        "- Lorsque tu dois inspecter un dépôt GitHub, appelle `github_inspect` avant toute synthèse.",
        "- Lorsque tu as besoin de lire une page officielle ou un README, appelle `fetch_url`.",
    ]
    if "create_page" in enabled_tools:
        instructions.append(
            "- Lorsque tu dois rédiger ou synthétiser une page web pérenne sous forme de brouillon cLAIr Pages, "
            "appelle l'outil `clair_create_page` (ou `mcp__clair__clair_create_page`) avec les arguments requis."
        )
    instructions.extend(
        [
            "- N'affirme jamais une date, un hash, une release ou un lien absent des résultats d'outils ; "
            "signale explicitement ce qui n'a pas pu être vérifié.",
            "- Structure ta réponse clairement avec des sections utiles, des étapes concrètes et, "
            "si l'outil `code_execution` est actif et pertinent, des blocs de code propres et sûrs.",
        ]
    )
    sections.append("\n".join(instructions))
    return "\n\n".join(sections)


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        return None


async def _synthesize_hermes_learning(
    settings: Settings,
    prompt: str,
    answer: str,
    model: str,
) -> tuple[dict[str, str] | None, str | None]:
    """Extrait une compétence réutilisable (`SKILL.md`) et un fait mémoire (`MEMORY.md`)."""
    if settings.demo_mode or not settings.enabled(settings.llm_api_key) or not answer.strip():
        return None, None
    key = settings.llm_api_key.get_secret_value().strip()
    learn_model = (getattr(settings, "skill_prompt_model", "") or model or settings.default_model).strip()
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es le module d'auto-amélioration de Hermes Agent. À partir de la mission utilisateur "
                "et de la réponse produite, extrais au format JSON strict :\n"
                '{"skill": {"name": "Nom court <= 40 car.", "prompt": "Instruction système réutilisable incluant des critères de vérification factuelle (URLs officielles, dates exactes, signalement des faits non confirmés)"}, '
                '"memory": "Une phrase factuelle concise sur la préférence ou le contexte utilisateur (ou chaîne vide)"}'
                "\nRéponds uniquement par l'objet JSON."
            ),
        },
        {
            "role": "user",
            "content": f"Mission :\n{prompt[:1500]}\n\nRéponse :\n{answer[:3000]}",
        },
    ]
    try:
        async with httpx.AsyncClient(timeout=_LEARNING_TIMEOUT, follow_redirects=False) as client:
            resp = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": learn_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )
        if not resp.is_success:
            return None, None
        payload = resp.json()
        raw_content = payload["choices"][0]["message"]["content"]
        parsed = _parse_json_object(raw_content)
        if not parsed:
            return None, None
        skill_obj = parsed.get("skill")
        suggested_skill: dict[str, str] | None = None
        if isinstance(skill_obj, dict):
            s_name = str(skill_obj.get("name", "")).strip()[:80]
            s_prompt = str(skill_obj.get("prompt", "")).strip()[:4000]
            if s_name and s_prompt:
                suggested_skill = {"name": s_name, "prompt": s_prompt}
        raw_mem = parsed.get("memory")
        suggested_memory = str(raw_mem).strip()[:500] if isinstance(raw_mem, str) and raw_mem.strip() else None
        return suggested_skill, suggested_memory
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        _logger.debug("Auto-apprentissage Hermes ignoré: %s", exc)
        return None, None


async def _fetch_openrouter_generation_cost(settings: Settings, generation_id: str) -> float | None:
    """Interroge `/generation?id=...` sur OpenRouter pour récupérer le coût réel facturé (USD)."""
    clean_id = (generation_id or "").strip()
    if not clean_id or not clean_id.startswith("gen-"):
        return None
    base_url = (getattr(settings, "llm_base_url", "") or "").strip().rstrip("/")
    if "openrouter.ai" not in base_url.lower() or not settings.enabled(settings.llm_api_key):
        return None
    key = settings.llm_api_key.get_secret_value().strip()
    try:
        async with httpx.AsyncClient(timeout=_GENERATION_COST_TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(
                f"{base_url}/generation",
                params={"id": clean_id},
                headers={"Authorization": f"Bearer {key}"},
            )
        if not resp.is_success:
            return None
        data = resp.json().get("data")
        if isinstance(data, dict):
            raw = data.get("total_cost")
            if isinstance(raw, (int, float)) and raw >= 0:
                return float(raw)
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    return None


async def _stream_gateway_mission(
    settings: Settings,
    prompt: str,
    model: str,
    session_id: str,
    system_prompt: str,
    auto_learn_skill: bool,
    enabled_tools: list[str],
    *,
    user_id: str | None = None,
    allowed_permissions: set[str] | None = None,
    sessions: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    gateway_url = settings.hermes_api_url.rstrip("/")
    headers = _gateway_headers(settings, session_id=session_id)
    headers["Accept"] = "text/event-stream"

    step_gw_id = "step_gateway"
    yield {
        "type": "step",
        "id": step_gw_id,
        "tool": "gateway",
        "title": f"Connexion au Gateway Hermes ({gateway_url})",
        "status": "running",
        "detail": f"Session persistante {session_id}",
    }

    request_body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
    }
    if session_id:
        request_body["session_id"] = session_id
        request_body["metadata"] = {"session_id": session_id, "user_id": user_id or ""}

    authorized_tools = CLAIR_TOOL_REGISTRY.to_openai_tools(allowed_permissions or set())
    if authorized_tools:
        request_body["tools"] = authorized_tools
        request_body["tool_choice"] = "auto"

    started_at = time.monotonic()
    splitter = providers.ThinkTagSplitter()
    accumulated = ""
    seen_tools: dict[str, str] = {}
    pending_tool_calls: dict[int, dict[str, Any]] = {}
    running_tools: dict[str, tuple[str, str]] = {}
    usage_by_gen: dict[str, dict[str, int]] = {}
    cost_by_gen: dict[str, float] = {}
    generation_ids: list[str] = []
    explicit_llm_calls: int | None = None
    tool_waves = 0
    in_tool_wave = False
    current_event = "message"
    data_lines: list[str] = []
    created_pages: list[dict[str, Any]] = []
    lease_registered = False
    if user_id:
        lease = register_gateway_mission_lease(
            session_id=session_id,
            user_id=user_id,
            allowed_permissions=allowed_permissions or set(),
            model=model,
        )
        lease_registered = True
        headers["X-Clair-Mission-Token"] = lease.mission_token

    try:
        async with httpx.AsyncClient(timeout=_GATEWAY_STREAM_TIMEOUT, follow_redirects=False) as client:
            async with client.stream(
                "POST",
                f"{gateway_url}/v1/chat/completions",
                headers=headers,
                json=request_body,
            ) as response:
                if not response.is_success:
                    yield {
                        "type": "step",
                        "id": step_gw_id,
                        "tool": "gateway",
                        "title": "Gateway Hermes",
                        "status": "error",
                        "detail": f"HTTP {response.status_code}",
                    }
                    raise providers.ProviderError(
                        f"Le Gateway Hermes a refusé la requête (HTTP {response.status_code})."
                    )

                yield {
                    "type": "step",
                    "id": step_gw_id,
                    "tool": "gateway",
                    "title": "Gateway Hermes connecté",
                    "status": "done",
                    "detail": f"Exécution sur {model}",
                }

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip(" "))
                        continue
                    if line == "" and data_lines:
                        raw_data = "\n".join(data_lines)
                        data_lines.clear()
                        if raw_data.strip() == "[DONE]":
                            break
                        try:
                            payload = json.loads(raw_data)
                        except ValueError:
                            current_event = "message"
                            continue

                        if current_event == "hermes.tool.progress" or (
                            isinstance(payload, dict) and payload.get("type") == "hermes.tool.progress"
                        ):
                            tool_id = str(payload.get("tool_call_id") or payload.get("tool") or uuid4())
                            tool_name = str(payload.get("tool") or payload.get("name") or "gateway")
                            progress_msg = str(payload.get("message") or payload.get("detail") or "Exécution outil Hermes")
                            done_flag = bool(payload.get("done") or payload.get("status") == "done")
                            seen_tools[tool_id] = tool_name
                            if not in_tool_wave:
                                tool_waves += 1
                                in_tool_wave = True
                            if done_flag:
                                running_tools.pop(tool_id, None)
                            else:
                                running_tools[tool_id] = (tool_name, progress_msg)
                            yield {
                                "type": "step",
                                "id": f"gw_{tool_id}",
                                "tool": tool_name,
                                "title": f"Outil Hermes · {tool_name}",
                                "status": "done" if done_flag else "running",
                                "detail": progress_msg,
                            }
                            current_event = "message"
                            continue

                        if isinstance(payload, dict):
                            gen_id = str(payload.get("id") or "gateway-default").strip() or "gateway-default"
                            if payload.get("id") and gen_id not in generation_ids:
                                generation_ids.append(gen_id)
                            raw_llm_calls = payload.get("llm_calls")
                            if isinstance(raw_llm_calls, int) and raw_llm_calls > 0:
                                explicit_llm_calls = raw_llm_calls
                            if isinstance(payload.get("usage"), dict):
                                u_obj = payload["usage"]
                                if isinstance(u_obj.get("llm_calls"), int) and u_obj["llm_calls"] > 0:
                                    explicit_llm_calls = u_obj["llm_calls"]
                                parsed_u: dict[str, int] = {}
                                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                                    val = u_obj.get(k)
                                    if isinstance(val, int) and val >= 0:
                                        parsed_u[k] = val
                                if parsed_u:
                                    usage_by_gen[gen_id] = parsed_u
                                raw_cost = u_obj.get("cost") if u_obj.get("cost") is not None else u_obj.get("total_cost")
                                if isinstance(raw_cost, (int, float)) and raw_cost >= 0:
                                    cost_by_gen[gen_id] = float(raw_cost)
                            choices = payload.get("choices") or []
                            if choices and isinstance(choices[0], dict):
                                delta = choices[0].get("delta") or {}
                                for tc in delta.get("tool_calls") or []:
                                    if isinstance(tc, dict):
                                        _merge_tool_call_delta(pending_tool_calls, tc)
                                        fn = (tc.get("function") or {}).get("name")
                                        tc_id = str(tc.get("id") or fn or "tool")
                                        if fn and tc_id not in seen_tools:
                                            seen_tools[tc_id] = str(fn)
                                            yield {
                                                "type": "step",
                                                "id": f"gw_{tc_id}",
                                                "tool": str(fn),
                                                "title": f"Invocation {fn}",
                                                "status": "done",
                                                "detail": "Exécuté côté Gateway Hermes",
                                            }
                                thought_chunk = (
                                    delta.get("reasoning_content")
                                    or delta.get("reasoning")
                                    or delta.get("thought")
                                    or delta.get("thinking")
                                    or ""
                                )
                                if isinstance(thought_chunk, str) and thought_chunk:
                                    yield {"type": "thought", "text": thought_chunk}
                                content_chunk = delta.get("content") or ""
                                if isinstance(content_chunk, str) and content_chunk:
                                    in_tool_wave = False
                                    for r_id, (r_name, r_msg) in list(running_tools.items()):
                                        yield {
                                            "type": "step",
                                            "id": f"gw_{r_id}",
                                            "tool": r_name,
                                            "title": f"Outil Hermes · {r_name}",
                                            "status": "done",
                                            "detail": r_msg,
                                        }
                                    running_tools.clear()
                                    clean_c, clean_t = splitter.process(content_chunk)
                                    if clean_t:
                                        yield {"type": "thought", "text": clean_t}
                                    if clean_c:
                                        accumulated += clean_c
                                        yield {"type": "delta", "text": clean_c}
                        current_event = "message"

        # Adaptateur backend : exécution des outils cLAIr demandés dans la mission
        if user_id and sessions:
            lease = resolve_gateway_mission_lease(session_id)
            current_pages = lease.created_pages if lease else []
            ctx = ToolExecutionContext(
                settings=settings,
                sessions=sessions,
                user_id=user_id,
                allowed_permissions=allowed_permissions or set(),
                model=model,
                created_pages=current_pages,
            )
            if pending_tool_calls:
                for entry in pending_tool_calls.values():
                    fn_name = (entry.get("function") or {}).get("name") or ""
                    fn_args = (entry.get("function") or {}).get("arguments") or ""
                    tool_def = CLAIR_TOOL_REGISTRY.get(fn_name)
                    if tool_def is not None:
                        already_executed = any(p.get("title") for p in current_pages)
                        if not already_executed:
                            res = await CLAIR_TOOL_REGISTRY.execute(fn_name, fn_args, ctx)
                            yield {
                                "type": "step",
                                "id": f"gw_{entry['id']}",
                                "tool": fn_name,
                                "title": f"Brouillon cLAIr Page · {res.title or fn_name}",
                                "status": "done" if res.success else "error",
                                "detail": (
                                    f"Brouillon créé ({res.slug})"
                                    if res.success
                                    else (res.error or "Échec de l'outil")
                                ),
                            }

            if not current_pages:
                match_tool = re.search(
                    r'(?:<tool_call>|```(?:json)?\s*)\s*(\{[\s\S]*?"(?:name|tool)"\s*:\s*"(?:clair_create_page|mcp__clair__clair_create_page|mcp_clair_clair_create_page)"[\s\S]*?\})\s*(?:</tool_call>|```)?',
                    accumulated,
                )
                if match_tool:
                    try:
                        parsed_call = json.loads(match_tool.group(1))
                        call_fn = parsed_call.get("name") or parsed_call.get("tool") or "clair_create_page"
                        call_args = parsed_call.get("arguments") or parsed_call.get("parameters") or parsed_call
                        res = await CLAIR_TOOL_REGISTRY.execute(call_fn, call_args, ctx)
                        yield {
                            "type": "step",
                            "id": f"gw_txt_{uuid4().hex[:6]}",
                            "tool": "clair_create_page",
                            "title": f"Brouillon cLAIr Page · {res.title or 'clair_create_page'}",
                            "status": "done" if res.success else "error",
                            "detail": f"Brouillon créé ({res.slug})" if res.success else (res.error or "Échec"),
                        }
                    except (ValueError, TypeError):
                        pass
    except httpx.HTTPError as exc:
        yield {
            "type": "step",
            "id": step_gw_id,
            "tool": "gateway",
            "title": "Erreur de connexion Gateway Hermes",
            "status": "error",
            "detail": str(exc)[:180],
        }
        raise providers.ProviderError("Impossible de joindre le Gateway Hermes.") from None
    finally:
        if lease_registered:
            created_pages = unregister_gateway_mission_lease(session_id)

    for r_id, (r_name, r_msg) in list(running_tools.items()):
        yield {
            "type": "step",
            "id": f"gw_{r_id}",
            "tool": r_name,
            "title": f"Outil Hermes · {r_name}",
            "status": "done",
            "detail": r_msg,
        }
    running_tools.clear()

    fin_c, fin_t = splitter.finalize()
    if fin_t:
        yield {"type": "thought", "text": fin_t}
    if fin_c:
        accumulated += fin_c
        yield {"type": "delta", "text": fin_c}

    suggested_skill = None
    suggested_memory = None
    if auto_learn_skill and "skills" in enabled_tools:
        suggested_skill, suggested_memory = await _synthesize_hermes_learning(
            settings, prompt, accumulated, model
        )

    for gen_id in generation_ids:
        if gen_id not in cost_by_gen:
            fetched_cost = await _fetch_openrouter_generation_cost(settings, gen_id)
            if fetched_cost is not None:
                cost_by_gen[gen_id] = fetched_cost

    prompt_tokens = sum(u.get("prompt_tokens", 0) for u in usage_by_gen.values())
    completion_tokens = sum(u.get("completion_tokens", 0) for u in usage_by_gen.values())
    total_tokens = sum(u.get("total_tokens", 0) for u in usage_by_gen.values())
    if not total_tokens and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    observed_llm_calls = explicit_llm_calls or max(len(generation_ids), 1 + tool_waves, 1)
    final_cost_usd = round(sum(cost_by_gen.values()), 6) if cost_by_gen else None

    metrics = {
        "llm_calls": observed_llm_calls,
        "tool_calls": len(seen_tools),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": final_cost_usd,
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "stop_reason": "completed",
    }

    yield {
        "type": "artifacts",
        "sources": [],
        "created_pages": created_pages,
        "suggested_skill": suggested_skill,
        "suggested_memory": suggested_memory,
        "metrics": metrics,
    }
    yield {"type": "done", "content": accumulated, "metrics": metrics, "created_pages": created_pages}


def _merge_tool_call_delta(acc: dict[int, dict[str, Any]], tc: dict[str, Any]) -> None:
    idx = tc.get("index", 0)
    if not isinstance(idx, int):
        idx = 0
    entry = acc.setdefault(
        idx,
        {"id": tc.get("id") or f"call_{idx}_{uuid4().hex[:6]}", "type": "function", "function": {"name": "", "arguments": ""}},
    )
    if tc.get("id"):
        entry["id"] = tc["id"]
    if tc.get("extra_content") is not None:
        entry["extra_content"] = tc["extra_content"]
    if tc.get("thought_signature") is not None:
        entry["thought_signature"] = tc["thought_signature"]
    fn = tc.get("function")
    if isinstance(fn, dict):
        if fn.get("name"):
            entry["function"]["name"] += str(fn["name"])
        if fn.get("arguments"):
            entry["function"]["arguments"] += str(fn["arguments"])


def _tool_step_category(fn_name: str) -> str:
    if fn_name in {"web_search", "fetch_url", "github_inspect"}:
        return "web_search"
    if fn_name == "clair_create_page" or fn_name.endswith("__clair_create_page"):
        return "create_page"
    return "code_execution"


async def _run_openrouter_turn(
    settings: Settings,
    llm_model: str,
    messages: list[dict[str, Any]],
    openai_tools: list[dict[str, Any]],
    *,
    tool_choice: str = "auto",
) -> AsyncIterator[dict[str, Any]]:
    """Exécute un tour LLM OpenRouter en streaming avec support `tools`, `finish_reason` et `usage`."""
    key = settings.llm_api_key.get_secret_value().strip()
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": llm_model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if openai_tools:
        payload["tools"] = openai_tools
        payload["tool_choice"] = tool_choice

    splitter = providers.ThinkTagSplitter()
    tool_calls_acc: dict[int, dict[str, Any]] = {}
    content_acc = ""
    thought_acc = ""
    finish_reason = ""
    usage: dict[str, int] = {}
    cost_usd = 0.0
    stream_error = ""

    async with httpx.AsyncClient(timeout=_GATEWAY_STREAM_TIMEOUT, follow_redirects=False) as client:
        async with client.stream(
            "POST",
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            if resp.status_code in {400, 404} and openai_tools:
                yield {"type": "_tools_unsupported"}
                return
            if not resp.is_success:
                body = (await resp.aread()).decode("utf-8", errors="ignore")[:300]
                raise providers.ProviderError(f"Erreur OpenRouter HTTP {resp.status_code} : {body}")

            async for line in resp.aiter_lines():
                stripped = line.strip()
                if not stripped or not stripped.startswith("data:"):
                    continue
                data_raw = stripped[5:].strip()
                if data_raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_raw)
                except ValueError:
                    continue
                if isinstance(chunk.get("error"), dict):
                    err_obj = chunk["error"]
                    stream_error = str(err_obj.get("message") or err_obj.get("code") or "Erreur OpenRouter inconnue")
                    break
                if isinstance(chunk.get("usage"), dict):
                    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        val = chunk["usage"].get(k)
                        if isinstance(val, int):
                            usage[k] = val
                    raw_cost = chunk["usage"].get("cost")
                    if raw_cost is None:
                        raw_cost = chunk["usage"].get("total_cost")
                    if isinstance(raw_cost, (int, float)) and raw_cost >= 0:
                        cost_usd = float(raw_cost)
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice0 = choices[0]
                if isinstance(choice0.get("finish_reason"), str) and choice0["finish_reason"]:
                    finish_reason = choice0["finish_reason"]
                delta = choice0.get("delta") or {}
                reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    thought_acc += reasoning
                    yield {"type": "thought", "text": reasoning}
                elif isinstance(delta.get("reasoning_details"), list):
                    for rd in delta["reasoning_details"]:
                        if isinstance(rd, dict) and isinstance(rd.get("text"), str) and rd["text"]:
                            thought_acc += rd["text"]
                            yield {"type": "thought", "text": rd["text"]}
                for tc in delta.get("tool_calls") or []:
                    if isinstance(tc, dict):
                        _merge_tool_call_delta(tool_calls_acc, tc)
                piece = delta.get("content")
                if isinstance(piece, str) and piece:
                    c_out, t_out = splitter.process(piece)
                    if t_out:
                        thought_acc += t_out
                        yield {"type": "thought", "text": t_out}
                    if c_out:
                        content_acc += c_out
                        yield {"type": "delta", "text": c_out}

    if stream_error:
        _logger.warning("Erreur SSE OpenRouter (model=%s): %s", llm_model, stream_error)
        raise providers.ProviderError(f"Erreur OpenRouter : {stream_error}")

    fin_c, fin_t = splitter.finalize()
    if fin_t:
        thought_acc += fin_t
        yield {"type": "thought", "text": fin_t}
    if fin_c:
        content_acc += fin_c
        yield {"type": "delta", "text": fin_c}

    ordered_calls = [tool_calls_acc[idx] for idx in sorted(tool_calls_acc)]
    for tc in ordered_calls:
        if not tc["function"]["arguments"].strip():
            tc["function"]["arguments"] = "{}"

    _logger.info(
        "Hermes OpenRouter turn: model=%s finish_reason=%s tool_calls=%d content_len=%d thought_len=%d",
        llm_model,
        finish_reason or "unknown",
        len(ordered_calls),
        len(content_acc),
        len(thought_acc),
    )
    yield {
        "type": "_turn_end",
        "content": content_acc,
        "thought": thought_acc,
        "finish_reason": finish_reason or "unknown",
        "tool_calls": ordered_calls,
        "usage": usage,
        "cost_usd": cost_usd,
    }


def _canonical_tool_signature(fn_name: str, raw_args: str) -> str:
    try:
        parsed = json.loads(raw_args) if raw_args and raw_args.strip() else {}
        norm_args = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except ValueError:
        norm_args = (raw_args or "").strip()
    return f"{fn_name}:{norm_args}"


def _build_partial_restitution(
    stop_reason: str,
    sources: list[dict[str, str]],
    tool_notes: list[str],
) -> str:
    labels = {
        "max_tool_calls": "Limite maximale de 10 appels d'outils atteinte",
        "max_llm_calls": "Limite maximale de 15 appels LLM atteinte",
        "timeout_120s": "Délai maximal de 120 secondes atteint",
        "budget_exceeded": "Budget financier maximal dépassé",
        "repeated_call": "Appels d'outils identiques répétés détectés",
        "no_progress": "Absence de progression détectée",
    }
    reason_label = labels.get(stop_reason, stop_reason)
    lines = [
        f"### Restitution partielle ({reason_label})",
        "",
        "La boucle agentique s'est arrêtée proprement afin de respecter les garde-fous configurés.",
    ]
    if tool_notes:
        lines.extend(["", "#### Résultats d'outils collectés", *[f"- {note}" for note in tool_notes[:12]]])
    if sources:
        lines.extend(
            [
                "",
                "#### Sources vérifiées",
                *[f"- [{s.get('title') or s.get('url')}]({s.get('url')})" for s in sources[:10] if s.get("url")],
            ]
        )
    return "\n".join(lines)


async def stream_hermes_mission(
    settings: Settings,
    prompt: str,
    model: str | None = None,
    session_id: str | None = None,
    soul_prompt: str | None = None,
    enabled_tools: list[str] | None = None,
    user_memories: list[str] | None = None,
    user_skills: list[dict[str, str]] | None = None,
    auto_learn_skill: bool = True,
    execution_mode: str = "auto",
    sessions: Any = None,
    user_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Orchestre une mission Hermes (Gateway, Boucle Autonome Locale ou Démo)."""
    probe = await probe_hermes_gateway(settings)
    mode = probe["mode"]
    if mode == "disabled":
        raise providers.ProviderError("L'intégration Hermes Agent est désactivée par configuration (HERMES_ENABLED=false).")
    if mode == "offline":
        raise providers.ProviderError("Configurez LLM_API_KEY, un Gateway Hermes actif ou DEMO_MODE=true.")

    pref = (execution_mode or "auto").strip()
    if pref == "local_autonomous" and mode == "gateway":
        if not settings.enabled(settings.llm_api_key):
            raise providers.ProviderError("Configurez LLM_API_KEY pour utiliser le moteur local_autonomous.")
        mode = "local_autonomous"
    elif pref == "gateway" and mode not in {"gateway", "demo"}:
        raise providers.ProviderError(
            "Le Gateway Docker Hermes (8642) n'est pas joignable. Lancez clair-hermes ou choisissez local_autonomous."
        )

    active_tools = list(dict.fromkeys(enabled_tools or ["web_search", "memory", "skills", "code_execution"]))
    allowed_permissions = permissions_from_enabled_tools(active_tools)
    active_session = (session_id or "").strip() or f"clair-{uuid4().hex[:12]}"
    selected_model = (model or "").strip() or getattr(settings, "hermes_default_model", "") or settings.default_model
    memories = user_memories or []
    skills = user_skills or []
    soul = (soul_prompt or "").strip() or DEFAULT_HERMES_SOUL

    yield {
        "type": "meta",
        "mode": mode,
        "session_id": active_session,
        "model": selected_model,
        "gateway_url": probe.get("gateway_url", ""),
    }

    if mode == "demo":
        yield {
            "type": "step",
            "id": "step_memory",
            "tool": "memory",
            "title": "Consultation USER.md & MEMORY.md",
            "status": "done",
            "detail": f"{len(memories)} souvenir(s) et {len(skills)} compétence(s) chargés",
        }
        await asyncio.sleep(0.03)
        if "web_search" in active_tools:
            yield {
                "type": "step",
                "id": "step_web",
                "tool": "web_search",
                "title": "Recherche Web simulée (SearXNG)",
                "status": "done",
                "detail": "Mode démonstration actif — aucune requête réseau externe",
            }
            await asyncio.sleep(0.03)
        yield {
            "type": "step",
            "id": "step_exec",
            "tool": "code_execution",
            "title": "Raisonnement & structuration Hermes",
            "status": "done",
            "detail": f"Session {active_session}",
        }
        yield {
            "type": "thought",
            "text": (
                f"Mission analysée : « {prompt[:140]} ».\n"
                f"Outils actifs : {', '.join(active_tools)}. Préparation d'une synthèse structurée "
                "et d'une compétence @skill réutilisable."
            ),
        }
        demo_reply = (
            f"### Rapport de mission Hermes Agent (Mode Démonstration)\n\n"
            f"**Objectif traité :** {prompt}\n\n"
            f"1. **Contexte & Mémoire (`USER.md`)** : {len(memories)} souvenir(s) utilisateur et "
            f"{len(skills)} compétence(s) pris en compte.\n"
            f"2. **Outils mobilisés** : {', '.join(f'`{t}`' for t in active_tools)}.\n"
            "3. **Prochaine étape recommandée** : Enregistrez la compétence suggérée ci-dessous dans vos "
            "`@Compétences`, ou lancez le conteneur Gateway officiel avec "
            "`docker compose --profile hermes up -d` pour activer le serveur MCP/terminal complet."
        )
        for offset in range(0, len(demo_reply), 40):
            yield {"type": "delta", "text": demo_reply[offset : offset + 40]}
            await asyncio.sleep(0.005)
        suggested_skill = (
            {
                "name": "Méthode Hermes",
                "prompt": (
                    "Adopte la démarche Hermes Agent : 1) vérifie les faits et le contexte existant, "
                    "2) décompose le problème en étapes vérifiables, 3) propose des actions concrètes et "
                    "signale les risques ou angles morts."
                ),
            }
            if ("skills" in active_tools and auto_learn_skill)
            else None
        )
        suggested_memory = (
            f"Intérêt pour l'orchestration autonome Hermes autour de : {prompt[:120]}"
            if "memory" in active_tools
            else None
        )
        if suggested_skill:
            yield {
                "type": "step",
                "id": "step_skill",
                "tool": "skills",
                "title": "Boucle d'auto-amélioration (SKILL.md)",
                "status": "done",
                "detail": f"Compétence « {suggested_skill['name']} » prête à être importée",
            }
        yield {
            "type": "artifacts",
            "sources": [],
            "suggested_skill": suggested_skill,
            "suggested_memory": suggested_memory,
        }
        yield {"type": "done", "content": demo_reply}
        return

    if mode == "gateway":
        # En mode Gateway, transmettre le modèle OpenRouter choisi ou HERMES_DEFAULT_MODEL avant repli
        gw_models = probe.get("gateway_models") or []
        gw_model = (
            (model or "").strip()
            or (getattr(settings, "hermes_default_model", "") or "").strip()
            or (gw_models[0] if gw_models else "hermes-agent")
        )
        system_prompt = _build_hermes_system_prompt(soul, memories, skills, active_tools, [])
        async for ev in _stream_gateway_mission(
            settings=settings,
            prompt=prompt,
            model=gw_model,
            session_id=active_session,
            system_prompt=system_prompt,
            auto_learn_skill=auto_learn_skill,
            enabled_tools=active_tools,
            user_id=user_id,
            allowed_permissions=allowed_permissions,
            sessions=sessions,
        ):
            yield ev
        return

    # Mode local_autonomous : boucle ReAct multi-outils cLAIr (Mémoire + SearXNG/URL/GitHub + OpenRouter + Auto-Skill)
    started_at = time.monotonic()
    if "memory" in active_tools:
        yield {
            "type": "step",
            "id": "step_memory",
            "tool": "memory",
            "title": "Chargement USER.md & Compétences",
            "status": "done",
            "detail": f"{len(memories)} souvenir(s) et {len(skills)} compétence(s) injectés",
        }

    sources: list[dict[str, str]] = []
    valid_ids = {m["id"] for m in settings.models}
    is_openrouter = probe.get("provider") == "openrouter"
    if selected_model in valid_ids or (is_openrouter and "/" in selected_model):
        llm_model = selected_model
    else:
        llm_model = settings.default_model

    openai_tools = hermes_tools.build_openai_tools(active_tools, bool(settings.web_search_enabled))
    registry_ctx = ToolExecutionContext(
        settings=settings,
        sessions=sessions,
        user_id=user_id,
        allowed_permissions=allowed_permissions,
        model=llm_model,
        sources_acc=sources,
    )
    system_prompt = _build_hermes_system_prompt(soul, memories, skills, active_tools, sources)
    llm_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    llm_calls = 0
    total_tool_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    cost_usd = 0.0
    max_cost_usd = float(getattr(settings, "hermes_max_cost_usd", 0.25) or 0.0)
    accumulated = ""
    use_native_tools = bool(openai_tools)
    seen_signatures: set[str] = set()
    seen_result_hashes: set[str] = set()
    tool_notes: list[str] = []
    no_progress_turns = 0
    stop_reason = "completed"

    while True:
        if (time.monotonic() - started_at) >= _MAX_MISSION_SECONDS:
            stop_reason = "timeout_120s"
            break
        if max_cost_usd > 0.0 and cost_usd >= max_cost_usd:
            stop_reason = "budget_exceeded"
            break
        if llm_calls >= _MAX_LLM_CALLS:
            stop_reason = "max_llm_calls"
            break

        turn = llm_calls
        llm_calls += 1
        step_id = f"step_llm_{turn}"
        yield {
            "type": "step",
            "id": step_id,
            "tool": "code_execution",
            "title": f"Raisonnement Hermes (tour {turn + 1})",
            "status": "running",
            "detail": f"Modèle {llm_model} via {'OpenRouter' if is_openrouter else 'LLM'}",
        }

        turn_tools = openai_tools if use_native_tools else []
        turn_tool_choice = "auto" if (use_native_tools and total_tool_calls < _MAX_TOOL_CALLS) else "none"
        turn_content = ""
        turn_thought = ""
        turn_finish_reason = "unknown"
        turn_calls: list[dict[str, Any]] = []
        tools_unsupported = False

        async for ev in _run_openrouter_turn(
            settings,
            llm_model,
            llm_messages,
            turn_tools,
            tool_choice=turn_tool_choice,
        ):
            if ev["type"] == "_tools_unsupported":
                tools_unsupported = True
                break
            if ev["type"] == "thought":
                yield ev
            elif ev["type"] == "delta":
                turn_content += ev["text"]
                accumulated += ev["text"]
                yield ev
            elif ev["type"] == "_turn_end":
                turn_calls = ev["tool_calls"]
                turn_thought = str(ev.get("thought") or "")
                turn_finish_reason = str(ev.get("finish_reason") or "unknown")
                usage = ev["usage"]
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                total_tokens += usage.get("total_tokens", 0)
                cost_usd += float(ev.get("cost_usd") or 0.0)

        if tools_unsupported:
            use_native_tools = False
            yield {
                "type": "step",
                "id": step_id,
                "tool": "code_execution",
                "title": "Synthèse directe (outils natifs non supportés)",
                "status": "running",
                "detail": llm_model,
            }
            async for ev in providers.stream_chat_events(settings, llm_messages, llm_model):
                if ev["type"] == "thought":
                    yield {"type": "thought", "text": ev["text"]}
                elif ev["type"] == "delta":
                    accumulated += ev["text"]
                    yield {"type": "delta", "text": ev["text"]}
            yield {
                "type": "step",
                "id": step_id,
                "tool": "code_execution",
                "title": "Synthèse agentique terminée",
                "status": "done",
                "detail": f"{len(accumulated)} caractères générés",
            }
            break

        if max_cost_usd > 0.0 and cost_usd >= max_cost_usd and turn_calls:
            stop_reason = "budget_exceeded"
            yield {
                "type": "step",
                "id": step_id,
                "tool": "code_execution",
                "title": "Budget financier atteint",
                "status": "error",
                "detail": f"${cost_usd:.4f} / ${max_cost_usd:.4f}",
            }
            break

        if not turn_calls:
            if turn_content.strip():
                yield {
                    "type": "step",
                    "id": step_id,
                    "tool": "code_execution",
                    "title": "Synthèse agentique terminée",
                    "status": "done",
                    "detail": f"{len(accumulated)} caractères générés (finish={turn_finish_reason})",
                }
                break
            has_reasoning = bool(turn_thought.strip())
            if has_reasoning:
                # Un raisonnement intermédiaire sans contenu final n'est pas une absence de progression :
                # on conserve une trace dans l'historique et on invite le modèle à agir ou conclure.
                llm_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Tu as formulé un raisonnement intermédiaire sans appel d'outil ni réponse finale. "
                            "Appelle maintenant l'outil nécessaire (ex. `github_inspect` ou `fetch_url`) "
                            "ou rédige directement la synthèse finale."
                        ),
                    }
                )
                yield {
                    "type": "step",
                    "id": step_id,
                    "tool": "code_execution",
                    "title": f"Raisonnement intermédiaire (tour {turn + 1})",
                    "status": "done",
                    "detail": f"Relance vers outil/synthèse (finish={turn_finish_reason}, thought={len(turn_thought)} car.)",
                }
                continue

            no_progress_turns += 1
            reason_detail = (
                f"Réponse vide sans outil (finish={turn_finish_reason}, "
                f"content=0, thought=0, tentative {no_progress_turns}/2)"
            )
            _logger.warning("Hermes sans progression (tour %d): %s", turn + 1, reason_detail)
            if no_progress_turns >= 2:
                stop_reason = "no_progress"
                yield {
                    "type": "step",
                    "id": step_id,
                    "tool": "code_execution",
                    "title": "Absence de progression détectée",
                    "status": "error",
                    "detail": reason_detail,
                }
                break
            llm_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Ta réponse précédente était vide. Exploite les résultats d'outils déjà reçus "
                        "pour appeler l'outil suivant ou rédiger la réponse finale."
                    ),
                }
            )
            yield {
                "type": "step",
                "id": step_id,
                "tool": "code_execution",
                "title": f"Réponse vide (tour {turn + 1})",
                "status": "done",
                "detail": reason_detail,
            }
            continue

        yield {
            "type": "step",
            "id": step_id,
            "tool": "code_execution",
            "title": f"Planification de {len(turn_calls)} outil(s)",
            "status": "done",
            "detail": f"{', '.join(tc['function']['name'] for tc in turn_calls)} (finish={turn_finish_reason})",
        }

        llm_messages.append(
            {
                "role": "assistant",
                "content": turn_content if turn_content else "",
                "tool_calls": turn_calls,
            }
        )

        progress_in_turn = False
        duplicates_in_turn = 0
        for tc in turn_calls:
            if (time.monotonic() - started_at) >= _MAX_MISSION_SECONDS:
                stop_reason = "timeout_120s"
                break
            if total_tool_calls >= _MAX_TOOL_CALLS:
                stop_reason = "max_tool_calls"
                break

            fn_name = tc["function"]["name"]
            fn_args = tc["function"]["arguments"]
            sig = _canonical_tool_signature(fn_name, fn_args)
            if sig in seen_signatures:
                duplicates_in_turn += 1
                yield {
                    "type": "step",
                    "id": f"step_dup_{llm_calls}_{duplicates_in_turn}",
                    "tool": _tool_step_category(fn_name),
                    "title": f"Appel identique bloqué ({fn_name})",
                    "status": "error",
                    "detail": "Déjà exécuté avec les mêmes arguments",
                }
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(
                            {"error": "Appel identique déjà exécuté. Exploite les résultats existants ou conclus."}
                        ),
                    }
                )
                continue

            seen_signatures.add(sig)
            total_tool_calls += 1
            tc_step_id = f"step_tc_{total_tool_calls}"
            yield {
                "type": "step",
                "id": tc_step_id,
                "tool": _tool_step_category(fn_name),
                "title": f"Outil {fn_name}",
                "status": "running",
                "detail": fn_args[:90] if fn_args else "",
            }
            sources_before = len(sources)
            result_text, detail, ok = await hermes_tools.execute_hermes_tool(
                settings, fn_name, fn_args, sources_acc=sources, registry_ctx=registry_ctx
            )
            result_hash = hashlib.sha256(result_text.encode("utf-8", errors="ignore")).hexdigest()
            if not ok:
                gained_new_info = False
            elif fn_name == "web_search" and len(sources) == sources_before:
                # Une recherche web qui ne retourne aucune nouvelle source (vide ou doublon)
                # ne constitue pas une progression informationnelle.
                gained_new_info = False
            elif result_hash in seen_result_hashes:
                gained_new_info = False
            else:
                gained_new_info = True
                seen_result_hashes.add(result_hash)

            if gained_new_info:
                progress_in_turn = True
            if ok:
                tool_notes.append(f"`{fn_name}` : {detail}")
            yield {
                "type": "step",
                "id": tc_step_id,
                "tool": _tool_step_category(fn_name),
                "title": f"Outil {fn_name} {'terminé' if ok else 'en échec'}",
                "status": "done" if ok else "error",
                "detail": detail,
            }
            llm_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_text})

        if stop_reason != "completed":
            break
        if not progress_in_turn and not turn_content.strip():
            no_progress_turns += 1
            if duplicates_in_turn > 0 and no_progress_turns >= 2:
                stop_reason = "repeated_call"
                break
            if no_progress_turns >= 2:
                stop_reason = "no_progress"
                break
        else:
            no_progress_turns = 0

    if stop_reason != "completed":
        yield {
            "type": "step",
            "id": "step_limit",
            "tool": "code_execution",
            "title": "Arrêt propre de la boucle",
            "status": "done",
            "detail": stop_reason,
        }
        if not accumulated.strip():
            partial_text = _build_partial_restitution(stop_reason, sources, tool_notes)
            accumulated = partial_text
            yield {"type": "delta", "text": partial_text}

    suggested_skill = None
    suggested_memory = None
    if auto_learn_skill and ("skills" in active_tools or "memory" in active_tools) and accumulated.strip():
        yield {
            "type": "step",
            "id": "step_skill",
            "tool": "skills",
            "title": "Auto-amélioration (extraction Skill & Mémoire)",
            "status": "running",
            "detail": "Capitalisation de l'expérience",
        }
        suggested_skill, suggested_memory = await _synthesize_hermes_learning(
            settings, prompt, accumulated, llm_model
        )
        if "skills" not in active_tools:
            suggested_skill = None
        if "memory" not in active_tools:
            suggested_memory = None
        yield {
            "type": "step",
            "id": "step_skill",
            "tool": "skills",
            "title": "Auto-amélioration terminée",
            "status": "done",
            "detail": (
                f"Compétence « {suggested_skill['name']} » proposée"
                if suggested_skill
                else "Aucun nouvel artefact requis"
            ),
        }

    metrics = {
        "llm_calls": llm_calls,
        "tool_calls": total_tool_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 6),
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "stop_reason": stop_reason,
    }

    yield {
        "type": "artifacts",
        "sources": sources,
        "created_pages": registry_ctx.created_pages,
        "suggested_skill": suggested_skill,
        "suggested_memory": suggested_memory,
        "metrics": metrics,
    }
    yield {"type": "done", "content": accumulated, "metrics": metrics}
