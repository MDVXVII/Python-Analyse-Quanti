"""Tests du Module 2 sur des cas calculés à la main."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from scanner.data.pit import PitView
from scanner.data.store import MarketData
from scanner.fundamentals.health import altman_z, altman_z2, altman_zone, beneish_m, piotroski
from scanner.fundamentals.signals import compute_fundamental_signals
from scanner.fundamentals.statements import latest_versions, ttm_flows

S = lambda v: pd.Series([float(v)], index=["X"])  # noqa: E731


def test_altman_original_hand_computed():
    # X1=0.2, X2=0.3, X3=0.1, X4=1.5, X5=1.2 -> 0.24+0.42+0.33+0.9+1.2 = 3.09
    z = altman_z(wc=S(20), re=S(30), ebit=S(10), mve=S(150), tl=S(100), sales=S(120), ta=S(100))
    assert z.iloc[0] == pytest.approx(3.09)
    assert altman_zone(z, pd.Series([True], index=["X"])).iloc[0] == "safe"


def test_altman_z2_hand_computed():
    # 6.56*0.1 + 3.26*0.05 + 6.72*0.02 + 1.05*0.5 = 0.656+0.163+0.1344+0.525 = 1.4784
    z = altman_z2(wc=S(10), re=S(5), ebit=S(2), bve=S(50), tl=S(100), ta=S(100))
    assert z.iloc[0] == pytest.approx(1.4784)
    assert altman_zone(z, pd.Series([False], index=["X"])).iloc[0] == "grey"


def test_piotroski_perfect_and_worst():
    good = piotroski(
        ni=S(10),
        cfo=S(15),
        assets=S(100),
        assets_prev=S(100),
        assets_prev2=S(100),
        ni_prev=S(5),
        ltd=S(10),
        ltd_prev=S(20),
        ca=S(50),
        cl=S(20),
        ca_prev=S(40),
        cl_prev=S(20),
        shares=S(100),
        shares_prev=S(100),
        revenue=S(200),
        revenue_prev=S(150),
        gp=S(80),
        gp_prev=S(50),
    )
    assert good[0].iloc[0] == 9 and good[1].iloc[0] == 9
    bad = piotroski(
        ni=S(-10),
        cfo=S(-15),
        assets=S(100),
        assets_prev=S(100),
        assets_prev2=S(100),
        ni_prev=S(5),
        ltd=S(30),
        ltd_prev=S(20),
        ca=S(30),
        cl=S(20),
        ca_prev=S(40),
        cl_prev=S(20),
        shares=S(110),
        shares_prev=S(100),
        revenue=S(100),
        revenue_prev=S(150),
        gp=S(30),
        gp_prev=S(50),
    )
    assert bad[0].iloc[0] == 0


def test_piotroski_nan_when_too_few_criteria():
    nan = pd.Series([np.nan], index=["X"])
    score, count = piotroski(
        ni=S(10),
        cfo=S(15),
        assets=S(100),
        assets_prev=S(100),
        assets_prev2=nan,
        ni_prev=nan,
        ltd=nan,
        ltd_prev=nan,
        ca=nan,
        cl=nan,
        ca_prev=nan,
        cl_prev=nan,
        shares=nan,
        shares_prev=nan,
        revenue=nan,
        revenue_prev=nan,
        gp=nan,
        gp_prev=nan,
    )
    assert np.isnan(score.iloc[0]) and count.iloc[0] < 7


def test_beneish_neutral_company_equals_constant_plus_coefficients():
    # Tous les indices à 1 et TATA = 0 : M = -4.84 + 0.92+0.528+0.404+0.892+0.115-0.172-0.327
    kw = dict(
        rec=S(10),
        rec_p=S(10),
        sales=S(100),
        sales_p=S(100),
        cogs=S(60),
        cogs_p=S(60),
        ca=S(30),
        ca_p=S(30),
        ppe=S(40),
        ppe_p=S(40),
        ta=S(100),
        ta_p=S(100),
        dep=S(5),
        dep_p=S(5),
        sga=S(10),
        sga_p=S(10),
        cl=S(20),
        cl_p=S(20),
        ltd=S(10),
        ltd_p=S(10),
        ni=S(8),
        cfo=S(8),
    )
    m, imputed = beneish_m(**kw)
    assert m.iloc[0] == pytest.approx(-4.84 + 0.92 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 - 0.327)
    assert imputed.iloc[0] == 0


def test_beneish_flags_aggressive_accruals_and_receivables():
    m, _ = beneish_m(
        rec=S(30),
        rec_p=S(10),
        sales=S(150),
        sales_p=S(100),
        cogs=S(100),
        cogs_p=S(60),
        ca=S(30),
        ca_p=S(30),
        ppe=S(40),
        ppe_p=S(40),
        ta=S(100),
        ta_p=S(100),
        dep=S(5),
        dep_p=S(5),
        sga=S(10),
        sga_p=S(10),
        cl=S(20),
        cl_p=S(20),
        ltd=S(10),
        ltd_p=S(10),
        ni=S(20),
        cfo=S(5),
    )
    assert m.iloc[0] > -1.78


def _facts(rows):
    df = pd.DataFrame(
        rows,
        columns=[
            "symbol",
            "concept",
            "value",
            "period_start",
            "period_end",
            "fiscal_period",
            "available_at",
        ],
    )
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["available_at"] = pd.to_datetime(df["available_at"], utc=True)
    df["tag_rank"] = 0
    df["unit"] = "USD"
    df["lag_estimated"] = False
    return df


def test_ttm_derives_q4_from_annual():
    rows = [
        ("A.US", "revenue", 10, "2023-01-01", "2023-03-31", "Q", "2023-05-01"),
        ("A.US", "revenue", 11, "2023-04-01", "2023-06-30", "Q", "2023-08-01"),
        ("A.US", "revenue", 12, "2023-07-01", "2023-09-30", "Q", "2023-11-01"),
        ("A.US", "revenue", 50, "2023-01-01", "2023-12-31", "FY", "2024-02-15"),  # T4 = 17
        ("A.US", "revenue", 14, "2024-01-01", "2024-03-31", "Q", "2024-05-01"),
    ]
    latest = latest_versions(_facts(rows))
    values, ends = ttm_flows(latest)
    # T2..T4 2023 + T1 2024 = 11 + 12 + 17 + 14 = 54
    assert values.loc["A.US", "revenue"] == pytest.approx(54)
    assert ends.loc["A.US"] == pd.Timestamp("2024-03-31")


def test_ttm_falls_back_to_annual_when_quarters_incomplete():
    rows = [
        ("A.US", "revenue", 50, "2023-01-01", "2023-12-31", "FY", "2024-02-15"),
        ("A.US", "revenue", 14, "2024-01-01", "2024-03-31", "Q", "2024-05-01"),
    ]
    values, _ = ttm_flows(latest_versions(_facts(rows)))
    assert values.loc["A.US", "revenue"] == 50


def test_restatement_invisible_before_publication():
    rows = [
        ("A.US", "revenue", 100, "2023-01-01", "2023-12-31", "FY", "2024-02-15"),
        ("A.US", "revenue", 90, "2023-01-01", "2023-12-31", "FY", "2024-06-01"),
    ]
    facts = _facts(rows)
    before = facts[facts["available_at"] <= pd.Timestamp("2024-03-01", tz="UTC")]
    assert latest_versions(before)["value"].tolist() == [100]
    assert latest_versions(facts)["value"].tolist() == [90]


def test_financials_are_excluded_from_industrial_ratios(small_market):
    d = small_market.data
    view = PitView(d, datetime(2021, 6, 1, tzinfo=UTC))
    from scanner.core.config import load_config

    cfg = load_config().settings.fundamentals
    out = compute_fundamental_signals(view, cfg)
    fin = out[out["is_financial"]]
    assert len(fin) > 0
    assert fin["F-EY"].isna().all() and fin["F-ALTZ"].isna().all()
    assert fin["F-BM"].notna().any()


def test_currency_mismatch_blocks_valuation(small_market):
    d = small_market.data
    sec = d.securities.copy()
    sec.loc[sec.index[0], "currency"] = "JPY"  # devise de cotation ≠ devise des comptes
    data = MarketData(d.prices, d.facts, d.events, sec)
    from scanner.core.config import load_config

    out = compute_fundamental_signals(
        PitView(data, datetime(2021, 6, 1, tzinfo=UTC)), load_config().settings.fundamentals
    )
    sym = sec.iloc[0]["symbol"]
    assert not out.loc[sym, "currency_ok"]
    assert np.isnan(out.loc[sym, "F-EY"])
