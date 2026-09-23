"""Univers d'investissement : univers « live » par paliers et univers de backtest par règles.

* **Live** (rapport quotidien) : réunion des indices du palier 1, filtrée par la liquidité,
  avec des drapeaux d'exécution (PEA, TTF, SRD).
* **Backtest** : à chaque date, top N par capitalisation dans une région, avec filtres de
  prix et de volume, calculé sur une base de prix **incluant les délistés** : aucune
  dépendance à une composition d'indice actuelle (pas de biais du survivant par construction).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scanner.core.config import Settings
from scanner.core.reference import region_of
from scanner.data.pit import PitView

UNIVERSE_COLUMNS = [
    "symbol",
    "tier",
    "indices",
    "region",
    "country",
    "currency",
    "sector",
    "passes_liquidity",
    "liquidity_note",
    "adv60_usd",
    "market_cap_usd",
    "pea_eligible",
    "ttf_applicable",
    "srd_eligible",
]

EXCLUDED_TYPES = {"ETF", "FUND", "MUTUALFUND", "PREFERRED", "PREFERRED STOCK", "WARRANT", "SPAC"}


def load_override(path: Path) -> set[str] | None:
    """Liste de symboles d'un fichier CSV optionnel (ex. valeurs éligibles au SRD).

    ``None`` si le fichier n'existe pas (information inconnue), ce qui est différent
    d'une liste officielle vide.
    """
    if not path.exists():
        return None
    df = pd.read_csv(path, comment="#")
    return {str(s).strip() for s in df.get("symbol", pd.Series(dtype=str)).dropna()}


def live_universe(
    constituents: dict[str, list[str]],
    securities: pd.DataFrame,
    quant: pd.DataFrame,
    fundamentals: pd.DataFrame,
    settings: Settings,
    fx_to_usd: dict[str, float],
    srd_list: set[str] | None = None,
    ttf_list: set[str] | None = None,
) -> pd.DataFrame:
    """Univers du jour avec filtres de liquidité et drapeaux d'exécution.

    ``quant`` doit contenir ``adv60_usd`` et ``last_close_usd`` ; ``fundamentals`` peut
    contenir ``desc_market_cap`` (en devise des comptes, vérifiée cohérente).
    """
    liq = settings.universe.liquidity
    members: dict[str, list[str]] = {}
    for index_id, syms in constituents.items():
        for s in syms:
            members.setdefault(s, []).append(index_id)
    symbols = sorted(members)
    sec = securities.set_index("symbol").reindex(symbols)
    q = quant.reindex(symbols)
    f = fundamentals.reindex(symbols) if not fundamentals.empty else pd.DataFrame(index=symbols)

    currency = sec["currency"].astype("string")
    fx = currency.map(lambda c: fx_to_usd.get(str(c), np.nan)).astype(float)
    mcap_local = (
        f["desc_market_cap"] if "desc_market_cap" in f.columns else pd.Series(np.nan, index=symbols)
    )
    mcap_usd = mcap_local.astype(float) * fx
    adv = q["adv60_usd"] if "adv60_usd" in q.columns else pd.Series(np.nan, index=symbols)
    price = (
        q["last_close_usd"] if "last_close_usd" in q.columns else pd.Series(np.nan, index=symbols)
    )

    notes = []
    passes = []
    for s in symbols:
        reasons = []
        stype = str(sec.at[s, "security_type"]).upper() if "security_type" in sec.columns else ""
        if stype in EXCLUDED_TYPES:
            reasons.append(f"type exclu ({stype})")
        if pd.isna(adv.get(s)):
            reasons.append("volume inconnu")
        elif adv[s] < liq.min_adv_usd:
            reasons.append(f"volume {adv[s] / 1e6:.2f} M$ < {liq.min_adv_usd / 1e6:.1f} M$")
        if pd.notna(price.get(s)) and price[s] < liq.min_price_usd:
            reasons.append(f"prix {price[s]:.2f} $ < {liq.min_price_usd} $")
        if pd.notna(mcap_usd.get(s)) and mcap_usd[s] < liq.min_market_cap_usd:
            reasons.append("capitalisation insuffisante")
        passes.append(not reasons)
        notes.append(
            "; ".join(reasons)
            if reasons
            else ("capitalisation inconnue" if pd.isna(mcap_usd.get(s)) else "")
        )

    country = sec["country"].astype("string")
    eur_rate = fx_to_usd.get("EUR", np.nan)
    mcap_eur = mcap_usd / eur_rate if eur_rate else pd.Series(np.nan, index=symbols)
    ttf = (country == "FR") & (mcap_eur >= settings.universe.ttf_min_market_cap_eur)
    if ttf_list is not None:  # liste officielle chargée (même vide) : elle fait foi
        ttf = pd.Series([s in ttf_list for s in symbols], index=symbols)
    out = pd.DataFrame(
        {
            "symbol": symbols,
            "tier": 1,
            "indices": [",".join(sorted(members[s])) for s in symbols],
            "region": [region_of(c if isinstance(c, str) else None) for c in country],
            "country": country.to_numpy(),
            "currency": currency.to_numpy(),
            "sector": sec["sector"].astype("string").to_numpy(),
            "passes_liquidity": passes,
            "liquidity_note": notes,
            "adv60_usd": adv.to_numpy(),
            "market_cap_usd": mcap_usd.to_numpy(),
            "pea_eligible": country.isin(settings.universe.pea_countries).fillna(False).to_numpy(),
            "ttf_applicable": ttf.fillna(False).to_numpy(),
            "srd_eligible": [(s in srd_list) if srd_list is not None else None for s in symbols],
        }
    )
    return out[UNIVERSE_COLUMNS]


def rule_based_universe(
    view: PitView,
    region: str,
    top_n: int,
    min_price_usd: float,
    min_adv_usd: float,
    fx_to_usd: dict[str, float],
    adv_window: int = 60,
) -> list[str]:
    """Univers de backtest à la date ``view.as_of`` : top N par capitalisation (repli : volume).

    La capitalisation utilise le nombre d'actions publié **à la date** (faits PIT) et le cours
    brut ; si le nombre d'actions est inconnu, le titre est classé par volume.
    """
    sec = view.securities()
    if sec.empty:
        return []
    sec = sec[[region_of(c if isinstance(c, str) else None) == region for c in sec["country"]]]
    syms = [s for s in view.listed_symbols() if s in set(sec["symbol"])]
    if not syms:
        return []
    close = view.panel("close", adv_window).reindex(columns=syms)
    volume = view.panel("volume", adv_window).reindex(columns=syms)
    ccy = sec.set_index("symbol")["currency"].reindex(syms)
    fx = ccy.map(lambda c: fx_to_usd.get(str(c), np.nan)).astype(float)
    last = close.ffill().iloc[-1] * fx
    adv = (close * volume).median() * fx
    recent = close.iloc[-5:].notna().any()  # encore coté récemment
    ok = (last >= min_price_usd) & (adv >= min_adv_usd) & recent

    facts = view.facts()
    shares = pd.Series(np.nan, index=syms)
    if not facts.empty:
        sh = facts[(facts["concept"] == "shares_outstanding") & facts["symbol"].isin(syms)]
        if not sh.empty:
            sh = sh.sort_values(["period_end", "available_at"]).groupby("symbol").tail(1)
            shares = sh.set_index("symbol")["value"].reindex(syms)
    mcap = last * shares
    # Sans nombre d'actions, capitalisation approchée par volume / rotation typique (0,4 %/jour).
    rank_key = mcap.fillna(adv / 0.004)
    eligible = rank_key[ok].sort_values(ascending=False)
    return sorted(eligible.index[:top_n])
