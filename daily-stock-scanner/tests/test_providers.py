"""Tests des providers sur des réponses simulées (format documenté des API).

Ces tests garantissent le parsing et les conventions de disponibilité. Ils ne remplacent
pas une vérification sur réponses réelles (marqueur ``network``, exclu par défaut).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pandas as pd
import pytest

from scanner.core import symbols
from scanner.data.http import HttpClient
from scanner.data.providers.constituents import LocalCsvConstituents, parse_wikipedia_table
from scanner.data.providers.eodhd import (
    EodhdProvider,
    fundamentals_to_events,
    fundamentals_to_facts,
)
from scanner.data.providers.finnhub import calendar_to_events
from scanner.data.providers.sec_edgar import (
    SecEdgarProvider,
    earnings_events,
    parse_acceptance,
    parse_companyfacts,
    parse_submissions_filings,
)
from scanner.data.providers.yfinance_provider import history_to_prices, statements_to_facts

LAGS = {"annual": 120, "semiannual": 75, "quarterly": 60}

COMPANYFACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {
                    "shares": [
                        {
                            "end": "2023-10-20",
                            "val": 15550061000,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        }
                    ]
                }
            }
        },
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        {
                            "start": "2022-09-25",
                            "end": "2023-09-30",
                            "val": 383285000000,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        },
                        {
                            "start": "2023-07-02",
                            "end": "2023-09-30",
                            "val": 89498000000,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        },
                    ]
                }
            },
            "Assets": {
                "units": {
                    "USD": [
                        {
                            "end": "2023-09-30",
                            "val": 352583000000,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        }
                    ]
                }
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "units": {
                    "USD": [
                        {
                            "start": "2022-09-25",
                            "end": "2023-09-30",
                            "val": 10959000000,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        }
                    ]
                }
            },
            "EarningsPerShareDiluted": {
                "units": {
                    "USD/shares": [
                        {
                            "start": "2023-07-02",
                            "end": "2023-09-30",
                            "val": 1.46,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        }
                    ]
                }
            },
            "SomeUnmappedTag": {
                "units": {
                    "USD": [{"end": "2023-09-30", "val": 1, "accn": "x", "filed": "2023-11-03"}]
                }
            },
        },
    },
}

SUBMISSIONS = {
    "cik": "320193",
    "name": "Apple Inc.",
    "sic": "3571",
    "exchanges": ["Nasdaq"],
    "addresses": {"business": {"stateOrCountry": "CA"}},
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-23-000106",
                "0000320193-23-000104",
                "0000320193-23-000099",
            ],
            "filingDate": ["2023-11-03", "2023-11-02", "2023-10-01"],
            "acceptanceDateTime": [
                "2023-11-02T18:04:23.000Z",
                "2023-11-02T16:30:31.000Z",
                "2023-10-01T10:00:00.000Z",
            ],
            "form": ["10-K", "8-K", "8-K"],
            "items": ["", "2.02,9.01", "5.02"],
            "reportDate": ["2023-09-30", "2023-11-02", "2023-10-01"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm"],
        },
        "files": [],
    },
}


def test_symbols_roundtrip():
    assert symbols.to_yahoo("MC.PA") == "MC.PA"
    assert symbols.to_yahoo("SAP.XETRA") == "SAP.DE"
    assert symbols.to_yahoo("BRK-B.US") == "BRK-B"
    assert symbols.from_yahoo("SAP.DE") == "SAP.XETRA"
    assert symbols.from_yahoo("VOD.L") == "VOD.LSE"
    assert symbols.from_yahoo("BRK-B") == "BRK-B.US"
    assert symbols.default_country("ASML.AS") == "NL"


def test_acceptance_interpreted_conservatively():
    # 18:04 « Z » interprété comme heure de New York -> 22:04 UTC (EDT), jamais plus tôt.
    ts = parse_acceptance("2023-11-02T18:04:23.000Z")
    assert ts == datetime(2023, 11, 2, 22, 4, 23, tzinfo=UTC)


def test_companyfacts_parsing_and_availability():
    filings = parse_submissions_filings(SUBMISSIONS)
    acceptance = dict(zip(filings["accessionNumber"], filings["acceptance_utc"], strict=False))
    df = parse_companyfacts(COMPANYFACTS, "AAPL.US", acceptance)
    assert set(df["concept"]) == {
        "revenue",
        "total_assets",
        "capex",
        "shares_outstanding",
        "eps_diluted",
    }
    rev = df[df["concept"] == "revenue"].set_index("fiscal_period")
    assert rev.loc["FY", "value"] == 383285000000
    assert rev.loc["Q", "value"] == 89498000000
    # disponibilité = horodatage d'acceptation (converti), pas la date de période
    assert (df["available_at"] == pd.Timestamp("2023-11-02 22:04:23", tz="UTC")).all()
    assert not df["lag_estimated"].any()
    # rang de priorité du tag de revenu (2e tag de la liste)
    assert rev.loc["FY", "tag_rank"] == 1


def test_companyfacts_without_acceptance_uses_next_day():
    df = parse_companyfacts(COMPANYFACTS, "AAPL.US", None)
    assert (df["available_at"] == pd.Timestamp("2023-11-04", tz="UTC")).all()


def test_earnings_events_from_8k_item_202():
    filings = parse_submissions_filings(SUBMISSIONS)
    ev = earnings_events(filings, "AAPL.US")
    assert len(ev) == 1
    assert ev.iloc[0]["event_type"] == "earnings_release"
    assert ev.iloc[0]["available_at"] == pd.Timestamp("2023-11-02 20:30:31", tz="UTC")


def test_sec_provider_requires_user_agent(tmp_path):
    from scanner.data.providers.base import ProviderError

    with pytest.raises(ProviderError):
        SecEdgarProvider(user_agent="no-email", cache_dir=tmp_path)


def test_sec_provider_end_to_end_with_mock(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "company_tickers" in url:
            return httpx.Response(
                200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}
            )
        if "submissions" in url:
            return httpx.Response(200, json=SUBMISSIONS)
        if "companyfacts" in url:
            return httpx.Response(200, json=COMPANYFACTS)
        return httpx.Response(404)

    client = HttpClient(
        "sec_edgar", tmp_path, 1000, transport=httpx.MockTransport(handler), sleep=lambda s: None
    )
    p = SecEdgarProvider(user_agent=None, cache_dir=None, client=client)
    facts = p.get_facts("AAPL.US")
    assert len(facts) == 6
    info = p.get_security_info("AAPL.US")
    assert info["country"] == "US" and info["sector"] == "Information Technology"


def test_yfinance_conversions():
    idx = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="America/New_York")
    hist = pd.DataFrame(
        {
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Adj Close": [1.1, 2.1],
            "Volume": [100, 200],
        },
        index=idx,
    )
    px = history_to_prices(hist, "AAPL.US")
    assert list(px["adj_close"]) == [1.1, 2.1]
    assert px["date"].dt.tz is None

    annual = pd.DataFrame(
        {pd.Timestamp("2023-12-31"): [1000.0, -50.0], pd.Timestamp("2022-12-31"): [900.0, -40.0]},
        index=["Total Revenue", "Capital Expenditure"],
    )
    facts = statements_to_facts({"annual": annual}, "X.PA", LAGS, "EUR")
    assert facts["lag_estimated"].all()
    cap = facts[facts["concept"] == "capex"].sort_values("period_end")
    assert list(cap["value"]) == [40.0, 50.0]  # décaissement rendu positif
    rev = facts[(facts["concept"] == "revenue") & (facts["period_end"] == "2023-12-31")].iloc[0]
    assert rev["available_at"] == pd.Timestamp("2024-04-29", tz="UTC")  # +120 jours


EODHD_FUND = {
    "General": {
        "Code": "MC",
        "Name": "LVMH",
        "CountryISO": "FR",
        "CurrencyCode": "EUR",
        "GicSector": "Consumer Discretionary",
        "ISIN": "FR0000121014",
    },
    "Highlights": {"MarketCapitalization": 3.5e11},
    "Financials": {
        "Income_Statement": {
            "currency_symbol": "EUR",
            "yearly": {
                "2023-12-31": {
                    "date": "2023-12-31",
                    "filing_date": "2024-01-25",
                    "totalRevenue": "86153000000.00",
                    "grossProfit": "59277000000.00",
                },
                "2022-12-31": {"date": "2022-12-31", "totalRevenue": "79184000000.00"},
            },
        },
        "Cash_Flow": {
            "currency_symbol": "EUR",
            "yearly": {
                "2023-12-31": {
                    "date": "2023-12-31",
                    "filing_date": "2024-01-25",
                    "capitalExpenditures": "-7478000000",
                }
            },
        },
    },
    "Earnings": {
        "History": {
            "2023-12-31": {
                "reportDate": "2024-01-25",
                "date": "2023-12-31",
                "epsActual": 16.8,
                "beforeAfterMarket": "AfterMarket",
            }
        }
    },
}


def test_eodhd_fundamentals_parsing():
    facts = fundamentals_to_facts(EODHD_FUND, "MC.PA", LAGS)
    rev = facts[facts["concept"] == "revenue"].set_index("period_end")
    assert not rev.loc["2023-12-31", "lag_estimated"]
    assert rev.loc["2023-12-31", "available_at"] == pd.Timestamp("2024-01-26", tz="UTC")
    # pas de filing_date -> décalage conservateur et drapeau
    assert rev.loc["2022-12-31", "lag_estimated"]
    assert rev.loc["2022-12-31", "available_at"] == pd.Timestamp("2023-04-30", tz="UTC")  # +120 j
    capex = facts[facts["concept"] == "capex"].iloc[0]
    assert capex["value"] == 7478000000
    ev = fundamentals_to_events(EODHD_FUND, "MC.PA")
    assert ev.iloc[0]["available_at"] == pd.Timestamp("2024-01-26", tz="UTC")


def test_eodhd_provider_prices_and_info(tmp_path):
    def handler(request):
        if "/eod/" in str(request.url):
            assert request.url.params["api_token"] == "KEY"
            return httpx.Response(
                200,
                json=[
                    {
                        "date": "2024-01-02",
                        "open": 1,
                        "high": 2,
                        "low": 0.5,
                        "close": 1.5,
                        "adjusted_close": 1.4,
                        "volume": 1000,
                    }
                ],
            )
        return httpx.Response(200, json=EODHD_FUND)

    client = HttpClient(
        "eodhd", tmp_path, 1000, transport=httpx.MockTransport(handler), sleep=lambda s: None
    )
    p = EodhdProvider(api_key="KEY", cache_dir=None, client=client)
    px = p.get_daily_prices(
        "MC.PA", pd.Timestamp("2024-01-01").date(), pd.Timestamp("2024-01-05").date()
    )
    assert px.iloc[0]["adj_close"] == 1.4
    info = p.get_security_info("MC.PA")
    assert info["country"] == "FR" and info["sector"] == "Consumer Discretionary"


def test_finnhub_calendar():
    ev = calendar_to_events(
        {
            "earningsCalendar": [
                {"date": "2026-10-28", "hour": "amc", "symbol": "BRK.B"},
                {"date": None, "symbol": "X"},
            ]
        },
        datetime(2026, 9, 23, tzinfo=UTC),
    )
    assert list(ev["symbol"]) == ["BRK-B.US"]
    assert ev.iloc[0]["event_type"] == "earnings_scheduled"


def test_local_csv_constituents(tmp_path):
    (tmp_path / "SBF120.csv").write_text(
        "# commentaire\nsymbol,name\nMC.PA,LVMH\nOR.PA,L'Oréal\n", encoding="utf-8"
    )
    assert LocalCsvConstituents(tmp_path).get_constituents("SBF120") == ["MC.PA", "OR.PA"]


def test_wikimedia_user_agent_has_contact():
    from scanner.data.providers.constituents import wikimedia_user_agent

    assert "github.com" in wikimedia_user_agent()
    assert wikimedia_user_agent("Jean Dupont jean@exemple.fr").endswith("contact: jean@exemple.fr")


def test_wikipedia_table_parsing():
    rows = "".join(f"<tr><td>T{i}</td><td>Name {i}</td></tr>" for i in range(100))
    html = (
        f"<table><tr><th>Symbol</th><th>Security</th></tr>{rows}"
        "<tr><td>BRK.B</td><td>Berkshire</td></tr></table>"
    )
    out = parse_wikipedia_table(html)
    assert "BRK-B.US" in out and len(out) == 101
