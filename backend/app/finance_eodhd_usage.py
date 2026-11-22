"""Suivi de la consommation de l'API EOD Historical Data (EODHD).

- Barème officiel des coûts par endpoint (« API calls » décomptés du quota journalier), d'après
  https://eodhd.com/financial-apis/api-limits (1 requête HTTP peut coûter 1, 5, 10 ou 100 « calls »).
- Compteur local en mémoire des requêtes émises par l'application depuis minuit UTC (remis à zéro
  chaque jour et au redémarrage du serveur), ventilé par endpoint avec le coût estimé.
- Consommation réelle du compte via `/api/user` (`apiRequests`, `dailyRateLimit`, `extraLimit`),
  qui ne consomme pas de quota.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
import urllib.parse
from typing import Any

import httpx

from .config import Settings

_logger = logging.getLogger("uvicorn.error")

# Barème EODHD : endpoint (premier segment après /api/) -> (coût en « API calls », libellé FR)
EODHD_ENDPOINT_COSTS: dict[str, tuple[int, str]] = {
    "eod": (1, "Historique des cours (EOD)"),
    "real-time": (1, "Cours temps réel / différé"),
    "div": (1, "Dividendes"),
    "search": (1, "Recherche de titres"),
    "exchanges-list": (1, "Liste des bourses"),
    "exchange-symbol-list": (1, "Liste des titres d'une bourse"),
    "calendar": (1, "Calendrier (résultats)"),
    "ust": (1, "Taux du Trésor US"),
    "news": (5, "Actualités"),
    "sentiments": (5, "Sentiment de marché"),
    "fundamentals": (10, "Fondamentaux"),
    "insider-transactions": (10, "Transactions d'initiés"),
    "macro-indicator": (10, "Indicateurs macroéconomiques"),
    "historical-market-cap": (10, "Capitalisation historique"),
    "eod-bulk-last-day": (100, "Cours du jour d'une bourse entière (bulk)"),
}
_DEFAULT_COST = 1

_LOCK = threading.Lock()
_USAGE_DAY: str = ""
_USAGE: dict[str, int] = {}  # endpoint -> nombre de requêtes

_USER_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_USER_CACHE_TTL_SEC = 60.0


def _today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def endpoint_from_url(url: str) -> str | None:
    """Extrait l'endpoint EODHD (`eod`, `fundamentals`…) d'une URL, ou `None` si ce n'est pas EODHD."""
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host != "eodhd.com" and not host.endswith(".eodhd.com"):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "api":
        return None
    return parts[1].lower()


def endpoint_cost(endpoint: str) -> int:
    return EODHD_ENDPOINT_COSTS.get(endpoint, (_DEFAULT_COST, endpoint))[0]


def record_eodhd_call(url: str) -> None:
    """Comptabilise une requête sortante si elle vise l'API EODHD (sans effet pour les autres URLs)."""
    global _USAGE_DAY
    endpoint = endpoint_from_url(url)
    if not endpoint or endpoint == "user":
        return
    today = _today_utc()
    with _LOCK:
        if _USAGE_DAY != today:
            _USAGE_DAY = today
            _USAGE.clear()
        _USAGE[endpoint] = _USAGE.get(endpoint, 0) + 1


def get_local_usage() -> dict[str, Any]:
    """Retourne la consommation locale du jour (UTC), ventilée par endpoint avec le coût estimé."""
    today = _today_utc()
    with _LOCK:
        snapshot = dict(_USAGE) if _USAGE_DAY == today else {}
    items = []
    for endpoint, count in snapshot.items():
        unit = endpoint_cost(endpoint)
        items.append(
            {
                "endpoint": endpoint,
                "label": EODHD_ENDPOINT_COSTS.get(endpoint, (unit, endpoint))[1],
                "requests": count,
                "unit_cost": unit,
                "calls": count * unit,
            }
        )
    items.sort(key=lambda it: (-it["calls"], it["endpoint"]))
    return {
        "date": today,
        "total_requests": sum(it["requests"] for it in items),
        "total_calls": sum(it["calls"] for it in items),
        "by_endpoint": items,
    }


def get_cost_table() -> list[dict[str, Any]]:
    return [
        {"endpoint": ep, "unit_cost": cost, "label": label}
        for ep, (cost, label) in sorted(EODHD_ENDPOINT_COSTS.items(), key=lambda kv: (kv[1][0], kv[0]))
    ]


def _int_or_none(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


async def fetch_eodhd_account_usage(settings: Settings, *, force: bool = False) -> dict[str, Any] | None:
    """Lit la consommation réelle du compte EODHD via `/api/user` (cache 60 s, sans coût de quota)."""
    if settings.demo_mode or not settings.enabled(settings.eod_historical_data_key):
        return None
    now = time.time()
    if not force and _USER_CACHE["data"] is not None and now - float(_USER_CACHE["ts"]) < _USER_CACHE_TTL_SEC:
        return _USER_CACHE["data"]
    key = settings.eod_historical_data_key.get_secret_value()
    url = f"https://eodhd.com/api/user?api_token={urllib.parse.quote(key)}&fmt=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            _logger.debug("EODHD /api/user HTTP %s", resp.status_code)
            return None
        raw = resp.json()
    except Exception as exc:
        _logger.debug("EODHD /api/user indisponible: %s", exc)
        return None
    if not isinstance(raw, dict):
        return None
    used = _int_or_none(raw.get("apiRequests"))
    limit = _int_or_none(raw.get("dailyRateLimit"))
    data = {
        "subscription": str(raw.get("subscriptionType") or ""),
        "api_requests_today": used,
        "api_requests_date": str(raw.get("apiRequestsDate") or "") or None,
        "daily_limit": limit,
        "extra_limit": _int_or_none(raw.get("extraLimit")),
        "remaining_today": (max(0, limit - used) if (limit is not None and used is not None) else None),
    }
    _USER_CACHE.update({"ts": now, "data": data})
    return data


def estimate_daily_sync_cost(prefs: dict[str, Any], daily_limit: int | None) -> dict[str, Any]:
    """Estime le coût maximal (« API calls ») de la synchro quotidienne selon les préférences enregistrées."""
    bulk_cost = endpoint_cost("eod-bulk-last-day")
    light_cost = endpoint_cost("fundamentals") + endpoint_cost("eod")
    limit = int(daily_limit or 100_000)
    lines: list[dict[str, Any]] = []

    full_codes = list(prefs.get("full_data_exchanges") or [])
    if full_codes:
        lines.append(
            {
                "label": f"Cours du jour en bulk ({', '.join(full_codes)})",
                "calls": bulk_cost * len(full_codes),
            }
        )

    if prefs.get("screener_fundamentals", True):
        pct = int(prefs.get("fundamentals_budget_pct") or 10)
        budget = int(limit * pct / 100)
        lines.append(
            {
                "label": (
                    f"Fondamentaux : budget de {pct} % de la limite (≈ {budget // light_cost} titres en chargement léger, "
                    "utilisé seulement s'il reste des titres à charger ou à rafraîchir)"
                ),
                "calls": budget + endpoint_cost("calendar"),
            }
        )

    return {
        "lines": lines,
        "max_daily_calls": sum(int(line["calls"]) for line in lines),
        "light_load_calls": light_cost,
        "full_dossier_calls_estimate": 38,
        "note": (
            "Hors cours des indices suivis (1 call par titre non à jour) et fiches consultées "
            "(≈ 38 calls pour une fiche complète avec sentiment, initiés, capitalisation historique et macro)."
        ),
    }


async def get_eodhd_usage_report(settings: Settings) -> dict[str, Any]:
    """Assemble la consommation réelle, la consommation locale, le barème et l'estimation de la synchro."""
    from .finance_warehouse import get_sync_preferences, warehouse_db_path

    prefs = get_sync_preferences(warehouse_db_path(settings))
    account = await fetch_eodhd_account_usage(settings)
    return {
        "account": account,
        "local": get_local_usage(),
        "cost_table": get_cost_table(),
        "sync_estimate": estimate_daily_sync_cost(prefs, (account or {}).get("daily_limit")),
        "source_url": "https://eodhd.com/financial-apis/api-limits",
    }
