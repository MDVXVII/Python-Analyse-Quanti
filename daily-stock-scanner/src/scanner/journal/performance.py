"""Suivi prospectif des recommandations passées (paper trading, Module 9).

Prix de référence : **ouverture de la première séance suivant la recommandation**
(``next_open``), ou la clôture si l'ouverture n'est pas disponible. On ne mesure jamais
une recommandation à un prix qui était déjà connu au moment où elle a été émise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def evaluate_entries(
    entries: pd.DataFrame,
    open_px: pd.DataFrame,
    close_px: pd.DataFrame,
    horizons: list[int],
    reference: str = "next_open",
) -> pd.DataFrame:
    """Rendement de chaque recommandation à chaque horizon (en séances), signé selon le sens.

    Rendement en excès : par rapport à l'univers équipondéré (tous les titres du panel) sur
    la même fenêtre, signé comme la recommandation.
    """
    if entries.empty or close_px.empty:
        return pd.DataFrame()
    idx = close_px.index
    filled = close_px.ffill()
    rows = []
    for _, e in entries.iterrows():
        sym = e["symbol"]
        if sym not in close_px.columns:
            continue
        day = pd.Timestamp(str(e["as_of"])[:10])
        pos = int(idx.searchsorted(day))  # première séance >= date de décision
        if pos >= len(idx):
            continue
        ref = np.nan
        if reference == "next_open" and sym in open_px.columns:
            ref = open_px[sym].iloc[pos]
        if pd.isna(ref):
            ref = close_px[sym].iloc[pos]
        sign = -1.0 if e.get("side") == "short" else 1.0
        row = {
            "seq": e.get("seq"),
            "as_of": day,
            "book": e.get("book"),
            "side": e.get("side"),
            "symbol": sym,
            "reference_price": ref,
        }
        for h in horizons:
            p = pos + h
            row[f"ret_{h}d"] = np.nan
            row[f"excess_{h}d"] = np.nan
            if p < len(idx) and pd.notna(ref) and ref > 0:
                px = close_px[sym].iloc[: p + 1].dropna()
                if len(px):
                    raw = float(px.iloc[-1]) / ref - 1
                    bench = float((filled.iloc[p] / close_px.iloc[pos] - 1).mean())
                    row[f"ret_{h}d"] = sign * raw
                    row[f"excess_{h}d"] = sign * (raw - bench)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_performance(evaluated: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Nombre, rendement moyen et taux de réussite par livre, sens et horizon."""
    if evaluated.empty:
        return pd.DataFrame(columns=["book", "side", "horizon", "n", "mean_return", "hit_rate"])
    rows = []
    for (book, side), grp in evaluated.groupby(["book", "side"]):
        for h in horizons:
            r = grp[f"ret_{h}d"].dropna()
            rows.append(
                {
                    "book": book,
                    "side": side,
                    "horizon": h,
                    "n": len(r),
                    "mean_return": float(r.mean()) if len(r) else np.nan,
                    "hit_rate": float((r > 0).mean()) if len(r) else np.nan,
                }
            )
    return pd.DataFrame(rows)
