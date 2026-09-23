"""Provider Finnhub (offre gratuite : 60 appels/min, usage personnel).

Usage en Phase 1 : **calendrier des résultats à venir** (catalyseurs datés, pénalité
« événement binaire imminent »). La date d'annonce du calendrier n'étant pas historisée,
ces données servent au rapport du jour, jamais au backtest.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from scanner.data.http import HttpClient
from scanner.data.providers.base import ProviderError
from scanner.data.schemas import EVENTS, conform

BASE = "https://finnhub.io/api/v1"


def calendar_to_events(payload: dict[str, Any], observed_at: datetime) -> pd.DataFrame:
    rows = []
    for e in payload.get("earningsCalendar", []) or []:
        if not e.get("symbol") or not e.get("date"):
            continue
        hour = (e.get("hour") or "").lower()  # bmo / amc / dmh
        rows.append(
            {
                "symbol": f"{str(e['symbol']).replace('.', '-')}.US",
                "event_type": "earnings_scheduled",
                "event_time": pd.Timestamp(e["date"], tz="UTC"),
                "available_at": observed_at,
                "source": "finnhub",
                "detail": hour or None,
            }
        )
    if not rows:
        return conform(pd.DataFrame(columns=EVENTS.columns), EVENTS)
    return conform(pd.DataFrame(rows), EVENTS)


class FinnhubProvider:
    name = "finnhub"

    def __init__(
        self,
        api_key: str | None,
        cache_dir: Path | None,
        rate_per_sec: float = 0.9,
        cache_ttl_hours: float = 12,
        client: HttpClient | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ProviderError("FINNHUB_API_KEY manquante")
            client = HttpClient("finnhub", cache_dir, rate_per_sec)
        self.http = client
        self.key = api_key or ""
        self.ttl = cache_ttl_hours

    def earnings_calendar(self, start: date, end: date) -> pd.DataFrame:
        payload = self.http.get(
            f"{BASE}/calendar/earnings",
            params={"from": start.isoformat(), "to": end.isoformat(), "token": self.key},
            ttl_hours=self.ttl,
        ).json()
        return calendar_to_events(payload, datetime.now(UTC))
