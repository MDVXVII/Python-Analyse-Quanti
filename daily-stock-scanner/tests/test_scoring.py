from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from scanner.data.pit import PitView
from scanner.pipeline.engine import compute_signals, score_all_books
from scanner.scoring.composite import changes_vs_previous, score_book, select_ideas
from scanner.scoring.normalize import rank_gauss


def test_rank_gauss_is_within_group():
    vals = pd.Series([1, 2, 3, 100, 200, 300], index=list("abcdef"), dtype=float)
    groups = pd.Series(["x", "x", "x", "y", "y", "y"], index=vals.index)
    z = rank_gauss(vals, [groups], min_group_size=3)
    # même rang relatif dans chaque groupe -> même z
    assert z["a"] == pytest.approx(z["d"]) and z["c"] == pytest.approx(z["f"])
    assert z["b"] == pytest.approx(0.0)


def test_rank_gauss_falls_back_when_group_too_small():
    vals = pd.Series([1.0, 2.0, 3.0, 4.0], index=list("abcd"))
    fine = pd.Series(["x", "x", "y", "z"], index=vals.index)
    coarse = pd.Series("all", index=vals.index)
    z = rank_gauss(vals, [fine, coarse], min_group_size=3)
    assert z.notna().all() and z.is_monotonic_increasing


def test_rank_gauss_keeps_nan():
    vals = pd.Series([1.0, np.nan, 3.0], index=list("abc"))
    z = rank_gauss(vals, [pd.Series("g", index=vals.index)], min_group_size=2)
    assert np.isnan(z["b"])


def _toy_inputs(n=40):
    idx = pd.Index([f"S{i:02d}.US" for i in range(n)], name="symbol")
    rng = np.random.default_rng(0)
    signals = pd.DataFrame(
        {
            "F-EY": rng.normal(size=n),
            "F-FCFY": rng.normal(size=n),
            "F-BM": rng.normal(size=n),
            "F-GP": np.linspace(-1, 1, n),
            "F-CBOP": rng.normal(size=n),
            "F-ACCR": rng.normal(size=n),
            "F-PIOT": rng.integers(0, 10, n).astype(float),
            "Q-MOM-12-1": rng.normal(size=n),
            "Q-RESMOM": rng.normal(size=n),
            "Q-LOWVOL": rng.uniform(0.1, 0.5, n),
            "F-ISSUE": rng.normal(size=n),
            "F-AGR": rng.normal(size=n),
            "F-BENM": -2.5,
            "altman_zone": "safe",
        },
        index=idx,
    )
    meta = pd.DataFrame(
        {
            "sector": "Industrials",
            "region": "US",
            "passes_liquidity": True,
            "adv60_usd": 5e7,
            "liquidity_note": "",
        },
        index=idx,
    )
    return signals, meta


def test_contributions_sum_to_raw_composite(config):
    signals, meta = _toy_inputs()
    bs = score_book("M", signals, meta, config)
    np.testing.assert_allclose(bs.contributions.sum(axis=1), bs.raw_composite, atol=1e-12)
    assert set(bs.families.columns) == set(config.weights.books["M"])


def test_higher_signal_gives_higher_score_all_else_equal(config):
    signals, meta = _toy_inputs()
    base = score_book("M", signals, meta, config).raw_composite
    bumped = signals.copy()
    bumped.loc["S00.US", "F-GP"] = 10.0  # meilleure rentabilité de l'univers
    after = score_book("M", bumped, meta, config).raw_composite
    assert after["S00.US"] > base["S00.US"]


def test_negative_sign_signals_are_inverted(config):
    signals, meta = _toy_inputs()
    signals["F-AGR"] = np.linspace(0, 1, len(signals))  # croissance d'actifs : signe -1
    bs = score_book("M", signals, meta, config)
    assert bs.contributions["F-AGR"].iloc[0] > bs.contributions["F-AGR"].iloc[-1]


def test_penalties_and_liquidity_exclusion(config):
    signals, meta = _toy_inputs()
    signals.loc["S01.US", "F-BENM"] = -1.0
    signals.loc["S02.US", "altman_zone"] = "distress"
    meta.loc["S03.US", "passes_liquidity"] = False
    upcoming = pd.Series({"S04.US": 2.0})
    bs = score_book("S", signals, meta, config, upcoming)
    p = config.settings.penalties
    assert bs.penalties.loc["S01.US", "beneish"] == p.beneish
    assert bs.penalties.loc["S02.US", "altman"] == p.altman_distress["S"]
    assert bs.penalties.loc["S04.US", "binary_event"] == p.binary_event["S"]
    assert np.isnan(bs.composite["S03.US"])
    assert "Beneish" in bs.flags.loc["S01.US", "flags"]


def test_family_coverage_shrinks_score(config):
    signals, meta = _toy_inputs()
    full = score_book("M", signals, meta, config).families["value"]
    partial = signals.copy()
    partial.loc["S05.US", ["F-FCFY", "F-BM"]] = np.nan  # 1 signal sur 3 : sous le seuil de 60 %
    fam = score_book("M", partial, meta, config).families["value"]
    assert fam["S05.US"] == 0.0 and full["S05.US"] != 0.0


def test_select_ideas_and_changes(config):
    signals, meta = _toy_inputs()
    bs = score_book("M", signals, meta, config)
    ideas = select_ideas(bs, 5, 3)
    assert (ideas["side"] == "long").sum() == 5 and (ideas["side"] == "short").sum() == 3
    longs = ideas[ideas["side"] == "long"]
    assert longs["score"].is_monotonic_decreasing
    prev = ideas.copy()
    prev.loc[prev.index[0], "symbol"] = "OLD.US"
    ch = changes_vs_previous(ideas, prev, {"M": bs.families}, None)
    assert set(ch["change"]) == {"entrée", "sortie"}


def test_end_to_end_scores_on_synthetic(small_market, config):
    view = PitView(small_market.data, datetime(2021, 9, 1, tzinfo=UTC))
    syms = view.listed_symbols()
    sig = compute_signals(view, syms, config)
    books = score_all_books(sig, config)
    for b, bs in books.items():
        assert bs.composite.notna().sum() > 30, b
    # la qualité latente plantée doit être récompensée par le livre L (qualité/sécurité)
    q = small_market.quality.loc[:"2021-06-30"].iloc[-1]
    corr = books["L"].composite.corr(q.reindex(books["L"].composite.index), method="spearman")
    assert corr > 0.3
