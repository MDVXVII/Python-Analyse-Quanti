"""Convention de symboles interne et conversions vers les fournisseurs.

Symbole interne : ``TICKER.PLACE`` avec les codes de place d'EODHD (ex. ``AAPL.US``,
``MC.PA``, ``SAP.XETRA``, ``BRK-B.US``). Les classes d'actions utilisent un tiret.
"""

from __future__ import annotations

# code de place interne -> (suffixe Yahoo, pays par défaut, devise par défaut)
EXCHANGES: dict[str, tuple[str, str, str]] = {
    "US": ("", "US", "USD"),
    "PA": (".PA", "FR", "EUR"),
    "XETRA": (".DE", "DE", "EUR"),
    "F": (".F", "DE", "EUR"),
    "AS": (".AS", "NL", "EUR"),
    "BR": (".BR", "BE", "EUR"),
    "LS": (".LS", "PT", "EUR"),
    "MI": (".MI", "IT", "EUR"),
    "MC": (".MC", "ES", "EUR"),
    "VI": (".VI", "AT", "EUR"),
    "IR": (".IR", "IE", "EUR"),
    "HE": (".HE", "FI", "EUR"),
    "LSE": (".L", "GB", "GBP"),
    "SW": (".SW", "CH", "CHF"),
    "ST": (".ST", "SE", "SEK"),
    "CO": (".CO", "DK", "DKK"),
    "OL": (".OL", "NO", "NOK"),
    "WAR": (".WA", "PL", "PLN"),
}
_YAHOO_TO_INTERNAL = {suffix: code for code, (suffix, _, _) in EXCHANGES.items() if suffix}


def split(symbol: str) -> tuple[str, str]:
    """``"MC.PA"`` -> ``("MC", "PA")``. Lève ``ValueError`` si la place est absente."""
    if "." not in symbol:
        raise ValueError(f"symbole sans place : {symbol!r} (attendu TICKER.PLACE)")
    ticker, exch = symbol.rsplit(".", 1)
    return ticker, exch.upper()


def to_yahoo(symbol: str) -> str:
    ticker, exch = split(symbol)
    suffix = EXCHANGES.get(exch, ("." + exch, "", ""))[0]
    return f"{ticker}{suffix}"


def from_yahoo(yahoo_symbol: str) -> str:
    for suffix, code in _YAHOO_TO_INTERNAL.items():
        if yahoo_symbol.upper().endswith(suffix.upper()):
            return f"{yahoo_symbol[: -len(suffix)]}.{code}"
    return f"{yahoo_symbol.replace('.', '-')}.US"


def to_eodhd(symbol: str) -> str:
    return symbol  # la convention interne est celle d'EODHD


def us_ticker(symbol: str) -> str:
    """Ticker US tel qu'utilisé par la SEC (``BRK-B.US`` -> ``BRK-B``)."""
    ticker, exch = split(symbol)
    if exch != "US":
        raise ValueError(f"{symbol} n'est pas un titre US")
    return ticker


def default_country(symbol: str) -> str | None:
    _, exch = split(symbol)
    return EXCHANGES.get(exch, ("", None, None))[1]


def default_currency(symbol: str) -> str | None:
    _, exch = split(symbol)
    return EXCHANGES.get(exch, ("", None, None))[2]
