"""Interfaces des providers de données.

Un provider convertit une source externe vers les schémas de :mod:`scanner.data.schemas`.
Les modules d'analyse ne dépendent que de ces interfaces : on peut remplacer yfinance
par EODHD (ou une source payante future) sans toucher au reste du code.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


class ProviderError(RuntimeError):
    """Erreur d'un provider (source indisponible, réponse inattendue, clé manquante…)."""


@runtime_checkable
class PriceProvider(Protocol):
    name: str

    def get_daily_prices(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """OHLCV quotidien conforme au schéma ``PRICES`` (clôtures brutes et ajustées)."""
        ...


@runtime_checkable
class FundamentalsProvider(Protocol):
    name: str

    def get_facts(self, symbol: str) -> pd.DataFrame:
        """Faits comptables en format long conformes au schéma ``FACTS`` (bitemporels)."""
        ...


@runtime_checkable
class EventsProvider(Protocol):
    name: str

    def get_events(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Événements datés (publications de résultats…) conformes au schéma ``EVENTS``."""
        ...


@runtime_checkable
class SecurityInfoProvider(Protocol):
    name: str

    def get_security_info(self, symbol: str) -> dict[str, object]:
        """Informations descriptives : nom, pays, devise, secteur, capitalisation…"""
        ...


@runtime_checkable
class ConstituentsProvider(Protocol):
    name: str

    def get_constituents(self, index_id: str) -> list[str]:
        """Composition actuelle d'un indice (identifiants du fichier ``settings.yaml``)."""
        ...
