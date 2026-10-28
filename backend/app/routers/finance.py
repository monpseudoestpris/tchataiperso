import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings
from ..deps import current_user, get_settings
from ..finance import get_financial_dashboard_data
from ..models import User

_logger = logging.getLogger("uvicorn.error")

router = APIRouter()


@router.get("/details")
async def get_finance_details(
    query: str = Query(
        ...,
        min_length=1,
        description="Nom d'entreprise, code ISIN ou ticker financier (ex. 'Air Liquide', 'AAPL', 'AI.PA')",
    ),
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
        return await get_financial_dashboard_data(settings, clean_q, limit_bars=30)
    except HTTPException:
        raise
    except Exception as exc:
        _logger.warning("Erreur lors de la récupération du tableau de bord financier (%s): %s", clean_q, exc)
        raise HTTPException(
            502, f"Impossible de récupérer les données financières pour « {query} » : {exc}"
        ) from exc
