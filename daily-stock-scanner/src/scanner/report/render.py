"""Module 12 : rapport quotidien (Markdown pour l'archive, HTML pour l'email), en français.

Règles de rédaction : chaque chiffre affiché provient des données (statut « Fait ») ; tout
ce qui n'est pas encore disponible est annoncé comme tel ; aucune thèse n'est inventée
(la rédaction par LLM arrive en Phase 3, avec contrôle de fidélité aux sources).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from scanner.core.config import AppConfig, BookId
from scanner.scoring.composite import BookScores

TEMPLATES = Path(__file__).parent / "templates"

PCT_SIGNALS = {
    "Q-MOM-12-1",
    "Q-MOM-6-1",
    "Q-INDMOM",
    "Q-RS",
    "Q-EAR",
    "Q-STREV",
    "Q-LOWVOL",
    "F-GP",
    "F-CBOP",
    "F-ROIC",
    "F-ACCR",
    "F-EY",
    "F-FCFY",
    "F-AGR",
    "F-ISSUE",
    "F-LEV",
    "F-DPROF",
    "F-ROIC-STAB",
    "F-GM-STAB",
    "F-PE-HIST",
}
SUFFIX = {"F-PIOT": " / 9", "Q-TREND": " / 8", "F-BM": " x", "F-COVER": " x"}


def fmt_value(signal: str, value: Any) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)) or pd.isna(value):
        return "n.d."
    v = float(value)
    if signal in PCT_SIGNALS:
        return f"{v * 100:+.1f} %" if signal not in {"F-PE-HIST"} else f"{v * 100:.0f}e percentile"
    if signal == "Q-52WH":
        return f"{v * 100:.0f} % du plus haut"
    if signal == "Q-ABVOL":
        return f"volume x{math.exp(v):.1f} vs moyenne"
    return f"{v:.2f}{SUFFIX.get(signal, '')}"


@dataclass
class Idea:
    book: str
    side: str
    rank: int
    symbol: str
    name: str
    sector: str
    country: str
    score: float
    drivers: list[dict[str, str]]
    families: dict[str, float]
    flags: list[str]
    execution: list[str]
    invalidation: str
    catalysts: str


@dataclass
class ReportContext:
    run_date: str
    as_of: str
    last_price_date: str
    run_id: str
    config_fingerprint: str
    data_sources: list[dict[str, str]]
    universe_size: int
    universe_liquid: int
    books: dict[str, dict[str, Any]]
    changes: list[dict[str, str]]
    alerts: list[str]
    qc: list[dict[str, str]]
    performance: list[dict[str, Any]]
    notices: list[str] = field(default_factory=list)
    demo: bool = False


def _invalidation(book: BookId, side: str, q: pd.Series) -> str:
    last, atr, sma200 = q.get("last_close"), q.get("risk_atr20"), q.get("tech_sma200")
    if book == "S" and pd.notna(last) and pd.notna(atr):
        level = last - 2.5 * atr if side == "long" else last + 2.5 * atr
        where = "sous" if side == "long" else "au-dessus de"
        return f"technique : clôture {where} {level:.2f} (2,5 x ATR 20 j)"
    if book == "M" and pd.notna(sma200):
        return (
            f"technique : clôture {'sous' if side == 'long' else 'au-dessus de'} la moyenne "
            f"200 j ({sma200:.2f}, cours ajusté) ; logique : dégradation du score sous la médiane"
        )
    return (
        "logique : Piotroski ≤ 3 ou passage d'Altman en zone de détresse au prochain exercice "
        "publié (suivi automatique en Phase 4)"
    )


def build_ideas(
    book: BookId,
    ideas: pd.DataFrame,
    scores: BookScores,
    values: pd.DataFrame,
    universe: pd.DataFrame,
    securities: pd.DataFrame,
    config: AppConfig,
    catalysts: pd.Series | None = None,
) -> list[Idea]:
    out = []
    names = securities.set_index("symbol")["name"] if not securities.empty else pd.Series(dtype=str)
    uni = universe.set_index("symbol") if not universe.empty else pd.DataFrame()
    for _, row in ideas[ideas["book"] == book].iterrows():
        sym = row["symbol"]
        contrib = scores.contributions.loc[sym].dropna()
        top = contrib.reindex(contrib.abs().sort_values(ascending=False).index[:4])
        drivers = []
        for sig, c in top.items():
            d = config.signals.by_id[str(sig)]
            drivers.append(
                {
                    "signal": d.name,
                    "value": fmt_value(str(sig), values.at[sym, sig]),
                    "contribution": f"{c:+.2f}",
                }
            )
        flags = [f for f in str(scores.flags.at[sym, "flags"]).split(" | ") if f]
        execution = []
        if not uni.empty and sym in uni.index:
            u = uni.loc[sym]
            if row["side"] == "long":
                execution.append("éligible PEA (approx.)" if bool(u["pea_eligible"]) else "CTO")
            else:
                srd = u.get("srd_eligible")
                execution.append("short papier" + (" — SRD possible" if srd is True else ""))
            if bool(u["ttf_applicable"]):
                execution.append("TTF 0,4 % à l'achat")
        cat = catalysts.get(sym) if catalysts is not None else None
        out.append(
            Idea(
                book=book,
                side=row["side"],
                rank=int(row["rank"]),
                symbol=sym,
                name=str(names.get(sym, sym)),
                sector=str(values.at[sym, "sector"]),
                country=str(uni.loc[sym, "country"]) if not uni.empty and sym in uni.index else "?",
                score=float(row["score"]),
                drivers=drivers,
                families={k: float(v) for k, v in scores.families.loc[sym].items()},
                flags=flags,
                execution=execution,
                invalidation=_invalidation(book, row["side"], values.loc[sym]),
                catalysts=str(cat)
                if cat
                else "prochaine publication : non disponible (source calendrier absente)",
            )
        )
    return out


def render(ctx: ReportContext) -> tuple[str, str]:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["num"] = lambda v, d=2: (
        "n.d." if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.{d}f}"
    )
    env.filters["pct"] = lambda v, d=1: (
        "n.d."
        if v is None or (isinstance(v, float) and not math.isfinite(v))
        else f"{v * 100:.{d}f} %"
    )
    data = ctx.__dict__
    return (
        env.get_template("daily.md.j2").render(**data),
        env.get_template("daily.html.j2").render(**data),
    )
