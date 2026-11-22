"""Normalisation géographique des titres financiers (pays, zones boursières, places).

Fournit une résolution déterministe et 100 % locale pour le Screener Boursier :
- Canonisation des noms de pays en français (évite les doublons `USA` / `United States` / `US`).
- Déduction du pays à partir du code place boursière (`PA`, `XETRA`, `LSE`, `US`…) ou du suffixe
  ticker (`.PA`, `.DE`, `.L`, `.SW`…) lorsque les fondamentaux n'ont pas encore été chargés.
- Rattachement aux grandes zones boursières (`europe`, `eurozone`, `north_america`, `asia_pacific`,
  `latin_america`, `mea`) et libellés lisibles des places boursières.
"""

from __future__ import annotations

import unicodedata
from typing import Any

# Zones boursières affichées dans le Screener (ordre logique d'affichage)
MARKET_ZONES: tuple[dict[str, str], ...] = (
    {"code": "eurozone", "label": "Zone Euro", "flag": "🇪🇺"},
    {"code": "europe", "label": "Europe", "flag": "🌍"},
    {"code": "north_america", "label": "Amérique du Nord", "flag": "🌎"},
    {"code": "asia_pacific", "label": "Asie-Pacifique", "flag": "🌏"},
    {"code": "latin_america", "label": "Amérique latine", "flag": "🌎"},
    {"code": "mea", "label": "Moyen-Orient & Afrique", "flag": "🌍"},
)

MARKET_ZONE_BY_CODE: dict[str, dict[str, str]] = {z["code"]: z for z in MARKET_ZONES}
VALID_MARKET_ZONES: frozenset[str] = frozenset(MARKET_ZONE_BY_CODE.keys())

# Pays de la Zone Euro (noms canoniques français)
EUROZONE_COUNTRIES: frozenset[str] = frozenset(
    {
        "Allemagne",
        "Autriche",
        "Belgique",
        "Chypre",
        "Croatie",
        "Espagne",
        "Estonie",
        "Finlande",
        "France",
        "Grèce",
        "Irlande",
        "Italie",
        "Lettonie",
        "Lituanie",
        "Luxembourg",
        "Malte",
        "Pays-Bas",
        "Portugal",
        "Slovaquie",
        "Slovénie",
    }
)

# Pays canonique -> Zone boursière principale
_COUNTRY_TO_PRIMARY_ZONE: dict[str, str] = {
    # Europe
    **{c: "europe" for c in EUROZONE_COUNTRIES},
    "Royaume-Uni": "europe",
    "Suisse": "europe",
    "Suède": "europe",
    "Danemark": "europe",
    "Norvège": "europe",
    "Pologne": "europe",
    "République tchèque": "europe",
    "Hongrie": "europe",
    "Roumanie": "europe",
    "Islande": "europe",
    "Bulgarie": "europe",
    # Amérique du Nord
    "États-Unis": "north_america",
    "Canada": "north_america",
    # Asie-Pacifique
    "Japon": "asia_pacific",
    "Hong Kong": "asia_pacific",
    "Chine": "asia_pacific",
    "Corée du Sud": "asia_pacific",
    "Australie": "asia_pacific",
    "Inde": "asia_pacific",
    "Taïwan": "asia_pacific",
    "Singapour": "asia_pacific",
    "Nouvelle-Zélande": "asia_pacific",
    "Indonésie": "asia_pacific",
    "Thaïlande": "asia_pacific",
    "Malaisie": "asia_pacific",
    "Vietnam": "asia_pacific",
    "Philippines": "asia_pacific",
    # Amérique latine
    "Brésil": "latin_america",
    "Mexique": "latin_america",
    "Chili": "latin_america",
    "Colombie": "latin_america",
    "Pérou": "latin_america",
    "Argentine": "latin_america",
    # Moyen-Orient & Afrique
    "Israël": "mea",
    "Afrique du Sud": "mea",
    "Arabie saoudite": "mea",
    "Émirats arabes unis": "mea",
    "Qatar": "mea",
    "Turquie": "mea",
    "Égypte": "mea",
    "Maroc": "mea",
}

# Drapeaux par pays canonique
COUNTRY_FLAGS: dict[str, str] = {
    "France": "🇫🇷",
    "États-Unis": "🇺🇸",
    "Allemagne": "🇩🇪",
    "Royaume-Uni": "🇬🇧",
    "Suisse": "🇨🇭",
    "Pays-Bas": "🇳🇱",
    "Belgique": "🇧🇪",
    "Italie": "🇮🇹",
    "Espagne": "🇪🇸",
    "Portugal": "🇵🇹",
    "Irlande": "🇮🇪",
    "Autriche": "🇦🇹",
    "Luxembourg": "🇱🇺",
    "Finlande": "🇫🇮",
    "Suède": "🇸🇪",
    "Danemark": "🇩🇰",
    "Norvège": "🇳🇴",
    "Pologne": "🇵🇱",
    "Grèce": "🇬🇷",
    "République tchèque": "🇨🇿",
    "Hongrie": "🇭🇺",
    "Canada": "🇨🇦",
    "Japon": "🇯🇵",
    "Hong Kong": "🇭🇰",
    "Chine": "🇨🇳",
    "Corée du Sud": "🇰🇷",
    "Australie": "🇦🇺",
    "Inde": "🇮🇳",
    "Taïwan": "🇹🇼",
    "Singapour": "🇸🇬",
    "Nouvelle-Zélande": "🇳🇿",
    "Indonésie": "🇮🇩",
    "Thaïlande": "🇹🇭",
    "Malaisie": "🇲🇾",
    "Vietnam": "🇻🇳",
    "Philippines": "🇵🇭",
    "Brésil": "🇧🇷",
    "Mexique": "🇲🇽",
    "Chili": "🇨🇱",
    "Colombie": "🇨🇴",
    "Pérou": "🇵🇪",
    "Argentine": "🇦🇷",
    "Israël": "🇮🇱",
    "Afrique du Sud": "🇿🇦",
    "Arabie saoudite": "🇸🇦",
    "Émirats arabes unis": "🇦🇪",
    "Qatar": "🇶🇦",
    "Turquie": "🇹🇷",
    "Égypte": "🇪🇬",
    "Maroc": "🇲🇦",
}

# Alias (normalisés sans accents en minuscules) -> Pays canonique français
_COUNTRY_ALIASES: dict[str, str] = {
    # États-Unis
    "us": "États-Unis",
    "usa": "États-Unis",
    "u.s.": "États-Unis",
    "u.s.a.": "États-Unis",
    "united states": "États-Unis",
    "united states of america": "États-Unis",
    "etats-unis": "États-Unis",
    "etats unis": "États-Unis",
    # France
    "fr": "France",
    "fra": "France",
    "france": "France",
    # Allemagne
    "de": "Allemagne",
    "deu": "Allemagne",
    "germany": "Allemagne",
    "allemagne": "Allemagne",
    # Royaume-Uni
    "gb": "Royaume-Uni",
    "gbr": "Royaume-Uni",
    "uk": "Royaume-Uni",
    "united kingdom": "Royaume-Uni",
    "great britain": "Royaume-Uni",
    "royaume-uni": "Royaume-Uni",
    "royaume uni": "Royaume-Uni",
    # Suisse
    "ch": "Suisse",
    "che": "Suisse",
    "switzerland": "Suisse",
    "suisse": "Suisse",
    # Pays-Bas
    "nl": "Pays-Bas",
    "nld": "Pays-Bas",
    "netherlands": "Pays-Bas",
    "the netherlands": "Pays-Bas",
    "pays-bas": "Pays-Bas",
    "pays bas": "Pays-Bas",
    # Belgique
    "be": "Belgique",
    "bel": "Belgique",
    "belgium": "Belgique",
    "belgique": "Belgique",
    # Italie
    "it": "Italie",
    "ita": "Italie",
    "italy": "Italie",
    "italie": "Italie",
    # Espagne
    "es": "Espagne",
    "esp": "Espagne",
    "spain": "Espagne",
    "espagne": "Espagne",
    # Portugal
    "pt": "Portugal",
    "prt": "Portugal",
    "portugal": "Portugal",
    # Irlande
    "ie": "Irlande",
    "irl": "Irlande",
    "ireland": "Irlande",
    "irlande": "Irlande",
    # Autriche
    "at": "Autriche",
    "aut": "Autriche",
    "austria": "Autriche",
    "autriche": "Autriche",
    # Luxembourg
    "lu": "Luxembourg",
    "lux": "Luxembourg",
    "luxembourg": "Luxembourg",
    # Finlande
    "fi": "Finlande",
    "fin": "Finlande",
    "finland": "Finlande",
    "finlande": "Finlande",
    # Suède
    "se": "Suède",
    "swe": "Suède",
    "sweden": "Suède",
    "suede": "Suède",
    # Danemark
    "dk": "Danemark",
    "dnk": "Danemark",
    "denmark": "Danemark",
    "danemark": "Danemark",
    # Norvège
    "no": "Norvège",
    "nor": "Norvège",
    "norway": "Norvège",
    "norvege": "Norvège",
    # Pologne
    "pl": "Pologne",
    "pol": "Pologne",
    "poland": "Pologne",
    "pologne": "Pologne",
    # Grèce
    "gr": "Grèce",
    "grc": "Grèce",
    "greece": "Grèce",
    "grece": "Grèce",
    # République tchèque
    "cz": "République tchèque",
    "cze": "République tchèque",
    "czech republic": "République tchèque",
    "czechia": "République tchèque",
    "republique tcheque": "République tchèque",
    # Hongrie
    "hu": "Hongrie",
    "hun": "Hongrie",
    "hungary": "Hongrie",
    "hongrie": "Hongrie",
    # Canada
    "ca": "Canada",
    "can": "Canada",
    "canada": "Canada",
    # Japon
    "jp": "Japon",
    "jpn": "Japon",
    "japan": "Japon",
    "japon": "Japon",
    # Hong Kong
    "hk": "Hong Kong",
    "hkg": "Hong Kong",
    "hong kong": "Hong Kong",
    # Chine
    "cn": "Chine",
    "chn": "Chine",
    "china": "Chine",
    "chine": "Chine",
    # Corée du Sud
    "kr": "Corée du Sud",
    "kor": "Corée du Sud",
    "south korea": "Corée du Sud",
    "korea": "Corée du Sud",
    "republic of korea": "Corée du Sud",
    "coree du sud": "Corée du Sud",
    # Australie
    "au": "Australie",
    "aus": "Australie",
    "australia": "Australie",
    "australie": "Australie",
    # Inde
    "in": "Inde",
    "ind": "Inde",
    "india": "Inde",
    "inde": "Inde",
    # Taïwan
    "tw": "Taïwan",
    "twn": "Taïwan",
    "taiwan": "Taïwan",
    # Singapour
    "sg": "Singapour",
    "sgp": "Singapour",
    "singapore": "Singapour",
    "singapour": "Singapour",
    # Nouvelle-Zélande
    "nz": "Nouvelle-Zélande",
    "nzl": "Nouvelle-Zélande",
    "new zealand": "Nouvelle-Zélande",
    "nouvelle-zelande": "Nouvelle-Zélande",
    # Indonésie / Thaïlande / Malaisie / Vietnam / Philippines
    "id": "Indonésie",
    "indonesia": "Indonésie",
    "indonesie": "Indonésie",
    "th": "Thaïlande",
    "thailand": "Thaïlande",
    "thailande": "Thaïlande",
    "my": "Malaisie",
    "malaysia": "Malaisie",
    "malaisie": "Malaisie",
    "vn": "Vietnam",
    "vietnam": "Vietnam",
    "ph": "Philippines",
    "philippines": "Philippines",
    # Amérique latine
    "br": "Brésil",
    "bra": "Brésil",
    "brazil": "Brésil",
    "bresil": "Brésil",
    "mx": "Mexique",
    "mex": "Mexique",
    "mexico": "Mexique",
    "mexique": "Mexique",
    "cl": "Chili",
    "chile": "Chili",
    "chili": "Chili",
    "co": "Colombie",
    "colombia": "Colombie",
    "colombie": "Colombie",
    "pe": "Pérou",
    "peru": "Pérou",
    "perou": "Pérou",
    "ar": "Argentine",
    "argentina": "Argentine",
    "argentine": "Argentine",
    # Moyen-Orient & Afrique
    "il": "Israël",
    "isr": "Israël",
    "israel": "Israël",
    "za": "Afrique du Sud",
    "zaf": "Afrique du Sud",
    "south africa": "Afrique du Sud",
    "afrique du sud": "Afrique du Sud",
    "sa": "Arabie saoudite",
    "saudi arabia": "Arabie saoudite",
    "arabie saoudite": "Arabie saoudite",
    "ae": "Émirats arabes unis",
    "uae": "Émirats arabes unis",
    "united arab emirates": "Émirats arabes unis",
    "emirats arabes unis": "Émirats arabes unis",
    "qa": "Qatar",
    "qatar": "Qatar",
    "tr": "Turquie",
    "turkey": "Turquie",
    "turkiye": "Turquie",
    "turquie": "Turquie",
    "eg": "Égypte",
    "egypt": "Égypte",
    "egypte": "Égypte",
    "ma": "Maroc",
    "morocco": "Maroc",
    "maroc": "Maroc",
}

# Code place boursière / suffixe ticker -> Pays canonique français
_EXCHANGE_TO_COUNTRY: dict[str, str] = {
    # États-Unis
    "US": "États-Unis",
    "NASDAQ": "États-Unis",
    "NYSE": "États-Unis",
    "NYSE ARCA": "États-Unis",
    "NYSE MKT": "États-Unis",
    "AMEX": "États-Unis",
    "BATS": "États-Unis",
    "OTC": "États-Unis",
    "PINK": "États-Unis",
    "NMFQS": "États-Unis",
    # France
    "PA": "France",
    "EPA": "France",
    "PAR": "France",
    "EURONEXT PARIS": "France",
    # Allemagne
    "XETRA": "Allemagne",
    "DE": "Allemagne",
    "F": "Allemagne",
    "FRA": "Allemagne",
    "STU": "Allemagne",
    "MU": "Allemagne",
    "BE": "Allemagne",
    "DU": "Allemagne",
    "HM": "Allemagne",
    "HA": "Allemagne",
    # Royaume-Uni
    "LSE": "Royaume-Uni",
    "L": "Royaume-Uni",
    "LON": "Royaume-Uni",
    "IOB": "Royaume-Uni",
    # Suisse
    "SW": "Suisse",
    "SIX": "Suisse",
    "VX": "Suisse",
    # Pays-Bas
    "AS": "Pays-Bas",
    "AMS": "Pays-Bas",
    # Belgique
    "BR": "Belgique",
    "EBR": "Belgique",
    # Italie
    "MI": "Italie",
    "MIL": "Italie",
    # Espagne
    "MC": "Espagne",
    "BME": "Espagne",
    "MAD": "Espagne",
    # Portugal
    "LS": "Portugal",
    "LIS": "Portugal",
    # Irlande
    "IR": "Irlande",
    "ISE": "Irlande",
    # Autriche
    "VI": "Autriche",
    "VIE": "Autriche",
    # Luxembourg
    "LU": "Luxembourg",
    # Nordiques
    "ST": "Suède",
    "STO": "Suède",
    "CO": "Danemark",
    "CPH": "Danemark",
    "HE": "Finlande",
    "HEL": "Finlande",
    "OL": "Norvège",
    "OSL": "Norvège",
    # Autres Europe
    "WAR": "Pologne",
    "WA": "Pologne",
    "WSE": "Pologne",
    "AT": "Grèce",
    "ATH": "Grèce",
    "PR": "République tchèque",
    "BUD": "Hongrie",
    # Canada
    "TO": "Canada",
    "TSX": "Canada",
    "V": "Canada",
    "NEO": "Canada",
    "CN": "Canada",
    # Asie-Pacifique
    "T": "Japon",
    "TSE": "Japon",
    "TYO": "Japon",
    "JPX": "Japon",
    "HK": "Hong Kong",
    "HKEX": "Hong Kong",
    "HKG": "Hong Kong",
    "AU": "Australie",
    "ASX": "Australie",
    "AX": "Australie",
    "KO": "Corée du Sud",
    "KQ": "Corée du Sud",
    "KS": "Corée du Sud",
    "KRX": "Corée du Sud",
    "NSE": "Inde",
    "BSE": "Inde",
    "NS": "Inde",
    "BO": "Inde",
    "SHG": "Chine",
    "SHE": "Chine",
    "SS": "Chine",
    "SZ": "Chine",
    "TW": "Taïwan",
    "TWO": "Taïwan",
    "SG": "Singapour",
    "SI": "Singapour",
    "SGX": "Singapour",
    "NZ": "Nouvelle-Zélande",
    "JK": "Indonésie",
    "BK": "Thaïlande",
    "KL": "Malaisie",
    "VN": "Vietnam",
    "PSE": "Philippines",
    # Amérique latine
    "SA": "Brésil",
    "BVMF": "Brésil",
    "MX": "Mexique",
    "BMV": "Mexique",
    "SN": "Chili",
    "BA": "Argentine",
    # Moyen-Orient & Afrique
    "TA": "Israël",
    "TASE": "Israël",
    "JSE": "Afrique du Sud",
    "JO": "Afrique du Sud",
    "SR": "Arabie saoudite",
    "IS": "Turquie",
}

# Libellés lisibles pour les places boursières courantes
EXCHANGE_LABELS: dict[str, str] = {
    "US": "US · NYSE / Nasdaq",
    "NASDAQ": "NASDAQ · Nasdaq US",
    "NYSE": "NYSE · New York",
    "NYSE ARCA": "NYSE ARCA · ETF US",
    "AMEX": "AMEX · NYSE American",
    "PA": "PA · Euronext Paris",
    "XETRA": "XETRA · Francfort",
    "DE": "DE · Francfort (XETRA)",
    "F": "F · Francfort",
    "LSE": "LSE · Londres",
    "L": "L · Londres (LSE)",
    "SW": "SW · SIX Suisse",
    "SIX": "SIX · Bourse Suisse",
    "AS": "AS · Euronext Amsterdam",
    "BR": "BR · Euronext Bruxelles",
    "MI": "MI · Borsa Italiana (Milan)",
    "MC": "MC · Bolsa de Madrid",
    "LS": "LS · Euronext Lisbonne",
    "ST": "ST · Nasdaq Stockholm",
    "CO": "CO · Nasdaq Copenhague",
    "HE": "HE · Nasdaq Helsinki",
    "OL": "OL · Oslo Børs",
    "VI": "VI · Bourse de Vienne",
    "IR": "IR · Euronext Dublin",
    "WAR": "WAR · Varsovie",
    "TO": "TO · Toronto (TSX)",
    "TSX": "TSX · Toronto",
    "T": "T · Tokyo (TSE)",
    "TSE": "TSE · Tokyo",
    "HK": "HK · Hong Kong (HKEX)",
    "AU": "AU · Australie (ASX)",
    "KO": "KO · Séoul (KRX)",
    "NSE": "NSE · Inde (Mumbai)",
    "SHG": "SHG · Shanghai",
    "SHE": "SHE · Shenzhen",
    "TW": "TW · Taïwan",
    "SG": "SG · Singapour (SGX)",
    "SA": "SA · São Paulo (B3)",
    "MX": "MX · Mexique (BMV)",
    "TA": "TA · Tel Aviv",
    "JSE": "JSE · Johannesburg",
    "EUFUND": "EUFUND · Fonds européens",
}


def _strip_accents_lower(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text.strip())
    return "".join(ch for ch in norm if not unicodedata.combining(ch)).lower()


def _extract_symbol_suffix(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    if "." not in sym:
        return ""
    return sym.rsplit(".", 1)[1].strip()


def canonicalize_country(
    raw_country: str | None = "",
    *,
    exchange: str | None = "",
    symbol: str | None = "",
) -> str:
    """Retourne le nom canonique français du pays (ou le déduit de la place / du suffixe ticker)."""
    raw = str(raw_country or "").strip()
    if raw:
        key = _strip_accents_lower(raw)
        if key in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[key]
        return raw

    exch = str(exchange or "").strip().upper()
    if exch and exch in _EXCHANGE_TO_COUNTRY:
        return _EXCHANGE_TO_COUNTRY[exch]

    suffix = _extract_symbol_suffix(symbol or "")
    if suffix and suffix in _EXCHANGE_TO_COUNTRY:
        return _EXCHANGE_TO_COUNTRY[suffix]

    return ""


def resolve_market_zone(
    country: str | None = "",
    *,
    exchange: str | None = "",
    symbol: str | None = "",
) -> str:
    """Retourne la zone boursière principale (`europe`, `north_america`, `asia_pacific`, `latin_america`, `mea`)."""
    canon_country = canonicalize_country(country, exchange=exchange, symbol=symbol)
    if canon_country in _COUNTRY_TO_PRIMARY_ZONE:
        return _COUNTRY_TO_PRIMARY_ZONE[canon_country]
    exch = str(exchange or "").strip().upper()
    if exch == "EUFUND":
        return "europe"
    return ""


def normalize_market_zone_filter(raw_zone: str | None) -> str:
    """Normalise un code ou libellé de zone boursière pour le filtrage Screener."""
    raw = str(raw_zone or "").strip()
    if not raw:
        return ""
    key = _strip_accents_lower(raw).replace("-", "_").replace(" ", "_")
    aliases = {
        "eurozone": "eurozone",
        "zone_euro": "eurozone",
        "eur": "eurozone",
        "europe": "europe",
        "eu": "europe",
        "north_america": "north_america",
        "amerique_du_nord": "north_america",
        "us": "north_america",
        "na": "north_america",
        "asia_pacific": "asia_pacific",
        "asie_pacifique": "asia_pacific",
        "asia": "asia_pacific",
        "asie": "asia_pacific",
        "apac": "asia_pacific",
        "latin_america": "latin_america",
        "amerique_latine": "latin_america",
        "latam": "latin_america",
        "mea": "mea",
        "moyen_orient_afrique": "mea",
        "middle_east_africa": "mea",
    }
    return aliases.get(key, key if key in VALID_MARKET_ZONES else "")


def country_flag(country: str | None) -> str:
    """Retourne l'emoji drapeau associé au pays canonique."""
    return COUNTRY_FLAGS.get(str(country or "").strip(), "🌐")


def exchange_display_label(exchange: str | None) -> str:
    """Retourne un libellé lisible pour un code place boursière."""
    code = str(exchange or "").strip().upper()
    if not code:
        return ""
    return EXCHANGE_LABELS.get(code, code)


def format_market_zone_item(code: str, count: int) -> dict[str, Any]:
    meta = MARKET_ZONE_BY_CODE.get(code, {"code": code, "label": code, "flag": "🌐"})
    return {
        "code": code,
        "label": f"{meta['flag']} {meta['label']}",
        "name": meta["label"],
        "flag": meta["flag"],
        "count": count,
    }
