from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from scanner.data.pit import PitView
from scanner.universe import live_universe, rule_based_universe

FX = {"USD": 1.0, "EUR": 1.10, "GBP": 1.30}


def _inputs():
    syms = ["AAA.US", "BBB.US", "MC.PA", "VOD.LSE", "TINY.US", "ETF.US"]
    sec = pd.DataFrame(
        {
            "symbol": syms,
            "country": ["US", "US", "FR", "GB", "US", "US"],
            "currency": ["USD", "USD", "EUR", "GBP", "USD", "USD"],
            "sector": ["Industrials"] * 6,
            "security_type": ["EQUITY", "EQUITY", "EQUITY", "EQUITY", "EQUITY", "ETF"],
        }
    )
    quant = pd.DataFrame(
        {
            "adv60_usd": [5e7, 2e6, 3e8, 1e8, 2e5, 1e9],
            "last_close_usd": [50, 10, 700, 1.2, 2.0, 400],
        },
        index=syms,
    )
    fund = pd.DataFrame({"desc_market_cap": [2e10, 1e9, 3e11, 4e10, 1e8, None]}, index=syms)
    cons = {
        "SP500": ["AAA.US", "BBB.US", "TINY.US", "ETF.US"],
        "SBF120": ["MC.PA"],
        "STOXX600": ["MC.PA", "VOD.LSE"],
    }
    return cons, sec, quant, fund


def test_live_universe_filters_and_flags(config):
    cons, sec, quant, fund = _inputs()
    u = live_universe(cons, sec, quant, fund, config.settings, FX).set_index("symbol")
    assert u.loc["MC.PA", "indices"] == "SBF120,STOXX600"
    assert u.loc["AAA.US", "passes_liquidity"]
    assert not u.loc["TINY.US", "passes_liquidity"]
    assert "volume" in u.loc["TINY.US", "liquidity_note"]
    assert not u.loc["ETF.US", "passes_liquidity"]
    # PEA : France oui, Royaume-Uni non (depuis le Brexit), US non
    assert u.loc["MC.PA", "pea_eligible"] and not u.loc["VOD.LSE", "pea_eligible"]
    assert not u.loc["AAA.US", "pea_eligible"]
    # TTF : société française > 1 Md€
    assert u.loc["MC.PA", "ttf_applicable"] and not u.loc["AAA.US", "ttf_applicable"]
    assert u.loc["VOD.LSE", "region"] == "EU"


def test_live_universe_uses_official_lists_when_given(config):
    cons, sec, quant, fund = _inputs()
    u = live_universe(
        cons, sec, quant, fund, config.settings, FX, srd_list={"MC.PA"}, ttf_list=set()
    ).set_index("symbol")
    assert bool(u.loc["MC.PA", "srd_eligible"]) and u.loc["AAA.US", "srd_eligible"] == False  # noqa: E712
    assert not u.loc["MC.PA", "ttf_applicable"]


def test_rule_based_universe_is_point_in_time(small_market):
    early = PitView(small_market.data, datetime(2017, 3, 1, tzinfo=UTC))
    late = PitView(small_market.data, datetime(2023, 6, 1, tzinfo=UTC))
    u1 = rule_based_universe(early, "US", 25, 3.0, 1e6, FX)
    u2 = rule_based_universe(late, "US", 25, 3.0, 1e6, FX)
    assert len(u1) == 25 and len(u2) == 25
    sec = small_market.data.securities.set_index("symbol")
    # un titre radié avant 2023 peut figurer en 2017 mais jamais en 2023
    for s in u2:
        d = sec.loc[s, "delisted_on"]
        assert pd.isna(d) or d > pd.Timestamp("2023-05-31")
    assert all(s.endswith(".US") for s in u1 + u2)
