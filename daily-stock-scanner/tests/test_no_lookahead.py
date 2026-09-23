"""Garantie anti-biais d'anticipation (principe non négociable n° 2).

Test d'« empoisonnement du futur » : on ajoute des données **postérieures** à ``as_of``
avec des valeurs absurdes (prix x1000, faits x1e6, publications fictives). Si un seul
signal ou score change, c'est qu'une information future a fuité dans le calcul.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from scanner.data.pit import PitView
from scanner.data.store import MarketData
from scanner.pipeline.engine import compute_signals, score_all_books

AS_OF = datetime(2021, 9, 1, tzinfo=UTC)


def _poison(data: MarketData, as_of: datetime) -> MarketData:
    cutoff = pd.Timestamp(as_of.date())
    px = data.prices
    future_px = px[px["date"] >= cutoff - pd.Timedelta(days=0)].copy()
    # 1) les prix futurs deviennent absurdes
    future_px[["open", "high", "low", "close", "adj_close"]] *= 1000.0
    future_px["volume"] *= 50.0
    # 2) des prix à la date exacte de décision (clôture du jour J, non visible avant l'ouverture)
    same_day = px[px["date"] == px[px["date"] < cutoff]["date"].max()].copy()
    same_day["date"] = cutoff
    same_day[["close", "adj_close"]] *= 777.0
    prices = pd.concat([px[px["date"] < cutoff], future_px, same_day], ignore_index=True)
    prices = prices.drop_duplicates(subset=["symbol", "date"], keep="last")

    ts = pd.Timestamp(as_of)
    f = data.facts
    # 3) retraitements absurdes publiés APRÈS as_of pour des périodes passées
    restated = f[f["available_at"] <= ts].copy()
    restated["value"] *= 1e6
    restated["available_at"] = ts + pd.Timedelta(seconds=1)
    restated["accession"] = "POISON"
    facts = pd.concat([f, restated], ignore_index=True)

    # 4) publications de résultats fictives juste après as_of
    ev = data.events
    fake = ev.drop_duplicates("symbol").copy()
    fake["event_time"] = ts + pd.Timedelta(hours=1)
    fake["available_at"] = ts + pd.Timedelta(hours=1)
    events = pd.concat([ev, fake], ignore_index=True)
    return MarketData(prices=prices, facts=facts, events=events, securities=data.securities)


@pytest.fixture(scope="module")
def clean_and_poisoned(small_market, config):
    clean_view = PitView(small_market.data, AS_OF)
    syms = clean_view.listed_symbols()
    clean = compute_signals(clean_view, syms, config)
    poisoned_view = PitView(_poison(small_market.data, AS_OF), AS_OF)
    poisoned = compute_signals(poisoned_view, syms, config)
    return clean, poisoned


def test_signals_unchanged_by_future_data(clean_and_poisoned):
    clean, poisoned = clean_and_poisoned
    num = clean.values.select_dtypes("number").columns
    pd.testing.assert_frame_equal(
        clean.values[num], poisoned.values[num], check_exact=False, rtol=1e-12, atol=1e-12
    )


def test_scores_unchanged_by_future_data(clean_and_poisoned, config):
    clean, poisoned = clean_and_poisoned
    a = score_all_books(clean, config)
    b = score_all_books(poisoned, config)
    for book in a:
        pd.testing.assert_series_equal(a[book].composite, b[book].composite)


def test_poison_would_be_detected_if_it_leaked(small_market, config):
    """Contrôle du test lui-même : sans PitView (as_of plus tardif), le poison est visible."""
    later = datetime(2021, 9, 10, tzinfo=UTC)
    view = PitView(_poison(small_market.data, AS_OF), later)
    syms = view.listed_symbols()[:10]
    sig = compute_signals(view, syms, config)
    assert (sig.values["last_close"] > 1000).any()


def test_listed_symbols_exclude_future_ipos(small_market):
    view = PitView(small_market.data, AS_OF)
    sec = small_market.data.securities.set_index("symbol")
    for s in view.listed_symbols():
        assert sec.loc[s, "listed_from"] <= pd.Timestamp(AS_OF.date())
    assert np.all(
        [
            pd.isna(sec.loc[s, "delisted_on"])
            or sec.loc[s, "delisted_on"] > pd.Timestamp("2021-08-31")
            for s in view.listed_symbols()
        ]
    )
