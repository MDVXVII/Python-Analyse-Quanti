"""Compositions d'indices : fichiers locaux et Wikipédia (repli gratuit).

Ordre de priorité défini dans ``sources.yaml`` (``priority.constituents``) : EODHD si
une clé est disponible, puis fichiers locaux ``config/universe/<INDICE>.csv``, puis
Wikipédia (S&P 500 et Nasdaq-100 uniquement : les tableaux du STOXX 600 et du SBF 120
n'y sont pas assez fiables).

Limite : ce sont des compositions **actuelles**. Le backtest n'en dépend pas (il utilise
un univers défini par des règles à chaque date, ARCHITECTURE.md §3.2).
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

from scanner.core.logging import get_logger
from scanner.data.providers.base import ProviderError

log = get_logger(__name__)

WIKIPEDIA_PAGES = {
    "SP500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "NDX100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}


class LocalCsvConstituents:
    """Lit ``<dir>/<INDICE>.csv`` (colonne ``symbol`` au format interne ``TICKER.PLACE``)."""

    name = "local_csv"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get_constituents(self, index_id: str) -> list[str]:
        path = self.directory / f"{index_id}.csv"
        if not path.exists():
            raise ProviderError(f"fichier de composition absent : {path}")
        df = pd.read_csv(path, comment="#")
        if "symbol" not in df.columns:
            raise ProviderError(f"{path} : colonne 'symbol' requise")
        return sorted({str(s).strip() for s in df["symbol"].dropna() if str(s).strip()})


def parse_wikipedia_table(html: str) -> list[str]:
    """Extrait les tickers US du premier tableau ayant une colonne ``Symbol`` ou ``Ticker``."""
    for table in pd.read_html(StringIO(html)):
        cols = {str(c).strip().lower(): c for c in table.columns}
        col = cols.get("symbol") or cols.get("ticker")
        if col is None:
            continue
        tickers = [str(t).strip().upper().replace(".", "-") for t in table[col].dropna()]
        tickers = [t for t in tickers if t and t.replace("-", "").isalnum()]
        if len(tickers) >= 90:
            return sorted({f"{t}.US" for t in tickers})
    raise ProviderError("aucun tableau de composition exploitable trouvé")


class WikipediaConstituents:
    name = "wikipedia"

    def __init__(self, user_agent: str = "daily-stock-scanner (projet personnel)") -> None:
        self.user_agent = user_agent

    def get_constituents(self, index_id: str) -> list[str]:
        url = WIKIPEDIA_PAGES.get(index_id)
        if url is None:
            raise ProviderError(f"pas de page Wikipédia fiable pour {index_id}")
        r = httpx.get(
            url, headers={"User-Agent": self.user_agent}, timeout=30, follow_redirects=True
        )
        r.raise_for_status()
        return parse_wikipedia_table(r.text)
