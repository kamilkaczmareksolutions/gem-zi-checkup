"""Broker execution and cost models."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class BrokerModel:
    name: str
    fractional_shares: bool
    fx_cost_per_leg: float     # applied on sell AND buy (round-trip = 2x)
    commission_pct: float
    commission_min_pln: float
    slippage: float
    capital_gains_tax: float
    cash_interest_rate: float = 0.0

    # ── helpers ────────────────────────────────────────────────────────

    def rotation_cost_pct(self, trade_value_pln: float) -> float:
        """Total cost of one full rotation (sell old + buy new) as a fraction."""
        fx = 2.0 * self.fx_cost_per_leg
        slip = 2.0 * self.slippage
        comm = self._commission_frac(trade_value_pln) * 2.0
        return fx + slip + comm

    def sell_cost_pct(self, trade_value_pln: float) -> float:
        return self.fx_cost_per_leg + self.slippage + self._commission_frac(trade_value_pln)

    def buy_cost_pct(self, trade_value_pln: float) -> float:
        return self.fx_cost_per_leg + self.slippage + self._commission_frac(trade_value_pln)

    def shares_and_residual(self, capital: float, price_per_share: float) -> tuple[float, float]:
        """Return (shares, uninvested_cash).

        For fractional brokers shares can be non-integer and residual ~ 0.
        """
        if price_per_share <= 0:
            return 0.0, capital
        if self.fractional_shares:
            return capital / price_per_share, 0.0
        n = math.floor(capital / price_per_share)
        residual = capital - n * price_per_share
        return float(n), residual

    def tax_on_gain(self, gain: float) -> float:
        if gain <= 0:
            return 0.0
        return gain * self.capital_gains_tax

    # ── private ────────────────────────────────────────────────────────

    def _commission_frac(self, trade_value_pln: float) -> float:
        if self.commission_pct == 0.0 and self.commission_min_pln == 0.0:
            return 0.0
        comm = max(trade_value_pln * self.commission_pct, self.commission_min_pln)
        return comm / trade_value_pln if trade_value_pln > 0 else 0.0


def make_broker(cfg_broker: dict) -> BrokerModel:
    return BrokerModel(
        name=cfg_broker["name"],
        fractional_shares=cfg_broker["fractional_shares"],
        fx_cost_per_leg=cfg_broker["fx_cost_per_leg"],
        commission_pct=cfg_broker["commission_pct"],
        commission_min_pln=cfg_broker["commission_min_pln"],
        slippage=cfg_broker["slippage"],
        capital_gains_tax=cfg_broker["capital_gains_tax"],
        cash_interest_rate=cfg_broker.get("cash_interest_rate", 0.0),
    )
