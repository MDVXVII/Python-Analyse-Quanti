"""Interface en ligne de commande : ``scanner --help``."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import typer

from scanner.core.config import Secrets, load_config
from scanner.core.logging import setup_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Scanner d'actions quotidien (fondamental, quant, flux, actualité, macro).",
)
journal_app = typer.Typer(no_args_is_help=True, help="Journal des recommandations.")
app.add_typer(journal_app, name="journal")


def _date(value: str | None) -> date:
    return date.fromisoformat(value) if value else datetime.now(UTC).date()


@app.command()
def demo(
    out: Path = typer.Option(Path("data/demo"), help="Dossier de sortie"),
    validation: bool = typer.Option(False, help="Exécuter aussi la validation (quelques minutes)"),
) -> None:
    """Démonstration hors ligne sur données synthétiques (aucune clé, aucun réseau)."""
    setup_logging()
    from scanner.pipeline.demo import run_demo

    res = run_demo(load_config(), out, with_validation=validation)
    for r in res.daily:
        typer.echo(f"rapport : {r.report_md}")
    if res.validation_md:
        typer.echo(f"validation : {res.validation_md}")


@app.command()
def run(
    day: str = typer.Option(
        None, "--date", help="Date d'exécution AAAA-MM-JJ (défaut : aujourd'hui UTC)"
    ),
    ingest_data: bool = typer.Option(
        True, "--ingest/--no-ingest", help="Collecter les données avant"
    ),
    email: bool = typer.Option(True, "--email/--no-email", help="Envoyer le rapport par email"),
    limit: int = typer.Option(0, help="Limiter l'univers aux N premiers titres (tests)"),
) -> None:
    """Exécution quotidienne : collecte, contrôles, signaux, scores, rapport, journal."""
    setup_logging()
    from scanner.data.store import DataStore
    from scanner.pipeline.daily import RunPaths, run_daily
    from scanner.pipeline.ingest import build_providers, fetch_constituents, ingest

    config = load_config()
    secrets = Secrets()
    run_date = _date(day)
    providers = build_providers(config, secrets)
    constituents, cons_status = fetch_constituents(
        providers, config.settings.universe.tier1_indices
    )
    if limit:
        constituents = {k: v[:limit] for k, v in constituents.items()}
    symbols = sorted({s for v in constituents.values() for s in v})
    if not symbols:
        typer.echo(
            "Aucune composition d'indice disponible : voir config/universe/README.md", err=True
        )
        raise typer.Exit(code=2)
    paths = RunPaths.from_config(config)
    notices = []
    if ingest_data:
        rep = ingest(DataStore(paths.data_dir), providers, symbols, run_date, config)
        notices.append(f"Collecte : {rep.summary()}.")
        if rep.errors:
            notices.append("Erreurs de collecte (extrait) : " + " ; ".join(rep.errors[:5]))
    res = run_daily(
        config,
        secrets,
        run_date,
        paths,
        constituents,
        cons_status,
        provider_status=providers.status,
        send_email=email,
        notices=notices,
    )
    typer.echo(f"rapport : {res.report_md}")
    typer.echo(f"engagement public : {res.commitment}")


@app.command()
def validate(
    region: str = typer.Option("US"),
    start: str = typer.Option("2011-01-01"),
    end: str = typer.Option(None),
    oos_start: str = typer.Option("2019-01-01"),
    label: str = typer.Option("données locales", help="Origine des données (affichée)"),
    survivorship_free: bool = typer.Option(False, help="La base inclut-elle les délistés ?"),
) -> None:
    """Protocole de validation sur les données du stockage local (Module 9)."""
    setup_logging()
    from scanner.backtest.report import render_validation_markdown
    from scanner.backtest.validation import ValidationSettings, run_validation
    from scanner.data.store import DataStore
    from scanner.pipeline.daily import RunPaths

    config = load_config()
    paths = RunPaths.from_config(config)
    data = DataStore(paths.data_dir).load()
    vs = ValidationSettings(
        region=region,
        start=_date(start),
        end=_date(end),
        oos_start=_date(oos_start),
        data_label=label,
        survivorship_free=survivorship_free,
    )
    res = run_validation(data, config, vs, trials_log=paths.data_dir / "backtests" / "trials.jsonl")
    out = paths.reports_dir / f"validation_{region}_{vs.end.isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_validation_markdown(res), encoding="utf-8")
    typer.echo(f"rapport de validation : {out}")


@app.command()
def snapshot(day: str = typer.Option(None, "--date"), max_symbols: int = typer.Option(0)) -> None:
    """Archive les instantanés de consensus et d'options (historique PIT construit par nous)."""
    setup_logging()
    import pandas as pd

    from scanner.data.store import DataStore
    from scanner.pipeline.daily import RunPaths
    from scanner.pipeline.ingest import build_providers, fetch_constituents

    config = load_config()
    providers = build_providers(config, Secrets())
    if providers.yfinance is None:
        typer.echo("yfinance indisponible", err=True)
        raise typer.Exit(code=2)
    cons, _ = fetch_constituents(providers, ["SP500", "NDX100"])
    us = sorted({s for v in cons.values() for s in v})
    snap_cfg = config.settings.snapshots
    store = DataStore(RunPaths.from_config(config).data_dir)
    run_date = _date(day)
    for kind, cfg, fn in (
        ("consensus", snap_cfg.consensus, providers.yfinance.consensus_snapshot),
        ("options", snap_cfg.options, providers.yfinance.options_snapshot),
    ):
        if not cfg.enabled:
            continue
        n = max_symbols or cfg.max_symbols
        rows = []
        for sym in us[:n]:
            try:
                rows.append(fn(sym))
            except Exception as exc:  # source non officielle : on consigne et on continue
                rows.append({"symbol": sym, "error": str(exc)[:120]})
        path = store.write_snapshot(kind, run_date, pd.DataFrame(rows))
        typer.echo(f"{kind} : {path} ({len(rows)} titres)")


@journal_app.command("verify")
def journal_verify() -> None:
    """Vérifie l'intégrité de la chaîne de hachage du journal."""
    from scanner.journal.journal import Journal
    from scanner.pipeline.daily import RunPaths

    ok, n, problem = Journal(RunPaths.from_config(load_config()).journal_file).verify()
    typer.echo(
        f"{'intègre' if ok else 'CORROMPU'} : {n} entrée(s)" + (f" — {problem}" if problem else "")
    )
    raise typer.Exit(code=0 if ok else 1)


if __name__ == "__main__":  # pragma: no cover
    app()
