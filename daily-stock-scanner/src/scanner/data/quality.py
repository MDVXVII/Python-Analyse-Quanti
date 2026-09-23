"""Contrôles qualité automatiques des données (Module 11).

Chaque anomalie est classée ``BLOCK`` (titre écarté du calcul) ou ``WARN`` (affichée
dans le rapport). Aucune donnée n'est « réparée » silencieusement.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scanner.data.pit import PitView


@dataclass(frozen=True)
class QcIssue:
    severity: str  # BLOCK | WARN
    check: str
    symbol: str
    detail: str


def run_quality_checks(
    view: PitView,
    symbols: list[str],
    max_stale_days: int = 5,
    max_abs_return: float = 0.5,
    identity_tolerance: float = 0.05,
) -> list[QcIssue]:
    issues: list[QcIssue] = []
    close = view.panel("close").reindex(columns=symbols)
    if close.empty:
        return [QcIssue("BLOCK", "prix", "*", "aucun prix disponible")]
    last_day = pd.Timestamp(view.last_price_date)
    last_valid = close.apply(lambda c: c.last_valid_index())
    for sym in symbols:
        lv = last_valid.get(sym)
        if lv is None or pd.isna(lv):
            issues.append(QcIssue("BLOCK", "prix manquants", sym, "aucun cours visible"))
            continue
        age = int(np.busday_count(pd.Timestamp(lv).date(), last_day.date()))
        if age > max_stale_days:
            issues.append(QcIssue("WARN", "fraîcheur", sym, f"dernier cours il y a {age} séances"))
    recent = close.iloc[-260:]
    if (recent <= 0).any().any():
        for sym in recent.columns[(recent <= 0).any()]:
            issues.append(QcIssue("BLOCK", "prix non positif", str(sym), "cours <= 0"))
    rets = close.iloc[-2:].pct_change(fill_method=None).iloc[-1] if len(close) >= 2 else pd.Series()
    for sym_key, r in rets.items():
        sym = str(sym_key)
        if pd.notna(r) and abs(r) > max_abs_return:
            issues.append(
                QcIssue(
                    "WARN",
                    "variation extrême",
                    str(sym),
                    f"{r:+.0%} sur la dernière séance (opération sur titre ?)",
                )
            )
    facts = view.facts()
    if not facts.empty:
        bs = facts[
            facts["concept"].isin(["total_assets", "total_liabilities", "total_equity"])
            & facts["symbol"].isin(symbols)
        ]
        if not bs.empty:
            wide = bs.pivot_table(
                index=["symbol", "period_end"],
                columns="concept",
                values="value",
                aggfunc="last",
                observed=True,
            )
            if {"total_assets", "total_liabilities", "total_equity"} <= set(wide.columns):
                last = wide.groupby(level="symbol", observed=True).tail(1).dropna()
                gap = (
                    last["total_assets"] - last["total_liabilities"] - last["total_equity"]
                ).abs()
                rel = gap / last["total_assets"].abs()
                for key, v in rel[rel > identity_tolerance].items():
                    sym = str(key[0]) if isinstance(key, tuple) else str(key)
                    issues.append(
                        QcIssue(
                            "WARN",
                            "identité comptable",
                            str(sym),
                            f"actif ≠ passif + capitaux propres (écart {v:.0%})",
                        )
                    )
    return issues


def issues_frame(issues: list[QcIssue]) -> pd.DataFrame:
    return pd.DataFrame(
        [i.__dict__ for i in issues], columns=["severity", "check", "symbol", "detail"]
    )
