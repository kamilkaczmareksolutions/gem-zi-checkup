"""Performance and risk metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq


# ── XIRR (money-weighted annualized return) ──────────────────────────

def build_cashflows(
    equity: pd.Series,
    initial_capital: float = 0.0,
    contribution_schedule: pd.Series | None = None,
) -> pd.Series:
    """Build investor cashflow series for XIRR calculation.

    Convention: negative = money going IN, positive = money coming OUT.
    Last entry is the terminal portfolio value (positive).
    """
    flows: dict = {}

    if initial_capital > 0:
        dt0 = equity.index[0]
        flows[dt0] = flows.get(dt0, 0.0) - initial_capital

    if contribution_schedule is not None:
        # Only include contributions that actually entered the backtest
        # (i.e. those starting from the first equity curve date)
        start_dt = equity.index[0]
        for dt, amt in contribution_schedule.items():
            if start_dt <= dt <= equity.index[-1]:
                flows[dt] = flows.get(dt, 0.0) - amt

    dt_end = equity.index[-1]
    flows[dt_end] = flows.get(dt_end, 0.0) + equity.iloc[-1]

    cf = pd.Series(flows).sort_index()
    return cf


def xirr(cashflows: pd.Series) -> float:
    """Compute annualized money-weighted return (XIRR) via Newton/Brent.

    cashflows: Series indexed by datetime, negative=outflow, positive=inflow.
    Returns annualized rate (e.g. 0.12 = 12%).
    """
    if cashflows.empty or len(cashflows) < 2:
        return 0.0

    dates = cashflows.index
    amounts = cashflows.values.astype(float)
    t0 = dates[0]
    day_fracs = np.array([(d - t0).days / 365.25 for d in dates])

    def npv(r):
        return np.sum(amounts / (1.0 + r) ** day_fracs)

    # bracketing: find sign change in [-0.5, 10.0]
    lo, hi = -0.5, 10.0
    try:
        npv_lo = npv(lo)
        npv_hi = npv(hi)
        if npv_lo * npv_hi > 0:
            # widen bracket
            for h in [50.0, 100.0, 500.0]:
                if npv(lo) * npv(h) < 0:
                    hi = h
                    break
            else:
                return 0.0
        rate = brentq(npv, lo, hi, xtol=1e-9, maxiter=500)
        return float(rate)
    except (ValueError, RuntimeError):
        return 0.0


# ── Classic metrics (still useful for Sharpe, Sortino, MaxDD) ────────

def cagr(equity: pd.Series) -> float:
    """Simple CAGR — only meaningful WITHOUT external cashflows."""
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1


def sharpe(equity: pd.Series, rf_annual: float = 0.0) -> float:
    rets = equity.pct_change().dropna()
    if rets.std() == 0 or len(rets) < 2:
        return 0.0
    monthly_rf = (1 + rf_annual) ** (1 / 12) - 1
    excess = rets - monthly_rf
    return excess.mean() / excess.std() * np.sqrt(12)


def sortino(equity: pd.Series, rf_annual: float = 0.0) -> float:
    rets = equity.pct_change().dropna()
    monthly_rf = (1 + rf_annual) ** (1 / 12) - 1
    excess = rets - monthly_rf
    downside = excess[excess < 0]
    if len(downside) < 1:
        return np.inf if excess.mean() > 0 else 0.0
    down_std = np.sqrt((downside ** 2).mean())
    if down_std == 0:
        return 0.0
    return excess.mean() / down_std * np.sqrt(12)


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return dd.min()


def calmar_xirr(xirr_val: float, mdd: float) -> float:
    if mdd == 0:
        return 0.0
    return xirr_val / abs(mdd)


def total_return(equity: pd.Series) -> float:
    if equity.iloc[0] == 0:
        return 0.0
    return equity.iloc[-1] / equity.iloc[0] - 1


def compute_all(
    equity: pd.Series,
    label: str = "",
    initial_capital: float = 0.0,
    contribution_schedule: pd.Series | None = None,
) -> dict:
    """Compute all metrics. When cashflows are provided, XIRR replaces CAGR."""
    mdd = max_drawdown(equity)

    has_cashflows = initial_capital > 0 or contribution_schedule is not None
    if has_cashflows:
        cf = build_cashflows(equity, initial_capital, contribution_schedule)
        xirr_val = xirr(cf)
    else:
        xirr_val = cagr(equity)

    return dict(
        label=label,
        total_return=total_return(equity),
        xirr=xirr_val,
        sharpe=sharpe(equity),
        sortino=sortino(equity),
        max_drawdown=mdd,
        calmar=calmar_xirr(xirr_val, mdd),
        final_value=equity.iloc[-1],
        months=len(equity),
    )
