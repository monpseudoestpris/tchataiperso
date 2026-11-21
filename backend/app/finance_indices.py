"""Catalogue des grands indices boursiers mondiaux et de leurs compositions.

Combine :
1. Les compositions live via EODHD (`/api/fundamentals/{INDEX}.INDX`, champ `Components`)
   mémorisées dans l'entrepôt SQLite `finance_warehouse.db` (`finance_index_constituents`).
2. Des listes de repli complètes et vérifiées pour les grands indices européens, américains
   et asiatiques (CAC 40, Dow Jones 30, NASDAQ 100, EURO STOXX 50, DAX 40, FTSE 100, SMI 20,
   Nikkei 225, S&P 500) lorsque l'API ne retourne pas `Components` ou hors ligne.
3. Les niveaux et variations journalières des indices (EODHD prioritaire + cache 15 min + Yahoo).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import urllib.parse
from typing import Any

import httpx

from .config import Settings
from .finance import (
    DEFAULT_USER_AGENT,
    _safe_float,
    _to_adjusted_ohlc_bar,
    fetch_eodhd_historical_eod,
    fetch_yahoo_chart,
)
from .finance_warehouse import (
    get_cached_symbols_set,
    get_index_constituents,
    get_instrument_eod_sync_info,
    get_snapshot,
    get_stored_eod_bars,
    get_warehouse_overview,
    is_eod_fresh_today,
    resolve_canonical_symbol,
    save_index_constituents,
    save_snapshot,
    search_warehouse_catalog,
    upsert_eod_bars,
    upsert_instrument,
    warehouse_db_path,
)
from .finance_watchlist import compute_period_returns

_logger = logging.getLogger("uvicorn.error")

_CONSTITUENTS_TTL_SEC = 24 * 3600.0
_INDEX_QUOTE_TTL_SEC = 900.0
_INDX_CATALOG_TTL_SEC = 7 * 24 * 3600.0

INDEX_DEFINITIONS: list[dict[str, Any]] = [
    # --- Principaux (Major) ---
    {
        "code": "CAC40",
        "tier": "major",
        "name": "CAC 40",
        "region": "France",
        "flag": "🇫🇷",
        "currency": "EUR",
        "eod_ticker": "FCHI.INDX",
        "yahoo_symbol": "^FCHI",
        "description": "40 principales capitalisations d'Euronext Paris",
    },
    {
        "code": "SP500",
        "tier": "major",
        "name": "S&P 500",
        "region": "États-Unis",
        "flag": "🇺🇸",
        "currency": "USD",
        "eod_ticker": "GSPC.INDX",
        "yahoo_symbol": "^GSPC",
        "description": "500 plus grandes sociétés cotées aux États-Unis",
    },
    {
        "code": "NASDAQ100",
        "tier": "major",
        "name": "NASDAQ 100",
        "region": "États-Unis",
        "flag": "🇺🇸",
        "currency": "USD",
        "eod_ticker": "NDX.INDX",
        "yahoo_symbol": "^NDX",
        "description": "100 principales valeurs technologiques et de croissance du Nasdaq",
    },
    {
        "code": "DJI",
        "tier": "major",
        "name": "Dow Jones 30",
        "region": "États-Unis",
        "flag": "🇺🇸",
        "currency": "USD",
        "eod_ticker": "DJI.INDX",
        "yahoo_symbol": "^DJI",
        "description": "30 valeurs industrielles et blue chips historiques américaines",
    },
    {
        "code": "EUROSTOXX50",
        "tier": "major",
        "name": "EURO STOXX 50",
        "region": "Zone Euro",
        "flag": "🇪🇺",
        "currency": "EUR",
        "eod_ticker": "STOXX50E.INDX",
        "eod_alt_tickers": ["SX5E.INDX"],
        "yahoo_symbol": "^STOXX50E",
        "description": "50 leaders de la zone euro",
    },
    {
        "code": "DAX40",
        "tier": "major",
        "name": "DAX 40",
        "region": "Allemagne",
        "flag": "🇩🇪",
        "currency": "EUR",
        "eod_ticker": "GDAXI.INDX",
        "yahoo_symbol": "^GDAXI",
        "description": "40 principales valeurs de la Bourse de Francfort (XETRA)",
    },
    {
        "code": "FTSE100",
        "tier": "major",
        "name": "FTSE 100",
        "region": "Royaume-Uni",
        "flag": "🇬🇧",
        "currency": "GBP",
        "eod_ticker": "FTSE.INDX",
        "eod_alt_tickers": ["UKX.INDX"],
        "yahoo_symbol": "^FTSE",
        "description": "100 plus grandes capitalisations de Londres (LSE)",
    },
    {
        "code": "SMI20",
        "tier": "major",
        "name": "SMI 20",
        "region": "Suisse",
        "flag": "🇨🇭",
        "currency": "CHF",
        "eod_ticker": "SSMI.INDX",
        "yahoo_symbol": "^SSMI",
        "description": "20 plus grandes valeurs suisses (SIX Swiss Exchange)",
    },
    {
        "code": "NIKKEI225",
        "tier": "major",
        "name": "Nikkei 225",
        "region": "Japon",
        "flag": "🇯🇵",
        "currency": "JPY",
        "eod_ticker": "N225.INDX",
        "yahoo_symbol": "^N225",
        "description": "225 valeurs phares de la Bourse de Tokyo",
    },
    # --- Indices secondaires / Mid & Small Caps / Nationaux (EODHD INDX) ---
    {
        "code": "SBF120",
        "tier": "minor",
        "name": "SBF 120",
        "region": "France",
        "flag": "🇫🇷",
        "currency": "EUR",
        "eod_ticker": "PX4.INDX",
        "eod_alt_tickers": ["SBF120.INDX"],
        "yahoo_symbol": "^SBF120",
        "description": "120 plus grandes valeurs françaises (CAC 40 + Next 20 + Mid 60)",
    },
    {
        "code": "CACNEXT20",
        "tier": "minor",
        "name": "CAC Next 20",
        "region": "France",
        "flag": "🇫🇷",
        "currency": "EUR",
        "eod_ticker": "CN20.INDX",
        "yahoo_symbol": "^CN20",
        "description": "20 valeurs françaises suivant le CAC 40 (antichambre du CAC 40)",
    },
    {
        "code": "CACMID60",
        "tier": "minor",
        "name": "CAC Mid 60",
        "region": "France",
        "flag": "🇫🇷",
        "currency": "EUR",
        "eod_ticker": "CACMD.INDX",
        "yahoo_symbol": "^CACMD",
        "description": "60 valeurs moyennes françaises d'Euronext Paris",
    },
    {
        "code": "RUT",
        "tier": "minor",
        "name": "Russell 2000",
        "region": "États-Unis",
        "flag": "🇺🇸",
        "currency": "USD",
        "eod_ticker": "RUT.INDX",
        "yahoo_symbol": "^RUT",
        "description": "2 000 petites et moyennes capitalisations américaines",
    },
    {
        "code": "SP400",
        "tier": "minor",
        "name": "S&P MidCap 400",
        "region": "États-Unis",
        "flag": "🇺🇸",
        "currency": "USD",
        "eod_ticker": "MID.INDX",
        "yahoo_symbol": "^MID",
        "description": "400 valeurs américaines de moyenne capitalisation",
    },
    {
        "code": "SP600",
        "tier": "minor",
        "name": "S&P SmallCap 600",
        "region": "États-Unis",
        "flag": "🇺🇸",
        "currency": "USD",
        "eod_ticker": "SML.INDX",
        "yahoo_symbol": "^SML",
        "description": "600 petites capitalisations américaines rentables",
    },
    {
        "code": "IXIC",
        "tier": "minor",
        "name": "NASDAQ Composite",
        "region": "États-Unis",
        "flag": "🇺🇸",
        "currency": "USD",
        "eod_ticker": "IXIC.INDX",
        "yahoo_symbol": "^IXIC",
        "description": "Indice global du marché Nasdaq",
    },
    {
        "code": "MDAX",
        "tier": "minor",
        "name": "MDAX",
        "region": "Allemagne",
        "flag": "🇩🇪",
        "currency": "EUR",
        "eod_ticker": "MDAXI.INDX",
        "eod_alt_tickers": ["MDAX.INDX"],
        "yahoo_symbol": "^MDAXI",
        "description": "50 moyennes capitalisations industrielles et tech allemandes",
    },
    {
        "code": "TECDAX",
        "tier": "minor",
        "name": "TecDAX",
        "region": "Allemagne",
        "flag": "🇩🇪",
        "currency": "EUR",
        "eod_ticker": "TDXP.INDX",
        "eod_alt_tickers": ["TECDAX.INDX"],
        "yahoo_symbol": "^TECDAX",
        "description": "30 principales valeurs technologiques allemandes",
    },
    {
        "code": "FTSE250",
        "tier": "minor",
        "name": "FTSE 250",
        "region": "Royaume-Uni",
        "flag": "🇬🇧",
        "currency": "GBP",
        "eod_ticker": "FTMC.INDX",
        "yahoo_symbol": "^FTMC",
        "description": "250 moyennes capitalisations britanniques (LSE)",
    },
    {
        "code": "STOXX600",
        "tier": "minor",
        "name": "STOXX Europe 600",
        "region": "Europe",
        "flag": "🇪🇺",
        "currency": "EUR",
        "eod_ticker": "STOXX.INDX",
        "eod_alt_tickers": ["SXXP.INDX"],
        "yahoo_symbol": "^STOXX",
        "description": "600 grandes, moyennes et petites capitalisations européennes",
    },
    {
        "code": "AEX25",
        "tier": "minor",
        "name": "AEX 25",
        "region": "Pays-Bas",
        "flag": "🇳🇱",
        "currency": "EUR",
        "eod_ticker": "AEX.INDX",
        "yahoo_symbol": "^AEX",
        "description": "25 principales capitalisations d'Euronext Amsterdam",
    },
    {
        "code": "BEL20",
        "tier": "minor",
        "name": "BEL 20",
        "region": "Belgique",
        "flag": "🇧🇪",
        "currency": "EUR",
        "eod_ticker": "BFX.INDX",
        "eod_alt_tickers": ["BEL20.INDX"],
        "yahoo_symbol": "^BFX",
        "description": "20 valeurs phares d'Euronext Bruxelles",
    },
    {
        "code": "IBEX35",
        "tier": "minor",
        "name": "IBEX 35",
        "region": "Espagne",
        "flag": "🇪🇸",
        "currency": "EUR",
        "eod_ticker": "IBEX.INDX",
        "yahoo_symbol": "^IBEX",
        "description": "35 principales valeurs de la Bourse de Madrid",
    },
    {
        "code": "FTSEMIB",
        "tier": "minor",
        "name": "FTSE MIB",
        "region": "Italie",
        "flag": "🇮🇹",
        "currency": "EUR",
        "eod_ticker": "FTSEMIB.INDX",
        "yahoo_symbol": "FTSEMIB.MI",
        "description": "40 principales capitalisations de la Bourse de Milan",
    },
    {
        "code": "PSI20",
        "tier": "minor",
        "name": "PSI 20",
        "region": "Portugal",
        "flag": "🇵🇹",
        "currency": "EUR",
        "eod_ticker": "PSI20.INDX",
        "yahoo_symbol": "^PSI20",
        "description": "Principal indice de la Bourse de Lisbonne",
    },
    {
        "code": "OMXS30",
        "tier": "minor",
        "name": "OMX Stockholm 30",
        "region": "Suède",
        "flag": "🇸🇪",
        "currency": "SEK",
        "eod_ticker": "OMX.INDX",
        "eod_alt_tickers": ["OMXS30.INDX"],
        "yahoo_symbol": "^OMX",
        "description": "30 valeurs les plus échangées du Nasdaq Stockholm",
    },
    {
        "code": "TSX",
        "tier": "minor",
        "name": "S&P/TSX Composite",
        "region": "Canada",
        "flag": "🇨🇦",
        "currency": "CAD",
        "eod_ticker": "GSPTSE.INDX",
        "yahoo_symbol": "^GSPTSE",
        "description": "Indice principal de la Bourse de Toronto",
    },
    {
        "code": "ASX200",
        "tier": "minor",
        "name": "S&P/ASX 200",
        "region": "Australie",
        "flag": "🇦🇺",
        "currency": "AUD",
        "eod_ticker": "AXJO.INDX",
        "yahoo_symbol": "^AXJO",
        "description": "200 plus grandes sociétés cotées en Australie",
    },
    {
        "code": "HSI",
        "tier": "minor",
        "name": "Hang Seng",
        "region": "Hong Kong",
        "flag": "🇭🇰",
        "currency": "HKD",
        "eod_ticker": "HSI.INDX",
        "yahoo_symbol": "^HSI",
        "description": "Principales valeurs de la Bourse de Hong Kong",
    },
    {
        "code": "KOSPI",
        "tier": "minor",
        "name": "KOSPI",
        "region": "Corée du Sud",
        "flag": "🇰🇷",
        "currency": "KRW",
        "eod_ticker": "KS11.INDX",
        "yahoo_symbol": "^KS11",
        "description": "Indice composite de la Bourse de Séoul",
    },
    {
        "code": "NIFTY50",
        "tier": "minor",
        "name": "Nifty 50",
        "region": "Inde",
        "flag": "🇮🇳",
        "currency": "INR",
        "eod_ticker": "NSEI.INDX",
        "yahoo_symbol": "^NSEI",
        "description": "50 principales capitalisations du National Stock Exchange (Inde)",
    },
]

_INDEX_BY_CODE: dict[str, dict[str, Any]] = {d["code"]: d for d in INDEX_DEFINITIONS}

# Correspondance code place EODHD -> suffixe ticker EODHD / Yahoo
_EOD_TO_YAHOO_SUFFIX: dict[str, str] = {
    "US": "",
    "NASDAQ": "",
    "NYSE": "",
    "PA": ".PA",
    "XETRA": ".DE",
    "DE": ".DE",
    "F": ".F",
    "LSE": ".L",
    "L": ".L",
    "AS": ".AS",
    "BR": ".BR",
    "MI": ".MI",
    "MC": ".MC",
    "SW": ".SW",
    "SIX": ".SW",
    "HE": ".HE",
    "ST": ".ST",
    "CO": ".CO",
    "OL": ".OL",
    "TO": ".TO",
    "T": ".T",
    "HK": ".HK",
}

_YAHOO_TO_EOD_EXCH: dict[str, str] = {
    "DE": "XETRA",
    "L": "LSE",
}


def _row(symbol: str, name: str, sector: str = "", exchange: str = "", yahoo: str | None = None) -> dict[str, Any]:
    sym = symbol.strip().upper()
    if yahoo:
        y_sym = yahoo.strip().upper()
    elif sym.endswith(".US"):
        y_sym = sym[:-3]
    elif sym.endswith(".XETRA"):
        y_sym = f"{sym[:-6]}.DE"
    elif sym.endswith(".LSE"):
        y_sym = f"{sym[:-4]}.L"
    else:
        y_sym = sym
    exch = exchange or (sym.split(".", 1)[1] if "." in sym else "US")
    return {
        "symbol": sym,
        "eod_ticker": sym,
        "yahoo_symbol": y_sym,
        "name": name,
        "sector": sector,
        "industry": "",
        "exchange": exch,
        "weight_pct": None,
    }


def _normalize_eodhd_component(raw: dict[str, Any], idx: int) -> dict[str, Any] | None:
    code = str(raw.get("Code") or "").strip().upper()
    exch = str(raw.get("Exchange") or "US").strip().upper()
    name = str(raw.get("Name") or code).strip()
    if not code:
        return None
    if "." in code:
        eod_ticker = code
        base, parsed_exch = code.split(".", 1)
        exch = parsed_exch
    else:
        eod_exch = _YAHOO_TO_EOD_EXCH.get(exch, exch or "US")
        eod_ticker = f"{code}.{eod_exch}"
        base = code
    y_suffix = _EOD_TO_YAHOO_SUFFIX.get(exch, f".{exch}" if exch else "")
    yahoo_symbol = f"{base}{y_suffix}" if y_suffix else base
    weight = _safe_float(raw.get("Weight"))
    return {
        "symbol": eod_ticker,
        "eod_ticker": eod_ticker,
        "yahoo_symbol": yahoo_symbol,
        "name": name,
        "sector": str(raw.get("Sector") or "").strip(),
        "industry": str(raw.get("Industry") or "").strip(),
        "exchange": exch,
        "weight_pct": round(weight, 3) if weight is not None else None,
        "position": idx,
    }


# ---------------------------------------------------------------------------
# Listes de repli structurées (utilisées si EODHD ne fournit pas Components ou hors ligne)
# ---------------------------------------------------------------------------

_CAC40_COMPONENTS: list[dict[str, Any]] = [
    _row("AC.PA", "Accor", "Consommation discrétionnaire", "PA"),
    _row("AI.PA", "Air Liquide", "Matériaux", "PA"),
    _row("AIR.PA", "Airbus", "Industrie & Aéronautique", "PA"),
    _row("MT.AS", "ArcelorMittal", "Matériaux", "AS"),
    _row("CS.PA", "AXA", "Finance & Assurance", "PA"),
    _row("BNP.PA", "BNP Paribas", "Finance & Banque", "PA"),
    _row("EN.PA", "Bouygues", "Industrie & Construction", "PA"),
    _row("BVI.PA", "Bureau Veritas", "Services aux entreprises", "PA"),
    _row("CAP.PA", "Capgemini", "Technologie", "PA"),
    _row("CA.PA", "Carrefour", "Consommation de base", "PA"),
    _row("ACA.PA", "Crédit Agricole", "Finance & Banque", "PA"),
    _row("BN.PA", "Danone", "Consommation de base", "PA"),
    _row("DSY.PA", "Dassault Systèmes", "Technologie", "PA"),
    _row("EDEN.PA", "Edenred", "Services financiers", "PA"),
    _row("ENGI.PA", "Engie", "Services aux collectivités", "PA"),
    _row("EL.PA", "EssilorLuxottica", "Santé & Optique", "PA"),
    _row("ERF.PA", "Eurofins Scientific", "Santé", "PA"),
    _row("RMS.PA", "Hermès International", "Luxe", "PA"),
    _row("KER.PA", "Kering", "Luxe", "PA"),
    _row("LR.PA", "Legrand", "Industrie électrique", "PA"),
    _row("OR.PA", "L'Oréal", "Consommation de base", "PA"),
    _row("MC.PA", "LVMH", "Luxe", "PA"),
    _row("ML.PA", "Michelin", "Automobile & Équipements", "PA"),
    _row("ORA.PA", "Orange", "Télécommunications", "PA"),
    _row("RI.PA", "Pernod Ricard", "Boissons & Spiritueux", "PA"),
    _row("PUB.PA", "Publicis Groupe", "Communication", "PA"),
    _row("RNO.PA", "Renault", "Automobile", "PA"),
    _row("SAF.PA", "Safran", "Industrie & Aéronautique", "PA"),
    _row("SGO.PA", "Saint-Gobain", "Matériaux & Construction", "PA"),
    _row("SAN.PA", "Sanofi", "Santé & Pharma", "PA"),
    _row("SU.PA", "Schneider Electric", "Industrie électrique", "PA"),
    _row("GLE.PA", "Société Générale", "Finance & Banque", "PA"),
    _row("STLAP.PA", "Stellantis", "Automobile", "PA"),
    _row("STMPA.PA", "STMicroelectronics", "Semi-conducteurs", "PA"),
    _row("TEP.PA", "Teleperformance", "Services aux entreprises", "PA"),
    _row("HO.PA", "Thales", "Défense & Aérospatiale", "PA"),
    _row("TTE.PA", "TotalEnergies", "Énergie", "PA"),
    _row("URW.PA", "Unibail-Rodamco-Westfield", "Immobilier", "PA"),
    _row("VIE.PA", "Veolia Environnement", "Services aux collectivités", "PA"),
    _row("DG.PA", "Vinci", "Infrastructures & Construction", "PA"),
]

_DJI_COMPONENTS: list[dict[str, Any]] = [
    _row("MMM.US", "3M Company", "Industrie", "US"),
    _row("AXP.US", "American Express", "Finance", "US"),
    _row("AMGN.US", "Amgen", "Santé", "US"),
    _row("AMZN.US", "Amazon.com", "Consommation & Cloud", "US"),
    _row("AAPL.US", "Apple", "Technologie", "US"),
    _row("BA.US", "Boeing", "Aéronautique", "US"),
    _row("CAT.US", "Caterpillar", "Industrie", "US"),
    _row("CVX.US", "Chevron", "Énergie", "US"),
    _row("CSCO.US", "Cisco Systems", "Technologie", "US"),
    _row("KO.US", "Coca-Cola", "Consommation de base", "US"),
    _row("DIS.US", "Walt Disney", "Médias & Loisirs", "US"),
    _row("GS.US", "Goldman Sachs", "Finance", "US"),
    _row("HD.US", "Home Depot", "Distribution", "US"),
    _row("HON.US", "Honeywell", "Industrie", "US"),
    _row("IBM.US", "IBM", "Technologie", "US"),
    _row("JNJ.US", "Johnson & Johnson", "Santé", "US"),
    _row("JPM.US", "JPMorgan Chase", "Finance", "US"),
    _row("MCD.US", "McDonald's", "Restauration", "US"),
    _row("MRK.US", "Merck & Co.", "Santé", "US"),
    _row("MSFT.US", "Microsoft", "Technologie", "US"),
    _row("NKE.US", "Nike", "Consommation discrétionnaire", "US"),
    _row("NVDA.US", "NVIDIA", "Semi-conducteurs", "US"),
    _row("PG.US", "Procter & Gamble", "Consommation de base", "US"),
    _row("CRM.US", "Salesforce", "Logiciels", "US"),
    _row("SHW.US", "Sherwin-Williams", "Matériaux", "US"),
    _row("TRV.US", "Travelers Companies", "Assurance", "US"),
    _row("UNH.US", "UnitedHealth Group", "Santé", "US"),
    _row("VZ.US", "Verizon Communications", "Télécommunications", "US"),
    _row("V.US", "Visa", "Paiements", "US"),
    _row("WMT.US", "Walmart", "Distribution", "US"),
]

_NASDAQ100_COMPONENTS: list[dict[str, Any]] = [
    _row("AAPL.US", "Apple", "Technologie", "US"),
    _row("MSFT.US", "Microsoft", "Technologie", "US"),
    _row("NVDA.US", "NVIDIA", "Semi-conducteurs", "US"),
    _row("AMZN.US", "Amazon.com", "Consommation & Cloud", "US"),
    _row("META.US", "Meta Platforms", "Communication", "US"),
    _row("GOOGL.US", "Alphabet (Class A)", "Communication", "US"),
    _row("GOOG.US", "Alphabet (Class C)", "Communication", "US"),
    _row("AVGO.US", "Broadcom", "Semi-conducteurs", "US"),
    _row("TSLA.US", "Tesla", "Automobile & Énergie", "US"),
    _row("COST.US", "Costco Wholesale", "Distribution", "US"),
    _row("NFLX.US", "Netflix", "Médias & Streaming", "US"),
    _row("ASML.US", "ASML Holding", "Semi-conducteurs", "US"),
    _row("AMD.US", "Advanced Micro Devices", "Semi-conducteurs", "US"),
    _row("PEP.US", "PepsiCo", "Consommation de base", "US"),
    _row("LIN.US", "Linde", "Matériaux", "US"),
    _row("ADBE.US", "Adobe", "Logiciels", "US"),
    _row("CSCO.US", "Cisco Systems", "Réseaux", "US"),
    _row("TMUS.US", "T-Mobile US", "Télécommunications", "US"),
    _row("QCOM.US", "Qualcomm", "Semi-conducteurs", "US"),
    _row("TXN.US", "Texas Instruments", "Semi-conducteurs", "US"),
    _row("INTU.US", "Intuit", "Logiciels", "US"),
    _row("AMAT.US", "Applied Materials", "Semi-conducteurs", "US"),
    _row("AMGN.US", "Amgen", "Biotechnologie", "US"),
    _row("ISRG.US", "Intuitive Surgical", "Santé & MedTech", "US"),
    _row("CMCSA.US", "Comcast", "Télécommunications", "US"),
    _row("BKNG.US", "Booking Holdings", "Voyage en ligne", "US"),
    _row("HON.US", "Honeywell", "Industrie", "US"),
    _row("VRTX.US", "Vertex Pharmaceuticals", "Biotechnologie", "US"),
    _row("LRCX.US", "Lam Research", "Semi-conducteurs", "US"),
    _row("PANW.US", "Palo Alto Networks", "Cybersécurité", "US"),
    _row("MU.US", "Micron Technology", "Semi-conducteurs", "US"),
    _row("ADI.US", "Analog Devices", "Semi-conducteurs", "US"),
    _row("KLAC.US", "KLA Corporation", "Semi-conducteurs", "US"),
    _row("MELI.US", "MercadoLibre", "E-commerce & Fintech", "US"),
    _row("GILD.US", "Gilead Sciences", "Biotechnologie", "US"),
    _row("CRWD.US", "CrowdStrike", "Cybersécurité", "US"),
    _row("SNPS.US", "Synopsys", "Logiciels EDA", "US"),
    _row("CDNS.US", "Cadence Design Systems", "Logiciels EDA", "US"),
    _row("REGN.US", "Regeneron Pharmaceuticals", "Biotechnologie", "US"),
    _row("PLTR.US", "Palantir Technologies", "Logiciels & IA", "US"),
    _row("APP.US", "AppLovin", "Logiciels", "US"),
    _row("SBUX.US", "Starbucks", "Restauration", "US"),
    _row("MDLZ.US", "Mondelez International", "Consommation de base", "US"),
    _row("CTAS.US", "Cintas", "Services", "US"),
    _row("MAR.US", "Marriott International", "Hôtellerie", "US"),
    _row("ORLY.US", "O'Reilly Automotive", "Distribution auto", "US"),
    _row("CEG.US", "Constellation Energy", "Énergie", "US"),
    _row("CSX.US", "CSX Corporation", "Transport ferroviaire", "US"),
    _row("PYPL.US", "PayPal Holdings", "Fintech", "US"),
    _row("ABNB.US", "Airbnb", "Voyage en ligne", "US"),
    _row("ADSK.US", "Autodesk", "Logiciels", "US"),
    _row("FTNT.US", "Fortinet", "Cybersécurité", "US"),
    _row("NXPI.US", "NXP Semiconductors", "Semi-conducteurs", "US"),
    _row("MRVL.US", "Marvell Technology", "Semi-conducteurs", "US"),
    _row("ROP.US", "Roper Technologies", "Technologie industrielle", "US"),
    _row("PCAR.US", "PACCAR", "Industrie", "US"),
    _row("WDAY.US", "Workday", "Logiciels SaaS", "US"),
    _row("MNST.US", "Monster Beverage", "Boissons", "US"),
    _row("AEP.US", "American Electric Power", "Services aux collectivités", "US"),
    _row("PAYX.US", "Paychex", "Services RH", "US"),
    _row("CPRT.US", "Copart", "Services auto", "US"),
    _row("ROST.US", "Ross Stores", "Distribution", "US"),
    _row("KDP.US", "Keurig Dr Pepper", "Boissons", "US"),
    _row("FAST.US", "Fastenal", "Distribution industrielle", "US"),
    _row("DDOG.US", "Datadog", "Logiciels Cloud", "US"),
    _row("EXC.US", "Exelon", "Services aux collectivités", "US"),
    _row("KHC.US", "Kraft Heinz", "Agroalimentaire", "US"),
    _row("BKR.US", "Baker Hughes", "Services pétroliers", "US"),
    _row("TEAM.US", "Atlassian", "Logiciels", "US"),
    _row("EA.US", "Electronic Arts", "Jeux vidéo", "US"),
    _row("XEL.US", "Xcel Energy", "Services aux collectivités", "US"),
    _row("IDXX.US", "IDEXX Laboratories", "Santé animale", "US"),
    _row("ODFL.US", "Old Dominion Freight Line", "Logistique", "US"),
    _row("CTSH.US", "Cognizant", "Services IT", "US"),
    _row("DXCM.US", "DexCom", "MedTech", "US"),
    _row("ZS.US", "Zscaler", "Cybersécurité", "US"),
    _row("CCEP.US", "Coca-Cola Europacific Partners", "Boissons", "US"),
    _row("MCHP.US", "Microchip Technology", "Semi-conducteurs", "US"),
    _row("FANG.US", "Diamondback Energy", "Énergie", "US"),
    _row("BIIB.US", "Biogen", "Biotechnologie", "US"),
    _row("ON.US", "ON Semiconductor", "Semi-conducteurs", "US"),
    _row("GFS.US", "GlobalFoundries", "Semi-conducteurs", "US"),
    _row("TTWO.US", "Take-Two Interactive", "Jeux vidéo", "US"),
    _row("ARM.US", "Arm Holdings", "Semi-conducteurs", "US"),
    _row("AXON.US", "Axon Enterprise", "Sécurité & Défense", "US"),
    _row("MSTR.US", "MicroStrategy", "Logiciels", "US"),
    _row("SHOP.US", "Shopify", "E-commerce", "US"),
]

_SP500_FALLBACK_COMPONENTS: list[dict[str, Any]] = [
    _row("AAPL.US", "Apple", "Technologie", "US"),
    _row("NVDA.US", "NVIDIA", "Semi-conducteurs", "US"),
    _row("MSFT.US", "Microsoft", "Technologie", "US"),
    _row("AMZN.US", "Amazon.com", "Consommation & Cloud", "US"),
    _row("META.US", "Meta Platforms", "Communication", "US"),
    _row("GOOGL.US", "Alphabet (Class A)", "Communication", "US"),
    _row("BRK-B.US", "Berkshire Hathaway", "Finance", "US"),
    _row("AVGO.US", "Broadcom", "Semi-conducteurs", "US"),
    _row("TSLA.US", "Tesla", "Automobile & Énergie", "US"),
    _row("LLY.US", "Eli Lilly", "Santé & Pharma", "US"),
    _row("JPM.US", "JPMorgan Chase", "Finance", "US"),
    _row("WMT.US", "Walmart", "Distribution", "US"),
    _row("V.US", "Visa", "Paiements", "US"),
    _row("MA.US", "Mastercard", "Paiements", "US"),
    _row("UNH.US", "UnitedHealth Group", "Santé", "US"),
    _row("XOM.US", "ExxonMobil", "Énergie", "US"),
    _row("COST.US", "Costco Wholesale", "Distribution", "US"),
    _row("ORCL.US", "Oracle", "Logiciels", "US"),
    _row("HD.US", "Home Depot", "Distribution", "US"),
    _row("PG.US", "Procter & Gamble", "Consommation de base", "US"),
    _row("JNJ.US", "Johnson & Johnson", "Santé", "US"),
    _row("BAC.US", "Bank of America", "Finance", "US"),
    _row("ABBV.US", "AbbVie", "Santé & Pharma", "US"),
    _row("NFLX.US", "Netflix", "Médias", "US"),
    _row("CRM.US", "Salesforce", "Logiciels", "US"),
    _row("KO.US", "Coca-Cola", "Consommation de base", "US"),
    _row("CVX.US", "Chevron", "Énergie", "US"),
    _row("MRK.US", "Merck & Co.", "Santé & Pharma", "US"),
    _row("AMD.US", "Advanced Micro Devices", "Semi-conducteurs", "US"),
    _row("PEP.US", "PepsiCo", "Consommation de base", "US"),
    _row("TMO.US", "Thermo Fisher Scientific", "Santé", "US"),
    _row("LIN.US", "Linde", "Matériaux", "US"),
    _row("ACN.US", "Accenture", "Services IT", "US"),
    _row("MCD.US", "McDonald's", "Restauration", "US"),
    _row("CSCO.US", "Cisco Systems", "Réseaux", "US"),
    _row("ABT.US", "Abbott Laboratories", "Santé", "US"),
    _row("ADBE.US", "Adobe", "Logiciels", "US"),
    _row("WFC.US", "Wells Fargo", "Finance", "US"),
    _row("GE.US", "GE Aerospace", "Aéronautique", "US"),
    _row("NOW.US", "ServiceNow", "Logiciels", "US"),
    _row("PM.US", "Philip Morris International", "Consommation de base", "US"),
    _row("IBM.US", "IBM", "Technologie", "US"),
    _row("CAT.US", "Caterpillar", "Industrie", "US"),
    _row("TXN.US", "Texas Instruments", "Semi-conducteurs", "US"),
    _row("DIS.US", "Walt Disney", "Médias", "US"),
    _row("GS.US", "Goldman Sachs", "Finance", "US"),
    _row("ISRG.US", "Intuitive Surgical", "MedTech", "US"),
    _row("QCOM.US", "Qualcomm", "Semi-conducteurs", "US"),
    _row("RTX.US", "RTX Corporation", "Défense & Aérospatiale", "US"),
    _row("AXP.US", "American Express", "Finance", "US"),
]

_EUROSTOXX50_COMPONENTS: list[dict[str, Any]] = [
    _row("ASML.AS", "ASML Holding", "Semi-conducteurs", "AS"),
    _row("MC.PA", "LVMH", "Luxe", "PA"),
    _row("SAP.XETRA", "SAP SE", "Logiciels", "XETRA", "SAP.DE"),
    _row("SIE.XETRA", "Siemens", "Industrie", "XETRA", "SIE.DE"),
    _row("TTE.PA", "TotalEnergies", "Énergie", "PA"),
    _row("SU.PA", "Schneider Electric", "Industrie électrique", "PA"),
    _row("ALV.XETRA", "Allianz", "Assurance", "XETRA", "ALV.DE"),
    _row("OR.PA", "L'Oréal", "Consommation de base", "PA"),
    _row("AI.PA", "Air Liquide", "Matériaux", "PA"),
    _row("SAN.PA", "Sanofi", "Santé & Pharma", "PA"),
    _row("AIR.PA", "Airbus", "Aéronautique", "PA"),
    _row("RMS.PA", "Hermès International", "Luxe", "PA"),
    _row("DTE.XETRA", "Deutsche Telekom", "Télécommunications", "XETRA", "DTE.DE"),
    _row("EL.PA", "EssilorLuxottica", "Santé & Optique", "PA"),
    _row("BNP.PA", "BNP Paribas", "Finance & Banque", "PA"),
    _row("IBE.MC", "Iberdrola", "Services aux collectivités", "MC"),
    _row("ITX.MC", "Inditex", "Distribution", "MC"),
    _row("SAN.MC", "Banco Santander", "Finance & Banque", "MC"),
    _row("BBVA.MC", "BBVA", "Finance & Banque", "MC"),
    _row("UCG.MI", "UniCredit", "Finance & Banque", "MI"),
    _row("ISP.MI", "Intesa Sanpaolo", "Finance & Banque", "MI"),
    _row("ENEL.MI", "Enel", "Services aux collectivités", "MI"),
    _row("RACE.MI", "Ferrari", "Automobile & Luxe", "MI"),
    _row("SAF.PA", "Safran", "Aéronautique", "PA"),
    _row("CS.PA", "AXA", "Assurance", "PA"),
    _row("MU.XETRA", "Munich Re", "Réassurance", "XETRA", "MUV2.DE"),
    _row("INGA.AS", "ING Groep", "Finance & Banque", "AS"),
    _row("ADYEN.AS", "Adyen", "Paiements", "AS"),
    _row("PRX.AS", "Prosus", "Technologie", "AS"),
    _row("DG.PA", "Vinci", "Infrastructures", "PA"),
    _row("SGO.PA", "Saint-Gobain", "Matériaux", "PA"),
    _row("BN.PA", "Danone", "Agroalimentaire", "PA"),
    _row("IFX.XETRA", "Infineon Technologies", "Semi-conducteurs", "XETRA", "IFX.DE"),
    _row("MBG.XETRA", "Mercedes-Benz Group", "Automobile", "XETRA", "MBG.DE"),
    _row("BMW.XETRA", "BMW", "Automobile", "XETRA", "BMW.DE"),
    _row("BAS.XETRA", "BASF", "Chimie", "XETRA", "BAS.DE"),
    _row("ABI.BR", "AB InBev", "Boissons", "BR"),
    _row("AD.AS", "Ahold Delhaize", "Distribution", "AS"),
    _row("ENI.MI", "Eni", "Énergie", "MI"),
    _row("STLAM.MI", "Stellantis", "Automobile", "MI"),
    _row("NOKIA.HE", "Nokia", "Télécommunications", "HE"),
    _row("NDA-FI.HE", "Nordea Bank", "Finance & Banque", "HE"),
    _row("DB1.XETRA", "Deutsche Börse", "Marchés financiers", "XETRA", "DB1.DE"),
    _row("DHL.XETRA", "DHL Group", "Logistique", "XETRA", "DHL.DE"),
    _row("BAYN.XETRA", "Bayer", "Santé & Agrochimie", "XETRA", "BAYN.DE"),
    _row("KER.PA", "Kering", "Luxe", "PA"),
    _row("RI.PA", "Pernod Ricard", "Boissons", "PA"),
    _row("ORA.PA", "Orange", "Télécommunications", "PA"),
    _row("ADS.XETRA", "Adidas", "Équipement sportif", "XETRA", "ADS.DE"),
    _row("FLTR.LSE", "Flutter Entertainment", "Divertissement", "LSE", "FLTR.L"),
]

_DAX40_COMPONENTS: list[dict[str, Any]] = [
    _row("SAP.XETRA", "SAP SE", "Logiciels", "XETRA", "SAP.DE"),
    _row("SIE.XETRA", "Siemens", "Industrie", "XETRA", "SIE.DE"),
    _row("ALV.XETRA", "Allianz", "Assurance", "XETRA", "ALV.DE"),
    _row("DTE.XETRA", "Deutsche Telekom", "Télécommunications", "XETRA", "DTE.DE"),
    _row("AIR.XETRA", "Airbus", "Aéronautique", "XETRA", "AIR.DE"),
    _row("MUV2.XETRA", "Munich Re", "Réassurance", "XETRA", "MUV2.DE"),
    _row("ENR.XETRA", "Siemens Energy", "Énergie", "XETRA", "ENR.DE"),
    _row("RHM.XETRA", "Rheinmetall", "Défense", "XETRA", "RHM.DE"),
    _row("DB1.XETRA", "Deutsche Börse", "Finance", "XETRA", "DB1.DE"),
    _row("SHL.XETRA", "Siemens Healthineers", "MedTech", "XETRA", "SHL.DE"),
    _row("IFX.XETRA", "Infineon Technologies", "Semi-conducteurs", "XETRA", "IFX.DE"),
    _row("DHL.XETRA", "DHL Group", "Logistique", "XETRA", "DHL.DE"),
    _row("MBG.XETRA", "Mercedes-Benz Group", "Automobile", "XETRA", "MBG.DE"),
    _row("BMW.XETRA", "BMW", "Automobile", "XETRA", "BMW.DE"),
    _row("BAS.XETRA", "BASF", "Chimie", "XETRA", "BAS.DE"),
    _row("ADS.XETRA", "Adidas", "Consommation", "XETRA", "ADS.DE"),
    _row("DBK.XETRA", "Deutsche Bank", "Finance & Banque", "XETRA", "DBK.DE"),
    _row("CBK.XETRA", "Commerzbank", "Finance & Banque", "XETRA", "CBK.DE"),
    _row("HNR1.XETRA", "Hannover Re", "Réassurance", "XETRA", "HNR1.DE"),
    _row("EOAN.XETRA", "E.ON", "Services aux collectivités", "XETRA", "EOAN.DE"),
    _row("RWE.XETRA", "RWE", "Énergie", "XETRA", "RWE.DE"),
    _row("VOW3.XETRA", "Volkswagen", "Automobile", "XETRA", "VOW3.DE"),
    _row("BAYN.XETRA", "Bayer", "Santé & Chimie", "XETRA", "BAYN.DE"),
    _row("MRK.XETRA", "Merck KGaA", "Santé & Science", "XETRA", "MRK.DE"),
    _row("BEI.XETRA", "Beiersdorf", "Cosmétiques", "XETRA", "BEI.DE"),
    _row("HEN3.XETRA", "Henkel", "Biens de consommation", "XETRA", "HEN3.DE"),
    _row("FRE.XETRA", "Fresenius", "Santé", "XETRA", "FRE.DE"),
    _row("FME.XETRA", "Fresenius Medical Care", "Santé", "XETRA", "FME.DE"),
    _row("MTX.XETRA", "MTU Aero Engines", "Aéronautique", "XETRA", "MTX.DE"),
    _row("DTG.XETRA", "Daimler Truck", "Véhicules industriels", "XETRA", "DTG.DE"),
    _row("HEI.XETRA", "Heidelberg Materials", "Matériaux", "XETRA", "HEI.DE"),
    _row("SY1.XETRA", "Symrise", "Chimie & Arômes", "XETRA", "SY1.DE"),
    _row("VNA.XETRA", "Vonovia", "Immobilier", "XETRA", "VNA.DE"),
    _row("QIA.XETRA", "Qiagen", "Biotechnologie", "XETRA", "QIA.DE"),
    _row("ZAL.XETRA", "Zalando", "E-commerce", "XETRA", "ZAL.DE"),
    _row("CON.XETRA", "Continental", "Équipementier auto", "XETRA", "CON.DE"),
    _row("BNR.XETRA", "Brenntag", "Distribution chimique", "XETRA", "BNR.DE"),
    _row("P911.XETRA", "Porsche AG", "Automobile", "XETRA", "P911.DE"),
    _row("PAH3.XETRA", "Porsche SE", "Holding auto", "XETRA", "PAH3.DE"),
    _row("SRT3.XETRA", "Sartorius", "Biotechnologie", "XETRA", "SRT3.DE"),
]

_FTSE100_COMPONENTS: list[dict[str, Any]] = [
    _row("AZN.LSE", "AstraZeneca", "Santé & Pharma", "LSE", "AZN.L"),
    _row("SHEL.LSE", "Shell", "Énergie", "LSE", "SHEL.L"),
    _row("HSBA.LSE", "HSBC Holdings", "Finance & Banque", "LSE", "HSBA.L"),
    _row("ULVR.LSE", "Unilever", "Consommation de base", "LSE", "ULVR.L"),
    _row("REL.LSE", "RELX", "Information & Data", "LSE", "REL.L"),
    _row("BP.LSE", "BP", "Énergie", "LSE", "BP.L"),
    _row("RIO.LSE", "Rio Tinto", "Mines & Matériaux", "LSE", "RIO.L"),
    _row("GSK.LSE", "GSK", "Santé & Pharma", "LSE", "GSK.L"),
    _row("RR.LSE", "Rolls-Royce Holdings", "Aéronautique", "LSE", "RR.L"),
    _row("BATS.LSE", "British American Tobacco", "Consommation de base", "LSE", "BATS.L"),
    _row("DGE.LSE", "Diageo", "Boissons & Spiritueux", "LSE", "DGE.L"),
    _row("LSEG.LSE", "London Stock Exchange Group", "Marchés financiers", "LSE", "LSEG.L"),
    _row("GLEN.LSE", "Glencore", "Matières premières", "LSE", "GLEN.L"),
    _row("BA.LSE", "BAE Systems", "Défense", "LSE", "BA.L"),
    _row("BARC.LSE", "Barclays", "Finance & Banque", "LSE", "BARC.L"),
    _row("LLOY.LSE", "Lloyds Banking Group", "Finance & Banque", "LSE", "LLOY.L"),
    _row("NWG.LSE", "NatWest Group", "Finance & Banque", "LSE", "NWG.L"),
    _row("NG.LSE", "National Grid", "Services aux collectivités", "LSE", "NG.L"),
    _row("CPG.LSE", "Compass Group", "Services", "LSE", "CPG.L"),
    _row("EXPN.LSE", "Experian", "Data & Crédit", "LSE", "EXPN.L"),
    _row("PRU.LSE", "Prudential", "Assurance", "LSE", "PRU.L"),
    _row("TSCO.LSE", "Tesco", "Distribution", "LSE", "TSCO.L"),
    _row("VOD.LSE", "Vodafone Group", "Télécommunications", "LSE", "VOD.L"),
    _row("AAL.LSE", "Anglo American", "Mines & Matériaux", "LSE", "AAL.L"),
    _row("HLN.LSE", "Haleon", "Santé grand public", "LSE", "HLN.L"),
]

_SMI20_COMPONENTS: list[dict[str, Any]] = [
    _row("NESN.SW", "Nestlé", "Agroalimentaire", "SW"),
    _row("ROG.SW", "Roche Holding", "Santé & Pharma", "SW"),
    _row("NOVN.SW", "Novartis", "Santé & Pharma", "SW"),
    _row("ABBN.SW", "ABB", "Industrie & Robotique", "SW"),
    _row("UBSG.SW", "UBS Group", "Finance & Banque", "SW"),
    _row("ZURN.SW", "Zurich Insurance Group", "Assurance", "SW"),
    _row("CFR.SW", "Richemont", "Luxe", "SW"),
    _row("SREN.SW", "Swiss Re", "Réassurance", "SW"),
    _row("SIKA.SW", "Sika", "Matériaux & Chimie", "SW"),
    _row("ALCN.SW", "Alcon", "MedTech & Ophtalmologie", "SW"),
    _row("HOLN.SW", "Holcim", "Matériaux de construction", "SW"),
    _row("LONN.SW", "Lonza Group", "Biotechnologie", "SW"),
    _row("GIVN.SW", "Givaudan", "Arômes & Parfums", "SW"),
    _row("PGHN.SW", "Partners Group", "Capital-investissement", "SW"),
    _row("SCMN.SW", "Swisscom", "Télécommunications", "SW"),
    _row("GEBN.SW", "Geberit", "Équipements sanitaires", "SW"),
    _row("SLHN.SW", "Swiss Life Holding", "Assurance", "SW"),
    _row("SOON.SW", "Sonova", "MedTech", "SW"),
    _row("KNIN.SW", "Kuehne + Nagel", "Logistique", "SW"),
    _row("LOGN.SW", "Logitech", "Périphériques informatiques", "SW"),
]

_NIKKEI225_COMPONENTS: list[dict[str, Any]] = [
    _row("7203.T", "Toyota Motor", "Automobile", "T"),
    _row("6758.T", "Sony Group", "Électronique & Divertissement", "T"),
    _row("9983.T", "Fast Retailing (Uniqlo)", "Distribution", "T"),
    _row("8035.T", "Tokyo Electron", "Semi-conducteurs", "T"),
    _row("9984.T", "SoftBank Group", "Technologie & Investissement", "T"),
    _row("6861.T", "Keyence", "Automatisation", "T"),
    _row("8306.T", "Mitsubishi UFJ Financial", "Finance & Banque", "T"),
    _row("6857.T", "Advantest", "Semi-conducteurs", "T"),
    _row("6501.T", "Hitachi", "Industrie & IT", "T"),
    _row("4063.T", "Shin-Etsu Chemical", "Matériaux & Semi-conducteurs", "T"),
    _row("9432.T", "NTT", "Télécommunications", "T"),
    _row("9433.T", "KDDI", "Télécommunications", "T"),
    _row("4519.T", "Chugai Pharmaceutical", "Santé & Pharma", "T"),
    _row("7974.T", "Nintendo", "Jeux vidéo", "T"),
    _row("6098.T", "Recruit Holdings", "Services RH & Tech", "T"),
    _row("8058.T", "Mitsubishi Corp.", "Négoce & Industrie", "T"),
    _row("8001.T", "ITOCHU", "Négoce & Industrie", "T"),
    _row("4568.T", "Daiichi Sankyo", "Santé & Pharma", "T"),
    _row("6367.T", "Daikin Industries", "Industrie", "T"),
    _row("7267.T", "Honda Motor", "Automobile", "T"),
]

_CACNEXT20_COMPONENTS: list[dict[str, Any]] = [
    _row("AKE.PA", "Arkema", "Chimie", "PA"),
    _row("AM.PA", "Dassault Aviation", "Défense & Aérospatiale", "PA"),
    _row("BIM.PA", "BioMérieux", "Santé & Diagnostics", "PA"),
    _row("BOL.PA", "Bolloré", "Conglomérat & Médias", "PA"),
    _row("ENX.PA", "Euronext", "Marchés financiers", "PA"),
    _row("FGR.PA", "Eiffage", "Construction & Concessions", "PA"),
    _row("FR.PA", "Valeo", "Équipementier auto", "PA"),
    _row("GFC.PA", "Gecina", "Immobilier", "PA"),
    _row("GET.PA", "Getlink", "Infrastructures", "PA"),
    _row("IPN.PA", "Ipsen", "Santé & Pharma", "PA"),
    _row("LI.PA", "Klépierre", "Immobilier commercial", "PA"),
    _row("NEX.PA", "Nexans", "Câbles & Électrification", "PA"),
    _row("RXL.PA", "Rexel", "Distribution électrique", "PA"),
    _row("SCR.PA", "SCOR", "Réassurance", "PA"),
    _row("SK.PA", "SEB", "Équipement domestique", "PA"),
    _row("SOI.PA", "Soitec", "Semi-conducteurs", "PA"),
    _row("SOP.PA", "Sopra Steria Group", "Services IT", "PA"),
    _row("SPIE.PA", "SPIE", "Services multi-techniques", "PA"),
    _row("SW.PA", "Sodexo", "Services", "PA"),
    _row("VIV.PA", "Vivendi", "Médias", "PA"),
]

_CACMID_EXTRA_COMPONENTS: list[dict[str, Any]] = [
    _row("ADP.PA", "Aéroports de Paris", "Infrastructures", "PA"),
    _row("AF.PA", "Air France-KLM", "Transport aérien", "PA"),
    _row("ALO.PA", "Alstom", "Transport ferroviaire", "PA"),
    _row("AMUN.PA", "Amundi", "Gestion d'actifs", "PA"),
    _row("ATE.PA", "Alten", "Ingénierie & IT", "PA"),
    _row("ATO.PA", "Atos", "Services IT", "PA"),
    _row("AYV.PA", "Ayvens", "Mobilité", "PA"),
    _row("BB.PA", "Société BIC", "Biens de consommation", "PA"),
    _row("BEN.PA", "Bénéteau", "Nautisme", "PA"),
    _row("COFA.PA", "Coface", "Assurance-crédit", "PA"),
    _row("COV.PA", "Covivio", "Immobilier", "PA"),
    _row("DBG.PA", "Derichebourg", "Recyclage & Services", "PA"),
    _row("DEC.PA", "JCDecaux", "Publicité extérieure", "PA"),
    _row("ELIOR.PA", "Elior Group", "Restauration collective", "PA"),
    _row("ELIS.PA", "Elis", "Services industriels", "PA"),
    _row("ERA.PA", "Eramet", "Mines & Métallurgie", "PA"),
    _row("ES.PA", "Esso", "Énergie", "PA"),
    _row("EXA.PA", "Exail Technologies", "Défense & Robotique", "PA"),
    _row("FDJ.PA", "FDJ United", "Jeux & Services", "PA"),
    _row("FNAC.PA", "Fnac Darty", "Distribution", "PA"),
    _row("FRVIA.PA", "Forvia", "Équipementier auto", "PA"),
    _row("GTT.PA", "GTT (Gaztransport & Technigaz)", "Énergie & Ingénierie", "PA"),
    _row("ICAD.PA", "Icade", "Immobilier", "PA"),
    _row("NK.PA", "Imerys", "Matériaux & Minéraux", "PA"),
    _row("IPS.PA", "Ipsos", "Études de marché", "PA"),
    _row("MMB.PA", "Lagardère", "Médias & Distribution", "PA"),
    _row("MAU.PA", "Maurel & Prom", "Énergie", "PA"),
    _row("MF.PA", "Wendel", "Investissement", "PA"),
    _row("NXI.PA", "Nexity", "Immobilier", "PA"),
    _row("OPM.PA", "OPmobility", "Équipementier auto", "PA"),
    _row("OVH.PA", "OVHcloud", "Cloud & Hébergement", "PA"),
    _row("PLX.PA", "Pluxee", "Services aux entreprises", "PA"),
    _row("RCO.PA", "Rémy Cointreau", "Boissons & Spiritueux", "PA"),
    _row("RF.PA", "Eurazeo", "Capital-investissement", "PA"),
    _row("RUI.PA", "Rubis", "Énergie & Logistique", "PA"),
    _row("SESG.PA", "SES", "Satellites & Télécoms", "PA"),
    _row("TRI.PA", "Trigano", "Loisirs", "PA"),
    _row("UBI.PA", "Ubisoft", "Jeux vidéo", "PA"),
    _row("VK.PA", "Vallourec", "Industrie & Énergie", "PA"),
    _row("VCT.PA", "Vicat", "Matériaux de construction", "PA"),
    _row("VIRP.PA", "Virbac", "Santé animale", "PA"),
    _row("VLA.PA", "Valneva", "Biotechnologie", "PA"),
    _row("VU.PA", "VusionGroup", "Technologie & Retail", "PA"),
    _row("WLN.PA", "Worldline", "Paiements", "PA"),
]

_AEX25_COMPONENTS: list[dict[str, Any]] = [
    _row("ASML.AS", "ASML Holding", "Semi-conducteurs", "AS"),
    _row("SHELL.AS", "Shell", "Énergie", "AS"),
    _row("UNA.AS", "Unilever", "Consommation de base", "AS"),
    _row("REL.AS", "RELX", "Information & Data", "AS"),
    _row("PRX.AS", "Prosus", "Technologie", "AS"),
    _row("INGA.AS", "ING Groep", "Finance & Banque", "AS"),
    _row("ADYEN.AS", "Adyen", "Paiements", "AS"),
    _row("AD.AS", "Ahold Delhaize", "Distribution", "AS"),
    _row("ASM.AS", "ASM International", "Semi-conducteurs", "AS"),
    _row("BESI.AS", "BE Semiconductor Industries", "Semi-conducteurs", "AS"),
    _row("WKL.AS", "Wolters Kluwer", "Logiciels & Information", "AS"),
    _row("HEIA.AS", "Heineken", "Boissons", "AS"),
    _row("DSFIR.AS", "DSM-Firmenich", "Chimie & Nutrition", "AS"),
    _row("PHIA.AS", "Philips", "MedTech", "AS"),
    _row("NN.AS", "NN Group", "Assurance", "AS"),
    _row("ASRNL.AS", "ASR Nederland", "Assurance", "AS"),
    _row("AGN.AS", "Aegon", "Assurance", "AS"),
    _row("AKZA.AS", "AkzoNobel", "Chimie", "AS"),
    _row("KPN.AS", "KPN", "Télécommunications", "AS"),
    _row("IMCD.AS", "IMCD", "Distribution chimique", "AS"),
    _row("RAND.AS", "Randstad", "Services RH", "AS"),
    _row("UMG.AS", "Universal Music Group", "Médias & Musique", "AS"),
    _row("EXO.AS", "Exor", "Investissement", "AS"),
    _row("ABN.AS", "ABN AMRO Bank", "Finance & Banque", "AS"),
    _row("MT.AS", "ArcelorMittal", "Matériaux", "AS"),
]

_BEL20_COMPONENTS: list[dict[str, Any]] = [
    _row("ABI.BR", "AB InBev", "Boissons", "BR"),
    _row("ARGX.BR", "argenx", "Biotechnologie", "BR"),
    _row("UCB.BR", "UCB", "Santé & Pharma", "BR"),
    _row("KBC.BR", "KBC Group", "Finance & Banque", "BR"),
    _row("AGEAS.BR", "Ageas", "Assurance", "BR"),
    _row("SOLB.BR", "Solvay", "Chimie", "BR"),
    _row("SYENS.BR", "Syensqo", "Chimie de spécialité", "BR"),
    _row("UMI.BR", "Umicore", "Matériaux", "BR"),
    _row("ACKB.BR", "Ackermans & van Haaren", "Investissement", "BR"),
    _row("GBLB.BR", "GBL", "Investissement", "BR"),
    _row("SOF.BR", "Sofina", "Investissement", "BR"),
    _row("WDP.BR", "Warehouses De Pauw", "Immobilier logistique", "BR"),
    _row("AED.BR", "Aedifica", "Immobilier santé", "BR"),
    _row("COFB.BR", "Cofinimmo", "Immobilier", "BR"),
    _row("ELI.BR", "Elia Group", "Réseaux électriques", "BR"),
    _row("DIE.BR", "D'Ieteren Group", "Distribution & Services", "BR"),
    _row("LOTB.BR", "Lotus Bakeries", "Agroalimentaire", "BR"),
    _row("MELE.BR", "Melexis", "Semi-conducteurs", "BR"),
    _row("GLPG.BR", "Galapagos", "Biotechnologie", "BR"),
    _row("PROX.BR", "Proximus", "Télécommunications", "BR"),
]

_IBEX35_COMPONENTS: list[dict[str, Any]] = [
    _row("ITX.MC", "Inditex", "Distribution", "MC"),
    _row("IBE.MC", "Iberdrola", "Services aux collectivités", "MC"),
    _row("SAN.MC", "Banco Santander", "Finance & Banque", "MC"),
    _row("BBVA.MC", "BBVA", "Finance & Banque", "MC"),
    _row("CABK.MC", "CaixaBank", "Finance & Banque", "MC"),
    _row("AMS.MC", "Amadeus IT Group", "Technologie voyage", "MC"),
    _row("FER.MC", "Ferrovial", "Infrastructures", "MC"),
    _row("TEF.MC", "Telefónica", "Télécommunications", "MC"),
    _row("REP.MC", "Repsol", "Énergie", "MC"),
    _row("NTGY.MC", "Naturgy Energy Group", "Énergie", "MC"),
    _row("CLNX.MC", "Cellnex Telecom", "Infrastructures télécoms", "MC"),
    _row("AENA.MC", "Aena", "Aéroports", "MC"),
    _row("ACS.MC", "ACS", "Construction", "MC"),
    _row("IAG.MC", "IAG (International Airlines)", "Transport aérien", "MC"),
    _row("SAB.MC", "Banco de Sabadell", "Finance & Banque", "MC"),
    _row("BKT.MC", "Bankinter", "Finance & Banque", "MC"),
    _row("MAP.MC", "Mapfre", "Assurance", "MC"),
    _row("RED.MC", "Redeia", "Réseaux électriques", "MC"),
    _row("ENG.MC", "Enagás", "Infrastructures gaz", "MC"),
    _row("GRF.MC", "Grifols", "Santé & Pharma", "MC"),
    _row("IDR.MC", "Indra Sistemas", "Défense & IT", "MC"),
    _row("PUIG.MC", "Puig Brands", "Luxe & Beauté", "MC"),
]

_FTSEMIB_COMPONENTS: list[dict[str, Any]] = [
    _row("UCG.MI", "UniCredit", "Finance & Banque", "MI"),
    _row("ISP.MI", "Intesa Sanpaolo", "Finance & Banque", "MI"),
    _row("ENEL.MI", "Enel", "Services aux collectivités", "MI"),
    _row("RACE.MI", "Ferrari", "Automobile & Luxe", "MI"),
    _row("ENI.MI", "Eni", "Énergie", "MI"),
    _row("G.MI", "Assicurazioni Generali", "Assurance", "MI"),
    _row("STLAM.MI", "Stellantis", "Automobile", "MI"),
    _row("STMMI.MI", "STMicroelectronics", "Semi-conducteurs", "MI"),
    _row("LDO.MI", "Leonardo", "Défense & Aérospatiale", "MI"),
    _row("PRY.MI", "Prysmian", "Câbles & Électrification", "MI"),
    _row("MONC.MI", "Moncler", "Luxe", "MI"),
    _row("TRN.MI", "Terna", "Réseaux électriques", "MI"),
    _row("SRG.MI", "Snam", "Infrastructures gaz", "MI"),
    _row("PST.MI", "Poste Italiane", "Services financiers & Postaux", "MI"),
    _row("FBK.MI", "FinecoBank", "Finance & Banque", "MI"),
    _row("BMED.MI", "Banca Mediolanum", "Finance", "MI"),
    _row("TEN.MI", "Tenaris", "Industrie & Énergie", "MI"),
    _row("CPR.MI", "Campari", "Boissons", "MI"),
    _row("AMP.MI", "Amplifon", "MedTech", "MI"),
    _row("REC.MI", "Recordati", "Santé & Pharma", "MI"),
]

_MDAX_COMPONENTS: list[dict[str, Any]] = [
    _row("LHA.XETRA", "Deutsche Lufthansa", "Transport aérien", "XETRA", "LHA.DE"),
    _row("PUM.XETRA", "Puma", "Équipement sportif", "XETRA", "PUM.DE"),
    _row("HLE.XETRA", "Hella", "Équipementier auto", "XETRA", "HLE.DE"),
    _row("GXI.XETRA", "Gerresheimer", "Santé & Emballage", "XETRA", "GXI.DE"),
    _row("BOSS.XETRA", "Hugo Boss", "Mode & Luxe", "XETRA", "BOSS.DE"),
    _row("FPE3.XETRA", "Fuchs", "Chimie & Lubrifiants", "XETRA", "FPE3.DE"),
    _row("EVK.XETRA", "Evonik Industries", "Chimie", "XETRA", "EVK.DE"),
    _row("LXS.XETRA", "Lanxess", "Chimie", "XETRA", "LXS.DE"),
    _row("LEG.XETRA", "LEG Immobilien", "Immobilier", "XETRA", "LEG.DE"),
    _row("KRN.XETRA", "Krones", "Machines industrielles", "XETRA", "KRN.DE"),
    _row("KGX.XETRA", "Kion Group", "Logistique & Industrie", "XETRA", "KGX.DE"),
    _row("TKA.XETRA", "Thyssenkrupp", "Industrie & Acier", "XETRA", "TKA.DE"),
    _row("AFX.XETRA", "Carl Zeiss Meditec", "MedTech", "XETRA", "AFX.DE"),
    _row("NEM.XETRA", "Nemetschek", "Logiciels BTP", "XETRA", "NEM.DE"),
    _row("TMV.XETRA", "TeamViewer", "Logiciels", "XETRA", "TMV.DE"),
    _row("DHER.XETRA", "Delivery Hero", "Livraison", "XETRA", "DHER.DE"),
    _row("HFG.XETRA", "HelloFresh", "Agroalimentaire", "XETRA", "HFG.DE"),
    _row("UN0.XETRA", "Uniper", "Énergie", "XETRA", "UN0.DE"),
    _row("NDX1.XETRA", "Nordex", "Énergie éolienne", "XETRA", "NDX1.DE"),
    _row("HAG.XETRA", "Hensoldt", "Défense & Capteurs", "XETRA", "HAG.DE"),
]

_RUT_FALLBACK_COMPONENTS: list[dict[str, Any]] = [
    _row("SMCI.US", "Super Micro Computer", "Serveurs & IA", "US"),
    _row("IONQ.US", "IonQ", "Informatique quantique", "US"),
    _row("RKLB.US", "Rocket Lab USA", "Aérospatiale", "US"),
    _row("ASTS.US", "AST SpaceMobile", "Télécommunications", "US"),
    _row("LUNR.US", "Intuitive Machines", "Aérospatiale", "US"),
    _row("SOUN.US", "SoundHound AI", "Logiciels & IA", "US"),
    _row("KTOS.US", "Kratos Defense", "Défense", "US"),
    _row("AVAV.US", "AeroVironment", "Défense & Drones", "US"),
    _row("CRSP.US", "CRISPR Therapeutics", "Biotechnologie", "US"),
    _row("HALO.US", "Halozyme Therapeutics", "Biotechnologie", "US"),
    _row("FN.US", "Fabrinet", "Électronique & Optique", "US"),
    _row("SPSC.US", "SPS Commerce", "Logiciels SaaS", "US"),
    _row("PI.US", "Impinj", "Semi-conducteurs", "US"),
    _row("RMBS.US", "Rambus", "Semi-conducteurs", "US"),
    _row("LFUS.US", "Littelfuse", "Composants électroniques", "US"),
    _row("BOOT.US", "Boot Barn Holdings", "Distribution", "US"),
    _row("TXRH.US", "Texas Roadhouse", "Restauration", "US"),
    _row("WING.US", "Wingstop", "Restauration", "US"),
    _row("MATX.US", "Matson", "Transport maritime", "US"),
    _row("MOD.US", "Modine Manufacturing", "Industrie thermique", "US"),
]

_FALLBACK_CONSTITUENTS: dict[str, list[dict[str, Any]]] = {
    "CAC40": _CAC40_COMPONENTS,
    "SP500": _SP500_FALLBACK_COMPONENTS,
    "NASDAQ100": _NASDAQ100_COMPONENTS,
    "DJI": _DJI_COMPONENTS,
    "EUROSTOXX50": _EUROSTOXX50_COMPONENTS,
    "DAX40": _DAX40_COMPONENTS,
    "FTSE100": _FTSE100_COMPONENTS,
    "SMI20": _SMI20_COMPONENTS,
    "NIKKEI225": _NIKKEI225_COMPONENTS,
    "CACNEXT20": _CACNEXT20_COMPONENTS,
    "CACMID60": _CACMID_EXTRA_COMPONENTS,
    "SBF120": _CAC40_COMPONENTS + _CACNEXT20_COMPONENTS + _CACMID_EXTRA_COMPONENTS,
    "AEX25": _AEX25_COMPONENTS,
    "BEL20": _BEL20_COMPONENTS,
    "IBEX35": _IBEX35_COMPONENTS,
    "FTSEMIB": _FTSEMIB_COMPONENTS,
    "MDAX": _MDAX_COMPONENTS,
    "RUT": _RUT_FALLBACK_COMPONENTS,
}


async def _fetch_eodhd_index_components(
    client: httpx.AsyncClient,
    eod_ticker: str,
    api_key: str,
) -> list[dict[str, Any]]:
    """Interroge `/api/fundamentals/{eod_ticker}` pour extraire `Components`."""
    if not api_key or not eod_ticker:
        return []
    url = (
        f"https://eodhd.com/api/fundamentals/{urllib.parse.quote(eod_ticker)}"
        f"?api_token={urllib.parse.quote(api_key)}&fmt=json"
    )
    try:
        resp = await client.get(url, timeout=14.0)
        if resp.status_code != 200:
            return []
        payload = resp.json()
        if not isinstance(payload, dict):
            return []
        raw_comp = payload.get("Components")
        items: list[dict[str, Any]] = []
        if isinstance(raw_comp, dict):
            iterable = raw_comp.values()
        elif isinstance(raw_comp, list):
            iterable = raw_comp
        else:
            return []
        for idx, entry in enumerate(iterable):
            if isinstance(entry, dict):
                norm = _normalize_eodhd_component(entry, idx)
                if norm:
                    items.append(norm)
        return items
    except Exception as exc:
        _logger.debug("EODHD index components fallback (%s): %s", eod_ticker, exc)
        return []


async def _fetch_single_index_quote(
    settings: Settings,
    defn: dict[str, Any],
    eod_key: str,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    db_path = warehouse_db_path(settings)
    code = defn["code"]
    snap = get_snapshot(db_path, defn["eod_ticker"], "index_quote", max_age_seconds=_INDEX_QUOTE_TTL_SEC)
    if snap and isinstance(snap.get("normalized"), dict):
        q = snap["normalized"]
        return {
            "last_price": q.get("last_price"),
            "change_pct": q.get("change_pct"),
            "as_of": q.get("as_of"),
            "source": snap.get("provider"),
        }

    if settings.demo_mode:
        return {"last_price": None, "change_pct": None, "as_of": None, "source": "demo"}

    last_price: float | None = None
    change_pct: float | None = None
    as_of: str | None = None
    source = "cache"

    async with sem:
        try:
            if eod_key:
                bars = await fetch_eodhd_historical_eod(client, defn["eod_ticker"], eod_key, limit=5)
                if bars:
                    latest = bars[0]
                    prev = bars[1] if len(bars) >= 2 else None
                    last_price = _safe_float(latest.get("close"))
                    prev_close = _safe_float(prev.get("close")) if prev else None
                    as_of = str(latest.get("date") or "")
                    if last_price is not None and prev_close and prev_close > 0:
                        change_pct = round(((last_price - prev_close) / prev_close) * 100.0, 2)
                    source = "EODHD"

            if last_price is None:
                chart = await fetch_yahoo_chart(client, defn["yahoo_symbol"], range_period="5d", interval="1d")
                if chart:
                    meta = chart.get("meta") or {}
                    last_price = _safe_float(meta.get("regularMarketPrice"))
                    prev_close = _safe_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
                    if last_price is not None and prev_close and prev_close > 0:
                        change_pct = round(((last_price - prev_close) / prev_close) * 100.0, 2)
                    as_of = datetime.date.today().isoformat()
                    source = "Yahoo Finance"
        except Exception as exc:
            _logger.debug("Index quote fetch ignored (%s): %s", code, exc)

    if last_price is not None:
        save_snapshot(
            db_path,
            defn["eod_ticker"],
            source,
            "index_quote",
            None,
            {"last_price": last_price, "change_pct": change_pct, "as_of": as_of},
            currency=defn["currency"],
        )

    return {
        "last_price": round(last_price, 2) if last_price is not None else None,
        "change_pct": change_pct,
        "as_of": as_of,
        "source": source,
    }


async def list_principal_indices(
    settings: Settings,
    include_quotes: bool = True,
    tier: str = "major",
) -> dict[str, Any]:
    """Retourne les indices principaux et secondaires, compteurs de composition et état de l'entrepôt."""
    db_path = warehouse_db_path(settings)
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )

    quotes_by_code: dict[str, dict[str, Any]] = {}
    if include_quotes:
        targets = [
            d for d in INDEX_DEFINITIONS
            if tier == "all" or d.get("tier") == tier or d.get("tier") == "major"
        ]
        sem = asyncio.Semaphore(6)
        async with httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
            timeout=10.0,
        ) as client:
            results = await asyncio.gather(
                *[_fetch_single_index_quote(settings, d, eod_key, client, sem) for d in targets]
            )
            for defn, q in zip(targets, results):
                quotes_by_code[defn["code"]] = q

    items: list[dict[str, Any]] = []
    for defn in INDEX_DEFINITIONS:
        code = defn["code"]
        stored, _ = get_index_constituents(db_path, code, max_age_seconds=None)
        fallback = _FALLBACK_CONSTITUENTS.get(code, [])
        count = len(stored) if stored else len(fallback)
        q = quotes_by_code.get(code, {})
        if not q and not include_quotes:
            snap = get_snapshot(db_path, defn["eod_ticker"], "index_quote", max_age_seconds=_INDEX_QUOTE_TTL_SEC)
            if snap and isinstance(snap.get("normalized"), dict):
                q = snap["normalized"]
        items.append(
            {
                **defn,
                "constituents_count": count,
                "last_price": q.get("last_price"),
                "change_pct": q.get("change_pct"),
                "as_of": q.get("as_of"),
            }
        )

    return {
        "indices": items,
        "warehouse": get_warehouse_overview(db_path),
    }


async def list_eodhd_indx_catalog(
    settings: Settings,
    query: str = "",
    limit: int = 120,
    refresh: bool = False,
) -> dict[str, Any]:
    """Récupère et filtre la liste complète des indices EODHD (`/api/exchange-symbol-list/INDX`)."""
    db_path = warehouse_db_path(settings)
    rows: list[dict[str, Any]] = []
    source = "Entrepôt SQLite"

    if not refresh:
        snap = get_snapshot(db_path, "INDX_CATALOG", "eodhd_exchange_list", max_age_seconds=_INDX_CATALOG_TTL_SEC)
        if snap and isinstance(snap.get("normalized"), list):
            rows = snap["normalized"]

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )

    if not rows and eod_key and not settings.demo_mode:
        url = f"https://eodhd.com/api/exchange-symbol-list/INDX?api_token={urllib.parse.quote(eod_key)}&fmt=json"
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
                timeout=15.0,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    raw = resp.json()
                    if isinstance(raw, list):
                        for item in raw:
                            if not isinstance(item, dict):
                                continue
                            code = str(item.get("Code") or "").strip().upper()
                            if not code:
                                continue
                            eod_ticker = code if "." in code else f"{code}.INDX"
                            rows.append(
                                {
                                    "code": eod_ticker,
                                    "eod_ticker": eod_ticker,
                                    "name": str(item.get("Name") or code).strip(),
                                    "country": str(item.get("Country") or "").strip(),
                                    "currency": str(item.get("Currency") or "").strip(),
                                    "type": str(item.get("Type") or "INDEX").strip(),
                                }
                            )
                        if rows:
                            source = "EODHD INDX API"
                            save_snapshot(db_path, "INDX_CATALOG", "EODHD", "eodhd_exchange_list", None, rows)
        except Exception as exc:
            _logger.debug("EODHD INDX catalog fallback: %s", exc)

    if not rows:
        source = "Référentiel intégré"
        rows = [
            {
                "code": d["eod_ticker"],
                "eod_ticker": d["eod_ticker"],
                "name": d["name"],
                "country": d["region"],
                "currency": d["currency"],
                "type": "INDEX",
            }
            for d in INDEX_DEFINITIONS
        ]

    needle = (query or "").strip().upper()
    if needle:
        filtered = [
            r for r in rows
            if needle in f"{r.get('code', '')} {r.get('name', '')} {r.get('country', '')}".upper()
        ]
    else:
        filtered = rows

    return {
        "total": len(rows),
        "matched": len(filtered),
        "source": source,
        "items": filtered[: max(1, min(limit, 300))],
    }


def _resolve_dynamic_index_defn(db_path: Any, code: str) -> dict[str, Any] | None:
    """Résout un code prédéfini ou un ticker EODHD `.INDX` du catalogue."""
    if code in _INDEX_BY_CODE:
        return _INDEX_BY_CODE[code]

    normalized = code if code.endswith(".INDX") else f"{code}.INDX"
    for d in INDEX_DEFINITIONS:
        if d["eod_ticker"].upper() == normalized or normalized in [a.upper() for a in d.get("eod_alt_tickers", [])]:
            return d

    # Cherche dans le catalogue EODHD mémorisé s'il existe
    snap = get_snapshot(db_path, "INDX_CATALOG", "eodhd_exchange_list", max_age_seconds=None)
    if snap and isinstance(snap.get("normalized"), list):
        for entry in snap["normalized"]:
            if isinstance(entry, dict) and str(entry.get("eod_ticker") or "").upper() == normalized:
                return {
                    "code": normalized,
                    "tier": "minor",
                    "name": str(entry.get("name") or normalized),
                    "region": str(entry.get("country") or "EODHD INDX"),
                    "flag": "🌐",
                    "currency": str(entry.get("currency") or "USD"),
                    "eod_ticker": normalized,
                    "yahoo_symbol": f"^{normalized.split('.', 1)[0]}",
                    "description": f"Indice EODHD {entry.get('name') or normalized}",
                }

    # Autorise tout ticker `.INDX` explicite (ex. `PX4.INDX`, `AEX.INDX`)
    if code.endswith(".INDX") and len(code) <= 24:
        return {
            "code": code,
            "tier": "minor",
            "name": code.replace(".INDX", ""),
            "region": "EODHD INDX",
            "flag": "🌐",
            "currency": "USD",
            "eod_ticker": code,
            "yahoo_symbol": f"^{code.split('.', 1)[0]}",
            "description": f"Indice EODHD {code}",
        }
    return None


def _extract_sparkline(
    bars: list[dict[str, Any]] | None,
    max_points: int = 30,
    window_bars: int = 66,
) -> list[float]:
    """Extrait une série miniature chronologique des derniers cours de clôture."""
    if not bars or max_points < 2:
        return []
    window = bars[-window_bars:] if window_bars > 0 else bars
    closes: list[float] = []
    for bar in window:
        raw_close = _safe_float(bar.get("close"))
        if raw_close is not None and math.isfinite(raw_close) and raw_close > 0:
            closes.append(round(raw_close, 2))
    if len(closes) <= max_points:
        return closes
    step = (len(closes) - 1) / float(max_points - 1)
    sampled = [closes[min(len(closes) - 1, round(i * step))] for i in range(max_points)]
    sampled[0] = closes[0]
    sampled[-1] = closes[-1]
    return sampled


async def get_index_composition(
    settings: Settings,
    index_code: str,
    refresh: bool = False,
) -> dict[str, Any] | None:
    """Retourne la composition complète et sélectionnable d'un indice (majeur, mineur ou `.INDX`)."""
    raw_code = (index_code or "").strip().upper()
    db_path = warehouse_db_path(settings)
    defn = _resolve_dynamic_index_defn(db_path, raw_code)
    if not defn:
        return None
    code = defn["code"]

    items: list[dict[str, Any]] = []
    source = "cache"

    if not refresh:
        stored, _ = get_index_constituents(db_path, code, max_age_seconds=_CONSTITUENTS_TTL_SEC)
        if stored:
            items = stored
            source = "Entrepôt SQLite"

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )

    if not items and eod_key and not settings.demo_mode:
        candidate_tickers = [defn["eod_ticker"], *defn.get("eod_alt_tickers", [])]
        async with httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
            timeout=14.0,
        ) as client:
            for cand in candidate_tickers:
                live_items = await _fetch_eodhd_index_components(client, cand, eod_key)
                if live_items:
                    items = live_items
                    source = f"EODHD ({cand})"
                    save_index_constituents(db_path, code, items)
                    break

    if not items:
        fallback = [dict(r, position=idx) for idx, r in enumerate(_FALLBACK_CONSTITUENTS.get(code, []))]
        items = fallback
        source = "Référentiel intégré" if items else "Indisponible sur cet indice EODHD"
        if items:
            save_index_constituents(db_path, code, items)

    cached_syms = get_cached_symbols_set(db_path)
    today_iso = datetime.date.today().isoformat()
    enriched: list[dict[str, Any]] = []
    cached_count = 0
    synced_today_count = 0
    sectors: set[str] = set()
    for item in items:
        sym = str(item.get("symbol") or "").upper()
        eod_t = str(item.get("eod_ticker") or sym).upper()
        y_t = str(item.get("yahoo_symbol") or sym).upper()
        is_cached = sym in cached_syms or eod_t in cached_syms or y_t in cached_syms
        extra_quote: dict[str, Any] = {"sparkline": []}
        if is_cached:
            cached_count += 1
            canonical = resolve_canonical_symbol(db_path, eod_t or sym)
            sync_info = get_instrument_eod_sync_info(db_path, canonical)
            if sync_info.get("eod_synced_date") == today_iso:
                synced_today_count += 1
            stored_bars = get_stored_eod_bars(db_path, canonical, limit=66)
            if stored_bars:
                closes_raw = [
                    val
                    for val in (_safe_float(b.get("close")) for b in stored_bars)
                    if val is not None and math.isfinite(val) and val > 0
                ]
                extra_quote["sparkline"] = _extract_sparkline(stored_bars)
                if closes_raw:
                    last_close = closes_raw[-1]
                    extra_quote["price"] = round(last_close, 2)
                    extra_quote["currency"] = defn.get("currency") or "EUR"
                    if len(closes_raw) >= 2 and closes_raw[-2] > 0:
                        extra_quote["change_1d_pct"] = round(
                            ((last_close - closes_raw[-2]) / closes_raw[-2]) * 100.0,
                            2,
                        )
        sec = str(item.get("sector") or "").strip()
        if sec:
            sectors.add(sec)
        enriched.append({**item, **extra_quote, "cached_in_warehouse": is_cached})

    return {
        "index": {
            **defn,
            "constituents_count": len(enriched),
            "cached_count": cached_count,
            "synced_today_count": synced_today_count,
            "source": source,
            "sectors": sorted(sectors),
        },
        "constituents": enriched,
    }


def search_finance_catalog(
    settings: Settings,
    query: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Recherche ultra-rapide dans l'entrepôt SQLite + référentiel des indices principaux."""
    clean = (query or "").strip()
    if not clean:
        return []
    db_path = warehouse_db_path(settings)
    results = search_warehouse_catalog(db_path, clean, limit=limit)
    if len(results) >= limit:
        return results

    seen = {str(r.get("eod_ticker") or r.get("symbol")).upper() for r in results}
    cached_syms = get_cached_symbols_set(db_path)

    if len(results) < limit:
        from .finance_warehouse import search_exchange_symbols

        eufund_hits = search_exchange_symbols(db_path, "EUFUND", query=clean, limit=limit - len(results))
        for r in eufund_hits.get("items") or []:
            sym = str(r.get("eod_ticker") or "").upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            results.append(
                {
                    "symbol": str(r.get("symbol") or sym),
                    "eod_ticker": sym,
                    "yahoo_symbol": sym,
                    "name": str(r.get("name") or sym),
                    "exchange": "EUFUND",
                    "sector": str(r.get("type") or "Fonds"),
                    "index_code": "EUFUND",
                    "cached": bool(r.get("cached_in_warehouse")),
                }
            )
            if len(results) >= limit:
                return results

    needle = clean.upper()
    for idx_code, rows in _FALLBACK_CONSTITUENTS.items():
        for r in rows:
            sym = str(r["eod_ticker"]).upper()
            if sym in seen:
                continue
            haystack = f"{sym} {r['yahoo_symbol']} {r['name']} {r['sector']}".upper()
            if needle in haystack:
                seen.add(sym)
                results.append(
                    {
                        "symbol": r["symbol"],
                        "eod_ticker": sym,
                        "yahoo_symbol": r["yahoo_symbol"],
                        "name": r["name"],
                        "exchange": r["exchange"],
                        "sector": r["sector"],
                        "index_code": idx_code,
                        "cached": sym in cached_syms or r["yahoo_symbol"].upper() in cached_syms,
                    }
                )
                if len(results) >= limit:
                    return results
    return results


def _yahoo_chart_to_adjusted_bars(chart: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not chart or "timestamp" not in chart:
        return []
    ts = chart.get("timestamp") or []
    ind = chart.get("indicators") or {}
    q_ind = (ind.get("quote") or [{}])[0] or {}
    adj_ind = ((ind.get("adjclose") or [{}])[0] or {}).get("adjclose") or []
    opens = q_ind.get("open") or []
    highs = q_ind.get("high") or []
    lows = q_ind.get("low") or []
    closes = q_ind.get("close") or []
    vols = q_ind.get("volume") or []
    bars: list[dict[str, Any]] = []
    for i, t_val in enumerate(ts):
        if t_val is None or i >= len(closes):
            continue
        c_val = closes[i]
        if c_val is None:
            continue
        d_str = datetime.datetime.fromtimestamp(t_val, datetime.timezone.utc).strftime("%Y-%m-%d")
        adj_bar = _to_adjusted_ohlc_bar(
            d_str,
            opens[i] if i < len(opens) else None,
            highs[i] if i < len(highs) else None,
            lows[i] if i < len(lows) else None,
            c_val,
            adj_ind[i] if i < len(adj_ind) else None,
            vols[i] if i < len(vols) else None,
        )
        if adj_bar:
            bars.append(adj_bar)
    return bars


async def get_index_performances(
    settings: Settings,
    index_code: str,
    *,
    refresh: bool = False,
    cache_only: bool = False,
    max_constituents: int = 550,
) -> dict[str, Any] | None:
    """Charge toutes les actions d'un indice en entrepôt (ou lit la BDD locale) et calcule leurs performances."""
    comp = await get_index_composition(settings, index_code, refresh=refresh and not cache_only)
    if comp is None:
        return None

    defn = comp["index"]
    constituents = list(comp["constituents"] or [])[: max(1, max_constituents)]
    db_path = warehouse_db_path(settings)
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    today_iso = datetime.date.today().isoformat()
    default_currency = str(defn.get("currency") or "EUR")
    sem = asyncio.Semaphore(10)

    async def _load_one(client: httpx.AsyncClient, item: dict[str, Any]) -> dict[str, Any]:
        eod_t = str(item.get("eod_ticker") or item.get("symbol") or "").upper()
        yahoo_t = str(item.get("yahoo_symbol") or item.get("symbol") or "").upper()
        sym = str(item.get("symbol") or eod_t).upper()
        canonical = resolve_canonical_symbol(db_path, eod_t or sym)
        sync_info = get_instrument_eod_sync_info(db_path, canonical)
        stored = get_stored_eod_bars(db_path, canonical, limit=420)
        fresh_today = is_eod_fresh_today(sync_info, min_bars_needed=380, today_iso=today_iso)

        use_local_only = cache_only or (fresh_today and not refresh)
        bars: list[dict[str, Any]] = stored if (use_local_only and stored) else []
        loaded_from_cache = bool(bars)
        source_used = "warehouse" if bars else "none"
        currency = default_currency

        if not bars and not cache_only and not settings.demo_mode:
            async with sem:
                try:
                    if eod_key and eod_t:
                        raw_eod = await fetch_eodhd_historical_eod(client, eod_t, eod_key, limit=420)
                        if raw_eod:
                            parsed: list[dict[str, Any]] = []
                            for b in reversed(raw_eod):
                                d_str = str(b.get("date") or "")[:10]
                                adj_bar = _to_adjusted_ohlc_bar(
                                    d_str,
                                    b.get("open"),
                                    b.get("high"),
                                    b.get("low"),
                                    b.get("close"),
                                    b.get("adjusted_close"),
                                    b.get("volume"),
                                )
                                if adj_bar:
                                    parsed.append(adj_bar)
                            if parsed:
                                bars = parsed
                                source_used = "eodhd"
                    if not bars and yahoo_t:
                        chart = await fetch_yahoo_chart(client, yahoo_t, range_period="2y", interval="1d")
                        if chart:
                            meta = chart.get("meta") or {}
                            if meta.get("currency"):
                                currency = str(meta["currency"]).upper()
                            y_bars = _yahoo_chart_to_adjusted_bars(chart)
                            if y_bars:
                                bars = y_bars
                                source_used = "yahoo_finance"
                except Exception as exc:
                    _logger.debug("Chargement lot indice %s (%s) ignoré: %s", index_code, sym, exc)

            if bars:
                try:
                    upsert_instrument(
                        db_path,
                        {
                            "symbol": canonical,
                            "eod_ticker": eod_t or canonical,
                            "yahoo_symbol": yahoo_t or canonical,
                            "short_name": str(item.get("name") or sym),
                            "long_name": str(item.get("name") or sym),
                            "exchange": str(item.get("exchange") or ""),
                            "currency": currency,
                            "sector": str(item.get("sector") or "") or None,
                            "industry": str(item.get("industry") or "") or None,
                        },
                    )
                    upsert_eod_bars(db_path, canonical, bars, source_used, requested_limit=420)
                    sync_info = get_instrument_eod_sync_info(db_path, canonical)
                except Exception as exc:
                    _logger.debug("Persistance lot indice %s (%s) ignorée: %s", index_code, sym, exc)

        if not bars and stored:
            bars = stored
            loaded_from_cache = True

        returns = compute_period_returns(bars)
        as_of = str(bars[-1].get("date") or "")[:10] if bars else None
        return {
            **item,
            "currency": currency,
            "price": returns["price"],
            "change_1d_pct": returns["change_1d_pct"],
            "change_1w_pct": returns["change_1w_pct"],
            "change_1m_pct": returns["change_1m_pct"],
            "change_3m_pct": returns["change_3m_pct"],
            "change_ytd_pct": returns.get("change_ytd_pct"),
            "change_1y_pct": returns["change_1y_pct"],
            "as_of": as_of,
            "bars_count": len(bars),
            "sparkline": _extract_sparkline(bars),
            "eod_synced_date": sync_info.get("eod_synced_date"),
            "eod_synced_at": sync_info.get("eod_synced_at"),
            "loaded_from_cache": loaded_from_cache,
            "cached_in_warehouse": bool(bars) or bool(item.get("cached_in_warehouse")),
        }

    async with httpx.AsyncClient(
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
        timeout=15.0,
    ) as client:
        rows = list(await asyncio.gather(*(_load_one(client, c) for c in constituents)))

    def _avg(key: str) -> float | None:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    loaded_count = sum(1 for r in rows if r.get("price") is not None)
    from_cache_count = sum(1 for r in rows if r.get("loaded_from_cache") and r.get("price") is not None)
    fetched_count = max(0, loaded_count - from_cache_count)
    synced_today_count = sum(1 for r in rows if r.get("eod_synced_date") == today_iso)
    sync_timestamps = [str(r["eod_synced_at"]) for r in rows if r.get("eod_synced_at")]
    last_synced_at = max(sync_timestamps) if sync_timestamps else None
    gainers_1d = sum(1 for r in rows if (r.get("change_1d_pct") or 0) > 0)
    losers_1d = sum(1 for r in rows if (r.get("change_1d_pct") or 0) < 0)
    gainers_1y = sum(1 for r in rows if (r.get("change_1y_pct") or 0) > 0)
    losers_1y = sum(1 for r in rows if (r.get("change_1y_pct") or 0) < 0)

    if not cache_only:
        try:
            from .finance_screener import rebuild_screener_snapshots_from_warehouse

            loaded_syms = [
                str(r.get("eod_ticker") or r.get("symbol") or "").upper()
                for r in rows
                if r.get("price") is not None
            ]
            if loaded_syms:
                rebuild_screener_snapshots_from_warehouse(db_path, loaded_syms)
        except Exception as exc:
            _logger.debug("Actualisation snapshots screener indice %s ignorée: %s", index_code, exc)

    return {
        "index": {
            **defn,
            "cached_count": sum(1 for r in rows if r.get("cached_in_warehouse")),
            "synced_today_count": synced_today_count,
        },
        "summary": {
            "total_count": len(comp["constituents"]),
            "loaded_count": loaded_count,
            "from_cache_count": from_cache_count,
            "fetched_count": fetched_count,
            "synced_today_count": synced_today_count,
            "last_synced_at": last_synced_at,
            "avg_1d_pct": _avg("change_1d_pct"),
            "avg_1w_pct": _avg("change_1w_pct"),
            "avg_1m_pct": _avg("change_1m_pct"),
            "avg_3m_pct": _avg("change_3m_pct"),
            "avg_ytd_pct": _avg("change_ytd_pct"),
            "avg_1y_pct": _avg("change_1y_pct"),
            "gainers_1d": gainers_1d,
            "losers_1d": losers_1d,
            "gainers_1y": gainers_1y,
            "losers_1y": losers_1y,
        },
        "items": rows,
        "warehouse": get_warehouse_overview(db_path),
    }
