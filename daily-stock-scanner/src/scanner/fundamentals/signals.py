"""Module 2 : calcul des signaux fondamentaux à une date (point-in-time).

Point d'entrée : :func:`compute_fundamental_signals`. Il ne lit que la ``PitView`` et
renvoie un tableau symbole x colonnes :

* les signaux du catalogue (``F-GP``, ``F-EY``…), sous leur identifiant ;
* des champs descriptifs affichés dans le rapport (``desc_*``) ;
* des champs de contrôle : devise cohérente, âge des états, décalage estimé, zone Altman.

Les définitions exactes sont documentées dans ``config/signals.yaml``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scanner.core.config import FundamentalsCfg
from scanner.data.pit import PitView
from scanner.fundamentals.health import altman_z, altman_z2, altman_zone, beneish_m, piotroski
from scanner.fundamentals.statements import (
    annual_table,
    latest_stocks,
    latest_versions,
    quarterly_eps,
    safe_div,
    statement_currency,
    stock_one_year_ago,
    ttm_flows,
)

SUE_VALID_DAYS = 90  # ~60 séances : fenêtre documentée du PEAD


def _col(df: pd.DataFrame, name: str, index: pd.Index) -> pd.Series:
    if df is None or df.empty or name not in df.columns:
        return pd.Series(np.nan, index=index, dtype=float)
    return df[name].reindex(index).astype(float)


def _annual_stats(annual: pd.DataFrame) -> pd.DataFrame:
    """Stats multi-exercices : stabilité du ROIC et de la marge, croissance de la rentabilité."""
    if annual.empty:
        return pd.DataFrame()
    a = annual.copy()

    def get(c: str) -> pd.Series:
        return a[c].astype(float) if c in a.columns else pd.Series(np.nan, index=a.index)

    gp = get("gross_profit").fillna(get("revenue") - get("cogs"))
    tax_rate = safe_div(get("income_tax"), get("pretax_income")).clip(0, 0.35).fillna(0.25)
    debt = get("long_term_debt").fillna(0) + get("short_term_debt").fillna(0)
    invested = get("total_equity") + debt - get("cash").fillna(0)
    a["_roic"] = safe_div(get("ebit") * (1 - tax_rate), invested.where(invested > 0))
    a["_gm"] = safe_div(gp, get("revenue"))
    a["_gpa"] = safe_div(gp, get("total_assets"))
    g = a.groupby(level="symbol")
    out = pd.DataFrame(
        {
            "roic_std": g["_roic"].agg(
                lambda s: s.tail(5).std() if s.tail(5).notna().sum() >= 3 else np.nan
            ),
            "gm_std": g["_gm"].agg(
                lambda s: s.tail(5).std() if s.tail(5).notna().sum() >= 3 else np.nan
            ),
        }
    )

    def _dprof(s: pd.Series) -> float:
        s = s.dropna().tail(5)
        if len(s) < 3:
            return np.nan
        return float((s.iloc[-1] - s.iloc[0]) / (len(s) - 1))

    out["gpa_trend"] = g["_gpa"].agg(_dprof)
    return out


def compute_fundamental_signals(
    view: PitView, cfg: FundamentalsCfg, symbols: list[str] | None = None
) -> pd.DataFrame:
    """Signaux fondamentaux pour ``symbols`` (par défaut : titres cotés) à ``view.as_of``."""
    symbols = symbols if symbols is not None else view.listed_symbols()
    index = pd.Index(sorted(symbols), name="symbol")
    out = pd.DataFrame(index=index)
    facts = view.facts()
    if facts.empty or not len(index):
        return out
    facts = facts[facts["symbol"].isin(index)]
    latest = latest_versions(facts)
    as_of = pd.Timestamp(view.last_price_date)
    max_age = pd.Timedelta(days=cfg.max_statement_age_days)

    ttm, ttm_end = ttm_flows(latest)
    stocks, stock_date = latest_stocks(latest)
    annual = annual_table(latest)
    stats = _annual_stats(annual)

    fresh_flow = (as_of - ttm_end.reindex(index)) <= max_age
    fresh_stock = (as_of - stock_date.reindex(index)) <= max_age
    T = lambda c: _col(ttm, c, index).where(fresh_flow)  # noqa: E731
    B = lambda c: _col(stocks, c, index).where(fresh_stock)  # noqa: E731

    # ---------------------------------------------------------------- marché et devise
    sec = view.securities().set_index("symbol").reindex(index)
    close = view.panel("close")
    last_close = (
        close.ffill().iloc[-1].reindex(index) if not close.empty else pd.Series(np.nan, index=index)
    )
    shares = B("shares_outstanding")
    mcap = last_close * shares
    ccy = statement_currency(latest).reindex(index)
    currency_ok = (ccy.astype("string") == sec["currency"].astype("string")).fillna(False)
    mcap = mcap.where(currency_ok)
    sector = sec["sector"].astype("string")
    is_fin = sector.isin(cfg.financial_sectors).fillna(False)

    revenue, cogs = T("revenue"), T("cogs")
    gp = T("gross_profit").fillna(revenue - cogs)
    ebit, cfo, capex = T("ebit"), T("cfo"), T("capex")
    ni, interest = T("net_income"), T("interest_expense")
    assets = B("total_assets")
    cash = B("cash").fillna(0)
    debt = B("long_term_debt").fillna(0) + B("short_term_debt").fillna(0)
    equity = B("total_equity")
    ev = mcap + debt - cash
    ev = ev.where(ev > 0)

    tax_rate = safe_div(T("income_tax"), T("pretax_income")).clip(0, 0.35).fillna(0.25)
    invested = equity + debt - cash

    out["F-GP"] = safe_div(gp, assets)
    out["F-CBOP"] = safe_div(cfo + interest.fillna(0), assets)
    out["F-ROIC"] = safe_div(ebit * (1 - tax_rate), invested.where(invested > 0))
    out["F-ROIC-STAB"] = _col(stats, "roic_std", index)
    out["F-GM-STAB"] = _col(stats, "gm_std", index)
    out["F-DPROF"] = _col(stats, "gpa_trend", index)
    out["F-EY"] = safe_div(ebit, ev)
    out["F-FCFY"] = safe_div(cfo - capex.fillna(0), ev)
    out["F-BM"] = safe_div(equity.where(equity > 0), mcap)
    out["F-LEV"] = safe_div(debt, assets)
    cover = safe_div(ebit, interest)
    out["F-COVER"] = cover.where(interest > 0, np.where(ebit > 0, 50.0, np.nan)).clip(upper=50)

    # ------------------------------------------------ comparaisons annuelles (t, t-1, t-2)
    if not annual.empty:
        a = annual.sort_index()
        g = a.groupby(level="symbol")
        cur = g.tail(1).reset_index(level="period_end")
        prev = g.nth(-2).reset_index(level="period_end") if len(a) else pd.DataFrame()
        prev2 = g.nth(-3).reset_index(level="period_end") if len(a) else pd.DataFrame()
        fresh_fy = (as_of - cur["period_end"].reindex(index)) <= max_age

        def A(frame: pd.DataFrame, c: str) -> pd.Series:
            return _col(frame, c, index).where(fresh_fy)

        a_gp = A(cur, "gross_profit").fillna(A(cur, "revenue") - A(cur, "cogs"))
        p_gp = A(prev, "gross_profit").fillna(A(prev, "revenue") - A(prev, "cogs"))
        f_score, _ = piotroski(
            ni=A(cur, "net_income"),
            cfo=A(cur, "cfo"),
            assets=A(cur, "total_assets"),
            assets_prev=A(prev, "total_assets"),
            assets_prev2=A(prev2, "total_assets"),
            ni_prev=A(prev, "net_income"),
            ltd=A(cur, "long_term_debt"),
            ltd_prev=A(prev, "long_term_debt"),
            ca=A(cur, "current_assets"),
            cl=A(cur, "current_liabilities"),
            ca_prev=A(prev, "current_assets"),
            cl_prev=A(prev, "current_liabilities"),
            shares=A(cur, "shares_outstanding"),
            shares_prev=A(prev, "shares_outstanding"),
            revenue=A(cur, "revenue"),
            revenue_prev=A(prev, "revenue"),
            gp=a_gp,
            gp_prev=p_gp,
        )
        out["F-PIOT"] = f_score
        avg_assets = (A(cur, "total_assets") + A(prev, "total_assets")) / 2
        out["F-ACCR"] = safe_div(A(cur, "net_income") - A(cur, "cfo"), avg_assets)
        out["F-AGR"] = safe_div(A(cur, "total_assets"), A(prev, "total_assets")) - 1
        m, _ = beneish_m(
            rec=A(cur, "receivables"),
            rec_p=A(prev, "receivables"),
            sales=A(cur, "revenue"),
            sales_p=A(prev, "revenue"),
            cogs=A(cur, "cogs").fillna(A(cur, "revenue") - a_gp),
            cogs_p=A(prev, "cogs").fillna(A(prev, "revenue") - p_gp),
            ca=A(cur, "current_assets"),
            ca_p=A(prev, "current_assets"),
            ppe=A(cur, "ppe_net"),
            ppe_p=A(prev, "ppe_net"),
            ta=A(cur, "total_assets"),
            ta_p=A(prev, "total_assets"),
            dep=A(cur, "depreciation"),
            dep_p=A(prev, "depreciation"),
            sga=A(cur, "sga"),
            sga_p=A(prev, "sga"),
            cl=A(cur, "current_liabilities"),
            cl_p=A(prev, "current_liabilities"),
            ltd=A(cur, "long_term_debt"),
            ltd_p=A(prev, "long_term_debt"),
            ni=A(cur, "net_income"),
            cfo=A(cur, "cfo"),
        )
        out["F-BENM"] = m
        out["fy_end"] = cur["period_end"].reindex(index)
    else:
        for c in ("F-PIOT", "F-ACCR", "F-AGR", "F-BENM"):
            out[c] = np.nan

    # --------------------------------------------------------------------- Altman
    wc = B("current_assets") - B("current_liabilities")
    tl = B("total_liabilities").fillna(B("liabilities_and_equity") - equity)
    original = (sector.isin(cfg.altman_original_sectors) & (sec["country"] == "US")).fillna(False)
    z_orig = altman_z(wc, B("retained_earnings"), ebit, mcap, tl, revenue, assets)
    z_alt = altman_z2(wc, B("retained_earnings"), ebit, equity, tl, assets)
    z = z_orig.where(original, z_alt)
    out["F-ALTZ"] = z
    out["altman_variant"] = np.where(original, "Z", "Z''")
    out["altman_zone"] = altman_zone(z, original)

    # ------------------------------------------------------------ émissions nettes
    sh_prev = stock_one_year_ago(latest, "shares_outstanding", stock_date).reindex(index)
    out["F-ISSUE"] = -np.log(safe_div(shares, sh_prev).where(lambda s: s > 0))

    # -------------------------------------------------------------------- SUE
    out["F-SUE"] = _sue(latest, index, view.as_of_ts)

    # ------------------------------------------------ E/P par rapport à l'historique (OBS)
    out["F-PE-HIST"] = _ep_vs_history(annual, close, shares, ni, mcap, index)

    # --------------------------------------------------------- financières : exclusions
    not_for_fin = [
        "F-GP",
        "F-CBOP",
        "F-ROIC",
        "F-ROIC-STAB",
        "F-GM-STAB",
        "F-ACCR",
        "F-EY",
        "F-FCFY",
        "F-PIOT",
        "F-ALTZ",
        "F-BENM",
        "F-COVER",
        "F-LEV",
        "F-DPROF",
    ]
    for c in not_for_fin:
        if c in out.columns:
            out[c] = out[c].where(~is_fin)
    out.loc[is_fin, "altman_zone"] = None

    # ------------------------------------------------------- champs descriptifs / contrôle
    out["desc_revenue_ttm"] = revenue
    out["desc_net_margin"] = safe_div(ni, revenue)
    out["desc_fcf_conversion"] = safe_div(cfo - capex.fillna(0), ni.where(ni > 0))
    out["desc_market_cap"] = mcap
    out["desc_ev"] = ev
    out["statement_currency"] = ccy
    out["currency_ok"] = currency_ok
    out["statement_date"] = stock_date.reindex(index)
    lag_est = facts.groupby("symbol")["lag_estimated"].agg(lambda s: bool(s.fillna(False).any()))
    out["lag_estimated"] = lag_est.reindex(index).fillna(False).astype(bool)
    out["is_financial"] = is_fin
    return out


def _sue(latest: pd.DataFrame, index: pd.Index, as_of: pd.Timestamp) -> pd.Series:
    """SUE à marche aléatoire saisonnière, valable ``SUE_VALID_DAYS`` après publication."""
    eps = quarterly_eps(latest)
    if eps.empty:
        return pd.Series(np.nan, index=index)
    eps = eps.sort_values(["symbol", "period_end"])
    g = eps.groupby("symbol")
    lag_end = g["period_end"].shift(4)
    gap = (eps["period_end"] - lag_end).dt.days
    diff = (eps["value"] - g["value"].shift(4)).where((gap >= 330) & (gap <= 400))
    eps["diff"] = diff
    eps["sd"] = eps.groupby("symbol")["diff"].transform(
        lambda s: s.shift(1).rolling(8, min_periods=4).std()
    )
    last = eps.groupby("symbol").tail(1).set_index("symbol")
    sue = safe_div(last["diff"], last["sd"].where(last["sd"] > 1e-9))
    fresh = (as_of - last["available_at"]).dt.days <= SUE_VALID_DAYS
    return sue.where(fresh).reindex(index)


def _ep_vs_history(
    annual: pd.DataFrame,
    close: pd.DataFrame,
    shares: pd.Series,
    ni_ttm: pd.Series,
    mcap: pd.Series,
    index: pd.Index,
) -> pd.Series:
    """Percentile du E/P actuel parmi les E/P de fin d'exercice (5 ans), à leur publication."""
    if annual.empty or close.empty or "net_income" not in annual.columns:
        return pd.Series(np.nan, index=index)
    ep_now = safe_div(ni_ttm, mcap)
    a = annual.reset_index()
    a = a[a["symbol"].isin(index)].dropna(subset=["available_at"])
    rows = []
    cidx = close.index
    for sym, grp in a.groupby("symbol"):
        if sym not in close.columns or pd.isna(ep_now.get(sym)):
            continue
        hist = []
        for _, r in grp.tail(5).iterrows():
            day = pd.Timestamp(r["available_at"]).tz_localize(None).normalize()
            pos = cidx.searchsorted(day)
            if pos >= len(cidx):
                continue
            px = close[sym].iloc[pos]
            sh = r.get("shares_outstanding", np.nan)
            if pd.notna(px) and pd.notna(sh) and sh > 0:
                hist.append(r["net_income"] / (px * sh))
        if len(hist) >= 3:
            rows.append((sym, float((np.array(hist) < ep_now[sym]).mean())))
    return pd.Series(dict(rows), dtype=float).reindex(index)
