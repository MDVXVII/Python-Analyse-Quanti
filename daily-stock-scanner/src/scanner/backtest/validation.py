"""Module 9 : protocole de validation et rapport honnête.

Déroulé (ARCHITECTURE.md §7) :

1. à chaque date de décision (fin de mois), univers défini par des règles, signaux et scores
   calculés **exactement** comme dans le rapport quotidien (même moteur, même PitView) ;
2. IC de rang de chaque signal (orienté, normalisé par secteur x région) à plusieurs
   horizons, séparé entre période de conception et période **hors échantillon** ;
3. décision pré-enregistrée par signal : promouvoir / maintenir / rétrograder ;
4. backtest de portefeuille des livres, net de coûts, face à des références (univers
   équipondéré, momentum simple), avec Deflated Sharpe tenant compte du nombre d'essais ;
5. walk-forward : l'IC passé permet-il de mieux pondérer que 1/N, hors échantillon ?

Chaque exécution est ajoutée au journal des essais (``trials.jsonl``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scanner.backtest.costs import CostModel
from scanner.backtest.engine import PortfolioSpec, equal_weight_benchmark, run_backtest
from scanner.backtest.ic import (
    forward_returns,
    ic_summary,
    quantile_spread,
    rank_ic,
    spacing_in_days,
)
from scanner.backtest.metrics import newey_west_tstat, summarize
from scanner.backtest.walkforward import expanding_splits, oos_scores, walk_forward_compare
from scanner.core.config import BOOK_IDS, AppConfig, SignalDef, SignalStatus
from scanner.core.logging import get_logger
from scanner.core.timeutil import rebalance_dates, utc_midnight
from scanner.data.pit import PitView
from scanner.data.store import MarketData
from scanner.pipeline.engine import compute_signals, score_all_books
from scanner.scoring.composite import normalize_signals
from scanner.universe import rule_based_universe

log = get_logger(__name__)

HORIZONS = (1, 5, 21, 63, 126, 252)


@dataclass(frozen=True)
class ValidationSettings:
    region: str
    start: date
    end: date
    oos_start: date
    data_label: str
    survivorship_free: bool
    rebalance: str = "monthly"
    top_fraction: float = 0.2
    lag_days: int = 1
    min_oos_dates: int = 24
    horizons: tuple[int, ...] = HORIZONS


@dataclass
class Panels:
    dates: list[pd.Timestamp]
    z: dict[str, pd.DataFrame]  # signal -> date x symbole (z orienté)
    composite: dict[str, pd.DataFrame]  # livre -> date x symbole
    universe: dict[pd.Timestamp, list[str]]
    meta: pd.DataFrame  # pays, région, volume (dernière vue connue)


@dataclass
class SignalVerdict:
    signal: str
    name: str
    status: str
    horizon: int
    is_ic: float
    oos_ic: float
    oos_t: float
    oos_hit: float
    oos_n: int
    oos_spread_ann: float
    decay: dict[int, float]
    decision: str
    reason: str


@dataclass
class ValidationResults:
    settings: ValidationSettings
    verdicts: list[SignalVerdict]
    books: dict[str, dict[str, dict[str, float]]]
    walk_forward: dict[str, float]
    n_trials: int
    config_fingerprint: str
    generated_at: str
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------ collecte


def primary_horizon(sig: SignalDef) -> int:
    if "S" in sig.books:
        return 21
    if "M" in sig.books:
        return 63
    return 126


def collect_panels(data: MarketData, config: AppConfig, vs: ValidationSettings) -> Panels:
    adj = data.panel("adj_close")
    idx = adj.index[(adj.index >= pd.Timestamp(vs.start)) & (adj.index <= pd.Timestamp(vs.end))]
    dates = list(rebalance_dates(pd.DatetimeIndex(idx), vs.rebalance))
    region_cfg = config.settings.backtest_universe[vs.region]
    defs = [
        s
        for s in config.signals.signals
        if s.books and s.status not in (SignalStatus.PENALTY, SignalStatus.RETIRED)
    ]
    z_rows: dict[str, dict[pd.Timestamp, pd.Series]] = {s.id: {} for s in defs}
    comp_rows: dict[str, dict[pd.Timestamp, pd.Series]] = {b: {} for b in BOOK_IDS}
    universe: dict[pd.Timestamp, list[str]] = {}
    meta = pd.DataFrame()
    for k, d in enumerate(dates):
        view = PitView(data, utc_midnight(d.date() + timedelta(days=1)))
        fx = {"USD": 1.0, **config.settings.market.fx_fallback_to_usd}
        syms = rule_based_universe(
            view, vs.region, region_cfg.top_n, region_cfg.min_price_usd, region_cfg.min_adv_usd, fx
        )
        if len(syms) < 20:
            continue
        sig = compute_signals(view, syms, config)
        z = normalize_signals(
            sig.values,
            defs,
            sig.meta,
            config.settings.scoring.min_group_size,
            config.settings.scoring.z_clip,
        )
        for s in defs:
            z_rows[s.id][d] = z[s.id]
        for b, bs in score_all_books(sig, config).items():
            comp_rows[b][d] = bs.composite
        universe[d] = syms
        meta = (
            sig.values[["region", "adv60_usd"]]
            .join(view.securities().set_index("symbol")[["country"]], how="left")
            .combine_first(meta)
        )
        if k % 12 == 0:
            log.info(
                "validation : collecte", extra={"ctx": {"date": str(d.date()), "n": len(syms)}}
            )
    to_frame = lambda rows: pd.DataFrame(rows).T.sort_index() if rows else pd.DataFrame()  # noqa: E731
    return Panels(
        dates=sorted(universe),
        z={k: to_frame(v) for k, v in z_rows.items()},
        composite={b: to_frame(v) for b, v in comp_rows.items()},
        universe=universe,
        meta=meta,
    )


# ----------------------------------------------------------------------------- décisions


def decide(sig: SignalDef, oos: dict[str, float], spread: float, min_n: int) -> tuple[str, str]:
    """Règles pré-enregistrées (ARCHITECTURE.md §7.4)."""
    n = int(oos.get("n_dates", 0))
    ic, t = oos.get("ic_mean", np.nan), oos.get("ic_t_nw", np.nan)
    if n < min_n or not np.isfinite(ic):
        return "DONNÉES INSUFFISANTES", f"{n} dates hors échantillon (< {min_n})"
    threshold = 3.0 if sig.status == SignalStatus.OBSERVATION else 2.0
    if ic > 0 and np.isfinite(t) and t >= threshold and (not np.isfinite(spread) or spread > 0):
        target = "candidat" if sig.status == SignalStatus.OBSERVATION else "validé"
        return f"PROMOUVOIR ({target})", f"IC {ic:+.3f}, t = {t:.2f} ≥ {threshold:g}"
    if ic < 0 and np.isfinite(t) and t <= -1:
        return "RÉTROGRADER (observation)", f"IC de mauvais signe ({ic:+.3f}, t = {t:.2f})"
    return "MAINTENIR", f"preuve insuffisante (IC {ic:+.3f}, t = {t:.2f} < {threshold:g})"


def _period(df: Any, start: pd.Timestamp | None, end: pd.Timestamp | None) -> Any:
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):  # série vide (aucune date exploitable)
        return df.iloc[0:0]
    mask = np.ones(len(idx), dtype=bool)
    if start is not None:
        mask &= idx >= start
    if end is not None:
        mask &= idx < end
    return df[mask]


def _trials(path: Path, key: dict[str, Any]) -> int:
    if not path.exists():
        return 1
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("data_label") == key["data_label"] and rec.get("region") == key["region"]:
            n += 1
    return n + 1


# ------------------------------------------------------------------------------ évaluation


def run_validation(
    data: MarketData, config: AppConfig, vs: ValidationSettings, trials_log: Path | None = None
) -> ValidationResults:
    panels = collect_panels(data, config, vs)
    adj = data.panel("adj_close")
    if not panels.dates:
        raise ValueError("aucune date de décision exploitable (univers trop petit ?)")
    oos = pd.Timestamp(vs.oos_start)
    spacing = spacing_in_days(panels.dates, pd.DatetimeIndex(adj.index))
    delist = config.costs.delisting_return
    needed = sorted(set(vs.horizons) | {21, 63, 126})  # horizons principaux toujours calculés
    fwd = {h: forward_returns(adj, panels.dates, h, vs.lag_days, delist) for h in needed}

    verdicts = []
    for sig in [s for s in config.signals.signals if s.id in panels.z]:
        z = panels.z[sig.id]
        if z.empty:
            continue
        h = primary_horizon(sig)
        decay = {}
        for hh in vs.horizons:
            ic_oos = _period(rank_ic(z, fwd[hh]), oos, None)
            decay[hh] = float(ic_oos.mean()) if len(ic_oos) else float("nan")
        ic_all = rank_ic(z, fwd[h])
        s_is = ic_summary(_period(ic_all, None, oos), h, spacing)
        s_oos = ic_summary(_period(ic_all, oos, None), h, spacing)
        spread = _period(quantile_spread(z, fwd[h]), oos, None)
        spread_ann = float(spread.mean() * 252 / h) if len(spread) else float("nan")
        decision, reason = decide(sig, s_oos, spread_ann, vs.min_oos_dates)
        verdicts.append(
            SignalVerdict(
                signal=sig.id,
                name=sig.name,
                status=sig.status.value,
                horizon=h,
                is_ic=s_is["ic_mean"],
                oos_ic=s_oos["ic_mean"],
                oos_t=s_oos["ic_t_nw"],
                oos_hit=s_oos["ic_hit"],
                oos_n=int(s_oos["n_dates"]),
                oos_spread_ann=spread_ann,
                decay=decay,
                decision=decision,
                reason=reason,
            )
        )

    key = {"data_label": vs.data_label, "region": vs.region}
    n_trials = _trials(trials_log, key) if trials_log else 1

    # ------------------------------------------------------------------- portefeuilles
    meta = panels.meta
    costs = CostModel(config.costs, meta["region"], meta["country"], meta["adv60_usd"])
    spec = PortfolioSpec(top_fraction=vs.top_fraction, long_short=True, lag_days=vs.lag_days)
    books: dict[str, dict[str, dict[str, float]]] = {}
    bench = equal_weight_benchmark(panels.universe, adj, vs.lag_days, delist)
    mom = panels.z.get("Q-MOM-12-1", pd.DataFrame())
    mom_res = (
        run_backtest({d: mom.loc[d] for d in mom.index}, adj, spec, costs, delist)
        if not mom.empty
        else None
    )
    for label, series in {
        "Univers équipondéré (sans coûts)": bench,
        "Momentum 12-1 seul (long, net)": mom_res.long.returns if mom_res else None,
    }.items():
        if series is not None:
            books[label] = {
                "IS": summarize(_period(series, None, oos), n_trials=1),
                "OOS": summarize(_period(series, oos, None), n_trials=1),
            }
    for b, comp in panels.composite.items():
        if comp.empty:
            continue
        res = run_backtest({d: comp.loc[d] for d in comp.index}, adj, spec, costs, delist)
        turn = res.annual_turnover()
        books[f"Livre {b} — long (net)"] = {
            "IS": summarize(_period(res.long.returns, None, oos), n_trials=n_trials, turnover=turn),
            "OOS": summarize(
                _period(res.long.returns, oos, None), n_trials=n_trials, turnover=turn
            ),
        }
        if res.long_short is not None:
            books[f"Livre {b} — long/short papier (net)"] = {
                "IS": summarize(_period(res.long_short, None, oos), n_trials=n_trials),
                "OOS": summarize(_period(res.long_short, oos, None), n_trials=n_trials),
            }

    # ------------------------------------------------------------------- walk-forward (livre M)
    wf: dict[str, float] = {}
    m_signals = [
        s.id for s in config.signals.for_book("M", config.settings.scoring.statuses_in_score)
    ]
    z_m = {s: panels.z[s] for s in m_signals if s in panels.z and not panels.z[s].empty}
    if z_m:
        h = 63
        ic_m = {s: rank_ic(z, fwd[h]) for s, z in z_m.items()}
        dates_idx = pd.DatetimeIndex(panels.dates)
        splits = expanding_splits(dates_idx, min_train_years=3.0)
        if splits:
            wt = walk_forward_compare(z_m, ic_m, splits)
            wf_scores = oos_scores(z_m, wt)
            eq_w = pd.Series(1.0 / len(z_m), index=list(z_m))
            eq_scores = oos_scores(z_m, wt.assign(weight=wt["signal"].map(eq_w)))
            ic_wf = rank_ic(wf_scores, fwd[h])
            ic_eq = rank_ic(eq_scores, fwd[h])
            s_wf, s_eq = ic_summary(ic_wf, h, spacing), ic_summary(ic_eq, h, spacing)
            diff = (ic_wf - ic_eq).dropna()
            wf = {
                "ic_weighted_mean": s_wf["ic_mean"],
                "ic_weighted_t": s_wf["ic_t_nw"],
                "equal_mean": s_eq["ic_mean"],
                "equal_t": s_eq["ic_t_nw"],
                "diff_mean": float(diff.mean()) if len(diff) else float("nan"),
                "diff_t": newey_west_tstat(diff, max(0, int(np.ceil(h / spacing)) - 1)),
                "n_splits": float(len(splits)),
            }

    results = ValidationResults(
        settings=vs,
        verdicts=verdicts,
        books=books,
        walk_forward=wf,
        n_trials=n_trials,
        config_fingerprint=config.fingerprint,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    if trials_log is not None:
        trials_log.parent.mkdir(parents=True, exist_ok=True)
        with trials_log.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        **key,
                        "generated_at": results.generated_at,
                        "config": config.fingerprint,
                        "start": str(vs.start),
                        "end": str(vs.end),
                        "oos_start": str(vs.oos_start),
                    }
                )
                + "\n"
            )
    return results


def results_to_json(res: ValidationResults) -> str:
    payload = asdict(res)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
