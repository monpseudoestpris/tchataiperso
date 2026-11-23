"""Couverture unifiée des sources de synchronisation et chargement immédiat par source (cours & catalogues)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .config import Settings
from .finance_eodhd_usage import fetch_eodhd_account_usage
from .finance_warehouse import (
    DEFAULT_ETF_EXCHANGE_CODES,
    _connect,
    _norm_sym,
    _utc_iso,
    get_stored_eod_bars,
    get_sync_preferences,
    list_warehouse_watchlist_items_for_sync,
    resolve_canonical_symbol,
    seed_etfs_from_exchange_catalog,
    seed_screener_from_exchange_catalogs,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

_EXCLUDED_EXCHANGES: frozenset[str] = frozenset({"ALL", "EUFUND", "CC", "INDX"})
VALID_SYNC_SOURCE_KINDS: frozenset[str] = frozenset(
    {"watchlists", "major_indices", "index", "stocks_exchange", "etf_exchange", "catalog_exchange"}
)
DEFAULT_DAILY_HYDRATE_BATCH = 80
DEFAULT_SOURCE_HYDRATE_BATCH = 150

# Ordres de grandeur hors-ligne (remplacés par les compteurs exacts dès que le catalogue EODHD est synchronisé)
ESTIMATED_EXCHANGE_COUNTS: dict[str, tuple[int, int]] = {
    "PA": (820, 420),
    "XETRA": (1100, 2400),
    "US": (22000, 3800),
    "LSE": (3200, 1900),
    "SW": (260, 1600),
    "AS": (150, 220),
    "MI": (420, 1450),
    "BR": (140, 80),
    "MC": (160, 90),
    "TO": (1600, 1150),
}
ESTIMATED_CATALOG_COUNTS: dict[str, int] = {
    "EUFUND": 55000,
    "CC": 4500,
}


def validate_sync_source_target(kind: str, code: str | None = None) -> tuple[str, str | None]:
    """Valide et normalise `(kind, code)` pour un chargement ponctuel de source ; lève `ValueError` sinon."""
    clean_kind = str(kind or "").strip().lower()
    if clean_kind not in VALID_SYNC_SOURCE_KINDS:
        raise ValueError(f"Type de source inconnu : {kind!r}")
    clean_code = _norm_sym(code or "") or None

    if clean_kind in ("watchlists", "major_indices"):
        return clean_kind, None
    if not clean_code:
        raise ValueError("Code cible requis pour ce type de source.")
    if clean_kind == "index":
        return clean_kind, clean_code
    if not clean_code.replace("-", "").replace("_", "").isalnum() or len(clean_code) > 12:
        raise ValueError(f"Code bourse invalide : {code!r}")
    if clean_kind in ("stocks_exchange", "etf_exchange") and clean_code in _EXCLUDED_EXCHANGES:
        raise ValueError(f"Code bourse non pris en charge pour ce type : {clean_code}")
    if clean_kind == "catalog_exchange" and clean_code in ("ALL", "INDX"):
        raise ValueError(f"Code catalogue invalide : {clean_code}")
    return clean_kind, clean_code


def get_unified_exchange_sources(
    db_path: Path,
    extra_codes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Retourne par place boursière la couverture Actions (cours, fondamentaux) et ETFs (cours)."""
    from .finance_geography import canonicalize_country, country_flag, exchange_display_label

    cat_stats: dict[str, dict[str, Any]] = {}
    scr_stats: dict[str, dict[str, int]] = {}
    discovered_codes: set[str] = set()

    if db_path.exists():
        with _connect(db_path) as conn:
            cat_rows = conn.execute(
                """
                SELECT UPPER(exchange_code) AS exch,
                       COUNT(*) AS total_symbols,
                       SUM(CASE WHEN LOWER(COALESCE(type, '')) = 'common stock' THEN 1 ELSE 0 END) AS stocks_total,
                       SUM(CASE WHEN LOWER(COALESCE(type, '')) = 'etf' THEN 1 ELSE 0 END) AS etf_total,
                       MAX(CASE WHEN currency != '' THEN currency ELSE NULL END) AS currency,
                       MAX(fetched_at) AS max_ts
                FROM finance_exchange_symbols
                WHERE exchange_code != ''
                GROUP BY UPPER(exchange_code)
                """
            ).fetchall()
            for r in cat_rows:
                code = _norm_sym(str(r["exch"] or ""))
                if not code or code in _EXCLUDED_EXCHANGES:
                    continue
                discovered_codes.add(code)
                cat_stats[code] = {
                    "total_symbols": int(r["total_symbols"] or 0),
                    "stocks_total": int(r["stocks_total"] or 0),
                    "etf_total": int(r["etf_total"] or 0),
                    "currency": str(r["currency"] or "").upper(),
                    "fetched_at": float(r["max_ts"]) if r["max_ts"] is not None else None,
                }

            scr_rows = conn.execute(
                """
                SELECT UPPER(exchange) AS exch,
                       SUM(CASE WHEN COALESCE(asset_type, 'stock') != 'etf' THEN 1 ELSE 0 END) AS stocks_in_scr,
                       SUM(CASE WHEN COALESCE(asset_type, 'stock') != 'etf'
                                 AND (price IS NOT NULL OR bars_count > 0) THEN 1 ELSE 0 END) AS stocks_bars,
                       SUM(CASE WHEN COALESCE(asset_type, 'stock') != 'etf'
                                 AND has_fundamentals = 1 THEN 1 ELSE 0 END) AS stocks_fund,
                       SUM(CASE WHEN asset_type = 'etf' THEN 1 ELSE 0 END) AS etf_in_scr,
                       SUM(CASE WHEN asset_type = 'etf'
                                 AND (price IS NOT NULL OR bars_count > 0) THEN 1 ELSE 0 END) AS etf_bars
                FROM finance_screener_snapshots
                WHERE exchange != ''
                GROUP BY UPPER(exchange)
                """
            ).fetchall()
            for r in scr_rows:
                code = _norm_sym(str(r["exch"] or ""))
                if not code or code in _EXCLUDED_EXCHANGES:
                    continue
                discovered_codes.add(code)
                scr_stats[code] = {
                    "stocks_in_screener": int(r["stocks_in_scr"] or 0),
                    "stocks_with_bars": int(r["stocks_bars"] or 0),
                    "stocks_with_fundamentals": int(r["stocks_fund"] or 0),
                    "etf_in_screener": int(r["etf_in_scr"] or 0),
                    "etf_with_bars": int(r["etf_bars"] or 0),
                }

    extra_set = {
        _norm_sym(c)
        for c in (extra_codes or [])
        if _norm_sym(c) and _norm_sym(c) not in _EXCLUDED_EXCHANGES
    }
    default_order = {c: i for i, c in enumerate(DEFAULT_ETF_EXCHANGE_CODES)}
    ordered_codes = sorted(
        set(DEFAULT_ETF_EXCHANGE_CODES) | extra_set | discovered_codes,
        key=lambda c: (0 if c in default_order else 1, default_order.get(c, 999), c),
    )

    out: list[dict[str, Any]] = []
    for code in ordered_codes:
        c_info = cat_stats.get(code) or {}
        s_info = scr_stats.get(code) or {}
        total_syms = int(c_info.get("total_symbols") or 0)
        stocks_in_scr = int(s_info.get("stocks_in_screener") or 0)
        etf_in_scr = int(s_info.get("etf_in_screener") or 0)
        if code not in default_order and code not in extra_set and total_syms == 0 and stocks_in_scr == 0 and etf_in_scr == 0:
            continue
        country = canonicalize_country("", exchange=code)
        catalog_synced = total_syms > 0
        est_stocks, est_etfs = ESTIMATED_EXCHANGE_COUNTS.get(code, (0, 0))
        stocks_total = int(c_info.get("stocks_total") or 0) if catalog_synced else max(stocks_in_scr, est_stocks)
        etf_total = int(c_info.get("etf_total") or 0) if catalog_synced else max(etf_in_scr, est_etfs)
        out.append(
            {
                "code": code,
                "label": exchange_display_label(code),
                "country": country,
                "flag": country_flag(country) if country else "🌐",
                "currency": str(c_info.get("currency") or ""),
                "catalog_synced": catalog_synced,
                "counts_estimated": not catalog_synced,
                "synced_at": _utc_iso(c_info["fetched_at"]) if c_info.get("fetched_at") is not None else None,
                "stocks_total": stocks_total,
                "stocks_in_screener": stocks_in_scr,
                "stocks_with_bars": int(s_info.get("stocks_with_bars") or 0),
                "stocks_with_fundamentals": int(s_info.get("stocks_with_fundamentals") or 0),
                "etf_total": etf_total,
                "etf_in_screener": etf_in_scr,
                "etf_with_bars": int(s_info.get("etf_with_bars") or 0),
            }
        )
    return out


async def ensure_exchange_catalog_counts(
    settings: Settings,
    codes: list[str] | None = None,
) -> dict[str, Any]:
    """Récupère sans injection Screener les listes d'échanges encore vides pour afficher leurs compteurs exacts."""
    from .finance_funds import get_daily_sync_state, sync_exchange_catalog_if_needed
    from .finance_warehouse import get_exchange_catalog_meta

    db_path = warehouse_db_path(settings)
    if not settings.demo_mode and settings.enabled(settings.eod_historical_data_key):
        target_codes = [
            _norm_sym(c)
            for c in (codes if codes is not None else [*DEFAULT_ETF_EXCHANGE_CODES, "EUFUND", "CC"])
            if _norm_sym(c)
        ]
        missing = [
            c
            for c in dict.fromkeys(target_codes)
            if get_exchange_catalog_meta(db_path, c).get("total", 0) == 0
        ]
        if missing:
            sem = asyncio.Semaphore(4)

            async def _sync_one(code: str) -> None:
                async with sem:
                    try:
                        await sync_exchange_catalog_if_needed(settings, code, refresh=False)
                    except Exception as exc:
                        _logger.debug("Pré-comptage catalogue %s ignoré: %s", code, exc)

            await asyncio.gather(*(_sync_one(c) for c in missing))
    return await get_daily_sync_state(settings)


def get_missing_bar_symbols_for_exchange(
    db_path: Path,
    exchange_code: str,
    asset_type: str,
    limit: int = DEFAULT_SOURCE_HYDRATE_BATCH,
) -> list[str]:
    """Retourne jusqu'à `limit` tickers sans historique EOD pour une bourse et un type (`stock` | `etf`)."""
    clean_code = _norm_sym(exchange_code)
    if not db_path.exists() or not clean_code or limit <= 0:
        return []
    is_etf = str(asset_type or "").strip().lower() == "etf"
    type_sql = "asset_type = 'etf'" if is_etf else "COALESCE(asset_type, 'stock') != 'etf'"
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(eod_ticker, ''), symbol) AS target_sym
            FROM finance_screener_snapshots
            WHERE UPPER(exchange) = ?
              AND {type_sql}
              AND price IS NULL
              AND COALESCE(bars_count, 0) = 0
            ORDER BY (market_cap IS NULL) ASC, market_cap DESC, symbol ASC
            LIMIT ?
            """,
            (clean_code, max(1, min(300, int(limit)))),
        ).fetchall()
    return [_norm_sym(str(r["target_sym"] or "")) for r in rows if r["target_sym"]]


async def hydrate_exchange_missing_bars_with_safety(
    settings: Settings,
    exchange_code: str,
    asset_type: str,
    *,
    max_batch: int = DEFAULT_SOURCE_HYDRATE_BATCH,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Charge un lot d'historiques EOD manquants (1 call / titre) en respectant la marge de sécurité du quota."""
    from .finance_screener import hydrate_screener_bars_batch

    if settings.demo_mode:
        return {"targeted": 0, "loaded": 0, "errors": 0, "calls": 0, "stopped_reason": "Mode démo actif"}
    db_path = warehouse_db_path(settings)
    missing_syms = get_missing_bar_symbols_for_exchange(db_path, exchange_code, asset_type, limit=max_batch)
    if not missing_syms:
        return {"targeted": 0, "loaded": 0, "errors": 0, "calls": 0, "stopped_reason": None}

    if settings.enabled(settings.eod_historical_data_key):
        prefs = get_sync_preferences(db_path)
        account = await fetch_eodhd_account_usage(settings, force=False)
        if account:
            daily_limit = int(account.get("daily_limit") or 100_000)
            safety_floor = int(daily_limit * int(prefs.get("fundamentals_quota_safety_pct") or 15) / 100)
            acc_left = account.get("remaining_today")
            if acc_left is not None and acc_left < safety_floor:
                return {
                    "targeted": 0,
                    "loaded": 0,
                    "errors": 0,
                    "calls": 0,
                    "stopped_reason": "Quota du compte sous la marge de sécurité",
                }

    res = await hydrate_screener_bars_batch(settings, missing_syms, on_progress=on_progress)
    return {
        "targeted": int(res.get("targeted") or 0),
        "loaded": int(res.get("loaded") or 0),
        "errors": int(res.get("errors") or 0),
        "calls": int(res.get("calls") or 0),
        "stopped_reason": res.get("stopped_reason"),
    }


async def run_daily_bulk_and_missing_bars_sync(
    settings: Settings,
    *,
    full_data_codes: list[str],
    stock_price_codes: list[str],
    etf_exch_codes: list[str],
) -> dict[str, Any]:
    """Exécute la synchro quotidienne des cours en bulk (mutualisée Actions + ETFs) et complète un lot manquant."""
    from .finance_exchange_full_sync import get_full_exchange_coverage, update_exchange_last_day_prices

    db_path = warehouse_db_path(settings)
    stock_seed_codes = list(dict.fromkeys([*full_data_codes, *stock_price_codes]))
    if stock_seed_codes:
        seed_screener_from_exchange_catalogs(db_path, stock_seed_codes)

    daily_bulk_codes = list(dict.fromkeys([*full_data_codes, *stock_price_codes, *etf_exch_codes]))
    bulk_results: dict[str, dict[str, Any]] = {}
    for code in daily_bulk_codes:
        bulk_results[code] = await update_exchange_last_day_prices(settings, code)

    full_summary: dict[str, Any] = {}
    if full_data_codes:
        cov_map = get_full_exchange_coverage(db_path, full_data_codes)
        for code in full_data_codes:
            prices = bulk_results.get(code) or {}
            full_summary[code] = {
                "prices_updated": int(prices.get("updated") or 0),
                "prices_error": prices.get("error"),
                **cov_map.get(code, {"total": 0, "with_data": 0}),
            }

    hydrated_bars: dict[str, dict[str, Any]] = {}
    for code in stock_price_codes:
        hydrated_bars[f"stock:{code}"] = await hydrate_exchange_missing_bars_with_safety(
            settings, code, "stock", max_batch=DEFAULT_DAILY_HYDRATE_BATCH
        )
    for code in etf_exch_codes:
        hydrated_bars[f"etf:{code}"] = await hydrate_exchange_missing_bars_with_safety(
            settings, code, "etf", max_batch=DEFAULT_DAILY_HYDRATE_BATCH
        )

    return {
        "bulk_codes": daily_bulk_codes,
        "bulk_results": bulk_results,
        "full_exchanges": full_summary,
        "hydrated_bars": hydrated_bars,
    }


async def execute_single_sync_source(
    settings: Settings,
    *,
    kind: str,
    code: str | None = None,
    batch_size: int = DEFAULT_SOURCE_HYDRATE_BATCH,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Charge immédiatement les cours (ou catalogue) d'une source unique en 1 clic."""
    from .finance_exchange_full_sync import update_exchange_last_day_prices
    from .finance_funds import sync_exchange_catalog_if_needed
    from .finance_indices import INDEX_DEFINITIONS, get_index_performances, list_principal_indices
    from .finance_screener import hydrate_screener_bars_batch, rebuild_screener_snapshots_from_warehouse
    from .finance_watchlist import fetch_watchlist_quotes

    clean_kind, clean_code = validate_sync_source_target(kind, code)
    db_path = warehouse_db_path(settings)
    safe_batch = max(1, min(300, int(batch_size or DEFAULT_SOURCE_HYDRATE_BATCH)))

    if clean_kind == "watchlists":
        raw_items = list_warehouse_watchlist_items_for_sync(db_path)
        enriched_count = 0
        hydrated_loaded = 0
        if raw_items:
            wl_objs = [SimpleNamespace(**it) for it in raw_items]
            enriched = await fetch_watchlist_quotes(settings, wl_objs, refresh=True)
            enriched_count = len(enriched)
            missing_wl: list[str] = []
            canonicals: list[str] = []
            for it in raw_items:
                sym = _norm_sym(str(it.get("eod_ticker") or it.get("symbol") or ""))
                if not sym:
                    continue
                canon = resolve_canonical_symbol(db_path, sym)
                canonicals.append(canon)
                if not get_stored_eod_bars(db_path, canon, limit=1):
                    missing_wl.append(sym)
            if missing_wl and not settings.demo_mode:
                hyd = await hydrate_screener_bars_batch(settings, missing_wl[:safe_batch], on_progress=on_progress)
                hydrated_loaded = int(hyd.get("loaded") or 0)
            if canonicals:
                rebuild_screener_snapshots_from_warehouse(db_path, list(dict.fromkeys(canonicals)))
        msg = f"Listes de suivi : {enriched_count} cotation(s) actualisée(s), {hydrated_loaded} historique(s) complété(s)."
        return {"kind": clean_kind, "enriched": enriched_count, "hydrated": hydrated_loaded, "message": msg}

    if clean_kind == "major_indices":
        idx_res = await list_principal_indices(settings, include_quotes=True, tier="major")
        major_codes = [str(d["code"]).upper() for d in INDEX_DEFINITIONS if d.get("tier") == "major"]
        ok_cnt = 0
        for pos, idx_code in enumerate(major_codes, start=1):
            if on_progress is not None:
                on_progress(pos - 1, len(major_codes), idx_code)
            try:
                perf = await get_index_performances(settings, idx_code, refresh=True)
                if perf:
                    ok_cnt += 1
            except Exception as exc:
                _logger.debug("Actualisation indice majeur %s ignorée: %s", idx_code, exc)
        if on_progress is not None:
            on_progress(len(major_codes), len(major_codes), "Terminé")
        quotes_cnt = len(idx_res.get("indices") or [])
        msg = f"Grands indices : {quotes_cnt} cotation(s) et {ok_cnt}/{len(major_codes)} compositions actualisées."
        return {"kind": clean_kind, "quotes": quotes_cnt, "indices_ok": ok_cnt, "message": msg}

    if clean_kind == "index":
        assert clean_code is not None
        perf = await get_index_performances(settings, clean_code, refresh=True)
        if perf is None:
            raise ValueError(f"Indice inconnu : {clean_code}")
        loaded_cnt = int((perf.get("summary") or {}).get("loaded_count") or 0)
        msg = f"Indice {clean_code} : {loaded_cnt} action(s) actualisée(s)."
        return {"kind": clean_kind, "code": clean_code, "loaded": loaded_cnt, "message": msg}

    if clean_kind in ("stocks_exchange", "etf_exchange"):
        assert clean_code is not None
        is_etf = clean_kind == "etf_exchange"
        asset_type = "etf" if is_etf else "stock"
        _, cat_src = await sync_exchange_catalog_if_needed(settings, clean_code)
        if is_etf:
            seeded = int(seed_etfs_from_exchange_catalog(db_path, [clean_code]).get(clean_code) or 0)
        else:
            seeded = seed_screener_from_exchange_catalogs(db_path, [clean_code])
        bulk = (
            await update_exchange_last_day_prices(settings, clean_code)
            if (not settings.demo_mode and settings.enabled(settings.eod_historical_data_key))
            else {"updated": 0, "error": None}
        )
        hyd = await hydrate_exchange_missing_bars_with_safety(
            settings,
            clean_code,
            asset_type,
            max_batch=safe_batch,
            on_progress=on_progress,
        )
        label = "ETFs" if is_etf else "Actions"
        msg = (
            f"{label} {clean_code} ({cat_src}) : {seeded} référencée(s), "
            f"{int(bulk.get('updated') or 0)} cours du jour, {hyd['loaded']} historique(s) chargé(s)."
        )
        if hyd.get("stopped_reason"):
            msg += f" ({hyd['stopped_reason']})"
        return {
            "kind": clean_kind,
            "code": clean_code,
            "catalog_source": cat_src,
            "seeded": seeded,
            "bulk_updated": int(bulk.get("updated") or 0),
            "hydrated": hyd,
            "message": msg,
        }

    # clean_kind == "catalog_exchange"
    assert clean_code is not None
    meta, cat_src = await sync_exchange_catalog_if_needed(settings, clean_code, refresh=True)
    total_cat = int(meta.get("total") or 0)
    msg = f"Catalogue {clean_code} ({cat_src}) : {total_cat} titres en base."
    return {"kind": clean_kind, "code": clean_code, "total": total_cat, "catalog_source": cat_src, "message": msg}
