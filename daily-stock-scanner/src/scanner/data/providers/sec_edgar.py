"""Provider SEC EDGAR : fondamentaux US « tels que déposés », dates d'annonce, métadonnées.

C'est la colonne vertébrale point-in-time pour les États-Unis :

* ``companyfacts`` fournit **chaque** valeur XBRL déposée, avec le numéro d'accession et
  la date de dépôt. Une valeur retraitée dans un dépôt ultérieur apparaît comme une
  nouvelle ligne : on peut donc reconstituer ce qui était connu à n'importe quelle date.
* ``submissions`` fournit l'horodatage d'acceptation de chaque dépôt et les items des
  8-K (item 2.02 = publication de résultats).

Règles d'accès SEC : User-Agent déclaratif obligatoire (« Nom email »), 10 requêtes/s max.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from scanner.core.logging import get_logger
from scanner.core.reference import sector_from_sic
from scanner.core.symbols import us_ticker
from scanner.core.timeutil import filing_available_at
from scanner.data.http import HttpClient
from scanner.data.providers.base import ProviderError
from scanner.data.schemas import EVENTS, FACTS, conform
from scanner.fundamentals.concepts import CONCEPTS, ifrs_index, us_gaap_index

log = get_logger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"

_EASTERN = ZoneInfo("America/New_York")
_US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split()
)
_ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
_QUARTERLY_FORMS = ("10-Q", "10-Q/A", "6-K")


def parse_acceptance(value: str | None) -> datetime | None:
    """Horodatage d'acceptation EDGAR -> UTC.

    Le champ est suffixé ``Z`` mais il est documenté de façon ambiguë. Par prudence, on
    l'interprète comme une heure de New York : si c'était réellement de l'UTC, on ne fait
    que retarder la disponibilité de 4 à 5 heures (jamais l'avancer).
    """
    if not value:
        return None
    naive = datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=None)
    return naive.replace(tzinfo=_EASTERN).astimezone(UTC)


def _fiscal_period_from_duration(start: str | None, end: str) -> str | None:
    if not start:
        return None
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    if 80 <= days <= 100:
        return "Q"
    if 170 <= days <= 195:
        return "H"
    if 260 <= days <= 285:
        return "9M"
    if 350 <= days <= 380:
        return "FY"
    return "OTHER"


def parse_companyfacts(payload: dict[str, Any], symbol: str,
                       acceptance_by_accn: dict[str, datetime] | None = None) -> pd.DataFrame:
    """Convertit une réponse ``companyfacts`` en faits canoniques (schéma ``FACTS``).

    ``acceptance_by_accn`` (optionnel) : horodatages d'acceptation issus de ``submissions``,
    plus précis que la simple date de dépôt.
    """
    gaap_idx = us_gaap_index()
    ifrs_idx = ifrs_index()
    acceptance_by_accn = acceptance_by_accn or {}
    rows: list[dict[str, Any]] = []
    facts = payload.get("facts", {})
    for taxonomy, tags in facts.items():
        for tag, body in tags.items():
            if taxonomy == "us-gaap":
                mapped = gaap_idx.get(tag)
            elif taxonomy == "dei":
                mapped = gaap_idx.get(f"dei:{tag}")
            elif taxonomy == "ifrs-full":
                mapped = ifrs_idx.get(tag)
            else:
                mapped = None
            if mapped is None:
                continue
            concept_name, rank = mapped
            concept = CONCEPTS[concept_name]
            for unit, items in body.get("units", {}).items():
                if not _unit_ok(concept_name, concept.nature, unit):
                    continue
                for it in items:
                    filed = it.get("filed")
                    end = it.get("end")
                    if not filed or not end or it.get("val") is None:
                        continue
                    accn = it.get("accn")
                    value = float(it["val"])
                    if concept.absolute:
                        value = abs(value)
                    avail = filing_available_at(date.fromisoformat(filed),
                                                acceptance_by_accn.get(accn or ""))
                    rows.append({
                        "symbol": symbol,
                        "concept": concept_name,
                        "value": value,
                        "period_start": it.get("start"),
                        "period_end": end,
                        "fiscal_period": _fiscal_period_from_duration(it.get("start"), end),
                        "form": it.get("form"),
                        "unit": unit,
                        "available_at": avail,
                        "lag_estimated": False,
                        "source": "sec_edgar",
                        "accession": accn,
                        "tag": f"{taxonomy}:{tag}",
                        "tag_rank": rank,
                    })
    if not rows:
        return conform(pd.DataFrame(columns=FACTS.columns), FACTS)
    df = conform(pd.DataFrame(rows), FACTS)
    # Un même fait peut apparaître plusieurs fois dans un dépôt (cadres différents) : dédoublonnage.
    return df.drop_duplicates(
        subset=["concept", "tag", "period_start", "period_end", "accession", "value"]
    ).reset_index(drop=True)


def _unit_ok(concept_name: str, nature: str, unit: str) -> bool:
    if concept_name == "shares_outstanding":
        return unit == "shares"
    if nature == "per_share":
        return "/shares" in unit
    return unit.isalpha() and len(unit) == 3  # montant en devise ISO (USD, EUR…)


def parse_submissions_filings(payload: dict[str, Any]) -> pd.DataFrame:
    """Table des dépôts (bloc ``filings.recent`` ou page d'archive)."""
    block = payload.get("filings", {}).get("recent", payload)
    keys = ["accessionNumber", "filingDate", "acceptanceDateTime", "form", "items",
            "reportDate", "primaryDocument"]
    n = len(block.get("accessionNumber", []))
    data = {k: block.get(k, [None] * n) for k in keys}
    df = pd.DataFrame(data)
    df["acceptance_utc"] = [parse_acceptance(v) for v in df["acceptanceDateTime"]]
    return df


def earnings_events(filings: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Publications de résultats : 8-K comportant l'item 2.02."""
    mask = filings["form"].isin(["8-K", "8-K/A"]) & filings["items"].fillna("").str.contains("2.02")
    sub = filings.loc[mask]
    ev = pd.DataFrame({
        "symbol": symbol,
        "event_type": "earnings_release",
        "event_time": sub["acceptance_utc"],
        "available_at": sub["acceptance_utc"],
        "source": "sec_edgar",
        "detail": sub["accessionNumber"],
    })
    return conform(ev, EVENTS)


class SecEdgarProvider:
    """Provider SEC EDGAR (fondamentaux et événements US)."""

    name = "sec_edgar"

    def __init__(self, user_agent: str | None, cache_dir: Path | None, rate_per_sec: float = 8,
                 cache_ttl_hours: float = 20, client: HttpClient | None = None) -> None:
        if client is None:
            if not user_agent or "@" not in user_agent:
                raise ProviderError(
                    "SEC_USER_AGENT manquant ou invalide : la SEC exige « Nom Prénom email@domaine »")
            client = HttpClient("sec_edgar", cache_dir, rate_per_sec,
                                headers={"User-Agent": user_agent,
                                         "Accept-Encoding": "gzip, deflate"})
        self.http = client
        self.ttl = cache_ttl_hours
        self._cik_map: dict[str, int] | None = None

    # -- référentiel ---------------------------------------------------------------------
    def cik_map(self) -> dict[str, int]:
        if self._cik_map is None:
            payload = self.http.get(TICKERS_URL, ttl_hours=24 * 7).json()
            self._cik_map = {str(v["ticker"]).upper().replace(".", "-"): int(v["cik_str"])
                             for v in payload.values()}
        return self._cik_map

    def cik_for(self, symbol: str) -> int:
        ticker = us_ticker(symbol).upper()
        cik = self.cik_map().get(ticker)
        if cik is None:
            raise ProviderError(f"{symbol} : CIK introuvable dans le référentiel SEC")
        return cik

    # -- dépôts -------------------------------------------------------------------------
    def submissions(self, cik: int, include_archive: bool = True) -> tuple[dict[str, Any], pd.DataFrame]:
        payload = self.http.get(SUBMISSIONS_URL.format(cik=cik), ttl_hours=self.ttl).json()
        frames = [parse_submissions_filings(payload)]
        if include_archive:
            for f in payload.get("filings", {}).get("files", []):
                page = self.http.get(SUBMISSIONS_PAGE_URL.format(name=f["name"]),
                                     ttl_hours=24 * 30).json()
                frames.append(parse_submissions_filings(page))
        return payload, pd.concat(frames, ignore_index=True)

    def get_facts(self, symbol: str) -> pd.DataFrame:
        cik = self.cik_for(symbol)
        _, filings = self.submissions(cik)
        acceptance = dict(zip(filings["accessionNumber"], filings["acceptance_utc"], strict=False))
        payload = self.http.get(FACTS_URL.format(cik=cik), ttl_hours=self.ttl).json()
        return parse_companyfacts(payload, symbol, acceptance)

    def get_events(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        cik = self.cik_for(symbol)
        _, filings = self.submissions(cik)
        ev = earnings_events(filings, symbol)
        lo = pd.Timestamp(start, tz="UTC")
        hi = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        return ev[(ev["event_time"] >= lo) & (ev["event_time"] < hi)].reset_index(drop=True)

    def get_security_info(self, symbol: str) -> dict[str, object]:
        cik = self.cik_for(symbol)
        payload, _ = self.submissions(cik, include_archive=False)
        state = (payload.get("addresses", {}).get("business", {}) or {}).get("stateOrCountry")
        return {
            "symbol": symbol,
            "name": payload.get("name"),
            "cik": f"{cik:010d}",
            "sic": payload.get("sic"),
            "sector": sector_from_sic(payload.get("sic")),
            "country": "US" if state in _US_STATES else None,
            "currency": "USD",
            "exchange": (payload.get("exchanges") or [None])[0],
            "source": self.name,
        }
