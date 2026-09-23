"""Modèle de coûts de transaction (paramètres dans ``config/costs.yaml``).

Coût d'une transaction, en fraction du montant échangé :

* courtage selon la région ;
* demi-spread selon la tranche de liquidité (volume quotidien médian en USD) ;
* taxes à l'**achat** selon le pays (TTF française 0,4 % si ``ttf_applicable``, ITF
  italienne, taxe espagnole, stamp duty britannique).
"""

from __future__ import annotations

import pandas as pd

from scanner.core.config import Costs


class CostModel:
    def __init__(
        self,
        costs: Costs,
        region: pd.Series,
        country: pd.Series,
        adv_usd: pd.Series,
        ttf_applicable: pd.Series | None = None,
    ) -> None:
        self.costs = costs
        idx = region.index
        commission = region.map(
            lambda r: costs.commission_bps.get(str(r), costs.commission_bps.get("US", 0.0))
        )
        spread = adv_usd.reindex(idx).map(self._half_spread)
        self._sell_bps = (commission.astype(float) + spread.astype(float)).fillna(
            max(b.bps for b in costs.half_spread_bps) + max(costs.commission_bps.values())
        )
        taxes = (
            country.reindex(idx).map(lambda c: costs.buy_taxes_bps.get(str(c), 0.0)).astype(float)
        )
        if ttf_applicable is not None:
            is_fr = country.reindex(idx) == "FR"
            taxes = taxes.where(
                ~is_fr | ttf_applicable.reindex(idx).fillna(False).astype(bool), 0.0
            )
        self._buy_bps = self._sell_bps + taxes

    def _half_spread(self, adv: float) -> float:
        if pd.isna(adv):
            return float(self.costs.half_spread_bps[-1].bps)
        for bucket in self.costs.half_spread_bps:  # triées par seuil décroissant
            if adv >= bucket.min_adv_usd:
                return float(bucket.bps)
        return float(self.costs.half_spread_bps[-1].bps)

    def rebalance_cost(self, delta_weights: pd.Series) -> float:
        """Coût (fraction du capital) d'un changement de poids ``delta_weights``."""
        buys = delta_weights.clip(lower=0)
        sells = (-delta_weights).clip(lower=0)
        buy_rate = self._buy_bps.reindex(delta_weights.index).fillna(self._buy_bps.max()) / 1e4
        sell_rate = self._sell_bps.reindex(delta_weights.index).fillna(self._sell_bps.max()) / 1e4
        return float((buys * buy_rate).sum() + (sells * sell_rate).sum())

    @property
    def borrow_daily(self) -> float:
        return self.costs.short_borrow_bps_per_year / 1e4 / 252
