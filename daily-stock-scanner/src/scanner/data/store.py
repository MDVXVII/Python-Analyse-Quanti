"""Stockage local Parquet (+ DuckDB pour les requêtes) — modèle bitemporel.

Organisation sous ``data_dir`` :

* ``prices/<symbole>.parquet``      OHLCV, dédoublonné sur (symbole, date) — dernière collecte gagne
* ``facts/<symbole>.parquet``       faits fondamentaux : **toutes les versions** sont conservées
* ``events/<symbole>.parquet``      événements datés
* ``securities.parquet``            référentiel descriptif
* ``snapshots/<type>/<date>.parquet``  instantanés quotidiens (consensus, options)
* ``runs/<run_id>/...``             sorties de chaque exécution (signaux, scores, manifeste)

Les écritures sont atomiques (fichier temporaire puis renommage).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from scanner.data.schemas import EVENTS, FACTS, PRICES, SECURITIES, conform

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(symbol: str) -> str:
    return _SAFE.sub("_", symbol)


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def _merge(existing: pd.DataFrame | None, new: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if existing is None or existing.empty:
        merged = new
    elif new.empty:
        merged = existing
    else:
        merged = pd.concat([existing, new], ignore_index=True)
    return merged.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)


@dataclass
class MarketData:
    """Ensemble de données chargé en mémoire, consommé via :class:`scanner.data.pit.PitView`."""

    prices: pd.DataFrame
    facts: pd.DataFrame
    events: pd.DataFrame
    securities: pd.DataFrame
    _panels: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    def panel(self, column: str) -> pd.DataFrame:
        """Panel large (dates x symboles) d'une colonne de prix, mis en cache."""
        if column not in self._panels:
            if self.prices.empty:
                self._panels[column] = pd.DataFrame()
            else:
                p = self.prices.pivot_table(index="date", columns="symbol", values=column,
                                            aggfunc="last")
                p.index = pd.DatetimeIndex(p.index)
                self._panels[column] = p.sort_index()
        return self._panels[column]

    @property
    def symbols(self) -> list[str]:
        return sorted(self.securities["symbol"].astype(str).unique())


class DataStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- écritures -----------------------------------------------------------------------
    def write_prices(self, df: pd.DataFrame) -> int:
        df = conform(df, PRICES)
        for symbol, grp in df.groupby("symbol"):
            path = self.root / "prices" / f"{_safe(str(symbol))}.parquet"
            existing = pd.read_parquet(path) if path.exists() else None
            _atomic_write(_merge(existing, grp, ["symbol", "date"]).sort_values("date"), path)
        return len(df)

    def write_facts(self, df: pd.DataFrame) -> int:
        df = conform(df, FACTS)
        keys = ["symbol", "concept", "tag", "period_start", "period_end", "available_at",
                "value", "accession"]
        for symbol, grp in df.groupby("symbol"):
            path = self.root / "facts" / f"{_safe(str(symbol))}.parquet"
            existing = pd.read_parquet(path) if path.exists() else None
            _atomic_write(_merge(existing, grp, keys), path)
        return len(df)

    def write_events(self, df: pd.DataFrame) -> int:
        df = conform(df, EVENTS)
        for symbol, grp in df.groupby("symbol"):
            path = self.root / "events" / f"{_safe(str(symbol))}.parquet"
            existing = pd.read_parquet(path) if path.exists() else None
            _atomic_write(_merge(existing, grp, ["symbol", "event_type", "event_time", "source"]),
                          path)
        return len(df)

    def write_securities(self, df: pd.DataFrame) -> int:
        df = conform(df, SECURITIES)
        path = self.root / "securities.parquet"
        existing = pd.read_parquet(path) if path.exists() else None
        _atomic_write(_merge(existing, df, ["symbol"]), path)
        return len(df)

    def write_snapshot(self, kind: str, day: date, df: pd.DataFrame) -> Path:
        path = self.root / "snapshots" / kind / f"{day.isoformat()}.parquet"
        _atomic_write(df, path)
        return path

    def write_run_frame(self, run_id: str, name: str, df: pd.DataFrame) -> Path:
        path = self.root / "runs" / run_id / f"{name}.parquet"
        _atomic_write(df, path)
        return path

    def write_run_manifest(self, run_id: str, manifest: dict[str, Any]) -> Path:
        path = self.root / "runs" / run_id / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
        return path

    # -- lectures ------------------------------------------------------------------------
    def _read_dir(self, sub: str, symbols: Iterable[str] | None, columns: list[str]) -> pd.DataFrame:
        base = self.root / sub
        if not base.exists():
            return pd.DataFrame(columns=columns)
        if symbols is None:
            files = sorted(base.glob("*.parquet"))
        else:
            files = [base / f"{_safe(s)}.parquet" for s in symbols]
            files = [f for f in files if f.exists()]
        if not files:
            return pd.DataFrame(columns=columns)
        con = duckdb.connect()
        try:
            file_list = ", ".join(f"'{f.as_posix()}'" for f in files)
            return con.execute(
                f"SELECT * FROM read_parquet([{file_list}], union_by_name=true)").df()
        finally:
            con.close()

    def read_prices(self, symbols: Iterable[str] | None = None, start: date | None = None,
                    end: date | None = None) -> pd.DataFrame:
        df = self._read_dir("prices", symbols, PRICES.columns)
        if df.empty:
            return conform(df, PRICES)
        df = conform(df, PRICES)
        if start is not None:
            df = df[df["date"] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df["date"] <= pd.Timestamp(end)]
        return df.reset_index(drop=True)

    def read_facts(self, symbols: Iterable[str] | None = None) -> pd.DataFrame:
        return conform(self._read_dir("facts", symbols, FACTS.columns), FACTS)

    def read_events(self, symbols: Iterable[str] | None = None) -> pd.DataFrame:
        return conform(self._read_dir("events", symbols, EVENTS.columns), EVENTS)

    def read_securities(self) -> pd.DataFrame:
        path = self.root / "securities.parquet"
        if not path.exists():
            return conform(pd.DataFrame(columns=SECURITIES.columns), SECURITIES)
        return conform(pd.read_parquet(path), SECURITIES)

    def read_run_frame(self, run_id: str, name: str) -> pd.DataFrame | None:
        path = self.root / "runs" / run_id / f"{name}.parquet"
        return pd.read_parquet(path) if path.exists() else None

    def list_runs(self) -> list[str]:
        base = self.root / "runs"
        return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []

    def load(self, symbols: Iterable[str] | None = None, start: date | None = None,
             end: date | None = None) -> MarketData:
        syms = list(symbols) if symbols is not None else None
        securities = self.read_securities()
        if syms is not None:
            securities = securities[securities["symbol"].isin(syms)].reset_index(drop=True)
        return MarketData(prices=self.read_prices(syms, start, end), facts=self.read_facts(syms),
                          events=self.read_events(syms), securities=securities)
