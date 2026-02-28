"""Core GEM backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .broker import BrokerModel
from .momentum import compute_momentum, select_best


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[dict] = field(default_factory=list)
    holdings: pd.Series = field(default_factory=lambda: pd.Series(dtype=str))
    total_costs: float = 0.0
    total_taxes: float = 0.0
    num_rotations: int = 0


def run_gem(
    prices: pd.DataFrame,
    broker: BrokerModel,
    risky: list[str],
    safe: list[str],
    initial_capital: float,
    deadband: float = 0.0,
    lookback: int = 12,
    skip: int = 1,
    monthly_contribution: float = 0.0,
    rebalance_day_offset: int = 0,
) -> BacktestResult:
    """Run a single GEM backtest.

    Parameters
    ----------
    prices : month-end adjusted close DataFrame
    broker : execution / cost model
    risky, safe : ticker lists
    initial_capital : starting value in original currency units
    deadband : minimum momentum spread required for rotation
    rebalance_day_offset : ignored in month-end mode (reserved for timing-luck)
    """
    all_tickers = [t for t in risky + safe if t in prices.columns]
    if not all_tickers:
        raise ValueError("No valid tickers in prices")

    mom = compute_momentum(prices[all_tickers], lookback=lookback, skip=skip)
    signals = select_best(mom, risky, safe)

    valid_idx = signals.dropna(subset=["target"]).index
    start_idx = valid_idx[0]
    ts_range = prices.loc[start_idx:].index

    capital = initial_capital
    cash = 0.0
    current_holding: str | None = None
    current_shares: float = 0.0
    cost_basis: float = 0.0
    total_costs = 0.0
    total_taxes = 0.0
    num_rotations = 0

    equity_vals: list[float] = []
    equity_dates: list = []
    trades: list[dict] = []
    holding_series: list[str] = []

    for dt in ts_range:
        capital += monthly_contribution

        if dt not in signals.index:
            # no signal this month, hold position
            if current_holding and current_holding in prices.columns:
                port_val = current_shares * prices.loc[dt, current_holding] + cash
            else:
                port_val = capital + cash
            equity_vals.append(port_val)
            equity_dates.append(dt)
            holding_series.append(current_holding or "CASH")
            continue

        sig = signals.loc[dt]
        target = sig["target"]

        if target is None or (target not in prices.columns):
            if current_holding and current_holding in prices.columns:
                port_val = current_shares * prices.loc[dt, current_holding] + cash
            else:
                port_val = capital + cash
            equity_vals.append(port_val)
            equity_dates.append(dt)
            holding_series.append(current_holding or "CASH")
            continue

        if current_holding is None:
            # first allocation
            price = prices.loc[dt, target]
            buy_cost_frac = broker.buy_cost_pct(capital)
            investable = capital * (1.0 - buy_cost_frac)
            cost_paid = capital * buy_cost_frac
            total_costs += cost_paid

            shares, residual = broker.shares_and_residual(investable, price)
            current_holding = target
            current_shares = shares
            cash = residual
            cost_basis = shares * price
            capital = 0.0

            trades.append(dict(date=dt, action="BUY", ticker=target,
                               shares=shares, price=price, cost=cost_paid))

        elif target != current_holding:
            # potential rotation — check deadband
            current_mom = mom.loc[dt, current_holding] if current_holding in mom.columns else -np.inf
            target_mom = sig["mom_target"]

            spread = target_mom - current_mom if np.isfinite(current_mom) else np.inf

            # absolute momentum switches (risk-off/on transitions) bypass deadband
            was_risk_off = current_holding in safe
            going_risk_off = sig["is_risk_off"]
            regime_change = was_risk_off != going_risk_off

            if not regime_change and spread < deadband:
                # insufficient spread -> hold
                port_val = current_shares * prices.loc[dt, current_holding] + cash
                equity_vals.append(port_val)
                equity_dates.append(dt)
                holding_series.append(current_holding)
                continue

            # execute rotation
            sell_price = prices.loc[dt, current_holding]
            sell_proceeds_gross = current_shares * sell_price
            sell_cost_frac = broker.sell_cost_pct(sell_proceeds_gross)
            sell_cost = sell_proceeds_gross * sell_cost_frac
            total_costs += sell_cost

            gain = sell_proceeds_gross - cost_basis
            tax = broker.tax_on_gain(gain)
            total_taxes += tax

            net_from_sell = sell_proceeds_gross - sell_cost - tax

            trades.append(dict(date=dt, action="SELL", ticker=current_holding,
                               shares=current_shares, price=sell_price,
                               cost=sell_cost, tax=tax, gain=gain))

            # buy new
            buy_capital = net_from_sell + cash + monthly_contribution
            monthly_contribution = 0.0  # already counted
            buy_price = prices.loc[dt, target]
            buy_cost_frac = broker.buy_cost_pct(buy_capital)
            investable = buy_capital * (1.0 - buy_cost_frac)
            buy_cost = buy_capital * buy_cost_frac
            total_costs += buy_cost

            shares, residual = broker.shares_and_residual(investable, buy_price)
            current_holding = target
            current_shares = shares
            cash = residual
            cost_basis = shares * buy_price
            capital = 0.0
            num_rotations += 1

            trades.append(dict(date=dt, action="BUY", ticker=target,
                               shares=shares, price=buy_price, cost=buy_cost))
        else:
            # same holding — optionally add new contributions
            if monthly_contribution > 0 and capital > 0:
                price = prices.loc[dt, current_holding]
                add_cost_frac = broker.buy_cost_pct(capital)
                investable = capital * (1.0 - add_cost_frac)
                cost_paid = capital * add_cost_frac
                total_costs += cost_paid
                new_shares, new_res = broker.shares_and_residual(investable, price)
                current_shares += new_shares
                cash += new_res
                cost_basis += new_shares * price
                capital = 0.0

        # record portfolio value
        if current_holding and current_holding in prices.columns:
            port_val = current_shares * prices.loc[dt, current_holding] + cash
        else:
            port_val = cash
        equity_vals.append(port_val)
        equity_dates.append(dt)
        holding_series.append(current_holding or "CASH")

    return BacktestResult(
        equity=pd.Series(equity_vals, index=pd.DatetimeIndex(equity_dates), name="equity"),
        trades=trades,
        holdings=pd.Series(holding_series, index=pd.DatetimeIndex(equity_dates), name="holding"),
        total_costs=total_costs,
        total_taxes=total_taxes,
        num_rotations=num_rotations,
    )
