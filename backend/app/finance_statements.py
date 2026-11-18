"""États financiers (compte de résultat, bilan, flux de trésorerie, BPA) et ratios dérivés.

Normalise vers un format canonique unique les données issues d'EOD Historical Data
(`/api/fundamentals`) et de Yahoo Finance (`fundamentals-timeseries`).
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from .config import Settings

_logger = logging.getLogger("uvicorn.error")

_TIMESERIES_URL = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,32}$")
_USER_AGENT = "Mozilla/5.0"

# (clé canonique, libellé français)
INCOME_FIELDS = [
    ("TotalRevenue", "Chiffre d'affaires"),
    ("CostOfRevenue", "Coût des ventes"),
    ("GrossProfit", "Marge brute"),
    ("ResearchAndDevelopment", "Recherche & Développement"),
    ("SellingGeneralAndAdministration", "Frais commerciaux & admin. (SG&A)"),
    ("OperatingExpense", "Charges d'exploitation"),
    ("OperatingIncome", "Résultat d'exploitation"),
    ("EBITDA", "EBITDA"),
    ("EBIT", "EBIT"),
    ("InterestExpense", "Charges d'intérêts"),
    ("PretaxIncome", "Résultat avant impôt"),
    ("TaxProvision", "Impôts"),
    ("NetIncome", "Résultat net"),
    ("DilutedEPS", "BPA dilué"),
    ("BasicEPS", "BPA de base"),
    ("DilutedAverageShares", "Actions diluées (moy.)"),
]
BALANCE_FIELDS = [
    ("TotalAssets", "Total actifs"),
    ("CurrentAssets", "Actifs courants"),
    ("CashAndCashEquivalents", "Trésorerie & équivalents"),
    ("CashCashEquivalentsAndShortTermInvestments", "Trésorerie + placements CT"),
    ("AccountsReceivable", "Créances clients"),
    ("Inventory", "Stocks"),
    ("NetPPE", "Immobilisations corporelles nettes"),
    ("GoodwillAndIntangibleAssets", "Goodwill & actifs incorporels"),
    ("TotalLiabilitiesNetMinorityInterest", "Total passifs"),
    ("CurrentLiabilities", "Passifs courants"),
    ("AccountsPayable", "Dettes fournisseurs"),
    ("ShortTermDebt", "Dette court terme"),
    ("LongTermDebt", "Dette long terme"),
    ("TotalDebt", "Dette totale"),
    ("NetDebt", "Dette nette"),
    ("StockholdersEquity", "Capitaux propres"),
    ("RetainedEarnings", "Résultats non distribués"),
    ("WorkingCapital", "Fonds de roulement"),
    ("CommonStockSharesOutstanding", "Actions en circulation"),
]
CASHFLOW_FIELDS = [
    ("OperatingCashFlow", "Flux d'exploitation"),
    ("CapitalExpenditure", "Investissements (CAPEX)"),
    ("FreeCashFlow", "Free cash flow"),
    ("DepreciationAndAmortization", "Amortissements & dépréciations"),
    ("StockBasedCompensation", "Rémunération en actions (SBC)"),
    ("ChangeInWorkingCapital", "Variation du BFR"),
    ("InvestingCashFlow", "Flux d'investissement"),
    ("FinancingCashFlow", "Flux de financement"),
    ("CashDividendsPaid", "Dividendes versés"),
    ("RepurchaseOfCapitalStock", "Rachats d'actions"),
    ("IssuanceOfDebt", "Émission / remb. net de dette"),
    ("EndCashPosition", "Trésorerie de fin de période"),
]

# Champs EODHD complémentaires (affichés en plus des postes canoniques ; vides sous Yahoo Finance)
EXTRA_EOD_INCOME_FIELDS: list[tuple[str, str]] = [
    ("eod_income_operatingExpenses", "Charges d'exploitation (brutes EOD)"),
    ("eod_income_sellingAndMarketingExpenses", "Frais commerciaux & marketing"),
    ("eod_income_generalAndAdministrativeExpenses", "Frais généraux & administratifs"),
    ("eod_income_otherOperatingExpenses", "Autres charges d'exploitation"),
    ("eod_income_reconciledDepreciation", "Amortissements réconciliés"),
    ("eod_income_depreciationAndAmortization", "Dotations aux amort. & dépréc."),
    ("eod_income_interestIncome", "Produits d'intérêts"),
    ("eod_income_netInterestIncome", "Intérêts nets"),
    ("eod_income_totalOtherIncomeExpenseNet", "Autres produits / charges nets"),
    ("eod_income_nonOperatingIncomeNetOther", "Autres résultats hors exploitation"),
    ("eod_income_netIncomeFromContinuingOps", "Résultat net des activités poursuivies"),
    ("eod_income_netIncomeApplicableToCommonShares", "Résultat net part actions ordinaires"),
    ("eod_income_minorityInterest", "Part des intérêts minoritaires (résultat)"),
    ("eod_income_discontinuedOperations", "Activités abandonnées"),
    ("eod_income_extraordinaryItems", "Éléments extraordinaires"),
    ("eod_income_effectOfAccountingCharges", "Effet des changements comptables"),
    ("eod_income_nonRecurring", "Éléments non récurrents"),
    ("eod_income_otherItems", "Autres éléments du résultat"),
    ("eod_income_preferredStockAndOtherAdjustments", "Ajustements actions préférentielles"),
]
EXTRA_EOD_BALANCE_FIELDS: list[tuple[str, str]] = [
    ("eod_balance_shortTermInvestments", "Placements à court terme"),
    ("eod_balance_otherCurrentAssets", "Autres actifs courants"),
    ("eod_balance_goodWill", "Goodwill (écart d'acquisition)"),
    ("eod_balance_intangibleAssets", "Actifs incorporels"),
    ("eod_balance_accumulatedAmortization", "Amortissements cumulés"),
    ("eod_balance_propertyPlantEquipment", "Immobilisations corporelles brutes"),
    ("eod_balance_accumulatedDepreciation", "Dépréciations cumulées"),
    ("eod_balance_longTermInvestments", "Participations & placements LT"),
    ("eod_balance_nonCurrentAssetsTotal", "Total actifs non courants"),
    ("eod_balance_otherNonCurrAssets", "Autres actifs non courants"),
    ("eod_balance_deferredLongTermAssetCharges", "Actifs d'impôts différés"),
    ("eod_balance_otherAssets", "Autres actifs"),
    ("eod_balance_shortLongTermDebt", "Dettes CT & part à moins d'1 an"),
    ("eod_balance_longTermDebtTotal", "Dette long terme totale (EOD)"),
    ("eod_balance_capitalLeaseObligationsCurrent", "Obligations locatives CT"),
    ("eod_balance_otherCurrentLiab", "Autres passifs courants"),
    ("eod_balance_capitalLeaseObligations", "Obligations de crédit-bail / location"),
    ("eod_balance_deferredLongTermLiab", "Passifs d'impôts différés LT"),
    ("eod_balance_nonCurrentLiabilitiesTotal", "Total passifs non courants"),
    ("eod_balance_otherNonCurrLiab", "Autres passifs non courants"),
    ("eod_balance_nonCurrentLiabilitiesOther", "Autres passifs non courants (détail)"),
    ("eod_balance_otherLiab", "Autres passifs"),
    ("eod_balance_noncontrollingInterestInConsolidatedEntity", "Intérêts minoritaires (bilan)"),
    ("eod_balance_minorityInterest", "Intérêts minoritaires (alt.)"),
    ("eod_balance_preferredStockTotalEquity", "Actions préférentielles"),
    ("eod_balance_preferredStockRedeemable", "Actions préférentielles rachetables"),
    ("eod_balance_commonStock", "Capital social (actions ordinaires)"),
    ("eod_balance_capitalSurpluse", "Primes d'émission"),
    ("eod_balance_additionalPaidInCapital", "Apports supplémentaires en capital"),
    ("eod_balance_treasuryStock", "Actions propres (autocontrôle)"),
    ("eod_balance_otherStockholderEquity", "Autres capitaux propres"),
    ("eod_balance_netTangibleAssets", "Actif net tangible"),
    ("eod_balance_netInvestedCapital", "Capital investi net"),
    ("eod_balance_liabilitiesAndStockholdersEquity", "Total passif & capitaux propres"),
    ("eod_balance_earningAssets", "Actifs productifs"),
]
EXTRA_EOD_CASHFLOW_FIELDS: list[tuple[str, str]] = [
    ("eod_cashflow_changeToNetincome", "Ajustements au résultat net"),
    ("eod_cashflow_changeToAccountReceivables", "Variation des créances clients"),
    ("eod_cashflow_changeToLiabilities", "Variation des dettes d'exploitation"),
    ("eod_cashflow_changeToInventory", "Variation des stocks"),
    ("eod_cashflow_changeToOperatingActivities", "Autres variations du BFR"),
    ("eod_cashflow_otherNonCashItems", "Autres éléments sans effet de trésorerie"),
    ("eod_cashflow_deferredTaxes", "Impôts différés (flux)"),
    ("eod_cashflow_investments", "Achats / cessions de placements"),
    ("eod_cashflow_otherCashflowsFromInvestingActivities", "Autres flux d'investissement"),
    ("eod_cashflow_saleOfStock", "Émission / cession d'actions"),
    ("eod_cashflow_netIssuanceOfCommonStock", "Émission nette d'actions ordinaires"),
    ("eod_cashflow_netIssuanceOfPreferredStock", "Émission nette d'actions préférentielles"),
    ("eod_cashflow_debtRepayment", "Remboursements de dette"),
    ("eod_cashflow_longTermDebtIssuance", "Émissions de dette LT"),
    ("eod_cashflow_longTermDebtPayments", "Remboursements de dette LT"),
    ("eod_cashflow_otherCashflowsFromFinancingActivities", "Autres flux de financement"),
    ("eod_cashflow_effectOfExchangeRateChanges", "Effet des variations de change"),
    ("eod_cashflow_changeInCash", "Variation nette de trésorerie"),
    ("eod_cashflow_beginPeriodCashFlow", "Trésorerie d'ouverture"),
]

_ALL_EOD_LABEL_BY_KEY: dict[str, str] = {
    key: label
    for group in (EXTRA_EOD_INCOME_FIELDS, EXTRA_EOD_BALANCE_FIELDS, EXTRA_EOD_CASHFLOW_FIELDS)
    for key, label in group
}

_STATEMENTS = {
    "income": INCOME_FIELDS,
    "balance": BALANCE_FIELDS,
    "cashflow": CASHFLOW_FIELDS,
}
_FULL_STATEMENT_FIELDS = {
    "income": [*INCOME_FIELDS, *EXTRA_EOD_INCOME_FIELDS],
    "balance": [*BALANCE_FIELDS, *EXTRA_EOD_BALANCE_FIELDS],
    "cashflow": [*CASHFLOW_FIELDS, *EXTRA_EOD_CASHFLOW_FIELDS],
}
_CANON_STMT_KEYS: dict[str, str] = {
    key: stmt_name
    for stmt_name, fields in _FULL_STATEMENT_FIELDS.items()
    for key, _ in fields
}


def infer_statement_type(metric_key: str) -> str:
    """Retourne le type d'état (`income` | `balance` | `cashflow` | `other`) d'une métrique."""
    if metric_key in _CANON_STMT_KEYS:
        return _CANON_STMT_KEYS[metric_key]
    if metric_key.startswith("eod_income_"):
        return "income"
    if metric_key.startswith("eod_balance_"):
        return "balance"
    if metric_key.startswith("eod_cashflow_"):
        return "cashflow"
    return "other"


def build_statement_type_map(series: dict[str, Any]) -> dict[str, str]:
    """Construit la table complète `{metric_key: statement_type}` pour l'entrepôt SQLite."""
    return {**_CANON_STMT_KEYS, **{k: infer_statement_type(k) for k in series.keys()}}


def _humanize_eod_field(raw_key: str) -> str:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw_key).replace("_", " ").strip()
    return spaced[:1].upper() + spaced[1:] if spaced else raw_key


# Association clé métrique -> type d'état pour l'indexation en entrepôt
STATEMENT_TYPE_BY_KEY: dict[str, str] = dict(_CANON_STMT_KEYS)

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
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.upper() in ("NA", "N/A", "NONE", "NULL", "-"):
            return None
        try:
            parsed = float(cleaned)
            return parsed if math.isfinite(parsed) else None
        except ValueError:
            return None
    return None


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


# Correspondances (clé canonique -> liste de clés EODHD par ordre de priorité)
_EOD_INCOME_MAP: list[tuple[str, tuple[str, ...]]] = [
    ("TotalRevenue", ("totalRevenue",)),
    ("CostOfRevenue", ("costOfRevenue",)),
    ("GrossProfit", ("grossProfit",)),
    ("ResearchAndDevelopment", ("researchDevelopment",)),
    ("SellingGeneralAndAdministration", ("sellingGeneralAdministrative",)),
    ("OperatingExpense", ("totalOperatingExpenses", "operatingExpenses")),
    ("OperatingIncome", ("operatingIncome",)),
    ("EBITDA", ("ebitda",)),
    ("EBIT", ("ebit", "operatingIncome")),
    ("InterestExpense", ("interestExpense",)),
    ("PretaxIncome", ("incomeBeforeTax",)),
    ("TaxProvision", ("incomeTaxExpense",)),
    ("NetIncome", ("netIncome", "netIncomeApplicableToCommonShares")),
    ("DilutedEPS", ("dilutedEPS", "epsDiluted")),
    ("BasicEPS", ("basicEPS", "eps")),
    ("DilutedAverageShares", ("weightedAverageShsOutDil", "weightedAverageShsOut", "dilutedAverageShares", "basicAverageShares")),
]

_EOD_BALANCE_MAP: list[tuple[str, tuple[str, ...]]] = [
    ("TotalAssets", ("totalAssets",)),
    ("CurrentAssets", ("totalCurrentAssets",)),
    ("CashAndCashEquivalents", ("cash", "cashAndEquivalents")),
    ("CashCashEquivalentsAndShortTermInvestments", ("cashAndShortTermInvestments", "cash")),
    ("AccountsReceivable", ("netReceivables",)),
    ("Inventory", ("inventory",)),
    ("NetPPE", ("propertyPlantAndEquipmentNet", "propertyPlantEquipmentNet", "propertyPlantEquipment")),
    ("GoodwillAndIntangibleAssets", ("goodWill",)),  # complété par goodWill + intangibleAssets ci-dessous
    ("TotalLiabilitiesNetMinorityInterest", ("totalLiab",)),
    ("CurrentLiabilities", ("totalCurrentLiabilities",)),
    ("AccountsPayable", ("accountsPayable",)),
    ("ShortTermDebt", ("shortTermDebt", "shortLongTermDebt")),
    ("LongTermDebt", ("longTermDebt", "longTermDebtTotal")),
    ("TotalDebt", ("shortLongTermDebtTotal",)),
    ("NetDebt", ("netDebt",)),
    ("StockholdersEquity", ("totalStockholderEquity",)),
    ("RetainedEarnings", ("retainedEarnings",)),
    ("WorkingCapital", ("netWorkingCapital",)),
    ("CommonStockSharesOutstanding", ("commonStockSharesOutstanding", "commonStockShares")),
]

_EOD_CASHFLOW_MAP: list[tuple[str, tuple[str, ...]]] = [
    ("OperatingCashFlow", ("totalCashFromOperatingActivities",)),
    ("CapitalExpenditure", ("capitalExpenditures",)),
    ("FreeCashFlow", ("freeCashFlow",)),
    ("DepreciationAndAmortization", ("depreciation",)),
    ("StockBasedCompensation", ("stockBasedCompensation",)),
    ("ChangeInWorkingCapital", ("changeInWorkingCapital",)),
    ("InvestingCashFlow", ("totalCashflowsFromInvestingActivities",)),
    ("FinancingCashFlow", ("totalCashFromFinancingActivities",)),
    ("CashDividendsPaid", ("dividendsPaid",)),
    ("RepurchaseOfCapitalStock", ("salePurchaseOfStock",)),
    ("IssuanceOfDebt", ("netBorrowings",)),
    ("EndCashPosition", ("endPeriodCashPosition",)),
]


def _pick_first_num(row: dict[str, Any], candidates: tuple[str, ...]) -> float | None:
    for key in candidates:
        val = _num(row.get(key))
        if val is not None:
            return val
    return None


def parse_eodhd_fundamentals_to_series(
    fundamentals: dict[str, Any],
    period_type: str,
) -> dict[str, dict[str, float | None]]:
    """Convertit un payload EODHD `/api/fundamentals` en `{clé_canonique: {date: valeur}}`."""
    if not isinstance(fundamentals, dict):
        return {}
    fin = fundamentals.get("Financials") or {}
    eod_bucket = "yearly" if period_type == "annual" else "quarterly"
    series: dict[str, dict[str, float | None]] = {}

    def ingest_section(
        section_name: str,
        stmt_type: str,
        mapping: list[tuple[str, tuple[str, ...]]],
    ) -> dict[str, dict[str, Any]]:
        section = (fin.get(section_name) or {}).get(eod_bucket) or {}
        if not isinstance(section, dict):
            return {}
        mapped_eod_fields = {eod_keys[0] for _, eod_keys in mapping if eod_keys}
        meta_fields = {"date", "filing_date", "currency_symbol"}
        for raw_date, row in section.items():
            if not isinstance(row, dict):
                continue
            d_str = str(row.get("date") or raw_date or "").strip()[:10]
            if not d_str:
                continue
            for canon_key, eod_keys in mapping:
                val = _pick_first_num(row, eod_keys)
                if val is not None:
                    series.setdefault(canon_key, {})[d_str] = val
            # Ingérer également tous les champs EODHD supplémentaires présents dans ce tableau
            for raw_key, raw_val in row.items():
                if raw_key in meta_fields or raw_key in mapped_eod_fields:
                    continue
                val = _num(raw_val)
                if val is not None:
                    extra_key = f"eod_{stmt_type}_{raw_key}"
                    series.setdefault(extra_key, {})[d_str] = val
        return section

    inc_sec = ingest_section("Income_Statement", "income", _EOD_INCOME_MAP)
    bal_sec = ingest_section("Balance_Sheet", "balance", _EOD_BALANCE_MAP)
    cf_sec = ingest_section("Cash_Flow", "cashflow", _EOD_CASHFLOW_MAP)

    # Compléments spécifiques EODHD (sommes ou dérivés manquants)
    for raw_date, row in bal_sec.items():
        if not isinstance(row, dict):
            continue
        d_str = str(row.get("date") or raw_date or "").strip()[:10]
        if not d_str:
            continue
        gw = _num(row.get("goodWill"))
        intang = _num(row.get("intangibleAssets"))
        if gw is not None:
            series.setdefault("eod_balance_goodWill", {})[d_str] = gw
        if gw is not None or intang is not None:
            series.setdefault("GoodwillAndIntangibleAssets", {})[d_str] = (gw or 0.0) + (intang or 0.0)
        if series.get("TotalDebt", {}).get(d_str) is None:
            st = _num(row.get("shortTermDebt")) or _num(row.get("shortLongTermDebt"))
            lt = _num(row.get("longTermDebt")) or _num(row.get("longTermDebtTotal"))
            if st is not None or lt is not None:
                series.setdefault("TotalDebt", {})[d_str] = (st or 0.0) + (lt or 0.0)
        if series.get("WorkingCapital", {}).get(d_str) is None:
            ca = series.get("CurrentAssets", {}).get(d_str)
            cl = series.get("CurrentLiabilities", {}).get(d_str)
            if ca is not None and cl is not None:
                series.setdefault("WorkingCapital", {})[d_str] = ca - cl
        if series.get("NetDebt", {}).get(d_str) is None:
            td = series.get("TotalDebt", {}).get(d_str)
            cash = series.get("CashAndCashEquivalents", {}).get(d_str) or series.get("CashCashEquivalentsAndShortTermInvestments", {}).get(d_str)
            if td is not None and cash is not None:
                series.setdefault("NetDebt", {})[d_str] = td - cash

    for raw_date, row in inc_sec.items():
        if not isinstance(row, dict):
            continue
        d_str = str(row.get("date") or raw_date or "").strip()[:10]
        if not d_str:
            continue
        if series.get("GrossProfit", {}).get(d_str) is None:
            rev = series.get("TotalRevenue", {}).get(d_str)
            cost = series.get("CostOfRevenue", {}).get(d_str)
            if rev is not None and cost is not None:
                series.setdefault("GrossProfit", {})[d_str] = rev - cost
        if series.get("EBITDA", {}).get(d_str) is None:
            ebit = series.get("EBIT", {}).get(d_str) or series.get("OperatingIncome", {}).get(d_str)
            da = _num(row.get("depreciationAndAmortization")) or series.get("DepreciationAndAmortization", {}).get(d_str)
            if ebit is not None and da is not None:
                series.setdefault("EBITDA", {})[d_str] = ebit + abs(da)

    for raw_date, row in cf_sec.items():
        if not isinstance(row, dict):
            continue
        d_str = str(row.get("date") or raw_date or "").strip()[:10]
        if not d_str:
            continue
        if series.get("FreeCashFlow", {}).get(d_str) is None:
            ocf = series.get("OperatingCashFlow", {}).get(d_str)
            capex = series.get("CapitalExpenditure", {}).get(d_str)
            if ocf is not None and capex is not None:
                series.setdefault("FreeCashFlow", {})[d_str] = ocf - abs(capex)

    # Enrichir DilutedEPS sur les dates d'exercices déjà présentes (évite de créer des dates orphelines -01-31 vs -01-25)
    earnings = fundamentals.get("Earnings") or {}
    existing_dates = sorted({d for vals in series.values() for d in vals.keys()})
    year_to_existing = {d[:4]: d for d in existing_dates}
    ym_to_existing = {d[:7]: d for d in existing_dates}
    if period_type == "annual":
        for raw_date, row in (earnings.get("Annual") or {}).items():
            if not isinstance(row, dict):
                continue
            d_str = str(row.get("date") or raw_date or "").strip()[:10]
            eps = _num(row.get("epsActual"))
            target_d = year_to_existing.get(d_str[:4]) if existing_dates else d_str
            if target_d and eps is not None and series.get("DilutedEPS", {}).get(target_d) is None:
                series.setdefault("DilutedEPS", {})[target_d] = eps
    else:
        for raw_date, row in (earnings.get("History") or {}).items():
            if not isinstance(row, dict):
                continue
            d_str = str(row.get("date") or raw_date or "").strip()[:10]
            eps = _num(row.get("epsActual"))
            target_d = ym_to_existing.get(d_str[:7]) if existing_dates else d_str
            if target_d and eps is not None and series.get("DilutedEPS", {}).get(target_d) is None:
                series.setdefault("DilutedEPS", {})[target_d] = eps

    # Compléter CommonStockSharesOutstanding depuis outstandingShares (souvent plus complet sur EODHD Europe)
    out_shares = fundamentals.get("outstandingShares") or {}
    share_bucket = out_shares.get("annual" if period_type == "annual" else "quarterly") or {}
    if isinstance(share_bucket, dict):
        for row in share_bucket.values():
            if not isinstance(row, dict):
                continue
            d_str = str(row.get("dateFormatted") or row.get("date") or "").strip()[:10]
            sh_val = _num(row.get("shares"))
            if not d_str or sh_val is None or sh_val <= 0:
                continue
            target_d = (year_to_existing.get(d_str[:4]) if period_type == "annual" else ym_to_existing.get(d_str[:7])) if existing_dates else d_str
            if target_d and series.get("CommonStockSharesOutstanding", {}).get(target_d) is None:
                series.setdefault("CommonStockSharesOutstanding", {})[target_d] = sh_val

    return series


def extract_eodhd_earnings_history(fundamentals: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extrait l'historique complet des publications BPA (estimé vs publié, surprise %)."""
    if not isinstance(fundamentals, dict):
        return []
    history = (fundamentals.get("Earnings") or {}).get("History") or {}
    if not isinstance(history, dict):
        return []
    rows: list[dict[str, Any]] = []
    for raw_date, item in history.items():
        if not isinstance(item, dict):
            continue
        period_date = str(item.get("date") or raw_date or "").strip()[:10]
        if not period_date:
            continue
        eps_actual = _num(item.get("epsActual"))
        eps_estimate = _num(item.get("epsEstimate"))
        eps_diff = _num(item.get("epsDifference"))
        surprise_pct = _num(item.get("surprisePercent"))
        if eps_actual is None and eps_estimate is None:
            continue
        rows.append(
            {
                "date": period_date,
                "report_date": str(item.get("reportDate") or "").strip()[:10] or None,
                "currency": str(item.get("currency") or "").strip() or None,
                "eps_actual": eps_actual,
                "eps_estimate": eps_estimate,
                "eps_difference": eps_diff,
                "surprise_pct": surprise_pct,
            }
        )
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def merge_statement_series(
    primary: dict[str, dict[str, float | None]],
    fallback: dict[str, dict[str, float | None]],
) -> dict[str, dict[str, float | None]]:
    """Fusionne deux dictionnaires de séries `{clé: {date: valeur}}` en priorisant `primary`."""
    merged: dict[str, dict[str, float | None]] = {}
    all_keys = set(primary.keys()) | set(fallback.keys())
    for key in all_keys:
        combined = dict(fallback.get(key) or {})
        for d_str, val in (primary.get(key) or {}).items():
            if val is not None:
                combined[d_str] = val
        if combined:
            merged[key] = combined
    return merged


def compute_ratios(series: dict[str, dict[str, float | None]], dates: list[str], annual: bool) -> dict[str, list[float | None]]:
    """Calcule les ratios dérivés pour chaque date (None si une donnée manque)."""

    def at(key: str, d: str) -> float | None:
        return (series.get(key) or {}).get(d)

    ratios: dict[str, list[float | None]] = {k: [] for k, _, _ in RATIO_DEFS}
    for i, d in enumerate(dates):
        rev, net = at("TotalRevenue", d), at("NetIncome", d)
        prev_rev = at("TotalRevenue", dates[i - 1]) if annual and i > 0 else None
        if not annual and i >= 4:
            # Croissance YoY trimestrielle par rapport au même trimestre N-1
            prev_rev = at("TotalRevenue", dates[i - 4])
        capex = at("CapitalExpenditure", d)
        fcf = at("FreeCashFlow", d)
        if fcf is None:
            ocf = at("OperatingCashFlow", d)
            if ocf is not None and capex is not None:
                fcf = ocf - abs(capex)
        row = {
            "revenue_growth": _div(rev - prev_rev, abs(prev_rev), True) if rev is not None and prev_rev else None,
            "gross_margin": _div(at("GrossProfit", d), rev, True),
            "operating_margin": _div(at("OperatingIncome", d), rev, True),
            "ebitda_margin": _div(at("EBITDA", d), rev, True),
            "net_margin": _div(net, rev, True),
            "fcf_margin": _div(fcf, rev, True),
            "fcf_conversion": _div(fcf, net, True),
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


def _dedupe_annual_dates(series: dict[str, dict[str, float | None]]) -> dict[str, dict[str, float | None]]:
    """Fusionne les dates multiples au sein d'une même année fiscale YYYY."""
    raw_dates = sorted({d for vals in series.values() for d, v in vals.items() if v is not None})
    if not raw_dates:
        return series
    year_to_dates: dict[str, list[str]] = {}
    for d in raw_dates:
        year_to_dates.setdefault(d[:4], []).append(d)
    if all(len(v) == 1 for v in year_to_dates.values()):
        return series
    merged: dict[str, dict[str, float | None]] = {}
    for yr in sorted(year_to_dates.keys()):
        yr_dates = year_to_dates[yr]
        canon = yr_dates[-1]
        for key, date_map in series.items():
            val: float | None = None
            for d in yr_dates:
                if date_map.get(d) is not None:
                    val = date_map[d]
            if val is not None:
                merged.setdefault(key, {})[canon] = val
    return merged


def build_period_from_series(
    series: dict[str, dict[str, float | None]],
    annual: bool,
    max_periods: int | None = None,
) -> dict[str, Any]:
    """Construit les 3 tables (postes canoniques + EODHD complets) + ratios à partir des séries."""
    if annual:
        series = _dedupe_annual_dates(series)
    dates = sorted({d for values in series.values() for d, v in values.items() if v is not None})
    if max_periods is not None and max_periods > 0:
        dates = dates[-max_periods:]
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, fields in _FULL_STATEMENT_FIELDS.items():
        prefix = f"eod_{name}_"
        known_keys = {key for key, _ in fields}
        # Garder tous les postes du schéma complet (cellules vides sous Yahoo si absent)
        rows_list: list[dict[str, Any]] = [
            {"key": key, "label": label, "values": [(series.get(key) or {}).get(d) for d in dates]}
            for key, label in fields
        ] if dates else []
        # Ajouter dynamiquement tout champ EODHD supplémentaire (banques, assurance, REIT...) présent dans les données
        dynamic_keys = sorted(
            k for k in series.keys()
            if k.startswith(prefix) and k not in known_keys and any(series[k].get(d) is not None for d in dates)
        )
        for dyn_k in dynamic_keys:
            raw_field = dyn_k[len(prefix):]
            rows_list.append({
                "key": dyn_k,
                "label": _ALL_EOD_LABEL_BY_KEY.get(dyn_k) or _humanize_eod_field(raw_field),
                "values": [(series[dyn_k].get(d)) for d in dates],
            })
        tables[name] = rows_list
    ratios = compute_ratios(series, dates, annual=annual)
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


def build_period(payload: dict[str, Any], prefix: str, max_periods: int | None = None) -> dict[str, Any]:
    """Construit les 3 tables + ratios pour une périodicité Yahoo (annuelle ou trimestrielle)."""
    series = parse_timeseries(payload, prefix)
    return build_period_from_series(series, annual=(prefix == "annual"), max_periods=max_periods)


async def _fetch_chunk(client: httpx.AsyncClient, symbol: str, type_list: list[str]) -> list[dict[str, Any]]:
    params = {"type": ",".join(type_list), "period1": 946684800, "period2": int(time.time()) + 86400}
    url = f"{_TIMESERIES_URL}{urllib.parse.quote(symbol)}?{urllib.parse.urlencode(params, safe=',')}"
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            return ((resp.json().get("timeseries") or {}).get("result") or [])
    except Exception as exc:
        _logger.warning("Erreur fundamentals-timeseries (%s): %s", symbol, exc)
    return []


async def _fetch(client: httpx.AsyncClient, symbol: str, prefix: str) -> dict[str, Any]:
    all_types = [prefix + key for fields in _STATEMENTS.values() for key, _ in fields]
    chunks = [all_types[i : i + 16] for i in range(0, len(all_types), 16)]
    chunk_results = await asyncio.gather(*(_fetch_chunk(client, symbol, ch) for ch in chunks))
    merged_results = [item for sub in chunk_results for item in sub]
    return {"timeseries": {"result": merged_results}} if merged_results else {}


async def fetch_yahoo_timeseries_bundle(symbol: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Télécharge les séries annuelles et trimestrielles brutes depuis Yahoo Finance."""
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=15.0
    ) as client:
        return await asyncio.gather(
            _fetch(client, symbol, "annual"),
            _fetch(client, symbol, "quarterly"),
        )


async def get_financial_statements(
    symbol: str,
    settings: "Settings | None" = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Renvoie les états financiers annuels et trimestriels (EODHD prioritaire + cache BDD + backup Yahoo)."""
    if settings is not None:
        from .finance_provider import get_unified_financial_statements

        return await get_unified_financial_statements(settings, symbol, refresh=refresh)

    annual, quarterly = await fetch_yahoo_timeseries_bundle(symbol)
    return {
        "symbol": symbol,
        "source_provider": "yahoo_finance",
        "source_label": "Yahoo Finance",
        "cached": False,
        "annual": build_period(annual, "annual"),
        "quarterly": build_period(quarterly, "quarterly"),
        "earnings_history": [],
    }
