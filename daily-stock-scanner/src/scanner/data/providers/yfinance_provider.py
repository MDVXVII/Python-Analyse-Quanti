"""Provider yfinance (Yahoo Finance, non officiel) : prototypage, secours, instantanés.

Limites connues (ARCHITECTURE.md §2) : API non officielle, limitations de débit
fréquentes (``YFRateLimitError``), pas de délistés, fondamentaux limités à ~4-5 périodes
**sans date de publication** (les faits sont donc marqués ``lag_estimated=True``).
À ne jamais utiliser comme source critique une fois EODHD en place.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from scanner.core.logging import get_logger
from scanner.core.reference import normalize_sector
from scanner.core.symbols import default_country, default_currency, to_yahoo
from scanner.core.timeutil import estimated_available_at
from scanner.data.providers.base import ProviderError
from scanner.data.schemas import FACTS, PRICES, conform

log = get_logger(__name__)

# Libellés yfinance -> concept canonique
_YF_FIELDS: dict[str, tuple[str, ...]] = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "cogs": ("Cost Of Revenue",),
    "gross_profit": ("Gross Profit",),
    "sga": ("Selling General And Administration",),
    "ebit": ("Operating Income", "EBIT"),
    "pretax_income": ("Pretax Income",),
    "income_tax": ("Tax Provision",),
    "net_income": ("Net Income", "Net Income Common Stockholders"),
    "interest_expense": ("Interest Expense",),
    "depreciation": ("Reconciled Depreciation", "Depreciation And Amortization"),
    "eps_diluted": ("Diluted EPS",),
    "cfo": ("Operating Cash Flow",),
    "capex": ("Capital Expenditure",),
    "total_assets": ("Total Assets",),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "total_liabilities": ("Total Liabilities Net Minority Interest",),
    "total_equity": ("Stockholders Equity", "Common Stock Equity"),
    "cash": ("Cash And Cash Equivalents",),
    "receivables": ("Accounts Receivable", "Receivables"),
    "inventory": ("Inventory",),
    "ppe_net": ("Net PPE",),
    "long_term_debt": ("Long Term Debt",),
    "short_term_debt": ("Current Debt",),
    "retained_earnings": ("Retained Earnings",),
    "shares_outstanding": ("Ordinary Shares Number", "Share Issued"),
}
_ABSOLUTE = {"capex", "interest_expense", "depreciation"}
_FLOWS = {"revenue", "cogs", "gross_profit", "sga", "ebit", "pretax_income", "income_tax",
          "net_income", "interest_expense", "depreciation", "eps_diluted", "cfo", "capex"}

COUNTRY_ISO = {
    "united states": "US", "france": "FR", "germany": "DE", "netherlands": "NL",
    "united kingdom": "GB", "switzerland": "CH", "italy": "IT", "spain": "ES", "belgium": "BE",
    "sweden": "SE", "denmark": "DK", "norway": "NO", "finland": "FI", "ireland": "IE",
    "austria": "AT", "portugal": "PT", "luxembourg": "LU", "poland": "PL", "canada": "CA",
    "japan": "JP", "china": "CN", "hong kong": "HK", "taiwan": "TW", "south korea": "KR",
    "india": "IN", "brazil": "BR", "mexico": "MX", "israel": "IL", "australia": "AU",
    "singapore": "SG", "bermuda": "BM", "cayman islands": "KY", "jersey": "JE", "guernsey": "GG",
}


def _yf() -> Any:
    try:
        import yfinance
    except ImportError as exc:  # pragma: no cover - dépendance déclarée
        raise ProviderError("yfinance n'est pas installé") from exc
    return yfinance


def history_to_prices(hist: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Convertit un historique yfinance (``auto_adjust=False``) au schéma ``PRICES``."""
    if hist is None or hist.empty:
        return conform(pd.DataFrame(columns=PRICES.columns), PRICES)
    h = hist.copy()
    idx = pd.DatetimeIndex(h.index)
    h.index = idx.tz_localize(None) if idx.tz is not None else idx
    df = pd.DataFrame({
        "symbol": symbol,
        "date": h.index,
        "open": h.get("Open"),
        "high": h.get("High"),
        "low": h.get("Low"),
        "close": h.get("Close"),
        "adj_close": h.get("Adj Close", h.get("Close")),
        "volume": h.get("Volume"),
        "source": "yfinance",
        "ingested_at": datetime.now(UTC),
    })
    return conform(df, PRICES)


def statements_to_facts(statements: dict[str, pd.DataFrame], symbol: str,
                        lags: dict[str, int], currency: str | None) -> pd.DataFrame:
    """Convertit les états yfinance (colonnes = fins de période) en faits canoniques.

    Aucune date de publication n'est fournie : on applique un décalage conservateur et on
    marque ``lag_estimated=True``.
    """
    rows: list[dict[str, Any]] = []
    for freq, frame in statements.items():
        if frame is None or frame.empty:
            continue
        lag = lags["annual"] if freq == "annual" else lags["quarterly"]
        months = 12 if freq == "annual" else 3
        for concept, labels in _YF_FIELDS.items():
            label = next((lab for lab in labels if lab in frame.index), None)
            if label is None:
                continue
            for col, value in frame.loc[label].items():
                if pd.isna(value):
                    continue
                end = pd.Timestamp(str(col)).normalize()
                v = abs(float(value)) if concept in _ABSOLUTE else float(value)
                start = (end - pd.DateOffset(months=months) + pd.Timedelta(days=1)
                         if concept in _FLOWS else None)
                rows.append({
                    "symbol": symbol, "concept": concept, "value": v,
                    "period_start": start, "period_end": end,
                    "fiscal_period": ("FY" if freq == "annual" else "Q") if concept in _FLOWS else None,
                    "form": f"yfinance-{freq}", "unit": currency,
                    "available_at": estimated_available_at(end.date(), lag),
                    "lag_estimated": True, "source": "yfinance", "tag": label, "tag_rank": 0,
                })
    return conform(pd.DataFrame(rows, columns=FACTS.columns) if not rows else pd.DataFrame(rows),
                   FACTS)


class YFinanceProvider:
    name = "yfinance"

    def __init__(self, pause_seconds: float = 0.3,
                 publication_lags: dict[str, int] | None = None) -> None:
        self.pause = pause_seconds
        self.lags = publication_lags or {"annual": 120, "semiannual": 75, "quarterly": 60}

    def _ticker(self, symbol: str) -> Any:
        time.sleep(self.pause)
        return _yf().Ticker(to_yahoo(symbol))

    def get_daily_prices(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        hist = self._ticker(symbol).history(start=start, end=end + timedelta(days=1),
                                            auto_adjust=False, actions=False)
        return history_to_prices(hist, symbol)

    def get_facts(self, symbol: str) -> pd.DataFrame:
        t = self._ticker(symbol)
        info = self._safe_info(t)
        currency = info.get("financialCurrency") or info.get("currency")
        statements: dict[str, pd.DataFrame] = {}
        for freq, attrs in {"annual": ("income_stmt", "balance_sheet", "cashflow"),
                            "quarterly": ("quarterly_income_stmt", "quarterly_balance_sheet",
                                          "quarterly_cashflow")}.items():
            frames = [getattr(t, a, None) for a in attrs]
            frames = [f for f in frames if isinstance(f, pd.DataFrame) and not f.empty]
            if frames:
                statements[freq] = pd.concat(frames)
        return statements_to_facts(statements, symbol, self.lags, currency)

    @staticmethod
    def _safe_info(t: Any) -> dict[str, Any]:
        try:
            info = t.info
            return info if isinstance(info, dict) else {}
        except Exception as exc:  # yfinance lève des exceptions variées selon les versions
            log.warning("yfinance info indisponible", extra={"ctx": {"error": str(exc)[:200]}})
            return {}

    def get_security_info(self, symbol: str) -> dict[str, object]:
        info = self._safe_info(self._ticker(symbol))
        country_raw = str(info.get("country") or "").strip().lower()
        return {
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName") or symbol,
            "country": COUNTRY_ISO.get(country_raw) or default_country(symbol),
            "currency": info.get("currency") or default_currency(symbol),
            "sector": normalize_sector(info.get("sector")),
            "industry": info.get("industry"),
            "security_type": info.get("quoteType"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "source": self.name,
        }

    # -- instantanés archivés quotidiennement (historique PIT construit par nous) --------
    def consensus_snapshot(self, symbol: str) -> dict[str, object]:
        """Consensus BPA actuel et son évolution sur 7/30/60/90 jours (instantané)."""
        t = self._ticker(symbol)
        out: dict[str, object] = {"symbol": symbol}
        trend = getattr(t, "eps_trend", None)
        if isinstance(trend, pd.DataFrame) and not trend.empty:
            for period in ("0q", "+1q", "0y", "+1y"):
                if period in trend.index:
                    for col in trend.columns:
                        out[f"eps_trend_{period}_{col}"] = _num(trend.loc[period, col])
        revisions = getattr(t, "eps_revisions", None)
        if isinstance(revisions, pd.DataFrame) and not revisions.empty:
            for period in ("0q", "0y"):
                if period in revisions.index:
                    for col in revisions.columns:
                        out[f"eps_rev_{period}_{col}"] = _num(revisions.loc[period, col])
        return out

    def options_snapshot(self, symbol: str, spot: float | None = None) -> dict[str, object]:
        """Smirk de volatilité sur la première échéance > 10 jours (Xing, Zhang & Zhao 2010).

        smirk = IV du put OTM (strike le plus proche de 0,95 x spot) - IV du call ATM.
        """
        t = self._ticker(symbol)
        expiries = list(getattr(t, "options", []) or [])
        today = date.today()
        valid = [e for e in expiries if (date.fromisoformat(e) - today).days > 10]
        if not valid:
            return {"symbol": symbol}
        expiry = valid[0]
        chain = t.option_chain(expiry)
        if spot is None:
            hist = t.history(period="5d")
            spot = float(hist["Close"].iloc[-1]) if not hist.empty else None
        if not spot:
            return {"symbol": symbol, "expiry": expiry}
        calls, puts = chain.calls, chain.puts
        atm_call = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]
        otm_put = puts.iloc[(puts["strike"] - 0.95 * spot).abs().argsort()[:1]]
        iv_c = float(atm_call["impliedVolatility"].iloc[0]) if not atm_call.empty else float("nan")
        iv_p = float(otm_put["impliedVolatility"].iloc[0]) if not otm_put.empty else float("nan")
        return {"symbol": symbol, "expiry": expiry, "spot": spot, "iv_atm_call": iv_c,
                "iv_otm_put": iv_p, "smirk": iv_p - iv_c,
                "call_volume": float(calls["volume"].fillna(0).sum()),
                "put_volume": float(puts["volume"].fillna(0).sum())}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f
