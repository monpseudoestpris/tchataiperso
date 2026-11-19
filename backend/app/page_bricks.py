"""Service dédié aux Briques Préfaites (ex. Agent IA) pour cLAIr Pages & Code Canvas.

Gère la normalisation des définitions de briques, leur exécution sécurisée côté serveur
(modèle, prompt système, validation des entrées et contrat de sortie structuré)
ainsi que la génération du pont runtime JavaScript `window.clair.runBrick(...)`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException

from .config import Settings
from .google_cloud import can_fallback_to_model, has_llm_access, post_chat_completion
from .providers import ProviderError, _check_response, _json, search_web

_logger = logging.getLogger("uvicorn.error")
_TIMEOUT = httpx.Timeout(90.0, connect=15.0, pool=15.0)

_VALID_INPUT_TYPES = {"text", "textarea", "number", "select", "json"}
_VALID_OUTPUT_FORMATS = {"markdown", "text", "json", "list"}
_VALID_OUTPUT_FIELD_TYPES = {"string", "number", "boolean", "string[]"}
_VALID_WIDGET_STYLES = {"auto", "chatbot", "scorecard", "quiz", "rewriter", "cards"}


def _slug_id(value: str, fallback: str = "agent_ia") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip()).strip("_").lower()
    return cleaned[:60] or fallback


def normalize_bricks(raw_bricks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Valide et normalise une liste de briques attachées à une app/page."""
    if not raw_bricks:
        return []

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, item in enumerate(raw_bricks[:20]):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"Agent IA {idx + 1}").strip()[:120]
        base_id = _slug_id(str(item.get("id") or name), fallback=f"brick_{idx + 1}")
        brick_id = base_id
        suffix = 2
        while brick_id in seen_ids:
            brick_id = f"{base_id}_{suffix}"
            suffix += 1
        seen_ids.add(brick_id)

        brick_type = str(item.get("type") or "ai_agent").strip()
        if brick_type not in {"ai_agent", "web_search_agent", "finance_eod_agent"}:
            brick_type = "ai_agent"

        raw_inputs = item.get("inputs") if isinstance(item.get("inputs"), list) else []
        norm_inputs: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for f_idx, field in enumerate(raw_inputs[:20]):
            if not isinstance(field, dict):
                continue
            f_label = str(field.get("label") or field.get("key") or f"Entrée {f_idx + 1}").strip()[:100]
            f_key = _slug_id(str(field.get("key") or f_label), fallback=f"input_{f_idx + 1}")
            if f_key in seen_keys:
                f_key = f"{f_key}_{f_idx + 1}"
            seen_keys.add(f_key)
            f_type = str(field.get("type") or "text").strip().lower()
            if f_type not in _VALID_INPUT_TYPES:
                f_type = "text"
            options = [
                str(opt).strip()[:120]
                for opt in (field.get("options") or [])
                if str(opt).strip()
            ][:30]
            norm_inputs.append({
                "key": f_key,
                "label": f_label,
                "type": f_type,
                "required": bool(field.get("required", True)),
                "placeholder": str(field.get("placeholder") or "").strip()[:240],
                "default_value": str(field.get("default_value") or "").strip()[:1000],
                "options": options,
            })

        raw_out = item.get("output_spec") if isinstance(item.get("output_spec"), dict) else {}
        out_format = str(raw_out.get("format") or "markdown").strip().lower()
        if out_format not in _VALID_OUTPUT_FORMATS:
            out_format = "markdown"
        raw_out_fields = raw_out.get("fields") if isinstance(raw_out.get("fields"), list) else []
        norm_out_fields: list[dict[str, str]] = []
        for o_idx, of in enumerate(raw_out_fields[:25]):
            if not isinstance(of, dict):
                continue
            o_key = _slug_id(str(of.get("key") or f"champ_{o_idx + 1}"), fallback=f"champ_{o_idx + 1}")
            o_type = str(of.get("type") or "string").strip()
            if o_type not in _VALID_OUTPUT_FIELD_TYPES:
                o_type = "string"
            norm_out_fields.append({
                "key": o_key,
                "type": o_type,
                "description": str(of.get("description") or "").strip()[:250],
            })

        widget_style = str(item.get("widget_style") or "auto").strip().lower()
        if widget_style not in _VALID_WIDGET_STYLES:
            widget_style = "auto"

        normalized.append({
            "id": brick_id,
            "name": name,
            "type": brick_type,
            "description": str(item.get("description") or "").strip()[:400],
            "model": str(item.get("model") or "auto").strip()[:200],
            "system_prompt": str(item.get("system_prompt") or "").strip()[:8000],
            "web_search_enabled": bool(item.get("web_search_enabled", brick_type == "web_search_agent")),
            "finance_data_enabled": bool(item.get("finance_data_enabled", brick_type == "finance_eod_agent")),
            "show_widget": bool(item.get("show_widget", False)),
            "widget_style": widget_style,
            "welcome_message": str(item.get("welcome_message") or "").strip()[:1000],
            "inputs": norm_inputs,
            "output_spec": {
                "format": out_format,
                "description": str(raw_out.get("description") or "").strip()[:1000],
                "fields": norm_out_fields,
            },
        })

    return normalized


def build_bricks_prompt_context(bricks: list[dict[str, Any]] | None) -> str:
    """Construit le contexte SDK à injecter dans les prompts IA pour câbler les briques."""
    norm = normalize_bricks(bricks)
    if not norm:
        return ""

    lines = [
        "BRIQUES PRÉFAITES CONNECTÉES DISPONIBLES DANS L'APPLICATION :",
        "Le runtime de la page expose automatiquement `await window.clair.runBrick(brickId, inputs)` qui appelle le backend sécurisé.",
        "Utilise directement ces briques depuis le JavaScript de l'application :",
    ]
    for brick in norm:
        input_example = {
            inp["key"]: inp.get("default_value") or inp.get("placeholder") or f"<{inp['type']}>"
            for inp in brick["inputs"]
        }
        out_spec = brick["output_spec"]
        out_desc = f"format={out_spec['format']}"
        if out_spec["format"] == "json" and out_spec["fields"]:
            keys_str = ", ".join(f"{f['key']}:{f['type']}" for f in out_spec["fields"])
            out_desc += f" ({keys_str})"
        elif out_spec["description"]:
            out_desc += f" ({out_spec['description']})"
        lines.append(
            f"- Brique `{brick['id']}` ({brick['name']}) | Modèle: {brick['model'] or 'auto'}\n"
            f"  Appel JS: `const res = await window.clair.runBrick({json.dumps(brick['id'])}, {json.dumps(input_example, ensure_ascii=False)});`\n"
            f"  Sortie (`res.output`): {out_desc}"
        )
    return "\n".join(lines)


def _extract_json_payload(raw_text: str) -> Any:
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    obj_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except Exception:
            pass
    return None


def _coerce_field_value(value: Any, expected_type: str) -> Any:
    if expected_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        try:
            num_str = str(value).replace(",", ".").strip()
            return float(num_str) if "." in num_str else int(num_str)
        except Exception:
            return 0
    if expected_type == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "1", "oui", "yes"}
    if expected_type == "string[]":
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [line.strip("- •\t ") for line in value.splitlines() if line.strip()]
        return []
    return "" if value is None else (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))


def _build_demo_output(brick: dict[str, Any], inputs: dict[str, Any]) -> tuple[Any, str]:
    out_spec = brick.get("output_spec") or {}
    out_format = out_spec.get("format", "markdown")
    fields = out_spec.get("fields") or []
    widget_style = brick.get("widget_style", "auto")
    clean_inputs = {k: v for k, v in inputs.items() if k != "_history"}
    input_preview = ", ".join(f"{k}={str(v)[:60]}" for k, v in clean_inputs.items()) or "aucune entrée"

    if out_format == "json":
        demo_obj: dict[str, Any] = {}
        for f in fields:
            f_key = f["key"]
            f_type = f.get("type", "string")
            if f_type == "number":
                demo_obj[f_key] = 17 if "20" in f_key else 85
            elif f_type == "boolean":
                demo_obj[f_key] = True
            elif f_type == "string[]":
                if widget_style == "quiz" and "question" in f_key:
                    demo_obj[f_key] = [
                        "Quel est le principe central du sujet ? | A) Une approche modulaire | B) Une boucle infinie | C) Un stockage volatil | D) Aucune réponse | Réponse: A | Explication: Une architecture modulaire facilite la maintenance et les tests.",
                        "Quel format facilite l'échange structuré ? | A) BMP | B) JSON | C) WAV | D) MIDI | Réponse: B | Explication: Le JSON est léger, lisible et natif en JavaScript.",
                    ]
                else:
                    demo_obj[f_key] = [
                        f"Élément 1 généré pour {brick['name']}",
                        f"Élément 2 basé sur ({input_preview})",
                    ]
            else:
                demo_obj[f_key] = f"[Mode démo · {brick['name']}] Réponse pour {f_key} ({input_preview})"
        if not demo_obj:
            demo_obj = {"resultat": f"[Mode démo · {brick['name']}] Traitement effectué pour : {input_preview}"}
        return demo_obj, json.dumps(demo_obj, ensure_ascii=False, indent=2)

    if out_format == "list":
        items = [
            f"Point clé 1 ({brick['name']}) : analyse de {input_preview}",
            "Point clé 2 : recommandation structurée prête à l'emploi",
            "Point clé 3 : vérification finale effectuée",
        ]
        return items, "\n".join(f"- {it}" for it in items)

    if widget_style == "chatbot":
        msg = clean_inputs.get("message") or next(iter(clean_inputs.values()), "")
        reply = (
            f"Bonjour ! Voici ma réponse de démonstration pour : « {str(msg)[:120]} ».\n\n"
            f"*(Mode démo actif sur {brick['name']} — ajoutez une clé API LLM dans `.env` pour dialoguer avec le modèle réel.)*"
        )
        return reply, reply

    text_val = (
        f"### Résultat de {brick['name']} (mode démonstration)\n\n"
        f"**Entrées reçues :** {input_preview}\n\n"
        f"**Sortie attendue :** {out_spec.get('description') or 'Synthèse structurée'}\n\n"
        "Configurez une clé API LLM dans `.env` pour activer les réponses complètes du modèle choisi."
    )
    if out_format == "text":
        text_val = re.sub(r"[#*`]", "", text_val)
    return text_val, text_val


def _compute_technical_indicators_summary(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcule SMA20, SMA50, RSI14, MACD et variations à partir des barres EOD chronologiques."""
    closes = [float(b["close"]) for b in bars if isinstance(b.get("close"), (int, float))]
    if not closes:
        return {}

    last = closes[-1]
    sma20 = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 20 else None
    sma50 = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 50 else None

    rsi14 = None
    if len(closes) >= 15:
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent = deltas[-14:]
        gains = sum(d for d in recent if d > 0) / 14.0
        losses = sum(-d for d in recent if d < 0) / 14.0
        if losses == 0:
            rsi14 = 100.0
        else:
            rs = gains / losses
            rsi14 = round(100.0 - (100.0 / (1.0 + rs)), 2)

    def _ema(values: list[float], period: int) -> list[float]:
        if len(values) < period:
            return []
        k = 2.0 / (period + 1)
        ema_vals = [sum(values[:period]) / period]
        for v in values[period:]:
            ema_vals.append(v * k + ema_vals[-1] * (1.0 - k))
        return ema_vals

    macd_val = None
    if len(closes) >= 26:
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        if ema12 and ema26:
            macd_val = round(ema12[-1] - ema26[-1], 4)

    period_return_pct = round(((last - closes[0]) / closes[0]) * 100, 2) if closes[0] else None
    return {
        "bars_count": len(closes),
        "last_close": round(last, 4),
        "period_high": round(max(closes), 4),
        "period_low": round(min(closes), 4),
        "period_return_pct": period_return_pct,
        "sma_20": round(sma20, 4) if sma20 is not None else None,
        "sma_50": round(sma50, 4) if sma50 is not None else None,
        "rsi_14": rsi14,
        "macd": macd_val,
    }


async def _fetch_brick_finance_context(settings: Settings, cleaned_inputs: dict[str, Any]) -> str:
    """Collecte les données réelles EODHD + Yahoo Finance + indicateurs techniques + signaux MOAT."""
    query = ""
    for key in ("symbole", "ticker", "entreprise", "action", "requete", "sujet"):
        val = str(cleaned_inputs.get(key) or "").strip()
        if val:
            query = val
            break
    if not query:
        for val in cleaned_inputs.values():
            if isinstance(val, str) and val.strip():
                query = val.strip()[:80]
                break
    if not query:
        return ""

    horizon = str(cleaned_inputs.get("horizon") or "").lower()
    chart_range = "3m"
    limit_bars = 90
    if "1 mois" in horizon or horizon == "1m":
        chart_range, limit_bars = "1m", 35
    elif "6 mois" in horizon or horizon == "6m":
        chart_range, limit_bars = "6m", 140
    elif "1 an" in horizon or horizon == "1y":
        chart_range, limit_bars = "1y", 260

    try:
        from .finance import get_financial_dashboard_data
        from .finance_moat import compute_moat_quantitative_signals

        data = await get_financial_dashboard_data(
            settings, query, limit_bars=limit_bars, chart_range=chart_range
        )
    except Exception as exc:
        _logger.warning("Collecte données finance brique échouée pour '%s': %s", query, exc)
        return ""

    bars = data.get("eod_bars") or []
    tech = _compute_technical_indicators_summary(bars)
    stats = data.get("financial_stats") or {}
    moat_signals = compute_moat_quantitative_signals(stats)

    summary = {
        "symbol": data.get("symbol"),
        "eod_ticker": data.get("eod_ticker"),
        "yahoo_symbol": data.get("yahoo_symbol"),
        "name": data.get("long_name") or data.get("short_name"),
        "exchange": data.get("exchange"),
        "currency": data.get("currency"),
        "price": data.get("price"),
        "change": data.get("change"),
        "change_percent": data.get("change_percent"),
        "volume": data.get("volume"),
        "technical_indicators": tech,
        "financial_stats": stats,
        "moat_quantitative_signals": moat_signals,
    }
    return json.dumps(summary, ensure_ascii=False, default=str)[:9000]


def _extract_history_messages(raw_history: Any) -> list[dict[str, str]]:
    if not isinstance(raw_history, list):
        return []
    messages: list[dict[str, str]] = []
    for turn in raw_history[-12:]:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:2500]})
    return messages


async def execute_page_brick(
    *,
    settings: Settings,
    brick: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    fallback_model: str | None = None,
) -> dict[str, Any]:
    """Exécute une brique Agent IA avec validation des entrées et structuration des sorties."""
    norm_list = normalize_bricks([brick])
    if not norm_list:
        raise HTTPException(422, "Définition de brique invalide")
    spec = norm_list[0]

    provided = dict(inputs or {})
    cleaned_inputs: dict[str, Any] = {}
    for field in spec["inputs"]:
        key = field["key"]
        raw_val = provided.get(key)
        if raw_val is None or (isinstance(raw_val, str) and not raw_val.strip()):
            raw_val = field.get("default_value") or ""
        if field.get("required") and (raw_val is None or (isinstance(raw_val, str) and not raw_val.strip())):
            raise HTTPException(422, f"Le champ requis « {field['label']} » ({key}) est vide.")
        cleaned_inputs[key] = raw_val

    # Inclure également toute clé supplémentaire transmise par le code JS de l'app (hors _history)
    history_messages = _extract_history_messages(provided.get("_history"))
    for k, v in provided.items():
        if k not in cleaned_inputs and k != "_history":
            cleaned_inputs[k] = v

    target_model = (
        spec["model"]
        if spec.get("model") and spec["model"] != "auto"
        else (fallback_model or getattr(settings, "default_model", None) or "openai/gpt-4o-mini")
    )

    out_spec = spec["output_spec"]
    out_format = out_spec["format"]

    # Mode démonstration ou absence d'accès fournisseur -> réponse structurée propre
    if getattr(settings, "demo_mode", False) or not has_llm_access(settings, target_model):
        demo_out, demo_raw = _build_demo_output(spec, cleaned_inputs)
        return {
            "brick_id": spec["id"],
            "brick_name": spec["name"],
            "model_used": f"{target_model} (démo)",
            "format": out_format,
            "output": demo_out,
            "raw_text": demo_raw,
            "sources": [],
        }

    # Recherche web optionnelle si activée sur la brique
    web_sources: list[dict[str, str]] = []
    if spec.get("web_search_enabled"):
        query_parts = [str(v).strip() for v in cleaned_inputs.values() if isinstance(v, str) and v.strip()]
        search_query = " ".join(query_parts)[:240]
        if search_query:
            try:
                web_sources = await search_web(settings, search_query, limit=5)
            except Exception as exc:
                _logger.warning("Recherche web brique '%s' échouée (non bloquant): %s", spec["id"], exc)

    # Données boursières EODHD / Yahoo Finance & indicateurs techniques si activés
    finance_context = ""
    if spec.get("finance_data_enabled"):
        finance_context = await _fetch_brick_finance_context(settings, cleaned_inputs)

    # Construction du contrat système
    sys_parts = [
        f"Tu es l'agent IA intégré « {spec['name']} » (brique applicative cLAIr).",
    ]
    if spec["system_prompt"]:
        sys_parts.append(f"INSTRUCTIONS DE L'AGENT :\n{spec['system_prompt']}")
    if out_spec.get("description"):
        sys_parts.append(f"SORTIE ATTENDUE :\n{out_spec['description']}")

    if out_format == "json":
        schema_lines = []
        for f in out_spec.get("fields") or []:
            schema_lines.append(f'- "{f["key"]}" ({f["type"]}) : {f.get("description") or f["key"]}')
        schema_txt = "\n".join(schema_lines) if schema_lines else '- "resultat" (string) : réponse principale'
        sys_parts.append(
            "FORMAT DE SORTIE STRICTEMENT OBLIGATOIRE :\n"
            "Réponds UNIQUEMENT avec un objet JSON valide (sans texte avant ni après) contenant exactement les clés suivantes :\n"
            f"{schema_txt}"
        )
    elif out_format == "list":
        sys_parts.append(
            "FORMAT DE SORTIE STRICTEMENT OBLIGATOIRE :\n"
            'Réponds UNIQUEMENT avec un tableau JSON valide de chaînes de caractères (ex. ["élément 1", "élément 2"]).'
        )
    elif out_format == "text":
        sys_parts.append("FORMAT DE SORTIE : Réponds en texte brut clair, concis et sans balises Markdown superflues.")
    else:
        sys_parts.append("FORMAT DE SORTIE : Réponds en Markdown bien structuré et directement exploitable.")

    # Construction du message utilisateur à partir des entrées
    user_lines = ["ENTRÉES FOURNIES PAR L'APPLICATION :"]
    if not cleaned_inputs:
        user_lines.append("(Aucune entrée structurée fournie)")
    else:
        label_by_key = {f["key"]: f["label"] for f in spec["inputs"]}
        for k, v in cleaned_inputs.items():
            lbl = label_by_key.get(k, k)
            val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            user_lines.append(f"- {lbl} (`{k}`) :\n{val_str}")

    if finance_context:
        user_lines.append(
            "\nDONNÉES BOURSIÈRES RÉELLES (EODHD / YAHOO FINANCE / INDICATEURS TECHNIQUES) :\n"
            f"{finance_context}"
        )

    if web_sources:
        user_lines.append("\nSOURCES WEB RÉCENTES COLLECTÉES :")
        for idx, src in enumerate(web_sources, start=1):
            user_lines.append(
                f"[{idx}] {src.get('title', 'Source')} ({src.get('url', '')})\n{src.get('snippet', '')}"
            )

    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": "\n\n".join(sys_parts)},
        *history_messages,
        {"role": "user", "content": "\n".join(user_lines)},
    ]
    request_payload: dict[str, Any] = {
        "model": target_model,
        "messages": llm_messages,
        "stream": False,
        "temperature": 0.35 if out_format in {"json", "list"} else 0.6,
        "max_tokens": 4096,
    }
    if out_format == "json":
        request_payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await post_chat_completion(settings, request_payload, client=client)
            if response.status_code in (400, 422) and "response_format" in request_payload:
                # Certains modèles/routeurs n'acceptent pas response_format
                retry_payload = {k: v for k, v in request_payload.items() if k != "response_format"}
                response = await post_chat_completion(settings, retry_payload, client=client)
            default_m = getattr(settings, "default_model", "")
            if (
                response.status_code in (400, 404, 422)
                and default_m
                and default_m != target_model
                and can_fallback_to_model(settings, target_model, default_m)
            ):
                target_model = default_m
                retry_payload = {**request_payload, "model": target_model}
                retry_payload.pop("response_format", None)
                response = await post_chat_completion(settings, retry_payload, client=client)
            _check_response(response, "Fournisseur IA")
            payload = _json(response, "Fournisseur IA")
            raw_text = str(payload["choices"][0]["message"]["content"] or "").strip()
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Erreur réseau lors de l'appel à l'agent IA : {exc}") from exc

    parsed_output: Any = raw_text
    if out_format == "json":
        parsed = _extract_json_payload(raw_text)
        if isinstance(parsed, dict):
            fields = out_spec.get("fields") or []
            if fields:
                structured: dict[str, Any] = {}
                for f in fields:
                    f_key = f["key"]
                    structured[f_key] = _coerce_field_value(parsed.get(f_key), f["type"])
                for k, v in parsed.items():
                    if k not in structured:
                        structured[k] = v
                parsed_output = structured
            else:
                parsed_output = parsed
        else:
            parsed_output = {"raw": raw_text}
    elif out_format == "list":
        parsed = _extract_json_payload(raw_text)
        if isinstance(parsed, list):
            parsed_output = [str(item).strip() for item in parsed if str(item).strip()]
        elif isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
            parsed_output = [str(item).strip() for item in parsed["items"] if str(item).strip()]
        else:
            parsed_output = [
                line.strip("- •*\t ")
                for line in raw_text.splitlines()
                if line.strip()
            ]

    return {
        "brick_id": spec["id"],
        "brick_name": spec["name"],
        "model_used": target_model,
        "format": out_format,
        "output": parsed_output,
        "raw_text": raw_text,
        "sources": web_sources,
    }


_BRICKS_RUNTIME_TEMPLATE = r"""
// === cLAIr Bricks Runtime (SDK Agent IA + Widgets Clé-en-main) ===
(function() {
  if (typeof window === 'undefined') return;
  var BRICKS = __BRICKS_JSON__;
  window.__CLAIR_BRICKS__ = BRICKS;

  var pendingCalls = {};
  var seq = 0;

  if (!window.__clair_brick_listener__) {
    window.__clair_brick_listener__ = true;
    window.addEventListener('message', function(event) {
      var data = event && event.data;
      if (!data || data.type !== 'CLAIR_BRICK_RESULT') return;
      var entry = pendingCalls[data.requestId];
      if (!entry) return;
      delete pendingCalls[data.requestId];
      clearTimeout(entry.timer);
      if (data.ok) {
        entry.resolve(data.result);
      } else {
        entry.reject(new Error(data.error || "Erreur lors de l'exécution de la brique"));
      }
    });
  }

  function resolveBrick(brickIdOrName) {
    if (!BRICKS.length) return null;
    if (!brickIdOrName || brickIdOrName === 'default') return BRICKS[0];
    var needle = String(brickIdOrName).toLowerCase();
    for (var i = 0; i < BRICKS.length; i++) {
      if (String(BRICKS[i].id).toLowerCase() === needle || String(BRICKS[i].name).toLowerCase() === needle) {
        return BRICKS[i];
      }
    }
    return null;
  }

  function runBrick(brickId, inputs) {
    return new Promise(function(resolve, reject) {
      if (window.parent === window) {
        reject(new Error("Cette brique IA nécessite d'être exécutée dans l'environnement cLAIr (Aperçu Canvas ou Mes Apps)."));
        return;
      }
      var resolved = resolveBrick(brickId);
      var targetId = resolved ? resolved.id : String(brickId || 'default');
      var reqId = 'cb_' + (++seq) + '_' + Date.now();
      var timer = setTimeout(function() {
        if (pendingCalls[reqId]) {
          delete pendingCalls[reqId];
          reject(new Error("Délai d'attente dépassé pour la brique IA."));
        }
      }, 95000);
      pendingCalls[reqId] = { resolve: resolve, reject: reject, timer: timer };
      window.parent.postMessage({
        type: 'CLAIR_BRICK_CALL',
        requestId: reqId,
        brickId: targetId,
        inputs: inputs || {}
      }, '*');
    });
  }

  window.clair = window.clair || {};
  window.clair.listBricks = function() { return BRICKS.slice(); };
  window.clair.runBrick = runBrick;
  window.clair.askAgent = function(brickIdOrInputs, maybeInputs) {
    if (typeof brickIdOrInputs === 'string') return runBrick(brickIdOrInputs, maybeInputs || {});
    return runBrick('default', brickIdOrInputs || {});
  };

  function inferWidgetStyle(brick) {
    if (brick.widget_style && brick.widget_style !== 'auto') return brick.widget_style;
    var fields = (brick.output_spec && brick.output_spec.fields) || [];
    var keys = fields.map(function(f) { return String(f.key || '').toLowerCase(); });
    if (keys.indexOf('questions') !== -1 && keys.indexOf('titre_quiz') !== -1) return 'quiz';
    if (keys.some(function(k) { return k.indexOf('note_') === 0 || k.indexOf('score_qualite') === 0; })) return 'scorecard';
    if (keys.indexOf('version_corrigee') !== -1 || keys.indexOf('traduction') !== -1) return 'rewriter';
    if (brick.id && brick.id.indexOf('bot_ia') !== -1) return 'chatbot';
    return 'cards';
  }

  function appendMetaFooter(container, res) {
    if (res && res.model_used) {
      var meta = document.createElement('div');
      meta.style.cssText = 'margin-top:8px;font-size:11px;color:#64748b;';
      meta.textContent = 'Modèle : ' + res.model_used;
      container.appendChild(meta);
    }
  }

  function renderQuizOutput(container, out, res) {
    var titleText = out.titre_quiz ? String(out.titre_quiz) : 'Quiz Interactif';
    var header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;';
    var titleEl = document.createElement('strong');
    titleEl.style.cssText = 'font-size:14px;color:#0f172a;';
    titleEl.textContent = '🎯 ' + titleText;
    var scoreBadge = document.createElement('span');
    scoreBadge.style.cssText = 'font-size:12px;font-weight:700;padding:3px 9px;border-radius:999px;background:#e0f2fe;color:#0369a1;';
    var rawQuestions = Array.isArray(out.questions) ? out.questions : [];
    var score = 0;
    var answered = 0;
    scoreBadge.textContent = 'Score : 0 / ' + rawQuestions.length;
    header.appendChild(titleEl);
    header.appendChild(scoreBadge);
    container.appendChild(header);

    rawQuestions.forEach(function(rawLine, qIdx) {
      var parts = String(rawLine).split('|').map(function(s) { return s.trim(); });
      var qCard = document.createElement('div');
      qCard.style.cssText = 'margin-bottom:10px;padding:10px;border-radius:10px;background:#ffffff;border:1px solid #cbd5e1;';
      var qTitle = document.createElement('div');
      qTitle.style.cssText = 'font-size:13px;font-weight:700;color:#0f172a;margin-bottom:7px;';
      qTitle.textContent = (qIdx + 1) + '. ' + (parts[0] || String(rawLine));
      qCard.appendChild(qTitle);

      var ansPart = parts.find(function(p) { return /^r[eé]ponse\s*:/i.test(p); }) || '';
      var expPart = parts.find(function(p) { return /^explication\s*:/i.test(p); }) || '';
      var correctLetter = ansPart.replace(/^r[eé]ponse\s*:/i, '').trim().charAt(0).toUpperCase();
      var options = parts.filter(function(p) { return /^[A-D][\)\.\:]/i.test(p); });

      var feedback = document.createElement('div');
      feedback.style.cssText = 'display:none;margin-top:6px;padding:6px 8px;border-radius:6px;font-size:12px;';

      if (options.length) {
        var optWrap = document.createElement('div');
        optWrap.style.cssText = 'display:grid;grid-template-columns:1fr;gap:5px;';
        var done = false;
        options.forEach(function(opt) {
          var letter = opt.trim().charAt(0).toUpperCase();
          var optBtn = document.createElement('button');
          optBtn.type = 'button';
          optBtn.textContent = opt;
          optBtn.style.cssText = 'text-align:left;padding:6px 9px;border-radius:7px;border:1px solid #cbd5e1;background:#f8fafc;color:#0f172a;font-size:12.5px;cursor:pointer;';
          optBtn.onclick = function() {
            if (done) return;
            done = true;
            answered += 1;
            var ok = !correctLetter || letter === correctLetter;
            if (ok) score += 1;
            scoreBadge.textContent = 'Score : ' + score + ' / ' + rawQuestions.length + ' (' + answered + ' rép.)';
            optBtn.style.background = ok ? '#dcfce7' : '#fee2e2';
            optBtn.style.borderColor = ok ? '#16a34a' : '#dc2626';
            optBtn.style.color = ok ? '#14532d' : '#7f1d1d';
            feedback.style.display = 'block';
            feedback.style.background = ok ? '#f0fdf4' : '#fef2f2';
            feedback.style.color = ok ? '#166534' : '#991b1b';
            feedback.textContent = (ok ? '✓ Bonne réponse ! ' : '✗ Réponse attendue : ' + (correctLetter || '?') + '. ') + expPart.replace(/^explication\s*:/i, '').trim();
          };
          optWrap.appendChild(optBtn);
        });
        qCard.appendChild(optWrap);
      }
      qCard.appendChild(feedback);
      container.appendChild(qCard);
    });

    if (out.conseil_revision) {
      var tip = document.createElement('div');
      tip.style.cssText = 'padding:8px;border-radius:8px;background:#fefce8;border:1px solid #fde047;font-size:12px;color:#713f12;';
      tip.textContent = '💡 ' + String(out.conseil_revision);
      container.appendChild(tip);
    }
    appendMetaFooter(container, res);
  }

  function renderRewriterOutput(container, out, res) {
    var mainKey = out.version_corrigee !== undefined ? 'version_corrigee' : (out.traduction !== undefined ? 'traduction' : Object.keys(out)[0]);
    var mainVal = mainKey ? String(out[mainKey] || '') : '';
    var box = document.createElement('div');
    box.style.cssText = 'padding:10px 12px;border-radius:10px;background:#ffffff;border:1px solid #93c5fd;margin-bottom:8px;';
    var top = document.createElement('div');
    top.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;';
    var lbl = document.createElement('strong');
    lbl.style.cssText = 'font-size:12px;text-transform:uppercase;color:#0284c7;';
    lbl.textContent = mainKey || 'Résultat';
    var copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.textContent = '📋 Copier';
    copyBtn.style.cssText = 'padding:3px 9px;border-radius:6px;border:1px solid #cbd5e1;background:#f8fafc;color:#0f172a;font-size:11.5px;font-weight:600;cursor:pointer;';
    copyBtn.onclick = function() {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(mainVal).then(function() {
          copyBtn.textContent = '✓ Copié !';
          setTimeout(function() { copyBtn.textContent = '📋 Copier'; }, 1600);
        }).catch(function() {});
      }
    };
    top.appendChild(lbl);
    top.appendChild(copyBtn);
    var textBody = document.createElement('div');
    textBody.style.cssText = 'white-space:pre-wrap;font-size:13.5px;line-height:1.55;color:#0f172a;';
    textBody.textContent = mainVal;
    box.appendChild(top);
    box.appendChild(textBody);
    container.appendChild(box);

    Object.keys(out).forEach(function(k) {
      if (k === mainKey) return;
      var row = document.createElement('div');
      row.style.cssText = 'margin-bottom:6px;padding:7px 9px;border-radius:8px;background:rgba(15,23,42,0.04);';
      var keyEl = document.createElement('div');
      keyEl.style.cssText = 'font-size:11px;font-weight:700;text-transform:uppercase;color:#0284c7;margin-bottom:2px;';
      keyEl.textContent = k;
      var valEl = document.createElement('div');
      valEl.style.cssText = 'font-size:12.5px;white-space:pre-wrap;';
      var v = out[k];
      valEl.textContent = Array.isArray(v) ? v.map(function(x) { return '• ' + x; }).join('\n') : String(v);
      row.appendChild(keyEl);
      row.appendChild(valEl);
      container.appendChild(row);
    });
    appendMetaFooter(container, res);
  }

  function renderScorecardOutput(container, out, res) {
    var scoreKey = Object.keys(out).find(function(k) { return typeof out[k] === 'number'; });
    var boolKey = Object.keys(out).find(function(k) { return typeof out[k] === 'boolean'; });
    if (scoreKey || boolKey) {
      var banner = document.createElement('div');
      banner.style.cssText = 'display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;border-radius:10px;background:#ffffff;border:1px solid #cbd5e1;margin-bottom:8px;';
      if (scoreKey) {
        var denom = scoreKey.indexOf('20') !== -1 ? '/20' : '/100';
        var pill = document.createElement('span');
        pill.style.cssText = 'font-size:18px;font-weight:800;color:#0284c7;';
        pill.textContent = String(out[scoreKey]) + denom;
        banner.appendChild(pill);
      }
      if (boolKey) {
        var ok = Boolean(out[boolKey]);
        var statusPill = document.createElement('span');
        statusPill.style.cssText = 'padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;' + (ok ? 'background:#dcfce7;color:#166534;' : 'background:#fee2e2;color:#991b1b;');
        statusPill.textContent = ok ? '✓ Validé' : '⚠ À améliorer';
        banner.appendChild(statusPill);
      }
      container.appendChild(banner);
    }
    Object.keys(out).forEach(function(k) {
      if (k === scoreKey || k === boolKey) return;
      var row = document.createElement('div');
      row.style.cssText = 'margin-bottom:7px;padding:8px;border-radius:8px;background:rgba(15,23,42,0.04);';
      var keyEl = document.createElement('div');
      keyEl.style.cssText = 'font-size:11px;font-weight:700;text-transform:uppercase;color:#0284c7;margin-bottom:3px;';
      keyEl.textContent = k;
      var valEl = document.createElement('div');
      valEl.style.cssText = 'font-size:13px;white-space:pre-wrap;line-height:1.45;';
      var v = out[k];
      valEl.textContent = Array.isArray(v) ? v.map(function(x) { return '• ' + x; }).join('\n') : (typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v));
      row.appendChild(keyEl);
      row.appendChild(valEl);
      container.appendChild(row);
    });
    appendMetaFooter(container, res);
  }

  // Rendu automatique sécurisé (sans innerHTML sur les données utilisateur)
  function renderOutputInto(container, res, brick) {
    while (container.firstChild) container.removeChild(container.firstChild);
    var out = res && res.output !== undefined ? res.output : res;
    var styleMode = brick ? inferWidgetStyle(brick) : 'cards';

    if (out && typeof out === 'object' && !Array.isArray(out)) {
      if (styleMode === 'quiz' && Array.isArray(out.questions)) {
        renderQuizOutput(container, out, res);
        return;
      }
      if (styleMode === 'rewriter') {
        renderRewriterOutput(container, out, res);
        return;
      }
      if (styleMode === 'scorecard') {
        renderScorecardOutput(container, out, res);
        return;
      }
    }

    if (Array.isArray(out)) {
      var ul = document.createElement('ul');
      ul.style.cssText = 'margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px;';
      out.forEach(function(item) {
        var li = document.createElement('li');
        li.textContent = typeof item === 'string' ? item : JSON.stringify(item);
        ul.appendChild(li);
      });
      container.appendChild(ul);
    } else if (out && typeof out === 'object') {
      Object.keys(out).forEach(function(k) {
        var row = document.createElement('div');
        row.style.cssText = 'margin-bottom:8px;padding:8px;border-radius:8px;background:rgba(15,23,42,0.04);';
        var keyEl = document.createElement('div');
        keyEl.style.cssText = 'font-size:11px;font-weight:700;text-transform:uppercase;color:#0284c7;margin-bottom:3px;';
        keyEl.textContent = k;
        var valEl = document.createElement('div');
        valEl.style.cssText = 'font-size:13px;white-space:pre-wrap;line-height:1.45;';
        var v = out[k];
        valEl.textContent = Array.isArray(v) ? v.map(function(x) { return '• ' + x; }).join('\n') : (typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v));
        row.appendChild(keyEl);
        row.appendChild(valEl);
        container.appendChild(row);
      });
    } else {
      var pre = document.createElement('div');
      pre.style.cssText = 'white-space:pre-wrap;font-size:13px;line-height:1.5;';
      pre.textContent = String(out || '');
      container.appendChild(pre);
    }
    appendMetaFooter(container, res);
  }

  function buildChatbotPanel(brick, embedded) {
    var card = document.createElement('div');
    card.style.cssText = embedded
      ? 'border:1px solid rgba(148,163,184,0.35);border-radius:14px;padding:14px;background:#ffffff;color:#0f172a;font-family:system-ui,-apple-system,sans-serif;box-shadow:0 6px 22px rgba(15,23,42,0.07);display:flex;flex-direction:column;gap:10px;'
      : 'padding:12px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;margin-bottom:10px;display:flex;flex-direction:column;gap:8px;';

    var titleRow = document.createElement('div');
    titleRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;';
    var h = document.createElement('strong');
    h.style.cssText = 'font-size:14px;color:#0f172a;';
    h.textContent = '💬 ' + brick.name;
    var rightWrap = document.createElement('div');
    rightWrap.style.cssText = 'display:flex;align-items:center;gap:6px;';
    var badge = document.createElement('span');
    badge.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:999px;background:#e0f2fe;color:#0369a1;font-weight:600;';
    badge.textContent = brick.model && brick.model !== 'auto' ? brick.model.split('/').pop() : 'Modèle auto';
    var clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.textContent = 'Effacer';
    clearBtn.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:6px;border:1px solid #cbd5e1;background:#fff;color:#475569;cursor:pointer;';
    rightWrap.appendChild(badge);
    rightWrap.appendChild(clearBtn);
    titleRow.appendChild(h);
    titleRow.appendChild(rightWrap);
    card.appendChild(titleRow);

    var extraControls = {};
    var inputs = brick.inputs || [];
    var primaryField = inputs.find(function(inp) { return inp.type === 'textarea' || inp.type === 'text'; }) || inputs[0];
    var extraFields = inputs.filter(function(inp) { return !primaryField || inp.key !== primaryField.key; });

    if (extraFields.length) {
      var extraBar = document.createElement('div');
      extraBar.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;';
      extraFields.forEach(function(inp) {
        var lbl = document.createElement('label');
        lbl.style.cssText = 'display:flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:#475569;';
        lbl.textContent = inp.label + ':';
        var el;
        if (inp.type === 'select' && Array.isArray(inp.options) && inp.options.length) {
          el = document.createElement('select');
          inp.options.forEach(function(opt) {
            var o = document.createElement('option');
            o.value = opt;
            o.textContent = opt;
            el.appendChild(o);
          });
        } else {
          el = document.createElement('input');
          el.type = 'text';
        }
        el.style.cssText = 'padding:4px 7px;border-radius:6px;border:1px solid #cbd5e1;font-size:12px;background:#fff;color:#0f172a;';
        if (inp.default_value) el.value = inp.default_value;
        extraControls[inp.key] = el;
        lbl.appendChild(el);
        extraBar.appendChild(lbl);
      });
      card.appendChild(extraBar);
    }

    var history = [];
    var log = document.createElement('div');
    log.style.cssText = 'min-height:150px;max-height:300px;overflow-y:auto;padding:10px;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;display:flex;flex-direction:column;gap:8px;';

    function appendBubble(role, text) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;' + (role === 'user' ? 'justify-content:flex-end;' : 'justify-content:flex-start;');
      var bubble = document.createElement('div');
      bubble.style.cssText = role === 'user'
        ? 'max-width:82%;padding:8px 11px;border-radius:12px 12px 2px 12px;background:linear-gradient(135deg,#0284c7,#4f46e5);color:#fff;font-size:13px;line-height:1.45;white-space:pre-wrap;'
        : 'max-width:86%;padding:8px 11px;border-radius:12px 12px 12px 2px;background:#ffffff;border:1px solid #e2e8f0;color:#0f172a;font-size:13px;line-height:1.5;white-space:pre-wrap;';
      bubble.textContent = text;
      row.appendChild(bubble);
      log.appendChild(row);
      log.scrollTop = log.scrollHeight;
      return bubble;
    }

    function resetChat() {
      history = [];
      while (log.firstChild) log.removeChild(log.firstChild);
      appendBubble('assistant', brick.welcome_message || ('Bonjour ! Je suis ' + brick.name + '. Comment puis-je vous aider ?'));
    }
    clearBtn.onclick = resetChat;
    resetChat();

    var form = document.createElement('form');
    form.style.cssText = 'display:flex;gap:6px;align-items:flex-end;';
    var inputEl = document.createElement('textarea');
    inputEl.rows = 2;
    inputEl.placeholder = (primaryField && primaryField.placeholder) || 'Écrivez votre message…';
    inputEl.style.cssText = 'flex:1;padding:8px 10px;border-radius:9px;border:1px solid #cbd5e1;font-size:13px;font-family:inherit;resize:none;background:#fff;color:#0f172a;';
    var sendBtn = document.createElement('button');
    sendBtn.type = 'submit';
    sendBtn.textContent = 'Envoyer';
    sendBtn.style.cssText = 'padding:9px 14px;border:none;border-radius:9px;background:#0284c7;color:#fff;font-weight:700;font-size:12.5px;cursor:pointer;';
    form.appendChild(inputEl);
    form.appendChild(sendBtn);

    inputEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var text = inputEl.value.trim();
      if (!text || sendBtn.disabled) return;
      inputEl.value = '';
      appendBubble('user', text);
      var pendingBubble = appendBubble('assistant', 'Réflexion en cours…');
      sendBtn.disabled = true;

      var payload = { _history: history.slice() };
      Object.keys(extraControls).forEach(function(k) { payload[k] = extraControls[k].value; });
      if (primaryField) payload[primaryField.key] = text;
      else payload.message = text;

      runBrick(brick.id, payload).then(function(res) {
        var reply = typeof res.output === 'string' ? res.output : (res.raw_text || JSON.stringify(res.output, null, 2));
        pendingBubble.textContent = reply;
        history.push({ role: 'user', content: text });
        history.push({ role: 'assistant', content: reply });
      }).catch(function(err) {
        pendingBubble.textContent = 'Erreur : ' + (err && err.message ? err.message : String(err));
      }).finally(function() {
        sendBtn.disabled = false;
        log.scrollTop = log.scrollHeight;
      });
    });

    card.appendChild(log);
    card.appendChild(form);
    return card;
  }

  function buildBrickPanel(brick, embedded) {
    if (inferWidgetStyle(brick) === 'chatbot') {
      return buildChatbotPanel(brick, embedded);
    }

    var card = document.createElement('div');
    card.style.cssText = embedded
      ? 'border:1px solid rgba(148,163,184,0.35);border-radius:12px;padding:14px;background:#ffffff;color:#0f172a;font-family:system-ui,-apple-system,sans-serif;box-shadow:0 4px 16px rgba(15,23,42,0.06);'
      : 'padding:12px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;margin-bottom:10px;';

    var titleRow = document.createElement('div');
    titleRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;';
    var h = document.createElement('strong');
    h.style.cssText = 'font-size:14px;color:#0f172a;';
    h.textContent = '🤖 ' + brick.name;
    var badge = document.createElement('span');
    badge.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:999px;background:#e0f2fe;color:#0369a1;font-weight:600;';
    badge.textContent = brick.model && brick.model !== 'auto' ? brick.model.split('/').pop() : 'Modèle auto';
    titleRow.appendChild(h);
    titleRow.appendChild(badge);
    card.appendChild(titleRow);

    if (brick.description) {
      var desc = document.createElement('p');
      desc.style.cssText = 'margin:0 0 10px;font-size:12px;color:#475569;';
      desc.textContent = brick.description;
      card.appendChild(desc);
    }

    var form = document.createElement('form');
    form.style.cssText = 'display:flex;flex-direction:column;gap:8px;';
    var controls = {};

    (brick.inputs || []).forEach(function(inp) {
      var wrap = document.createElement('label');
      wrap.style.cssText = 'display:flex;flex-direction:column;gap:4px;font-size:12px;font-weight:600;color:#334155;';
      wrap.textContent = inp.label + (inp.required ? ' *' : '');
      var el;
      if (inp.type === 'textarea' || inp.type === 'json') {
        el = document.createElement('textarea');
        el.rows = 3;
      } else if (inp.type === 'select' && Array.isArray(inp.options) && inp.options.length) {
        el = document.createElement('select');
        inp.options.forEach(function(opt) {
          var o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          el.appendChild(o);
        });
      } else {
        el = document.createElement('input');
        el.type = inp.type === 'number' ? 'number' : 'text';
      }
      el.style.cssText = 'width:100%;box-sizing:border-box;padding:7px 9px;border:1px solid #cbd5e1;border-radius:7px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a;';
      if (inp.placeholder && 'placeholder' in el) el.placeholder = inp.placeholder;
      if (inp.default_value) el.value = inp.default_value;
      controls[inp.key] = el;
      wrap.appendChild(el);
      form.appendChild(wrap);
    });

    var btn = document.createElement('button');
    btn.type = 'submit';
    btn.textContent = "Exécuter l'agent IA";
    btn.style.cssText = 'align-self:flex-start;padding:8px 14px;border:none;border-radius:8px;background:#0284c7;color:#fff;font-weight:600;font-size:12.5px;cursor:pointer;';
    form.appendChild(btn);

    var outBox = document.createElement('div');
    outBox.style.cssText = 'display:none;margin-top:10px;padding:10px;border-radius:8px;border:1px solid #bae6fd;background:#f0f9ff;color:#0f172a;';

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var payload = {};
      Object.keys(controls).forEach(function(k) { payload[k] = controls[k].value; });
      btn.disabled = true;
      btn.textContent = 'Exécution en cours…';
      outBox.style.display = 'block';
      outBox.textContent = 'Analyse par ' + brick.name + '…';
      runBrick(brick.id, payload).then(function(res) {
        renderOutputInto(outBox, res, brick);
      }).catch(function(err) {
        outBox.textContent = 'Erreur : ' + (err && err.message ? err.message : String(err));
      }).finally(function() {
        btn.disabled = false;
        btn.textContent = "Exécuter l'agent IA";
      });
    });

    card.appendChild(form);
    card.appendChild(outBox);
    return card;
  }

  function mountBrickWidgets() {
    if (!BRICKS.length || !document.body) return;

    // 1. Monter les conteneurs explicites <div data-clair-brick="...">
    var explicitIds = {};
    document.querySelectorAll('[data-clair-brick]').forEach(function(host) {
      var bid = host.getAttribute('data-clair-brick');
      var brick = resolveBrick(bid);
      if (brick && !host.getAttribute('data-clair-mounted')) {
        host.setAttribute('data-clair-mounted', '1');
        explicitIds[brick.id] = true;
        host.appendChild(buildBrickPanel(brick, true));
      }
    });

    if (document.getElementById('clair-bricks-dock')) return;

    // 2. Monter le tiroir flottant pour les briques avec show_widget === true non déjà montées
    var dockBricks = BRICKS.filter(function(b) {
      return b.show_widget !== false && !explicitIds[b.id];
    });
    if (!dockBricks.length) return;

    var dock = document.createElement('div');
    dock.id = 'clair-bricks-dock';
    dock.className = 'no-print';
    dock.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483000;font-family:system-ui,-apple-system,sans-serif;';

    var panel = document.createElement('div');
    panel.style.cssText = 'display:none;width:min(410px, calc(100vw - 32px));max-height:74vh;overflow-y:auto;background:#ffffff;color:#0f172a;border:1px solid #cbd5e1;border-radius:14px;box-shadow:0 20px 45px rgba(15,23,42,0.25);padding:14px;margin-bottom:10px;';

    var header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;';
    var hTitle = document.createElement('strong');
    hTitle.style.cssText = 'font-size:13.5px;color:#0f172a;';
    hTitle.textContent = '🧩 Briques IA connectées (' + dockBricks.length + ')';
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = 'border:none;background:transparent;font-size:15px;cursor:pointer;color:#64748b;';
    closeBtn.onclick = function() { panel.style.display = 'none'; };
    header.appendChild(hTitle);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    dockBricks.forEach(function(b) {
      panel.appendChild(buildBrickPanel(b, false));
    });

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.textContent = '🧩 Briques IA (' + dockBricks.length + ')';
    toggle.style.cssText = 'padding:9px 14px;border:none;border-radius:999px;background:linear-gradient(135deg,#0284c7,#4f46e5);color:#fff;font-weight:700;font-size:12.5px;cursor:pointer;box-shadow:0 8px 24px rgba(2,132,199,0.35);';
    toggle.onclick = function() {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    };

    dock.appendChild(panel);
    dock.appendChild(toggle);
    document.body.appendChild(dock);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountBrickWidgets);
  } else {
    mountBrickWidgets();
  }
})();
"""


def build_bricks_runtime_js(bricks: list[dict[str, Any]] | None) -> str:
    """Génère le pont JS `window.clair.runBrick(...)` et les widgets prêts à l'emploi."""
    norm = normalize_bricks(bricks)
    bricks_json = json.dumps(norm, ensure_ascii=False).replace("</", "<\\/")
    return _BRICKS_RUNTIME_TEMPLATE.replace("__BRICKS_JSON__", bricks_json)


_BRICKS_SCRIPT_RE = re.compile(
    r'\n?<script\b[^>]*\bid=["\']clair-bricks-runtime-script["\'][^>]*>[\s\S]*?</script>\n?',
    re.IGNORECASE,
)


def inject_bricks_runtime_html(html_code: str, bricks: list[dict[str, Any]] | None) -> str:
    """Remplace ou injecte le runtime JS des briques (window.clair.runBrick + widgets) dans un document HTML."""
    if not html_code:
        return html_code
    cleaned = _BRICKS_SCRIPT_RE.sub("\n", html_code)
    norm = normalize_bricks(bricks)
    runtime_js = build_bricks_runtime_js(norm).strip()
    tag = f'\n<script id="clair-bricks-runtime-script">\n{runtime_js}\n</script>\n'
    if "</body>" in cleaned.lower():
        return re.sub(r"</body>", lambda _m: f"{tag}</body>", cleaned, count=1, flags=re.IGNORECASE)
    if "</html>" in cleaned.lower():
        return re.sub(r"</html>", lambda _m: f"{tag}</html>", cleaned, count=1, flags=re.IGNORECASE)
    return cleaned + tag


_VALID_DIAGRAM_KINDS = {"ui_input", "ai_brick", "ui_output", "ui_state"}

_DIAGRAM_PROPOSAL_PROMPT = """Tu es un architecte logiciel spécialisé dans les applications web propulsées par des agents IA cLAIr.
À partir de l'idée d'application décrite par l'utilisateur, conçois un DIAGRAMME D'ARCHITECTURE complet en JSON strict :
- L'application a une vraie interface utilisateur (composants `ui_input`, `ui_output`, `ui_state`) et un ou plusieurs cerveaux IA (`ai_brick`).
- Chaque brique `ai_brick` est intégrée À L'INTÉRIEUR de l'app (`show_widget: false`) et appelée via `window.clair.runBrick(id, inputs)`.
- Retourne UNIQUEMENT un objet JSON valide sans texte avant/après :
{
  "title": "Titre court de l'application",
  "summary": "Résumé clair de l'architecture et des flux de données",
  "nodes": [
    {
      "id": "node_slug",
      "kind": "ui_input | ai_brick | ui_output | ui_state",
      "label": "Nom affiché dans le diagramme",
      "subtitle": "Rôle UI ou résumé",
      "x": 60,
      "y": 90,
      "brick": null
    }
  ],
  "edges": [
    {
      "id": "e1",
      "from_node": "node_source_id",
      "to_node": "node_target_id",
      "label": "nom_variable_ou_donnee"
    }
  ]
}
Règles de disposition (coordonnées x, y dans un canevas ~920x520) :
- Place les nœuds `ui_input` à gauche (`x` autour de 40-80), les nœuds `ai_brick` au centre (`x` autour de 350-380) et les nœuds `ui_output` / `ui_state` à droite (`x` autour de 660-700), espacés verticalement (`y`: 45, 200, 355).
- Pour CHAQUE nœud `kind: "ai_brick"`, fournis un objet `"brick"` complet :
  {
    "id": "identifiant_snake_case",
    "name": "Nom lisible",
    "type": "ai_agent",
    "description": "Rôle dans l'app",
    "model": "auto",
    "system_prompt": "Instructions détaillées du personnage/agent",
    "web_search_enabled": false,
    "show_widget": false,
    "widget_style": "auto",
    "welcome_message": "",
    "inputs": [{"key": "cle", "label": "Libellé", "type": "text|textarea|select|number", "required": true, "placeholder": "", "default_value": "", "options": []}],
    "output_spec": {
      "format": "json",
      "description": "Ce que l'agent renvoie pour alimenter l'interface",
      "fields": [{"key": "reponse_bot", "type": "string", "description": "..."}, {"key": "score", "type": "number", "description": "..."}]
    }
  }
- Chaque flèche `edges` qui sort d'une brique `ai_brick` vers un composant `ui_output` doit porter en `label` le nom exact d'un champ de `output_spec.fields` (ex: `reponse_bot`, `score_comprehension`, `questions`)."""


def _build_fallback_diagram(prompt: str, title: str | None = None) -> dict[str, Any]:
    lower = prompt.lower()
    is_finance = any(kw in lower for kw in ("bourse", "finance", "action", "eod", "ticker", "rsi", "macd", "moat", "trading", "portefeuille", "indicateur"))
    is_quiz = any(kw in lower for kw in ("quiz", "qcm", "question", "révision", "revision", "examen"))
    is_bot = any(kw in lower for kw in ("bot", "chat", "niais", "élève", "eleve", "feynman", "tuteur", "personnage", "dialogue"))

    if is_finance:
        app_title = title or "Cockpit Boursier EOD & Indicateurs IA"
        return {
            "title": app_title,
            "summary": "L'utilisateur saisit un ticker ou une entreprise ; la brique EODHD/Yahoo calcule les indicateurs techniques (RSI, SMA, MACD) et l'analyste IA met à jour les cartes et signaux de l'app.",
            "nodes": [
                {"id": "ui_ticker", "kind": "ui_input", "label": "Recherche Ticker / Action", "subtitle": "Ex: AAPL, MC.PA, Stellantis + horizon", "x": 40, "y": 135},
                {
                    "id": "ai_eod",
                    "kind": "ai_brick",
                    "label": "Cotation EOD & Indicateurs",
                    "subtitle": "EODHD + Yahoo + RSI/SMA/MACD JSON",
                    "x": 350,
                    "y": 135,
                    "brick": {
                        "id": "finance_eod_indicateurs",
                        "name": "Cotation EOD & Indicateurs",
                        "type": "finance_eod_agent",
                        "description": "Analyse technique réelle basée sur les cours EODHD et Yahoo Finance.",
                        "model": "auto",
                        "system_prompt": "Tu es un analyste technique quantitatif. Appuie-toi sur les données EOD et indicateurs calculés (SMA20, SMA50, RSI14, MACD) pour produire une lecture claire et chiffrée.",
                        "web_search_enabled": False,
                        "finance_data_enabled": True,
                        "show_widget": False,
                        "widget_style": "auto",
                        "welcome_message": "",
                        "inputs": [
                            {"key": "symbole", "label": "Ticker ou entreprise", "type": "text", "required": True, "placeholder": "Ex: AAPL, MC.PA", "default_value": "AAPL", "options": []},
                            {"key": "horizon", "label": "Horizon", "type": "select", "required": False, "placeholder": "", "default_value": "3 mois", "options": ["1 mois", "3 mois", "6 mois", "1 an"]},
                        ],
                        "output_spec": {
                            "format": "json",
                            "description": "Cours, indicateurs et niveaux clés pour le cockpit boursier",
                            "fields": [
                                {"key": "ticker", "type": "string", "description": "Symbole boursier"},
                                {"key": "prix_actuel", "type": "number", "description": "Dernier cours connu"},
                                {"key": "rsi_14", "type": "number", "description": "RSI 14 jours"},
                                {"key": "tendance_technique", "type": "string", "description": "Haussière / Neutre / Baissière"},
                                {"key": "niveaux_cles", "type": "string[]", "description": "Supports, résistances et signaux SMA/MACD"},
                                {"key": "synthese_eod", "type": "string", "description": "Synthèse technique actionnable"},
                            ],
                        },
                    },
                },
                {"id": "ui_cards_eod", "kind": "ui_output", "label": "Cartes Cours & RSI/SMA", "subtitle": "Affiche prix_actuel, rsi_14 et tendance", "x": 670, "y": 55},
                {"id": "ui_signaux", "kind": "ui_output", "label": "Niveaux Clés & Synthèse", "subtitle": "Affiche niveaux_cles et synthese_eod", "x": 670, "y": 230},
            ],
            "edges": [
                {"id": "e1", "from_node": "ui_ticker", "to_node": "ai_eod", "label": "symbole + horizon"},
                {"id": "e2", "from_node": "ai_eod", "to_node": "ui_cards_eod", "label": "prix_actuel + rsi_14 + tendance_technique"},
                {"id": "e3", "from_node": "ai_eod", "to_node": "ui_signaux", "label": "niveaux_cles + synthese_eod"},
            ],
        }

    if is_bot or not is_quiz:
        app_title = title or ("Le NiaisBot — Révision par dialogue" if "niais" in lower else "Application Bot IA Intégré")
        return {
            "title": app_title,
            "summary": "L'interface utilisateur (sélecteur, champ de tchat, fil de discussion, jauge et score) est directement pilotée par la brique Agent IA interne.",
            "nodes": [
                {
                    "id": "ui_sujet",
                    "kind": "ui_input",
                    "label": "Sélecteur de Sujet",
                    "subtitle": "Choisit le thème actif dans l'app",
                    "x": 40,
                    "y": 60,
                },
                {
                    "id": "ui_chat_input",
                    "kind": "ui_input",
                    "label": "Champ de Tchat de l'App",
                    "subtitle": "Saisie utilisateur + historique multi-tours",
                    "x": 40,
                    "y": 240,
                },
                {
                    "id": "ai_bot_moteur",
                    "kind": "ai_brick",
                    "label": "Moteur IA Conversationnel",
                    "subtitle": "Génère la réplique, la jauge et le score JSON",
                    "x": 350,
                    "y": 140,
                    "brick": {
                        "id": "bot_moteur_app",
                        "name": "Cerveau Bot de l'App",
                        "type": "ai_agent",
                        "description": "Incarne le personnage/assistant de l'application et calcule l'évolution de la jauge.",
                        "model": "auto",
                        "system_prompt": f"Tu es le moteur IA intégré de l'application « {app_title} ». Réponds dans le rôle demandé par le contexte (`{prompt[:280]}`) en tenant compte du sujet choisi et de l'historique de conversation. Évalue la compréhension ou progression de 0 à 100.",
                        "web_search_enabled": False,
                        "show_widget": False,
                        "widget_style": "auto",
                        "welcome_message": "",
                        "inputs": [
                            {"key": "sujet", "label": "Sujet actif", "type": "text", "required": True, "placeholder": "Ex: La Mitose cellulaire", "default_value": "", "options": []},
                            {"key": "message", "label": "Message utilisateur", "type": "textarea", "required": True, "placeholder": "Explication ou question", "default_value": "", "options": []},
                        ],
                        "output_spec": {
                            "format": "json",
                            "description": "Réponse du bot dans l'app + état de la jauge et score",
                            "fields": [
                                {"key": "reponse_bot", "type": "string", "description": "Réplique affichée dans les bulles du bot de l'app"},
                                {"key": "score_progression", "type": "number", "description": "Niveau de progression / compréhension de 0 à 100"},
                                {"key": "statut_jauge", "type": "string", "description": "Libellé court sous la jauge (ex: Commence à comprendre)"},
                            ],
                        },
                    },
                },
                {
                    "id": "ui_bulles",
                    "kind": "ui_output",
                    "label": "Fil de Discussion de l'App",
                    "subtitle": "Affiche reponse_bot dans les bulles intégrées",
                    "x": 670,
                    "y": 40,
                },
                {
                    "id": "ui_jauge",
                    "kind": "ui_output",
                    "label": "Jauge de Progression",
                    "subtitle": "Barre dynamique % + statut_jauge",
                    "x": 670,
                    "y": 195,
                },
                {
                    "id": "ui_score",
                    "kind": "ui_output",
                    "label": "Badge Score /100",
                    "subtitle": "Compteur score_progression",
                    "x": 670,
                    "y": 350,
                },
            ],
            "edges": [
                {"id": "e1", "from_node": "ui_sujet", "to_node": "ai_bot_moteur", "label": "sujet"},
                {"id": "e2", "from_node": "ui_chat_input", "to_node": "ai_bot_moteur", "label": "message + _history"},
                {"id": "e3", "from_node": "ai_bot_moteur", "to_node": "ui_bulles", "label": "reponse_bot"},
                {"id": "e4", "from_node": "ai_bot_moteur", "to_node": "ui_jauge", "label": "score_progression + statut_jauge"},
                {"id": "e5", "from_node": "ai_bot_moteur", "to_node": "ui_score", "label": "score_progression"},
            ],
        }

    app_title = title or "Application Quiz & Coaching IA"
    return {
        "title": app_title,
        "summary": "Génération de QCM interactif et correction personnalisée intégrés directement dans les vues de l'application.",
        "nodes": [
            {"id": "ui_theme", "kind": "ui_input", "label": "Sujet & Difficulté", "subtitle": "Formulaire de démarrage", "x": 40, "y": 120},
            {
                "id": "ai_quiz",
                "kind": "ai_brick",
                "label": "Générateur Quiz IA",
                "subtitle": "Produit les questions QCM JSON",
                "x": 350,
                "y": 120,
                "brick": {
                    "id": "moteur_quiz_app",
                    "name": "Moteur Quiz App",
                    "type": "ai_agent",
                    "description": "Génère les questions du quiz dans l'interface.",
                    "model": "auto",
                    "system_prompt": f"Génère 4 questions QCM pour l'application : {prompt[:260]}",
                    "web_search_enabled": False,
                    "show_widget": False,
                    "widget_style": "auto",
                    "welcome_message": "",
                    "inputs": [
                        {"key": "sujet", "label": "Sujet", "type": "text", "required": True, "placeholder": "", "default_value": "", "options": []},
                    ],
                    "output_spec": {
                        "format": "json",
                        "description": "Liste de questions QCM structurées",
                        "fields": [
                            {"key": "titre_quiz", "type": "string", "description": "Titre du quiz"},
                            {"key": "questions", "type": "string[]", "description": "Questions formatées"},
                        ],
                    },
                },
            },
            {"id": "ui_qcm", "kind": "ui_output", "label": "Grille QCM Interactive", "subtitle": "Affiche questions & score live", "x": 670, "y": 120},
        ],
        "edges": [
            {"id": "e1", "from_node": "ui_theme", "to_node": "ai_quiz", "label": "sujet"},
            {"id": "e2", "from_node": "ai_quiz", "to_node": "ui_qcm", "label": "questions + titre_quiz"},
        ],
    }


def normalize_app_diagram(raw: dict[str, Any] | None, fallback_prompt: str = "", fallback_title: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list) or not raw["nodes"]:
        return _build_fallback_diagram(fallback_prompt, fallback_title)

    nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    for idx, item in enumerate(raw["nodes"][:20]):
        if not isinstance(item, dict):
            continue
        nid = _slug_id(str(item.get("id") or f"node_{idx + 1}"), fallback=f"node_{idx + 1}")
        if nid in seen_node_ids:
            nid = f"{nid}_{idx + 1}"
        seen_node_ids.add(nid)
        kind = str(item.get("kind") or "ui_output").strip().lower()
        if kind not in _VALID_DIAGRAM_KINDS:
            kind = "ui_output"

        node_obj: dict[str, Any] = {
            "id": nid,
            "kind": kind,
            "label": str(item.get("label") or f"Bloc {idx + 1}").strip()[:100],
            "subtitle": str(item.get("subtitle") or "").strip()[:220],
            "x": int(item.get("x") if isinstance(item.get("x"), (int, float)) else (40 + (idx % 3) * 310)),
            "y": int(item.get("y") if isinstance(item.get("y"), (int, float)) else (50 + (idx // 3) * 155)),
        }
        if kind == "ai_brick":
            raw_brick = item.get("brick") if isinstance(item.get("brick"), dict) else {}
            brick_seed = {
                **raw_brick,
                "id": raw_brick.get("id") or nid,
                "name": raw_brick.get("name") or node_obj["label"],
                "show_widget": bool(raw_brick.get("show_widget", False)),
            }
            norm_bricks = normalize_bricks([brick_seed])
            if norm_bricks:
                node_obj["brick"] = norm_bricks[0]
        nodes.append(node_obj)

    if not nodes:
        return _build_fallback_diagram(fallback_prompt, fallback_title)

    edges: list[dict[str, str]] = []
    for e_idx, edge in enumerate((raw.get("edges") or [])[:40]):
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("from_node") or "").strip()
        dst = str(edge.get("to_node") or "").strip()
        if src in seen_node_ids and dst in seen_node_ids and src != dst:
            edges.append({
                "id": str(edge.get("id") or f"e{e_idx + 1}"),
                "from_node": src,
                "to_node": dst,
                "label": str(edge.get("label") or "données").strip()[:80],
            })

    return {
        "title": str(raw.get("title") or fallback_title or "Application IA").strip()[:160],
        "summary": str(raw.get("summary") or "").strip()[:500],
        "nodes": nodes,
        "edges": edges,
    }


async def propose_app_diagram(
    *,
    settings: Settings,
    prompt: str,
    title: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Génère un diagramme d'architecture d'application (UI + Briques IA internes + flux) via LLM ou fallback."""
    clean_prompt = (prompt or "").strip()
    target_model = model or getattr(settings, "page_model", None) or getattr(settings, "default_model", None) or "openai/gpt-4o-mini"

    if getattr(settings, "demo_mode", False) or not has_llm_access(settings, target_model) or not clean_prompt:
        return _build_fallback_diagram(clean_prompt, title)


_DIAGRAM_INTERVIEW_PROMPT = """Tu es l'Agent Architecte cLAIr : tu aides l'utilisateur à concevoir son application web AVANT la génération du code.
Tu disposes d'un catalogue de briques préfaites prêtes à l'emploi (ex. `bot_ia_chat`, `simulateur_roleplay`, `web_research_agent`, `studio_reecriture`, `traducteur_ia`, `extracteur_json`, `synthese_reunion`, `brainstorm_idees`, `generateur_quiz`, `coach_evaluateur`, `expliqueur_feynman`, `auditeur_code`, `finance_eod_indicateurs`, `finance_fondamentaux`, `finance_moat_ia`, `finance_actualites_ia`).

Ta mission en 2 phases :
1. **Phase Questions (`status: "questions"`)** : Lors du 1er message de l'utilisateur (sauf s'il a déjà tout précisé ou si `force_finalize` est demandé), identifie les briques les plus adaptées (`selected_brick_ids`) et pose **2 à 3 questions courtes et ciblées** pour clarifier :
   - le comportement/persona du bot ou moteur IA,
   - les éléments visuels souhaités dans l'app (jauges, score, onglets, quiz, tableau…),
   - les données échangées (entrées/sorties).
   Pour chaque question, propose 3 à 4 options cliquables concrètes.
2. **Phase Diagramme Prêt (`status: "ready"`)** : Dès que l'utilisateur a répondu aux questions (ou si `force_finalize` est vrai), sélectionne les briques finales (`selected_brick_ids`) et génère le **`diagram`** complet (nœuds `ui_input`, nœuds `ai_brick` avec `show_widget: false`, nœuds `ui_output` et `edges` reliés par les noms exacts de variables).

Réponds UNIQUEMENT avec un objet JSON valide :
{
  "status": "questions" | "ready",
  "assistant_message": "Message clair en français expliquant les briques choisies et les questions ou le diagramme prêt",
  "selected_brick_ids": ["id_template_1", "..."],
  "questions": [
    {
      "id": "q1",
      "question": "Question courte ?",
      "options": ["Option 1", "Option 2", "Option 3"]
    }
  ],
  "diagram": null ou { "title": "...", "summary": "...", "nodes": [...], "edges": [...] }
}"""


def _infer_brick_ids_from_text(text: str) -> list[str]:
    lower = text.lower()
    picked: list[str] = []
    if any(k in lower for k in ("bourse", "finance", "action", "eod", "ticker", "rsi", "macd", "moat", "trading", "portefeuille", "indicateur")):
        picked.extend(["finance_eod_indicateurs", "finance_fondamentaux"])
        if any(k in lower for k in ("moat", "concurrent", "long terme", "buffett")):
            picked.append("finance_moat_ia")
        if any(k in lower for k in ("actu", "news", "veille", "sentiment")):
            picked.append("finance_actualites_ia")
    if any(k in lower for k in ("bot", "chat", "discuter", "dialogue", "niais", "tuteur", "assistant")):
        picked.append("bot_ia_chat")
    if any(k in lower for k in ("jeu de rôle", "roleplay", "entretien", "simulation", "pitch", "client")):
        picked.append("simulateur_roleplay")
    if any(k in lower for k in ("quiz", "qcm", "question", "révis", "examen", "test")):
        picked.append("generateur_quiz")
    if any(k in lower for k in ("note", "évalu", "corrig", "coach", "score")):
        picked.append("coach_evaluateur")
    if any(k in lower for k in ("feynman", "expliqu", "vulgaris", "comprendre")):
        picked.append("expliqueur_feynman")
    if any(k in lower for k in ("réécri", "reformul", "orthographe", "style")):
        picked.append("studio_reecriture")
    if any(k in lower for k in ("tradui", "langue", "anglais", "espagnol")):
        picked.append("traducteur_ia")
    if any(k in lower for k in ("web", "actualit", "recherche", "fact")):
        picked.append("web_research_agent")
    if any(k in lower for k in ("code", "sécurit", "audit", "bug")):
        picked.append("auditeur_code")
    if any(k in lower for k in ("réunion", "compte-rendu", "notes")):
        picked.append("synthese_reunion")
    if any(k in lower for k in ("kpi", "dashboard", "extrait", "analyse")):
        picked.append("extracteur_json")
    if not picked:
        picked.append("bot_ia_chat")
    return picked[:4]


def _build_fallback_interview(
    messages: list[dict[str, str]],
    force_finalize: bool = False,
) -> dict[str, Any]:
    user_texts = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
    combined = "\n".join(user_texts)
    selected_ids = _infer_brick_ids_from_text(combined)

    if not force_finalize and len(user_texts) <= 1:
        return {
            "status": "questions",
            "assistant_message": (
                "J'ai analysé votre idée et pré-sélectionné des briques adaptées. "
                "Précisez ces quelques points pour que je construise le diagramme exact de votre application :"
            ),
            "selected_brick_ids": selected_ids,
            "questions": [
                {
                    "id": "q_role",
                    "question": "Quel rôle principal doit jouer l'IA au cœur de votre application ?",
                    "options": [
                        "Bot conversationnel intégré (avec historique)",
                        "Évaluateur / Coach qui attribue un score",
                        "Générateur de Quiz QCM interactif",
                        "Analyseur qui remplit des cartes KPI",
                    ],
                },
                {
                    "id": "q_ui",
                    "question": "Quels éléments visuels souhaitez-vous mettre à jour en direct dans l'app ?",
                    "options": [
                        "Bulles de discussion + Jauge de progression + Score /100",
                        "Cartes de résultats structurées + Liste d'actions",
                        "Grille QCM cliquable + Bilan final",
                    ],
                },
                {
                    "id": "q_ton",
                    "question": "Quel ton ou personnalité doit adopter le moteur IA ?",
                    "options": [
                        "Pédagogue clair et bienveillant",
                        "Personnage naïf / ludique (façon Feynman)",
                        "Expert rigoureux et synthétique",
                    ],
                },
            ],
            "diagram": None,
        }

    diagram = _build_fallback_diagram(combined)
    return {
        "status": "ready",
        "assistant_message": "Parfait ! Voici le diagramme d'architecture complet avec les briques IA câblées à l'intérieur de votre application. Vous pouvez l'ajuster ou lancer directement la génération du code.",
        "selected_brick_ids": selected_ids,
        "questions": [],
        "diagram": diagram,
    }


async def interview_app_diagram(
    *,
    settings: Settings,
    messages: list[dict[str, str]],
    available_templates: list[dict[str, Any]] | None = None,
    model: str | None = None,
    force_finalize: bool = False,
) -> dict[str, Any]:
    """Mène un court entretien interactif pour choisir les briques et construire le diagramme d'app."""
    clean_msgs = [
        {"role": m["role"], "content": m["content"].strip()}
        for m in messages
        if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str) and m["content"].strip()
    ]
    if not clean_msgs:
        raise HTTPException(422, "Décrivez d'abord l'application souhaitée.")

    user_turns = sum(1 for m in clean_msgs if m["role"] == "user")
    target_model = model or getattr(settings, "page_model", None) or getattr(settings, "default_model", None) or "openai/gpt-4o-mini"

    if getattr(settings, "demo_mode", False) or not has_llm_access(settings, target_model):
        return _build_fallback_interview(clean_msgs, force_finalize=force_finalize)

    catalog_summary = ""
    if available_templates:
        catalog_lines = [
            f"- `{t.get('templateId')}` ({t.get('name')}) : {t.get('tagline')}"
            for t in available_templates[:20]
            if isinstance(t, dict)
        ]
        catalog_summary = "\n\nCATALOGUE EXACT DES BRIQUES DISPONIBLES :\n" + "\n".join(catalog_lines)

    phase_hint = (
        "\n\nCONTRAINTE DE PHASE : L'utilisateur a demandé de finaliser maintenant (ou a déjà répondu). "
        "Tu DOIS répondre avec `\"status\": \"ready\"`, `\"questions\": []` et un `\"diagram\"` complet."
        if (force_finalize or user_turns >= 2)
        else "\n\nCONTRAINTE DE PHASE : C'est le premier message. Pose 2 à 3 questions ciblées (`\"status\": \"questions\"`) avec des options cliquables ET pré-sélectionne les briques pertinentes dans `selected_brick_ids`."
    )

    llm_messages = [
        {"role": "system", "content": _DIAGRAM_INTERVIEW_PROMPT + catalog_summary + phase_hint},
        *clean_msgs[-8:],
    ]

    request_payload: dict[str, Any] = {
        "model": target_model,
        "messages": llm_messages,
        "stream": False,
        "temperature": 0.35,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await post_chat_completion(settings, request_payload, client=client)
            if response.status_code in (400, 422):
                retry = {k: v for k, v in request_payload.items() if k != "response_format"}
                response = await post_chat_completion(settings, retry, client=client)
            _check_response(response, "Fournisseur IA")
            payload = _json(response, "Fournisseur IA")
            raw_text = str(payload["choices"][0]["message"]["content"] or "").strip()
            parsed = _extract_json_payload(raw_text)
            if isinstance(parsed, dict):
                status_val = "ready" if (force_finalize or parsed.get("status") == "ready") else "questions"
                selected_ids = [
                    str(bid).strip()
                    for bid in (parsed.get("selected_brick_ids") or [])
                    if str(bid).strip()
                ][:6]
                questions_out: list[dict[str, Any]] = []
                if status_val == "questions":
                    for q_idx, q in enumerate((parsed.get("questions") or [])[:4]):
                        if not isinstance(q, dict) or not str(q.get("question") or "").strip():
                            continue
                        questions_out.append({
                            "id": str(q.get("id") or f"q{q_idx + 1}"),
                            "question": str(q["question"]).strip()[:240],
                            "options": [
                                str(opt).strip()[:120]
                                for opt in (q.get("options") or [])
                                if str(opt).strip()
                            ][:5],
                        })
                    if not questions_out:
                        status_val = "ready"

                diagram_out = None
                if status_val == "ready" or isinstance(parsed.get("diagram"), dict):
                    combined_user = "\n".join(m["content"] for m in clean_msgs if m["role"] == "user")
                    diagram_out = normalize_app_diagram(
                        parsed.get("diagram") if isinstance(parsed.get("diagram"), dict) else None,
                        fallback_prompt=combined_user,
                    )

                return {
                    "status": status_val,
                    "assistant_message": str(parsed.get("assistant_message") or "").strip()[:800],
                    "selected_brick_ids": selected_ids or _infer_brick_ids_from_text(clean_msgs[0]["content"]),
                    "questions": questions_out,
                    "diagram": diagram_out,
                }
    except Exception as exc:
        _logger.warning("Erreur interview diagramme IA (fallback utilisé): %s", exc)

    return _build_fallback_interview(clean_msgs, force_finalize=force_finalize)

    user_content = f"Idée d'application à architecturer :\n{clean_prompt}"
    if title:
        user_content += f"\n\nTitre souhaité : {title}"

    request_payload: dict[str, Any] = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": _DIAGRAM_PROPOSAL_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "temperature": 0.35,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await post_chat_completion(settings, request_payload, client=client)
            if response.status_code in (400, 422):
                retry = {k: v for k, v in request_payload.items() if k != "response_format"}
                response = await post_chat_completion(settings, retry, client=client)
            _check_response(response, "Fournisseur IA")
            payload = _json(response, "Fournisseur IA")
            raw_text = str(payload["choices"][0]["message"]["content"] or "").strip()
            parsed = _extract_json_payload(raw_text)
            if isinstance(parsed, dict):
                return normalize_app_diagram(parsed, fallback_prompt=clean_prompt, fallback_title=title)
    except Exception as exc:
        _logger.warning("Erreur génération diagramme app IA (fallback utilisé): %s", exc)

    return _build_fallback_diagram(clean_prompt, title)


_DIAGRAM_INTERVIEW_PROMPT = """Tu es l'Agent Architecte cLAIr : tu aides l'utilisateur à concevoir son application web AVANT la génération du code.
Tu disposes d'un catalogue de briques préfaites prêtes à l'emploi (ex. `bot_ia_chat`, `simulateur_roleplay`, `web_research_agent`, `studio_reecriture`, `traducteur_ia`, `extracteur_json`, `synthese_reunion`, `brainstorm_idees`, `generateur_quiz`, `coach_evaluateur`, `expliqueur_feynman`, `auditeur_code`, `finance_eod_indicateurs`, `finance_fondamentaux`, `finance_moat_ia`, `finance_actualites_ia`).

Ta mission en 2 phases :
1. **Phase Questions (`status: "questions"`)** : Lors du 1er message de l'utilisateur (sauf s'il a déjà tout précisé ou si `force_finalize` est demandé), identifie les briques les plus adaptées (`selected_brick_ids`) et pose **2 à 3 questions courtes et ciblées** pour clarifier :
   - le comportement/persona du bot ou moteur IA,
   - les éléments visuels souhaités dans l'app (jauges, score, onglets, quiz, tableau…),
   - les données échangées (entrées/sorties).
   Pour chaque question, propose 3 à 4 options cliquables concrètes.
2. **Phase Diagramme Prêt (`status: "ready"`)** : Dès que l'utilisateur a répondu aux questions (ou si `force_finalize` est vrai), sélectionne les briques finales (`selected_brick_ids`) et génère le **`diagram`** complet (nœuds `ui_input`, nœuds `ai_brick` avec `show_widget: false`, nœuds `ui_output` et `edges` reliés par les noms exacts de variables).

Réponds UNIQUEMENT avec un objet JSON valide :
{
  "status": "questions" | "ready",
  "assistant_message": "Message clair en français expliquant les briques choisies et les questions ou le diagramme prêt",
  "selected_brick_ids": ["id_template_1", "..."],
  "questions": [
    {
      "id": "q1",
      "question": "Question courte ?",
      "options": ["Option 1", "Option 2", "Option 3"]
    }
  ],
  "diagram": null ou { "title": "...", "summary": "...", "nodes": [...], "edges": [...] }
}"""


def _infer_brick_ids_from_text(text: str) -> list[str]:
    lower = text.lower()
    picked: list[str] = []
    if any(k in lower for k in ("bourse", "finance", "action", "eod", "ticker", "rsi", "macd", "moat", "trading", "portefeuille", "indicateur")):
        picked.extend(["finance_eod_indicateurs", "finance_fondamentaux"])
        if any(k in lower for k in ("moat", "concurrent", "long terme", "buffett")):
            picked.append("finance_moat_ia")
        if any(k in lower for k in ("actu", "news", "veille", "sentiment")):
            picked.append("finance_actualites_ia")
    if any(k in lower for k in ("bot", "chat", "discuter", "dialogue", "niais", "tuteur", "assistant")):
        picked.append("bot_ia_chat")
    if any(k in lower for k in ("jeu de rôle", "roleplay", "entretien", "simulation", "pitch", "client")):
        picked.append("simulateur_roleplay")
    if any(k in lower for k in ("quiz", "qcm", "question", "révis", "examen", "test")):
        picked.append("generateur_quiz")
    if any(k in lower for k in ("note", "évalu", "corrig", "coach", "score")):
        picked.append("coach_evaluateur")
    if any(k in lower for k in ("feynman", "expliqu", "vulgaris", "comprendre")):
        picked.append("expliqueur_feynman")
    if any(k in lower for k in ("réécri", "reformul", "orthographe", "style")):
        picked.append("studio_reecriture")
    if any(k in lower for k in ("tradui", "langue", "anglais", "espagnol")):
        picked.append("traducteur_ia")
    if any(k in lower for k in ("web", "actualit", "recherche", "fact")):
        picked.append("web_research_agent")
    if any(k in lower for k in ("code", "sécurit", "audit", "bug")):
        picked.append("auditeur_code")
    if any(k in lower for k in ("réunion", "compte-rendu", "notes")):
        picked.append("synthese_reunion")
    if any(k in lower for k in ("kpi", "dashboard", "extrait", "analyse")):
        picked.append("extracteur_json")
    if not picked:
        picked.append("bot_ia_chat")
    return picked[:4]


def _build_fallback_interview(
    messages: list[dict[str, str]],
    force_finalize: bool = False,
) -> dict[str, Any]:
    user_texts = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
    combined = "\n".join(user_texts)
    selected_ids = _infer_brick_ids_from_text(combined)

    if not force_finalize and len(user_texts) <= 1:
        return {
            "status": "questions",
            "assistant_message": (
                "J'ai analysé votre idée et pré-sélectionné des briques adaptées. "
                "Précisez ces quelques points pour que je construise le diagramme exact de votre application :"
            ),
            "selected_brick_ids": selected_ids,
            "questions": [
                {
                    "id": "q_role",
                    "question": "Quel rôle principal doit jouer l'IA au cœur de votre application ?",
                    "options": [
                        "Bot conversationnel intégré (avec historique)",
                        "Évaluateur / Coach qui attribue un score",
                        "Générateur de Quiz QCM interactif",
                        "Analyseur qui remplit des cartes KPI",
                    ],
                },
                {
                    "id": "q_ui",
                    "question": "Quels éléments visuels souhaitez-vous mettre à jour en direct dans l'app ?",
                    "options": [
                        "Bulles de discussion + Jauge de progression + Score /100",
                        "Cartes de résultats structurées + Liste d'actions",
                        "Grille QCM cliquable + Bilan final",
                    ],
                },
                {
                    "id": "q_ton",
                    "question": "Quel ton ou personnalité doit adopter le moteur IA ?",
                    "options": [
                        "Pédagogue clair et bienveillant",
                        "Personnage naïf / ludique (façon Feynman)",
                        "Expert rigoureux et synthétique",
                    ],
                },
            ],
            "diagram": None,
        }

    diagram = _build_fallback_diagram(combined)
    return {
        "status": "ready",
        "assistant_message": "Parfait ! Voici le diagramme d'architecture complet avec les briques IA câblées à l'intérieur de votre application. Vous pouvez l'ajuster ou lancer directement la génération du code.",
        "selected_brick_ids": selected_ids,
        "questions": [],
        "diagram": diagram,
    }


async def interview_app_diagram(
    *,
    settings: Settings,
    messages: list[dict[str, str]],
    available_templates: list[dict[str, Any]] | None = None,
    model: str | None = None,
    force_finalize: bool = False,
) -> dict[str, Any]:
    """Mène un court entretien interactif pour choisir les briques et construire le diagramme d'app."""
    clean_msgs = [
        {"role": m["role"], "content": m["content"].strip()}
        for m in messages
        if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str) and m["content"].strip()
    ]
    if not clean_msgs:
        raise HTTPException(422, "Décrivez d'abord l'application souhaitée.")

    user_turns = sum(1 for m in clean_msgs if m["role"] == "user")
    target_model = model or getattr(settings, "page_model", None) or getattr(settings, "default_model", None) or "openai/gpt-4o-mini"

    if getattr(settings, "demo_mode", False) or not has_llm_access(settings, target_model):
        return _build_fallback_interview(clean_msgs, force_finalize=force_finalize)

    catalog_summary = ""
    if available_templates:
        catalog_lines = [
            f"- `{t.get('templateId')}` ({t.get('name')}) : {t.get('tagline')}"
            for t in available_templates[:20]
            if isinstance(t, dict)
        ]
        catalog_summary = "\n\nCATALOGUE EXACT DES BRIQUES DISPONIBLES :\n" + "\n".join(catalog_lines)

    phase_hint = (
        "\n\nCONTRAINTE DE PHASE : L'utilisateur a demandé de finaliser maintenant (ou a déjà répondu). "
        "Tu DOIS répondre avec `\"status\": \"ready\"`, `\"questions\": []` et un `\"diagram\"` complet."
        if (force_finalize or user_turns >= 2)
        else "\n\nCONTRAINTE DE PHASE : C'est le premier message. Pose 2 à 3 questions ciblées (`\"status\": \"questions\"`) avec des options cliquables ET pré-sélectionne les briques pertinentes dans `selected_brick_ids`."
    )

    llm_messages = [
        {"role": "system", "content": _DIAGRAM_INTERVIEW_PROMPT + catalog_summary + phase_hint},
        *clean_msgs[-8:],
    ]

    request_payload: dict[str, Any] = {
        "model": target_model,
        "messages": llm_messages,
        "stream": False,
        "temperature": 0.35,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await post_chat_completion(settings, request_payload, client=client)
            if response.status_code in (400, 422):
                retry = {k: v for k, v in request_payload.items() if k != "response_format"}
                response = await post_chat_completion(settings, retry, client=client)
            _check_response(response, "Fournisseur IA")
            payload = _json(response, "Fournisseur IA")
            raw_text = str(payload["choices"][0]["message"]["content"] or "").strip()
            parsed = _extract_json_payload(raw_text)
            if isinstance(parsed, dict):
                status_val = "ready" if (force_finalize or parsed.get("status") == "ready") else "questions"
                selected_ids = [
                    str(bid).strip()
                    for bid in (parsed.get("selected_brick_ids") or [])
                    if str(bid).strip()
                ][:6]
                questions_out: list[dict[str, Any]] = []
                if status_val == "questions":
                    for q_idx, q in enumerate((parsed.get("questions") or [])[:4]):
                        if not isinstance(q, dict) or not str(q.get("question") or "").strip():
                            continue
                        questions_out.append({
                            "id": str(q.get("id") or f"q{q_idx + 1}"),
                            "question": str(q["question"]).strip()[:240],
                            "options": [
                                str(opt).strip()[:120]
                                for opt in (q.get("options") or [])
                                if str(opt).strip()
                            ][:5],
                        })
                    if not questions_out:
                        status_val = "ready"

                diagram_out = None
                if status_val == "ready" or isinstance(parsed.get("diagram"), dict):
                    combined_user = "\n".join(m["content"] for m in clean_msgs if m["role"] == "user")
                    diagram_out = normalize_app_diagram(
                        parsed.get("diagram") if isinstance(parsed.get("diagram"), dict) else None,
                        fallback_prompt=combined_user,
                    )

                return {
                    "status": status_val,
                    "assistant_message": str(parsed.get("assistant_message") or "").strip()[:800],
                    "selected_brick_ids": selected_ids or _infer_brick_ids_from_text(clean_msgs[0]["content"]),
                    "questions": questions_out,
                    "diagram": diagram_out,
                }
    except Exception as exc:
        _logger.warning("Erreur interview diagramme IA (fallback utilisé): %s", exc)

    return _build_fallback_interview(clean_msgs, force_finalize=force_finalize)
