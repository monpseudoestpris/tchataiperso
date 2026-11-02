"""États financiers (compte de résultat, bilan, flux de trésorerie) et ratios dérivés.

Source : endpoint public Yahoo `fundamentals-timeseries` (sans crumb).
"""

import asyncio
import logging
import re
import time
import urllib.parse
from typing import Any

import httpx

_logger = logging.getLogger("uvicorn.error")

_TIMESERIES_URL = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,20}$")
_USER_AGENT = "Mozilla/5.0"

# (clé Yahoo sans préfixe, libellé français)
INCOME_FIELDS = [
    ("TotalRevenue", "Chiffre d'affaires"),
    ("CostOfRevenue", "Coût des ventes"),
    ("GrossProfit", "Marge brute"),
    ("OperatingExpense", "Charges d'exploitation"),
    ("OperatingIncome", "Résultat d'exploitation"),
    ("EBITDA", "EBITDA"),
    ("EBIT", "EBIT"),
    ("InterestExpense", "Charges d'intérêts"),
    ("PretaxIncome", "Résultat avant impôt"),
    ("TaxProvision", "Impôts"),
    ("NetIncome", "Résultat net"),
    ("DilutedEPS", "BPA dilué"),
    ("DilutedAverageShares", "Actions diluées (moy.)"),
]
BALANCE_FIELDS = [
    ("TotalAssets", "Total actifs"),
    ("CurrentAssets", "Actifs courants"),
    ("CashAndCashEquivalents", "Trésorerie & équivalents"),
    ("CashCashEquivalentsAndShortTermInvestments", "Trésorerie + placements CT"),
    ("Inventory", "Stocks"),
    ("AccountsReceivable", "Créances clients"),
    ("TotalLiabilitiesNetMinorityInterest", "Total passifs"),
    ("CurrentLiabilities", "Passifs courants"),
    ("LongTermDebt", "Dette long terme"),
    ("TotalDebt", "Dette totale"),
    ("NetDebt", "Dette nette"),
    ("StockholdersEquity", "Capitaux propres"),
    ("WorkingCapital", "Fonds de roulement"),
]
CASHFLOW_FIELDS = [
    ("OperatingCashFlow", "Flux d'exploitation"),
    ("InvestingCashFlow", "Flux d'investissement"),
    ("FinancingCashFlow", "Flux de financement"),
    ("CapitalExpenditure", "Investissements (CAPEX)"),
    ("FreeCashFlow", "Free cash flow"),
    ("DepreciationAndAmortization", "Amortissements"),
    ("ChangeInWorkingCapital", "Variation du BFR"),
    ("CashDividendsPaid", "Dividendes versés"),
    ("RepurchaseOfCapitalStock", "Rachats d'actions"),
    ("EndCashPosition", "Trésorerie de fin de période"),
]
_STATEMENTS = {
    "income": INCOME_FIELDS,
    "balance": BALANCE_FIELDS,
    "cashflow": CASHFLOW_FIELDS,
}

# (clé, libellé, format) -> format : "pct", "x" (multiple) ou "ratio"
RATIO_DEFS = [
    ("revenue_growth", "Croissance du CA", "pct"),
    ("gross_margin", "Marge brute", "pct"),
    ("operating_margin", "Marge d'exploitation", "pct"),
    ("ebitda_margin", "Marge d'EBITDA", "pct"),
    ("net_margin", "Marge nette", "pct"),
    ("fcf_margin", "Marge de FCF", "pct"),
    ("fcf_conversion", "Conversion FCF / résultat net", "pct"),
    ("capex_to_revenue", "CAPEX / CA", "pct"),
    ("roe", "ROE (période)", "pct"),
    ("roa", "ROA (période)", "pct"),
    ("debt_to_equity", "Dette / fonds propres", "x"),
    ("net_debt_to_ebitda", "Dette nette / EBITDA", "x"),
    ("current_ratio", "Liquidité générale", "x"),
    ("interest_coverage", "Couverture des intérêts", "x"),
]


def is_valid_symbol(symbol: str) -> bool:
    """Valide un ticker avant de l'insérer dans l'URL (anti-injection de chemin/paramètres)."""
    return bool(_SYMBOL_RE.fullmatch(symbol))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _div(a: float | None, b: float | None, pct: bool = False) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return round(a / b * (100 if pct else 1), 2)


def parse_timeseries(payload: dict[str, Any], prefix: str) -> dict[str, dict[str, float | None]]:
    """Transforme la réponse Yahoo en {clé: {date: valeur}} (clé sans préfixe annual/quarterly)."""
    out: dict[str, dict[str, float | None]] = {}
    results = (payload.get("timeseries") or {}).get("result") or []
    for item in results:
        types = (item.get("meta") or {}).get("type") or []
        if not types or not types[0].startswith(prefix):
            continue
        key = types[0][len(prefix):]
        points = item.get(types[0]) or []
        out[key] = {
            p["asOfDate"]: _num((p.get("reportedValue") or {}).get("raw"))
            for p in points
            if isinstance(p, dict) and p.get("asOfDate")
        }
    return out


def compute_ratios(series: dict[str, dict[str, float | None]], dates: list[str], annual: bool) -> dict[str, list[float | None]]:
    """Calcule les ratios dérivés pour chaque date (None si une donnée manque)."""

    def at(key: str, d: str) -> float | None:
        return (series.get(key) or {}).get(d)

    ratios: dict[str, list[float | None]] = {k: [] for k, _, _ in RATIO_DEFS}
    for i, d in enumerate(dates):
        rev, net = at("TotalRevenue", d), at("NetIncome", d)
        prev_rev = at("TotalRevenue", dates[i - 1]) if annual and i > 0 else None
        capex = at("CapitalExpenditure", d)
        row = {
            "revenue_growth": _div(rev - prev_rev, abs(prev_rev), True) if rev is not None and prev_rev else None,
            "gross_margin": _div(at("GrossProfit", d), rev, True),
            "operating_margin": _div(at("OperatingIncome", d), rev, True),
            "ebitda_margin": _div(at("EBITDA", d), rev, True),
            "net_margin": _div(net, rev, True),
            "fcf_margin": _div(at("FreeCashFlow", d), rev, True),
            "fcf_conversion": _div(at("FreeCashFlow", d), net, True),
            "capex_to_revenue": _div(abs(capex) if capex is not None else None, rev, True),
            "roe": _div(net, at("StockholdersEquity", d), True),
            "roa": _div(net, at("TotalAssets", d), True),
            "debt_to_equity": _div(at("TotalDebt", d), at("StockholdersEquity", d)),
            "net_debt_to_ebitda": _div(at("NetDebt", d), at("EBITDA", d)),
            "current_ratio": _div(at("CurrentAssets", d), at("CurrentLiabilities", d)),
            "interest_coverage": _div(at("EBIT", d), abs(at("InterestExpense", d) or 0) or None),
        }
        for k, v in row.items():
            ratios[k].append(v)
    return ratios


def build_period(payload: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Construit les 3 tables + ratios pour une périodicité (annuelle ou trimestrielle)."""
    series = parse_timeseries(payload, prefix)
    dates = sorted({d for values in series.values() for d in values})[-6:]
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, fields in _STATEMENTS.items():
        tables[name] = [
            {"key": key, "label": label, "values": [(series[key].get(d)) for d in dates]}
            for key, label in fields
            if key in series and any(series[key].get(d) is not None for d in dates)
        ]
    ratios = compute_ratios(series, dates, annual=prefix == "annual")
    return {
        "dates": dates,
        "income": tables["income"],
        "balance": tables["balance"],
        "cashflow": tables["cashflow"],
        "ratios": [
            {"key": k, "label": label, "format": fmt, "values": ratios[k]}
            for k, label, fmt in RATIO_DEFS
            if any(v is not None for v in ratios[k])
        ],
    }


async def _fetch(client: httpx.AsyncClient, symbol: str, prefix: str) -> dict[str, Any]:
    types = ",".join(prefix + key for fields in _STATEMENTS.values() for key, _ in fields)
    params = {"type": types, "period1": 946684800, "period2": int(time.time()) + 86400}
    url = f"{_TIMESERIES_URL}{urllib.parse.quote(symbol)}?{urllib.parse.urlencode(params, safe=',')}"
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        _logger.warning("Erreur fundamentals-timeseries (%s, %s): %s", symbol, prefix, exc)
    return {}


async def get_financial_statements(symbol: str) -> dict[str, Any]:
    """Renvoie les états financiers annuels et trimestriels d'un ticker Yahoo."""
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=15.0
    ) as client:
        annual, quarterly = await asyncio.gather(
            _fetch(client, symbol, "annual"), _fetch(client, symbol, "quarterly")
        )
    return {
        "symbol": symbol,
        "annual": build_period(annual, "annual"),
        "quarterly": build_period(quarterly, "quarterly"),
    }
