"""Orchestrateur d'outils Finance pour le tchat IA (boucle ReAct streaming + repli JSON).

Permet à n'importe quelle conversation tchat ou vocale d'interroger le Screener,
les dossiers boursiers, les 31 scores Uncle Stock, les 508 ratios, les watchlists,
les indices, les analyses archivées (MOAT, experts, rapports) et les catalogues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx

from . import providers
from .config import Settings
from .finance_chat_tools import (
    FINANCE_CHAT_TOOLS,
    FinanceToolContext,
    execute_finance_tool,
    format_tool_status_label,
)
from .google_cloud import (
    clean_secret,
    open_chat_stream,
    post_chat_completion,
    should_route_to_google_cloud,
)

_logger = logging.getLogger("uvicorn.error")

_MAX_LLM_TURNS = 5
_MAX_TOOL_CALLS = 8
_TOOL_TIMEOUT_SECONDS = 30.0
_MAX_TOOL_OUTPUT_CHARS = 24000
_STREAM_TIMEOUT = httpx.Timeout(90.0, connect=15.0, read=240.0, pool=15.0)
_ROUTER_TIMEOUT = httpx.Timeout(25.0, connect=8.0, pool=8.0)

_ALLOWED_TOOL_NAMES: frozenset[str] = frozenset(
    t["function"]["name"] for t in FINANCE_CHAT_TOOLS
)

_CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,6}(?:\.[A-Za-z]{1,4})?)\b")
_EXPLICIT_TICKER_RE = re.compile(
    r"\b[A-Z0-9]{1,10}\.(?:PA|US|DE|XETRA|LSE|SW|AS|BR|MI|MC|T|TO|HK|EUFUND|INDX)\b"
)

_FINANCE_INTENT_RE = re.compile(
    r"(?:"
    r"piotroski|puotrosky|piotrotski|altman|ih[- ]?score|uncle[- ]?stock|mohanram|montier|"
    r"levermann|greenblatt|oshaughnessy|pim[- ]?van[- ]?vliet|erp5|slater|ohlson|beneish|dechow|trap[- ]?score|"
    r"\brsi\b|rsi\s*14|\bmacd\b|sma\s*(?:20|50|200)|ema\s*(?:20|50)|bollinger|\badx\b|stochastique|\bstoch\b|"
    r"\batr\b|\broc\b|supertrend|isopressure|isopression|golden\s+cross|death\s+cross|survente|surachat|survendeu?|"
    r"\broic\b|\broe\b|ev\s*/\s*ebitda|ve\s*/\s*ebitda|fcf[- ]?yield|marge\s+de\s+securite|valeur\s+intrinseque|"
    r"\bdcf\b|\bpeg\b|price[- ]to[- ]book|dette\s+nette\s*/\s*ebitda|screener|\bper\b|"
    r"watchlist|listes?\s+de\s+suivi|\bmoat\b|rapports?\s+trimestriels?|avis\s+d['’]experts?|"
    r"cac\s*40|sbf\s*120|s&p\s*500|sp\s*500|nasdaq(?:\s*100)?|dow\s+jones|\bdax\b|stoxx|russell|ftse|nikkei|"
    r"eufund|\betf\b|boursier|\bbourse\b|dividendes?|capitalisation|\bticker\b|\bisin\b|"
    r"@finance|@bourse|cours\s+de\s+(?:l['’]action|bourse)|cotations?|"
    r"\bactions?\s+(?:francaises?|europeennes?|americaines?|us|allemandes?|suisses?|japonaises?|tech|value|dividendes?|qui|avec|dont|du|de|dans|les|cotees?)"
    r")",
    re.IGNORECASE,
)

_FINANCE_FOLLOWUP_RE = re.compile(
    r"\b(?:compare|comparer|detail|details|trie|trier|filtre|filtrer|semaine|mois|trimestre|"
    r"premiere|premier|meilleure|meilleur|moat|bilan|expert|rapport|ratio|ratios|score|scores|"
    r"lesquelles|lesquels|celles-ci|ceux-ci|pourquoi|plus|moins|suivant|suivantes|autres?|"
    r"et\s+(?:en|sur|avec|pour|celles|ceux))\b",
    re.IGNORECASE,
)

_EXPLICIT_WEB_INTENT_RE = re.compile(
    r"\b(?:sur\s+internet|sur\s+le\s+web|en\s+ligne|recherche\s+web|actualites?\s+recentes?|"
    r"dernieres?\s+nouvelles|news\s+recentes|cherche\s+sur\s+google)\b",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def should_enable_finance_tools(
    content: str,
    history: list[dict[str, Any]] | None = None,
    *,
    finance_mode: bool = False,
    has_finance_skill: bool = False,
) -> bool:
    """Détermine si les outils Finance doivent être activés pour ce message tchat."""
    if finance_mode or has_finance_skill:
        return True
    raw = str(content or "").strip()
    if not raw:
        return False

    if _CASHTAG_RE.search(raw) or _EXPLICIT_TICKER_RE.search(raw):
        return True
    folded = _fold(raw)
    if _FINANCE_INTENT_RE.search(folded):
        return True

    # Continuité conversationnelle si les tours précédents portaient sur la Finance
    recent_assistant = [
        m for m in (history or []) if m.get("role") == "assistant"
    ][-2:]
    had_recent_finance = any(
        any(
            isinstance(src, dict)
            and src.get("provider") in ("finance_warehouse", "eodhd", "yahoo_finance")
            for src in (m.get("sources") or [])
        )
        or bool(m.get("has_finance_attachment"))
        for m in recent_assistant
    )
    if had_recent_finance and (len(folded.split()) <= 10 or _FINANCE_FOLLOWUP_RE.search(folded)):
        return True

    return False


def should_suppress_auto_web_search(
    content: str,
    *,
    finance_mode: bool = False,
    finance_tools_active: bool = False,
) -> bool:
    """Empêche la recherche web auto (SearXNG) de polluer les requêtes sur l'entrepôt Finance local."""
    folded = _fold(content)
    if _EXPLICIT_WEB_INTENT_RE.search(folded):
        return False
    return bool(
        finance_mode
        or finance_tools_active
        or _FINANCE_INTENT_RE.search(folded)
        or _CASHTAG_RE.search(content or "")
        or _EXPLICIT_TICKER_RE.search(content or "")
    )


def _merge_tool_call_delta(acc: dict[int, dict[str, Any]], tc: dict[str, Any]) -> None:
    idx = tc.get("index", 0)
    if not isinstance(idx, int):
        idx = 0
    entry = acc.setdefault(
        idx,
        {
            "id": tc.get("id") or f"call_{idx}_{uuid4().hex[:6]}",
            "type": "function",
            "function": {"name": "", "arguments": ""},
        },
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


def _canonical_signature(fn_name: str, raw_args: str) -> str:
    try:
        parsed = json.loads(raw_args) if raw_args and raw_args.strip() else {}
        norm = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except ValueError:
        norm = (raw_args or "").strip()
    return f"{fn_name}:{norm}"


def _build_finance_sources(tool_ctx: FinanceToolContext) -> list[dict[str, Any]]:
    if not tool_ctx.consulted_tools and not tool_ctx.consulted_symbols:
        return []
    tools_label = ", ".join(tool_ctx.consulted_tools) or "finance_warehouse"
    sources: list[dict[str, Any]] = [
        {
            "title": "Entrepôt Finance · Screener & Dossiers",
            "url": "clair-finance://screener",
            "snippet": f"Données locales consultées ({tools_label}).",
            "provider": "finance_warehouse",
        }
    ]
    for sym in tool_ctx.consulted_symbols[:6]:
        sources.append(
            {
                "title": f"Entrepôt Finance · {sym} ({sym})",
                "url": f"clair-finance://ticker/{sym}",
                "snippet": f"Données financières et indicateurs locaux pour {sym}.",
                "provider": "finance_warehouse",
            }
        )
    return sources


async def _run_single_llm_turn(
    settings: Settings,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    tool_choice: str = "auto",
    enable_cache: bool = True,
    sampling_params: dict[str, Any] | None = None,
    stream_text_live: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    use_gc = should_route_to_google_cloud(settings, model)
    if not use_gc and not clean_secret(getattr(settings, "llm_api_key", None)):
        raise providers.ProviderError("Configurez la clé API du fournisseur IA pour utiliser cette fonction.")

    payload_messages = providers.prepare_messages_for_caching(
        messages,
        model=model,
        base_url=getattr(settings, "llm_base_url", ""),
        enable_cache=enable_cache and not use_gc,
    )
    payload: dict[str, Any] = {
        "model": model,
        "messages": payload_messages,
        "stream": True,
        "max_tokens": settings.llm_max_tokens,
    }
    if sampling_params is not None:
        for pk, pv in sampling_params.items():
            if pv is not None:
                payload[pk] = pv
    else:
        payload["temperature"] = settings.llm_temperature

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    splitter = providers.ThinkTagSplitter()
    tool_calls_acc: dict[int, dict[str, Any]] = {}
    content_acc = ""
    thought_acc = ""
    finish_reason = ""
    stream_error = ""

    async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT, follow_redirects=False) as client:
        async with open_chat_stream(
            settings,
            payload,
            client=client,
            timeout=_STREAM_TIMEOUT,
            provider_label="Fournisseur IA",
            raise_on_error=False,
        ) as (resp, data_iter, route_label):
            if resp.status_code in {400, 404} and tools:
                yield {"type": "_tools_unsupported"}
                return
            if not resp.is_success:
                from .google_cloud import check_response

                await resp.aread()
                check_response(resp, route_label)
                return

            async for data_raw in data_iter:
                if data_raw.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_raw)
                except ValueError:
                    continue
                if isinstance(chunk.get("error"), dict):
                    err = chunk["error"]
                    stream_error = str(err.get("message") or err.get("code") or f"Erreur {route_label}")
                    break
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice0 = choices[0]
                if isinstance(choice0.get("finish_reason"), str) and choice0["finish_reason"]:
                    finish_reason = choice0["finish_reason"]
                delta = choice0.get("delta") or {}

                reasoning = delta.get("reasoning") or delta.get("reasoning_content") or delta.get("thought")
                if not isinstance(reasoning, str) or not reasoning:
                    google_extra = (delta.get("extra_content") or {}).get("google")
                    if isinstance(google_extra, dict) and isinstance(google_extra.get("thought"), str):
                        reasoning = google_extra["thought"]
                if isinstance(reasoning, str) and reasoning:
                    thought_acc += reasoning
                    yield {"type": "thought", "text": reasoning}

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
                        if stream_text_live:
                            yield {"type": "delta", "text": c_out}

    if stream_error:
        raise providers.ProviderError(f"Erreur fournisseur IA : {stream_error}")

    fin_c, fin_t = splitter.finalize()
    if fin_t:
        thought_acc += fin_t
        yield {"type": "thought", "text": fin_t}
    if fin_c:
        content_acc += fin_c
        if stream_text_live:
            yield {"type": "delta", "text": fin_c}

    ordered_calls = [tool_calls_acc[idx] for idx in sorted(tool_calls_acc)]
    for tc in ordered_calls:
        if not tc["function"]["arguments"].strip():
            tc["function"]["arguments"] = "{}"

    yield {
        "type": "_turn_end",
        "content": content_acc,
        "thought": thought_acc,
        "finish_reason": finish_reason or "unknown",
        "tool_calls": ordered_calls,
    }


async def _plan_finance_tools_via_json_router(
    settings: Settings,
    user_query: str,
    recent_turns: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Repli JSON lorsque le modèle actif ne supporte pas le function calling natif."""
    router_model = (getattr(settings, "search_query_model", "") or settings.default_model).strip()
    tool_catalog = [
        {"name": t["function"]["name"], "description": t["function"]["description"]}
        for t in FINANCE_CHAT_TOOLS
    ]
    sys_msg = (
        "Tu es un routeur JSON vers les outils de l'entrepôt Finance local.\n"
        f"Outils disponibles : {json.dumps(tool_catalog, ensure_ascii=False)}\n"
        "Règles clés du Screener (`finance_screener_query`) :\n"
        "- Champs fréquents : `piotroski_f`, `ih_score`, `altman_z`, `mos_intrinsic_pct`, `pe_ttm`, `ev_ebitda`, "
        "`roic_pct`, `roe_pct`, `op_margin_pct`, `dividend_yield_pct`, `rsi_14`, `isopressure_p20`, `isopressure_p50`, `supertrend_dir`.\n"
        "- Règles : `{\"kind\":\"metric\",\"field\":\"piotroski_f\",\"op\":\"gt\",\"value\":5}` ; "
        "`{\"kind\":\"compare\",\"left\":\"isopressure_p20\",\"op\":\"gt\",\"right\":\"isopressure_p50\"}`.\n"
        "Retourne UNIQUEMENT un JSON valide : {\"calls\": [{\"name\": \"...\", \"arguments\": {...}}]} (max 2 appels)."
    )
    payload_user = {
        "recent_turns": [
            {"role": t.get("role"), "content": str(t.get("content") or "")[:400]}
            for t in (recent_turns or [])[-3:]
            if t.get("role") in ("user", "assistant")
        ],
        "question": user_query[:1500],
    }
    try:
        async with httpx.AsyncClient(timeout=_ROUTER_TIMEOUT, follow_redirects=False) as client:
            resp = await post_chat_completion(
                settings,
                {
                    "model": router_model,
                    "messages": [
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": json.dumps(payload_user, ensure_ascii=False)},
                    ],
                    "stream": False,
                    "temperature": 0,
                    "max_tokens": 600,
                },
                client=client,
                timeout=_ROUTER_TIMEOUT,
            )
        if not resp.is_success:
            return []
        raw = resp.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", str(raw or ""), re.DOTALL)
        parsed = json.loads(match.group(0) if match else str(raw))
        calls = parsed.get("calls") if isinstance(parsed, dict) else None
        if not isinstance(calls, list):
            return []
        valid: list[dict[str, Any]] = []
        for c in calls[:2]:
            if isinstance(c, dict) and c.get("name") in _ALLOWED_TOOL_NAMES:
                args = c.get("arguments")
                valid.append(
                    {
                        "name": str(c["name"]),
                        "arguments": args if isinstance(args, dict) else {},
                    }
                )
        return valid
    except Exception as exc:
        _logger.warning("Repli routeur JSON Finance indisponible: %s", exc)
        return []


def _extract_last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(
                    str(p.get("text") or "")
                    for p in c
                    if isinstance(p, dict) and p.get("type") == "text"
                )
    return ""


async def stream_finance_chat_turn(
    *,
    settings: Settings,
    model: str,
    messages: list[dict[str, Any]],
    tool_ctx: FinanceToolContext,
    enable_cache: bool = True,
    sampling_params: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Exécute un tour de tchat avec outils Finance natifs et repli transparent."""
    working_messages: list[dict[str, Any]] = [dict(m) for m in messages]
    seen_signatures: set[str] = set()
    total_tool_calls = 0
    emitted_any_text = False
    tools_unsupported = False

    yield {"type": "status", "message": "Agent Finance : interrogation de l'entrepôt boursier…"}

    for turn in range(_MAX_LLM_TURNS):
        allow_tools = total_tool_calls < _MAX_TOOL_CALLS and turn < (_MAX_LLM_TURNS - 1)
        turn_tools = FINANCE_CHAT_TOOLS if allow_tools else []
        turn_tool_choice = "auto" if allow_tools else "none"

        turn_content = ""
        turn_calls: list[dict[str, Any]] = []

        async for ev in _run_single_llm_turn(
            settings,
            model,
            working_messages,
            turn_tools,
            tool_choice=turn_tool_choice,
            enable_cache=enable_cache,
            sampling_params=sampling_params,
            stream_text_live=True,
        ):
            ev_type = ev.get("type")
            if ev_type == "_tools_unsupported":
                tools_unsupported = True
                break
            if ev_type == "thought":
                yield ev
            elif ev_type == "delta":
                if not emitted_any_text:
                    emitted_any_text = True
                yield ev
            elif ev_type == "_turn_end":
                turn_content = str(ev.get("content") or "")
                turn_calls = list(ev.get("tool_calls") or [])

        if tools_unsupported:
            break

        if not turn_calls:
            if turn_content.strip():
                yield {"type": "done", "sources": _build_finance_sources(tool_ctx)}
                return
            # Aucun appel d'outil et aucun texte produit -> demander explicitement de conclure
            working_messages.append(
                {
                    "role": "user",
                    "content": "Appelle les outils Finance nécessaires ou formule directement ta réponse à l'utilisateur.",
                }
            )
            continue

        # Enregistrer l'appel assistant puis exécuter chaque outil demandé
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": turn_content or "",
            "tool_calls": turn_calls,
        }
        working_messages.append(assistant_msg)

        for tc in turn_calls:
            if total_tool_calls >= _MAX_TOOL_CALLS:
                working_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc["function"]["name"],
                        "content": json.dumps(
                            {"error": "Plafond d'appels d'outils atteint pour ce tour. Synthétise les résultats déjà collectés."},
                            ensure_ascii=False,
                        ),
                    }
                )
                continue

            fn_name = str((tc.get("function") or {}).get("name") or "").strip()
            raw_args = str((tc.get("function") or {}).get("arguments") or "{}")
            sig = _canonical_signature(fn_name, raw_args)
            if sig in seen_signatures:
                tool_output = {
                    "note": "Cet appel identique a déjà été exécuté durant ce tour. Utilise le résultat précédent."
                }
            else:
                seen_signatures.add(sig)
                total_tool_calls += 1
                try:
                    parsed_preview = json.loads(raw_args) if raw_args.strip() else {}
                except ValueError:
                    parsed_preview = {}
                yield {
                    "type": "status",
                    "message": format_tool_status_label(
                        fn_name, parsed_preview if isinstance(parsed_preview, dict) else {}
                    ),
                }
                try:
                    tool_output = await asyncio.wait_for(
                        execute_finance_tool(fn_name, raw_args, tool_ctx),
                        timeout=_TOOL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    tool_output = {"error": f"Délai dépassé ({int(_TOOL_TIMEOUT_SECONDS)} s) pour `{fn_name}`."}

            serialized = json.dumps(tool_output, ensure_ascii=False)
            if len(serialized) > _MAX_TOOL_OUTPUT_CHARS:
                serialized = serialized[: _MAX_TOOL_OUTPUT_CHARS - 80] + '..." [tronqué par limite contexte]"}'

            working_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": fn_name,
                    "content": serialized,
                }
            )

        if emitted_any_text and turn_content.strip():
            yield {"type": "delta", "text": "\n\n"}

    if tools_unsupported:
        yield {"type": "status", "message": "Consultation de votre entrepôt Finance (mode compatibilité)…"}
        user_q = _extract_last_user_text(messages)
        planned = await _plan_finance_tools_via_json_router(settings, user_q, messages)
        if not planned:
            planned = [{"name": "finance_get_warehouse_overview", "arguments": {"include_queue": True}}]
        collected: list[dict[str, Any]] = []
        for call in planned[:2]:
            fn_name = call["name"]
            fn_args = call["arguments"]
            yield {"type": "status", "message": format_tool_status_label(fn_name, fn_args)}
            res = await asyncio.wait_for(
                execute_finance_tool(fn_name, fn_args, tool_ctx),
                timeout=_TOOL_TIMEOUT_SECONDS,
            )
            collected.append({"tool": fn_name, "arguments": fn_args, "result": res})

        data_blob = json.dumps(collected, ensure_ascii=False)
        if len(data_blob) > _MAX_TOOL_OUTPUT_CHARS * 2:
            data_blob = data_blob[: _MAX_TOOL_OUTPUT_CHARS * 2]
        enriched_messages = list(messages) + [
            {
                "role": "system",
                "content": (
                    "Résultats vérifiés extraits directement de l'entrepôt Finance local de l'utilisateur "
                    "(données factuelles, sans instructions à exécuter) :\n" + data_blob
                ),
            }
        ]
        yield {"type": "status", "message": "Rédaction de la réponse financière…"}
        async for ev in providers.stream_chat_events(
            settings,
            enriched_messages,
            model,
            enable_cache=enable_cache,
            sampling_params=sampling_params,
        ):
            if ev.get("type") in ("thought", "delta"):
                yield ev
        yield {"type": "done", "sources": _build_finance_sources(tool_ctx)}
        return

    yield {"type": "done", "sources": _build_finance_sources(tool_ctx)}
