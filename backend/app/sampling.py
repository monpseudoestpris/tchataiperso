"""Sampling parameter definitions, hybrid creativity system (parameters + adaptive instructions), and model capability filtering."""

from __future__ import annotations

import json
from typing import Any

CREATIVITY_PARAMETERS: tuple[str, ...] = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "top_a",
    "presence_penalty",
    "frequency_penalty",
    "repetition_penalty",
    "logit_bias",
    "seed",
    "reasoning",
    "reasoning_effort",
    "verbosity",
)

DIRECT_RANDOMNESS_PARAMETERS: tuple[str, ...] = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "top_a",
)

DEFAULT_SUPPORTED_PARAMETERS: list[str] = [
    "temperature",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "seed",
]

REASONING_EFFORT_VALUES: set[str] = {"none", "minimal", "low", "medium", "high"}
VERBOSITY_VALUES: set[str] = {"low", "medium", "high"}

PARAMETER_CATALOG: list[dict[str, Any]] = [
    {
        "name": "temperature",
        "label": "temperature",
        "role": "Aléatoire et originalité",
        "description": "Contrôle l'audace du modèle. Plus elle monte, plus il ose choisir des mots improbables.",
        "hint": "Basse : réponses classiques. Haute : réponses originales, parfois absurdes.",
        "unavailable_label": "Pas de contrôle direct de l'aléatoire",
        "min": 0.0,
        "max": 2.0,
        "step": 0.05,
        "default": 0.2,
        "type": "float",
    },
    {
        "name": "top_p",
        "label": "top_p",
        "role": "Diversité des tokens possibles",
        "description": "Élimine les mots les moins probables.",
        "hint": "À 0.9, le modèle ne choisit que parmi les mots représentant ensemble 90 % de la probabilité.",
        "unavailable_label": "Pas de réglage",
        "min": 0.01,
        "max": 1.0,
        "step": 0.05,
        "default": 1.0,
        "type": "float",
    },
    {
        "name": "top_k",
        "label": "top_k",
        "role": "Nombre de tokens candidats",
        "description": "Limite le nombre de mots possibles à chaque étape.",
        "hint": "À 20, le modèle choisit parmi les 20 mots les plus probables.",
        "unavailable_label": "Pas de réglage",
        "min": 1,
        "max": 500,
        "step": 1,
        "default": 40,
        "type": "int",
    },
    {
        "name": "min_p",
        "label": "min_p",
        "role": "Élimination des tokens trop improbables",
        "description": "Élimine les tokens dont la probabilité est trop faible par rapport au token le plus probable.",
        "hint": "À 0.05, tout token ayant moins de 5 % de la probabilité du meilleur choix est écarté.",
        "unavailable_label": "Pas de réglage",
        "min": 0.0,
        "max": 1.0,
        "step": 0.01,
        "default": 0.0,
        "type": "float",
    },
    {
        "name": "top_a",
        "label": "top_a",
        "role": "Filtrage dynamique des tokens",
        "description": "Ajuste dynamiquement le seuil de filtrage selon la confiance du modèle dans son premier choix.",
        "hint": "Quand le modèle est très sûr de lui, la sélection se resserre automatiquement.",
        "unavailable_label": "Pas de réglage",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "default": 0.0,
        "type": "float",
    },
    {
        "name": "presence_penalty",
        "label": "presence_penalty",
        "role": "Introduction de nouvelles idées",
        "description": "Encourage le modèle à introduire de nouvelles idées plutôt qu'à revenir sur les mêmes.",
        "hint": "Utile pour un brainstorming qui tourne en rond.",
        "unavailable_label": "Pas de réglage",
        "min": -2.0,
        "max": 2.0,
        "step": 0.1,
        "default": 0.0,
        "type": "float",
    },
    {
        "name": "frequency_penalty",
        "label": "frequency_penalty",
        "role": "Réduction des répétitions",
        "description": "Décourage les mots utilisés trop souvent dans la réponse.",
        "hint": "Évite de répéter constamment les mêmes expressions.",
        "unavailable_label": "Pas de réglage",
        "min": -2.0,
        "max": 2.0,
        "step": 0.1,
        "default": 0.0,
        "type": "float",
    },
    {
        "name": "repetition_penalty",
        "label": "repetition_penalty",
        "role": "Pénalisation des tokens déjà utilisés",
        "description": "Pénalise les répétitions, avec un mécanisme différent de frequency_penalty.",
        "hint": "Limite les phrases et formulations répétitives.",
        "unavailable_label": "Pas de réglage",
        "min": 0.1,
        "max": 2.0,
        "step": 0.05,
        "default": 1.0,
        "type": "float",
    },
    {
        "name": "logit_bias",
        "label": "logit_bias",
        "role": "Favoriser ou défavoriser certains tokens",
        "description": "Modifie manuellement la probabilité d'apparition de certains tokens (identifiants numériques).",
        "hint": 'Objet JSON {"token_id": bias} avec un biais entre -100 (interdit) et +100 (forcé).',
        "unavailable_label": "Pas de réglage",
        "default": None,
        "type": "json",
    },
    {
        "name": "seed",
        "label": "seed",
        "role": "Variation ou reproductibilité entre générations",
        "description": "Permet de tenter de reproduire les mêmes choix aléatoires.",
        "hint": "Même question + même seed = résultats potentiellement similaires, sans garantie absolue.",
        "unavailable_label": "Pas de réglage",
        "min": 0,
        "max": 2147483647,
        "step": 1,
        "default": None,
        "type": "int",
    },
    {
        "name": "reasoning",
        "label": "reasoning",
        "role": "Influence indirecte par la profondeur de réflexion",
        "description": "Contrôle le niveau de réflexion interne du modèle avant de formuler sa réponse.",
        "hint": "Utile sur les modèles sans température (ex. Sonnet 5.5) pour approfondir l'exploration conceptuelle.",
        "unavailable_label": "Pas de réglage",
        "default": None,
        "type": "select",
        "options": [
            {"value": "none", "label": "Désactivé (none)"},
            {"value": "low", "label": "Faible (low)"},
            {"value": "medium", "label": "Moyen (medium)"},
            {"value": "high", "label": "Élevé (high)"},
        ],
    },
    {
        "name": "reasoning_effort",
        "label": "reasoning_effort",
        "role": "Variante de configuration de l'effort de réflexion",
        "description": "Ajuste l'effort de raisonnement alloué aux modèles compatibles OpenAI / OpenRouter.",
        "hint": "Permet de choisir entre rapidité (low) et réflexion approfondie (high).",
        "unavailable_label": "Pas de réglage",
        "default": None,
        "type": "select",
        "options": [
            {"value": "minimal", "label": "Minimal (minimal)"},
            {"value": "low", "label": "Faible (low)"},
            {"value": "medium", "label": "Moyen (medium)"},
            {"value": "high", "label": "Élevé (high)"},
        ],
    },
    {
        "name": "verbosity",
        "label": "verbosity",
        "role": "Influence indirecte par le niveau de développement",
        "description": "Contrôle la longueur et le degré de développement des réponses.",
        "hint": "Permet d'obtenir des réponses très synthétiques (low) ou richement développées (high).",
        "unavailable_label": "Pas de réglage",
        "default": None,
        "type": "select",
        "options": [
            {"value": "low", "label": "Concis (low)"},
            {"value": "medium", "label": "Équilibré (medium)"},
            {"value": "high", "label": "Développé (high)"},
        ],
    },
]


def extract_supported_creativity_parameters(raw_supported: Any) -> list[str]:
    """Filter OpenRouter's supported_parameters into our canonical list of 13 parameters."""
    if isinstance(raw_supported, dict) and "supported_parameters" in raw_supported:
        raw_supported = raw_supported["supported_parameters"]
    if isinstance(raw_supported, list):
        lower_set = {str(item).strip().lower() for item in raw_supported if item is not None}
        if "include_reasoning" in lower_set:
            lower_set.add("reasoning")
        return [param for param in CREATIVITY_PARAMETERS if param in lower_set]
    if isinstance(raw_supported, dict):
        lower_set = {str(k).strip().lower() for k in raw_supported.keys()}
        if "include_reasoning" in lower_set:
            lower_set.add("reasoning")
        return [param for param in CREATIVITY_PARAMETERS if param in lower_set]
    return list(DEFAULT_SUPPORTED_PARAMETERS)


def model_supports_direct_temperature(supported_parameters: list[str] | set[str] | None) -> bool:
    """Return True if the model supports `temperature` directly."""
    if supported_parameters is None:
        return True
    return "temperature" in set(supported_parameters)


def sanitize_logit_bias(raw_bias: Any) -> dict[str, float] | None:
    """Validate and normalize a logit_bias mapping of token IDs to bias [-100, 100]."""
    if raw_bias is None:
        return None
    parsed = raw_bias
    if isinstance(raw_bias, str):
        text = raw_bias.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    cleaned: dict[str, float] = {}
    for k, v in list(parsed.items())[:200]:
        key_str = str(k).strip()
        if not key_str:
            continue
        try:
            bias_val = float(v)
        except (ValueError, TypeError):
            continue
        cleaned[key_str] = round(max(-100.0, min(100.0, bias_val)), 2)
    return cleaned if cleaned else None


def sanitize_sampling_dict(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate and normalize an explicit dictionary of sampling/model parameter overrides."""
    if not raw or not isinstance(raw, dict):
        return None
    cleaned: dict[str, Any] = {}
    if raw.get("temperature") is not None:
        val = float(raw["temperature"])
        cleaned["temperature"] = round(max(0.0, min(2.0, val)), 3)
    if raw.get("top_p") is not None:
        val = float(raw["top_p"])
        cleaned["top_p"] = round(max(0.01, min(1.0, val)), 3)
    if raw.get("top_k") is not None:
        val = int(raw["top_k"])
        cleaned["top_k"] = max(1, min(1000, val))
    if raw.get("min_p") is not None:
        val = float(raw["min_p"])
        cleaned["min_p"] = round(max(0.0, min(1.0, val)), 3)
    if raw.get("top_a") is not None:
        val = float(raw["top_a"])
        cleaned["top_a"] = round(max(0.0, min(1.0, val)), 3)
    if raw.get("presence_penalty") is not None:
        val = float(raw["presence_penalty"])
        cleaned["presence_penalty"] = round(max(-2.0, min(2.0, val)), 3)
    if raw.get("frequency_penalty") is not None:
        val = float(raw["frequency_penalty"])
        cleaned["frequency_penalty"] = round(max(-2.0, min(2.0, val)), 3)
    if raw.get("repetition_penalty") is not None:
        val = float(raw["repetition_penalty"])
        cleaned["repetition_penalty"] = round(max(0.1, min(2.0, val)), 3)
    if raw.get("logit_bias") is not None:
        lb = sanitize_logit_bias(raw.get("logit_bias"))
        if lb:
            cleaned["logit_bias"] = lb
    if raw.get("seed") is not None and str(raw.get("seed")).strip() != "":
        val = int(raw["seed"])
        cleaned["seed"] = max(0, min(2147483647, val))
    if raw.get("reasoning") is not None:
        r_val = raw["reasoning"]
        if isinstance(r_val, dict):
            eff = str(r_val.get("effort") or "").strip().lower()
            if eff in REASONING_EFFORT_VALUES:
                cleaned["reasoning"] = eff
            elif r_val.get("enabled") is False:
                cleaned["reasoning"] = "none"
        elif isinstance(r_val, str):
            eff = r_val.strip().lower()
            if eff in REASONING_EFFORT_VALUES:
                cleaned["reasoning"] = eff
    if raw.get("reasoning_effort") is not None:
        re_val = str(raw["reasoning_effort"]).strip().lower()
        if re_val in REASONING_EFFORT_VALUES:
            cleaned["reasoning_effort"] = re_val
    if raw.get("verbosity") is not None:
        v_val = str(raw["verbosity"]).strip().lower()
        if v_val in VERBOSITY_VALUES:
            cleaned["verbosity"] = v_val
    return cleaned if cleaned else None


def compute_parameters_from_creativity(
    creativity: float,
    supported_parameters: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """
    Translate a normalized creativity score (0.0 to 1.0) into concrete LLM sampling parameters,
    taking into account which parameters are supported by the model.
    For models without temperature/top_p/top_k (like Claude Sonnet 5.5), returns empty numeric
    sampling parameters (or subtle indirect defaults if appropriate) while the hybrid instruction
    generator steers creativity via system instructions.
    """
    c = max(0.0, min(1.0, float(creativity)))
    supported = (
        set(supported_parameters)
        if supported_parameters is not None
        else set(DEFAULT_SUPPORTED_PARAMETERS)
    )
    computed: dict[str, Any] = {}

    if "temperature" in supported:
        # 0.0 -> 0.0, 0.2 -> 0.3, 0.5 -> 0.75, 0.8 -> 1.2, 1.0 -> 1.5
        computed["temperature"] = round(c * 1.5, 2)

    if "top_p" in supported:
        # Low creativity narrows nucleus sampling; >= 0.7 opens to 0.95-1.0
        if c <= 0.7:
            top_p = 0.3 + (c / 0.7) * 0.65
        else:
            top_p = 0.95 + ((c - 0.7) / 0.3) * 0.05
        computed["top_p"] = round(max(0.1, min(1.0, top_p)), 2)

    if "top_k" in supported:
        # 0.0 -> 10 tokens, 0.5 -> 55 tokens, 1.0 -> 100 tokens
        computed["top_k"] = max(1, int(round(10 + c * 90)))

    if "min_p" in supported and "top_p" not in supported:
        # Higher min_p at low creativity filters unlikely tokens; lower min_p at high creativity opens choices
        computed["min_p"] = round(max(0.01, 0.15 - c * 0.13), 2)

    if "presence_penalty" in supported:
        # Encourage new ideas when creativity > 0.4
        if c > 0.4:
            computed["presence_penalty"] = round(((c - 0.4) / 0.6) * 0.6, 2)
        else:
            computed["presence_penalty"] = 0.0

    if "frequency_penalty" in supported:
        # Discourage word repetition when creativity > 0.3
        if c > 0.3:
            computed["frequency_penalty"] = round(((c - 0.3) / 0.7) * 0.5, 2)
        else:
            computed["frequency_penalty"] = 0.0

    if "repetition_penalty" in supported and "frequency_penalty" not in supported:
        # Fallback repetition control for models that only support repetition_penalty
        if c > 0.3:
            computed["repetition_penalty"] = round(1.0 + ((c - 0.3) / 0.7) * 0.15, 2)
        else:
            computed["repetition_penalty"] = 1.0

    return computed


def resolve_effective_creativity(
    *,
    message_creativity: float | None = None,
    conversation_creativity: float | None = None,
    active_skills: list[Any] | None = None,
) -> float | None:
    """Resolve the active creativity score (0.0 to 1.0) using hierarchy: Message > Conversation > Active Skill."""
    chosen: float | None = None
    if active_skills:
        for skill in active_skills:
            s_creat = getattr(skill, "creativity", None) if not isinstance(skill, dict) else skill.get("creativity")
            if s_creat is not None:
                chosen = float(s_creat)
                break
    if conversation_creativity is not None:
        chosen = float(conversation_creativity)
    if message_creativity is not None:
        chosen = float(message_creativity)
    if chosen is None:
        return None
    return max(0.0, min(1.0, chosen))


def build_creativity_instruction(
    creativity: float | None,
    *,
    has_temperature: bool = True,
) -> str:
    """
    Generate adaptive French system instructions from the creativity cursor for ALL models
    (both models with temperature/sampling parameters and models without temperature like Claude Sonnet 5.5).
    Enforces strict activity coherence and factual integrity (e.g., a scientific, technical,
    financial, or legal analysis may explore original hypotheses or angles, but MUST NEVER invent facts,
    numbers, citations, or references).
    """
    if creativity is None:
        return ""
    c = max(0.0, min(1.0, float(creativity)))
    pct = int(round(c * 100))

    mode_header = f"Calibrage de créativité ({pct} % — consignes comportementales) :"

    if c <= 0.20:
        posture = (
            "- Posture Attendue (Précision & Rigueur maximale) : privilégie les formulations directes, sobres, "
            "canoniques et déterministes. Va droit à l'essentiel, évite les digressions spéculatives ou les figures "
            "de style superflues, et appuie-toi sur les méthodes les plus éprouvées."
        )
    elif c <= 0.45:
        posture = (
            "- Posture Attendue (Équilibre & Clarté nuancée) : adopte un ton naturel, clair et structuré. "
            "Combine la solidité des approches classiques avec des exemples parlants et une expression fluide."
        )
    elif c <= 0.75:
        posture = (
            "- Posture Attendue (Créativité & Ouverture) : adopte une approche stimulante, expressive et originale. "
            "Propose des angles d'analyse variés, des analogies éclairantes, des connexions interdisciplinaires "
            "pertinentes et des pistes de réflexion neuves au-delà des lieux communs."
        )
    else:
        posture = (
            "- Posture Attendue (Audace & Exploration divergente) : fais preuve d'une grande richesse d'invention "
            "conceptuelle et stylistique. Explore des perspectives audacieuses, des hypothèses originales, des métaphores "
            "marquantes et des solutions hors des sentiers battus."
        )

    coherence_guardrail = (
        "- Cohérence avec l'activité & Rigueur factuelle absolue : adapte toujours cette créativité à la nature de la tâche. "
        "Pour la création littéraire ou le brainstorming, libère pleinement l'imagination. "
        "En revanche, pour une analyse scientifique, technique, médicale, juridique, historique ou financière, "
        "la créativité consiste à explorer des hypothèses originales, des angles d'attaque féconds ou des pédagogies éclairantes, "
        "mais tu ne dois JAMAIS inventer de faits, de chiffres, de sources ou de citations. "
        "Distingue toujours explicitement les faits établis des hypothèses exploratoires."
    )

    return f"{mode_header}\n{posture}\n{coherence_guardrail}"


def format_sampling_for_openrouter_payload(filtered_params: dict[str, Any]) -> dict[str, Any]:
    """
    Format validated and model-filtered sampling parameters into the exact JSON structure
    expected by OpenRouter's `/chat/completions` endpoint.
    """
    payload: dict[str, Any] = {}
    for k, v in filtered_params.items():
        if v is None:
            continue
        if k == "reasoning":
            if isinstance(v, dict):
                payload["reasoning"] = v
            elif isinstance(v, str):
                eff = v.strip().lower()
                if eff == "none":
                    payload["reasoning"] = {"enabled": False}
                elif eff in REASONING_EFFORT_VALUES:
                    payload["reasoning"] = {"effort": eff}
        else:
            payload[k] = v
    return payload


def resolve_effective_sampling(
    *,
    message_creativity: float | None = None,
    message_params: dict[str, Any] | None = None,
    conversation_creativity: float | None = None,
    conversation_params: dict[str, Any] | None = None,
    active_skills: list[Any] | None = None,
    supported_parameters: list[str] | None = None,
    default_temperature: float = 0.2,
) -> dict[str, Any]:
    """
    Resolve the final sampling payload for a chat completion request:
    Priority:
      1. Explicit message overrides (if provided)
      2. Conversation creativity & sampling_params
      3. First active skill that defines creativity or sampling_params
      4. Application default temperature (if supported by the model)
    Finally filters strictly by the model's `supported_parameters` and formats for OpenRouter.
    """
    supported = (
        set(supported_parameters)
        if supported_parameters is not None
        else set(DEFAULT_SUPPORTED_PARAMETERS)
    )

    chosen_creativity: float | None = None
    chosen_overrides: dict[str, Any] = {}

    # 3. Active skills (lowest custom priority; first skill with settings wins)
    if active_skills:
        for skill in active_skills:
            s_creat = getattr(skill, "creativity", None) if not isinstance(skill, dict) else skill.get("creativity")
            s_params = getattr(skill, "sampling_params", None) if not isinstance(skill, dict) else skill.get("sampling_params")
            clean_s_params = sanitize_sampling_dict(s_params)
            if s_creat is not None or clean_s_params:
                chosen_creativity = float(s_creat) if s_creat is not None else None
                if clean_s_params:
                    chosen_overrides.update(clean_s_params)
                break

    # 2. Conversation level overrides skill level
    clean_conv_params = sanitize_sampling_dict(conversation_params)
    if conversation_creativity is not None or clean_conv_params:
        if conversation_creativity is not None:
            chosen_creativity = float(conversation_creativity)
        if clean_conv_params:
            chosen_overrides.update(clean_conv_params)

    # 1. Message level overrides conversation level
    clean_msg_params = sanitize_sampling_dict(message_params)
    if message_creativity is not None or clean_msg_params:
        if message_creativity is not None:
            chosen_creativity = float(message_creativity)
        if clean_msg_params:
            chosen_overrides.update(clean_msg_params)

    # Compute base values from creativity or fallback to default_temperature
    raw_payload: dict[str, Any] = {}
    if chosen_creativity is not None:
        raw_payload.update(compute_parameters_from_creativity(chosen_creativity, supported))
    else:
        if "temperature" in supported:
            raw_payload["temperature"] = default_temperature

    # Apply explicit parameter overrides
    for param, value in chosen_overrides.items():
        if value is not None:
            raw_payload[param] = value

    # Strictly filter against supported_parameters of the target model
    filtered_payload = {
        k: v
        for k, v in raw_payload.items()
        if k in supported and v is not None
    }
    return format_sampling_for_openrouter_payload(filtered_payload)
