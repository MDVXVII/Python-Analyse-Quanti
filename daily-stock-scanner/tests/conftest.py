from __future__ import annotations

from datetime import date

import pytest

from scanner.core.config import AppConfig, load_config
from scanner.data.providers.synthetic import SyntheticMarket, SyntheticSpec, generate


@pytest.fixture(scope="session")
def config() -> AppConfig:
    return load_config()


@pytest.fixture(scope="session")
def small_market() -> SyntheticMarket:
    """Petit marché synthétique partagé (lecture seule dans les tests)."""
    return generate(
        SyntheticSpec(n_securities=90, start=date(2016, 1, 1), end=date(2023, 12, 29), seed=11)
    )
