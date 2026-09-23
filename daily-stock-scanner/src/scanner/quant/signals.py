"""Module 3 : signaux quantitatifs et techniques, calculés point-in-time sur les panels de prix.

Conventions : ``t`` = dernière clôture visible (veille de la décision). Les rendements
utilisent les cours ajustés (dividendes, splits) ; les niveaux de prix (seuils, capitalisation)
utilisent les cours bruts. Tous les calculs sont vectorisés sur l'univers.

Référence de chaque signal : ``config/signals.yaml``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scanner.core.reference import region_of
from scanner.data.pit import PitView

LOOKBACK = 800  # ~38 mois : couvre la fenêtre de 36 mois du momentum résiduel
EAR_VALID_DAYS = 90


def _ret(
    panel: pd.DataFrame, lag_end: int, lag_start: int, min_obs: int | None = None
) -> pd.Series:
    """Rendement entre t-lag_start et t-lag_end (en séances ; 0 = dernière clôture)."""
    if len(panel) <= lag_start:
        return pd.Series(np.nan, index=panel.columns)
    end = panel.iloc[-1 - lag_end]
    start = panel.iloc[-1 - lag_start]
    r = end / start - 1
    if min_obs is not None:
        window = panel.iloc[-1 - lag_start : len(panel) - lag_end]
        r = r.where(window.notna().sum() >= min_obs)
    return r


def _group_median(values: pd.Series, groups: pd.Series, min_size: int = 5) -> pd.Series:
    df = pd.DataFrame({"v": values, "g": groups})
    med = df.groupby("g")["v"].transform("median")
    size = df.groupby("g")["v"].transform("count")
    return med.where(size >= min_size)


def _market_returns(daily: pd.DataFrame, regions: pd.Series) -> pd.DataFrame:
    """Rendement de marché équipondéré par région (un proxy par colonne de ``daily``)."""
    out = pd.DataFrame(index=daily.index, columns=daily.columns, dtype=float)
    for reg in regions.dropna().unique():
        cols = regions.index[regions == reg].intersection(daily.columns)
        mkt = daily[cols].mean(axis=1)
        out[cols] = np.repeat(mkt.to_numpy()[:, None], len(cols), axis=1)
    return out


def residual_momentum(adj: pd.DataFrame, regions: pd.Series) -> pd.Series:
    """Momentum résiduel (Blitz, Huij & Martens 2011), version à un facteur (marché régional).

    Régression des rendements mensuels sur 36 mois (jusqu'à t-2), puis somme des résidus
    de t-12 à t-2 rapportée à leur écart-type.
    """
    monthly = adj.resample("ME").last()
    rets = monthly.pct_change(fill_method=None)
    if len(rets) < 20:
        return pd.Series(np.nan, index=adj.columns)
    window = rets.iloc[-38:-2] if len(rets) >= 38 else rets.iloc[:-2]
    mkt = _market_returns(window, regions)
    out = {}
    for col in window.columns:
        y = window[col].to_numpy(dtype=float)
        x = mkt[col].to_numpy(dtype=float) if col in mkt.columns else np.full_like(y, np.nan)
        ok = np.isfinite(y) & np.isfinite(x)
        if ok.sum() < 24 or not np.isfinite(y[-11:]).all():
            out[col] = np.nan
            continue
        X = np.column_stack([np.ones(ok.sum()), x[ok]])
        coef, *_ = np.linalg.lstsq(X, y[ok], rcond=None)
        resid = y - (coef[0] + coef[1] * x)
        form = resid[-11:]
        sd = np.nanstd(form, ddof=1)
        out[col] = float(np.nansum(form) / sd) if sd > 1e-12 else np.nan
    return pd.Series(out)


def earnings_reaction(view: PitView, daily: pd.DataFrame, mkt: pd.DataFrame) -> pd.Series:
    """EAR : rendement anormal cumulé sur [j-1, j+1] autour de la dernière publication visible.

    Jour 0 = jour de la publication si elle a lieu avant 13:30 UTC (avant l'ouverture US),
    sinon la séance suivante. Valable ``EAR_VALID_DAYS`` jours calendaires.
    """
    ev = view.events(["earnings_release"])
    if ev.empty or daily.empty:
        return pd.Series(np.nan, index=daily.columns)
    idx = daily.index
    last_day = idx[-1]
    ev = ev[ev["symbol"].isin(daily.columns)].sort_values("event_time")
    last = ev.groupby("symbol").tail(1)
    out: dict[str, float] = {}
    for _, e in last.iterrows():
        t_utc = pd.Timestamp(e["event_time"])
        day = t_utc.tz_convert("UTC").tz_localize(None).normalize()
        pos = int(idx.searchsorted(day))
        if t_utc.hour * 60 + t_utc.minute >= 13 * 60 + 30 and pos < len(idx) and idx[pos] == day:
            pos += 1
        if pos - 1 < 0 or pos + 1 >= len(idx) or (last_day - day).days > EAR_VALID_DAYS:
            continue
        sym = e["symbol"]
        r = daily[sym].iloc[pos - 1 : pos + 2]
        m = mkt[sym].iloc[pos - 1 : pos + 2]
        if r.notna().all() and m.notna().all():
            out[sym] = float(np.prod(1 + r.to_numpy()) / np.prod(1 + m.to_numpy()) - 1)
    return pd.Series(out, dtype=float).reindex(daily.columns)


def trend_template(adj: pd.DataFrame, rs_pct: pd.Series) -> pd.Series:
    """Nombre de critères du Trend Template de Minervini satisfaits (0 à 8)."""
    if len(adj) < 260:
        return pd.Series(np.nan, index=adj.columns)
    p = adj.iloc[-1]
    sma50 = adj.iloc[-50:].mean()
    sma150 = adj.iloc[-150:].mean()
    sma200 = adj.iloc[-200:].mean()
    sma200_1m = adj.iloc[-221:-21].mean()
    hi = adj.iloc[-252:].max()
    lo = adj.iloc[-252:].min()
    crit = [
        (p > sma150) & (p > sma200),
        sma150 > sma200,
        sma200 > sma200_1m,
        (sma50 > sma150) & (sma50 > sma200),
        p > sma50,
        p >= 1.30 * lo,
        p >= 0.75 * hi,
        rs_pct >= 0.70,
    ]
    score = pd.concat([c.astype(float) for c in crit], axis=1).sum(axis=1)
    return score.where(adj.iloc[-252:].notna().sum() >= 240)


def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    prev = close.shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()]).groupby(level=0).max()


def compute_quant_signals(
    view: PitView, symbols: list[str] | None = None, fx_to_usd: dict[str, float] | None = None
) -> pd.DataFrame:
    """Signaux du Module 3 et statistiques de risque pour ``symbols`` à ``view.as_of``."""
    symbols = symbols if symbols is not None else view.listed_symbols()
    cols = pd.Index(sorted(symbols), name="symbol")
    adj = view.panel("adj_close", LOOKBACK).reindex(columns=cols)
    out = pd.DataFrame(index=cols)
    if adj.empty or len(adj) < 30:
        return out
    close = view.panel("close", LOOKBACK).reindex(columns=cols)
    volume = view.panel("volume", LOOKBACK).reindex(columns=cols)
    sec = view.securities().set_index("symbol").reindex(cols)
    regions = sec["country"].map(lambda c: region_of(c if isinstance(c, str) else None))
    groups = sec["sector"].astype("string").fillna("?") + "|" + regions.astype("string")

    daily = adj.pct_change(fill_method=None)
    mkt = _market_returns(daily, regions)

    out["Q-MOM-12-1"] = _ret(adj, 21, 252, min_obs=200)
    out["Q-MOM-6-1"] = _ret(adj, 21, 126, min_obs=100)
    out["Q-RESMOM"] = residual_momentum(adj, regions)
    out["Q-INDMOM"] = _group_median(out["Q-MOM-6-1"], groups)
    r63 = _ret(adj, 0, 63, min_obs=55)
    out["Q-RS"] = r63 - _group_median(r63, groups)
    out["Q-52WH"] = (adj.iloc[-1] / adj.iloc[-252:].max()).where(
        adj.iloc[-252:].notna().sum() >= 200
    )
    vol252 = daily.iloc[-252:].std() * np.sqrt(252)
    out["Q-LOWVOL"] = vol252.where(daily.iloc[-252:].notna().sum() >= 200)
    v5 = volume.iloc[-5:].mean()
    v60 = volume.iloc[-65:-5].mean()
    out["Q-ABVOL"] = np.log((v5 / v60).where((v5 > 0) & (v60 > 0)))
    out["Q-EAR"] = earnings_reaction(view, daily, mkt)
    rs_pct = out["Q-MOM-12-1"].rank(pct=True)
    out["Q-TREND"] = trend_template(adj, rs_pct)
    high = view.panel("high", LOOKBACK).reindex(columns=cols)
    low = view.panel("low", LOOKBACK).reindex(columns=cols)
    tr = true_range(high, low, close) if not high.empty else pd.DataFrame()
    if not tr.empty and len(tr) >= 40:
        atr_now = tr.iloc[-20:].mean()
        atr_prev = tr.iloc[-40:-20].mean()
        out["Q-VCP"] = -np.log((atr_now / atr_prev).where((atr_now > 0) & (atr_prev > 0)))
        out["risk_atr20"] = atr_now
    else:
        out["Q-VCP"] = np.nan
        out["risk_atr20"] = np.nan
    out["Q-STREV"] = _ret(adj, 0, 21, min_obs=18)

    # --------------------------------------------------------- risque et descriptif
    m = mkt.iloc[-252:]
    d = daily.iloc[-252:]
    cov = (d - d.mean()).mul(m - m.mean()).sum() / (d.notna() & m.notna()).sum().clip(lower=2)
    out["risk_beta"] = cov / m.var()
    out["risk_vol_60d"] = daily.iloc[-60:].std() * np.sqrt(252)
    out["risk_vol_252d"] = vol252
    roll_max = adj.iloc[-252:].cummax()
    out["risk_max_dd_252d"] = (adj.iloc[-252:] / roll_max - 1).min()
    out["tech_sma50"] = adj.iloc[-50:].mean()
    out["tech_sma200"] = adj.iloc[-200:].mean()
    out["last_close"] = close.ffill().iloc[-1]
    out["last_adj_close"] = adj.ffill().iloc[-1]
    dollar_vol = (close * volume).iloc[-60:]
    fx = sec["currency"].map(lambda c: (fx_to_usd or {}).get(str(c), np.nan))
    out["adv60_local"] = dollar_vol.median()
    out["adv60_usd"] = out["adv60_local"] * fx
    out["last_close_usd"] = out["last_close"] * fx
    out["region"] = regions
    out["sector"] = sec["sector"]
    return out
