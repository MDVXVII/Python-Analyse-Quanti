"""Normalisation des signaux : percentiles au sein du groupe secteur x région, puis rang gaussien.

Le passage par les rangs rend le score insensible aux valeurs extrêmes (la winsorisation
devient superflue) et comparable entre secteurs : on classe une banque parmi les banques
européennes, pas face à un éditeur de logiciels américain.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import ndtri


def winsorize(s: pd.Series, lower: float, upper: float) -> pd.Series:
    """Écrête aux quantiles ``lower`` / ``upper`` (utile pour les z-scores bruts)."""
    lo, hi = s.quantile([lower, upper])
    return s.clip(lo, hi)


def _pct_in_groups(
    values: pd.Series, groups: pd.Series, min_size: int
) -> tuple[pd.Series, pd.Series]:
    """Percentile (rang moyen - 0,5) / n dans chaque groupe assez grand ; NaN ailleurs."""
    df = pd.DataFrame({"v": values, "g": groups.astype("string").fillna("?")})
    df = df[df["v"].notna()]
    n = df.groupby("g")["v"].transform("count")
    rank = df.groupby("g")["v"].rank(method="average")
    pct = ((rank - 0.5) / n).where(n >= min_size)
    return pct.reindex(values.index), n.reindex(values.index)


def rank_gauss(
    values: pd.Series, group_levels: list[pd.Series], min_group_size: int, clip: float = 3.0
) -> pd.Series:
    """Rang gaussien par groupe, avec repli sur des groupes plus larges si trop peu d'effectif.

    ``group_levels`` : du plus fin au plus large (ex. [secteur|région, secteur, région]).
    Le dernier niveau de repli est l'univers entier.
    """
    pct = pd.Series(np.nan, index=values.index)
    levels = [*group_levels, pd.Series("ALL", index=values.index)]
    for k, groups in enumerate(levels):
        missing = pct.isna() & values.notna()
        if not missing.any():
            break
        size = min_group_size if k < len(levels) - 1 else 2  # l'univers entier : dernier recours
        p, _ = _pct_in_groups(values, groups.reindex(values.index), size)
        pct = pct.where(~missing, p)
    z = pd.Series(ndtri(pct.clip(1e-6, 1 - 1e-6).to_numpy(dtype=float)), index=values.index)
    return z.clip(-clip, clip).where(values.notna())
