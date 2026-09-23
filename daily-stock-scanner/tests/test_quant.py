"""Tests du Module 3 sur des séries de prix construites à la main."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from scanner.data.pit import PitView
from scanner.data.store import MarketData
from scanner.quant.signals import compute_quant_signals, residual_momentum

DATES = pd.bdate_range("2020-01-01", periods=900)
AS_OF = datetime.combine((DATES[-1] + pd.Timedelta(days=1)).date(), datetime.min.time(), tzinfo=UTC)


def _market(
    series: dict[str, np.ndarray],
    volume: dict[str, np.ndarray] | None = None,
    events: pd.DataFrame | None = None,
    sectors: dict[str, str] | None = None,
) -> MarketData:
    rows = []
    for sym, px in series.items():
        vol = volume[sym] if volume and sym in volume else np.full(len(px), 1e6)
        rows.append(
            pd.DataFrame(
                {
                    "symbol": sym,
                    "date": DATES,
                    "close": px,
                    "adj_close": px,
                    "open": px,
                    "high": px * 1.01,
                    "low": px * 0.99,
                    "volume": vol,
                }
            )
        )
    prices = pd.concat(rows, ignore_index=True)
    sec = pd.DataFrame(
        {
            "symbol": list(series),
            "country": "US",
            "currency": "USD",
            "sector": [(sectors or {}).get(s, "Industrials") for s in series],
        }
    )
    ev = (
        events
        if events is not None
        else pd.DataFrame(columns=["symbol", "event_type", "event_time", "available_at"])
    )
    return MarketData(prices=prices, facts=pd.DataFrame(), events=ev, securities=sec)


def _flat(n=900, value=100.0):
    return np.full(n, value)


def test_momentum_12_1_skips_last_month():
    px = _flat()
    px[-253:-21] = np.linspace(100, 150, 232)  # +50 % entre t-252 et t-21
    px[-21:] = 80.0  # chute le dernier mois : ignorée
    q = compute_quant_signals(PitView(_market({"A.US": px, "B.US": _flat()}), AS_OF))
    assert q.loc["A.US", "Q-MOM-12-1"] == pytest.approx(150 / 100 - 1, rel=1e-3)
    assert q.loc["B.US", "Q-MOM-12-1"] == pytest.approx(0.0)
    assert q.loc["A.US", "Q-STREV"] == pytest.approx(80 / 150 - 1, rel=1e-3)


def test_52w_high_and_low_vol():
    rng = np.random.default_rng(0)
    calm = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, 900)))
    wild = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 900)))
    q = compute_quant_signals(PitView(_market({"C.US": calm, "W.US": wild}), AS_OF))
    assert q.loc["C.US", "Q-LOWVOL"] < q.loc["W.US", "Q-LOWVOL"]
    assert q.loc["C.US", "Q-LOWVOL"] == pytest.approx(0.005 * np.sqrt(252), rel=0.15)
    assert 0 < q.loc["W.US", "Q-52WH"] <= 1


def test_abnormal_volume():
    vol = np.full(900, 1e6)
    vol[-5:] = 3e6
    q = compute_quant_signals(
        PitView(_market({"V.US": _flat(), "N.US": _flat()}, volume={"V.US": vol}), AS_OF)
    )
    assert q.loc["V.US", "Q-ABVOL"] == pytest.approx(np.log(3))
    assert q.loc["N.US", "Q-ABVOL"] == pytest.approx(0)


def test_trend_template_uptrend_scores_eight():
    up = 50 * np.exp(0.002 * np.arange(900))  # +65 % par an : critères de Minervini tenus
    down = 200 * np.exp(-0.002 * np.arange(900))
    q = compute_quant_signals(PitView(_market({"U.US": up, "D.US": down, "F.US": _flat()}), AS_OF))
    assert q.loc["U.US", "Q-TREND"] == 8
    assert q.loc["D.US", "Q-TREND"] <= 1


def test_earnings_reaction_after_close_uses_next_day():
    px = _flat()
    day0 = len(DATES) - 10
    px[day0:] = 110.0  # +10 % le lendemain d'une publication après la clôture
    release = pd.Timestamp(DATES[day0 - 1]).tz_localize("UTC") + pd.Timedelta(hours=21)
    ev = pd.DataFrame(
        {
            "symbol": ["E.US"],
            "event_type": ["earnings_release"],
            "event_time": [release],
            "available_at": [release],
        }
    )
    q = compute_quant_signals(PitView(_market({"E.US": px, "M.US": _flat()}, events=ev), AS_OF))
    # marché équipondéré (E et M) : +5 % ; rendement anormal ≈ 1.10/1.05 - 1
    assert q.loc["E.US", "Q-EAR"] == pytest.approx(1.10 / 1.05 - 1, rel=1e-6)
    assert np.isnan(q.loc["M.US", "Q-EAR"])


def test_earnings_reaction_not_visible_before_release():
    px = _flat()
    release = pd.Timestamp(DATES[-1]).tz_localize("UTC") + pd.Timedelta(days=5)  # futur
    ev = pd.DataFrame(
        {
            "symbol": ["E.US"],
            "event_type": ["earnings_release"],
            "event_time": [release],
            "available_at": [release],
        }
    )
    q = compute_quant_signals(PitView(_market({"E.US": px, "M.US": _flat()}, events=ev), AS_OF))
    assert np.isnan(q.loc["E.US", "Q-EAR"])


def test_residual_momentum_detects_idiosyncratic_drift():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2019-01-01", periods=900)
    mkt = rng.normal(0.0004, 0.01, 900)
    cols = {}
    for k in range(12):
        cols[f"S{k}.US"] = 100 * np.exp(np.cumsum(mkt + rng.normal(0, 0.01, 900)))
    # Surperformance idiosyncratique RÉCENTE (12 derniers mois seulement) : c'est ce que mesure
    # le momentum résiduel. Une dérive constante serait absorbée par la constante de la régression.
    alpha = np.zeros(900)
    alpha[-260:] = 0.004  # ≈ +8 %/mois : nettement au-dessus du bruit (écart-type mensuel ≈ 4,6 %)
    drift = mkt + rng.normal(0, 0.01, 900) + alpha
    cols["D.US"] = 100 * np.exp(np.cumsum(drift))
    adj = pd.DataFrame(cols, index=idx)
    rm = residual_momentum(adj, pd.Series("US", index=adj.columns))
    assert rm["D.US"] == rm.max() and rm["D.US"] > 2


def test_industry_momentum_is_group_median():
    px = {f"T{k}.US": np.linspace(100, 100 + 10 * k, 900) for k in range(6)}
    q = compute_quant_signals(PitView(_market(px), AS_OF))
    assert q["Q-INDMOM"].nunique() == 1
    assert q["Q-INDMOM"].iloc[0] == pytest.approx(q["Q-MOM-6-1"].median())
