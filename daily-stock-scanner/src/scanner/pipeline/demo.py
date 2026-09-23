"""Démonstration de bout en bout sur données synthétiques (aucun accès réseau).

Écrit un marché synthétique dans un stockage temporaire, exécute le pipeline quotidien sur
deux séances consécutives (pour illustrer la section « changements vs la veille »), et
optionnellement le protocole de validation complet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scanner.backtest.report import render_validation_markdown
from scanner.backtest.validation import ValidationSettings, run_validation
from scanner.core.config import AppConfig, Secrets
from scanner.data.providers.synthetic import SyntheticSpec, generate
from scanner.data.store import DataStore
from scanner.pipeline.daily import DailyResult, RunPaths, run_daily

DEMO_NOTICE = (
    "Démonstration : marché synthétique généré localement (voir "
    "scanner/data/providers/synthetic.py). Aucune donnée réelle."
)


@dataclass
class DemoResult:
    daily: list[DailyResult]
    validation_md: Path | None


def run_demo(
    config: AppConfig,
    out_dir: Path,
    days: tuple[date, ...] = (date(2026, 9, 22), date(2026, 9, 23)),
    with_validation: bool = False,
    n_securities: int = 240,
) -> DemoResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    market = generate(SyntheticSpec(n_securities=n_securities, end=date(2026, 9, 22)))
    paths = RunPaths(
        data_dir=out_dir / "data",
        reports_dir=out_dir / "reports",
        journal_file=out_dir / "journal" / "journal.jsonl",
        commitments_dir=out_dir / "commitments",
    )
    store = DataStore(paths.data_dir)
    d = market.data
    store.write_prices(d.prices)
    store.write_facts(d.facts)
    store.write_events(d.events)
    store.write_securities(d.securities)
    # Comme une composition d'indice réelle : uniquement les sociétés encore cotées.
    listed = d.securities[d.securities["delisted_on"].isna()]["symbol"].astype(str)
    constituents = {"SYNTH": sorted(listed)}
    status = {"SYNTH": f"générateur synthétique ({len(constituents['SYNTH'])} titres cotés)"}
    secrets = Secrets(_env_file=None)  # type: ignore[call-arg]
    results = [
        run_daily(
            config,
            secrets,
            day,
            paths,
            constituents,
            status,
            provider_status={"synthétique": "actif (hors ligne)"},
            demo=True,
            send_email=False,
            notices=[DEMO_NOTICE],
        )
        for day in days
    ]
    md_path = None
    if with_validation:
        vs = ValidationSettings(
            region="US",
            start=date(2015, 6, 1),
            end=date(2026, 6, 30),
            oos_start=date(2020, 1, 1),
            data_label="synthétique (générateur interne)",
            survivorship_free=True,
        )
        res = run_validation(d, config, vs, trials_log=out_dir / "trials.jsonl")
        md_path = out_dir / "reports" / "validation_synthetique.md"
        md_path.write_text(render_validation_markdown(res), encoding="utf-8")
    return DemoResult(daily=results, validation_md=md_path)
