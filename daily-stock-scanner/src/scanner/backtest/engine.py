"""Moteur de backtest de portefeuille (rebalancement périodique, coûts, délistés).

Conventions (sans biais d'anticipation) :

* scores calculés à la date de décision ``d`` avec les clôtures jusqu'à ``d`` inclus ;
* exécution à la clôture de la séance ``d + lag`` (``lag = 1`` par défaut) : on ne
  trade jamais au prix qui a servi à décider ;
* entre deux rebalancements, les poids dérivent avec les prix (achat-conservation) ;
* un titre qui cesse d'être coté est soldé au dernier cours, ajusté du
  ``delisting_return`` configuré, puis la position passe en liquidités.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from scanner.backtest.costs import CostModel


@dataclass(frozen=True)
class PortfolioSpec:
    top_fraction: float = 0.2
    top_n: int | None = None
    long_short: bool = True
    lag_days: int = 1


@dataclass
class LegResult:
    returns: pd.Series  # rendement quotidien net de coûts
    gross: pd.Series  # avant coûts
    turnover: pd.Series  # rotation « aller simple » à chaque rebalancement
    holdings: dict[pd.Timestamp, list[str]] = field(default_factory=dict)


@dataclass
class BacktestResult:
    long: LegResult
    short: LegResult | None
    long_short: pd.Series | None
    rebalances_per_year: float

    def annual_turnover(self) -> float:
        t = self.long.turnover
        return float(t.mean() * self.rebalances_per_year) if len(t) else float("nan")


def select(scores: pd.Series, spec: PortfolioSpec) -> tuple[list[str], list[str]]:
    s = scores.dropna().sort_values(ascending=False)
    if s.empty:
        return [], []
    n = spec.top_n or max(1, math.ceil(len(s) * spec.top_fraction))
    n = min(n, len(s) // 2 if spec.long_short else len(s))
    longs = list(s.index[:n])
    shorts = list(s.index[-n:]) if spec.long_short and n > 0 else []
    return longs, shorts


def _simulate_leg(
    targets: dict[pd.Timestamp, list[str]],
    adj: pd.DataFrame,
    costs: CostModel | None,
    delisting_return: float,
    end: pd.Timestamp | None,
) -> LegResult:
    """Simule une jambe équipondérée. ``targets`` : date d'exécution -> titres détenus."""
    if not targets:
        empty = pd.Series(dtype=float)
        return LegResult(empty, empty, empty)
    dates = adj.index
    first = min(targets)
    last = end if end is not None else dates[-1]
    days = dates[(dates >= first) & (dates <= last)]
    daily = adj.pct_change(fill_method=None)
    last_valid = adj.apply(lambda c: c.last_valid_index())
    values: dict[str, float] = {}
    cash = 1.0
    out_net, out_gross, turnover = {}, {}, {}
    prev_total = 1.0
    for t in days:
        # 1) rendement du jour sur les positions existantes
        gross_total = cash
        for sym in list(values):
            r = daily.at[t, sym] if sym in daily.columns else np.nan
            if pd.isna(r):
                lv = last_valid.get(sym)
                if lv is None or pd.isna(lv) or lv < t:  # sortie de cote : on solde
                    cash += values.pop(sym) * (1 + delisting_return)
                    continue
                r = 0.0
            values[sym] *= 1 + float(r)  # type: ignore[arg-type]
            gross_total += values[sym]
        gross_total = cash + sum(values.values())
        cost = 0.0
        # 2) rebalancement à la clôture du jour d'exécution
        if t in targets:
            names = [s for s in targets[t] if s in adj.columns and pd.notna(adj.at[t, s])]
            total = gross_total
            old_w = pd.Series(values, dtype=float) / total if total > 0 else pd.Series(dtype=float)
            new_w = pd.Series(1.0 / len(names), index=names) if names else pd.Series(dtype=float)
            delta = new_w.reindex(old_w.index.union(new_w.index), fill_value=0.0) - old_w.reindex(
                old_w.index.union(new_w.index), fill_value=0.0
            )
            turnover[t] = float(delta.abs().sum() / 2)
            if costs is not None:
                cost = costs.rebalance_cost(delta) * total
            total_after = total - cost
            values = {str(s): float(w) * total_after for s, w in new_w.items()}
            cash = total_after - sum(values.values())
        net_total = cash + sum(values.values())
        out_gross[t] = gross_total / prev_total - 1
        out_net[t] = net_total / prev_total - 1
        prev_total = net_total
    idx = pd.DatetimeIndex(list(out_net))
    return LegResult(
        returns=pd.Series(out_net, index=idx).iloc[1:],
        gross=pd.Series(out_gross, index=idx).iloc[1:],
        turnover=pd.Series(turnover),
        holdings=targets,
    )


def run_backtest(
    scores: dict[pd.Timestamp, pd.Series],
    adj: pd.DataFrame,
    spec: PortfolioSpec,
    costs: CostModel | None = None,
    delisting_return: float = 0.0,
    end: pd.Timestamp | None = None,
) -> BacktestResult:
    """Backtest long (et short papier) à partir des scores par date de décision."""
    dates = adj.index
    long_t: dict[pd.Timestamp, list[str]] = {}
    short_t: dict[pd.Timestamp, list[str]] = {}
    for d in sorted(scores):
        pos = dates.searchsorted(pd.Timestamp(d), side="right") - 1 + spec.lag_days
        if pos >= len(dates) or pos < 0:
            continue
        exec_day = dates[int(pos)]
        longs, shorts = select(scores[d], spec)
        long_t[exec_day] = longs
        if spec.long_short:
            short_t[exec_day] = shorts
    n_years = max((max(long_t) - min(long_t)).days / 365.25, 1e-9) if len(long_t) > 1 else 1.0
    per_year = max(len(long_t) - 1, 1) / n_years
    long = _simulate_leg(long_t, adj, costs, delisting_return, end)
    short = _simulate_leg(short_t, adj, costs, delisting_return, end) if spec.long_short else None
    ls = None
    if short is not None and not long.returns.empty:
        borrow = costs.borrow_daily if costs is not None else 0.0
        joined = pd.concat([long.returns, short.returns], axis=1, keys=["l", "s"]).fillna(0.0)
        ls = joined["l"] - joined["s"] - borrow
    return BacktestResult(long=long, short=short, long_short=ls, rebalances_per_year=per_year)


def equal_weight_benchmark(
    universe_by_date: dict[pd.Timestamp, list[str]],
    adj: pd.DataFrame,
    lag_days: int = 1,
    delisting_return: float = 0.0,
    end: pd.Timestamp | None = None,
) -> pd.Series:
    """Univers équipondéré, rebalancé aux mêmes dates, sans coûts (référence « naïve »)."""
    scores = {d: pd.Series(1.0, index=syms) for d, syms in universe_by_date.items()}
    spec = PortfolioSpec(top_fraction=1.0, long_short=False, lag_days=lag_days)
    return run_backtest(scores, adj, spec, None, delisting_return, end).long.returns
