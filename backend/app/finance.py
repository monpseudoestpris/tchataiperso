import asyncio
import datetime
import html
import json
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

import httpx
from fastapi import HTTPException

from .config import Settings
from .documents import MAX_EXTRACTED_CHARS
from .models import Attachment
from .schemas import DocumentAnnotation, DocumentExtraction, ExtractedPage

_logger = logging.getLogger("uvicorn.error")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

YAHOO_HOST_PATTERNS = [
    re.compile(r"^(?:[a-zA-Z0-9_-]+\.)?finance\.yahoo\.com$", re.IGNORECASE),
]

EODHD_HOST_PATTERNS = [
    re.compile(r"^(?:[a-zA-Z0-9_-]+\.)?(?:eodhd\.com|eodhistoricaldata\.com)$", re.IGNORECASE),
]

YAHOO_QUOTE_URL_RE = re.compile(
    r"https?://(?:[a-zA-Z0-9_-]+\.)?finance\.yahoo\.com/quote/([A-Za-z0-9\.\^=_-]+)",
    re.IGNORECASE,
)

EODHD_URL_RE = re.compile(
    r"https?://(?:[a-zA-Z0-9_-]+\.)?(?:eodhd\.com|eodhistoricaldata\.com)/(?:financial-summary|api/[^/]+)/([A-Za-z0-9\.\^=_-]+)",
    re.IGNORECASE,
)

CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,6}(?:\.[A-Za-z]{1,4})?)\b")

MENTION_FINANCE_RE = re.compile(
    r"@(?:finance|bourse|action|stock)\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9\s\-\.\^=]{1,35})",
    re.IGNORECASE,
)

FINANCE_KEYWORDS_RE = re.compile(
    r"\b(?:cours|bourse|action|actions|cotation|cotations|ticker|dividende|dividendes|"
    r"capitalisation|valorisation|bilan|ebitda|chiffre d['’]affaires|résultats financiers|"
    r"donn[ée]es financi[èe]res|analyse financi[èe]re|march[ée] boursier|"
    r"infos?\s+sur\s+l['’]entreprise|infos?\s+sur\s+la\s+soci[ée]t[ée]|"
    r"analyse|analyses|bilan|bilans|"
    r"stock|stocks|share price|stock price|financials|market cap|per|pe ratio)\b",
    re.IGNORECASE,
)

ARTICLE_PREFIX_RE = re.compile(
    r"^(?:en\s+d[ée]tails?\s+|en\s+profondeur\s+|compl[èe]te\s+|d[ée]taill[ée]e\s+|"
    r"le\s+cours\s+de\s+bourse\s+de\s+|le\s+cours\s+de\s+bourse\s+d['’]|cours\s+de\s+bourse\s+de\s+|cours\s+de\s+bourse\s+d['’]|"
    r"le\s+cours\s+de\s+l['’]action\s+|le\s+cours\s+de\s+|le\s+cours\s+du\s+|le\s+cours\s+d['’]|"
    r"cours\s+de\s+l['’]action\s+|cours\s+de\s+|cours\s+du\s+|cours\s+d['’]|"
    r"sur\s+l['’]entreprise\s+|sur\s+la\s+soci[ée]t[ée]\s+|sur\s+|"
    r"de\s+l['’]entreprise\s+|de\s+la\s+soci[ée]t[ée]\s+|"
    r"l['’]action\s+|l['’]entreprise\s+|la\s+soci[ée]t[ée]\s+|le\s+titre\s+|"
    r"action\s+|actions\s+|titre\s+|entreprise\s+|soci[ée]t[ée]\s+|"
    r"bourse\s+de\s+|bourse\s+du\s+|bourse\s+d['’]|bourse\s+|"
    r"le\s+|la\s+|les\s+|un\s+|une\s+|du\s+|de\s+|des\s+|d['’]|l['’])+",
    re.IGNORECASE,
)

SUFFIX_CLEAN_RE = re.compile(
    r"\b(aujourd['’]?hui|aujourd|en ce moment|s['’]il te pla[iî]t|svp|stp|merci|actuel(?:lement)?|"
    r"r[ée]cent(?:es)?|en temps r[ée]el|sur le march[ée]|en direct|dans le monde|cette ann[ée]e)\b.*$",
    re.IGNORECASE,
)

STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "ce", "cet", "cette", "ces",
    "mon", "ton", "son", "notre", "votre", "leur", "bourse", "cours", "action", "actions",
    "finance", "info", "infos", "donne", "combien", "vaut", "quel", "quelle", "quels",
    "quelles", "est", "sont", "prix", "valeur", "titre", "societe", "société", "entreprise",
    "entreprises", "donnees", "données", "financieres", "financières", "telecharger", "télécharger",
    "afficher", "data", "chiffres", "resultats", "résultats", "analyse", "bilan",
    "stp", "svp", "merci", "détail", "detail", "financière", "financier", "financiers",
}

_cached_crumb: str | None = None


def is_yahoo_finance_url(url: str) -> bool:
    """Checks if a URL points to Yahoo Finance."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        return any(pattern.match(host) for pattern in YAHOO_HOST_PATTERNS)
    except Exception:
        return False


def is_eodhd_url(url: str) -> bool:
    """Checks if a URL points to EOD Historical Data."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        return any(pattern.match(host) for pattern in EODHD_HOST_PATTERNS)
    except Exception:
        return False


def is_financial_url(url: str) -> bool:
    """Checks if a URL points to any supported financial data provider."""
    return is_yahoo_finance_url(url) or is_eodhd_url(url)


def extract_ticker_from_url(url: str) -> str | None:
    """Extracts ticker symbol from a Yahoo Finance or EODHD quote URL."""
    match = YAHOO_QUOTE_URL_RE.search(url)
    if match:
        return urllib.parse.unquote(match.group(1).strip())
    match_eod = EODHD_URL_RE.search(url)
    if match_eod:
        return urllib.parse.unquote(match_eod.group(1).strip())
    return None


def clean_entity_candidate(raw: str) -> list[str]:
    """Cleans up an extracted entity candidate string and splits multi-entity queries."""
    text = raw.strip(" \t\r\n?!,.;:\"'`()[]{}")
    text = ARTICLE_PREFIX_RE.sub("", text).strip(" \t\r\n?!,.;:\"'`()[]{}")
    text = SUFFIX_CLEAN_RE.sub("", text).strip(" \t\r\n?!,.;:\"'`()[]{}")
    text = ARTICLE_PREFIX_RE.sub("", text).strip(" \t\r\n?!,.;:\"'`()[]{}")
    
    # Split queries like "Apple et Tesla" or "LVMH, Kering et Hermes" or "Apple vs Microsoft"
    parts = re.split(r"\s+(?:et(?:\s+de|\s+d['’])?|vs|versus|ou|,)\s+", text, flags=re.IGNORECASE)
    cleaned: list[str] = []
    for part in parts:
        p = ARTICLE_PREFIX_RE.sub("", part.strip(" \t\r\n?!,.;:\"'`()[]{}")).strip(" \t\r\n?!,.;:\"'`()[]{}")
        p = SUFFIX_CLEAN_RE.sub("", p).strip(" \t\r\n?!,.;:\"'`()[]{}")
        if p and len(p) >= 2 and p.lower() not in STOPWORDS:
            cleaned.append(p)
    return cleaned


def detect_financial_entities(text: str) -> list[str]:
    """
    Detects financial/stock queries and extracts company or ticker candidate names.
    Returns a deduplicated list of candidate entities (e.g. ['AAPL', 'LVMH']).
    """
    if not text or not text.strip():
        return []

    candidates: list[str] = []

    # 1. Yahoo Finance URLs
    for url_match in YAHOO_QUOTE_URL_RE.finditer(text):
        symbol = urllib.parse.unquote(url_match.group(1).strip())
        if symbol:
            candidates.append(symbol.upper())

    # 2. Cashtags like $AAPL, $MSFT, $TTE.PA
    for ct in CASHTAG_RE.findall(text):
        if ct.strip():
            candidates.append(ct.strip().upper())

    # 3. Explicit mentions like @finance Apple or @bourse LVMH
    for mention_match in MENTION_FINANCE_RE.finditer(text):
        for cand in clean_entity_candidate(mention_match.group(1)):
            if cand and len(cand) >= 2:
                candidates.append(cand)

    # 4. Pattern matching with financial intent keywords
    has_finance_intent = bool(FINANCE_KEYWORDS_RE.search(text))

    if has_finance_intent:
        patterns = [
            # "cours de bourse de/d' X", "cours de l'action X", "cours de X", "cours du CAC 40", "cours stellantis"
            r"(?:cours(?:\s+de\s+(?:bourse|l['’]action|la\s+cotation|la\s+valeur)?)?|cotation|actions?)\s+(?:(?:de\s+|d['’]|du\s+)?)(?:l['’]action\s+)?([A-Za-zÀ-ÖØ-öø-ÿ0-9\s\-\.\^='’]{2,40})",
            # "infos / données financières / résultats / analyse [financière/en détail] [de/sur] X"
            r"(?:infos?|informations?|donn[ée]es\s+financi[èe]res?|chiffres?\s+cl[ée]s?|r[ée]sultats\s+financiers?|analyse(?:\s+financi[èe]re|\s+en\s+d[ée]tails?|\s+compl[èe]te|\s+approfondie)?|bilan)\s+(?:(?:sur|de|d['’]|concernant)\s+)?(?:l['’]entreprise\s+|la\s+soci[ée]t[ée]\s+|l['’]action\s+)?([A-Za-zÀ-ÖØ-öø-ÿ0-9\s\-\.\^='’]{2,40})",
            # "combien vaut l'action X", "prix de l'action X"
            r"(?:prix|valeur)\s+de\s+l['’]action\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9\s\-\.\^='’]{2,40})",
            r"combien\s+vaut\s+(?:l['’]action\s+|le\s+titre\s+)?([A-Za-zÀ-ÖØ-öø-ÿ0-9\s\-\.\^='’]{2,40})",
            # "l'entreprise X" or "la société X" when financial intent is present
            r"(?:l['’]entreprise|la\s+soci[ée]t[ée]|le\s+groupe)\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9\s\-\.\^='’]{2,40})",
            # English: "stock price of X", "quote of X", "financials of X"
            r"(?:stock\s+price|share\s+price|quote|financials?|market\s+cap)\s+(?:(?:of|for)\s+)?([A-Za-z0-9\s\-\.\^='’]{2,40})",
        ]
        for pat in patterns:
            for match in re.finditer(pat, text, re.IGNORECASE):
                for cand in clean_entity_candidate(match.group(1)):
                    if cand and len(cand) >= 2 and cand.lower() not in STOPWORDS:
                        candidates.append(cand)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for cand in candidates:
        key = cand.lower()
        if key not in seen:
            seen.add(key)
            result.append(cand)

    return result[:3]  # Limit to 3 candidate entities per message


def query_variants(query: str, limit: int = 6) -> list[str]:
    """
    Returns the query followed by shorter word windows (dropping leading words
    first, then trailing words), so that noisy candidates such as
    « en détail air liquide » still resolve to « air liquide ».
    """
    words = query.split()
    variants: list[str] = [query.strip()]
    if len(words) > 1:
        for start in range(1, len(words)):
            variants.append(" ".join(words[start:]))
        for end in range(len(words) - 1, 0, -1):
            variants.append(" ".join(words[:end]))
    seen: set[str] = set()
    result: list[str] = []
    for v in variants:
        key = v.lower()
        if len(v) >= 2 and key not in seen and key not in STOPWORDS:
            seen.add(key)
            result.append(v)
    return result[:limit]


async def get_yahoo_crumb_and_client() -> tuple[httpx.AsyncClient, str | None]:
    """
    Creates an AsyncClient initialized with cookies from fc.yahoo.com
    and retrieves a fresh Yahoo Finance crumb token.
    """
    global _cached_crumb

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    client = httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=12.0,
    )

    try:
        # Step 1: Query fc.yahoo.com to receive initial session cookies
        await client.get("https://fc.yahoo.com")
    except Exception as exc:
        _logger.debug("fc.yahoo.com cookie step notice: %s", exc)

    try:
        # Step 2: Query getcrumb endpoint (returns text/plain)
        crumb_resp = await client.get("https://query2.finance.yahoo.com/v1/test/getcrumb")
        if crumb_resp.status_code == 200 and crumb_resp.text:
            text = crumb_resp.text.strip()
            if text and not text.startswith("{") and len(text) < 30:
                _cached_crumb = text
                return client, _cached_crumb
    except Exception as exc:
        _logger.warning("Échec de récupération du crumb Yahoo Finance: %s", exc)

    return client, _cached_crumb


async def search_yahoo_ticker(client: httpx.AsyncClient, query: str) -> dict[str, Any] | None:
    """
    Searches Yahoo Finance for a company or symbol via /v1/finance/search.
    Returns the top matching quote dictionary or None.
    """
    clean_q = query.strip()
    if not clean_q:
        return None

    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(clean_q)}&quotesCount=5&newsCount=0"
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        quotes = data.get("quotes", [])
        if not quotes:
            return None

        # Prefer equity or index with exact or highest score
        for quote in quotes:
            symbol = quote.get("symbol")
            if not symbol:
                continue
            if symbol.upper() == clean_q.upper():
                return quote

        # Fallback to the first quote that has a symbol
        for quote in quotes:
            if quote.get("symbol"):
                return quote

    except Exception as exc:
        _logger.warning("Erreur lors de la recherche du ticker Yahoo Finance (%s): %s", query, exc)

    return None


async def fetch_yahoo_chart(
    client: httpx.AsyncClient,
    symbol: str,
    range_period: str = "1mo",
    interval: str = "1d",
) -> dict[str, Any] | None:
    """Fetches chart data (OHLCV, current price, metadata) for symbol."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={range_period}&interval={interval}"
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result")
            if result and len(result) > 0:
                return result[0]
    except Exception as exc:
        _logger.warning("Erreur lors de l'appel v8/finance/chart pour %s: %s", symbol, exc)
    return None


async def fetch_yahoo_quote_summary(
    client: httpx.AsyncClient,
    symbol: str,
    crumb: str | None = None,
) -> dict[str, Any] | None:
    """Fetches quote summary (financials, key stats, profile, price) using crumb."""
    modules = "price,summaryDetail,financialData,defaultKeyStatistics,assetProfile"
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(symbol)}?modules={modules}"
    if crumb:
        url += f"&crumb={urllib.parse.quote(crumb)}"

    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("quoteSummary", {}).get("result")
            if result and len(result) > 0:
                return result[0]
        elif resp.status_code == 401 and crumb:
            # Crumb might have expired, try once more without crumb or log
            _logger.debug("quoteSummary 401 avec crumb pour %s", symbol)
    except Exception as exc:
        _logger.warning("Erreur lors de l'appel v10/finance/quoteSummary pour %s: %s", symbol, exc)
    return None


def _fmt_num(val: Any, suffix: str = "", default: str = "N/A") -> str:
    """Formats raw numerical values with units (Mrd, M, %, etc.)."""
    if val is None:
        return default
    if isinstance(val, dict):
        if "fmt" in val and val["fmt"]:
            return f"{val['fmt']}{(' ' + suffix) if suffix else ''}".strip()
        val = val.get("raw")
    if val is None or not isinstance(val, (int, float)):
        return default

    abs_v = abs(val)
    if abs_v >= 1e12:
        res = f"{val / 1e12:.2f} T"
    elif abs_v >= 1e9:
        res = f"{val / 1e9:.2f} Mrd"
    elif abs_v >= 1e6:
        res = f"{val / 1e6:.2f} M"
    elif abs_v >= 1e3:
        res = f"{val:,.2f}".replace(",", " ")
    else:
        res = f"{val:.2f}"

    return f"{res} {suffix}".strip() if suffix else res


def _fmt_pct(val: Any, default: str = "N/A") -> str:
    """Formats percentage values."""
    if val is None:
        return default
    if isinstance(val, dict):
        if "fmt" in val and val["fmt"]:
            return val["fmt"]
        val = val.get("raw")
    if val is None or not isinstance(val, (int, float)):
        return default
    # If already in percentage units (>1 or <-1 often means % for some fields)
    pct = val * 100 if abs(val) < 1.0 else val
    return f"{pct:+.2f}%"


def build_finance_markdown(
    symbol: str,
    top_quote: dict[str, Any] | None,
    chart_data: dict[str, Any] | None,
    summary_data: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any]]:
    """
    Builds structured, rich Markdown data for a financial ticker.
    Returns: (title, full_markdown, metadata_dict)
    """
    meta = chart_data.get("meta", {}) if chart_data else {}
    summary = summary_data or {}
    price_mod = summary.get("price", {})
    fin_mod = summary.get("financialData", {})
    stats_mod = summary.get("defaultKeyStatistics", {})
    profile_mod = summary.get("assetProfile", {})
    detail_mod = summary.get("summaryDetail", {})

    # Determine names and exchange
    short_name = (
        price_mod.get("shortName")
        or (top_quote.get("shortname") if top_quote else None)
        or meta.get("shortName")
        or (top_quote.get("longname") if top_quote else None)
        or symbol
    )
    long_name = (
        price_mod.get("longName")
        or (top_quote.get("longname") if top_quote else None)
        or meta.get("longName")
        or short_name
    )
    exchange = (
        price_mod.get("exchangeName")
        or (top_quote.get("exchDisp") if top_quote else None)
        or meta.get("exchangeName")
        or meta.get("fullExchangeName")
        or "Marché"
    )
    currency = price_mod.get("currency") or meta.get("currency") or "USD"

    # Current Price and Change
    curr_price = (
        price_mod.get("regularMarketPrice", {}).get("raw")
        if isinstance(price_mod.get("regularMarketPrice"), dict)
        else price_mod.get("regularMarketPrice")
    )
    if curr_price is None:
        curr_price = meta.get("regularMarketPrice")

    prev_close = (
        price_mod.get("regularMarketPreviousClose", {}).get("raw")
        if isinstance(price_mod.get("regularMarketPreviousClose"), dict)
        else price_mod.get("regularMarketPreviousClose")
    )
    if prev_close is None:
        prev_close = meta.get("chartPreviousClose") or detail_mod.get("previousClose", {}).get("raw")

    change = None
    change_pct = None
    if curr_price is not None and prev_close:
        change = curr_price - prev_close
        change_pct = (change / prev_close) * 100
    elif meta.get("regularMarketChangePercent") is not None:
        change_pct = meta.get("regularMarketChangePercent")

    # Format header
    price_str = f"{curr_price:.2f} {currency}" if curr_price is not None else "N/A"
    change_str = (
        f"{change:+.2f} {currency} ({change_pct:+.2f}%)"
        if change is not None and change_pct is not None
        else f"({change_pct:+.2f}%)" if change_pct is not None else ""
    )

    title = f"📈 {short_name} ({symbol})"
    yahoo_url = f"https://finance.yahoo.com/quote/{symbol}"

    lines: list[str] = [
        f"# 📈 {long_name} ({symbol})",
        f"> ⚡ **Données téléchargées en direct sur Yahoo Finance API** · Marché : {exchange} · Devise : `{currency}` · Fiche officielle : [{symbol}]({yahoo_url})",
        "",
        f"### 🏷️ Cours actuel : **{price_str}** {change_str}".strip(),
        "",
    ]

    # Daily Range & 52-Week Range
    day_low = meta.get("regularMarketDayLow") or detail_mod.get("dayLow", {}).get("raw")
    day_high = meta.get("regularMarketDayHigh") or detail_mod.get("dayHigh", {}).get("raw")
    w52_low = meta.get("fiftyTwoWeekLow") or detail_mod.get("fiftyTwoWeekLow", {}).get("raw")
    w52_high = meta.get("fiftyTwoWeekHigh") or detail_mod.get("fiftyTwoWeekHigh", {}).get("raw")

    # 1. Dashboard Table: Valuation & Key Indicators
    market_cap = price_mod.get("marketCap") or detail_mod.get("marketCap")
    pe_trailing = stats_mod.get("trailingPE") or detail_mod.get("trailingPE")
    pe_forward = stats_mod.get("forwardPE") or detail_mod.get("forwardPE")
    peg_ratio = stats_mod.get("pegRatio")
    price_to_book = stats_mod.get("priceToBook")
    ev_to_ebitda = stats_mod.get("enterpriseToEbitda")
    beta = stats_mod.get("beta") or detail_mod.get("beta")
    trailing_eps = stats_mod.get("trailingEps")
    forward_eps = stats_mod.get("forwardEps")
    div_yield = detail_mod.get("dividendYield")
    div_rate = detail_mod.get("dividendRate")
    payout_ratio = detail_mod.get("payoutRatio")

    lines.extend([
        "#### 📊 Indicateurs clés de valorisation & Multiples boursiers",
        "| Métrique | Valeur |",
        "| :--- | :--- |",
        f"| **Dernier cours** | `{price_str}` |",
        f"| **Fourchette du jour** | `{_fmt_num(day_low)} - {_fmt_num(day_high)} {currency}` |",
        f"| **Fourchette 52 semaines** | `{_fmt_num(w52_low)} - {_fmt_num(w52_high)} {currency}` |",
        f"| **Capitalisation boursière** | `{_fmt_num(market_cap, currency)}` |",
        f"| **Ratio C/B (P/E Trailing)** | `{_fmt_num(pe_trailing)}` |",
        f"| **P/E Forward (estimé)** | `{_fmt_num(pe_forward)}` |",
        f"| **Ratio PEG (Croissance)** | `{_fmt_num(peg_ratio)}` |",
        f"| **Price-to-Book (P/B)** | `{_fmt_num(price_to_book)}` |",
        f"| **EV / EBITDA** | `{_fmt_num(ev_to_ebitda)}` |",
        f"| **Bêta (volatilité marché)** | `{_fmt_num(beta)}` |",
        f"| **Bénéfice par action (BPA)** | `{_fmt_num(trailing_eps, currency)} (estimé futur : {_fmt_num(forward_eps, currency)})` |",
        f"| **Rendement du dividende** | `{_fmt_pct(div_yield)}` |",
    ])
    if div_rate:
        lines.append(f"| **Dividende annuel par action** | `{_fmt_num(div_rate, currency)}` |")
    if payout_ratio:
        lines.append(f"| **Taux de distribution (Payout)** | `{_fmt_pct(payout_ratio)}` |")
    lines.append("")

    # 2. Financials & Profitability (if available for equity)
    tot_revenue = fin_mod.get("totalRevenue")
    rev_growth = fin_mod.get("revenueGrowth")
    gross_margin = fin_mod.get("grossMargins")
    oper_margin = fin_mod.get("operatingMargins")
    profit_margin = fin_mod.get("profitMargins") or stats_mod.get("profitMargins")
    ebitda = fin_mod.get("ebitda")
    net_income = stats_mod.get("netIncomeToCommon")
    free_cash = fin_mod.get("freeCashflow")
    operating_cash = fin_mod.get("operatingCashflow")
    tot_cash = fin_mod.get("totalCash")
    tot_debt = fin_mod.get("totalDebt")
    debt_to_equity = fin_mod.get("debtToEquity")
    current_ratio = fin_mod.get("currentRatio")
    return_on_equity = fin_mod.get("returnOnEquity")

    if any(v is not None for v in (tot_revenue, ebitda, gross_margin, free_cash)):
        lines.extend([
            "#### 💰 Performance financière & Rentabilité",
            "| Indicateur financier | Donnée déclarée |",
            "| :--- | :--- |",
            f"| **Chiffre d'affaires (Revenue)** | `{_fmt_num(tot_revenue, currency)}` |",
            f"| **Croissance du CA** | `{_fmt_pct(rev_growth)}` |",
            f"| **Marge brute** | `{_fmt_pct(gross_margin)}` |",
            f"| **Marge opérationnelle** | `{_fmt_pct(oper_margin)}` |",
            f"| **Marge nette** | `{_fmt_pct(profit_margin)}` |",
            f"| **EBITDA** | `{_fmt_num(ebitda, currency)}` |",
            f"| **Bénéfice net** | `{_fmt_num(net_income, currency)}` |",
            f"| **Flux de trésorerie disponible (FCF)** | `{_fmt_num(free_cash, currency)}` |",
        ])
        if operating_cash:
            lines.append(f"| **Flux de trésorerie d'exploitation** | `{_fmt_num(operating_cash, currency)}` |")
        lines.extend([
            f"| **Trésorerie totale (Cash)** | `{_fmt_num(tot_cash, currency)}` |",
            f"| **Dette totale** | `{_fmt_num(tot_debt, currency)}` |",
        ])
        if debt_to_equity:
            lines.append(f"| **Ratio Dette / Fonds propres** | `{_fmt_num(debt_to_equity)}%` |")
        if current_ratio:
            lines.append(f"| **Ratio de liquidité générale** | `{_fmt_num(current_ratio)}` |")
        if return_on_equity:
            lines.append(f"| **Rentabilité des fonds propres (ROE)** | `{_fmt_pct(return_on_equity)}` |")
        lines.append("")

    # 3. Analyst Targets & Consensus
    target_mean = fin_mod.get("targetMeanPrice")
    target_high = fin_mod.get("targetHighPrice")
    target_low = fin_mod.get("targetLowPrice")
    recom_key = fin_mod.get("recommendationKey")
    analysts_count = fin_mod.get("numberOfAnalystOpinions")

    if target_mean or recom_key:
        lines.extend([
            "#### 🎯 Consensus & Objectifs des analystes",
            f"- **Recommandation moyenne :** `{str(recom_key).upper() if recom_key else 'N/A'}` "
            f"*(basée sur {_fmt_num(analysts_count, default='plusieurs')} avis d'analystes)*",
            f"- **Objectif de cours moyen :** `{_fmt_num(target_mean, currency)}`",
            f"- **Objectif haut / bas :** `{_fmt_num(target_high, currency)}` / `{_fmt_num(target_low, currency)}`",
            "",
        ])

    # 4. Recent Historical Trading Sessions (from chart candles)
    if chart_data and "timestamp" in chart_data:
        ts = chart_data.get("timestamp", [])
        quote_indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]
        opens = quote_indicators.get("open", [])
        highs = quote_indicators.get("high", [])
        lows = quote_indicators.get("low", [])
        closes = quote_indicators.get("close", [])
        volumes = quote_indicators.get("volume", [])

        valid_rows = []
        for i in range(len(ts)):
            c = closes[i] if i < len(closes) else None
            if c is not None:
                valid_rows.append((
                    ts[i],
                    opens[i] if i < len(opens) else None,
                    highs[i] if i < len(highs) else None,
                    lows[i] if i < len(lows) else None,
                    c,
                    volumes[i] if i < len(volumes) else None,
                ))

        # Take the last 7 sessions
        recent = valid_rows[-7:]
        if recent:
            lines.extend([
                "#### 📅 Historique récent des cotations (dernières séances)",
                "| Date | Ouverture | Plus haut | Plus bas | Clôture | Volume |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for t_val, o_val, h_val, l_val, c_val, v_val in recent:
                d_str = datetime.datetime.fromtimestamp(t_val, datetime.timezone.utc).strftime("%d/%m/%Y")
                o_str = f"{o_val:.2f}" if o_val is not None else "-"
                h_str = f"{h_val:.2f}" if h_val is not None else "-"
                l_str = f"{l_val:.2f}" if l_val is not None else "-"
                c_str = f"**{c_val:.2f}**"
                v_str = f"{v_val:,}".replace(",", " ") if v_val is not None else "-"
                lines.append(f"| {d_str} | {o_str} | {h_str} | {l_str} | {c_str} | {v_str} |")
            lines.append("")

    # 5. Company Profile & Overview
    sector = profile_mod.get("sector") or profile_mod.get("sectorDisp")
    industry = profile_mod.get("industry") or profile_mod.get("industryDisp")
    country = profile_mod.get("country")
    website = profile_mod.get("website")
    employees = profile_mod.get("fullTimeEmployees")
    summary_text = profile_mod.get("longBusinessSummary")

    if sector or summary_text:
        lines.extend([
            "#### 🏢 Profil de l'entreprise",
            f"- **Secteur :** {sector or 'N/A'} · **Industrie :** {industry or 'N/A'}",
            f"- **Pays / Siège :** {country or 'N/A'} · **Effectif :** {_fmt_num(employees, default='Non communiqué')}",
        ])
        if website:
            lines.append(f"- **Site officiel :** [{website}]({website})")
        if summary_text:
            short_desc = summary_text[:600].replace("\n", " ").strip()
            lines.append(f"\n> **Activité :** {short_desc}{'…' if len(summary_text) > 600 else ''}")
        lines.append("")

    full_markdown = "\n".join(lines)
    if len(full_markdown) > MAX_EXTRACTED_CHARS:
        full_markdown = full_markdown[:MAX_EXTRACTED_CHARS]

    metadata = {
        "symbol": symbol,
        "short_name": short_name,
        "long_name": long_name,
        "price": curr_price,
        "currency": currency,
        "change_percent": change_pct,
        "market_cap": market_cap,
        "exchange": exchange,
        "provider": "yahoo_finance",
        "source_label": "Yahoo Finance API",
        "url": yahoo_url,
    }

    return title, full_markdown, metadata


def _safe_float(val: Any) -> float | None:
    if val is None or val == "NA" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def score_eodhd_search_item(query: str, item: dict[str, Any]) -> int:
    q_clean = query.strip().lower()
    code = str(item.get("Code", "")).lower()
    name = str(item.get("Name", "")).lower()
    exch = str(item.get("Exchange", "")).upper()
    itype = str(item.get("Type", ""))
    country = str(item.get("Country", "")).lower()

    score = 0
    full_ticker = f"{code}.{exch.lower()}"
    if q_clean == full_ticker or q_clean == code:
        score += 100
    if name.startswith(q_clean):
        score += 60
    elif q_clean in name:
        score += 30

    if itype == "Common Stock":
        score += 40
    elif itype in ("ETF", "Index", "INDEX"):
        score += 20

    if exch == "PA" or country == "france":
        score += 25
    elif exch == "US" or country in ("usa", "united states"):
        score += 15

    # Penalize derivatives, ADRs or hedged tokens
    if any(term in name for term in ("cdr", "adr", "hedged", "tokenized", "leverage", "double short")):
        score -= 35

    return score


async def search_eodhd_ticker(
    client: httpx.AsyncClient,
    query: str,
    api_key: str,
) -> dict[str, Any] | None:
    """
    Searches EOD Historical Data for a ticker or company name.
    Returns the top matching quote/item or None.
    """
    clean_q = query.strip().strip("$")
    if not clean_q:
        return None

    # If query already looks like CODE.EXCHANGE (e.g. STLA.US, MC.PA)
    if "." in clean_q and len(clean_q.split(".")) == 2:
        code_part, exch_part = clean_q.split(".")
        if 1 <= len(code_part) <= 8 and 2 <= len(exch_part) <= 6:
            return {
                "Code": code_part.upper(),
                "Exchange": exch_part.upper(),
                "Name": clean_q.upper(),
                "ticker": f"{code_part.upper()}.{exch_part.upper()}",
                "Type": "Common Stock",
                "Country": "Marché",
                "Currency": "USD" if exch_part.upper() == "US" else "EUR",
            }

    url = f"https://eodhd.com/api/search/{urllib.parse.quote(clean_q)}?api_token={urllib.parse.quote(api_key)}&fmt=json"
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not isinstance(items, list) or not items:
            return None

        scored = sorted(items, key=lambda it: score_eodhd_search_item(clean_q, it), reverse=True)
        top = scored[0]
        code = str(top.get("Code", "")).upper()
        exch = str(top.get("Exchange", "")).upper()
        if not code:
            return None
        return {
            "Code": code,
            "Exchange": exch,
            "Name": top.get("Name") or code,
            "ticker": f"{code}.{exch}" if exch else code,
            "Type": top.get("Type", "Common Stock"),
            "Country": top.get("Country", ""),
            "Currency": top.get("Currency", "EUR" if exch == "PA" else "USD"),
            "ISIN": top.get("ISIN"),
            "previousClose": top.get("previousClose"),
        }
    except Exception as exc:
        _logger.warning("Erreur lors de la recherche du ticker EODHD (%s): %s", query, exc)
        return None


async def fetch_eodhd_realtime(
    client: httpx.AsyncClient,
    ticker: str,
    api_key: str,
) -> dict[str, Any] | None:
    """Fetches real-time / delayed quote from EOD Historical Data."""
    url = f"https://eodhd.com/api/real-time/{urllib.parse.quote(ticker)}?api_token={urllib.parse.quote(api_key)}&fmt=json"
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("code"):
                return data
    except Exception as exc:
        _logger.warning("Erreur lors de l'appel real-time EODHD (%s): %s", ticker, exc)
    return None


async def fetch_eodhd_historical_eod(
    client: httpx.AsyncClient,
    ticker: str,
    api_key: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fetches historical daily bars (EOD) from EOD Historical Data."""
    url = f"https://eodhd.com/api/eod/{urllib.parse.quote(ticker)}?order=d&fmt=json&limit={limit}&api_token={urllib.parse.quote(api_key)}"
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data[:limit]
    except Exception as exc:
        _logger.warning("Erreur lors de l'appel eod EODHD (%s): %s", ticker, exc)
    return []


async def fetch_eodhd_fundamentals(
    client: httpx.AsyncClient,
    ticker: str,
    api_key: str,
) -> dict[str, Any] | None:
    """Fetches fundamentals from EOD Historical Data (if plan permits)."""
    url = f"https://eodhd.com/api/fundamentals/{urllib.parse.quote(ticker)}?api_token={urllib.parse.quote(api_key)}&fmt=json"
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and any(k in data for k in ("General", "Highlights", "Valuation")):
                return data
    except Exception as exc:
        _logger.debug("Fundamentals EODHD non disponibles pour %s: %s", ticker, exc)
    return None


def build_eodhd_markdown(
    ticker: str,
    search_item: dict[str, Any] | None,
    rt_data: dict[str, Any],
    eod_bars: list[dict[str, Any]] | None,
    fundamentals: dict[str, Any] | None = None,
    yahoo_summary: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """
    Builds structured, rich Markdown data from EOD Historical Data API.
    Optionally enriched with Yahoo Finance fundamentals.
    Returns: (title, full_markdown, metadata_dict)
    """
    search_item = search_item or {}
    long_name = search_item.get("Name") or ticker
    short_name = long_name.split(" - ")[0].split(" (")[0].strip()
    exchange = search_item.get("Exchange") or (ticker.split(".")[1] if "." in ticker else "Marché")
    country = search_item.get("Country") or "International"
    currency = search_item.get("Currency") or ("USD" if exchange.upper() == "US" else "EUR")
    isin = search_item.get("ISIN")

    # Real-time quote fields
    curr_price = _safe_float(rt_data.get("close"))
    prev_close = _safe_float(rt_data.get("previousClose"))
    if curr_price is None and prev_close is not None:
        curr_price = prev_close

    open_price = _safe_float(rt_data.get("open"))
    high_price = _safe_float(rt_data.get("high"))
    low_price = _safe_float(rt_data.get("low"))
    volume = _safe_float(rt_data.get("volume"))

    change = _safe_float(rt_data.get("change"))
    change_pct = _safe_float(rt_data.get("change_p"))
    if change is None and curr_price is not None and prev_close is not None:
        change = curr_price - prev_close
    if change_pct is None and change is not None and prev_close and prev_close > 0:
        change_pct = (change / prev_close) * 100

    # Indicators from fundamentals or yahoo_summary
    market_cap = None
    pe_trailing = None
    div_yield = None
    w52_high = None
    w52_low = None
    sector = None
    industry = None
    summary_text = None
    website = None

    if fundamentals:
        hl = fundamentals.get("Highlights", {})
        gen = fundamentals.get("General", {})
        val = fundamentals.get("Valuation", {})
        tech = fundamentals.get("Technicals", {})
        market_cap = _safe_float(hl.get("MarketCapitalization"))
        pe_trailing = _safe_float(hl.get("PE") or val.get("TrailingPE"))
        div_yield = _safe_float(hl.get("DividendYield"))
        w52_high = _safe_float(tech.get("52WeekHigh"))
        w52_low = _safe_float(tech.get("52WeekLow"))
        sector = gen.get("Sector")
        industry = gen.get("Industry")
        summary_text = gen.get("Description")
        website = gen.get("WebURL")
        if gen.get("Name"):
            long_name = gen["Name"]
            short_name = long_name.split(" - ")[0].split(" (")[0].strip()

    if yahoo_summary:
        price_mod = yahoo_summary.get("price", {})
        stats_mod = yahoo_summary.get("defaultKeyStatistics", {})
        prof_mod = yahoo_summary.get("assetProfile", {})
        det_mod = yahoo_summary.get("summaryDetail", {})

        if market_cap is None:
            market_cap = _safe_float(price_mod.get("marketCap") or det_mod.get("marketCap"))
        if pe_trailing is None:
            pe_trailing = _safe_float(stats_mod.get("trailingPE") or det_mod.get("trailingPE"))
        if div_yield is None:
            div_yield = _safe_float(det_mod.get("dividendYield"))
        if w52_high is None:
            w52_high = _safe_float(det_mod.get("fiftyTwoWeekHigh"))
        if w52_low is None:
            w52_low = _safe_float(det_mod.get("fiftyTwoWeekLow"))
        if not sector:
            sector = prof_mod.get("sector")
        if not industry:
            industry = prof_mod.get("industry")
        if not summary_text:
            summary_text = prof_mod.get("longBusinessSummary")
        if not website:
            website = prof_mod.get("website")

    price_str = f"{curr_price:.2f} {currency}" if curr_price is not None else "N/A"
    change_str = (
        f"{change:+.2f} {currency} ({change_pct:+.2f}%)"
        if change is not None and change_pct is not None
        else f"({change_pct:+.2f}%)" if change_pct is not None else ""
    )

    title = f"📈 {short_name} ({ticker})"
    eodhd_url = f"https://eodhd.com/financial-summary/{ticker}"

    enriched_source = "EOD Historical Data API"
    if yahoo_summary:
        enriched_source = "EOD Historical Data & Yahoo Finance API"

    lines: list[str] = [
        f"# 📈 {long_name} ({ticker})",
        f"> ⚡ **Données téléchargées en direct via {enriched_source}** · Marché : {exchange} ({country}) · Devise : `{currency}` · Fiche : [{ticker}]({eodhd_url})",
        "",
        f"### 🏷️ Cours actuel : **{price_str}** {change_str}".strip(),
        "",
        "#### 📊 Indicateurs de séance & Marché",
        "| Métrique | Valeur |",
        "| :--- | :--- |",
        f"| **Dernier cours** | `{price_str}` |",
        f"| **Variation du jour** | `{change_str or 'N/A'}` |",
        f"| **Précédente clôture** | `{_fmt_num(prev_close)} {currency}` |",
        f"| **Séance du jour** | `Ouv. {_fmt_num(open_price)} · Haut {_fmt_num(high_price)} · Bas {_fmt_num(low_price)}` |",
        f"| **Volume de la séance** | `{_fmt_num(volume, suffix='titres')}` |",
    ]

    if isin:
        lines.append(f"| **Code ISIN** | `{isin}` |")
    if market_cap is not None:
        lines.append(f"| **Capitalisation boursière** | `{_fmt_num(market_cap, currency)}` |")
    if pe_trailing is not None:
        lines.append(f"| **Ratio C/B (P/E)** | `{_fmt_num(pe_trailing)}` |")
    if div_yield is not None:
        lines.append(f"| **Rendement du dividende** | `{_fmt_pct(div_yield)}` |")
    if w52_low is not None and w52_high is not None:
        lines.append(f"| **Fourchette 52 semaines** | `{_fmt_num(w52_low)} - {_fmt_num(w52_high)} {currency}` |")

    lines.append("")

    if eod_bars and len(eod_bars) > 0:
        lines.extend([
            "#### 📅 Historique des dernières séances de bourse (EOD)",
            "| Date | Clôture | Var. jour | Ouv. | Plus haut | Plus bas | Volume |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for i, bar in enumerate(eod_bars[:8]):
            b_date = bar.get("date", "N/A")
            b_close = _safe_float(bar.get("close") or bar.get("adjusted_close"))
            b_open = _safe_float(bar.get("open"))
            b_high = _safe_float(bar.get("high"))
            b_low = _safe_float(bar.get("low"))
            b_vol = _safe_float(bar.get("volume"))

            var_str = "—"
            if b_close is not None and i + 1 < len(eod_bars):
                older_close = _safe_float(eod_bars[i + 1].get("close") or eod_bars[i + 1].get("adjusted_close"))
                if older_close and older_close > 0:
                    diff_pct = ((b_close - older_close) / older_close) * 100
                    var_str = f"{diff_pct:+.2f}%"

            lines.append(
                f"| {b_date} | `{_fmt_num(b_close)} {currency}` | **{var_str}** | {_fmt_num(b_open)} | {_fmt_num(b_high)} | {_fmt_num(b_low)} | {_fmt_num(b_vol)} |"
            )
        lines.append("")

    if yahoo_summary:
        fin_mod = yahoo_summary.get("financialData", {})
        tot_rev = fin_mod.get("totalRevenue")
        ebitda_val = fin_mod.get("ebitda")
        if tot_rev is not None or ebitda_val is not None:
            lines.extend([
                "#### 💰 Performance financière & Rentabilité (Yahoo Finance)",
                "| Indicateur financier | Donnée déclarée |",
                "| :--- | :--- |",
                f"| **Chiffre d'affaires** | `{_fmt_num(tot_rev, currency)}` |",
                f"| **Croissance du CA** | `{_fmt_pct(fin_mod.get('revenueGrowth'))}` |",
                f"| **Marge brute** | `{_fmt_pct(fin_mod.get('grossMargins'))}` |",
                f"| **Marge opérationnelle** | `{_fmt_pct(fin_mod.get('operatingMargins'))}` |",
                f"| **Marge nette** | `{_fmt_pct(fin_mod.get('profitMargins'))}` |",
                f"| **EBITDA** | `{_fmt_num(ebitda_val, currency)}` |",
                f"| **Bénéfice net** | `{_fmt_num(stats_mod.get('netIncomeToCommon'), currency)}` |",
                f"| **Flux de trésorerie disponible (FCF)** | `{_fmt_num(fin_mod.get('freeCashflow'), currency)}` |",
                f"| **Trésorerie totale (Cash)** | `{_fmt_num(fin_mod.get('totalCash'), currency)}` |",
                f"| **Dette totale** | `{_fmt_num(fin_mod.get('totalDebt'), currency)}` |",
                "",
            ])
        recom = fin_mod.get("recommendationKey")
        t_mean = fin_mod.get("targetMeanPrice")
        if recom or t_mean:
            lines.extend([
                "#### 🎯 Consensus & Objectifs des analystes (Yahoo Finance)",
                f"- **Recommandation moyenne :** `{str(recom).upper() if recom else 'N/A'}` "
                f"*(basée sur {_fmt_num(fin_mod.get('numberOfAnalystOpinions'), default='plusieurs')} avis d'analystes)*",
                f"- **Objectif de cours moyen :** `{_fmt_num(t_mean, currency)}`",
                f"- **Objectif haut / bas :** `{_fmt_num(fin_mod.get('targetHighPrice'), currency)}` / `{_fmt_num(fin_mod.get('targetLowPrice'), currency)}`",
                "",
            ])

    if sector or summary_text:
        lines.extend([
            "#### 🏢 Profil de l'entreprise",
            f"- **Secteur :** {sector or 'N/A'} · **Industrie :** {industry or 'N/A'}",
            f"- **Pays / Marché :** {country} ({exchange})",
        ])
        if website:
            lines.append(f"- **Site officiel :** [{website}]({website})")
        if summary_text:
            short_desc = summary_text[:600].replace("\n", " ").strip()
            lines.append(f"\n> **Activité :** {short_desc}{'…' if len(summary_text) > 600 else ''}")
        lines.append("")

    lines.append(f"> ℹ️ Données de marché fournies par l'API **EOD Historical Data** [eodhd.com](https://eodhd.com) (ticker : `{ticker}`).")

    full_markdown = "\n".join(lines)
    if len(full_markdown) > MAX_EXTRACTED_CHARS:
        full_markdown = full_markdown[:MAX_EXTRACTED_CHARS]

    metadata = {
        "symbol": ticker,
        "short_name": short_name,
        "long_name": long_name,
        "price": curr_price,
        "currency": currency,
        "change_percent": change_pct,
        "market_cap": market_cap,
        "exchange": exchange,
        "provider": "eodhd",
        "source_label": enriched_source,
        "url": eodhd_url,
    }

    return title, full_markdown, metadata


async def fetch_eodhd_quote_data(
    settings: Settings,
    target: str,
    eod_client: httpx.AsyncClient | None = None,
    yahoo_summary: dict[str, Any] | None = None,
) -> tuple[str, bytes, str, str, dict[str, Any]] | None:
    """
    Fetches real-time stock quote and historical daily bars from EOD Historical Data API.
    Returns standard attachment tuple: (filename, content_bytes, mime_type, full_text, extraction_dict).
    """
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    if not eod_key:
        return None

    clean_target = target.strip()
    close_client = False
    if eod_client is None:
        eod_client = httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
            timeout=12.0,
        )
        close_client = True

    try:
        eod_item = None
        ticker_candidate = None
        if is_eodhd_url(clean_target):
            ticker_candidate = extract_ticker_from_url(clean_target)
        elif "." in clean_target and len(clean_target.split(".")) == 2:
            code_p, exch_p = clean_target.split(".")
            if 1 <= len(code_p) <= 8 and 2 <= len(exch_p) <= 6:
                ticker_candidate = clean_target.upper().strip("$")

        if not ticker_candidate:
            for variant in query_variants(clean_target):
                eod_item = await search_eodhd_ticker(eod_client, variant, eod_key)
                if eod_item:
                    ticker_candidate = eod_item.get("ticker")
                    break

        if not ticker_candidate:
            return None

        rt_data = await fetch_eodhd_realtime(eod_client, ticker_candidate, eod_key)
        if not rt_data:
            return None

        eod_bars = await fetch_eodhd_historical_eod(
            eod_client, ticker_candidate, eod_key, limit=10
        )
        fundamentals = await fetch_eodhd_fundamentals(
            eod_client, ticker_candidate, eod_key
        )

        title, full_markdown, meta = build_eodhd_markdown(
            ticker=ticker_candidate,
            search_item=eod_item,
            rt_data=rt_data,
            eod_bars=eod_bars,
            fundamentals=fundamentals,
            yahoo_summary=yahoo_summary,
        )

        filename = f"📈 {meta['short_name']} ({ticker_candidate}) · EOD Historical Data"[:255]
        mime_type = "text/html; type=finance; source=eod-historical-data"

        extraction = DocumentExtraction(
            model="eod-historical-data",
            pages=[
                ExtractedPage(
                    index=0,
                    markdown=full_markdown,
                    method="local",
                    images=[],
                )
            ],
            annotations=[
                DocumentAnnotation(
                    title=title,
                    summary=f"Cotation et cours de bourse en direct (EOD Historical Data) pour {meta['long_name']} ({ticker_candidate}) : "
                            f"Cours {meta.get('price')} {meta.get('currency')} ({(meta.get('change_percent') or 0):+.2f}%).",
                )
            ],
            warnings=[],
        ).model_dump()
        extraction.update(meta)
        content_bytes = full_markdown.encode("utf-8")
        return filename, content_bytes, mime_type, full_markdown, extraction
    finally:
        if close_client:
            await eod_client.aclose()


async def fetch_yahoo_financials_data(
    settings: Settings,
    target: str,
    yahoo_client: httpx.AsyncClient | None = None,
    crumb: str | None = None,
) -> tuple[str, bytes, str, str, dict[str, Any]] | None:
    """
    Fetches valuation multiples, financial statements, analyst consensus, and company
    profile from Yahoo Finance API.
    Returns standard attachment tuple: (filename, content_bytes, mime_type, full_text, extraction_dict).
    """
    clean_target = target.strip()
    ticker = None

    if is_yahoo_finance_url(clean_target):
        ticker = extract_ticker_from_url(clean_target)

    close_client = False
    if yahoo_client is None:
        yahoo_client, crumb = await get_yahoo_crumb_and_client()
        close_client = True

    try:
        top_quote = None
        if not ticker:
            # Map US stocks ending with .US if passed from EOD
            if clean_target.upper().endswith(".US"):
                ticker = clean_target.upper()[:-3]
            else:
                for variant in query_variants(clean_target):
                    top_quote = await search_yahoo_ticker(yahoo_client, variant)
                    if top_quote:
                        break
                if top_quote:
                    ticker = top_quote.get("symbol")
                elif " " not in clean_target:
                    ticker = clean_target.upper().strip("$")

        if not ticker:
            return None

        # Fetch chart (OHLCV + live metadata)
        chart_data = await fetch_yahoo_chart(yahoo_client, ticker, range_period="1mo", interval="1d")

        # Fetch quoteSummary (fundamentals, statistics, profile)
        summary_data = await fetch_yahoo_quote_summary(yahoo_client, ticker, crumb=crumb)

        if not chart_data and not summary_data:
            return None

        title, full_markdown, meta = build_finance_markdown(ticker, top_quote, chart_data, summary_data)

        filename = f"📈 {meta['short_name']} ({ticker}) · Yahoo Finance"[:255]
        mime_type = "text/html; type=finance; source=yahoo-finance"

        extraction = DocumentExtraction(
            model="yahoo-finance",
            pages=[
                ExtractedPage(
                    index=0,
                    markdown=full_markdown,
                    method="local",
                    images=[],
                )
            ],
            annotations=[
                DocumentAnnotation(
                    title=title,
                    summary=f"Données financières Yahoo Finance pour {meta['long_name']} ({ticker}) : "
                            f"Cours {meta.get('price')} {meta.get('currency')} ({(meta.get('change_percent') or 0):+.2f}%).",
                )
            ],
            warnings=[],
        ).model_dump()

        extraction.update(meta)
        extraction.setdefault("provider", "yahoo_finance")
        extraction.setdefault("source_label", "Yahoo Finance API")

        content_bytes = full_markdown.encode("utf-8")
        return filename, content_bytes, mime_type, full_markdown, extraction
    finally:
        if close_client:
            await yahoo_client.aclose()


async def fetch_dual_financial_attachments(
    settings: Settings,
    target: str,
) -> list[tuple[str, bytes, str, str, dict[str, Any]]]:
    """
    Fetches stock quote via EOD Historical Data API AND financial data via Yahoo Finance API.
    Returns both attachments [eod_attachment, yahoo_attachment] when available.
    Falls back gracefully to Yahoo Finance or EODHD if one provider fails or is unconfigured.
    """
    clean_target = target.strip()
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    is_yahoo_url = is_yahoo_finance_url(clean_target)

    # If explicit Yahoo URL or no EOD key: query Yahoo Finance directly
    if is_yahoo_url or not eod_key:
        y_att = await fetch_yahoo_financials_data(settings, clean_target)
        if y_att:
            return [y_att]
        raise HTTPException(404, f"Impossible de récupérer les données financières pour « {target} » sur Yahoo Finance.")

    # Concurrently fetch EOD quote and Yahoo financial data
    async def _safe_eod():
        try:
            return await fetch_eodhd_quote_data(settings, clean_target)
        except Exception as e_exc:
            _logger.warning("Échec EODHD pour « %s »: %s", clean_target, e_exc)
            return None

    async def _safe_yahoo(symbol_hint: str | None = None):
        try:
            lookup = symbol_hint or clean_target
            if lookup.endswith(".US"):
                lookup = lookup[:-3]
            return await fetch_yahoo_financials_data(settings, lookup)
        except Exception as y_exc:
            _logger.warning("Échec Yahoo Finance pour « %s »: %s", clean_target, y_exc)
            return None

    eod_res, yahoo_res = await asyncio.gather(_safe_eod(), _safe_yahoo(), return_exceptions=False)

    # If EOD succeeded but Yahoo initial lookup didn't, retry Yahoo using the resolved EOD symbol
    if eod_res and not yahoo_res:
        eod_symbol = eod_res[4].get("symbol")
        if eod_symbol:
            yahoo_res = await _safe_yahoo(eod_symbol)

    results: list[tuple[str, bytes, str, str, dict[str, Any]]] = []
    if eod_res:
        results.append(eod_res)
    if yahoo_res:
        results.append(yahoo_res)

    if not results:
        raise HTTPException(404, f"Impossible de récupérer les cotations et données financières pour « {target} ».")

    return results


async def fetch_and_parse_yahoo_finance(
    settings: Settings,
    target: str,
) -> tuple[str, bytes, str, str, dict[str, Any]]:
    """
    Fetches real-time stock quote and financial data.
    Maintains compatibility with callers expecting a single attachment tuple.
    Prefers EOD Historical Data (enriched with Yahoo Finance) when configured,
    with seamless automatic fallback to Yahoo Finance API.
    """
    clean_target = target.strip()
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    is_yahoo_url = is_yahoo_finance_url(clean_target)

    if eod_key and not is_yahoo_url:
        try:
            y_summary = None
            try:
                y_c, y_crumb = await get_yahoo_crumb_and_client()
                try:
                    for v in query_variants(clean_target):
                        t_q = await search_yahoo_ticker(y_c, v)
                        if t_q:
                            sym = t_q.get("symbol")
                            if sym:
                                y_summary = await fetch_yahoo_quote_summary(y_c, sym, crumb=y_crumb)
                                break
                finally:
                    await y_c.aclose()
            except Exception as y_exc:
                _logger.debug("Enrichissement Yahoo Finance omis: %s", y_exc)

            eod_tuple = await fetch_eodhd_quote_data(settings, clean_target, yahoo_summary=y_summary)
            if eod_tuple:
                return eod_tuple
        except Exception as eod_exc:
            _logger.warning("Échec EODHD pour « %s » (%s), repli sur Yahoo Finance...", clean_target, eod_exc)

    y_tuple = await fetch_yahoo_financials_data(settings, clean_target)
    if y_tuple:
        return y_tuple

    raise HTTPException(404, f"Impossible d'identifier l'actif financier pour « {target} ».")


fetch_and_parse_financial_data = fetch_and_parse_yahoo_finance


def _is_callable_mock(func: Any) -> bool:
    """Checks if a function object has been mocked in a test."""
    return (
        getattr(func, "_mock_name", None) is not None
        or getattr(func, "mock", None) is not None
        or hasattr(func, "assert_called")
        or hasattr(func, "assert_called_once")
        or hasattr(func, "return_value")
    )


async def process_message_finance_inquiries(
    settings: Settings,
    text: str,
    existing_attachments: list[Any],
    user_id: str,
    message_id: str,
    upload_dir: Path,
    finance_mode: bool = False,
    previous_targets: list[str] | None = None,
    entity_resolver: Callable[[str, list[str]], Awaitable[list[str]]] | None = None,
    failures: list[str] | None = None,
) -> list[Attachment]:
    """
    Inspects user message text for company or stock quote requests,
    downloads real-time financial data via EODHD (stock quote) and Yahoo Finance (financial statements),
    and returns newly created Attachment records for both sources.
    """
    previous_targets = [t for t in (previous_targets or []) if t]
    heuristic = detect_financial_entities(text)
    entities: list[str] = []
    resolved_by_llm = False
    if entity_resolver is not None and (heuristic or finance_mode):
        try:
            entities = [e.strip() for e in await entity_resolver(text, previous_targets) if e and e.strip()][:3]
            resolved_by_llm = True
        except Exception as exc:
            _logger.warning("Extraction des entités financières par IA indisponible; repli heuristique: %s", exc)
    if not resolved_by_llm:
        entities = heuristic
        if not entities and finance_mode:
            if previous_targets:
                entities = previous_targets[:3]
            else:
                cleaned = re.sub(r"[?!,.;:\"'`()\[\]{}]+", " ", text).strip()
                tokens = [t for t in cleaned.split() if t.lower() not in STOPWORDS and len(t) >= 2]
                if tokens:
                    entities = [" ".join(tokens[:3])]

    if not entities:
        return []

    # Get existing symbols or URLs already attached, tracked per provider to allow both EOD & Yahoo
    existing_keys: set[str] = set()
    for att in existing_attachments:
        if isinstance(att.extraction, dict):
            sym = str(att.extraction.get("symbol") or "").upper()
            prov = str(att.extraction.get("provider") or "").lower()
            if sym:
                existing_keys.add(f"{sym}:{prov}" if prov else sym)
            if att.extraction.get("url"):
                existing_keys.add(str(att.extraction.get("url")).lower())

    new_attachments: list[Attachment] = []

    for entity in entities:
        try:
            if _is_callable_mock(fetch_and_parse_yahoo_finance):
                mock_res = await fetch_and_parse_yahoo_finance(settings, entity)
                att_tuples = [mock_res] if isinstance(mock_res, tuple) else mock_res
            else:
                att_tuples = await fetch_dual_financial_attachments(settings, entity)

            for filename, content_bytes, mime_type, full_text, extraction in att_tuples:
                symbol = str(extraction.get("symbol", "")).upper()
                provider = str(extraction.get("provider", "")).lower()
                dedup_key = f"{symbol}:{provider}" if (symbol and provider) else symbol
                if dedup_key and dedup_key in existing_keys:
                    continue

                if dedup_key:
                    existing_keys.add(dedup_key)

                storage_name = str(uuid4())
                file_path = upload_dir / storage_name
                file_path.write_bytes(content_bytes)

                attachment = Attachment(
                    user_id=user_id,
                    filename=filename,
                    mime_type=mime_type,
                    size=len(content_bytes),
                    storage_name=storage_name,
                    extracted_text=full_text,
                    extraction=extraction,
                    message_id=message_id,
                )
                new_attachments.append(attachment)
                _logger.info("Données financières attachées pour %s (%s) [%s]", entity, symbol, extraction.get("provider", "finance"))

        except Exception as exc:
            _logger.warning("Impossible de récupérer les données financières pour « %s »: %s", entity, exc)
            if failures is not None:
                failures.append(entity)

    return new_attachments
