"""Schémas normalisés échangés entre providers, stockage et modules.

Chaque provider convertit ses données brutes vers ces schémas. Les modules d'analyse
ne connaissent que ces schémas, ce qui rend les providers interchangeables.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FrameSchema:
    name: str
    required: dict[
        str, str
    ]  # colonne -> famille de type ("str", "float", "date", "datetime", "bool", "int")
    optional: dict[str, str]

    @property
    def columns(self) -> list[str]:
        return [*self.required, *self.optional]


PRICES = FrameSchema(
    name="prices",
    required={
        "symbol": "str",
        "date": "date",
        "close": "float",
        "adj_close": "float",
        "volume": "float",
    },
    optional={
        "open": "float",
        "high": "float",
        "low": "float",
        "source": "str",
        "ingested_at": "datetime",
    },
)

# Faits fondamentaux en format long, bitemporels.
# concept      : nom canonique (voir fundamentals/concepts.py)
# period_start : début de période pour un flux (None pour un stock / bilan)
# period_end   : fin de période (ou date du bilan)
# available_at : instant de publication (UTC)
FACTS = FrameSchema(
    name="facts",
    required={
        "symbol": "str",
        "concept": "str",
        "value": "float",
        "period_end": "date",
        "available_at": "datetime",
    },
    optional={
        "period_start": "date",
        "fiscal_period": "str",
        "form": "str",
        "unit": "str",
        "lag_estimated": "bool",
        "source": "str",
        "accession": "str",
        "tag": "str",  # tag d'origine (traçabilité)
        "tag_rank": "int",  # priorité du tag pour le concept (0 = préféré)
        "ingested_at": "datetime",
    },
)

EVENTS = FrameSchema(
    name="events",
    required={
        "symbol": "str",
        "event_type": "str",  # earnings_release, earnings_scheduled, agm, ...
        "event_time": "datetime",
        "available_at": "datetime",
    },
    optional={"source": "str", "detail": "str", "ingested_at": "datetime"},
)

SECURITIES = FrameSchema(
    name="securities",
    required={
        "symbol": "str",
        "name": "str",
        "country": "str",
        "currency": "str",
    },
    optional={
        "isin": "str",
        "cik": "str",
        "exchange": "str",
        "sector": "str",
        "industry": "str",
        "sic": "str",
        "security_type": "str",
        "listed_from": "date",
        "delisted_on": "date",
        "shares_outstanding": "float",
        "market_cap": "float",
        "source": "str",
    },
)


class SchemaError(ValueError):
    pass


def conform(df: pd.DataFrame, schema: FrameSchema) -> pd.DataFrame:
    """Vérifie les colonnes requises, ajoute les optionnelles manquantes et type les colonnes.

    Lève :class:`SchemaError` si une colonne requise manque. Les lignes dont une valeur
    requise est manquante sont supprimées (et non imputées).
    """
    missing = [c for c in schema.required if c not in df.columns]
    if missing:
        raise SchemaError(f"{schema.name} : colonnes requises manquantes {missing}")
    out = df.copy()
    for col in schema.optional:
        if col not in out.columns:
            out[col] = None
    kinds = {**schema.required, **schema.optional}
    for col, kind in kinds.items():
        out[col] = _cast(out[col], kind)
    out = out.dropna(subset=list(schema.required))
    return out[schema.columns].reset_index(drop=True)


def _cast(s: pd.Series, kind: str) -> pd.Series:
    if kind == "float":
        return pd.to_numeric(s, errors="coerce").astype("float64")
    if kind == "int":
        return pd.to_numeric(s, errors="coerce").astype("Int64")
    if kind == "date":
        return pd.to_datetime(s, errors="coerce").dt.tz_localize(None).dt.normalize()
    if kind == "datetime":
        ts = pd.to_datetime(s, errors="coerce", utc=True)
        return ts
    if kind == "bool":
        return s.astype("boolean")
    return s.astype("string")
