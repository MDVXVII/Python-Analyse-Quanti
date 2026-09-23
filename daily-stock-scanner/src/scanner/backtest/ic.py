"""Coefficient d'information (IC) par signal, décroissance selon l'horizon, spreads par quantile.

Rendements futurs mesurés **à partir de la séance d'exécution** (``d + lag``) pour ne
pas utiliser la clôture qui a servi à calculer le signal. Un titre radié pendant
l'horizon garde son dernier cours (ajusté du rendement de délistement) : les perdants
disparus restent dans l'échantillon.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from scanner.backtest.metrics import newey_west_tstat


def forward_returns(
    adj: pd.DataFrame,
    decision_dates: list[pd.Timestamp],
    horizon: int,
    lag_days: int = 1,
    delisting_return: float = 0.0,
) -> pd.DataFrame:
    """Rendement entre ``d + lag`` et ``d + lag + horizon`` séances (date x symbole)."""
    idx = adj.index
    filled = adj.ffill()
    last_valid = adj.apply(lambda c: c.last_valid_index())
    rows = {}
    for d in decision_dates:
        p0 = idx.searchsorted(pd.Timestamp(d), side="right") - 1 + lag_days
        p1 = p0 + horizon
        if p0 < 0 or p1 >= len(idx):
            continue
        start = adj.iloc[p0]
        end = filled.iloc[p1]
        r = end / start - 1
        delisted = last_valid.reindex(r.index) < idx[int(p1)]
        r = r.where(~delisted, (1 + r) * (1 + delisting_return) - 1)
        rows[pd.Timestamp(d)] = r.where(start.notna())
    return pd.DataFrame(rows).T if rows else pd.DataFrame()


def rank_ic(scores: pd.DataFrame, fwd: pd.DataFrame, min_names: int = 10) -> pd.Series:
    """IC de rang (Spearman) par date entre scores et rendements futurs."""
    out = {}
    for d in scores.index.intersection(fwd.index):
        s, r = scores.loc[d], fwd.loc[d]
        ok = s.notna() & r.notna()
        if ok.sum() >= min_names:
            out[d] = float(s[ok].rank().corr(r[ok].rank()))
    return pd.Series(out, dtype=float)


def ic_summary(ic: pd.Series, horizon_days: int, spacing_days: float) -> dict[str, float]:
    """Moyenne, écart-type, t de Newey-West (lags = chevauchement), taux de réussite."""
    ic = ic.dropna()
    lags = max(0, math.ceil(horizon_days / max(spacing_days, 1)) - 1)
    return {
        "ic_mean": float(ic.mean()) if len(ic) else float("nan"),
        "ic_std": float(ic.std(ddof=1)) if len(ic) > 1 else float("nan"),
        "ic_t_nw": newey_west_tstat(ic, lags) if len(ic) > 2 else float("nan"),
        "ic_hit": float((ic > 0).mean()) if len(ic) else float("nan"),
        "n_dates": float(len(ic)),
    }


def quantile_spread(
    scores: pd.DataFrame, fwd: pd.DataFrame, n_quantiles: int = 5, min_names: int = 20
) -> pd.Series:
    """Rendement moyen du quantile supérieur moins le quantile inférieur, par date."""
    out = {}
    for d in scores.index.intersection(fwd.index):
        s, r = scores.loc[d], fwd.loc[d]
        ok = s.notna() & r.notna()
        if ok.sum() < min_names:
            continue
        q = pd.qcut(s[ok].rank(method="first"), n_quantiles, labels=False)
        out[d] = float(r[ok][q == n_quantiles - 1].mean() - r[ok][q == 0].mean())
    return pd.Series(out, dtype=float)


def spacing_in_days(dates: list[pd.Timestamp] | pd.DatetimeIndex, index: pd.DatetimeIndex) -> float:
    """Écart moyen (en séances) entre dates de décision successives."""
    pos = np.array([index.searchsorted(pd.Timestamp(d)) for d in dates])
    return float(np.diff(pos).mean()) if len(pos) > 1 else float("nan")
