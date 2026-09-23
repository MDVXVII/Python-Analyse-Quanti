"""Vérification des providers sur de **vraies** réponses (exclus par défaut : ``-m network``).

Exécutés par le job « network-smoke » de GitHub Actions, qui a accès à internet. Ils
confrontent les parseurs aux formats réels des API (ce que les tests sur réponses
simulées ne peuvent pas garantir).
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.network


def test_yfinance_prices_real():
    from scanner.data.providers.yfinance_provider import YFinanceProvider

    p = YFinanceProvider(pause_seconds=0.5)
    end = date.today()
    px = p.get_daily_prices_batch(["AAPL.US", "MC.PA"], end - timedelta(days=30), end)
    assert set(px["symbol"]) == {"AAPL.US", "MC.PA"}
    assert (px["close"] > 0).all() and px["adj_close"].notna().all()


def test_wikipedia_sp500_real():
    from scanner.data.providers.constituents import WikipediaConstituents

    syms = WikipediaConstituents().get_constituents("SP500")
    assert 490 <= len(syms) <= 510 and "AAPL.US" in syms


@pytest.mark.skipif(not os.environ.get("SEC_USER_AGENT"), reason="SEC_USER_AGENT non défini")
def test_sec_companyfacts_real(tmp_path):
    from scanner.data.providers.sec_edgar import SecEdgarProvider

    p = SecEdgarProvider(os.environ["SEC_USER_AGENT"], tmp_path)
    facts = p.get_facts("AAPL.US")
    concepts = set(facts["concept"])
    assert {"revenue", "net_income", "total_assets", "cfo", "eps_diluted"} <= concepts
    assert not facts["lag_estimated"].any()
    # chaque valeur est datée par sa publication, postérieure à la fin de période
    assert (facts["available_at"].dt.tz_convert(None) >= facts["period_end"]).all()
    ev = p.get_events("AAPL.US", date(2020, 1, 1), date.today())
    assert len(ev) >= 15  # une publication de résultats par trimestre depuis 2020
