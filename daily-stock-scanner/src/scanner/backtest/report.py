"""Rendu Markdown du rapport de validation (en français, sans enjoliver les résultats)."""

from __future__ import annotations

import math

from scanner.backtest.validation import ValidationResults


def _f(x: float, pct: bool = False, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n.d."
    return f"{x * 100:.{digits - 1}f} %" if pct else f"{x:.{digits}f}"


def render_validation_markdown(res: ValidationResults) -> str:
    vs = res.settings
    lines: list[str] = []
    add = lines.append
    add(f"# Rapport de validation — {vs.region}, {vs.start} → {vs.end}")
    add("")
    add(
        f"*Généré le {res.generated_at} UTC · configuration `{res.config_fingerprint}` · "
        f"essai n° {res.n_trials} sur ces données.*"
    )
    add("")
    if "synth" in vs.data_label.lower():
        add(
            "> **DONNÉES SYNTHÉTIQUES.** Ce rapport vérifie la mécanique du protocole (détection "
            "d'un signal planté, rejet d'un signal inopérant, absence de biais d'anticipation). "
            "Ses chiffres n'ont **aucune valeur économique** et ne disent rien des marchés réels."
        )
        add("")
    add("## Protocole")
    add("")
    add(
        f"- Données : {vs.data_label}. Base de prix incluant les délistés : "
        f"**{'oui' if vs.survivorship_free else 'non — résultats biaisés à la hausse'}**."
    )
    add(
        f"- Période de conception : {vs.start} → {vs.oos_start} ; **hors échantillon** : "
        f"{vs.oos_start} → {vs.end} (consulté une fois par décision)."
    )
    add(
        f"- Décisions en fin de mois, exécution à la clôture de la séance suivante "
        f"(décalage {vs.lag_days} j), univers défini par des règles à chaque date."
    )
    add(
        "- Signaux normalisés par secteur x région et orientés selon leur signe pré-enregistré ; "
        "IC de rang, t de Newey-West (chevauchement des horizons)."
    )
    add(
        "- Portefeuilles : quintile supérieur équipondéré (long) et quintile inférieur (short "
        "papier), nets de courtage, demi-spread et taxes (TTF 0,4 %…)."
    )
    add(
        "- Règles de décision : promotion si IC > 0 et t ≥ 2 (≥ 3 pour un signal en "
        "observation) et spread net > 0 ; rétrogradation si IC < 0 et t ≤ -1 ; sinon maintien."
    )
    add("")
    add("## Signaux")
    add("")
    add(
        "| Signal | Statut actuel | Horizon | IC conception | IC hors éch. | t (NW) | "
        "% IC > 0 | Dates | Spread Q5-Q1 ann. | Décision |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|")
    for v in sorted(
        res.verdicts, key=lambda v: (v.decision, -(v.oos_t if math.isfinite(v.oos_t) else -99))
    ):
        add(
            f"| {v.signal} — {v.name} | {v.status} | {v.horizon} j | {_f(v.is_ic, digits=3)} | "
            f"{_f(v.oos_ic, digits=3)} | {_f(v.oos_t)} | {_f(v.oos_hit, pct=True)} | {v.oos_n} | "
            f"{_f(v.oos_spread_ann, pct=True)} | **{v.decision}** — {v.reason} |"
        )
    add("")
    add("### Décroissance de l'IC hors échantillon selon l'horizon")
    add("")
    hs = sorted({h for v in res.verdicts for h in v.decay})
    add("| Signal | " + " | ".join(f"{h} j" for h in hs) + " |")
    add("|---|" + "---|" * len(hs))
    for v in res.verdicts:
        add(
            f"| {v.signal} | "
            + " | ".join(_f(v.decay.get(h, float("nan")), digits=3) for h in hs)
            + " |"
        )
    add("")
    add("## Portefeuilles (nets de coûts)")
    add("")
    add(
        "| Portefeuille | Période | Rend. ann. | Vol. ann. | Sharpe | Sortino | Drawdown max | "
        "% jours > 0 | Deflated Sharpe | Rotation ann. |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|")
    for name, per in res.books.items():
        for period, m in per.items():
            add(
                f"| {name} | {'conception' if period == 'IS' else 'hors éch.'} | "
                f"{_f(m['ann_return'], pct=True)} | {_f(m['ann_vol'], pct=True)} | "
                f"{_f(m['sharpe'])} | {_f(m['sortino'])} | {_f(m['max_drawdown'], pct=True)} | "
                f"{_f(m['hit_rate'], pct=True)} | "
                f"{_f(m['deflated_sharpe'])} | {_f(m['turnover_ann'])} |"
            )
    add("")
    add(
        f"*Deflated Sharpe : probabilité que le Sharpe dépasse le maximum attendu par chance après "
        f"{res.n_trials} essai(s) sur ces données (Bailey & López de Prado 2014). "
        "Une valeur < 0,95 signifie que la performance n'est pas distinguable du hasard.*"
    )
    add("")
    add("## Walk-forward : pondération par l'IC passé vs équipondération (livre M)")
    add("")
    wf = res.walk_forward
    if wf:
        add(
            f"- IC hors échantillon, pondération apprise (rétrécie vers 1/N) : "
            f"{_f(wf['ic_weighted_mean'], digits=3)} (t = {_f(wf['ic_weighted_t'])})"
        )
        add(
            f"- IC hors échantillon, équipondération : {_f(wf['equal_mean'], digits=3)} "
            f"(t = {_f(wf['equal_t'])})"
        )
        add(
            f"- Écart : {_f(wf['diff_mean'], digits=3)} (t = {_f(wf['diff_t'])}), "
            f"{int(wf['n_splits'])} périodes de test."
        )
        verdict = (
            "la pondération apprise ne fait pas significativement mieux : **on garde 1/N**."
            if not (math.isfinite(wf["diff_t"]) and wf["diff_t"] >= 2)
            else "la pondération apprise fait mieux (t ≥ 2) : à examiner avant tout changement."
        )
        add(f"- Conclusion : {verdict}")
    else:
        add("Historique insuffisant pour un walk-forward (3 ans d'apprentissage minimum).")
    add("")
    add("## Limites")
    add("")
    add("- Les secteurs sont ceux d'aujourd'hui (classification non historisée).")
    add("- Taux de change de repli fixes pour les filtres de liquidité en backtest.")
    add("- Le livre S est évalué à fréquence mensuelle en Phase 1 (hebdomadaire prévue).")
    add(
        "- Les décisions ci-dessus sont des **recommandations** : le changement de statut d'un "
        "signal se fait dans `config/signals.yaml`, avec une entrée de changelog."
    )
    for note in res.notes:
        add(f"- {note}")
    add("")
    return "\n".join(lines)
