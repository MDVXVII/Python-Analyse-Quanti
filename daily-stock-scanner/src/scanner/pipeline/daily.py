"""Pipeline quotidien (Module 11) : collecte → contrôles → signaux → scores → rapport → journal.

Utilisé à l'identique en local (``scanner run``), par GitHub Actions et par la démo hors
ligne (``scanner demo``, données synthétiques). Chaque exécution laisse une trace
complète dans ``runs/<run_id>/`` (signaux, scores, idées, manifeste) pour l'audit.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scanner.core.config import BOOK_IDS, AppConfig, BookId, Secrets
from scanner.core.logging import get_logger
from scanner.core.timeutil import as_of_for_run
from scanner.data.fx import fx_symbol
from scanner.data.pit import PitView
from scanner.data.quality import issues_frame, run_quality_checks
from scanner.data.store import DataStore
from scanner.journal.journal import Journal
from scanner.journal.performance import evaluate_entries, summarize_performance
from scanner.pipeline.engine import compute_signals, score_all_books, upcoming_event_days
from scanner.report.email import send_report
from scanner.report.render import ReportContext, build_ideas, render
from scanner.scoring.composite import changes_vs_previous, select_ideas
from scanner.universe import live_universe, load_override

log = get_logger(__name__)


@dataclass
class RunPaths:
    data_dir: Path
    reports_dir: Path
    journal_file: Path
    commitments_dir: Path

    @classmethod
    def from_config(cls, config: AppConfig) -> RunPaths:
        p = config.settings.paths
        return cls(
            data_dir=config.resolve(p.data_dir),
            reports_dir=config.resolve(p.reports_dir),
            journal_file=config.resolve(p.journal_dir) / "journal.jsonl",
            commitments_dir=config.resolve(p.commitments_dir),
        )


@dataclass
class DailyResult:
    run_id: str
    report_md: Path
    report_html: Path
    ideas: pd.DataFrame
    commitment: Path | None
    emailed: bool
    notices: list[str] = field(default_factory=list)


def _git_sha() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip()
            or "inconnu"
        )
    except OSError:
        return "inconnu"


def _previous_run(store: DataStore, before: str) -> str | None:
    runs = [r for r in store.list_runs() if r < before]
    return runs[-1] if runs else None


def run_daily(
    config: AppConfig,
    secrets: Secrets,
    run_date: date,
    paths: RunPaths,
    constituents: dict[str, list[str]],
    constituents_status: dict[str, str],
    provider_status: dict[str, str] | None = None,
    demo: bool = False,
    send_email: bool = True,
    notices: list[str] | None = None,
) -> DailyResult:
    notices = list(notices or [])
    store = DataStore(paths.data_dir)
    as_of = as_of_for_run(run_date)
    run_id = f"{run_date.isoformat()}_{datetime.now(UTC).strftime('%H%M%S')}"
    symbols = sorted({s for syms in constituents.values() for s in syms})
    securities = store.read_securities()
    ccys = sorted({str(c) for c in securities["currency"].dropna()} - {"USD"})
    data = store.load(
        symbols + [fx_symbol(c) for c in ccys], start=run_date - timedelta(days=5 * 365 + 2)
    )
    view = PitView(data, as_of)

    # -- contrôles qualité ---------------------------------------------------------------------
    issues = run_quality_checks(view, symbols)
    blocked = {i.symbol for i in issues if i.severity == "BLOCK"}
    usable = [s for s in view.listed_symbols() if s in set(symbols) and s not in blocked]
    if not usable:
        raise RuntimeError("aucun titre exploitable après contrôles qualité (données absentes ?)")

    # -- signaux, univers, scores --------------------------------------------------------------
    sig = compute_signals(view, usable, config)
    if sig.fx_fallback_used:
        notices.append(
            "Taux de change de repli (approximatifs) utilisés pour : "
            + ", ".join(sig.fx_fallback_used)
            + " — filtres de liquidité seulement."
        )
    universe = live_universe(
        {k: [s for s in v if s in set(usable)] for k, v in constituents.items()},
        view.securities(),
        sig.values,
        sig.values,
        config.settings,
        sig.fx,
        srd_list=load_override(config.config_dir / "universe" / "srd_eligible.csv"),
        ttf_list=load_override(config.config_dir / "universe" / "ttf_list.csv"),
    )
    uni = universe.set_index("symbol")
    sig.meta["passes_liquidity"] = uni["passes_liquidity"].reindex(sig.meta.index).fillna(False)
    sig.meta["liquidity_note"] = uni["liquidity_note"].reindex(sig.meta.index).fillna("")
    upcoming = upcoming_event_days(view, usable)
    books = score_all_books(sig, config, upcoming)
    ideas = pd.concat(
        [
            select_ideas(
                books[b], config.settings.books[b].top_n_long, config.settings.books[b].top_n_short
            )
            for b in BOOK_IDS
        ],
        ignore_index=True,
    )

    # -- comparaison avec la veille ------------------------------------------------------------
    prev_id = _previous_run(store, run_id)
    prev_ideas = store.read_run_frame(prev_id, "ideas") if prev_id else None
    prev_fams = {
        b: f.set_index("symbol")
        for b in BOOK_IDS
        if prev_id
        and (f := store.read_run_frame(prev_id, f"families_{b}")) is not None
        and "symbol" in f.columns
    }
    changes = changes_vs_previous(
        ideas, prev_ideas, {b: books[b].families for b in BOOK_IDS}, prev_fams or None
    )

    # -- catalyseurs connus (calendrier des résultats) -----------------------------------------
    sched = view.events(["earnings_scheduled"])
    catalysts = None
    if not sched.empty:
        fut = sched[sched["event_time"] >= pd.Timestamp(as_of)]
        nxt = fut.sort_values("event_time").groupby("symbol")["event_time"].first()
        catalysts = nxt.map(
            lambda t: (
                f"publication de résultats prévue le {t.date().isoformat()} "
                f"(source : {sched['source'].iloc[0]})"
            )
        )

    # -- suivi des recommandations passées -----------------------------------------------------
    journal = Journal(paths.journal_file)
    perf_rows: list[dict[str, Any]] = []
    past = journal.to_frame()
    if not past.empty:
        ev = evaluate_entries(
            past,
            view.panel("open"),
            view.panel("close"),
            config.settings.journal.eval_horizons_days,
            config.settings.journal.reference_price,
        )
        perf = summarize_performance(ev, config.settings.journal.eval_horizons_days)
        perf_rows = [
            {str(k): v for k, v in r.items()} for r in perf.to_dict("records") if r["n"] > 0
        ]

    # -- rapport -------------------------------------------------------------------------------
    book_ctx: dict[str, dict[str, Any]] = {}
    alerts: list[str] = []
    for b in BOOK_IDS:
        idea_objs = build_ideas(
            b, ideas, books[b], sig.values, universe, view.securities(), config, catalysts
        )
        book_ctx[b] = {"label": config.settings.books[b].label, "ideas": idea_objs}
        for i in idea_objs:
            alerts += [f"{i.symbol} (livre {b}) : {f}" for f in i.flags]
    if blocked:
        alerts.append(
            f"{len(blocked)} titre(s) écarté(s) par les contrôles qualité (voir section 6)."
        )
    sources = [
        {"name": k, "usage": "prix / fondamentaux / événements", "status": v}
        for k, v in (provider_status or {}).items()
    ]
    sources += [
        {"name": f"composition {k}", "usage": "univers palier 1", "status": v}
        for k, v in constituents_status.items()
    ]
    ctx = ReportContext(
        run_date=run_date.isoformat(),
        as_of=as_of.isoformat(),
        last_price_date=str(view.last_price_date),
        run_id=run_id,
        config_fingerprint=config.fingerprint,
        data_sources=sources,
        universe_size=len(universe),
        universe_liquid=int(universe["passes_liquidity"].sum()),
        books=book_ctx,
        changes=[{str(k): str(v) for k, v in c.items()} for c in changes.to_dict("records")],
        alerts=alerts,
        qc=[
            {str(k): str(v) for k, v in q.items()} for q in issues_frame(issues).to_dict("records")
        ],
        performance=perf_rows,
        notices=notices,
        demo=demo,
    )
    md, html = render(ctx)
    paths.reports_dir.mkdir(parents=True, exist_ok=True)
    md_path = paths.reports_dir / f"{run_date.isoformat()}.md"
    html_path = paths.reports_dir / f"{run_date.isoformat()}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    # -- archivage pour audit ------------------------------------------------------------------
    store.write_run_frame(run_id, "ideas", ideas)
    store.write_run_frame(run_id, "universe", universe)
    num = sig.values.select_dtypes(include=[np.number, "bool"])
    store.write_run_frame(run_id, "signals", num.reset_index())
    for b in BOOK_IDS:
        store.write_run_frame(
            run_id, f"families_{b}", books[b].families.rename_axis("symbol").reset_index()
        )
        store.write_run_frame(
            run_id,
            f"scores_{b}",
            pd.DataFrame(
                {"composite": books[b].composite, "raw": books[b].raw_composite}
            ).reset_index(),
        )
    store.write_run_manifest(
        run_id,
        {
            "run_id": run_id,
            "run_date": run_date.isoformat(),
            "as_of": as_of.isoformat(),
            "config": config.fingerprint,
            "code": _git_sha(),
            "symbols": len(symbols),
            "usable": len(usable),
            "qc_issues": len(issues),
            "providers": provider_status or {},
            "constituents": constituents_status,
            "demo": demo,
        },
    )

    # -- journal et engagement public ----------------------------------------------------------
    records = []
    for _, r in ideas.iterrows():
        book: BookId = r["book"]
        records.append(
            {
                "run_id": run_id,
                "as_of": as_of.isoformat(),
                "book": book,
                "side": r["side"],
                "rank": int(r["rank"]),
                "symbol": r["symbol"],
                "score": round(float(r["score"]), 6),
                "horizon_days": config.settings.books[book].horizon_days,
                "reference_price": config.settings.journal.reference_price,
                "config": config.fingerprint,
                "code": _git_sha(),
                "demo": demo,
            }
        )
    journal.append(records)
    commitment = journal.write_commitment(
        run_date.isoformat(), paths.commitments_dir, {"config": config.fingerprint, "demo": demo}
    )

    emailed = False
    if send_email:
        try:
            emailed = send_report(secrets, f"Scanner quotidien — {run_date.isoformat()}", md, html)
        except Exception as exc:  # l'échec d'envoi ne doit pas faire échouer l'exécution
            notices.append(f"envoi email en échec : {str(exc)[:120]}")
    log.info("exécution terminée", extra={"ctx": {"run_id": run_id, "ideas": len(ideas)}})
    return DailyResult(
        run_id=run_id,
        report_md=md_path,
        report_html=html_path,
        ideas=ideas,
        commitment=commitment,
        emailed=emailed,
        notices=notices,
    )
