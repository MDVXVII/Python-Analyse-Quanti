"""Référentiels : secteurs (11 secteurs de type GICS), régions et pays.

La classification GICS est propriétaire (MSCI / S&P). On ramène les classifications des
fournisseurs (yfinance, EODHD, codes SIC de la SEC) à 11 secteurs homogènes. C'est une
approximation documentée (ARCHITECTURE.md §15) : le secteur utilisé est le secteur actuel,
non historisé.
"""

from __future__ import annotations

SECTORS: tuple[str, ...] = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
)

_ALIASES: dict[str, str] = {
    # yfinance (classification Morningstar)
    "technology": "Information Technology",
    "financial services": "Financials",
    "healthcare": "Health Care",
    "consumer cyclical": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "basic materials": "Materials",
    "communication services": "Communication Services",
    "industrials": "Industrials",
    "energy": "Energy",
    "utilities": "Utilities",
    "real estate": "Real Estate",
    # GICS / EODHD
    "information technology": "Information Technology",
    "financials": "Financials",
    "health care": "Health Care",
    "consumer discretionary": "Consumer Discretionary",
    "consumer staples": "Consumer Staples",
    "materials": "Materials",
    "telecommunication services": "Communication Services",
}


def normalize_sector(raw: str | None) -> str | None:
    """Ramène un libellé de secteur fournisseur à l'un des 11 secteurs ; ``None`` si inconnu."""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key or key in {"nan", "none", "n/a", "other"}:
        return None
    if key in _ALIASES:
        return _ALIASES[key]
    for sector in SECTORS:
        if key == sector.lower():
            return sector
    return None


# Correspondance approximative code SIC → secteur (plages de la classification SIC).
# Sert uniquement de repli quand aucun fournisseur ne donne de secteur.
_SIC_RANGES: tuple[tuple[int, int, str], ...] = (
    (100, 999, "Consumer Staples"),  # agriculture
    (1000, 1299, "Materials"),  # mines métalliques, charbon
    (1300, 1399, "Energy"),  # pétrole et gaz
    (1400, 1499, "Materials"),
    (1500, 1799, "Industrials"),  # construction
    (2000, 2199, "Consumer Staples"),  # alimentation, tabac
    (2200, 2399, "Consumer Discretionary"),  # textile, habillement
    (2400, 2499, "Materials"),  # bois
    (2500, 2599, "Consumer Discretionary"),  # meubles
    (2600, 2699, "Materials"),  # papier
    (2700, 2799, "Communication Services"),  # édition
    (2800, 2829, "Materials"),  # chimie
    (2830, 2836, "Health Care"),  # pharmacie
    (2837, 2899, "Materials"),
    (2900, 2999, "Energy"),  # raffinage
    (3000, 3299, "Materials"),
    (3300, 3399, "Materials"),  # métallurgie
    (3400, 3569, "Industrials"),
    (3570, 3579, "Information Technology"),  # ordinateurs
    (3580, 3599, "Industrials"),
    (3600, 3699, "Information Technology"),  # électronique
    (3700, 3799, "Consumer Discretionary"),  # automobile (aéro corrigé ci-dessous)
    (3720, 3729, "Industrials"),  # aéronautique
    (3800, 3849, "Health Care"),  # instruments médicaux
    (3850, 3899, "Industrials"),
    (3900, 3999, "Consumer Discretionary"),
    (4000, 4799, "Industrials"),  # transport
    (4800, 4899, "Communication Services"),  # télécoms
    (4900, 4999, "Utilities"),
    (5000, 5199, "Industrials"),  # commerce de gros
    (5200, 5999, "Consumer Discretionary"),  # commerce de détail
    (5400, 5499, "Consumer Staples"),  # alimentaire de détail
    (6000, 6499, "Financials"),
    (6500, 6599, "Real Estate"),
    (6700, 6799, "Financials"),
    (6798, 6798, "Real Estate"),  # REIT
    (7000, 7299, "Consumer Discretionary"),  # hôtellerie, services aux personnes
    (7370, 7379, "Information Technology"),  # logiciels et services informatiques
    (7300, 7369, "Industrials"),  # services aux entreprises
    (7380, 7399, "Industrials"),
    (7800, 7999, "Communication Services"),  # divertissement
    (8000, 8099, "Health Care"),
    (8100, 8999, "Industrials"),
)


def sector_from_sic(sic: int | str | None) -> str | None:
    """Secteur approximatif à partir d'un code SIC (la plage la plus étroite l'emporte)."""
    if sic is None or sic == "":
        return None
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    best: tuple[int, str] | None = None
    for lo, hi, sector in _SIC_RANGES:
        if lo <= code <= hi:
            width = hi - lo
            if best is None or width < best[0]:
                best = (width, sector)
    return best[1] if best else None


EU_EEA_COUNTRIES: frozenset[str] = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
        "IS",
        "LI",
        "NO",
    }
)
# Europe développée hors UE/EEE, incluse dans le STOXX Europe 600.
OTHER_EUROPE: frozenset[str] = frozenset({"GB", "CH", "JE", "GG", "IM"})
DEVELOPED_OTHER: frozenset[str] = frozenset({"US", "CA", "JP", "AU", "NZ", "HK", "SG", "IL"})


def region_of(country: str | None) -> str:
    """Région d'analyse : ``US``, ``EU`` (Europe développée), ``EM`` ou ``OTHER``."""
    if not country:
        return "OTHER"
    c = country.upper()
    if c == "US":
        return "US"
    if c in EU_EEA_COUNTRIES or c in OTHER_EUROPE:
        return "EU"
    if c in DEVELOPED_OTHER:
        return "OTHER"
    return "EM"
