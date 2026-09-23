"""Collecte incrémentale des données vers le stockage local (Module 1).

Chaque source est interrogée selon l'ordre de priorité de ``sources.yaml`` ; une panne
n'arrête pas l'exécution : elle est consignée et remonte dans le rapport (section
qualité des données). Les faits fondamentaux ne sont re-téléchargés qu'après
``refresh_days`` jours (ils changent au rythme des publications).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from scanner.core.config import AppConfig, Secrets
from scanner.core.logging import get_logger
from scanner.core.symbols import default_country, default_currency, split
from scanner.data.providers.base import ProviderError
from scanner.data.providers.constituents import LocalCsvConstituents, WikipediaConstituents
from scanner.data.providers.eodhd import EodhdProvider
from scanner.data.providers.finnhub import FinnhubProvider
from scanner.data.providers.sec_edgar import SecEdgarProvider
from scanner.data.providers.yfinance_provider import YFinanceProvider
from scanner.data.store import DataStore

log = get_logger(__name__)


@dataclass
class Providers:
    sec: SecEdgarProvider | None
    yfinance: YFinanceProvider | None
    eodhd: EodhdProvider | None
    finnhub: FinnhubProvider | None
    constituents: list[Any]
    status: dict[str, str] = field(default_factory=dict)


def build_providers(config: AppConfig, secrets: Secrets) -> Providers:
    cache = config.resolve(config.settings.paths.cache_dir)
    src = config.sources.providers
    lags: dict[str, int] = {str(k): v for k, v in config.sources.publication_lags_days.items()}
    status: dict[str, str] = {}

    def attempt(name: str, factory: Any) -> Any:
        if not config.provider_enabled(name, secrets):
            status[name] = "désactivé (pas de clé)" if src[name].enabled == "auto" else "désactivé"
            return None
        try:
            obj = factory()
            status[name] = "actif"
            return obj
        except ProviderError as exc:
            status[name] = f"indisponible : {exc}"
            return None

    sec = attempt(
        "sec_edgar",
        lambda: SecEdgarProvider(
            secrets.sec_user_agent,
            cache,
            src["sec_edgar"].rate_per_sec or 8,
            src["sec_edgar"].cache_ttl_hours or 20,
        ),
    )
    yf = attempt("yfinance", lambda: YFinanceProvider(src["yfinance"].pause_seconds or 0.3, lags))
    eod = attempt(
        "eodhd",
        lambda: EodhdProvider(
            secrets.eodhd_api_key,
            cache,
            src["eodhd"].rate_per_sec or 15,
            src["eodhd"].cache_ttl_hours or 20,
            lags,
        ),
    )
    fh = attempt(
        "finnhub",
        lambda: FinnhubProvider(
            secrets.finnhub_api_key,
            cache,
            src["finnhub"].rate_per_sec or 0.9,
            src["finnhub"].cache_ttl_hours or 12,
        ),
    )
    chain: list[Any] = []
    for name in config.sources.priority.get("constituents", []):
        if name == "eodhd" and eod is not None:
            chain.append(eod)
        elif name == "local_csv":
            chain.append(LocalCsvConstituents(config.config_dir / "universe"))
        elif name == "wikipedia":
            chain.append(WikipediaConstituents())
    return Providers(sec=sec, yfinance=yf, eodhd=eod, finnhub=fh, constituents=chain, status=status)


def fetch_constituents(
    providers: Providers, indices: list[str]
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Composition de chaque indice, avec la source effectivement utilisée (ou l'échec)."""
    out: dict[str, list[str]] = {}
    used: dict[str, str] = {}
    for index_id in indices:
        errors = []
        for p in providers.constituents:
            try:
                out[index_id] = p.get_constituents(index_id)
                used[index_id] = f"{p.name} ({len(out[index_id])} titres)"
                break
            except Exception as exc:  # une source en panne ne doit pas bloquer les autres
                errors.append(f"{p.name}: {str(exc)[:80]}")
        if index_id not in out:
            used[index_id] = "INDISPONIBLE — " + " | ".join(errors)
    return out, used


@dataclass
class IngestReport:
    prices_rows: int = 0
    facts_rows: int = 0
    events_rows: int = 0
    securities: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.prices_rows} lignes de prix, {self.facts_rows} faits, {self.events_rows} "
            f"événements, {self.securities} fiches ; {len(self.errors)} erreur(s)"
        )


def _state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def ingest(
    store: DataStore,
    providers: Providers,
    symbols: list[str],
    run_date: date,
    config: AppConfig,
    history_years: int = 4,
    refresh_days: int = 7,
) -> IngestReport:
    rep = IngestReport()
    state_path = store.root / "ingest_state.json"
    state = _state(state_path)
    start_full = run_date - timedelta(days=365 * history_years + 30)

    # -- référentiel ----------------------------------------------------------------------
    known = set(store.read_securities()["symbol"].astype(str))
    infos = []
    for sym in [s for s in symbols if s not in known]:
        info: dict[str, Any] | None = None
        for p in (providers.eodhd, providers.yfinance, providers.sec):
            if p is None or (p is providers.sec and not sym.endswith(".US")):
                continue
            try:
                info = p.get_security_info(sym)
                break
            except Exception as exc:
                rep.errors.append(f"fiche {sym} via {p.name} : {str(exc)[:80]}")
        info = info or {"symbol": sym, "name": sym}
        info.setdefault("country", default_country(sym))
        info["country"] = info.get("country") or default_country(sym)
        info["currency"] = info.get("currency") or default_currency(sym)
        infos.append(info)
    if infos:
        rep.securities = store.write_securities(pd.DataFrame(infos))

    # -- prix (incrémental) -----------------------------------------------------------------
    existing = store.read_prices(symbols)
    last = (
        existing.groupby("symbol")["date"].max()
        if not existing.empty
        else pd.Series(dtype="datetime64[ns]")
    )
    need_full = [s for s in symbols if s not in last.index]
    need_inc = [s for s in symbols if s in last.index]
    inc_start = (last.min().date() - timedelta(days=10)) if len(last) else start_full
    frames = []
    if providers.eodhd is not None:
        for sym in symbols:
            s0 = start_full if sym in need_full else (last[sym].date() - timedelta(days=10))
            try:
                frames.append(providers.eodhd.get_daily_prices(sym, s0, run_date))
            except Exception as exc:
                rep.errors.append(f"prix {sym} (eodhd) : {str(exc)[:80]}")
    elif providers.yfinance is not None:
        for group, s0 in ((need_full, start_full), (need_inc, inc_start)):
            if group:
                try:
                    frames.append(providers.yfinance.get_daily_prices_batch(group, s0, run_date))
                except Exception as exc:
                    rep.errors.append(f"prix (yfinance, {len(group)} titres) : {str(exc)[:120]}")
    for f in frames:
        if not f.empty:
            rep.prices_rows += store.write_prices(f)

    # -- taux de change -------------------------------------------------------------------------
    sec_tab = store.read_securities()
    ccys = sorted({str(c) for c in sec_tab["currency"].dropna()} - {"USD"})
    if providers.yfinance is not None:
        for ccy in ccys:
            try:
                rep.prices_rows += store.write_prices(
                    providers.yfinance.get_fx_to_usd(ccy, start_full, run_date)
                )
            except Exception as exc:
                rep.errors.append(f"change {ccy} : {str(exc)[:80]}")

    # -- fondamentaux et événements (rafraîchis tous les ``refresh_days`` jours) ---------------
    for sym in symbols:
        last_fetch = state.get("facts", {}).get(sym)
        if last_fetch and (run_date - date.fromisoformat(last_fetch)).days < refresh_days:
            continue
        us = split(sym)[1] == "US"
        order = [providers.sec, providers.eodhd] if us else [providers.eodhd, providers.yfinance]
        for p in [p for p in order if p is not None]:
            try:
                facts = p.get_facts(sym)
                rep.facts_rows += store.write_facts(facts)
                if hasattr(p, "get_events"):
                    ev = p.get_events(sym, start_full, run_date)
                    rep.events_rows += store.write_events(ev)
                state.setdefault("facts", {})[sym] = run_date.isoformat()
                break
            except Exception as exc:
                rep.errors.append(f"fondamentaux {sym} via {p.name} : {str(exc)[:80]}")

    # -- calendrier des résultats à venir ----------------------------------------------------------
    if providers.finnhub is not None:
        try:
            cal = providers.finnhub.earnings_calendar(run_date, run_date + timedelta(days=21))
            cal = cal[cal["symbol"].isin(symbols)]
            rep.events_rows += store.write_events(cal)
        except Exception as exc:
            rep.errors.append(f"calendrier (finnhub) : {str(exc)[:80]}")

    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    log.info("ingestion terminée", extra={"ctx": {"summary": rep.summary()}})
    return rep
