"""High-level analysis: deadband sweeps, universe expansion, walk-forward, timing luck."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import run_gem, BacktestResult
from .broker import BrokerModel
from .metrics import compute_all


# ── Deadband sweep ──────────────────────────────────────────────────

def sweep_deadbands(
    prices: pd.DataFrame,
    broker: BrokerModel,
    risky: list[str],
    safe: list[str],
    initial_capital: float,
    deadbands: list[float],
    contribution_schedule: pd.Series | None = None,
) -> pd.DataFrame:
    """Run GEM for a range of deadband values, return metrics table."""
    rows = []
    for db in deadbands:
        res = run_gem(prices, broker, risky, safe, initial_capital, deadband=db,
                      contribution_schedule=contribution_schedule)
        m = compute_all(res.equity, label=f"db={db:.3f}",
                        initial_capital=initial_capital,
                        contribution_schedule=contribution_schedule)
        m["deadband"] = db
        m["rotations"] = res.num_rotations
        m["total_costs"] = res.total_costs
        m["total_taxes"] = res.total_taxes
        rows.append(m)
    return pd.DataFrame(rows)


# ── Dynamic deadband ────────────────────────────────────────────────

def run_gem_dynamic_deadband(
    prices: pd.DataFrame,
    broker: BrokerModel,
    risky: list[str],
    safe: list[str],
    initial_capital: float,
    base: float,
    k: float,
    vol_window: int = 6,
    contribution_schedule: pd.Series | None = None,
) -> BacktestResult:
    """Run GEM with volatility-scaled deadband: delta = base + k * sigma(vol_window)."""
    from .momentum import compute_momentum, select_best

    all_tickers = [t for t in risky + safe if t in prices.columns]
    mom = compute_momentum(prices[all_tickers], lookback=13, skip=1)
    rets = prices[all_tickers].pct_change()
    rolling_vol = rets.rolling(vol_window).std().mean(axis=1)

    signals = select_best(mom, risky, safe)
    valid_idx = signals.dropna(subset=["target"]).index
    start_idx = valid_idx[0]
    ts_range = prices.loc[start_idx:].index

    deposit_cost_init = initial_capital * broker.deposit_fx_cost
    capital = initial_capital - deposit_cost_init
    cash = 0.0
    current_holding = None
    current_shares = 0.0
    cost_basis = 0.0
    total_costs = deposit_cost_init
    total_taxes = 0.0
    num_rotations = 0

    equity_vals = []
    equity_dates = []
    trades = []
    holding_series = []

    contrib_lookup = contribution_schedule.to_dict() if contribution_schedule is not None else None

    for dt in ts_range:
        contrib = contrib_lookup[dt] if contrib_lookup and dt in contrib_lookup else 0.0
        if contrib > 0:
            dep_cost = contrib * broker.deposit_fx_cost
            capital += contrib - dep_cost
            total_costs += dep_cost

        if dt not in signals.index:
            if current_holding and current_holding in prices.columns:
                pv = current_shares * prices.loc[dt, current_holding] + cash + capital
            else:
                pv = capital + cash
            equity_vals.append(pv)
            equity_dates.append(dt)
            holding_series.append(current_holding or "CASH")
            continue

        sig = signals.loc[dt]
        target = sig["target"]
        if target is None or target not in prices.columns:
            if current_holding and current_holding in prices.columns:
                pv = current_shares * prices.loc[dt, current_holding] + cash + capital
            else:
                pv = capital + cash
            equity_vals.append(pv)
            equity_dates.append(dt)
            holding_series.append(current_holding or "CASH")
            continue

        # dynamic deadband
        vol_val = rolling_vol.get(dt, 0.0)
        if np.isnan(vol_val):
            vol_val = 0.0
        dyn_db = base + k * vol_val

        if current_holding is None:
            price = prices.loc[dt, target]
            bcf = broker.buy_cost_pct(capital)
            investable = capital * (1 - bcf)
            cost_paid = capital * bcf
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
            current_mom = mom.loc[dt, current_holding] if current_holding in mom.columns else -np.inf
            target_mom = sig["mom_target"]
            spread = target_mom - current_mom if np.isfinite(current_mom) else np.inf
            was_safe = current_holding in safe
            going_safe = sig["is_risk_off"]
            regime_change = was_safe != going_safe

            if not regime_change and spread < dyn_db:
                if capital > 0:
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
                pv = current_shares * prices.loc[dt, current_holding] + cash
                equity_vals.append(pv)
                equity_dates.append(dt)
                holding_series.append(current_holding)
                continue

            sp = prices.loc[dt, current_holding]
            gross = current_shares * sp
            scf = broker.sell_cost_pct(gross)
            sc = gross * scf
            total_costs += sc
            gain = gross - cost_basis
            tax = broker.tax_on_gain(gain)
            total_taxes += tax
            net = gross - sc - tax
            trades.append(dict(date=dt, action="SELL", ticker=current_holding,
                               shares=current_shares, price=sp, cost=sc, tax=tax))

            bp = prices.loc[dt, target]
            buy_cap = net + cash + capital
            capital = 0.0
            bcf = broker.buy_cost_pct(buy_cap)
            investable = buy_cap * (1 - bcf)
            bc = buy_cap * bcf
            total_costs += bc
            shares, residual = broker.shares_and_residual(investable, bp)
            current_holding = target
            current_shares = shares
            cash = residual
            cost_basis = shares * bp
            num_rotations += 1
            trades.append(dict(date=dt, action="BUY", ticker=target,
                               shares=shares, price=bp, cost=bc))
        else:
            # same holding — invest any accumulated capital
            if capital > 0:
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

        if current_holding and current_holding in prices.columns:
            pv = current_shares * prices.loc[dt, current_holding] + cash
        else:
            pv = cash
        equity_vals.append(pv)
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


# ── Universe comparison ─────────────────────────────────────────────

def compare_universes(
    prices: pd.DataFrame,
    broker: BrokerModel,
    universes: dict[str, dict],
    initial_capital: float,
    deadband: float = 0.03,
    contribution_schedule: pd.Series | None = None,
) -> pd.DataFrame:
    """Compare universes. Each runs over its own available data window.

    An additional 'common_window' variant trims all universes to the
    latest common start date so CAGR comparisons are fair.
    """
    rows = []
    equity_curves: dict[str, pd.Series] = {}

    for name, univ in universes.items():
        risky = [t for t in univ["risky"] if t in prices.columns]
        safe = [t for t in univ["safe"] if t in prices.columns]
        if not risky or not safe:
            continue
        res = run_gem(prices, broker, risky, safe, initial_capital, deadband=deadband,
                      contribution_schedule=contribution_schedule)
        m = compute_all(res.equity, label=name,
                        initial_capital=initial_capital,
                        contribution_schedule=contribution_schedule)
        m["universe"] = name
        m["n_etfs"] = len(risky) + len(safe)
        m["rotations"] = res.num_rotations
        m["total_costs"] = res.total_costs
        m["start_date"] = str(res.equity.index[0].date()) if len(res.equity) > 0 else ""
        m["end_date"] = str(res.equity.index[-1].date()) if len(res.equity) > 0 else ""
        rows.append(m)
        equity_curves[name] = res.equity

    # Common-window comparison skipped when using DCA — trimming an equity curve
    # with external cashflows and re-computing metrics would be misleading.

    return pd.DataFrame(rows)


# ── Walk-forward ────────────────────────────────────────────────────

def walk_forward(
    prices: pd.DataFrame,
    broker: BrokerModel,
    risky: list[str],
    safe: list[str],
    initial_capital: float,
    deadbands: list[float],
    train_months: int = 60,
    test_months: int = 12,
    step_months: int = 12,
    contribution_schedule: pd.Series | None = None,
) -> dict:
    """Rolling-window walk-forward: select best deadband on train, evaluate on test.

    Uses date-based slicing so that equity curves align correctly even when
    the backtest starts later than the price window (due to momentum lookback).
    """
    from .metrics import sharpe as calc_sharpe

    dates = prices.index
    total_months = len(dates)

    oos_equities: list[pd.Series] = []
    oos_selected_dbs: list[float] = []
    fold_records = []

    start = 0
    fold = 0
    while start + train_months + test_months <= total_months:
        train_end = start + train_months
        test_end = min(train_end + test_months, total_months)

        train_prices = prices.iloc[start:train_end]
        # for the test run, include history from start so momentum has lookback
        full_prices = prices.iloc[start:test_end]

        train_start_date = dates[start]
        train_end_date = dates[train_end - 1]
        test_start_date = dates[train_end]
        test_end_date = dates[test_end - 1]


        # select best deadband on training window
        best_db = deadbands[0] if deadbands else 0.0
        best_sharpe = -np.inf
        for db in deadbands:
            try:
                res = run_gem(train_prices, broker, risky, safe,
                              initial_capital, deadband=db,
                              contribution_schedule=contribution_schedule)
                if len(res.equity) < 3:
                    continue
                s = calc_sharpe(res.equity)
                if s > best_sharpe:
                    best_sharpe = s
                    best_db = db
            except Exception:
                continue

                # evaluate on full window (train+test) with selected deadband
        try:
            full_res = run_gem(full_prices, broker, risky, safe,
                               initial_capital, deadband=best_db,
                               contribution_schedule=contribution_schedule)
            test_equity = full_res.equity.loc[test_start_date:test_end_date]

            if len(test_equity) > 1 and test_equity.iloc[0] > 0:
                oos_equities.append(test_equity)
                oos_selected_dbs.append(best_db)

                oos_ret_from_full = test_equity.iloc[-1] / test_equity.iloc[0] - 1

                # FIX: OOS return is measured from the same OOS slice used for stitched equity.
                # This keeps fold metrics and stitched curve methodologically consistent.
                oos_ret = oos_ret_from_full

                fold_records.append(dict(
                    fold=fold,
                    train_start=train_start_date,
                    train_end=train_end_date,
                    test_start=test_start_date,
                    test_end=test_end_date,
                    selected_db=best_db,
                    oos_return=oos_ret,
                ))
        except Exception as e:
            print(f"  Fold {fold} ERROR: {e}")

        start += step_months
        fold += 1

    # stitch OOS equity: chain returns so that each fold starts where the
    # previous one ended
    if oos_equities:
        parts = []
        running_value = oos_equities[0].iloc[0] if len(oos_equities[0]) > 0 else 1.0
        for eq in oos_equities:
            if len(eq) < 2:
                continue
            rets = eq.pct_change().fillna(0)
            scaled = pd.Series(index=eq.index, dtype=float)
            val = running_value
            for i, (dt, r) in enumerate(rets.items()):
                if i == 0:
                    val = running_value
                else:
                    val = val * (1 + r)
                scaled[dt] = val
            running_value = val
            parts.append(scaled)
        stitched = pd.concat(parts) if parts else pd.Series(dtype=float)
        if not stitched.empty:
            stitched = stitched[~stitched.index.duplicated(keep="last")]
    else:
        stitched = pd.Series(dtype=float)

    return dict(
        oos_equity=stitched,
        folds=pd.DataFrame(fold_records),
        selected_deadbands=oos_selected_dbs,
    )


# ── Timing luck ─────────────────────────────────────────────────────

def timing_luck_test(
    daily_prices: pd.DataFrame,
    broker: BrokerModel,
    risky: list[str],
    safe: list[str],
    initial_capital: float,
    deadband: float,
    offsets: list[int],
    contribution_schedule: pd.Series | None = None,
    inflation_rates: dict[int, float] | None = None,
    base_contribution: float = 0.0,
) -> pd.DataFrame:
    """Test sensitivity to rebalancing day within each month.

    *offsets*: list of business-day offsets from month start (0 = first day).
    We resample daily prices to the Nth business day of each month.
    When contribution_schedule is provided, a new schedule is built for
    the resampled dates using the same base amount and inflation rates.
    """
    from .data import build_contribution_schedule

    rows = []
    for offset in offsets:
        try:
            monthly = _resample_nth_bday(daily_prices, offset)
            if monthly.empty or len(monthly) < 15:
                continue
            # Rebuild contribution schedule for resampled dates
            sched = None
            if base_contribution > 0 and inflation_rates:
                sched = build_contribution_schedule(base_contribution, monthly.index, inflation_rates)
            res = run_gem(monthly, broker, risky, safe, initial_capital, deadband=deadband,
                          contribution_schedule=sched)
            m = compute_all(res.equity, label=f"day_offset={offset}",
                            initial_capital=initial_capital,
                            contribution_schedule=sched)
            m["offset"] = offset
            m["rotations"] = res.num_rotations
            rows.append(m)
        except Exception:
            continue
    return pd.DataFrame(rows)


def _resample_nth_bday(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Pick the Nth business day of each month from a daily DataFrame.

    If a month has fewer than n+1 business days, the last business day
    of that month is selected instead.
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    groups = df.groupby([df.index.year, df.index.month])
    selected = []
    for _, grp in groups:
        if not grp.empty:
            idx = min(n, len(grp) - 1)
            selected.append(grp.iloc[idx])
    if not selected:
        return pd.DataFrame()
    return pd.DataFrame(selected)
