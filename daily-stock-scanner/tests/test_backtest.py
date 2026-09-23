"""Tests du Module 9 : moteur de portefeuille, IC, métriques, walk-forward, protocole."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from scanner.backtest.costs import CostModel
from scanner.backtest.engine import PortfolioSpec, run_backtest
from scanner.backtest.ic import forward_returns, ic_summary, rank_ic
from scanner.backtest.metrics import (
    deflated_sharpe,
    max_drawdown,
    newey_west_tstat,
    probabilistic_sharpe,
    sharpe,
)
from scanner.backtest.walkforward import expanding_splits, shrunk_ic_weights

DAYS = pd.bdate_range("2020-01-01", periods=60)


def _adj(daily: dict[str, float], n: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        {s: 100 * (1 + r) ** np.arange(n) for s, r in daily.items()}, index=DAYS[:n]
    )


def test_long_leg_tracks_selected_stock_without_costs():
    adj = _adj({"UP.US": 0.01, "DOWN.US": -0.01})
    scores = {DAYS[0]: pd.Series({"UP.US": 1.0, "DOWN.US": -1.0})}
    res = run_backtest(scores, adj, PortfolioSpec(top_n=1, long_short=True, lag_days=1))
    # exécution à la clôture de J+1, rendements à partir de J+2
    assert res.long.returns.index[0] == DAYS[2]
    np.testing.assert_allclose(res.long.returns.to_numpy(), 0.01)
    np.testing.assert_allclose(res.short.returns.to_numpy(), -0.01)
    np.testing.assert_allclose(res.long_short.to_numpy(), 0.02)


def test_costs_are_charged_at_rebalance(config):
    adj = _adj({"A.US": 0.0, "B.US": 0.0})
    meta_idx = pd.Index(["A.US", "B.US"])
    costs = CostModel(
        config.costs,
        pd.Series("US", index=meta_idx),
        pd.Series("US", index=meta_idx),
        pd.Series(1e8, index=meta_idx),
    )
    scores = {
        DAYS[0]: pd.Series({"A.US": 1.0, "B.US": 0.0}),
        DAYS[10]: pd.Series({"A.US": 0.0, "B.US": 1.0}),
    }
    res = run_backtest(scores, adj, PortfolioSpec(top_n=1, long_short=False), costs)
    buy_bps = config.costs.commission_bps["US"] + 2  # tranche de volume la plus liquide
    first = res.long.returns.loc[DAYS[1]] if DAYS[1] in res.long.returns.index else None
    assert first is None  # le premier jour d'exécution sert de base
    # deuxième rebalancement : vente de A et achat de B -> 2 x (courtage + demi-spread)
    cost_day = res.long.returns.loc[DAYS[11]]
    assert cost_day == pytest.approx(-2 * buy_bps / 1e4, rel=1e-6)
    assert res.long.turnover.loc[DAYS[11]] == pytest.approx(1.0)


def test_french_ftt_applies_on_buys_only(config):
    idx = pd.Index(["MC.PA"])
    c = CostModel(
        config.costs,
        pd.Series("EU", index=idx),
        pd.Series("FR", index=idx),
        pd.Series(1e8, index=idx),
        pd.Series(True, index=idx),
    )
    buy = c.rebalance_cost(pd.Series({"MC.PA": 1.0}))
    sell = c.rebalance_cost(pd.Series({"MC.PA": -1.0}))
    assert buy - sell == pytest.approx(0.004)


def test_delisted_stock_is_sold_with_delisting_return():
    adj = _adj({"A.US": 0.0, "B.US": 0.0})
    adj.loc[DAYS[20] :, "A.US"] = np.nan  # radiation
    scores = {DAYS[0]: pd.Series({"A.US": 1.0, "B.US": 0.0})}
    res = run_backtest(scores, adj, PortfolioSpec(top_n=1, long_short=False), delisting_return=-0.3)
    assert res.long.returns.loc[DAYS[20]] == pytest.approx(-0.3)
    assert (res.long.returns.loc[DAYS[21] :] == 0).all()  # liquidités ensuite


def test_forward_returns_skip_decision_close_and_keep_delisted():
    adj = _adj({"A.US": 0.01}, n=40)
    adj.iloc[5, 0] = adj.iloc[5, 0] * 2  # saut le jour de décision : ne doit pas compter
    fwd = forward_returns(adj, [DAYS[5]], horizon=5, lag_days=1)
    expected = adj.iloc[11, 0] / adj.iloc[6, 0] - 1
    assert fwd.loc[DAYS[5], "A.US"] == pytest.approx(expected)
    adj2 = adj.copy()
    adj2.iloc[8:, 0] = np.nan
    fwd2 = forward_returns(adj2, [DAYS[5]], horizon=5, lag_days=1, delisting_return=-0.5)
    assert fwd2.loc[DAYS[5], "A.US"] == pytest.approx((adj.iloc[7, 0] / adj.iloc[6, 0]) * 0.5 - 1)


def test_rank_ic_perfect_and_inverse():
    d = pd.Timestamp("2020-01-31")
    s = pd.DataFrame([np.arange(20.0)], index=[d], columns=[f"S{i}" for i in range(20)])
    assert rank_ic(s, s * 2).iloc[0] == pytest.approx(1.0)
    assert rank_ic(s, -s).iloc[0] == pytest.approx(-1.0)


def test_newey_west_equals_classic_t_without_lags():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0.1, 1, 500))
    classic = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    assert newey_west_tstat(x, 0) == pytest.approx(classic, rel=1e-9)
    # l'autocorrélation positive réduit le t
    ar = pd.Series(np.convolve(rng.normal(0.05, 1, 520), np.ones(20) / 20, mode="valid"))
    assert abs(newey_west_tstat(ar, 19)) < abs(newey_west_tstat(ar, 0))


def test_sharpe_psr_and_deflated_sharpe():
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.0008, 0.01, 2000))
    assert sharpe(r) == pytest.approx(r.mean() / r.std() * np.sqrt(252))
    sr = r.mean() / r.std()
    assert probabilistic_sharpe(sr, len(r), 0.0, 3.0, sr) == pytest.approx(0.5)
    # plus d'essais -> seuil plus exigeant -> DSR plus faible
    assert deflated_sharpe(r, 100) < deflated_sharpe(r, 1)


def test_max_drawdown():
    r = pd.Series([0.1, -0.5, 0.2])
    assert max_drawdown(r) == pytest.approx(-0.5)


def test_ic_summary_counts():
    ic = pd.Series(
        [0.05, 0.02, -0.01, 0.04], index=pd.date_range("2020-01-31", periods=4, freq="ME")
    )
    s = ic_summary(ic, horizon_days=21, spacing_days=21)
    assert s["n_dates"] == 4 and s["ic_hit"] == 0.75


def test_walk_forward_splits_never_overlap():
    dates = pd.date_range("2010-01-31", "2020-12-31", freq="ME")
    splits = expanding_splits(dates, min_train_years=3)
    for sp in splits:
        assert sp.train_end < sp.test_start
    starts = [sp.test_start for sp in splits]
    assert starts == sorted(starts)


def test_shrunk_weights():
    w = shrunk_ic_weights(pd.Series({"a": 0.04, "b": -0.02, "c": 0.0}), shrink=0.5)
    assert w.sum() == pytest.approx(1.0)
    assert w["a"] > w["c"] == w["b"]
    eq = shrunk_ic_weights(pd.Series({"a": -0.01, "b": -0.02}))
    assert (eq == 0.5).all()


@pytest.mark.slow
def test_protocol_detects_planted_signal_and_rejects_noise(config):
    """Contrôle du protocole : signal planté détecté ; aucun signal promu sur du bruit pur."""
    from scanner.backtest.validation import ValidationSettings, run_validation
    from scanner.data.providers.synthetic import SyntheticSpec, generate

    vs = ValidationSettings(
        region="US",
        start=date(2013, 6, 1),
        end=date(2020, 12, 31),
        oos_start=date(2016, 1, 1),
        data_label="synthétique (test)",
        survivorship_free=True,
        horizons=(21, 63),
        min_oos_dates=24,
    )
    planted = generate(
        SyntheticSpec(
            n_securities=90,
            start=date(2012, 1, 1),
            end=date(2021, 6, 30),
            seed=21,
            quality_premium=0.15,
            drift_sd_daily=0.0,
            eu_share=0.0,
        )
    )
    res = run_validation(planted.data, config, vs)
    v = {x.signal: x for x in res.verdicts}
    assert v["F-GP"].decision.startswith("PROMOUVOIR")

    noise = generate(
        SyntheticSpec(
            n_securities=90,
            start=date(2012, 1, 1),
            end=date(2021, 6, 30),
            seed=22,
            quality_premium=0.0,
            drift_sd_daily=0.0,
            eu_share=0.0,
        )
    )
    res0 = run_validation(noise.data, config, vs)
    promoted = [x.signal for x in res0.verdicts if x.decision.startswith("PROMOUVOIR")]
    # ~30 signaux testés à t >= 2 : quelques faux positifs sont possibles par hasard, pas plus.
    assert len(promoted) <= 3, promoted
