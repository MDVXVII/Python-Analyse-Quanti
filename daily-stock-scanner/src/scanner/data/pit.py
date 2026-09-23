"""Vue point-in-time : l'unique porte d'accès aux données pour le calcul des signaux.

``PitView(data, as_of)`` ne laisse passer que ce qui était **publiquement disponible**
à l'instant ``as_of`` :

* prix : dates ``<= last_visible_price_date(as_of)`` (clôture de la veille au plus tard) ;
* faits fondamentaux : ``available_at <= as_of`` ;
* événements : ``available_at <= as_of`` ;
* référentiel : titres cotés à ``as_of`` (dates de cotation et de radiation si connues).

Toute fonction de signal reçoit une ``PitView`` et jamais les données brutes : c'est ce
qui rend les tests « d'empoisonnement du futur » (tests/test_no_lookahead.py) significatifs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from scanner.core.timeutil import last_visible_price_date
from scanner.data.store import MarketData


class PitView:
    def __init__(self, data: MarketData, as_of: datetime) -> None:
        if as_of.tzinfo is None:
            raise ValueError("as_of doit être un datetime avec fuseau (UTC)")
        self._data = data
        self.as_of = as_of.astimezone(UTC)
        self.as_of_ts = pd.Timestamp(self.as_of)
        self.last_price_date: date = last_visible_price_date(self.as_of)
        self._cache: dict[str, pd.DataFrame] = {}

    # -- prix ----------------------------------------------------------------------------
    def panel(self, column: str = "adj_close", lookback: int | None = None) -> pd.DataFrame:
        """Panel (dates x symboles) jusqu'à la dernière clôture visible (``lookback`` séances)."""
        key = f"panel:{column}"
        if key not in self._cache:
            full = self._data.panel(column)
            if full.empty:
                self._cache[key] = full
            else:
                cutoff = pd.Timestamp(self.last_price_date)
                self._cache[key] = full.loc[full.index <= cutoff]
        p = self._cache[key]
        return p.iloc[-lookback:] if lookback is not None else p

    # -- fondamentaux et événements -------------------------------------------------------
    def facts(self) -> pd.DataFrame:
        if "facts" not in self._cache:
            f = self._data.slim_facts() if not self._data.facts.empty else self._data.facts
            self._cache["facts"] = f.loc[f["available_at"] <= self.as_of_ts] if not f.empty else f
        return self._cache["facts"]

    def events(self, event_types: list[str] | None = None) -> pd.DataFrame:
        if "events" not in self._cache:
            e = self._data.events
            self._cache["events"] = e.loc[e["available_at"] <= self.as_of_ts] if not e.empty else e
        e = self._cache["events"]
        if event_types is not None and not e.empty:
            e = e.loc[e["event_type"].isin(event_types)]
        return e

    # -- référentiel -----------------------------------------------------------------------
    def securities(self) -> pd.DataFrame:
        s = self._data.securities
        if s.empty:
            return s
        day = pd.Timestamp(self.last_price_date)
        mask = pd.Series(True, index=s.index)
        if "listed_from" in s.columns:
            mask &= s["listed_from"].isna() | (s["listed_from"] <= day)
        if "delisted_on" in s.columns:
            mask &= s["delisted_on"].isna() | (s["delisted_on"] > day)
        return s.loc[mask].reset_index(drop=True)

    def listed_symbols(self) -> list[str]:
        """Titres cotés à ``as_of`` et disposant d'au moins un prix visible."""
        sec = self.securities()
        px = self.panel("close")
        if px.empty:
            return []
        have_price = set(px.columns[px.notna().any()])
        return sorted(set(sec["symbol"].astype(str)) & have_price)
