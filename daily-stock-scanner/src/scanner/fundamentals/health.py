"""Scores de santé financière : Piotroski F, Altman Z / Z'', Beneish M.

Fonctions vectorisées : chaque argument est une ``pd.Series`` indexée par symbole
(exercice t, t-1, t-2). Les formules suivent les articles d'origine :

* Piotroski (2000), *Journal of Accounting Research* 38 — 9 critères binaires ;
* Altman (1968), *Journal of Finance* 23(4) — Z original (industriels) ; Altman (2005),
  *Emerging Markets Review* 6(4) — Z'' (non industriels et émergents) ;
* Beneish (1999), *Financial Analysts Journal* 55(5) — modèle à 8 variables.

Ces scores ne s'appliquent pas aux financières (banques, assurances, foncières) : le
module appelant les met à NaN pour ces secteurs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scanner.fundamentals.statements import safe_div

S = pd.Series


# ------------------------------------------------------------------------------ Piotroski


def piotroski(
    ni: S,
    cfo: S,
    assets: S,
    assets_prev: S,
    assets_prev2: S,
    ni_prev: S,
    ltd: S,
    ltd_prev: S,
    ca: S,
    cl: S,
    ca_prev: S,
    cl_prev: S,
    shares: S,
    shares_prev: S,
    revenue: S,
    revenue_prev: S,
    gp: S,
    gp_prev: S,
    min_criteria: int = 7,
) -> tuple[S, S]:
    """F-Score (0-9) et nombre de critères calculables.

    Le score est NaN si moins de ``min_criteria`` critères sont calculables (on n'impute pas
    un critère manquant à 0, ce qui biaiserait le score vers le bas).
    """
    avg_assets = (assets + assets_prev) / 2
    avg_assets_prev = (assets_prev + assets_prev2.fillna(assets_prev)) / 2
    roa = safe_div(ni, assets_prev)
    roa_prev = safe_div(ni_prev, assets_prev2.fillna(assets_prev))
    criteria = {
        "roa_pos": roa > 0,
        "cfo_pos": cfo > 0,
        "droa_pos": roa > roa_prev,
        "accrual": safe_div(cfo, assets_prev) > roa,
        "dlever": safe_div(ltd.fillna(0), avg_assets)
        < safe_div(ltd_prev.fillna(0), avg_assets_prev),
        "dliquid": safe_div(ca, cl) > safe_div(ca_prev, cl_prev),
        "no_issue": shares <= shares_prev * 1.001,
        "dmargin": safe_div(gp, revenue) > safe_div(gp_prev, revenue_prev),
        "dturn": safe_div(revenue, assets_prev)
        > safe_div(revenue_prev, assets_prev2.fillna(assets_prev)),
    }
    inputs = {
        "roa_pos": [ni, assets_prev],
        "cfo_pos": [cfo],
        "droa_pos": [ni, ni_prev, assets_prev],
        "accrual": [cfo, ni, assets_prev],
        "dlever": [assets, assets_prev],
        "dliquid": [ca, cl, ca_prev, cl_prev],
        "no_issue": [shares, shares_prev],
        "dmargin": [gp, revenue, gp_prev, revenue_prev],
        "dturn": [revenue, revenue_prev, assets_prev],
    }
    score = pd.Series(0.0, index=ni.index)
    count = pd.Series(0, index=ni.index)
    for name, cond in criteria.items():
        available = pd.concat(inputs[name], axis=1).notna().all(axis=1)
        score += (cond & available).astype(float)
        count += available.astype(int)
    return score.where(count >= min_criteria), count


# --------------------------------------------------------------------------------- Altman


def altman_z(wc: S, re: S, ebit: S, mve: S, tl: S, sales: S, ta: S) -> S:
    """Z original : 1,2 X1 + 1,4 X2 + 3,3 X3 + 0,6 X4 + 1,0 X5 (zones 1,81 / 2,99)."""
    return (
        1.2 * safe_div(wc, ta)
        + 1.4 * safe_div(re, ta)
        + 3.3 * safe_div(ebit, ta)
        + 0.6 * safe_div(mve, tl)
        + 1.0 * safe_div(sales, ta)
    )


def altman_z2(wc: S, re: S, ebit: S, bve: S, tl: S, ta: S) -> S:
    """Z'' : 6,56 X1 + 3,26 X2 + 6,72 X3 + 1,05 X4 (zones 1,10 / 2,60)."""
    return (
        6.56 * safe_div(wc, ta)
        + 3.26 * safe_div(re, ta)
        + 6.72 * safe_div(ebit, ta)
        + 1.05 * safe_div(bve, tl)
    )


def altman_zone(z: S, original: S) -> S:
    """``distress`` / ``grey`` / ``safe`` selon la variante utilisée (bool ``original``)."""
    lo = np.where(original, 1.81, 1.10)
    hi = np.where(original, 2.99, 2.60)
    zone = np.where(z < lo, "distress", np.where(z > hi, "safe", "grey"))
    return pd.Series(zone, index=z.index).where(z.notna())


# -------------------------------------------------------------------------------- Beneish

BENEISH_COEF = {
    "const": -4.84,
    "DSRI": 0.920,
    "GMI": 0.528,
    "AQI": 0.404,
    "SGI": 0.892,
    "DEPI": 0.115,
    "SGAI": -0.172,
    "TATA": 4.679,
    "LVGI": -0.327,
}


def beneish_m(
    rec: S,
    rec_p: S,
    sales: S,
    sales_p: S,
    cogs: S,
    cogs_p: S,
    ca: S,
    ca_p: S,
    ppe: S,
    ppe_p: S,
    ta: S,
    ta_p: S,
    dep: S,
    dep_p: S,
    sga: S,
    sga_p: S,
    cl: S,
    cl_p: S,
    ltd: S,
    ltd_p: S,
    ni: S,
    cfo: S,
) -> tuple[S, S]:
    """M-Score à 8 variables et nombre d'indices imputés à 1 (neutre).

    Convention usuelle : un indice non calculable (ex. SG&A non publiés) est fixé à 1.
    Les indices centraux (DSRI, GMI, AQI, SGI, TATA) sont exigés : sinon M = NaN.
    """
    gm = safe_div(sales - cogs, sales)
    gm_p = safe_div(sales_p - cogs_p, sales_p)
    idx = {
        "DSRI": safe_div(safe_div(rec, sales), safe_div(rec_p, sales_p)),
        "GMI": safe_div(gm_p, gm),
        "AQI": safe_div(1 - safe_div(ca + ppe, ta), 1 - safe_div(ca_p + ppe_p, ta_p)),
        "SGI": safe_div(sales, sales_p),
        "DEPI": safe_div(safe_div(dep_p, dep_p + ppe_p), safe_div(dep, dep + ppe)),
        "SGAI": safe_div(safe_div(sga, sales), safe_div(sga_p, sales_p)),
        "LVGI": safe_div(safe_div(cl + ltd.fillna(0), ta), safe_div(cl_p + ltd_p.fillna(0), ta_p)),
        "TATA": safe_div(ni - cfo, ta),
    }
    core_ok = (
        pd.concat([idx[k] for k in ("DSRI", "GMI", "AQI", "SGI", "TATA")], axis=1)
        .notna()
        .all(axis=1)
    )
    imputed = pd.Series(0, index=rec.index)
    m = pd.Series(BENEISH_COEF["const"], index=rec.index)
    for name, values in idx.items():
        if name in ("DEPI", "SGAI", "LVGI"):
            imputed += values.isna().astype(int)
            values = values.fillna(1.0)
        m = m + BENEISH_COEF[name] * values
    return m.where(core_ok), imputed
