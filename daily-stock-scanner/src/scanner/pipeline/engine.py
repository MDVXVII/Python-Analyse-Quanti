"""Moteur de calcul commun au pipeline quotidien et au backtest.

``compute_signals`` assemble les Modules 2 et 3 à une date ; ``score_all_books`` applique
le Module 8. Le backtest appelle exactement les mêmes fonctions que le rapport quotidien :
ce qui est validé est bien ce qui est utilisé.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scanner.core.config import BOOK_IDS, AppConfig, BookId
from scanner.data.fx import fx_to_usd
from scanner.data.pit import PitView
from scanner.fundamentals.signals import compute_fundamental_signals
from scanner.quant.signals import compute_quant_signals
from scanner.scoring.composite import BookScores, score_book


@dataclass
class SignalSet:
    values: pd.DataFrame  # symbole x (signaux + champs de contrôle)
    meta: pd.DataFrame  # secteur, région, liquidité…
    fx: dict[str, float]
    fx_fallback_used: list[str]


def compute_signals(
    view: PitView, symbols: list[str], config: AppConfig, liquidity: pd.DataFrame | None = None
) -> SignalSet:
    """Signaux quant + fondamentaux pour ``symbols`` à ``view.as_of``.

    ``liquidity`` (optionnel) : ``passes_liquidity`` / ``liquidity_note`` issus de l'univers
    live. À défaut, le filtre est recalculé à partir du volume et du prix.
    """
    ccys = sorted({str(c) for c in view.securities()["currency"].dropna()})
    fx, fallback = fx_to_usd(view, config.settings.market.fx_fallback_to_usd, ccys)
    quant = compute_quant_signals(view, symbols, fx)
    fund = compute_fundamental_signals(view, config.settings.fundamentals, symbols)
    values = quant.join(
        fund.drop(columns=[c for c in fund.columns if c in quant.columns]), how="left"
    )
    liq = config.settings.universe.liquidity
    meta = pd.DataFrame(index=values.index)
    meta["sector"] = values["sector"]
    meta["region"] = values["region"]
    meta["adv60_usd"] = values["adv60_usd"]
    if liquidity is not None:
        meta["passes_liquidity"] = liquidity["passes_liquidity"].reindex(values.index).fillna(False)
        meta["liquidity_note"] = liquidity["liquidity_note"].reindex(values.index).fillna("")
    else:
        ok = (values["adv60_usd"] >= liq.min_adv_usd) & (
            values["last_close_usd"] >= liq.min_price_usd
        )
        meta["passes_liquidity"] = ok.fillna(False)
        meta["liquidity_note"] = np.where(ok.fillna(False), "", "volume ou prix insuffisant")
    return SignalSet(values=values, meta=meta, fx=fx, fx_fallback_used=fallback)


def upcoming_event_days(
    view: PitView,
    symbols: list[str],
    exchange_days: pd.DatetimeIndex | None = None,
    horizon_days: int = 15,
) -> pd.Series:
    """Nombre de séances jusqu'à la prochaine publication programmée connue à ``as_of``."""
    ev = view.events(["earnings_scheduled"])
    if ev.empty:
        return pd.Series(np.nan, index=symbols, dtype=float)
    start = pd.Timestamp(view.as_of).tz_convert("UTC")
    ev = ev[(ev["event_time"] >= start) & ev["symbol"].isin(symbols)]
    if ev.empty:
        return pd.Series(np.nan, index=symbols, dtype=float)
    nxt = ev.sort_values("event_time").groupby("symbol")["event_time"].first()
    base = start.tz_localize(None).normalize()
    days = nxt.map(lambda t: float(np.busday_count(base.date(), t.tz_convert("UTC").date())))
    return days[days <= horizon_days].reindex(symbols)


def score_all_books(
    signals: SignalSet,
    config: AppConfig,
    upcoming: pd.Series | None = None,
    books: tuple[BookId, ...] = BOOK_IDS,
) -> dict[BookId, BookScores]:
    return {b: score_book(b, signals.values, signals.meta, config, upcoming) for b in books}
