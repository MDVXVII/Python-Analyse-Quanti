from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from scanner.core.timeutil import (
    as_of_for_run,
    last_visible_price_date,
    price_available_at,
    rebalance_dates,
    trading_days,
)
from scanner.data.pit import PitView
from scanner.data.store import DataStore, MarketData


def _prices(symbol, days, base=10.0):
    return pd.DataFrame(
        {
            "symbol": symbol,
            "date": pd.to_datetime(days),
            "close": base,
            "adj_close": base,
            "volume": 1000.0,
        }
    )


def test_price_visibility_convention():
    as_of = as_of_for_run(date(2024, 3, 15))
    assert last_visible_price_date(as_of) == date(2024, 3, 14)
    assert price_available_at(date(2024, 3, 14)) <= as_of
    assert price_available_at(date(2024, 3, 15)) > as_of


def test_trading_calendar_skips_holidays():
    days = trading_days(date(2024, 12, 23), date(2024, 12, 27), "XNYS")
    assert pd.Timestamp("2024-12-25") not in days
    assert len(days) == 4
    paris = trading_days(date(2024, 5, 1), date(2024, 5, 1), "XPAR")
    assert len(paris) == 0  # 1er mai férié à Paris


def test_rebalance_dates_monthly():
    idx = pd.bdate_range("2024-01-01", "2024-03-31")
    out = rebalance_dates(idx, "monthly")
    assert list(out.strftime("%Y-%m-%d")) == ["2024-01-31", "2024-02-29", "2024-03-29"]


def test_store_prices_upsert(tmp_path):
    store = DataStore(tmp_path)
    store.write_prices(_prices("AAA.US", ["2024-01-02", "2024-01-03"], 10))
    store.write_prices(_prices("AAA.US", ["2024-01-03", "2024-01-04"], 11))  # 03 réécrit
    px = store.read_prices(["AAA.US"])
    assert list(px["date"].dt.strftime("%d")) == ["02", "03", "04"]
    assert px.set_index("date").loc["2024-01-03", "close"] == 11


def test_store_facts_keep_all_versions(tmp_path):
    store = DataStore(tmp_path)
    base = {
        "symbol": "AAA.US",
        "concept": "revenue",
        "period_end": "2023-12-31",
        "period_start": "2023-01-01",
        "tag": "t",
        "accession": "a1",
    }
    v1 = pd.DataFrame([{**base, "value": 100.0, "available_at": "2024-02-01T00:00:00Z"}])
    v2 = pd.DataFrame(
        [{**base, "value": 105.0, "available_at": "2024-05-01T00:00:00Z", "accession": "a2"}]
    )
    store.write_facts(v1)
    store.write_facts(v2)
    store.write_facts(v1)  # réécriture identique : pas de doublon
    facts = store.read_facts(["AAA.US"])
    assert sorted(facts["value"]) == [100.0, 105.0]


def test_pit_view_filters_everything():
    prices = pd.concat([_prices("AAA.US", ["2024-03-13", "2024-03-14", "2024-03-15"])])
    facts = pd.DataFrame(
        {
            "symbol": "AAA.US",
            "concept": "revenue",
            "value": [1.0, 2.0],
            "period_end": pd.to_datetime(["2023-12-31", "2023-12-31"]),
            "available_at": pd.to_datetime(["2024-03-01", "2024-03-20"], utc=True),
        }
    )
    events = pd.DataFrame(
        {
            "symbol": "AAA.US",
            "event_type": "earnings_release",
            "event_time": pd.to_datetime(["2024-03-10", "2024-03-16"], utc=True),
            "available_at": pd.to_datetime(["2024-03-10", "2024-03-16"], utc=True),
        }
    )
    sec = pd.DataFrame(
        {
            "symbol": ["AAA.US", "BBB.US"],
            "listed_from": pd.to_datetime([None, None]),
            "delisted_on": pd.to_datetime([None, "2024-03-01"]),
        }
    )
    data = MarketData(prices=prices, facts=facts, events=events, securities=sec)
    v = PitView(data, datetime(2024, 3, 15, tzinfo=UTC))
    assert v.panel("close").index.max() == pd.Timestamp("2024-03-14")
    assert list(v.facts()["value"]) == [1.0]
    assert len(v.events()) == 1
    assert list(v.securities()["symbol"]) == ["AAA.US"]  # BBB radié avant as_of


def test_pit_view_requires_timezone():
    data = MarketData(
        prices=pd.DataFrame(),
        facts=pd.DataFrame(),
        events=pd.DataFrame(),
        securities=pd.DataFrame(),
    )
    try:
        PitView(data, datetime(2024, 1, 1))
    except ValueError:
        return
    raise AssertionError("un as_of sans fuseau doit être refusé")


def test_synthetic_market_respects_listing(small_market):
    d = small_market.data
    sec = d.securities.set_index("symbol")
    for sym, grp in d.prices.groupby("symbol"):
        assert grp["date"].min() >= sec.loc[sym, "listed_from"]
        if pd.notna(sec.loc[sym, "delisted_on"]):
            assert grp["date"].max() < sec.loc[sym, "delisted_on"]


def test_store_load_roundtrip(tmp_path, small_market):
    store = DataStore(tmp_path)
    d = small_market.data
    syms = d.symbols[:5]
    store.write_prices(d.prices[d.prices["symbol"].isin(syms)])
    store.write_facts(d.facts[d.facts["symbol"].isin(syms)])
    store.write_events(d.events[d.events["symbol"].isin(syms)])
    store.write_securities(d.securities[d.securities["symbol"].isin(syms)])
    loaded = store.load(syms)
    assert set(loaded.prices["symbol"]) == set(syms)
    assert len(loaded.facts) == len(d.facts[d.facts["symbol"].isin(syms)])
    assert loaded.panel("adj_close").shape[1] == 5
