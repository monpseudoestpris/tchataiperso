import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import current_user, get_sessions, get_settings, get_upload_dir
from ..finance import get_financial_dashboard_data
from ..finance_moat import analyze_and_build_stock_moat
from ..finance_news import search_and_summarize_stock_news
from ..finance_ranges import ChartRange, DEFAULT_CHART_RANGE
from ..finance_reports import MAX_REPORT_EXTRACTED_CHARS, analyze_quarterly_report, extract_report_text
from ..finance_statements import get_financial_statements, is_valid_symbol
from ..finance_watchlist import DEFAULT_WATCHLIST_SEEDS, fetch_watchlist_quotes, resolve_watchlist_instrument
from ..models import (
    FinanceCustomIndicator,
    FinanceQuarterlyReport,
    FinanceStockMoat,
    FinanceStockNews,
    FinanceWatchlistItem,
    User,
)
from ..schemas import (
    AddWatchlistItemRequest,
    AnalyzeStockMoatRequest,
    CreateCustomIndicatorRequest,
    SearchStockNewsRequest,
    UpdateCustomIndicatorRequest,
)
from ..serializers import (
    custom_indicator_json,
    quarterly_report_json,
    stock_moat_json,
    stock_news_json,
    watchlist_item_json,
)

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
        return await get_financial_dashboard_data(settings, clean_q, limit_bars=30, chart_range=range)
    except HTTPException:
        raise
    except Exception as exc:
        _logger.warning("Erreur lors de la récupération du tableau de bord financier (%s): %s", clean_q, exc)
        raise HTTPException(
            502, f"Impossible de récupérer les données financières pour « {query} » : {exc}"
        ) from exc


@router.get("/statements")
async def get_finance_statements(
    symbol: str = Query(..., min_length=1, max_length=20, description="Ticker Yahoo (ex. 'AI.PA')"),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Compte de résultat, bilan, flux de trésorerie (annuels et trimestriels) et ratios dérivés."""
    clean = symbol.strip()
    if not is_valid_symbol(clean):
        raise HTTPException(400, "Ticker invalide.")
    return await get_financial_statements(clean)


# ---------------------------------------------------------------------------
# Watchlist (Tableau de suivi 1J / 1S / 1M / 3M / 1A)
# ---------------------------------------------------------------------------


@router.get("/watchlist")
async def get_watchlist(
    seed_defaults: bool = Query(False, description="Initialiser la liste par défaut si vide"),
    include_quotes: bool = Query(True, description="Calculer les cours et variations 1J/1S/1M/3M/1A"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        items = list(
            db.scalars(
                select(FinanceWatchlistItem)
                .where(FinanceWatchlistItem.user_id == user.id)
                .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
            )
        )
        if not items and seed_defaults:
            for idx, seed in enumerate(DEFAULT_WATCHLIST_SEEDS):
                db.add(
                    FinanceWatchlistItem(
                        user_id=user.id,
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
            items = list(
                db.scalars(
                    select(FinanceWatchlistItem)
                    .where(FinanceWatchlistItem.user_id == user.id)
                    .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
                )
            )

    if not include_quotes:
        return {"items": [watchlist_item_json(item) for item in items]}
    enriched = await fetch_watchlist_quotes(settings, items)
    return {"items": enriched}


@router.post("/watchlist", status_code=201)
async def add_watchlist_item(
    body: AddWatchlistItemRequest,
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    resolved = await resolve_watchlist_instrument(settings, body.query)
    with sessions() as db:
        existing = db.scalar(
            select(FinanceWatchlistItem).where(
                FinanceWatchlistItem.user_id == user.id,
                FinanceWatchlistItem.symbol == resolved["symbol"],
            )
        )
        if existing:
            item = existing
        else:
            max_pos = db.scalar(
                select(func.max(FinanceWatchlistItem.position)).where(FinanceWatchlistItem.user_id == user.id)
            )
            item = FinanceWatchlistItem(
                user_id=user.id,
                symbol=resolved["symbol"],
                yahoo_symbol=resolved["yahoo_symbol"],
                eod_ticker=resolved["eod_ticker"],
                name=resolved["name"],
                exchange=resolved["exchange"],
                currency=resolved["currency"],
                position=(max_pos if max_pos is not None else -1) + 1,
            )
            db.add(item)
            db.commit()
            db.refresh(item)

    enriched = await fetch_watchlist_quotes(settings, [item])
    return enriched[0]


@router.post("/watchlist/seed-defaults", status_code=201)
async def seed_default_watchlist(
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        existing_symbols = set(
            db.scalars(select(FinanceWatchlistItem.symbol).where(FinanceWatchlistItem.user_id == user.id))
        )
        max_pos = db.scalar(
            select(func.max(FinanceWatchlistItem.position)).where(FinanceWatchlistItem.user_id == user.id)
        )
        next_pos = (max_pos if max_pos is not None else -1) + 1
        for seed in DEFAULT_WATCHLIST_SEEDS:
            if seed["symbol"] in existing_symbols:
                continue
            db.add(
                FinanceWatchlistItem(
                    user_id=user.id,
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
        items = list(
            db.scalars(
                select(FinanceWatchlistItem)
                .where(FinanceWatchlistItem.user_id == user.id)
                .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
            )
        )
    enriched = await fetch_watchlist_quotes(settings, items)
    return {"items": enriched}


@router.delete("/watchlist/{item_id}", status_code=204)
def delete_watchlist_item(
    item_id: str,
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
def list_stock_news(
    symbol: str | None = Query(None, max_length=32),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
) -> dict[str, Any]:
    with sessions() as db:
        stmt = select(FinanceStockNews).where(FinanceStockNews.user_id == user.id)
        if symbol and symbol.strip():
            stmt = stmt.where(FinanceStockNews.symbol == symbol.strip().upper())
        rows = list(db.scalars(stmt.order_by(FinanceStockNews.created_at.desc()).limit(30)))
    return {"items": [stock_news_json(row) for row in rows]}


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
        source_type, extracted_text = extract_report_text(content, filename)
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

