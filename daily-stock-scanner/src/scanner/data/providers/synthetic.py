"""Marché synthétique déterministe : tests, démonstration hors ligne, contrôle du backtest.

**Ce ne sont pas des données de marché.** Le générateur sert à trois choses :

1. vérifier que la chaîne complète fonctionne sans réseau (``scanner demo``) ;
2. vérifier l'absence de biais d'anticipation (on connaît la vérité terrain) ;
3. vérifier que le moteur de validation **détecte** un signal planté et **ne promeut pas**
   un signal sans pouvoir prédictif (contrôle des faux positifs).

Structure : rendement = bêta x marché + secteur + prime de qualité x q_i(t) + dérive
persistante a_i(t) (source de momentum) + bruit idiosyncratique. Les états financiers
trimestriels reflètent la qualité q_i(t), sont publiés avec retard (10-Q à 25-45 jours,
10-K à 50-75 jours) et contiennent quelques retraitements publiés ultérieurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from scanner.core.reference import SECTORS
from scanner.data.schemas import EVENTS, FACTS, PRICES, SECURITIES, conform
from scanner.data.store import MarketData


@dataclass(frozen=True)
class SyntheticSpec:
    n_securities: int = 240
    start: date = date(2014, 1, 1)
    end: date = date(2026, 9, 22)
    seed: int = 7
    quality_premium: float = 0.06      # rendement annuel par écart-type de qualité
    drift_sd_daily: float = 0.0004     # écart-type stationnaire de la dérive persistante
    drift_phi: float = 0.995           # persistance quotidienne de la dérive
    delisting_rate: float = 0.08
    late_listing_rate: float = 0.08
    restatement_rate: float = 0.05
    eu_share: float = 0.35


@dataclass
class SyntheticMarket:
    data: MarketData
    quality: pd.DataFrame     # vérité terrain : q_i par trimestre (index = fin de trimestre)
    spec: SyntheticSpec


def generate(spec: SyntheticSpec = SyntheticSpec()) -> SyntheticMarket:
    rng = np.random.default_rng(spec.seed)
    dates = pd.bdate_range(spec.start, spec.end)
    n, t = spec.n_securities, len(dates)

    # --------------------------------------------------------------- référentiel
    is_eu = rng.random(n) < spec.eu_share
    eu_exch = rng.choice(["PA", "XETRA"], size=n)
    symbols = [f"SYN{i:03d}.{eu_exch[i] if is_eu[i] else 'US'}" for i in range(n)]
    country = [("FR" if eu_exch[i] == "PA" else "DE") if is_eu[i] else "US" for i in range(n)]
    currency = ["EUR" if is_eu[i] else "USD" for i in range(n)]
    sector_idx = rng.integers(0, len(SECTORS), size=n)
    sectors = [SECTORS[k] for k in sector_idx]

    start_idx = np.zeros(n, dtype=int)
    late = rng.random(n) < spec.late_listing_rate
    start_idx[late] = rng.integers(t // 10, t // 2, size=late.sum())
    end_idx = np.full(n, t, dtype=int)
    delist = rng.random(n) < spec.delisting_rate
    end_idx[delist] = rng.integers(t // 3, int(t * 0.9), size=delist.sum())

    # ------------------------------------------------------------ qualité latente (par année)
    years = sorted({d.year for d in dates})
    q = np.zeros((len(years), n))
    q[0] = rng.standard_normal(n)
    for y in range(1, len(years)):
        q[y] = 0.9 * q[y - 1] + np.sqrt(1 - 0.81) * rng.standard_normal(n)
    year_pos = {y: k for k, y in enumerate(years)}
    q_daily = q[[year_pos[d.year] for d in dates]]  # (t, n)

    # ---------------------------------------------------------------- rendements
    market = rng.normal(0.00035, 0.011, size=t)
    sector_f = rng.normal(0.0, 0.006, size=(t, len(SECTORS)))
    beta = rng.uniform(0.6, 1.4, size=n)
    sigma = rng.uniform(0.012, 0.028, size=n)
    innov_sd = spec.drift_sd_daily * np.sqrt(1 - spec.drift_phi**2)
    drift = np.zeros((t, n))
    for k in range(1, t):
        drift[k] = spec.drift_phi * drift[k - 1] + innov_sd * rng.standard_normal(n)
    rets = (market[:, None] * beta[None, :] + sector_f[:, sector_idx]
            + spec.quality_premium / 252 * q_daily + drift
            + sigma[None, :] * rng.standard_normal((t, n)))

    p0 = rng.uniform(15, 150, size=n)
    close = p0[None, :] * np.exp(np.cumsum(rets, axis=0))
    live = (np.arange(t)[:, None] >= start_idx[None, :]) & (np.arange(t)[:, None] < end_idx[None, :])
    close = np.where(live, close, np.nan)
    open_ = close * (1 + rng.normal(0, 0.003, size=(t, n)))
    high = np.maximum(close, open_) * (1 + np.abs(rng.normal(0, 0.006, size=(t, n))))
    low = np.minimum(close, open_) * (1 - np.abs(rng.normal(0, 0.006, size=(t, n))))
    mcap0 = np.exp(rng.normal(np.log(5e9), 1.1, size=n))
    shares0 = mcap0 / p0
    adv_dollars = mcap0 * rng.uniform(0.002, 0.01, size=n)
    volume = (adv_dollars / p0)[None, :] * np.exp(rng.normal(0, 0.35, size=(t, n)))
    volume = np.where(live, volume, np.nan)

    prices = pd.DataFrame({
        "symbol": np.repeat(np.array(symbols)[None, :], t, axis=0).ravel(),
        "date": np.repeat(dates.to_numpy()[:, None], n, axis=1).ravel(),
        "open": open_.ravel(), "high": high.ravel(), "low": low.ravel(),
        "close": close.ravel(), "adj_close": close.ravel(), "volume": volume.ravel(),
        "source": "synthetic",
    }).dropna(subset=["close"])
    prices = conform(prices, PRICES)

    # --------------------------------------------------------- états financiers et événements
    quarter_ends = pd.date_range(spec.start, spec.end, freq="QE")
    fact_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    q_by_quarter = pd.DataFrame(index=quarter_ends, columns=symbols, dtype=float)
    for i, sym in enumerate(symbols):
        assets = mcap0[i] * rng.uniform(0.5, 1.2)
        shares = shares0[i]
        fy_acc: dict[str, float] = {}
        fy_count = 0
        for qe in quarter_ends:
            pos = dates.searchsorted(qe)
            if pos < start_idx[i] or pos >= end_idx[i]:
                continue
            qi = q[year_pos[qe.year], i]
            q_by_quarter.loc[qe, sym] = qi
            assets *= 1 + rng.normal(0.012 - 0.004 * qi, 0.01)
            shares *= 1 + (-0.0025 * qi) + rng.normal(0, 0.002)
            gp = assets * max(0.01, 0.08 + 0.025 * qi + rng.normal(0, 0.006))
            gm = float(np.clip(0.40 + 0.06 * qi + rng.normal(0, 0.01), 0.1, 0.9))
            revenue = gp / gm
            dep = assets * 0.010
            debt = assets * float(np.clip(0.30 - 0.08 * qi + rng.normal(0, 0.02), 0.02, 0.7))
            interest = debt * 0.012
            sga = gp * 0.45
            ebit = gp - sga - dep
            pretax = ebit - interest
            tax = max(0.0, 0.22 * pretax)
            ni = pretax - tax
            accrual = (0.004 - 0.004 * qi) * assets + rng.normal(0, 0.002) * assets
            cfo = ni + dep - accrual
            capex = assets * 0.012
            flows = {"revenue": revenue, "cogs": revenue - gp, "gross_profit": gp, "sga": sga,
                     "ebit": ebit, "pretax_income": pretax, "income_tax": tax, "net_income": ni,
                     "interest_expense": interest, "depreciation": dep, "cfo": cfo,
                     "capex": capex}
            cl = assets * 0.20
            stocks = {"total_assets": assets, "current_assets": assets * 0.35,
                      "current_liabilities": cl, "total_liabilities": debt + cl,
                      "total_equity": assets - debt - cl, "cash": assets * 0.08,
                      "receivables": assets * (0.12 - 0.01 * qi), "inventory": assets * 0.06,
                      "ppe_net": assets * 0.30, "long_term_debt": debt * 0.8,
                      "short_term_debt": debt * 0.2, "retained_earnings": assets * 0.25,
                      "shares_outstanding": shares}
            is_fy = qe.month == 12
            lag = int(rng.integers(50, 76) if is_fy else rng.integers(25, 46))
            filed = (qe + pd.Timedelta(days=lag)).date()
            avail = datetime.combine(filed + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
            form = "10-K" if is_fy else "10-Q"
            q_start = (qe - pd.DateOffset(months=3) + pd.Timedelta(days=1)).normalize()
            accn = f"{sym}-{qe.date().isoformat()}"
            fy_count += 1
            for name, v in flows.items():
                fy_acc[name] = fy_acc.get(name, 0.0) + v
                if not is_fy:  # un 10-K ne publie que l'exercice (le T4 est à reconstituer)
                    fact_rows.append(
                        _fact(sym, name, v, q_start, qe, "Q", form, avail, accn, currency[i])
                    )
            eps = ni / shares
            if not is_fy:
                fact_rows.append(_fact(sym, "eps_diluted", eps, q_start, qe, "Q", form, avail, accn,
                                       f"{currency[i]}/shares"))
            for name, v in stocks.items():
                unit = "shares" if name == "shares_outstanding" else currency[i]
                fact_rows.append(_fact(sym, name, v, None, qe, None, form, avail, accn, unit))
            if is_fy and fy_count == 4:
                fy_start = pd.Timestamp(qe.year, 1, 1)
                for name, v in fy_acc.items():
                    fact_rows.append(
                        _fact(sym, name, v, fy_start, qe, "FY", form, avail, accn, currency[i])
                    )
                fy_eps = fy_acc["net_income"] / shares
                fact_rows.append(_fact(sym, "eps_diluted", fy_eps, fy_start, qe, "FY", form, avail,
                                       accn, f"{currency[i]}/shares"))
            if is_fy:
                fy_acc, fy_count = {}, 0
            # Retraitement publié au trimestre suivant (nouvelle version, disponible plus tard).
            if not is_fy and rng.random() < spec.restatement_rate:
                later = avail + timedelta(days=91)
                fact_rows.append(_fact(sym, "revenue", revenue * 1.05, q_start, qe, "Q", "10-Q/A",
                                       later, accn + "-R", currency[i]))
            release = datetime.combine(filed - timedelta(days=3), datetime.min.time(),
                                       tzinfo=UTC) + timedelta(hours=21)
            event_rows.append({"symbol": sym, "event_type": "earnings_release",
                               "event_time": release, "available_at": release,
                               "source": "synthetic", "detail": form})

    facts = conform(pd.DataFrame(fact_rows), FACTS)
    events = conform(pd.DataFrame(event_rows), EVENTS)
    securities = conform(pd.DataFrame({
        "symbol": symbols,
        "name": [f"Société synthétique {i:03d}" for i in range(n)],
        "country": country, "currency": currency, "sector": sectors,
        "security_type": "EQUITY",
        "listed_from": [dates[start_idx[i]] for i in range(n)],
        "delisted_on": [dates[end_idx[i]] if end_idx[i] < t else pd.NaT for i in range(n)],
        "shares_outstanding": shares0, "market_cap": mcap0, "source": "synthetic",
    }), SECURITIES)
    return SyntheticMarket(MarketData(prices, facts, events, securities), q_by_quarter, spec)


def _fact(symbol: str, concept: str, value: float, start: pd.Timestamp | None, end: pd.Timestamp,
          fp: str | None, form: str, avail: datetime, accn: str, unit: str) -> dict[str, object]:
    return {"symbol": symbol, "concept": concept, "value": float(value), "period_start": start,
            "period_end": end, "fiscal_period": fp, "form": form, "unit": unit,
            "available_at": avail, "lag_estimated": False, "source": "synthetic",
            "accession": accn, "tag": f"synthetic:{concept}", "tag_rank": 0}
