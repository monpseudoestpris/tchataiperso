import asyncio
import datetime
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import current_user, get_sessions, get_settings, get_upload_dir
from ..finance import get_financial_dashboard_data
from ..finance_dossier import generate_dossier_ai_analysis, get_financial_dossier
from ..finance_experts import generate_finance_expert_opinion, list_finance_experts_and_cached
from ..finance_funds import (
    get_daily_sync_state,
    get_daily_sync_status,
    list_eufund_catalog,
    list_exchange_catalog,
    run_daily_sync_now,
    search_eodhd_funds_live,
    sync_configured_exchange_catalogs,
    sync_exchange_catalog_if_needed,
    update_daily_sync_preferences,
)
from ..finance_indices import (
    get_index_composition,
    get_index_performances,
    list_eodhd_indx_catalog,
    list_principal_indices,
    search_finance_catalog,
)
from ..providers import ProviderError
from ..finance_moat import analyze_and_build_stock_moat
from ..finance_news import get_cached_or_fetch_eodhd_news_feed, search_and_summarize_stock_news
from ..finance_ranges import ChartRange, DEFAULT_CHART_RANGE
from ..finance_reports import (
    MAX_REPORT_EXTRACTED_CHARS,
    analyze_quarterly_report,
    extract_markdown_tables,
    extract_report_content,
)
from ..finance_report_html import build_classy_report_html
from ..finance_statements import get_financial_statements, is_valid_symbol
from ..finance_warehouse import (
    delete_ai_analysis_entry,
    get_ai_analysis_entry,
    list_ai_analyses,
    load_user_watchlists_from_warehouse,
    resolve_canonical_symbol,
    sync_user_watchlists_to_warehouse,
    warehouse_db_path,
)
from ..finance_watchlist import (
    DEFAULT_WATCHLIST_SEEDS,
    fetch_watchlist_quotes,
    repair_watchlist_item_names,
    resolve_watchlist_instrument,
)
from ..models import (
    FinanceCustomIndicator,
    FinanceQuarterlyReport,
    FinanceStockMoat,
    FinanceStockNews,
    FinanceWatchlist,
    FinanceWatchlistItem,
    User,
    VisualDocument,
)
from ..schemas import (
    AddWatchlistItemRequest,
    AnalyzeStockMoatRequest,
    CreateCustomIndicatorRequest,
    CreateWatchlistRequest,
    SearchStockNewsRequest,
    UpdateCustomIndicatorRequest,
    UpdateWatchlistItemNoteRequest,
    UpdateWatchlistRequest,
)
from ..serializers import (
    custom_indicator_json,
    quarterly_report_json,
    stock_moat_json,
    stock_news_json,
    visual_doc_json,
    watchlist_item_json,
    watchlist_json,
)
from ..visual_documents import compile_finance_report_to_visual_doc, remove_visual_doc_dir

_logger = logging.getLogger("uvicorn.error")

router = APIRouter()


@router.get("/details")
async def get_finance_details(
    query: str = Query(
        ...,
        min_length=1,
        description="Nom d'entreprise, code ISIN ou ticker financier (ex. 'Air Liquide', 'AAPL', 'AI.PA')",
    ),
    range: ChartRange = Query(DEFAULT_CHART_RANGE, description="Durée d'affichage de la courbe"),
    refresh: bool = Query(False, description="Forcer le re-téléchargement depuis les APIs financières"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """
    Renvoie l'ensemble des données du tableau de bord financier pour la modale dédiée :
    - Cotations en direct et historique journalier EOD (courbe du cours)
    - Statistiques financières complètes structurées (Valorisation, Rentabilité, Bilan, Analystes, Profil)
    """
    clean_q = query.strip()
    if not clean_q:
        raise HTTPException(400, "Veuillez fournir un nom d'entreprise ou un ticker financier.")

    try:
        return await get_financial_dashboard_data(settings, clean_q, limit_bars=30, chart_range=range, refresh=refresh)
    except HTTPException:
        raise
    except Exception as exc:
        _logger.warning("Erreur lors de la récupération du tableau de bord financier (%s): %s", clean_q, exc)
        raise HTTPException(
            502, f"Impossible de récupérer les données financières pour « {query} » : {exc}"
        ) from exc


@router.get("/statements")
async def get_finance_statements(
    symbol: str = Query(..., min_length=1, max_length=32, description="Ticker (ex. 'AI.PA', 'AAPL.US', 'FR0013202132.EUFUND')"),
    refresh: bool = Query(False, description="Forcer le re-téléchargement depuis EODHD / Yahoo Finance"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Compte de résultat, bilan, flux de trésorerie, BPA et ratios dérivés (historique complet)."""
    clean = symbol.strip()
    if not is_valid_symbol(clean):
        raise HTTPException(400, "Ticker invalide.")
    return await get_financial_statements(clean, settings=settings, refresh=refresh)


@router.get("/dossier")
async def get_finance_dossier(
    symbol: str = Query(..., min_length=1, max_length=32, description="Ticker (ex. 'AAPL.US', 'AI.PA', 'FR0013202132.EUFUND')"),
    refresh: bool = Query(False, description="Forcer le rafraîchissement des données et historiques"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Dossier boursier institutionnel complet (capital, valorisation, risque, scores, parties prenantes, dividendes, comptes)."""
    clean = symbol.strip()
    if not is_valid_symbol(clean):
        raise HTTPException(400, "Ticker invalide.")
    return await get_financial_dossier(settings, clean, refresh=refresh)


@router.post("/dossier/analyze")
async def analyze_finance_dossier(
    body: dict[str, Any] = Body(...),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Génère et mémorise l'analyse fondamentale éditoriale basée sur les chiffres réels du dossier."""
    clean = str(body.get("symbol") or "").strip()
    if not clean or not is_valid_symbol(clean):
        raise HTTPException(400, "Ticker invalide.")
    model_id = body.get("model_id")
    try:
        return await generate_dossier_ai_analysis(
            settings, clean, model_id=str(model_id).strip() if model_id else None
        )
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Erreur réseau lors de l'analyse IA : {exc}") from exc


@router.get("/experts")
def get_finance_experts_endpoint(
    symbol: str | None = Query(None, max_length=32, description="Ticker pour charger les avis déjà mémorisés"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Liste les personnalités célèbres de la finance et leurs avis déjà enregistrés pour une action."""
    clean = (symbol or "").strip()
    if clean and not is_valid_symbol(clean):
        raise HTTPException(400, "Ticker invalide.")
    return list_finance_experts_and_cached(settings, clean or None)


@router.post("/dossier/expert")
async def request_finance_expert_opinion(
    body: dict[str, Any] = Body(...),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Génère l'avis d'un expert célèbre de la finance basé sur les chiffres complets et le modèle IA choisi."""
    clean = str(body.get("symbol") or "").strip()
    if not clean or not is_valid_symbol(clean):
        raise HTTPException(400, "Ticker invalide.")
    expert_id = str(body.get("expert_id") or "").strip()
    if not expert_id:
        raise HTTPException(400, "Identifiant d'expert requis.")
    model_id = body.get("model_id")
    question = body.get("question")
    try:
        return await generate_finance_expert_opinion(
            settings,
            clean,
            expert_id=expert_id,
            model_id=str(model_id).strip() if model_id else None,
            question=str(question).strip() if question else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Erreur réseau lors de la consultation d'expert : {exc}") from exc


def _dt_to_utc_iso(dt_val: datetime.datetime | None) -> str:
    if not dt_val:
        return ""
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=datetime.timezone.utc)
    return dt_val.astimezone(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@router.get("/ai-history")
def list_finance_ai_history(
    request: Request,
    symbol: str | None = Query(None, max_length=32, description="Filtrer par ticker (optionnel)"),
    kind: str | None = Query(None, max_length=24, description="expert | dossier | moat | news | report"),
    expert_id: str | None = Query(None, max_length=64),
    limit: int = Query(120, ge=1, le=300),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retourne l'historique daté complet des analyses IA (Experts, Dossier, MOAT, Veille, Rapports)."""
    clean_sym = (symbol or "").strip()
    if clean_sym and not is_valid_symbol(clean_sym):
        raise HTTPException(400, "Ticker invalide.")
    clean_kind = (kind or "").strip().lower() or None
    clean_expert = (expert_id or "").strip() or None

    db_path = warehouse_db_path(settings)
    items: list[dict[str, Any]] = []

    if clean_sym:
        # Déclenche l'éventuelle migration douce des anciens snapshots experts
        list_finance_experts_and_cached(settings, clean_sym)

    if clean_kind in (None, "expert", "dossier"):
        items.extend(
            list_ai_analyses(
                db_path,
                symbol=clean_sym or None,
                kind=clean_kind,
                expert_id=clean_expert,
                limit=limit,
            )
        )

    sessions = getattr(request.app.state, "sessions", None)
    if sessions and not clean_expert and clean_kind in (None, "moat", "news", "report"):
        sym_candidates: list[str] | None = None
        if clean_sym:
            raw_u = clean_sym.upper()
            canon_u = resolve_canonical_symbol(db_path, clean_sym)
            sym_candidates = list({raw_u, canon_u, raw_u.split(".")[0], canon_u.split(".")[0]})

        with sessions() as db:
            if clean_kind in (None, "moat"):
                stmt = select(FinanceStockMoat).where(FinanceStockMoat.user_id == user.id)
                if sym_candidates:
                    stmt = stmt.where(FinanceStockMoat.symbol.in_(sym_candidates))
                for m in db.scalars(stmt.order_by(FinanceStockMoat.created_at.desc()).limit(limit)):
                    c_iso = _dt_to_utc_iso(m.created_at)
                    verdict_txt = f"{m.moat_rating.upper()} ({m.moat_score}/100)"
                    items.append(
                        {
                            "id": f"moat:{m.id}",
                            "symbol": m.symbol,
                            "company_name": m.company_name,
                            "kind": "moat",
                            "expert_id": "",
                            "expert_name": "Évaluation MOAT",
                            "model": "IA MOAT",
                            "question": None,
                            "verdict": verdict_txt,
                            "conviction": f"{round(m.moat_score / 10, 1)}/10",
                            "horizon": "Avantage concurrentiel",
                            "markdown": m.summary_markdown,
                            "content_html": build_classy_report_html(
                                m.summary_markdown,
                                title=f"Analyse MOAT — {m.company_name or m.symbol}",
                                subtitle=f"Score MOAT : {m.moat_score}/100 ({m.moat_rating})",
                                symbol=m.symbol,
                                model="Analyse MOAT",
                                created_at=c_iso,
                                accent="#0ea5e9",
                                badge_label="MOAT",
                            ),
                            "news_sources": [],
                            "news_articles": [],
                            "created_at": c_iso,
                        }
                    )

            if clean_kind in (None, "news"):
                stmt = select(FinanceStockNews).where(FinanceStockNews.user_id == user.id)
                if sym_candidates:
                    stmt = stmt.where(FinanceStockNews.symbol.in_(sym_candidates))
                for n in db.scalars(stmt.order_by(FinanceStockNews.created_at.desc()).limit(limit)):
                    c_iso = _dt_to_utc_iso(n.created_at)
                    items.append(
                        {
                            "id": f"news:{n.id}",
                            "symbol": n.symbol,
                            "company_name": n.company_name,
                            "kind": "news",
                            "expert_id": "",
                            "expert_name": "Veille Actualités IA",
                            "model": n.search_query or "Veille Web",
                            "question": n.search_query or None,
                            "verdict": "",
                            "conviction": "",
                            "horizon": "",
                            "markdown": n.summary_markdown,
                            "content_html": build_classy_report_html(
                                n.summary_markdown,
                                title=f"Veille Actualités — {n.company_name or n.symbol}",
                                subtitle=n.search_query or "Synthèse d'actualités boursières",
                                symbol=n.symbol,
                                model="Veille IA",
                                created_at=c_iso,
                                accent="#f59e0b",
                                badge_label="Actualités IA",
                                question=n.search_query or None,
                            ),
                            "news_sources": ["SearXNG"],
                            "news_articles": n.articles or [],
                            "created_at": c_iso,
                        }
                    )

            if clean_kind in (None, "report"):
                stmt = select(FinanceQuarterlyReport).where(FinanceQuarterlyReport.user_id == user.id)
                if sym_candidates:
                    stmt = stmt.where(FinanceQuarterlyReport.symbol.in_(sym_candidates))
                for r in db.scalars(stmt.order_by(FinanceQuarterlyReport.created_at.desc()).limit(limit)):
                    c_iso = _dt_to_utc_iso(r.created_at)
                    items.append(
                        {
                            "id": f"report:{r.id}",
                            "symbol": r.symbol,
                            "company_name": r.company_name,
                            "kind": "report",
                            "expert_id": "",
                            "expert_name": f"Rapport · {r.period_label or r.title}",
                            "model": r.source_type or "Rapport",
                            "question": None,
                            "verdict": r.period_label or "",
                            "conviction": "",
                            "horizon": "",
                            "markdown": r.summary_markdown,
                            "content_html": build_classy_report_html(
                                r.summary_markdown,
                                title=f"{r.title} — {r.company_name or r.symbol}",
                                subtitle=r.period_label or "Analyse de rapport financier",
                                symbol=r.symbol,
                                model=r.source_type or "Rapport",
                                created_at=c_iso,
                                accent="#8b5cf6",
                                badge_label="Rapport Trimestriel",
                            ),
                            "news_sources": [],
                            "news_articles": [],
                            "created_at": c_iso,
                        }
                    )

    items.sort(key=lambda it: str(it.get("created_at") or ""), reverse=True)
    return {"items": items[:limit]}


@router.get("/ai-history/{analysis_id}")
def get_finance_ai_history_item(
    analysis_id: str,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retourne le détail d'une analyse IA archivée."""
    db_path = warehouse_db_path(settings)
    item = get_ai_analysis_entry(db_path, analysis_id)
    if not item:
        raise HTTPException(404, "Analyse archivée introuvable.")
    return item


@router.delete("/ai-history/{analysis_id}", status_code=204)
def delete_finance_ai_history_item(
    request: Request,
    analysis_id: str,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> Response:
    """Supprime une analyse IA archivée (expert, dossier, MOAT, veille ou rapport)."""
    clean_id = analysis_id.strip()
    sessions = getattr(request.app.state, "sessions", None)
    if clean_id.startswith("moat:") and sessions:
        raw_id = clean_id.split(":", 1)[1]
        with sessions() as db:
            row = db.scalar(
                select(FinanceStockMoat).where(FinanceStockMoat.id == raw_id, FinanceStockMoat.user_id == user.id)
            )
            if not row:
                raise HTTPException(404, "Analyse MOAT introuvable.")
            db.delete(row)
            db.commit()
        return Response(status_code=204)
    if clean_id.startswith("news:") and sessions:
        raw_id = clean_id.split(":", 1)[1]
        with sessions() as db:
            row = db.scalar(
                select(FinanceStockNews).where(FinanceStockNews.id == raw_id, FinanceStockNews.user_id == user.id)
            )
            if not row:
                raise HTTPException(404, "Archive actualité introuvable.")
            db.delete(row)
            db.commit()
        return Response(status_code=204)
    if clean_id.startswith("report:") and sessions:
        raw_id = clean_id.split(":", 1)[1]
        storage_name: str | None = None
        with sessions() as db:
            row = db.scalar(
                select(FinanceQuarterlyReport).where(
                    FinanceQuarterlyReport.id == raw_id, FinanceQuarterlyReport.user_id == user.id
                )
            )
            if not row:
                raise HTTPException(404, "Rapport introuvable.")
            storage_name = row.storage_name
            db.delete(row)
            db.commit()
        if storage_name:
            (settings.resolved_upload_dir / storage_name).unlink(missing_ok=True)
        return Response(status_code=204)

    db_path = warehouse_db_path(settings)
    deleted = delete_ai_analysis_entry(db_path, clean_id)
    if not deleted:
        raise HTTPException(404, "Analyse archivée introuvable.")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Indices principaux, Compositions & Recherche entrepôt rapide
# ---------------------------------------------------------------------------


@router.get("/indices")
async def get_principal_indices(
    include_quotes: bool = Query(True, description="Inclure les niveaux et variations journalières"),
    tier: str = Query("major", pattern="^(major|minor|all)$", description="Périmètre des cotations à rafraîchir"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Liste les indices principaux et secondaires ainsi que l'état de l'entrepôt SQLite."""
    return await list_principal_indices(settings, include_quotes=include_quotes, tier=tier)


@router.get("/indices/eodhd-catalog")
async def get_eodhd_indx_catalog_endpoint(
    q: str = Query("", max_length=80, description="Filtre par code, nom ou pays"),
    limit: int = Query(120, ge=1, le=300),
    refresh: bool = Query(False, description="Forcer le re-téléchargement depuis EODHD"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retourne le catalogue complet des indices EODHD (`/api/exchange-symbol-list/INDX`)."""
    return await list_eodhd_indx_catalog(settings, query=q, limit=limit, refresh=refresh)


@router.get("/indices/{index_code}")
async def get_principal_index_composition(
    index_code: str,
    refresh: bool = Query(False, description="Forcer le re-téléchargement de la composition"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retourne la composition sélectionnable d'un indice (CAC 40, S&P 500, NASDAQ 100, etc.)."""
    payload = await get_index_composition(settings, index_code, refresh=refresh)
    if payload is None:
        raise HTTPException(404, f"Indice inconnu : {index_code}")
    return payload


@router.get("/indices/{index_code}/performances")
async def get_cached_index_performances_endpoint(
    index_code: str,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Calcule le tableau des performances d'un indice uniquement à partir des cours déjà sauvegardés localement (0 appel réseau)."""
    payload = await get_index_performances(settings, index_code, refresh=False, cache_only=True)
    if payload is None:
        raise HTTPException(404, f"Indice inconnu : {index_code}")
    return payload


@router.post("/indices/{index_code}/performances")
async def load_index_performances_endpoint(
    index_code: str,
    refresh: bool = Query(False, description="Forcer le re-téléchargement des cours EOD"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Charge toutes les actions d'un indice en entrepôt et calcule le tableau complet de leurs performances."""
    payload = await get_index_performances(settings, index_code, refresh=refresh)
    if payload is None:
        raise HTTPException(404, f"Indice inconnu : {index_code}")
    return payload


@router.post("/indices/{index_code}/watchlist", status_code=201)
async def import_index_to_watchlist_endpoint(
    index_code: str,
    body: dict[str, Any] | None = Body(default=None),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    """Crée ou complète une liste de suivi avec toutes les actions d'un indice en une seule opération."""
    comp = await get_index_composition(settings, index_code, refresh=False)
    if comp is None:
        raise HTTPException(404, f"Indice inconnu : {index_code}")

    defn = comp["index"]
    constituents = comp["constituents"] or []
    req_body = body if isinstance(body, dict) else {}
    target_list_id = str(req_body.get("list_id") or "").strip() or None
    requested_name = str(req_body.get("list_name") or defn.get("name") or index_code).strip()[:80]
    default_curr = str(defn.get("currency") or "EUR").upper()[:16]

    with sessions() as db:
        lists = _ensure_user_watchlists(db, user.id, settings=settings)
        target: FinanceWatchlist | None = None
        if target_list_id:
            target = next((wl for wl in lists if wl.id == target_list_id), None)
            if not target:
                raise HTTPException(404, "Liste de suivi introuvable.")
        else:
            target = next((wl for wl in lists if wl.name.lower() == requested_name.lower()), None)
            if not target:
                max_pos = max((wl.position for wl in lists), default=-1)
                target = FinanceWatchlist(user_id=user.id, name=requested_name, position=max_pos + 1)
                db.add(target)
                db.commit()
                db.refresh(target)

        existing_rows = db.execute(
            select(FinanceWatchlistItem.symbol, FinanceWatchlistItem.eod_ticker).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
            )
        ).all()
        existing_syms = {str(r[0]).upper() for r in existing_rows if r[0]} | {
            str(r[1]).upper() for r in existing_rows if r[1]
        }
        max_item_pos = db.scalar(
            select(func.max(FinanceWatchlistItem.position)).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
            )
        )
        next_pos = (max_item_pos if max_item_pos is not None else -1) + 1
        added_count = 0
        for item in constituents:
            sym = str(item.get("eod_ticker") or item.get("symbol") or "").strip().upper()[:32]
            if not sym or sym in existing_syms:
                continue
            existing_syms.add(sym)
            db.add(
                FinanceWatchlistItem(
                    user_id=user.id,
                    list_id=target.id,
                    symbol=sym,
                    yahoo_symbol=str(item.get("yahoo_symbol") or sym).strip().upper()[:32],
                    eod_ticker=str(item.get("eod_ticker") or sym).strip().upper()[:32],
                    name=str(item.get("name") or sym).strip()[:200],
                    exchange=str(item.get("exchange") or "")[:80],
                    currency=default_curr,
                    position=next_pos,
                )
            )
            next_pos += 1
            added_count += 1
        if added_count > 0:
            db.commit()
        total_in_list = db.scalar(
            select(func.count(FinanceWatchlistItem.id)).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
            )
        )
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
        wl_payload = watchlist_json(target, int(total_in_list or 0))

    return {
        "list": wl_payload,
        "added_count": added_count,
        "total_constituents": len(constituents),
    }


@router.get("/catalog/search")
async def search_finance_catalog_endpoint(
    q: str = Query(..., min_length=1, max_length=80, description="Ticker, nom ou secteur"),
    limit: int = Query(25, ge=1, le=80),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Recherche rapide dans les actions déjà chargées en entrepôt, compositions d'indices et fonds EUFUND."""
    return {"items": search_finance_catalog(settings, q, limit=limit)}


@router.get("/catalog/exchanges")
async def get_exchange_catalog_endpoint(
    exchange: str = Query("EUFUND", max_length=12, description="Place EODHD (EUFUND, PA, US, XETRA, LSE, CC ou ALL)"),
    q: str = Query("", max_length=100, description="Filtre par nom, ISIN, gérant ou ticker"),
    currency: str = Query("", max_length=12, description="Filtre par devise (EUR, USD, CHF...)"),
    country: str = Query("", max_length=60, description="Filtre par pays"),
    type: str = Query("", max_length=40, description="Filtre par type (Common Stock, ETF, Fund, Currency...)"),
    fund_family: str = Query("", max_length=120, description="Filtre par société de gestion"),
    limit: int = Query(60, ge=1, le=300),
    offset: int = Query(0, ge=0),
    refresh: bool = Query(False, description="Forcer la re-synchronisation depuis EODHD"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Catalogue multi-marchés EODHD (`/api/exchange-symbol-list/{EXCHANGE}`) indexé localement en SQLite/FTS5."""
    try:
        return await list_exchange_catalog(
            settings,
            exchange=exchange,
            query=q,
            currency=currency,
            country=country,
            instrument_type=type,
            fund_family=fund_family,
            limit=limit,
            offset=offset,
            refresh=refresh,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/catalog/exchanges/sync")
async def sync_exchange_catalogs_endpoint(
    exchange: str = Query("ALL", max_length=12, description="Place à synchroniser (EUFUND, PA, US, XETRA, LSE, CC ou ALL)"),
    refresh: bool = Query(True, description="Forcer le téléchargement même si le cache a moins de 24h"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Synchronise manuellement un ou tous les marchés EODHD configurés."""
    clean_exch = (exchange or "ALL").strip().upper()
    if clean_exch == "ALL":
        return await sync_configured_exchange_catalogs(settings, refresh=refresh)
    try:
        meta, source = await sync_exchange_catalog_if_needed(settings, clean_exch, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "codes": [clean_exch],
        "fetched_exchanges": 1 if source.startswith("EODHD") else 0,
        "exchanges": {
            clean_exch: {
                "total": meta["total"],
                "source": source,
                "synced_at": meta["fetched_at"],
            }
        },
    }


@router.get("/sync-preferences")
async def get_finance_sync_preferences_endpoint(
    refresh_catalogs: bool = Query(False, description="Actualiser les listes complètes d'indices et de places EODHD"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retourne les réglages de synchronisation quotidienne automatique (indices activés par défaut)."""
    return await get_daily_sync_state(settings, refresh_catalogs=refresh_catalogs)


@router.put("/sync-preferences")
async def update_finance_sync_preferences_endpoint(
    body: dict[str, Any] = Body(...),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Enregistre ce que l'utilisateur souhaite synchroniser quotidiennement en arrière-plan."""
    return await update_daily_sync_preferences(settings, body)


@router.get("/sync-preferences/status")
def get_finance_sync_status_endpoint(
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retourne instantanément l'état et l'avancement en direct de la synchro automatique."""
    return get_daily_sync_status()


@router.post("/sync-preferences/run")
async def run_finance_sync_now_endpoint(
    refresh: bool = Query(False, description="Forcer le re-téléchargement même si déjà sauvegardé aujourd'hui"),
    background: bool = Query(True, description="Exécuter en tâche de fond détachée (résiste aux changements d'onglet)"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Déclenche immédiatement la synchronisation selon la sélection enregistrée."""
    if background:
        from ..finance_funds import start_daily_sync_background

        return await start_daily_sync_background(settings, refresh=refresh, respect_enabled=False)
    return await run_daily_sync_now(settings, refresh=refresh, respect_enabled=False)


@router.post("/sync-preferences/upgrade-eodhd")
async def upgrade_finance_warehouse_eodhd_endpoint(
    body: dict[str, Any] = Body(default_factory=dict),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Met à jour en lot les cours EOD et états financiers de l'entrepôt local depuis EODHD."""
    from ..finance_funds import start_eodhd_upgrade_background, upgrade_warehouse_to_eodhd

    kwargs = {
        "include_bars": bool(body.get("include_bars", True)),
        "include_fundamentals": bool(body.get("include_fundamentals", True)),
        "force_all_fundamentals": bool(body.get("force_all_fundamentals", False)),
        "max_fundamentals": int(body.get("max_fundamentals") or 250),
        "max_bars": int(body.get("max_bars") or 600),
    }
    if bool(body.get("background", True)):
        return await start_eodhd_upgrade_background(settings, **kwargs)
    return await upgrade_warehouse_to_eodhd(settings, **kwargs)


@router.get("/funds/eufund")
async def get_eufund_catalog_endpoint(
    q: str = Query("", max_length=100, description="Filtre par nom, ISIN ou code ticker"),
    currency: str = Query("", max_length=12, description="Filtre par devise (EUR, USD, CHF...)"),
    country: str = Query("", max_length=60, description="Filtre par pays"),
    type: str = Query("", max_length=40, description="Filtre par type"),
    fund_family: str = Query("", max_length=120, description="Filtre par société de gestion"),
    limit: int = Query(60, ge=1, le=300),
    offset: int = Query(0, ge=0),
    refresh: bool = Query(False, description="Forcer la re-synchronisation depuis EODHD"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Catalogue complet et filtrable des fonds européens EODHD (`/api/exchange-symbol-list/EUFUND`)."""
    return await list_eufund_catalog(
        settings,
        query=q,
        currency=currency,
        country=country,
        instrument_type=type,
        fund_family=fund_family,
        limit=limit,
        offset=offset,
        refresh=refresh,
    )


@router.get("/funds/search")
async def search_eodhd_funds_endpoint(
    q: str = Query(..., min_length=1, max_length=100, description="Nom du fonds ou code ISIN"),
    limit: int = Query(25, ge=1, le=60),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Recherche directe de fonds par nom ou ISIN (entrepôt EUFUND + EODHD `/api/search/?type=fund`)."""
    return await search_eodhd_funds_live(settings, q, limit=limit)


# ---------------------------------------------------------------------------
# Watchlists personnalisées & Tableau de suivi (1J / 1S / 1M / 3M / 1A)
# ---------------------------------------------------------------------------


def _backup_user_watchlists_to_warehouse(settings: Settings | None, db: Any, user_id: str) -> None:
    """Synchronise les listes et actions de l'utilisateur dans `finance_warehouse.db` (volume finance_data)."""
    if settings is None:
        return
    try:
        wls = list(
            db.scalars(
                select(FinanceWatchlist)
                .where(FinanceWatchlist.user_id == user_id)
                .order_by(FinanceWatchlist.position.asc(), FinanceWatchlist.created_at.asc())
            )
        )
        its = list(
            db.scalars(
                select(FinanceWatchlistItem)
                .where(FinanceWatchlistItem.user_id == user_id)
                .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
            )
        )
        sync_user_watchlists_to_warehouse(
            warehouse_db_path(settings),
            user_id,
            [
                {
                    "id": w.id,
                    "name": w.name,
                    "position": w.position,
                    "created_at": w.created_at.isoformat() if w.created_at else None,
                    "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                }
                for w in wls
            ],
            [
                {
                    "id": it.id,
                    "list_id": it.list_id,
                    "symbol": it.symbol,
                    "yahoo_symbol": it.yahoo_symbol,
                    "eod_ticker": it.eod_ticker,
                    "name": it.name,
                    "exchange": it.exchange,
                    "currency": it.currency,
                    "note": getattr(it, "note", "") or "",
                    "position": it.position,
                    "created_at": it.created_at.isoformat() if it.created_at else None,
                }
                for it in its
                if it.list_id
            ],
        )
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning("Synchronisation backup listes vers entrepôt ignorée : %s", exc)


def _ensure_user_watchlists(db: Any, user_id: str, settings: Settings | None = None) -> list[FinanceWatchlist]:
    """Garantit au moins une liste (ou restaure depuis `finance_warehouse.db`) et rattache les orphelins."""
    lists = list(
        db.scalars(
            select(FinanceWatchlist)
            .where(FinanceWatchlist.user_id == user_id)
            .order_by(FinanceWatchlist.position.asc(), FinanceWatchlist.created_at.asc())
        )
    )
    changed = False
    if not lists and settings is not None:
        backup = load_user_watchlists_from_warehouse(warehouse_db_path(settings), user_id)
        if backup.get("lists"):
            restored_ids: set[str] = set()
            for bw in backup["lists"]:
                wl = FinanceWatchlist(
                    id=str(bw["id"]),
                    user_id=user_id,
                    name=str(bw["name"])[:80],
                    position=int(bw.get("position") or 0),
                )
                db.add(wl)
                restored_ids.add(wl.id)
                lists.append(wl)
            for bit in backup.get("items") or []:
                lid = str(bit.get("list_id") or "")
                if lid not in restored_ids:
                    continue
                db.add(
                    FinanceWatchlistItem(
                        id=str(bit["id"]),
                        user_id=user_id,
                        list_id=lid,
                        symbol=str(bit["symbol"]),
                        yahoo_symbol=str(bit.get("yahoo_symbol") or ""),
                        eod_ticker=str(bit.get("eod_ticker") or ""),
                        name=str(bit.get("name") or bit["symbol"]),
                        exchange=str(bit.get("exchange") or ""),
                        currency=str(bit.get("currency") or "EUR"),
                        note=str(bit.get("note") or "")[:240],
                        position=int(bit.get("position") or 0),
                    )
                )
            db.commit()
            for wl in lists:
                db.refresh(wl)
            return lists

    if not lists:
        default_wl = FinanceWatchlist(user_id=user_id, name="Suivi principal", position=0)
        db.add(default_wl)
        db.commit()
        db.refresh(default_wl)
        lists = [default_wl]
        changed = True

    orphans = list(
        db.scalars(
            select(FinanceWatchlistItem).where(
                FinanceWatchlistItem.user_id == user_id,
                FinanceWatchlistItem.list_id.is_(None),
            )
        )
    )
    if orphans:
        first_id = lists[0].id
        for item in orphans:
            item.list_id = first_id
        db.commit()
        changed = True
    if changed:
        _backup_user_watchlists_to_warehouse(settings, db, user_id)
    return lists


def _watchlist_counts(db: Any, user_id: str) -> dict[str, int]:
    rows = db.execute(
        select(FinanceWatchlistItem.list_id, func.count(FinanceWatchlistItem.id))
        .where(FinanceWatchlistItem.user_id == user_id)
        .group_by(FinanceWatchlistItem.list_id)
    ).all()
    return {str(lid): int(cnt) for lid, cnt in rows if lid}


def _resolve_target_watchlist(
    db: Any,
    user_id: str,
    list_id: str | None,
    settings: Settings | None = None,
) -> tuple[list[FinanceWatchlist], FinanceWatchlist]:
    lists = _ensure_user_watchlists(db, user_id, settings=settings)
    if not list_id:
        return lists, lists[0]
    target = next((wl for wl in lists if wl.id == list_id), None)
    if not target:
        raise HTTPException(404, "Liste de suivi introuvable.")
    return lists, target


@router.get("/watchlists")
def list_user_watchlists(
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        lists = _ensure_user_watchlists(db, user.id, settings=settings)
        counts = _watchlist_counts(db, user.id)
    return {"lists": [watchlist_json(wl, counts.get(wl.id, 0)) for wl in lists]}


@router.post("/watchlists", status_code=201)
def create_user_watchlist(
    body: CreateWatchlistRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        lists = _ensure_user_watchlists(db, user.id, settings=settings)
        if any(wl.name.lower() == body.name.lower() for wl in lists):
            raise HTTPException(409, f"Une liste nommée « {body.name} » existe déjà.")
        max_pos = max((wl.position for wl in lists), default=-1)
        wl = FinanceWatchlist(user_id=user.id, name=body.name, position=max_pos + 1)
        db.add(wl)
        db.commit()
        db.refresh(wl)
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
    return watchlist_json(wl, 0)


@router.patch("/watchlists/{list_id}")
def rename_user_watchlist(
    list_id: str,
    body: UpdateWatchlistRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        lists, target = _resolve_target_watchlist(db, user.id, list_id, settings=settings)
        if any(wl.id != list_id and wl.name.lower() == body.name.lower() for wl in lists):
            raise HTTPException(409, f"Une liste nommée « {body.name} » existe déjà.")
        target.name = body.name
        db.commit()
        db.refresh(target)
        counts = _watchlist_counts(db, user.id)
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
    return watchlist_json(target, counts.get(target.id, 0))


@router.delete("/watchlists/{list_id}", status_code=204)
def delete_user_watchlist(
    list_id: str,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        lists, target = _resolve_target_watchlist(db, user.id, list_id, settings=settings)
        if len(lists) <= 1:
            raise HTTPException(400, "Vous devez conserver au moins une liste de suivi.")
        db.delete(target)
        db.commit()
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
    return Response(status_code=204)


@router.get("/watchlist")
async def get_watchlist(
    list_id: str | None = Query(None, description="ID de la liste personnalisée à afficher"),
    seed_defaults: bool = Query(False, description="Initialiser la liste par défaut si vide"),
    include_quotes: bool = Query(True, description="Calculer les cours et variations 1J/1S/1M/3M/1A"),
    refresh: bool = Query(False, description="Forcer la mise à jour réseau des cours"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        lists, target = _resolve_target_watchlist(db, user.id, list_id, settings=settings)
        items = list(
            db.scalars(
                select(FinanceWatchlistItem)
                .where(
                    FinanceWatchlistItem.user_id == user.id,
                    FinanceWatchlistItem.list_id == target.id,
                )
                .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
            )
        )
        if not items and seed_defaults and target.id == lists[0].id:
            for idx, seed in enumerate(DEFAULT_WATCHLIST_SEEDS):
                db.add(
                    FinanceWatchlistItem(
                        user_id=user.id,
                        list_id=target.id,
                        symbol=seed["symbol"],
                        yahoo_symbol=seed["yahoo_symbol"],
                        eod_ticker=seed["eod_ticker"],
                        name=seed["name"],
                        exchange=seed["exchange"],
                        currency=seed["currency"],
                        position=idx,
                    )
                )
            db.commit()
            _backup_user_watchlists_to_warehouse(settings, db, user.id)
            items = list(
                db.scalars(
                    select(FinanceWatchlistItem)
                    .where(
                        FinanceWatchlistItem.user_id == user.id,
                        FinanceWatchlistItem.list_id == target.id,
                    )
                    .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
                )
            )
        if items and await repair_watchlist_item_names(settings, items):
            db.commit()
            for it in items:
                db.refresh(it)
            _backup_user_watchlists_to_warehouse(settings, db, user.id)
        counts = _watchlist_counts(db, user.id)
        lists_payload = [watchlist_json(wl, counts.get(wl.id, 0)) for wl in lists]

    if not include_quotes:
        return {
            "active_list_id": target.id,
            "lists": lists_payload,
            "items": [watchlist_item_json(item) for item in items],
        }
    enriched = await fetch_watchlist_quotes(settings, items, refresh=refresh)
    return {
        "active_list_id": target.id,
        "lists": lists_payload,
        "items": enriched,
    }


@router.post("/watchlist", status_code=201)
async def add_watchlist_item(
    body: AddWatchlistItemRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    resolved = await resolve_watchlist_instrument(settings, body.query)
    with sessions() as db:
        _, target = _resolve_target_watchlist(db, user.id, body.list_id, settings=settings)
        existing = db.scalar(
            select(FinanceWatchlistItem).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
                FinanceWatchlistItem.symbol == resolved["symbol"],
            )
        )
        if existing:
            item = existing
            changed_existing = False
            if resolved.get("name") and str(existing.name or "").strip().upper() in {
                str(existing.symbol or "").upper(),
                str(existing.eod_ticker or "").upper(),
            } and str(resolved["name"]).upper() != str(existing.symbol or "").upper():
                existing.name = resolved["name"]
                changed_existing = True
            if body.note and body.note != (existing.note or ""):
                existing.note = body.note
                changed_existing = True
            if changed_existing:
                db.commit()
                db.refresh(existing)
                _backup_user_watchlists_to_warehouse(settings, db, user.id)
        else:
            max_pos = db.scalar(
                select(func.max(FinanceWatchlistItem.position)).where(
                    FinanceWatchlistItem.user_id == user.id,
                    FinanceWatchlistItem.list_id == target.id,
                )
            )
            item = FinanceWatchlistItem(
                user_id=user.id,
                list_id=target.id,
                symbol=resolved["symbol"],
                yahoo_symbol=resolved["yahoo_symbol"],
                eod_ticker=resolved["eod_ticker"],
                name=resolved["name"],
                exchange=resolved["exchange"],
                currency=resolved["currency"],
                note=body.note,
                position=(max_pos if max_pos is not None else -1) + 1,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            _backup_user_watchlists_to_warehouse(settings, db, user.id)

    enriched = await fetch_watchlist_quotes(settings, [item])
    return enriched[0]


@router.post("/watchlist/seed-defaults", status_code=201)
async def seed_default_watchlist(
    list_id: str | None = Query(None, description="ID de la liste cible"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        _, target = _resolve_target_watchlist(db, user.id, list_id, settings=settings)
        existing_symbols = set(
            db.scalars(
                select(FinanceWatchlistItem.symbol).where(
                    FinanceWatchlistItem.user_id == user.id,
                    FinanceWatchlistItem.list_id == target.id,
                )
            )
        )
        max_pos = db.scalar(
            select(func.max(FinanceWatchlistItem.position)).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
            )
        )
        next_pos = (max_pos if max_pos is not None else -1) + 1
        for seed in DEFAULT_WATCHLIST_SEEDS:
            if seed["symbol"] in existing_symbols:
                continue
            db.add(
                FinanceWatchlistItem(
                    user_id=user.id,
                    list_id=target.id,
                    symbol=seed["symbol"],
                    yahoo_symbol=seed["yahoo_symbol"],
                    eod_ticker=seed["eod_ticker"],
                    name=seed["name"],
                    exchange=seed["exchange"],
                    currency=seed["currency"],
                    position=next_pos,
                )
            )
            next_pos += 1
        db.commit()
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
        items = list(
            db.scalars(
                select(FinanceWatchlistItem)
                .where(
                    FinanceWatchlistItem.user_id == user.id,
                    FinanceWatchlistItem.list_id == target.id,
                )
                .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
            )
        )
    enriched = await fetch_watchlist_quotes(settings, items)
    return {"active_list_id": target.id, "items": enriched}


@router.patch("/watchlist/{item_id}")
def update_watchlist_item_note(
    item_id: str,
    body: UpdateWatchlistItemNoteRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    """Met à jour la note personnelle associée à une valeur dans une liste de suivi."""
    with sessions() as db:
        item = db.scalar(
            select(FinanceWatchlistItem).where(
                FinanceWatchlistItem.id == item_id,
                FinanceWatchlistItem.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Action suivie introuvable.")
        item.note = body.note
        db.commit()
        db.refresh(item)
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
        return watchlist_item_json(item)


@router.delete("/watchlist/{item_id}", status_code=204)
def delete_watchlist_item(
    item_id: str,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(FinanceWatchlistItem).where(
                FinanceWatchlistItem.id == item_id,
                FinanceWatchlistItem.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Action suivie introuvable.")
        db.delete(item)
        db.commit()
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Indicateurs techniques personnalisés (façon TradingView)
# ---------------------------------------------------------------------------


@router.get("/indicators")
def list_custom_indicators(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        items = list(
            db.scalars(
                select(FinanceCustomIndicator)
                .where(FinanceCustomIndicator.user_id == user.id)
                .order_by(FinanceCustomIndicator.created_at.asc())
            )
        )
    return {"items": [custom_indicator_json(item) for item in items]}


@router.post("/indicators", status_code=201)
def create_custom_indicator(
    body: CreateCustomIndicatorRequest,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        item = FinanceCustomIndicator(
            user_id=user.id,
            name=body.name,
            formula=body.formula,
            pane=body.pane,
            series_type=body.series_type,
            color=body.color,
            guide_lines=[g.model_dump() for g in body.guide_lines],
            enabled_by_default=body.enabled_by_default,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return custom_indicator_json(item)


@router.patch("/indicators/{indicator_id}")
def update_custom_indicator(
    indicator_id: str,
    body: UpdateCustomIndicatorRequest,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        item = db.scalar(
            select(FinanceCustomIndicator).where(
                FinanceCustomIndicator.id == indicator_id,
                FinanceCustomIndicator.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Indicateur personnalisé introuvable.")
        if body.name is not None:
            item.name = body.name
        if body.formula is not None:
            item.formula = body.formula
        if body.pane is not None:
            item.pane = body.pane
        if body.series_type is not None:
            item.series_type = body.series_type
        if body.color is not None:
            item.color = body.color
        if body.guide_lines is not None:
            item.guide_lines = [g.model_dump() for g in body.guide_lines]
        if body.enabled_by_default is not None:
            item.enabled_by_default = body.enabled_by_default
        db.commit()
        db.refresh(item)
        return custom_indicator_json(item)


@router.delete("/indicators/{indicator_id}", status_code=204)
def delete_custom_indicator(
    indicator_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(FinanceCustomIndicator).where(
                FinanceCustomIndicator.id == indicator_id,
                FinanceCustomIndicator.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Indicateur personnalisé introuvable.")
        db.delete(item)
        db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Recherche, synthèse et historique des News par action
# ---------------------------------------------------------------------------


@router.get("/news")
async def list_stock_news(
    symbol: str | None = Query(None, max_length=32),
    include_feed: bool = Query(True, description="Inclure les dépêches EODHD / Yahoo en cache (ou en direct)"),
    refresh: bool = Query(False, description="Forcer le re-téléchargement des dépêches EODHD/Yahoo"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    clean_sym = (symbol or "").strip().upper()
    sym_aliases: list[str] = []
    if clean_sym:
        db_path = warehouse_db_path(settings)
        canonical = resolve_canonical_symbol(db_path, clean_sym)
        sym_aliases = sorted(
            {
                s
                for s in (
                    clean_sym,
                    canonical,
                    canonical.split(".", 1)[0],
                    f"{clean_sym}.US" if "." not in clean_sym else "",
                )
                if s
            }
        )
    with sessions() as db:
        stmt = select(FinanceStockNews).where(FinanceStockNews.user_id == user.id)
        if sym_aliases:
            stmt = stmt.where(FinanceStockNews.symbol.in_(sym_aliases))
        rows = list(db.scalars(stmt.order_by(FinanceStockNews.created_at.desc()).limit(30)))
    feed: dict[str, Any] | None = None
    if clean_sym and include_feed:
        feed = await get_cached_or_fetch_eodhd_news_feed(settings, clean_sym, refresh=refresh, limit=20)
    return {"items": [stock_news_json(row) for row in rows], "feed": feed}


@router.post("/news/search", status_code=201)
async def search_stock_news(
    body: SearchStockNewsRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    result = await search_and_summarize_stock_news(
        settings,
        symbol=body.symbol,
        company_name=body.company_name,
        focus_query=body.focus_query,
    )
    with sessions() as db:
        item = FinanceStockNews(
            user_id=user.id,
            symbol=result["symbol"],
            company_name=result["company_name"],
            search_query=result["search_query"],
            summary_markdown=result["summary_markdown"],
            articles=result["articles"],
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return stock_news_json(item)


@router.delete("/news/{news_id}", status_code=204)
def delete_stock_news(
    news_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(FinanceStockNews).where(
                FinanceStockNews.id == news_id,
                FinanceStockNews.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Analyse d'actualités introuvable.")
        db.delete(item)
        db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Import, analyse, résumé et stockage des rapports trimestriels (PDF / texte)
# ---------------------------------------------------------------------------


@router.get("/reports")
def list_quarterly_reports(
    symbol: str | None = Query(None, max_length=32),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        stmt = select(FinanceQuarterlyReport).where(FinanceQuarterlyReport.user_id == user.id)
        if symbol and symbol.strip():
            stmt = stmt.where(FinanceQuarterlyReport.symbol == symbol.strip().upper())
        rows = list(db.scalars(stmt.order_by(FinanceQuarterlyReport.created_at.desc()).limit(50)))
    return {"items": [quarterly_report_json(row, include_extracted=False) for row in rows]}


@router.get("/reports/{report_id}")
def get_quarterly_report(
    report_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        item = db.scalar(
            select(FinanceQuarterlyReport).where(
                FinanceQuarterlyReport.id == report_id,
                FinanceQuarterlyReport.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Rapport trimestriel introuvable.")
        return quarterly_report_json(item, include_extracted=True)


@router.get("/reports/{report_id}/file")
def download_quarterly_report_file(
    report_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(
            select(FinanceQuarterlyReport).where(
                FinanceQuarterlyReport.id == report_id,
                FinanceQuarterlyReport.user_id == user.id,
            )
        )
        if not item or not item.storage_name or not (upload_dir / item.storage_name).is_file():
            raise HTTPException(404, "Fichier source du rapport introuvable.")
        media = "application/pdf" if item.source_type == "pdf" else "text/plain"
        return FileResponse(
            upload_dir / item.storage_name,
            media_type=media,
            filename=item.filename or f"{item.symbol}-rapport.txt",
            content_disposition_type="attachment",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )


@router.post("/reports", status_code=201)
async def import_and_analyze_quarterly_report(
    request: Request,
    symbol: str = Form(...),
    company_name: str = Form(""),
    title: str = Form(""),
    period_label: str = Form(""),
    raw_text: str = Form(""),
    file: UploadFile | None = File(None),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()[:32]
    if not clean_symbol:
        raise HTTPException(400, "Le symbole boursier est requis.")
    clean_company = company_name.strip()[:200] or clean_symbol
    clean_period = period_label.strip()[:60]
    clean_title = title.strip()[:255]

    storage_name: str | None = None
    stored_path: Path | None = None
    filename = ""
    source_type = "text"
    extracted_text = ""

    if file is not None and (file.filename or "").strip():
        upload_dir = get_upload_dir(request)
        try:
            content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        finally:
            await file.close()
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"Fichier limité à {settings.max_upload_mb} Mo.")
        if not content:
            raise HTTPException(422, "Le fichier importé est vide.")
        filename = Path((file.filename or "rapport.txt").replace("\\", "/")).name[:255]
        source_type, extracted_text = await extract_report_content(settings, content, filename)
        storage_name = f"finrep-{uuid4()}"
        stored_path = upload_dir / storage_name
        stored_path.write_bytes(content)
        if not clean_title:
            clean_title = Path(filename).stem[:255]
    else:
        cleaned_raw = raw_text.strip()
        if not cleaned_raw:
            raise HTTPException(422, "Importez un fichier (PDF/DOCX/TXT) ou collez le texte du rapport.")
        extracted_text = cleaned_raw[:MAX_REPORT_EXTRACTED_CHARS]
        source_type = "text"
        filename = "rapport-texte.txt"
        if not clean_title:
            clean_title = f"Rapport {clean_period or clean_symbol}"[:255]

    extracted_tables = extract_markdown_tables(extracted_text)
    extracted_at = datetime.datetime.now(datetime.timezone.utc)

    try:
        summary_markdown, key_metrics = await analyze_quarterly_report(
            settings,
            symbol=clean_symbol,
            company_name=clean_company,
            title=clean_title,
            period_label=clean_period,
            text=extracted_text,
        )
        with sessions() as db:
            item = FinanceQuarterlyReport(
                user_id=user.id,
                symbol=clean_symbol,
                company_name=clean_company,
                title=clean_title,
                period_label=clean_period,
                source_type=source_type,
                filename=filename,
                storage_name=storage_name,
                extracted_text=extracted_text,
                extracted_tables=extracted_tables,
                extracted_at=extracted_at,
                summary_markdown=summary_markdown,
                key_metrics=key_metrics,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return quarterly_report_json(item, include_extracted=True)
    except Exception:
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        raise


@router.post("/reports/{report_id}/visual-doc")
async def ensure_visual_doc_from_finance_report(
    report_id: str,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    """Convertit (ou récupère) un rapport financier archivé en `VisualDocument` interactif attachable au tchat / mode vocal."""
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        report = db.scalar(
            select(FinanceQuarterlyReport).where(
                FinanceQuarterlyReport.id == report_id,
                FinanceQuarterlyReport.user_id == user.id,
            )
        )
        if not report:
            raise HTTPException(404, "Rapport financier introuvable.")

        deterministic_slug = f"finrep-{report.id.replace('-', '')[:12].lower()}"
        existing = db.scalar(
            select(VisualDocument).where(
                VisualDocument.slug == deterministic_slug,
                VisualDocument.user_id == user.id,
            )
        )
        if existing is not None:
            return visual_doc_json(existing, detail=True)

        report_snapshot = {
            "id": report.id,
            "symbol": report.symbol,
            "company_name": report.company_name,
            "title": report.title,
            "period_label": report.period_label,
            "filename": report.filename or f"{report.symbol}-rapport.pdf",
            "storage_name": report.storage_name,
            "extracted_text": report.extracted_text or "",
            "summary_markdown": report.summary_markdown or "",
            "key_metrics": report.key_metrics if isinstance(report.key_metrics, dict) else {},
            "extracted_tables": report.extracted_tables if isinstance(report.extracted_tables, list) else [],
        }

    pdf_bytes: bytes | None = None
    storage_name = report_snapshot["storage_name"]
    if storage_name:
        candidate_path = (upload_dir / storage_name).resolve()
        try:
            if candidate_path.parent == upload_dir.resolve() and candidate_path.is_file():
                raw = candidate_path.read_bytes()
                if raw.startswith(b"%PDF-"):
                    pdf_bytes = raw
        except OSError:
            pdf_bytes = None

    title_parts = [report_snapshot["company_name"] or report_snapshot["symbol"]]
    if report_snapshot["period_label"]:
        title_parts.append(report_snapshot["period_label"])
    elif report_snapshot["title"]:
        title_parts.append(report_snapshot["title"])
    doc_title = " — ".join(title_parts)[:200]
    doc_id = str(uuid4())

    compiled = await asyncio.to_thread(
        compile_finance_report_to_visual_doc,
        app_data_dir=settings.app_data_dir,
        doc_id=doc_id,
        slug=deterministic_slug,
        title=doc_title,
        symbol=report_snapshot["symbol"],
        company_name=report_snapshot["company_name"],
        period_label=report_snapshot["period_label"],
        extracted_text=report_snapshot["extracted_text"],
        summary_markdown=report_snapshot["summary_markdown"],
        key_metrics=report_snapshot["key_metrics"],
        extracted_tables=report_snapshot["extracted_tables"],
        pdf_bytes=pdf_bytes,
    )

    try:
        with sessions() as db:
            vdoc = VisualDocument(
                id=doc_id,
                user_id=user.id,
                slug=deterministic_slug,
                title=doc_title,
                filename=report_snapshot["filename"][:255],
                source_type=compiled["source_type"],
                doc_category="financial",
                ocr_model=compiled["ocr_model"],
                vision_enriched=compiled["vision_enriched"],
                page_count=compiled["page_count"],
                figure_count=compiled["figure_count"],
                compiled_markdown=compiled["compiled_markdown"],
                pages_meta=compiled["pages_meta"],
                warnings=compiled["warnings"],
            )
            db.add(vdoc)
            db.commit()
            db.refresh(vdoc)
            return visual_doc_json(vdoc, detail=True)
    except Exception:
        remove_visual_doc_dir(settings.app_data_dir, doc_id)
        raise


@router.delete("/reports/{report_id}", status_code=204)
def delete_quarterly_report(
    report_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(
            select(FinanceQuarterlyReport).where(
                FinanceQuarterlyReport.id == report_id,
                FinanceQuarterlyReport.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Rapport trimestriel introuvable.")
        storage_name = item.storage_name
        db.delete(item)
        db.commit()
    if storage_name:
        (upload_dir / storage_name).unlink(missing_ok=True)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Analyse d'avantage concurrentiel (MOAT) par action
# ---------------------------------------------------------------------------


@router.get("/moat")
def list_stock_moats(
    symbol: str | None = Query(None, max_length=32),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        stmt = select(FinanceStockMoat).where(FinanceStockMoat.user_id == user.id)
        if symbol and symbol.strip():
            stmt = stmt.where(FinanceStockMoat.symbol == symbol.strip().upper())
        rows = list(db.scalars(stmt.order_by(FinanceStockMoat.created_at.desc()).limit(20)))
    return {"items": [stock_moat_json(row) for row in rows]}


@router.post("/moat/analyze", status_code=201)
async def analyze_stock_moat(
    body: AnalyzeStockMoatRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    clean_symbol = body.symbol.strip().upper()[:32]
    clean_company = body.company_name.strip()[:200] or clean_symbol

    with sessions() as db:
        recent_reports = list(
            db.scalars(
                select(FinanceQuarterlyReport)
                .where(
                    FinanceQuarterlyReport.user_id == user.id,
                    FinanceQuarterlyReport.symbol == clean_symbol,
                )
                .order_by(FinanceQuarterlyReport.created_at.desc())
                .limit(2)
            )
        )
        recent_news = list(
            db.scalars(
                select(FinanceStockNews)
                .where(
                    FinanceStockNews.user_id == user.id,
                    FinanceStockNews.symbol == clean_symbol,
                )
                .order_by(FinanceStockNews.created_at.desc())
                .limit(2)
            )
        )
        report_ctx = [
            {
                "title": r.title,
                "period_label": r.period_label,
                "summary_markdown": r.summary_markdown,
            }
            for r in recent_reports
        ]
        news_ctx = [{"summary_markdown": n.summary_markdown} for n in recent_news]

    result = await analyze_and_build_stock_moat(
        settings,
        symbol=clean_symbol,
        company_name=clean_company,
        financial_stats=body.financial_stats,
        custom_focus=body.custom_focus,
        news_items=news_ctx,
        reports=report_ctx,
    )

    with sessions() as db:
        item = FinanceStockMoat(
            user_id=user.id,
            symbol=clean_symbol,
            company_name=clean_company,
            moat_rating=result["moat_rating"],
            moat_score=result["moat_score"],
            pillars=result["pillars"],
            strengths=result["strengths"],
            weaknesses=result["weaknesses"],
            quantitative_signals=result["quantitative_signals"],
            summary_markdown=result["summary_markdown"],
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return stock_moat_json(item)


@router.delete("/moat/{moat_id}", status_code=204)
def delete_stock_moat(
    moat_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(FinanceStockMoat).where(
                FinanceStockMoat.id == moat_id,
                FinanceStockMoat.user_id == user.id,
            )
        )
        if not item:
            raise HTTPException(404, "Analyse MOAT introuvable.")
        db.delete(item)
        db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Screener boursier intégré (Fondamentaux & Indicateurs techniques)
# ---------------------------------------------------------------------------


@router.get("/screener/meta")
def get_finance_screener_meta(
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Retourne les champs filtrables, presets et couverture de l'entrepôt pour le Screener."""
    from ..finance_screener import get_screener_metadata

    return get_screener_metadata(settings)


@router.post("/screener/query")
def query_finance_screener(
    body: dict[str, Any] = Body(default_factory=dict),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    """Exécute un screening multi-critères (fondamentaux + technique) sur `finance_screener_snapshots`."""
    from ..finance_screener import query_screener

    universe_type = str(body.get("universe_type") or "all").strip().lower()
    universe_value = str(body.get("universe_value") or "").strip() or None
    wl_symbols: list[str] | None = None

    if universe_type == "watchlist":
        with sessions() as db:
            stmt = select(
                FinanceWatchlistItem.symbol,
                FinanceWatchlistItem.eod_ticker,
                FinanceWatchlistItem.yahoo_symbol,
            ).where(FinanceWatchlistItem.user_id == user.id)
            if universe_value:
                stmt = stmt.where(FinanceWatchlistItem.list_id == universe_value)
            rows = db.execute(stmt).all()
            wl_symbols = [
                str(s).strip().upper()
                for row in rows
                for s in row
                if s and str(s).strip()
            ]

    try:
        return query_screener(
            settings,
            timeframe=str(body.get("timeframe") or "day"),
            universe_type=universe_type,
            universe_value=universe_value,
            watchlist_symbols=wl_symbols,
            index_code=str(body.get("index_code") or ""),
            market_zone=str(body.get("market_zone") or ""),
            country=str(body.get("country") or ""),
            cap_category=str(body.get("cap_category") or ""),
            search=str(body.get("search") or ""),
            sector=str(body.get("sector") or ""),
            exchange=str(body.get("exchange") or ""),
            currency=str(body.get("currency") or ""),
            only_with_fundamentals=bool(body.get("only_with_fundamentals", False)),
            rules=body.get("rules") if isinstance(body.get("rules"), list) else [],
            sort_by=str(body.get("sort_by") or "market_cap"),
            sort_dir=str(body.get("sort_dir") or "desc"),
            limit=int(body.get("limit") or 100),
            offset=int(body.get("offset") or 0),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/screener/rebuild")
def rebuild_finance_screener(
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Reconstruit immédiatement l'index matérialisé du Screener à partir du cache local (0 appel réseau)."""
    from ..finance_screener import rebuild_screener_snapshots_from_warehouse

    return rebuild_screener_snapshots_from_warehouse(warehouse_db_path(settings))


@router.post("/screener/hydrate")
async def hydrate_finance_screener(
    body: dict[str, Any] = Body(default_factory=dict),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    """Synchronise les cours EOD (et optionnellement les fondamentaux manquants) d'un univers du Screener."""
    from ..finance_screener import hydrate_screener_universe

    universe_type = str(body.get("universe_type") or "index").strip().lower()
    universe_value = str(body.get("universe_value") or "").strip() or None
    wl_symbols: list[str] | None = None

    if universe_type == "watchlist":
        with sessions() as db:
            stmt = select(FinanceWatchlistItem.eod_ticker, FinanceWatchlistItem.symbol).where(
                FinanceWatchlistItem.user_id == user.id
            )
            if universe_value:
                stmt = stmt.where(FinanceWatchlistItem.list_id == universe_value)
            wl_symbols = [
                str(r[0] or r[1]).strip().upper()
                for r in db.execute(stmt).all()
                if (r[0] or r[1])
            ]

    try:
        if bool(body.get("background", False)):
            from ..finance_funds import start_screener_hydrate_background

            return await start_screener_hydrate_background(
                settings,
                universe_type=universe_type,
                universe_value=universe_value,
                watchlist_symbols=wl_symbols,
                include_fundamentals=bool(body.get("include_fundamentals", True)),
                max_fundamentals=int(body.get("max_fundamentals") or 40),
                refresh_eod=bool(body.get("refresh_eod", False)),
            )
        return await hydrate_screener_universe(
            settings,
            universe_type=universe_type,
            universe_value=universe_value,
            watchlist_symbols=wl_symbols,
            include_fundamentals=bool(body.get("include_fundamentals", True)),
            max_fundamentals=int(body.get("max_fundamentals") or 40),
            refresh_eod=bool(body.get("refresh_eod", False)),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/screener/export-watchlist", status_code=201)
def export_screener_to_watchlist(
    body: dict[str, Any] = Body(...),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    """Crée ou complète une liste de suivi avec une sélection de titres issus du Screener."""
    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(400, "Aucun titre à exporter vers la liste de suivi.")
    target_list_id = str(body.get("list_id") or "").strip() or None
    requested_name = str(body.get("list_name") or "Sélection Screener").strip()[:80] or "Sélection Screener"

    with sessions() as db:
        lists = _ensure_user_watchlists(db, user.id, settings=settings)
        target: FinanceWatchlist | None = None
        if target_list_id:
            target = next((wl for wl in lists if wl.id == target_list_id), None)
            if not target:
                raise HTTPException(404, "Liste de suivi introuvable.")
        else:
            target = next((wl for wl in lists if wl.name.lower() == requested_name.lower()), None)
            if not target:
                max_pos = max((wl.position for wl in lists), default=-1)
                target = FinanceWatchlist(user_id=user.id, name=requested_name, position=max_pos + 1)
                db.add(target)
                db.commit()
                db.refresh(target)

        existing_rows = db.execute(
            select(FinanceWatchlistItem.symbol, FinanceWatchlistItem.eod_ticker).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
            )
        ).all()
        existing_syms = {str(r[0]).upper() for r in existing_rows if r[0]} | {
            str(r[1]).upper() for r in existing_rows if r[1]
        }
        max_item_pos = db.scalar(
            select(func.max(FinanceWatchlistItem.position)).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
            )
        )
        next_pos = (max_item_pos if max_item_pos is not None else -1) + 1
        added_count = 0
        for item in raw_items[:200]:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("eod_ticker") or item.get("symbol") or "").strip().upper()[:32]
            if not sym or sym in existing_syms:
                continue
            existing_syms.add(sym)
            db.add(
                FinanceWatchlistItem(
                    user_id=user.id,
                    list_id=target.id,
                    symbol=sym,
                    yahoo_symbol=str(item.get("yahoo_symbol") or sym).strip().upper()[:32],
                    eod_ticker=str(item.get("eod_ticker") or sym).strip().upper()[:32],
                    name=str(item.get("name") or sym).strip()[:200],
                    exchange=str(item.get("exchange") or "")[:80],
                    currency=str(item.get("currency") or "EUR").strip().upper()[:16],
                    position=next_pos,
                )
            )
            next_pos += 1
            added_count += 1
        if added_count > 0:
            db.commit()
        total_in_list = db.scalar(
            select(func.count(FinanceWatchlistItem.id)).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.list_id == target.id,
            )
        )
        _backup_user_watchlists_to_warehouse(settings, db, user.id)
        wl_payload = watchlist_json(target, int(total_in_list or 0))

    return {
        "list": wl_payload,
        "added_count": added_count,
    }

