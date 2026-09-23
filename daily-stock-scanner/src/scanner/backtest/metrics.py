"""Métriques de performance et tests statistiques du backtest.

* Rendement, volatilité, Sharpe, Sortino, drawdown maximal, taux de réussite ;
* t-statistique de Newey-West (chevauchement des horizons de rendement) ;
* Probabilistic et Deflated Sharpe Ratio (Bailey & López de Prado 2014) : corrige le
  Sharpe de la non-normalité et du **nombre d'essais** réalisés (data mining).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

EULER_GAMMA = 0.5772156649015329


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    r = returns.dropna()
    if r.empty:
        return float("nan")
    growth = float(np.prod(1 + r.to_numpy(dtype=float)))
    if growth <= 0:
        return -1.0
    return growth ** (periods_per_year / len(r)) - 1


def annualized_vol(returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(returns.dropna().std(ddof=1) * math.sqrt(periods_per_year))


def sharpe(returns: pd.Series, periods_per_year: int = 252, rf: float = 0.0) -> float:
    r = returns.dropna() - rf / periods_per_year
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(periods_per_year)) if sd > 0 else float("nan")


def sortino(returns: pd.Series, periods_per_year: int = 252) -> float:
    r = returns.dropna()
    downside = r[r < 0]
    dd = math.sqrt((downside**2).sum() / len(r)) if len(r) else float("nan")
    return float(r.mean() / dd * math.sqrt(periods_per_year)) if dd and dd > 0 else float("nan")


def max_drawdown(returns: pd.Series) -> float:
    wealth = (1 + returns.fillna(0)).cumprod()
    return float((wealth / wealth.cummax() - 1).min()) if len(wealth) else float("nan")


def hit_rate(returns: pd.Series) -> float:
    r = returns.dropna()
    r = r[r != 0]
    return float((r > 0).mean()) if len(r) else float("nan")


def newey_west_tstat(x: pd.Series, lags: int) -> float:
    """t-stat de la moyenne avec erreur standard HAC (noyau de Bartlett)."""
    v = x.dropna().to_numpy(dtype=float)
    n = len(v)
    if n < 3:
        return float("nan")
    e = v - v.mean()
    gamma0 = float(e @ e) / n
    s = gamma0
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1 - lag / (lags + 1)
        s += 2 * w * float(e[lag:] @ e[:-lag]) / n
    se = math.sqrt(s / n) if s > 0 else float("nan")
    return float(v.mean() / se) if se and se > 0 else float("nan")


def probabilistic_sharpe(
    sr: float, n_obs: int, skew: float, kurt: float, sr_benchmark: float = 0.0
) -> float:
    """PSR : probabilité que le vrai Sharpe (par période) dépasse ``sr_benchmark``.

    ``kurt`` est la kurtosis **non** excédentaire (3 pour une loi normale).
    """
    if n_obs < 3 or not np.isfinite(sr):
        return float("nan")
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    if denom <= 0:
        return float("nan")
    z = (sr - sr_benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return float(norm.cdf(z))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Sharpe maximal attendu sous l'hypothèse nulle après ``n_trials`` essais indépendants."""
    if n_trials <= 1 or sr_variance <= 0:
        return 0.0
    a = (1 - EULER_GAMMA) * norm.ppf(1 - 1 / n_trials)
    b = EULER_GAMMA * norm.ppf(1 - 1 / (n_trials * math.e))
    return float(math.sqrt(sr_variance) * (a + b))


def deflated_sharpe(returns: pd.Series, n_trials: int, sr_variance: float | None = None) -> float:
    """DSR : PSR évalué au Sharpe maximal attendu par chance après ``n_trials`` essais.

    ``sr_variance`` : variance des Sharpe (par période) des essais. À défaut, on utilise
    la variance d'estimation du Sharpe de la série elle-même (approximation prudente).
    """
    r = returns.dropna()
    n = len(r)
    if n < 10 or r.std(ddof=1) == 0:
        return float("nan")
    sr = float(r.mean() / r.std(ddof=1))
    skew = float(r.skew())  # type: ignore[arg-type]
    kurt = float(r.kurt()) + 3.0  # type: ignore[arg-type]
    if sr_variance is None:
        sr_variance = (1 - skew * sr + (kurt - 1) / 4 * sr**2) / (n - 1)
    sr0 = expected_max_sharpe(n_trials, sr_variance)
    return probabilistic_sharpe(sr, n, skew, kurt, sr0)


def summarize(
    returns: pd.Series,
    periods_per_year: int = 252,
    n_trials: int = 1,
    turnover: float | None = None,
) -> dict[str, float]:
    return {
        "ann_return": annualized_return(returns, periods_per_year),
        "ann_vol": annualized_vol(returns, periods_per_year),
        "sharpe": sharpe(returns, periods_per_year),
        "sortino": sortino(returns, periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "hit_rate": hit_rate(returns),
        "deflated_sharpe": deflated_sharpe(returns, n_trials),
        "turnover_ann": float("nan") if turnover is None else turnover,
        "n_days": float(returns.notna().sum()),
    }
