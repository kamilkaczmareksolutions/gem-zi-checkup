from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.analysis import _resample_nth_bday, timing_luck_test
from src.backtest import run_gem
from src.broker import BrokerModel


def _prices() -> pd.DataFrame:
    idx = pd.bdate_range("2016-01-04", "2020-12-31")
    month_pos = idx.to_series().groupby([idx.year, idx.month]).cumcount()
    month_len = idx.to_series().groupby([idx.year, idx.month]).transform("size")
    frac = (month_pos / month_len.clip(lower=1)).to_numpy()
    drift = np.exp(0.00035 * np.arange(len(idx)))
    risk = 100.0 * drift * (1.15 - 0.30 * frac)
    return pd.DataFrame(
        {"RISK": risk, "SAFE": np.full(len(idx), 100.0)},
        index=idx,
    )


def _broker() -> BrokerModel:
    return BrokerModel(
        name="flat",
        fractional_shares=True,
        fx_cost_per_leg=0.0,
        commission_pct=0.0,
        commission_min_pln=0.0,
        slippage=0.0,
        capital_gains_tax=0.0,
    )


def _investor_flows(equity: pd.Series, deposit: float) -> pd.Series:
    start = equity.index[0]
    end = equity.index[-1]
    flows: dict = {}
    for dt in equity.index:
        if start <= dt <= end:
            flows[dt] = -deposit
    flows[end] = flows.get(end, 0.0) + float(equity.iloc[-1])
    return pd.Series(flows).sort_index()


def _irr(cashflows: pd.Series) -> float:
    dates = list(cashflows.index)
    amounts = [float(v) for v in cashflows.to_numpy()]
    origin = dates[0]
    years = [(d - origin).days / 365.25 for d in dates]

    def npv(rate: float) -> float:
        return sum(amount / (1.0 + rate) ** year for amount, year in zip(amounts, years))

    lo, hi = -0.9, 5.0
    if npv(lo) * npv(hi) > 0:
        raise AssertionError("independent IRR has no sign change")
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if npv(lo) * npv(mid) <= 0.0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def _oracle(prices: pd.DataFrame, broker: BrokerModel, offset: int, deposit: float) -> float:
    monthly = _resample_nth_bday(prices, offset)
    schedule = pd.Series(deposit, index=monthly.index)
    result = run_gem(
        monthly,
        broker,
        ["RISK"],
        ["SAFE"],
        0.0,
        deadband=0.0,
        contribution_schedule=schedule,
    )
    return _irr(_investor_flows(result.equity, deposit))


class TimingLuckXirrTest(unittest.TestCase):
    def test_missing_cpi_offsets_differ_from_zero(self) -> None:
        deposit = 1000.0
        offsets = [1, 10, 20]
        prices = _prices()
        broker = _broker()
        table = timing_luck_test(
            prices,
            broker,
            ["RISK"],
            ["SAFE"],
            0.0,
            0.0,
            offsets,
            inflation_rates={},
            base_contribution=deposit,
        )
        self.assertEqual(list(table["offset"]), offsets)
        got = []
        for offset in offsets:
            row = table.loc[table["offset"] == offset].iloc[0]
            expected = _oracle(prices, broker, offset, deposit)
            actual = float(row["xirr"])
            self.assertAlmostEqual(
                actual,
                expected,
                delta=1e-4,
                msg=f"offset {offset}: timing luck XIRR {actual:.6%} vs independent {expected:.6%}",
            )
            self.assertGreater(float(row["final_value"]), 0.0)
            got.append(actual)
        self.assertGreater(max(got) - min(got), 1e-3)


if __name__ == "__main__":
    unittest.main()
