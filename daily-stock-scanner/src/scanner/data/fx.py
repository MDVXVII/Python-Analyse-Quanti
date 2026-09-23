"""Taux de change vers l'USD : données de marché si disponibles, sinon taux de repli configurés."""

from __future__ import annotations

import pandas as pd

from scanner.data.pit import PitView


def fx_symbol(currency: str) -> str:
    return f"{currency.upper()}USD.FX"


def fx_to_usd(
    view: PitView, fallback: dict[str, float], currencies: list[str] | None = None
) -> tuple[dict[str, float], list[str]]:
    """Taux ``1 devise = x USD`` à ``as_of`` et liste des devises servies par le repli."""
    close = view.panel("close")
    currencies = currencies or list(fallback)
    rates: dict[str, float] = {"USD": 1.0}
    used_fallback: list[str] = []
    for ccy in currencies:
        if ccy == "USD":
            continue
        sym = fx_symbol(ccy)
        if not close.empty and sym in close.columns and close[sym].notna().any():
            rates[ccy] = float(close[sym].dropna().iloc[-1])
        elif ccy in fallback:
            rates[ccy] = float(fallback[ccy])
            used_fallback.append(ccy)
    return rates, used_fallback


def is_fx_symbol(symbol: str) -> bool:
    return symbol.endswith(".FX")


def drop_fx(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[~df.index.astype(str).str.endswith(".FX")]
