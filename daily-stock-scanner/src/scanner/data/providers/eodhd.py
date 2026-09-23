"""Provider EODHD (payant, ~100 €/mois pour l'offre All-In-One) : source principale prévue.

Apports clés (vérifiés le 23/09/2026, voir ARCHITECTURE.md §2) : prix mondiaux ajustés,
**délistés** (US depuis 2000 ; hors US surtout les 6-7 dernières années), bulk EOD par
place (un appel = toute une place pour un jour), fondamentaux, calendriers.

Avertissement d'honnêteté : ce module a été écrit d'après la documentation publique
d'EODHD et testé sur des réponses **simulées** ; il n'a pas encore été confronté à des
réponses réelles (accès réseau indisponible lors du développement). Les noms de champs
sont lus de façon défensive et toute donnée inattendue est journalisée.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from scanner.core.logging import get_logger
from scanner.core.reference import normalize_sector
from scanner.core.timeutil import estimated_available_at, filing_available_at
from scanner.data.http import HttpClient
from scanner.data.providers.base import ProviderError
from scanner.data.schemas import EVENTS, FACTS, PRICES, conform
from scanner.fundamentals.concepts import CONCEPTS, eodhd_index

log = get_logger(__name__)

BASE = "https://eodhd.com/api"

# Codes d'indices EODHD (à confirmer sur le compte : la couverture des compositions varie).
INDEX_CODES = {"SP500": "GSPC.INDX", "NDX100": "NDX.INDX", "STOXX600": "STOXX600.INDX",
               "SBF120": "SBF120.INDX"}


def eod_json_to_prices(rows: list[dict[str, Any]], symbol: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return conform(pd.DataFrame(columns=PRICES.columns), PRICES)
    df = df.rename(columns={"adjusted_close": "adj_close"})
    df["symbol"] = symbol
    df["source"] = "eodhd"
    df["ingested_at"] = datetime.now(UTC)
    return conform(df, PRICES)


def bulk_json_to_prices(rows: list[dict[str, Any]], exchange: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return conform(pd.DataFrame(columns=PRICES.columns), PRICES)
    df = df.rename(columns={"adjusted_close": "adj_close"})
    df["symbol"] = df["code"].astype(str) + "." + exchange
    df["source"] = "eodhd"
    df["ingested_at"] = datetime.now(UTC)
    return conform(df, PRICES)


def fundamentals_to_facts(payload: dict[str, Any], symbol: str,
                          lags: dict[str, int]) -> pd.DataFrame:
    """Convertit ``/fundamentals`` en faits canoniques.

    Date de publication : champ ``filing_date`` quand il existe, sinon décalage conservateur
    (``lag_estimated=True``). Les BPA publiés viennent de ``Earnings::History`` (``reportDate``).
    """
    idx = eodhd_index()
    rows: list[dict[str, Any]] = []
    fin = payload.get("Financials") or {}
    for statement in ("Income_Statement", "Balance_Sheet", "Cash_Flow"):
        block = fin.get(statement) or {}
        currency = block.get("currency_symbol")
        for freq in ("yearly", "quarterly"):
            months = 12 if freq == "yearly" else 3
            lag = lags["annual"] if freq == "yearly" else lags["quarterly"]
            for key, entry in (block.get(freq) or {}).items():
                if not isinstance(entry, dict):
                    continue
                end = pd.Timestamp(entry.get("date") or key).normalize()
                filing = entry.get("filing_date")
                if filing:
                    avail = filing_available_at(date.fromisoformat(str(filing)[:10]))
                    estimated = False
                else:
                    avail = estimated_available_at(end.date(), lag)
                    estimated = True
                for field, raw in entry.items():
                    mapped = idx.get(field)
                    if mapped is None or raw in (None, "", "None"):
                        continue
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        continue
                    concept_name, rank = mapped
                    concept = CONCEPTS[concept_name]
                    if concept.absolute:
                        value = abs(value)
                    is_flow = concept.nature != "stock"
                    rows.append({
                        "symbol": symbol, "concept": concept_name, "value": value,
                        "period_start": (end - pd.DateOffset(months=months) + pd.Timedelta(days=1))
                        if is_flow else None,
                        "period_end": end,
                        "fiscal_period": ("FY" if freq == "yearly" else "Q") if is_flow else None,
                        "form": f"eodhd-{freq}", "unit": entry.get("currency_symbol") or currency,
                        "available_at": avail, "lag_estimated": estimated, "source": "eodhd",
                        "tag": f"{statement}.{field}", "tag_rank": rank,
                    })
    history = ((payload.get("Earnings") or {}).get("History") or {})
    for key, entry in history.items():
        eps = entry.get("epsActual") if isinstance(entry, dict) else None
        report = entry.get("reportDate") if isinstance(entry, dict) else None
        if eps is None or not report:
            continue
        end = pd.Timestamp(entry.get("date") or key).normalize()
        rows.append({
            "symbol": symbol, "concept": "eps_diluted", "value": float(eps),
            "period_start": end - pd.DateOffset(months=3) + pd.Timedelta(days=1),
            "period_end": end, "fiscal_period": "Q", "form": "eodhd-earnings",
            "unit": "per_share", "available_at": filing_available_at(date.fromisoformat(report[:10])),
            "lag_estimated": False, "source": "eodhd", "tag": "Earnings.epsActual", "tag_rank": 0,
        })
    if not rows:
        return conform(pd.DataFrame(columns=FACTS.columns), FACTS)
    return conform(pd.DataFrame(rows), FACTS)


def fundamentals_to_events(payload: dict[str, Any], symbol: str) -> pd.DataFrame:
    history = ((payload.get("Earnings") or {}).get("History") or {})
    rows = []
    for entry in history.values():
        if not isinstance(entry, dict) or not entry.get("reportDate"):
            continue
        d = date.fromisoformat(entry["reportDate"][:10])
        # « AfterMarket » : l'information n'est exploitable qu'à la séance suivante.
        when = datetime.combine(d, datetime.min.time(), tzinfo=UTC)
        avail = when + timedelta(days=1)
        rows.append({"symbol": symbol, "event_type": "earnings_release", "event_time": when,
                     "available_at": avail, "source": "eodhd",
                     "detail": entry.get("beforeAfterMarket")})
    if not rows:
        return conform(pd.DataFrame(columns=EVENTS.columns), EVENTS)
    return conform(pd.DataFrame(rows), EVENTS)


class EodhdProvider:
    name = "eodhd"

    def __init__(self, api_key: str | None, cache_dir: Path | None, rate_per_sec: float = 15,
                 cache_ttl_hours: float = 20, publication_lags: dict[str, int] | None = None,
                 client: HttpClient | None = None) -> None:
        if client is None:
            if not api_key:
                raise ProviderError("EODHD_API_KEY manquante")
            client = HttpClient("eodhd", cache_dir, rate_per_sec)
        self.http = client
        self.key = api_key or ""
        self.ttl = cache_ttl_hours
        self.lags = publication_lags or {"annual": 120, "semiannual": 75, "quarterly": 60}
        self._fund_cache: dict[str, dict[str, Any]] = {}

    def _get(self, path: str, ttl: float | None = None, **params: Any) -> Any:
        params = {"api_token": self.key, "fmt": "json", **params}
        return self.http.get(f"{BASE}/{path}", params=params, ttl_hours=ttl).json()

    def get_daily_prices(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        rows = self._get(f"eod/{symbol}", ttl=self.ttl, **{"from": start.isoformat(),
                                                            "to": end.isoformat()})
        return eod_json_to_prices(rows, symbol)

    def get_bulk_prices(self, exchange: str, day: date) -> pd.DataFrame:
        rows = self._get(f"eod-bulk-last-day/{exchange}", ttl=self.ttl, date=day.isoformat())
        return bulk_json_to_prices(rows, exchange)

    def _fundamentals(self, symbol: str) -> dict[str, Any]:
        if symbol not in self._fund_cache:
            self._fund_cache[symbol] = self._get(f"fundamentals/{symbol}", ttl=self.ttl)
        return self._fund_cache[symbol]

    def get_facts(self, symbol: str) -> pd.DataFrame:
        return fundamentals_to_facts(self._fundamentals(symbol), symbol, self.lags)

    def get_events(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        ev = fundamentals_to_events(self._fundamentals(symbol), symbol)
        lo, hi = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        return ev[(ev["event_time"] >= lo) & (ev["event_time"] < hi)].reset_index(drop=True)

    def get_security_info(self, symbol: str) -> dict[str, object]:
        f = self._fundamentals(symbol)
        g = f.get("General") or {}
        h = f.get("Highlights") or {}
        s = f.get("SharesStats") or {}
        return {
            "symbol": symbol, "name": g.get("Name") or symbol, "isin": g.get("ISIN"),
            "country": g.get("CountryISO"), "currency": g.get("CurrencyCode"),
            "exchange": g.get("Exchange"),
            "sector": normalize_sector(g.get("GicSector") or g.get("Sector")),
            "industry": g.get("GicIndustry") or g.get("Industry"), "security_type": g.get("Type"),
            "delisted_on": g.get("DelistedDate"), "market_cap": h.get("MarketCapitalization"),
            "shares_outstanding": s.get("SharesOutstanding"), "source": self.name,
        }

    def get_exchange_symbols(self, exchange: str, delisted: bool = False) -> pd.DataFrame:
        rows = self._get(f"exchange-symbol-list/{exchange}", ttl=24 * 7,
                         **({"delisted": 1} if delisted else {}))
        return pd.DataFrame(rows)

    def get_constituents(self, index_id: str) -> list[str]:
        code = INDEX_CODES.get(index_id)
        if code is None:
            raise ProviderError(f"indice inconnu pour EODHD : {index_id}")
        payload = self._get(f"fundamentals/{code}", ttl=24)
        comps = payload.get("Components") or {}
        out = [f"{c['Code']}.{c.get('Exchange', 'US')}" for c in comps.values()
               if isinstance(c, dict) and c.get("Code")]
        if not out:
            raise ProviderError(f"composition vide pour {index_id} ({code}) sur EODHD")
        return out
