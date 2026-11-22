"""Synchronisation « bourse complète » pour le Screener (ex. tout Euronext Paris).

Pour chaque bourse choisie par l'utilisateur dans l'onglet « Données & Synchro » :
1. Toutes ses actions sont référencées dans le Screener (catalogue, sans appel réseau).
2. Cours du jour de toutes les actions déjà chargées via un seul appel EODHD
   `/api/eod-bulk-last-day/{EXCHANGE}` (≈ 100 calls par bourse, quel que soit le nombre de titres).
Les actions encore vides sont mises dans la file priorisée des fondamentaux (budget quotidien).
"""

from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .finance_eodhd_usage import record_eodhd_call
from .finance import DEFAULT_USER_AGENT, _to_adjusted_ohlc_bar
from .finance_warehouse import (
    _connect,
    _norm_sym,
    seed_screener_from_exchange_catalogs,
    upsert_eod_bars,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

# Une action catalogue « a des données » dès qu'une ligne Screener correspondante a un cours ou des fondamentaux
_HAS_DATA_EXISTS_SQL = """
    EXISTS (
        SELECT 1 FROM finance_screener_snapshots s
        WHERE (s.symbol = e.eod_ticker OR s.eod_ticker = e.eod_ticker)
          AND (s.price IS NOT NULL OR s.bars_count > 0 OR s.has_fundamentals = 1)
    )
"""


def get_full_exchange_coverage(db_path: Path, codes: list[str]) -> dict[str, dict[str, int]]:
    """Retourne, par bourse, le nombre d'actions du catalogue et combien ont déjà des données."""
    out: dict[str, dict[str, int]] = {}
    clean_codes = [_norm_sym(c) for c in codes if _norm_sym(c)]
    if not clean_codes or not db_path.exists():
        return out
    with _connect(db_path) as conn:
        for code in clean_codes:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN {_HAS_DATA_EXISTS_SQL} THEN 1 ELSE 0 END) AS with_data
                FROM finance_exchange_symbols e
                WHERE e.exchange_code = ? AND LOWER(COALESCE(e.type, '')) = 'common stock'
                """,
                (code,),
            ).fetchone()
            out[code] = {
                "total": int((row["total"] if row else 0) or 0),
                "with_data": int((row["with_data"] if row else 0) or 0),
            }
    return out


def _symbols_with_bars_by_eod_ticker(db_path: Path) -> dict[str, str]:
    """Mappe `eod_ticker` (et symbole) -> symbole canonique pour tous les titres ayant déjà des barres EOD."""
    mapping: dict[str, str] = {}
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT i.symbol, i.eod_ticker
            FROM finance_instruments i
            WHERE EXISTS (SELECT 1 FROM finance_eod_bars b WHERE b.symbol = i.symbol)
            """
        ).fetchall()
    for r in rows:
        canonical = _norm_sym(str(r["symbol"] or ""))
        if not canonical:
            continue
        mapping.setdefault(canonical, canonical)
        eod = _norm_sym(str(r["eod_ticker"] or ""))
        if eod:
            mapping[eod] = canonical
    return mapping


async def update_exchange_last_day_prices(settings: Settings, code: str) -> dict[str, Any]:
    """Met à jour le cours du jour de toutes les actions déjà chargées d'une bourse (1 appel bulk EODHD)."""
    clean = _norm_sym(code)
    result: dict[str, Any] = {"updated": 0, "error": None}
    if not settings.enabled(settings.eod_historical_data_key) or settings.demo_mode:
        result["error"] = "Clé EODHD requise"
        return result
    eod_key = settings.eod_historical_data_key.get_secret_value()
    url = (
        f"https://eodhd.com/api/eod-bulk-last-day/{urllib.parse.quote(clean)}"
        f"?api_token={urllib.parse.quote(eod_key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=90.0) as client:
            record_eodhd_call(url)
            resp = await client.get(url)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result
        raw = resp.json()
    except Exception as exc:
        _logger.warning("Bulk EOD %s indisponible: %s", clean, exc)
        result["error"] = "Appel EODHD impossible"
        return result
    if not isinstance(raw, list):
        result["error"] = "Réponse EODHD inattendue"
        return result

    db_path = warehouse_db_path(settings)
    known = _symbols_with_bars_by_eod_ticker(db_path)
    updated_symbols: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code_part = str(item.get("code") or "").strip().upper()
        if not code_part:
            continue
        eod_ticker = code_part if "." in code_part else f"{code_part}.{clean}"
        canonical = known.get(eod_ticker)
        if not canonical:
            continue  # Titre jamais chargé : sera complété progressivement (pas d'historique partiel)
        bar = _to_adjusted_ohlc_bar(
            str(item.get("date") or "")[:10],
            item.get("open"),
            item.get("high"),
            item.get("low"),
            item.get("close"),
            item.get("adjusted_close"),
            item.get("volume"),
        )
        if bar and upsert_eod_bars(db_path, canonical, [bar], "eodhd"):
            updated_symbols.append(canonical)

    if updated_symbols:
        from .finance_screener import rebuild_screener_snapshots_from_warehouse

        rebuild_screener_snapshots_from_warehouse(db_path, updated_symbols)
    result["updated"] = len(updated_symbols)
    return result


async def run_full_exchange_sync(settings: Settings, codes: list[str]) -> dict[str, Any]:
    """Synchro « bourse complète » : catalogue référencé dans le Screener + cours du jour en bulk.

    Les fondamentaux et historiques des titres encore vides sont chargés par la file priorisée
    (`finance_fundamentals_scheduler`), dans la limite du budget quotidien.
    """
    db_path = warehouse_db_path(settings)
    seed_screener_from_exchange_catalogs(db_path)
    summary: dict[str, Any] = {}
    for code in [_norm_sym(c) for c in codes if _norm_sym(c)]:
        prices = await update_exchange_last_day_prices(settings, code)
        summary[code] = {
            "prices_updated": int(prices.get("updated") or 0),
            "prices_error": prices.get("error"),
            **get_full_exchange_coverage(db_path, [code]).get(code, {"total": 0, "with_data": 0}),
        }
    return summary
