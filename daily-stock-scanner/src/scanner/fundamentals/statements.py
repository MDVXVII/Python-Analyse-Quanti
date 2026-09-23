"""Reconstitution point-in-time des états financiers à partir des faits bitemporels.

Entrée : faits déjà filtrés par :class:`~scanner.data.pit.PitView` (``available_at <= as_of``).
Sorties (toutes indexées par symbole, calcul vectorisé sur tout l'univers) :

* :func:`latest_versions` — pour chaque (symbole, concept, période), la version la plus
  récente **connue à la date** (les retraitements ultérieurs sont invisibles avant leur
  publication) ;
* :func:`annual_table` — exercices complets (flux FY + bilan de clôture), 6 derniers max ;
* :func:`ttm_flows` — flux sur 12 mois glissants : somme des 4 derniers trimestres (le T4
  est déduit de l'exercice : FY - T1 - T2 - T3, car un 10-K ne publie que l'exercice) ou
  des 2 derniers semestres, sinon dernier exercice ;
* :func:`latest_stocks` — dernier bilan disponible ;
* :func:`quarterly_eps` — BPA trimestriels discrets (pour la SUE).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scanner.fundamentals.concepts import CONCEPTS

FLOW_CONCEPTS = [c for c, d in CONCEPTS.items() if d.nature == "flow"]
STOCK_CONCEPTS = [c for c, d in CONCEPTS.items() if d.nature == "stock"]


def latest_versions(facts: pd.DataFrame) -> pd.DataFrame:
    """Meilleure version de chaque fait : tag préféré, puis publication la plus récente."""
    if facts.empty:
        return facts
    f = facts.copy()
    f["tag_rank"] = f["tag_rank"].fillna(0).astype(int)
    f["_start"] = f["period_start"].fillna(pd.Timestamp("1900-01-01"))
    f = f.sort_values(
        ["symbol", "concept", "_start", "period_end", "tag_rank", "available_at"],
        ascending=[True, True, True, True, True, False],
    )
    f = f.drop_duplicates(subset=["symbol", "concept", "_start", "period_end"], keep="first")
    return f.drop(columns="_start").reset_index(drop=True)


def _pivot(df: pd.DataFrame, index: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(index=index, columns="concept", values="value", aggfunc="last")


def statement_currency(latest: pd.DataFrame) -> pd.Series:
    """Devise dominante des montants monétaires, par symbole."""
    mon = latest[latest["concept"].isin(["revenue", "total_assets"]) & latest["unit"].notna()]
    if mon.empty:
        return pd.Series(dtype="string")
    return mon.groupby("symbol")["unit"].agg(lambda s: s.value_counts().index[0])


def annual_table(latest: pd.DataFrame, max_years: int = 6) -> pd.DataFrame:
    """Exercices : flux annuels (FY) joints au bilan de clôture. Index (symbol, period_end)."""
    fy = latest[(latest["fiscal_period"] == "FY") & latest["concept"].isin(FLOW_CONCEPTS)]
    flows = _pivot(fy, ["symbol", "period_end"])
    stocks_df = latest[latest["concept"].isin(STOCK_CONCEPTS)]
    stocks = _pivot(stocks_df, ["symbol", "period_end"])
    if flows.empty:
        return pd.DataFrame()
    table = flows.join(stocks, how="left", rsuffix="_stock") if not stocks.empty else flows
    # disponibilité de l'exercice = publication la plus tardive de ses faits FY
    avail = fy.groupby(["symbol", "period_end"])["available_at"].max().rename("available_at")
    table = table.join(avail)
    table = table.sort_index()
    return table.groupby(level="symbol", group_keys=False).tail(max_years)


def _discrete_periods(
    latest: pd.DataFrame, concepts: list[str], short: str, months: int
) -> pd.DataFrame:
    """Périodes discrètes (``Q`` ou ``H``), en déduisant la dernière période de l'exercice.

    Retourne un format long : symbol, concept, period_start, period_end, value.
    """
    base = latest[latest["concept"].isin(concepts)]
    parts = base[base["fiscal_period"] == short][
        ["symbol", "concept", "period_start", "period_end", "value"]
    ]
    fy = base[base["fiscal_period"] == "FY"][
        ["symbol", "concept", "period_start", "period_end", "value"]
    ]
    if fy.empty or parts.empty:
        return parts.reset_index(drop=True)
    n_parts = 12 // months
    # Rattache chaque période à l'exercice qui la contient (jointure « asof » : taille linéaire).
    fy_r = fy.rename(
        columns={
            "period_start": "period_start_fy",
            "period_end": "period_end_fy",
            "value": "value_fy",
        }
    ).sort_values("period_end_fy")
    m = pd.merge_asof(
        parts.sort_values("period_end"),
        fy_r,
        left_on="period_end",
        right_on="period_end_fy",
        by=["symbol", "concept"],
        direction="forward",
        tolerance=pd.Timedelta(days=380),
    )
    tol = pd.Timedelta(days=7)
    inside = (m["period_start"] >= m["period_start_fy"] - tol) & (
        m["period_end"] <= m["period_end_fy"] + tol
    )
    m = m[inside]
    agg = m.groupby(["symbol", "concept", "period_start_fy", "period_end_fy"]).agg(
        parts_sum=("value", "sum"),
        n=("value", "size"),
        last_end=("period_end", "max"),
        fy_value=("value_fy", "first"),
    )
    missing = agg[agg["n"] == n_parts - 1].reset_index()
    if not missing.empty:
        derived = pd.DataFrame(
            {
                "symbol": missing["symbol"],
                "concept": missing["concept"],
                "period_start": missing["last_end"] + pd.Timedelta(days=1),
                "period_end": missing["period_end_fy"],
                "value": missing["fy_value"] - missing["parts_sum"],
            }
        )
        span = (derived["period_end"] - derived["period_start"]).dt.days
        derived = derived[(span > months * 30 - 20) & (span < months * 30 + 20)]
        # ne pas écraser une période déjà publiée
        parts = pd.concat([parts, derived], ignore_index=True).drop_duplicates(
            subset=["symbol", "concept", "period_end"], keep="first"
        )
    return parts.sort_values(["symbol", "concept", "period_end"]).reset_index(drop=True)


def _rolling_sum(parts: pd.DataFrame, n: int) -> pd.DataFrame:
    """Somme des ``n`` dernières périodes si elles couvrent ~12 mois contigus."""
    if parts.empty:
        return pd.DataFrame(columns=["symbol", "concept", "value", "end"])
    last = parts.groupby(["symbol", "concept"]).tail(n)
    agg = last.groupby(["symbol", "concept"]).agg(
        value=("value", "sum"),
        count=("value", "size"),
        start=("period_start", "min"),
        end=("period_end", "max"),
    )
    span = (agg["end"] - agg["start"]).dt.days
    ok = (agg["count"] == n) & (span >= 350) & (span <= 380)
    return agg[ok].reset_index()[["symbol", "concept", "value", "end"]]


def ttm_flows(latest: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Flux sur 12 mois glissants. Retourne (valeurs symbol x concept, date de fin par symbole)."""
    candidates = []
    fy = latest[(latest["fiscal_period"] == "FY") & latest["concept"].isin(FLOW_CONCEPTS)]
    if not fy.empty:
        last_fy = fy.sort_values("period_end").groupby(["symbol", "concept"]).tail(1)
        candidates.append(
            last_fy[["symbol", "concept", "value", "period_end"]]
            .rename(columns={"period_end": "end"})
            .assign(pref=2)
        )
    for short, months, pref in (("Q", 3, 0), ("H", 6, 1)):
        parts = _discrete_periods(latest, FLOW_CONCEPTS, short, months)
        rs = _rolling_sum(parts, 12 // months)
        if not rs.empty:
            candidates.append(rs.assign(pref=pref))
    if not candidates:
        return pd.DataFrame(), pd.Series(dtype="datetime64[ns]")
    allc = pd.concat(candidates, ignore_index=True)
    # la fenêtre la plus récente l'emporte ; à date égale, trimestres > semestres > exercice
    allc = allc.sort_values(
        ["symbol", "concept", "end", "pref"], ascending=[True, True, False, True]
    )
    best = allc.drop_duplicates(subset=["symbol", "concept"], keep="first")
    values = best.pivot(index="symbol", columns="concept", values="value")
    ends = best.groupby("symbol")["end"].max()
    return values, ends


def latest_stocks(latest: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Dernier bilan (complété, si besoin, par le bilan précédent). Retourne (valeurs, date)."""
    st = latest[latest["concept"].isin(STOCK_CONCEPTS)]
    if st.empty:
        return pd.DataFrame(), pd.Series(dtype="datetime64[ns]")
    wide = _pivot(st, ["symbol", "period_end"]).sort_index()
    last2 = wide.groupby(level="symbol", group_keys=False).tail(2)
    values = last2.groupby(level="symbol").last()
    dates = last2.reset_index().groupby("symbol")["period_end"].max()
    return values, dates


def stock_one_year_ago(
    latest: pd.DataFrame, concept: str, ref_dates: pd.Series, tolerance_days: int = 60
) -> pd.Series:
    """Valeur d'un stock ~1 an avant ``ref_dates`` (par symbole), à ``tolerance_days`` près."""
    st = latest[latest["concept"] == concept][["symbol", "period_end", "value"]]
    if st.empty or ref_dates.empty:
        return pd.Series(dtype=float)
    ref = ref_dates.rename("ref").reset_index()
    m = st.merge(ref, on="symbol")
    m["dist"] = (m["period_end"] - (m["ref"] - pd.Timedelta(days=365))).dt.days.abs()
    m = m[m["dist"] <= tolerance_days].sort_values("dist")
    return m.drop_duplicates("symbol").set_index("symbol")["value"]


def quarterly_eps(latest: pd.DataFrame) -> pd.DataFrame:
    """BPA trimestriels discrets avec leur date de disponibilité (T4 déduit de l'exercice)."""
    eps = latest[latest["concept"] == "eps_diluted"]
    if eps.empty:
        return pd.DataFrame(columns=["symbol", "period_end", "value", "available_at"])
    parts = _discrete_periods(eps, ["eps_diluted"], "Q", 3)
    avail = eps.groupby(["symbol", "period_end"])["available_at"].max().reset_index()
    out = parts.merge(avail, on=["symbol", "period_end"], how="left")
    return out[["symbol", "period_end", "value", "available_at"]]


def safe_div(a: pd.Series | float, b: pd.Series | float) -> pd.Series:
    """Division qui renvoie NaN (et non ±inf) quand le dénominateur est nul ou manquant."""
    with np.errstate(divide="ignore", invalid="ignore"):
        out = pd.Series(a) / pd.Series(b) if not isinstance(a, pd.Series) else a / b
    return out.replace([np.inf, -np.inf], np.nan)
