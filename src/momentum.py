"""Momentum signal computation for GEM strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_momentum(
    prices: pd.DataFrame,
    lookback: int = 13,
    skip: int = 1,
) -> pd.DataFrame:
    """Compute 12-month momentum with skip-month: return from t-13 to t-1.

    The measurement window spans a full 12 months of returns, starting
    13 months ago and ending 1 month ago (the most recent month is
    excluded to avoid short-term reversal noise).

    ``momentum_i = price[t - skip] / price[t - lookback] - 1``

    Returns DataFrame aligned to *prices* index (first ``lookback`` rows are NaN).
    """
    numerator = prices.shift(skip)
    denominator = prices.shift(lookback)
    mom = numerator / denominator - 1.0
    return mom


def select_best(
    momentum: pd.DataFrame,
    risky: list[str],
    safe: list[str],
) -> pd.DataFrame:
    """For each row, determine the target ETF using dual-momentum logic.

    Returns DataFrame with columns: ``target``, ``mom_target``, ``mom_current_best_risky``,
    ``is_risk_off``.
    """
    avail_risky = [c for c in risky if c in momentum.columns]
    avail_safe = [c for c in safe if c in momentum.columns]

    records = []
    for dt, row in momentum.iterrows():
        risky_mom = row[avail_risky].dropna()
        safe_mom = row[avail_safe].dropna()

        if risky_mom.empty and safe_mom.empty:
            records.append(dict(date=dt, target=None, mom_target=np.nan,
                                mom_best_risky=np.nan, is_risk_off=True))
            continue

        best_risky = risky_mom.idxmax() if not risky_mom.empty else None
        best_risky_val = risky_mom.max() if not risky_mom.empty else -np.inf

        if best_risky_val < 0 or best_risky is None:
            # absolute momentum filter: risk-off
            if safe_mom.empty:
                target = best_risky
                target_val = best_risky_val
            else:
                target = safe_mom.idxmax()
                target_val = safe_mom.max()
            records.append(dict(date=dt, target=target, mom_target=target_val,
                                mom_best_risky=best_risky_val, is_risk_off=True))
        else:
            records.append(dict(date=dt, target=best_risky, mom_target=best_risky_val,
                                mom_best_risky=best_risky_val, is_risk_off=False))

    return pd.DataFrame(records).set_index("date")
