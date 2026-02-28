"""Performance and risk metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cagr(equity: pd.Series) -> float:
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


def calmar(equity: pd.Series) -> float:
    mdd = max_drawdown(equity)
    if mdd == 0:
        return 0.0
    return cagr(equity) / abs(mdd)


def total_return(equity: pd.Series) -> float:
    if equity.iloc[0] == 0:
        return 0.0
    return equity.iloc[-1] / equity.iloc[0] - 1


def compute_all(equity: pd.Series, label: str = "") -> dict:
    return dict(
        label=label,
        total_return=total_return(equity),
        cagr=cagr(equity),
        sharpe=sharpe(equity),
        sortino=sortino(equity),
        max_drawdown=max_drawdown(equity),
        calmar=calmar(equity),
        final_value=equity.iloc[-1],
        months=len(equity),
    )
