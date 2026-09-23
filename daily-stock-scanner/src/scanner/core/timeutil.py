"""Conventions temporelles : c'est ici que se joue l'absence de biais d'anticipation.

Conventions (voir ARCHITECTURE.md §4.2) :

* Un **prix de clôture** daté ``d`` est considéré disponible à ``d + 1 jour, 00:00 UTC``.
  Une décision prise « avant l'ouverture du jour D » (``as_of = D 00:00 UTC``) voit donc
  les clôtures jusqu'à ``D-1`` inclus, jamais celle de ``D``.
* Un **dépôt réglementaire** dont on connaît l'horodatage d'acceptation est disponible
  à cet horodatage. Si l'on ne connaît que la date de dépôt ``f``, il est disponible à
  ``f + 1 jour, 00:00 UTC`` (convention conservatrice).
* Si la date de publication est **inconnue**, on applique un décalage forfaitaire après
  la fin de période (``publication_lags_days`` de ``sources.yaml``) et on marque
  ``lag_estimated = True``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd

EXCHANGE_BY_REGION = {"US": "XNYS", "EU": "XPAR", "EM": "XNYS", "OTHER": "XNYS"}


def utc_midnight(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=UTC)


def as_of_for_run(run_date: date) -> datetime:
    """Horodatage de décision d'une exécution « avant ouverture » le jour ``run_date``."""
    return utc_midnight(run_date)


def price_available_at(d: date) -> datetime:
    """Instant où la clôture datée ``d`` devient utilisable."""
    return utc_midnight(d + timedelta(days=1))


def filing_available_at(filed: date, acceptance: datetime | None = None) -> datetime:
    """Instant où un dépôt devient utilisable (horodatage exact si connu, sinon J+1 00:00 UTC)."""
    if acceptance is not None:
        return acceptance if acceptance.tzinfo else acceptance.replace(tzinfo=UTC)
    return utc_midnight(filed + timedelta(days=1))


def estimated_available_at(period_end: date, lag_days: int) -> datetime:
    """Disponibilité estimée quand la date de publication réelle est inconnue."""
    return utc_midnight(period_end + timedelta(days=lag_days))


def last_visible_price_date(as_of: datetime) -> date:
    """Dernière date de clôture visible à ``as_of`` (inverse de :func:`price_available_at`)."""
    as_of_utc = as_of.astimezone(UTC)
    return as_of_utc.date() - timedelta(days=1)


def to_utc_timestamp(value: datetime | date | str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


@lru_cache(maxsize=8)
def _calendar(exchange: str) -> Any:
    import exchange_calendars as xcals

    return xcals.get_calendar(exchange)


def trading_days(start: date, end: date, exchange: str = "XNYS") -> pd.DatetimeIndex:
    """Séances de bourse entre ``start`` et ``end`` inclus (calendrier officiel de la place)."""
    cal = _calendar(exchange)
    lo = max(pd.Timestamp(start), cal.first_session)
    hi = min(pd.Timestamp(end), cal.last_session)
    if lo > hi:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(cal.sessions_in_range(lo, hi)).tz_localize(None)


def is_trading_day(d: date, exchange: str = "XNYS") -> bool:
    return len(trading_days(d, d, exchange)) == 1


def previous_trading_day(d: date, exchange: str = "XNYS") -> date:
    days = trading_days(d - timedelta(days=14), d - timedelta(days=1), exchange)
    if len(days) == 0:
        raise ValueError(f"aucune séance avant {d} sur {exchange}")
    return days[-1].date()


def next_trading_day(d: date, exchange: str = "XNYS") -> date:
    days = trading_days(d + timedelta(days=1), d + timedelta(days=14), exchange)
    if len(days) == 0:
        raise ValueError(f"aucune séance après {d} sur {exchange}")
    return days[0].date()


def rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    """Dernière séance de chaque période (semaine, mois, trimestre) présente dans ``index``."""
    if frequency == "daily":
        return index
    rule = {"weekly": "W-FRI", "monthly": "ME", "quarterly": "QE"}[frequency]
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(pd.Grouper(freq=rule)).last().dropna().to_numpy())
