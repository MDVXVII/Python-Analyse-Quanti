"""Module 8 : score composite par livre (S, M, L), pénalités et décomposition.

Principe (ARCHITECTURE.md §6) :

1. chaque signal actif est normalisé (rang gaussien dans son groupe secteur x région) et
   orienté selon son signe pré-enregistré ;
2. le score d'une famille = somme des z disponibles / nombre de signaux de la famille
   (une famille à moitié renseignée pèse moitié moins : pas d'imputation silencieuse) ;
3. composite = moyenne pondérée des familles (poids de ``weights.yaml``) ;
4. pénalités additives (liquidité, Beneish, Altman, événement binaire imminent) ;
5. la contribution de chaque signal est conservée : la somme des contributions égale le
   composite avant pénalités, ce qui rend chaque classement explicable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from scanner.core.config import AppConfig, BookId, SignalDef, SignalStatus
from scanner.scoring.normalize import rank_gauss


@dataclass
class BookScores:
    book: BookId
    composite: pd.Series  # score final (après pénalités)
    raw_composite: pd.Series  # avant pénalités
    families: pd.DataFrame  # score effectif par famille
    coverage: pd.DataFrame  # part de signaux disponibles par famille
    contributions: pd.DataFrame  # contribution de chaque signal actif au composite
    observation: pd.DataFrame  # z des signaux en observation (non pondérés)
    penalties: pd.DataFrame  # montant de chaque pénalité
    flags: pd.DataFrame  # alertes textuelles
    signals_used: list[str] = field(default_factory=list)


def _group_levels(frame: pd.DataFrame) -> list[pd.Series]:
    sector = frame["sector"].astype("string").fillna("?")
    region = frame["region"].astype("string").fillna("?")
    return [sector + "|" + region, sector, region]


def normalize_signals(
    signals: pd.DataFrame,
    defs: list[SignalDef],
    meta: pd.DataFrame,
    min_group_size: int,
    clip: float,
) -> pd.DataFrame:
    """z orienté (valeur haute = favorable à un long) pour chaque signal de ``defs``."""
    levels = _group_levels(meta.reindex(signals.index))
    out = {}
    for d in defs:
        if d.id not in signals.columns:
            out[d.id] = pd.Series(np.nan, index=signals.index)
            continue
        raw = pd.to_numeric(signals[d.id], errors="coerce") * d.sign
        out[d.id] = rank_gauss(raw, levels, min_group_size, clip)
    return pd.DataFrame(out, index=signals.index)


def score_book(
    book: BookId,
    signals: pd.DataFrame,
    meta: pd.DataFrame,
    config: AppConfig,
    upcoming_events_days: pd.Series | None = None,
) -> BookScores:
    """Score d'un livre.

    ``signals`` : symbole x identifiants de signaux (valeurs brutes) + champs de contrôle
    (``F-BENM``, ``altman_zone``…). ``meta`` : ``sector``, ``region``, ``passes_liquidity``,
    ``adv60_usd``. ``upcoming_events_days`` : séances jusqu'à la prochaine publication connue.
    """
    s_cfg = config.settings.scoring
    p_cfg = config.settings.penalties
    weights = config.weights.books[book]
    active = [d for d in config.signals.for_book(book, s_cfg.statuses_in_score)]
    observed = [d for d in config.signals.for_book(book) if d.status == SignalStatus.OBSERVATION]
    idx = signals.index
    z = normalize_signals(signals, active, meta, s_cfg.min_group_size, s_cfg.z_clip)
    z_obs = normalize_signals(signals, observed, meta, s_cfg.min_group_size, s_cfg.z_clip)

    total_w = sum(weights.values())
    fam_scores, fam_cov, contribs = {}, {}, {}
    for family, w in weights.items():
        members = [d.id for d in active if d.books[book] == family]
        if not members:
            continue
        zf = z[members]
        n_def = len(members)
        cov = zf.notna().sum(axis=1) / n_def
        eff = zf.sum(axis=1, min_count=1).fillna(0.0) / n_def
        eff = eff.where(cov >= s_cfg.min_module_coverage, 0.0)
        fam_scores[family] = eff
        fam_cov[family] = cov
        for m in members:
            contrib = (w / total_w) * zf[m].fillna(0.0) / n_def
            contribs[m] = contrib.where(cov >= s_cfg.min_module_coverage, 0.0)
    families = pd.DataFrame(fam_scores, index=idx)
    coverage = pd.DataFrame(fam_cov, index=idx)
    contributions = pd.DataFrame(contribs, index=idx)
    raw = sum((weights[f] / total_w) * families[f] for f in families.columns)
    raw = pd.Series(raw, index=idx, dtype=float)
    # un titre sans aucun signal disponible n'a pas de score (plutôt qu'un 0 trompeur)
    raw = raw.where(z.notna().any(axis=1))

    # ------------------------------------------------------------------ pénalités
    pen = pd.DataFrame(0.0, index=idx, columns=["liquidity", "beneish", "altman", "binary_event"])
    flags: dict[str, list[str]] = {s: [] for s in idx}
    liq_ok = meta["passes_liquidity"].reindex(idx).fillna(False).astype(bool)
    adv = pd.to_numeric(
        meta.get("adv60_usd", pd.Series(np.nan, index=idx)), errors="coerce"
    ).reindex(idx)
    min_adv = config.settings.universe.liquidity.min_adv_usd
    soft = liq_ok & (adv < min_adv * p_cfg.liquidity_soft_multiple)
    pen.loc[soft, "liquidity"] = p_cfg.liquidity_soft
    if "F-BENM" in signals.columns:
        ben = pd.to_numeric(signals["F-BENM"], errors="coerce") > p_cfg.beneish_threshold
        pen.loc[ben, "beneish"] = p_cfg.beneish
        for s in idx[ben]:
            flags[s].append(
                f"Beneish M = {signals.at[s, 'F-BENM']:.2f} > {p_cfg.beneish_threshold}"
                " (risque comptable à examiner)"
            )
    if "altman_zone" in signals.columns:
        distress = signals["altman_zone"].astype("string") == "distress"
        distress = distress.fillna(False)
        pen.loc[distress, "altman"] = p_cfg.altman_distress[book]
        for s in idx[distress]:
            flags[s].append("Altman en zone de détresse")
    if upcoming_events_days is not None:
        days = upcoming_events_days.reindex(idx)
        binary = (days >= 0) & (days <= p_cfg.binary_event_days)
        binary = binary.fillna(False)
        pen.loc[binary, "binary_event"] = p_cfg.binary_event[book]
        for s in idx[binary]:
            flags[s].append(f"publication de résultats dans {int(days[s])} séance(s)")
    final = (raw - pen.sum(axis=1)).where(liq_ok)
    for s in idx[~liq_ok]:
        note = str(meta.at[s, "liquidity_note"]) if "liquidity_note" in meta.columns else ""
        flags[s].append(f"exclu (liquidité) {note}".strip())
    flag_df = pd.DataFrame({"flags": [" | ".join(flags[s]) for s in idx]}, index=idx)
    return BookScores(
        book=book,
        composite=final,
        raw_composite=raw,
        families=families,
        coverage=coverage,
        contributions=contributions,
        observation=z_obs,
        penalties=pen,
        flags=flag_df,
        signals_used=[d.id for d in active],
    )


def select_ideas(scores: BookScores, top_long: int, top_short: int) -> pd.DataFrame:
    """Top N longs et shorts (papier) d'un livre, avec rang et score."""
    ranked = scores.composite.dropna().sort_values(ascending=False)
    longs = ranked.head(top_long)
    shorts = ranked.tail(top_short).sort_values() if top_short else ranked.iloc[0:0]
    rows = [
        {"book": scores.book, "side": "long", "rank": i + 1, "symbol": s, "score": v}
        for i, (s, v) in enumerate(longs.items())
    ]
    rows += [
        {"book": scores.book, "side": "short", "rank": i + 1, "symbol": s, "score": v}
        for i, (s, v) in enumerate(shorts.items())
    ]
    return pd.DataFrame(rows, columns=["book", "side", "rank", "symbol", "score"])


def top_contributors(scores: BookScores, symbol: str, k: int = 3) -> list[tuple[str, float]]:
    """Les ``k`` signaux qui contribuent le plus (en valeur absolue) au score d'un titre."""
    row = pd.Series(scores.contributions.loc[symbol]).dropna()
    order = row.abs().sort_values(ascending=False).index[:k]
    return [(sig, float(row[sig])) for sig in order]


def changes_vs_previous(
    current: pd.DataFrame,
    previous: pd.DataFrame | None,
    fam_now: Mapping[Any, pd.DataFrame],
    fam_prev: Mapping[Any, pd.DataFrame] | None,
) -> pd.DataFrame:
    """Entrées et sorties du top long, attribuées à la famille dont le score a le plus bougé."""
    cols = ["book", "change", "symbol", "cause"]
    if previous is None or previous.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for book in sorted(current["book"].unique()):
        now = set(current[(current["book"] == book) & (current["side"] == "long")]["symbol"])
        before = set(previous[(previous["book"] == book) & (previous["side"] == "long")]["symbol"])
        f_now = fam_now.get(book)
        f_prev = (fam_prev or {}).get(book)
        changes = [(s, "entrée") for s in sorted(now - before)] + [
            (s, "sortie") for s in sorted(before - now)
        ]
        for sym, change in changes:
            cause = "données de la veille indisponibles pour attribuer"
            if (
                f_now is not None
                and f_prev is not None
                and sym in f_now.index
                and sym in f_prev.index
            ):
                delta = (f_now.loc[sym] - f_prev.reindex(columns=f_now.columns).loc[sym]).dropna()
                if not delta.empty and delta.abs().max() > 0:
                    f = delta.abs().idxmax()
                    cause = f"famille « {f} » : {delta[f]:+.2f}"
                else:
                    cause = "mouvement des autres titres (score propre inchangé)"
            rows.append({"book": book, "change": change, "symbol": sym, "cause": cause})
    return pd.DataFrame(rows, columns=cols)
