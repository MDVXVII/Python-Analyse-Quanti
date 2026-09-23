"""Walk-forward : les pondérations ne sont jamais estimées sur la période où on les teste.

Politique du projet (research_notes.md §1.5) : équipondération par défaut. Ce module
mesure, **hors échantillon**, si une pondération fondée sur l'IC passé (rétrécie vers 1/N)
bat l'équipondération. Tant que ce n'est pas le cas de façon significative, les poids
restent égaux.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Split:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def expanding_splits(
    dates: pd.DatetimeIndex, min_train_years: float = 3.0, test_years: float = 1.0
) -> list[Split]:
    """Découpage à fenêtre d'apprentissage croissante, tests annuels successifs."""
    if len(dates) == 0:
        return []
    start = dates.min()
    first_test = start + pd.DateOffset(months=int(min_train_years * 12))
    splits = []
    t0 = first_test
    while t0 < dates.max():
        t1 = min(
            t0 + pd.DateOffset(months=int(test_years * 12)), dates.max() + pd.Timedelta(days=1)
        )
        splits.append(Split(start, t0 - pd.Timedelta(days=1), t0, t1 - pd.Timedelta(days=1)))
        t0 = t1
    return splits


def shrunk_ic_weights(ic_means: pd.Series, shrink: float = 0.5) -> pd.Series:
    """Poids ∝ IC positif, rétrécis vers 1/N : w = shrink/N + (1 - shrink) * IC+/ΣIC+."""
    n = len(ic_means)
    equal = pd.Series(1.0 / n, index=ic_means.index)
    pos = ic_means.clip(lower=0).fillna(0.0)
    if pos.sum() <= 0:
        return equal
    return shrink * equal + (1 - shrink) * pos / pos.sum()


def combine(z_by_signal: dict[str, pd.DataFrame], weights: pd.Series) -> pd.DataFrame:
    """Combinaison linéaire des z (date x symbole), en ignorant les signaux manquants."""
    total = None
    wsum = None
    for sig, w in weights.items():
        z = z_by_signal[str(sig)]
        contrib = z * w
        present = z.notna().astype(float) * w
        total = (
            contrib.fillna(0.0) if total is None else total.add(contrib.fillna(0.0), fill_value=0.0)
        )
        wsum = present if wsum is None else wsum.add(present, fill_value=0.0)
    if total is None or wsum is None:
        return pd.DataFrame()
    return (total / wsum.replace(0, np.nan)).where(wsum > 0)


def walk_forward_compare(
    z_by_signal: dict[str, pd.DataFrame],
    ic_by_signal: dict[str, pd.Series],
    splits: list[Split],
    shrink: float = 0.5,
) -> pd.DataFrame:
    """Pour chaque période de test : poids appris sur le passé seulement, et scores OOS.

    Retourne un tableau (période, signal) des poids utilisés — la preuve que chaque poids
    n'a été estimé qu'avec l'information disponible avant la période de test.
    """
    rows = []
    for sp in splits:
        means = pd.Series(
            {
                s: ic[(ic.index >= sp.train_start) & (ic.index <= sp.train_end)].mean()
                for s, ic in ic_by_signal.items()
            }
        )
        w = shrunk_ic_weights(means, shrink)
        for s, v in w.items():
            rows.append(
                {
                    "test_start": sp.test_start,
                    "test_end": sp.test_end,
                    "signal": s,
                    "train_ic": float(means.loc[str(s)]),
                    "weight": v,
                }
            )
    return pd.DataFrame(rows)


def oos_scores(z_by_signal: dict[str, pd.DataFrame], weights_table: pd.DataFrame) -> pd.DataFrame:
    """Scores combinés hors échantillon, période par période, avec les poids appris avant."""
    parts = []
    for (t0, t1), grp in weights_table.groupby(["test_start", "test_end"]):
        w = grp.set_index("signal")["weight"]
        combo = combine(z_by_signal, w)
        if not combo.empty:
            parts.append(combo[(combo.index >= t0) & (combo.index <= t1)])
    return pd.concat(parts).sort_index() if parts else pd.DataFrame()
