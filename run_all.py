#!/usr/bin/env python3
"""GEM IKE Backtest — complete analysis runner.

Produces all artefacts described in the plan:
  - equity curves
  - trade logs
  - deadband heatmaps
  - broker comparisons (XTB vs BOSSA vs mBank)
  - universe expansion results
  - walk-forward OOS report
  - final decision memo
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import load_config, all_tickers, ROOT
from src.data import (
    fetch_prices,
    validate_prices,
    common_window,
    load_cpi_annual,
    build_contribution_schedule,
)
from src.broker import make_broker, BrokerModel
from src.backtest import run_gem
from src.metrics import compute_all, xirr, sharpe, max_drawdown, build_cashflows
from src.analysis import (
    sweep_deadbands,
    run_gem_dynamic_deadband,
    compare_universes,
    walk_forward,
    timing_luck_test,
)

RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

warnings.filterwarnings("ignore", category=FutureWarning)


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════

def save_fig(fig, name: str):
    fig.savefig(RESULTS / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> saved {name}")


def print_header(text: str):
    bar = "=" * 70
    print(f"\n{bar}\n  {text}\n{bar}")




def compute_benchmark(prices: pd.DataFrame, ticker: str,
                      initial_capital: float,
                      contribution_schedule: pd.Series | None = None) -> dict:
    """Buy-and-hold benchmark with optional DCA contributions.

    When contribution_schedule is provided, each month's contribution buys
    additional shares at market price (no costs — pure benchmark).
    """
    if ticker not in prices.columns:
        return {}
    s = prices[ticker].dropna()
    if s.empty:
        return {}

    if contribution_schedule is not None:
        contrib_lookup = contribution_schedule.to_dict()
        shares = 0.0
        equity_vals = []
        for dt in s.index:
            contrib = contrib_lookup.get(dt, 0.0)
            if contrib > 0:
                shares += contrib / s[dt]
            if initial_capital > 0 and dt == s.index[0]:
                shares += initial_capital / s[dt]
                initial_capital = 0.0
            equity_vals.append(shares * s[dt])
        equity = pd.Series(equity_vals, index=s.index)
    else:
        equity = initial_capital * s / s.iloc[0]

    m = compute_all(equity, label=f"Benchmark ({ticker})",
                    initial_capital=initial_capital if contribution_schedule is None else 0.0,
                    contribution_schedule=contribution_schedule)
    m["ticker"] = ticker
    return m


# ════════════════════════════════════════════════════════════════════
#  ETAP 1 — Data contract & validation
# ════════════════════════════════════════════════════════════════════

def etap1(cfg):
    print_header("ETAP 1: Pobieranie danych i walidacja")
    tickers = all_tickers(cfg)
    benchmark_ticker = cfg["data"].get("benchmark", "VWRL.L")
    if benchmark_ticker not in tickers:
        tickers.append(benchmark_ticker)
    print(f"  Tickers: {tickers}")

    prices = fetch_prices(
        tickers,
        start=cfg["data"]["start_date"],
        end=cfg["data"]["end_date"],
    )
    print(f"  Pobrano dane: {prices.shape[0]} wierszy, {prices.shape[1]} kolumn")

    report = validate_prices(prices)
    print("\n  Raport pokrycia danych:")
    print(report.to_string())
    report.to_csv(RESULTS / "data_coverage.csv")

    return prices


# ════════════════════════════════════════════════════════════════════
#  ETAP 2 — Baseline GEM
# ════════════════════════════════════════════════════════════════════

def etap2(cfg, prices, brokers, contribution_schedule):
    print_header("ETAP 2: Baseline GEM (5 ETF, bez deadbandu)")
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]
    cap = cfg["portfolio"]["initial_capital_pln"]

    fig, ax = plt.subplots(figsize=(14, 6))
    results_summary = []

    for bname, broker in brokers.items():
        res = run_gem(prices, broker, risky, safe, cap, deadband=0.0,
                      contribution_schedule=contribution_schedule)
        m = compute_all(res.equity, label=broker.name,
                        initial_capital=cap,
                        contribution_schedule=contribution_schedule)
        m["broker"] = bname
        m["rotations"] = res.num_rotations
        m["total_costs"] = res.total_costs
        m["total_taxes"] = res.total_taxes
        results_summary.append(m)
        ax.plot(res.equity.index, res.equity.values, label=broker.name, linewidth=1.5)

        trades_df = pd.DataFrame(res.trades)
        if not trades_df.empty:
            trades_df.to_csv(RESULTS / f"trades_baseline_{bname}.csv", index=False)

        print(f"\n  {broker.name}:")
        print(f"    XIRR = {m['xirr']:.2%}, Sharpe = {m['sharpe']:.2f}, "
              f"MaxDD = {m['max_drawdown']:.2%}")
        print(f"    Rotacje = {res.num_rotations}, Koszty = {res.total_costs:.2f}, "
              f"Podatki = {res.total_taxes:.2f}")
        print(f"    Wartość końcowa = {m['final_value']:.2f}")

    ax.set_title("Baseline GEM (U5, deadband=0, DCA) — porównanie brokerów")
    ax.set_ylabel("Wartość portfela (PLN)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    save_fig(fig, "baseline_equity_curves.png")

    summary_df = pd.DataFrame(results_summary)
    summary_df.to_csv(RESULTS / "baseline_summary.csv", index=False)
    return summary_df


# ════════════════════════════════════════════════════════════════════
#  ETAP 3 — Broker comparison (detailed)
# ════════════════════════════════════════════════════════════════════

def etap3(cfg, prices, brokers, contribution_schedule):
    print_header("ETAP 3: Porównanie brokerów (różne deadbandy)")
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]
    cap = cfg["portfolio"]["initial_capital_pln"]

    db_range = cfg["deadband"]
    deadbands = list(np.arange(
        db_range["static_range"][0],
        db_range["static_range"][1] + db_range["static_step"],
        db_range["static_step"],
    ))

    all_results = {}
    for bname, broker in brokers.items():
        df = sweep_deadbands(prices, broker, risky, safe, cap, deadbands,
                             contribution_schedule=contribution_schedule)
        df["broker"] = bname
        all_results[bname] = df
        df.to_csv(RESULTS / f"deadband_sweep_{bname}.csv", index=False)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    metrics_to_plot = ["xirr", "sharpe", "max_drawdown", "rotations"]
    titles = ["XIRR", "Sharpe", "Max Drawdown", "Rotacje"]

    for ax, metric, title in zip(axes.flat, metrics_to_plot, titles):
        for bname, df in all_results.items():
            ax.plot(df["deadband"], df[metric], label=bname, linewidth=1.5)
        ax.set_xlabel("Deadband")
        ax.set_ylabel(title)
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Metryki vs Deadband — porównanie brokerów", fontsize=14)
    fig.tight_layout()
    save_fig(fig, "deadband_sweep_comparison.png")

    return all_results


# ════════════════════════════════════════════════════════════════════
#  ETAP 4 — Deadband calibration
# ════════════════════════════════════════════════════════════════════

def etap4(cfg, prices, brokers, benchmark_metrics, baseline_summary, contribution_schedule):
    print_header("ETAP 4: Kalibracja deadbandu (statyczny + dynamiczny)")
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]
    cap = cfg["portfolio"]["initial_capital_pln"]
    db_cfg = cfg["deadband"]

    bench_maxdd = benchmark_metrics.get("max_drawdown", -1.0) if benchmark_metrics else -1.0
    bench_xirr = benchmark_metrics.get("xirr", 0.0) if benchmark_metrics else 0.0
    print(f"\n  Benchmark (DCA): XIRR={bench_xirr:.2%}, MaxDD={bench_maxdd:.2%}")

    deadbands = list(np.arange(
        db_cfg["static_range"][0],
        db_cfg["static_range"][1] + db_cfg["static_step"],
        db_cfg["static_step"],
    ))

    ike_keys = ["xtb_ike", "bossa_ike_promo", "bossa_ike_standard", "mbank_ike"]
    ike_in_bl = baseline_summary[baseline_summary["broker"].isin(ike_keys)]
    if not ike_in_bl.empty:
        ref_broker_name = ike_in_bl.loc[ike_in_bl["final_value"].idxmax(), "broker"]
    else:
        ref_broker_name = list(brokers.keys())[0]
    ref_broker = brokers[ref_broker_name]

    print(f"\n  Broker referencyjny (najtańszy IKE): {ref_broker.name}")
    print(f"  MaxDD constraint oceniany na brokerze z najniższymi tarciami")

    ref_sweep = sweep_deadbands(prices, ref_broker, risky, safe, cap, deadbands,
                                contribution_schedule=contribution_schedule)
    ref_sweep["excess_xirr"] = ref_sweep["xirr"] - bench_xirr
    ref_sweep.to_csv(RESULTS / f"deadband_sweep_reference_{ref_broker_name}.csv", index=False)

    maxdd_threshold = bench_maxdd * 1.1
    safe_df = ref_sweep[ref_sweep["max_drawdown"] >= maxdd_threshold]
    if not safe_df.empty:
        best_idx = safe_df["excess_xirr"].idxmax()
        best_row = safe_df.loc[best_idx]
        selection_note = f"MaxDD <= benchmark + 10% margin, threshold: {maxdd_threshold:.2%}, ref: {ref_broker.name})"
    else:
        best_idx = ref_sweep["max_drawdown"].idxmax()
        best_row = ref_sweep.loc[best_idx]
        selection_note = f"fallback: min MaxDD (none passed filter on {ref_broker.name}, threshold was {maxdd_threshold:.2%})"

    is_optimal_db = float(best_row["deadband"])
    print(f"\n  IS optymalny deadband = {is_optimal_db:.3f} ({is_optimal_db*100:.1f}%) [{selection_note}]")
    print(f"    XIRR = {best_row['xirr']:.2%} (excess: {best_row['excess_xirr']:+.2%}), "
          f"MaxDD = {best_row['max_drawdown']:.2%}, Rotacje = {int(best_row['rotations'])}")

    # Per-broker metrics at IS optimal deadband
    optimal = {}
    for bname, broker in brokers.items():
        res = run_gem(prices, broker, risky, safe, cap, deadband=is_optimal_db,
                      contribution_schedule=contribution_schedule)
        m = compute_all(res.equity, label=broker.name,
                        initial_capital=cap,
                        contribution_schedule=contribution_schedule)
        optimal[bname] = dict(
            deadband=is_optimal_db,
            sharpe=m["sharpe"],
            xirr=m["xirr"],
            excess_xirr=m["xirr"] - bench_xirr,
            max_drawdown=m["max_drawdown"],
            rotations=res.num_rotations,
        )
        print(f"\n  {broker.name} @ db={is_optimal_db:.3f}:")
        print(f"    XIRR = {m['xirr']:.2%} (excess: {m['xirr'] - bench_xirr:+.2%}), "
              f"Sharpe = {m['sharpe']:.2f}, MaxDD = {m['max_drawdown']:.2%}")

    # Dynamic deadband tests
    dyn_cfg = db_cfg["dynamic"]
    dyn_results = []
    for bname, broker in brokers.items():
        for k in np.arange(dyn_cfg["k_range"][0],
                           dyn_cfg["k_range"][1] + dyn_cfg["k_step"],
                           dyn_cfg["k_step"]):
            res = run_gem_dynamic_deadband(
                prices, broker, risky, safe, cap,
                base=dyn_cfg["base"], k=k,
                vol_window=dyn_cfg["vol_window_months"],
                contribution_schedule=contribution_schedule,
            )
            m = compute_all(res.equity, label=f"{bname}_k={k:.2f}",
                            initial_capital=cap,
                            contribution_schedule=contribution_schedule)
            m["broker"] = bname
            m["k"] = k
            m["base"] = dyn_cfg["base"]
            m["rotations"] = res.num_rotations
            m["total_costs"] = res.total_costs
            dyn_results.append(m)

    dyn_df = pd.DataFrame(dyn_results)
    dyn_df.to_csv(RESULTS / "dynamic_deadband_results.csv", index=False)

    print("\n  Dynamiczny deadband:")
    for bname in brokers:
        sub = dyn_df[dyn_df["broker"] == bname]
        if sub.empty:
            continue
        best = sub.loc[sub["sharpe"].idxmax()]
        print(f"    {bname}: best k={best['k']:.2f}, Sharpe={best['sharpe']:.2f}, "
              f"XIRR={best['xirr']:.2%}")

    return is_optimal_db, optimal, ref_broker_name, dyn_df


# ════════════════════════════════════════════════════════════════════
#  ETAP 5 — Universe expansion
# ════════════════════════════════════════════════════════════════════

def etap5(cfg, prices, broker, optimal_db, contribution_schedule, recommended_db=None):
    print_header("ETAP 5: Rozszerzanie uniwersum ETF")
    cap = cfg["portfolio"]["initial_capital_pln"]
    db = optimal_db

    comp = compare_universes(prices, broker, cfg["universes"], cap, deadband=db,
                             contribution_schedule=contribution_schedule)
    comp.to_csv(RESULTS / "universe_comparison.csv", index=False)

    print(f"\n  Deadband = {db:.3f}, Broker = {broker.name}")
    for _, row in comp.iterrows():
        print(f"    {row['universe']} ({int(row['n_etfs'])} ETF): "
              f"XIRR={row['xirr']:.2%}, Sharpe={row['sharpe']:.2f}, "
              f"MaxDD={row['max_drawdown']:.2%}, Rotacje={int(row['rotations'])}")

    fig, ax = plt.subplots(figsize=(14, 6))
    for name, univ in cfg["universes"].items():
        r = [t for t in univ["risky"] if t in prices.columns]
        s = [t for t in univ["safe"] if t in prices.columns]
        if not r or not s:
            continue
        res = run_gem(prices, broker, r, s, cap, deadband=db,
                      contribution_schedule=contribution_schedule)
        ax.plot(res.equity.index, res.equity.values, label=name, linewidth=1.5)

    ax.set_title(f"Porównanie uniwersów ETF (deadband={db:.3f}, DCA, {broker.name})")
    ax.set_ylabel("Wartość portfela (PLN)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    save_fig(fig, "universe_comparison.png")

    comp_oos = None
    if recommended_db is not None and recommended_db != optimal_db:
        comp_oos = compare_universes(prices, broker, cfg["universes"], cap,
                                     deadband=recommended_db, contribution_schedule=contribution_schedule)
        comp_oos.to_csv(RESULTS / "universe_comparison_oos.csv", index=False)
        print(f"\n  Deadband = {recommended_db:.3f} (OOS rekomendowany), Broker = {broker.name}")
        for _, row in comp_oos.iterrows():
            print(f"    {row['universe']} ({int(row['n_etfs'])} ETF): "
                  f"XIRR={row['xirr']:.2%}, Sharpe={row['sharpe']:.2f}, "
                  f"MaxDD={row['max_drawdown']:.2%}, Rotacje={int(row['rotations'])}")

    return comp, comp_oos


# ════════════════════════════════════════════════════════════════════
#  ETAP 6 — Robustness
# ════════════════════════════════════════════════════════════════════

def etap6(cfg, prices, daily_prices, broker, optimal_db, contribution_schedule,
          inflation_rates, base_contribution):
    print_header("ETAP 6: Testy odporności")
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]
    cap = cfg["portfolio"]["initial_capital_pln"]

    db_range = cfg["deadband"]
    deadbands = list(np.arange(
        db_range["static_range"][0],
        db_range["static_range"][1] + db_range["static_step"],
        db_range["static_step"],
    ))

    # Walk-forward
    print("\n  Walk-forward validation...")
    wf = walk_forward(
        prices, broker, risky, safe, cap, deadbands,
        train_months=cfg["walk_forward"]["train_months"],
        test_months=cfg["walk_forward"]["test_months"],
        step_months=cfg["walk_forward"]["step_months"],
        contribution_schedule=contribution_schedule,
    )
    if not wf["folds"].empty:
        wf["folds"].to_csv(RESULTS / "walk_forward_folds.csv", index=False)
        print("    Wyniki walk-forward po foldach:")
        print(wf["folds"].to_string())
        if len(wf["oos_equity"]) > 1:
            oos_m = compute_all(wf["oos_equity"], label="OOS")
            fold_rets = wf["folds"]["oos_return"]
            honest_sharpe = fold_rets.mean() / fold_rets.std() if fold_rets.std() > 0 else 0.0
            honest_mdd = wf["folds"]["oos_return"].min()
            print(f"\n    OOS stitched: Sharpe={honest_sharpe:.2f},"
                  f" MaxDD(worst fold)={honest_mdd:.2%}")

            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(wf["oos_equity"].index, wf["oos_equity"].values, linewidth=1.5)
            ax.set_title("Walk-Forward OOS Equity Curve")
            ax.set_ylabel("Wartość (PLN)")
            ax.grid(True, alpha=0.3)
            save_fig(fig, "walk_forward_oos.png")
    else:
        print("    Za mało danych na walk-forward.")

    # Timing luck
    print("\n  Timing luck test...")
    if daily_prices is not None and not daily_prices.empty:
        offsets = cfg.get("rebalance_days", [1, 5, 10, 15, 20])
        tl = timing_luck_test(daily_prices, broker, risky, safe, cap, optimal_db, offsets,
                              contribution_schedule=contribution_schedule,
                              inflation_rates=inflation_rates,
                              base_contribution=base_contribution)
        if not tl.empty:
            tl.to_csv(RESULTS / "timing_luck.csv", index=False)
            print("    Wyniki timing luck:")
            for _, row in tl.iterrows():
                print(f"      Offset {row['offset']}: XIRR={row['xirr']:.2%}")

            xirr_vals = tl["xirr"].dropna()
            print(f"    Rozrzut XIRR: min={xirr_vals.min():.2%}, "
                  f"max={xirr_vals.max():.2%}, "
                  f"std={xirr_vals.std():.2%}")
            
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(tl["offset"], tl["xirr"], color="steelblue", alpha=0.8)
            ax.set_xlabel("Dzień roboczy miesiąca (offset)")
            ax.set_ylabel("XIRR")
            ax.set_title("Timing Luck — wrażliwość na dzień rebalancingu")
            ax.grid(True, alpha=0.3, axis="y")
            save_fig(fig, "timing_luck.png")
    else:
        print("    Brak danych dziennych — pominięto timing luck.")

    # Cost sensitivity
    print("\n  Analiza czułości kosztów FX...")
    fx_costs = [0.0, 0.0025, 0.005, 0.0075, 0.01]
    fx_results = []
    for fx in fx_costs:
        test_broker = BrokerModel(
            name=f"fx={fx:.3f}",
            fractional_shares=True,
            fx_cost_per_leg=fx,
            commission_pct=0.0,
            commission_min_pln=0.0,
            slippage=0.001,
            capital_gains_tax=0.0,
        )
        res = run_gem(prices, test_broker, risky, safe, cap, deadband=optimal_db,
                      contribution_schedule=contribution_schedule)
        m = compute_all(res.equity, label=f"fx={fx:.4f}",
                        initial_capital=cap,
                        contribution_schedule=contribution_schedule)
        m["fx_cost_per_leg"] = fx
        m["rotations"] = res.num_rotations
        m["total_costs"] = res.total_costs
        fx_results.append(m)

    fx_df = pd.DataFrame(fx_results)
    fx_df.to_csv(RESULTS / "fx_sensitivity.csv", index=False)
    print(fx_df[["fx_cost_per_leg", "xirr", "sharpe", "total_costs", "final_value"]].to_string())

    return wf


# ════════════════════════════════════════════════════════════════════
#  ETAP 7 — Decision memo
# ════════════════════════════════════════════════════════════════════

def etap7(cfg, baseline_summary, optimal_dbs, universe_comp, universe_comp_oos, wf_result, prices, brokers, benchmark_metrics=None, blend_info=None):
    print_header("ETAP 7: Rekomendacja końcowa")

    cap = cfg["portfolio"]["initial_capital_pln"]
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]

    # Contribution scenarios — start from 0 PLN, inflation-adjusted monthly contributions
    print("\n  Scenariusze z regularnymi wpłatami (kapitał startowy = 0, rewaloryzacja CPI):")
    inflation_rates = load_cpi_annual()
    print(f"  CPI załadowane z pliku GUS ({len(inflation_rates)} lat: {min(inflation_rates)}–{max(inflation_rates)})")

    # Determine simulation date range (same as backtest would use)
    from src.momentum import compute_momentum, select_best
    all_tickers = [t for t in risky + safe if t in prices.columns]
    mom = compute_momentum(prices[all_tickers], lookback=13, skip=1)
    signals = select_best(mom, risky, safe)
    valid_idx = signals.dropna(subset=["target"]).index
    sim_dates = prices.loc[valid_idx[0]:].index

    contribution_results = []
    for contrib_base in cfg["portfolio"]["contribution_scenarios"]:
        schedule = build_contribution_schedule(contrib_base, sim_dates, inflation_rates)
        total_contributed = schedule.sum()

        print(f"\n  Wpłata bazowa: {contrib_base} PLN/mies. (rewaloryzowana o CPI)")
        print(f"    Okres: {sim_dates[0].date()} → {sim_dates[-1].date()} ({len(sim_dates)} mies.)")
        print(f"    Wpłata końcowa (po inflacji): {schedule.iloc[-1]:.2f} PLN/mies.")
        print(f"    Suma wpłat: {total_contributed:,.0f} PLN")

        for bname, broker in brokers.items():
            db = optimal_dbs.get(bname, {}).get("deadband", 0.03)
            res = run_gem(prices, broker, risky, safe, 0.0,
                          deadband=db, contribution_schedule=schedule)
            m = compute_all(res.equity, label=f"{bname}_contrib={contrib_base}",
                            initial_capital=0.0,
                            contribution_schedule=schedule)
            m["broker"] = bname
            m["base_contribution"] = contrib_base
            m["total_contributed"] = total_contributed
            m["final_contribution"] = schedule.iloc[-1]
            m["optimal_deadband"] = db
            m["rotations"] = res.num_rotations
            m["total_costs"] = res.total_costs
            m["total_taxes"] = res.total_taxes
            contribution_results.append(m)
            print(f"    {broker.name}: {m['final_value']:,.0f} PLN (mnożnik: {m['final_value']/total_contributed:.2f}×)")

    contrib_df = pd.DataFrame(contribution_results)
    contrib_df.to_csv(RESULTS / "contribution_scenarios.csv", index=False)

    # Find crossover points: at what capital do BOSSA / mBank beat XTB?
    ike_brokers = ["xtb_ike", "bossa_ike_promo", "mbank_ike"]
    ike_brokers = [b for b in ike_brokers if b in brokers]
    print(f"\n  Analiza crossover dla: {ike_brokers}")

    test_capitals = list(range(5000, 200001, 5000))
    crossover_data = []
    crossover_capitals = {}

    for test_cap in test_capitals:
        results_by_broker = {}
        for bname in ike_brokers:
            broker = brokers[bname]
            db = optimal_dbs.get(bname, {}).get("deadband", 0.03)
            res = run_gem(prices, broker, risky, safe, test_cap, deadband=db)
            m = compute_all(res.equity, label=bname,
                            initial_capital=test_cap)
            results_by_broker[bname] = m
            crossover_data.append(dict(
                capital=test_cap, broker=bname,
                xirr=m["xirr"], final_value=m["final_value"],
            ))

        if "xtb_ike" in results_by_broker:
            xtb_val = results_by_broker["xtb_ike"]["final_value"]
            for rival in ike_brokers:
                if rival == "xtb_ike":
                    continue
                if rival in results_by_broker:
                    if results_by_broker[rival]["final_value"] > xtb_val:
                        if rival not in crossover_capitals:
                            crossover_capitals[rival] = test_cap

    crossover_df = pd.DataFrame(crossover_data)
    crossover_df.to_csv(RESULTS / "crossover_analysis.csv", index=False)

    for rival, cap_val in crossover_capitals.items():
        print(f"    {rival} > XTB od kapitału ~{cap_val:,} PLN")
    if not crossover_capitals:
        print("    Żaden broker nie przewyższa XTB w testowanym zakresie"
              " (lub jest lepszy od samego początku)")

    crossover_capital = crossover_capitals.get("bossa_ike_promo")

    # plot crossover
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = {"xtb_ike": "C0", "bossa_ike_promo": "C1", "mbank_ike": "C2"}
    for bname in ike_brokers:
        sub = crossover_df[crossover_df["broker"] == bname]
        if not sub.empty:
            ax.plot(sub["capital"], sub["final_value"],
                    label=brokers[bname].name, linewidth=1.5,
                    color=colors.get(bname))
    for rival, cap_val in crossover_capitals.items():
        ax.axvline(cap_val, linestyle="--", alpha=0.7,
                   color=colors.get(rival, "gray"),
                   label=f"Crossover {rival} ~{cap_val:,} PLN")
    ax.set_xlabel("Kapitał początkowy (PLN)")
    ax.set_ylabel("Wartość końcowa (PLN)")
    ax.set_title("XTB vs BOSSA vs mBank — próg przejścia wg kapitału")
    ax.legend()
    ax.grid(True, alpha=0.3)
    save_fig(fig, "crossover_brokers.png")

    # Generate decision memo
    _write_decision_memo(cfg, baseline_summary, optimal_dbs, universe_comp,
                         universe_comp_oos,
                         wf_result, crossover_capitals, contrib_df, brokers,
                         benchmark_metrics, blend_info)


def _write_decision_memo(cfg, baseline, optimal_dbs, universe_comp,
                         universe_comp_oos,
                         wf_result, crossover_capitals, contrib_df, brokers,
                         benchmark_metrics=None, blend_info=None):
    cap = cfg["portfolio"]["initial_capital_pln"]

    # Gather baseline metrics for all IKE brokers
    ike_keys = ["xtb_ike", "bossa_ike_promo", "mbank_ike"]
    ike_metrics = {}
    for bk in ike_keys:
        if bk in baseline["broker"].values:
            ike_metrics[bk] = baseline[baseline["broker"] == bk].iloc[0]

    # Determine best broker at current capital
    if ike_metrics:
        best_bk = max(ike_metrics, key=lambda k: ike_metrics[k]["final_value"])
        rec_broker = brokers[best_bk].name if best_bk in brokers else best_bk
        vals = {bk: f"{ike_metrics[bk]['final_value']:.0f}" for bk in ike_metrics}
        vals_str = ", ".join(f"{brokers[bk].name}={v} PLN" for bk, v in vals.items() if bk in brokers)
        rec_reason = (f"Przy kapitale {cap:.0f} PLN, najlepszy wynik końcowy daje "
                      f"{rec_broker} ({vals_str}).")
    else:
        rec_broker = "XTB IKE"
        rec_reason = "Brak danych porównawczych."

    # Blended deadband — single value for all brokers
    blended_db = blend_info["recommended_snapped"] if blend_info else 0.03
    is_opt = blend_info["is_optimal"] if blend_info else blended_db
    oos_avg = blend_info.get("oos_avg") if blend_info else None
    oos_median = blend_info.get("oos_median") if blend_info else None
    ref_broker_label = blend_info.get("ref_broker_name", "") if blend_info else ""

    # Per-broker metrics at blended deadband
    db_rows = []
    for bk in ike_keys:
        if bk in optimal_dbs:
            excess = optimal_dbs[bk].get("excess_xirr", 0.0)
            maxdd = optimal_dbs[bk].get("max_drawdown", 0.0)
            label = brokers[bk].name if bk in brokers else bk
            db_rows.append(f"| {label} | {excess:+.2%} | {maxdd:.2%} | {optimal_dbs[bk].get('sharpe', 0):.2f} |")  # excess = excess_xirr

    # recommended universe
    is_db_for_display = blend_info.get("is_optimal", 0) if blend_info else 0
    if universe_comp is not None and not universe_comp.empty:
        best_univ = universe_comp.loc[universe_comp["sharpe"].idxmax()]
        rec_universe = best_univ["universe"]
        rec_univ_detail = (f"{rec_universe} ({int(best_univ['n_etfs'])} ETF-ów): "
                           f"Sharpe={best_univ['sharpe']:.2f}, XIRR={best_univ['xirr']:.2%} "
                           f"(testowane przy IS deadband={is_db_for_display:.1%})")
        if universe_comp_oos is not None and not universe_comp_oos.empty:
            best_univ_oos = universe_comp_oos.loc[universe_comp_oos["sharpe"].idxmax()]
            rec_univ_detail += (f"\n\n**Przy rekomendowanym deadband={blended_db:.1%} (OOS):** "
                                f"{best_univ_oos['universe']}({int(best_univ_oos['n_etfs'])} ETF-ów): "
                                f"Sharpe={best_univ_oos['sharpe']:.2f}, XIRR={best_univ_oos['xirr']:.2%}")
    else:
        rec_universe = "U5"
        rec_univ_detail = "Brak danych porównawczych."

    # OOS validation
    if wf_result and "folds" in wf_result and not wf_result["folds"].empty:
        avg_oos_ret = wf_result["folds"]["oos_return"].mean()
        oos_note = f"Średni OOS return per fold (skumulowany, 2-letni): {avg_oos_ret:.2%}. Annualizowany: {(1 + avg_oos_ret)**0.5 - 1:.2%}"
        if blend_info and blend_info.get("oos_deadbands"):
            oos_note += f"\nWybrane deadbandy per fold: {[f'{d:.3f}' for d in blend_info['oos_deadbands']]}"
    else:
        oos_note = "Za mało danych na pełną walidację walk-forward."

    memo = f"""# Rekomendacja końcowa — GEM na IKE

## Stan portfela
- Kapitał: {cap:,.0f} PLN
- Obecny koszyk: U5 (CNDX.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L

## 1. Broker: {rec_broker}

{rec_reason}

### Porównanie modeli kosztowych

| Broker | FX/leg | Prowizja | Frakcje | Uwagi |
|--------|--------|----------|---------|-------|
| XTB IKE | 0.5% | 0% | Tak | Wysoki FX, brak cash drag |
| BOSSA IKE (promo) | 0% | 0% (promo) | Nie | Subkonta walutowe, promo do 2027 |
| mBank IKE (eMakler) | 0.1% | 0% (stale) | Nie | Brak subkont walutowych, FX na obu nogach rotacji |

### Warunki migracji
"""
    for rival, cap_val in crossover_capitals.items():
        rival_name = brokers[rival].name if rival in brokers else rival
        memo += f"- {rival_name} > XTB od kapitału ~{cap_val:,} PLN\n"
    if not crossover_capitals:
        memo += "- Żaden alternatywny broker nie bije XTB w testowanym zakresie (lub jest lepszy od początku).\n"

    # benchmark section
    if benchmark_metrics:
        bench_ticker = benchmark_metrics.get("ticker", "IWDA.L")
        bench_xirr_val = benchmark_metrics.get("xirr", 0)
        bench_maxdd = benchmark_metrics.get("max_drawdown", 0)
        bench_final = benchmark_metrics.get("final_value", 0)
        bench_section = f"""
## Benchmark: {bench_ticker} (pasywny DCA)
- XIRR: {bench_xirr_val:.2%}
- MaxDD: {bench_maxdd:.2%}
- Wartość końcowa: {bench_final:,.0f} PLN
"""
    else:
        bench_section = ""

    memo += bench_section

    # Blend methodology section
    blend_section = f"""
## 2. Optymalny deadband

**Wynik: deadband = {blended_db:.3f} ({blended_db*100:.1f}%)** (jednakowy dla wszystkich brokerów)

### Jak obliczono:
1. **Broker referencyjny**: {ref_broker_label} (najtańszy IKE — najniższe tarcia kosztowe)
2. **IS optymalny** (informacyjnie): {is_opt:.3f} ({is_opt*100:.1f}%) — górna granica rozsądnego deadbandu;
najwyższy excess XIRR spośród deadbandów, których MaxDD nie przekracza MaxDD benchmarku + 10% margin.
Nie używany bezpośrednio do rekomendacji — podatny na look-ahead bias.
"""
    if oos_avg is not None:
        blend_section += f"""3. **OOS średnia** (walk-forward): {oos_avg:.3f} ({oos_avg*100:.1f}%)
4. **OOS mediana** (walk-forward): {oos_median:.3f} ({oos_median*100:.1f}%)
5. **Rekomendowany deadband** = {blend_info['recommended_raw']:.4f}
   → zaokrąglony do siatki: **{blended_db:.3f} ({blended_db*100:.1f}%)**
"""
    else:
        blend_section += "\nBrak danych OOS — użyty IS optymalny bez korekty.\n"

    blend_section += f"""
### Wyniki per broker @ deadband = {blended_db:.3f}

| Broker | Excess XIRR | MaxDD | Sharpe (IS) |
|--------|-------------|-------|--------|
{chr(10).join(db_rows)}

"""
    memo += blend_section

    memo += f"""## 3. Uniwersum ETF

Rekomendowane: **{rec_universe}**
{rec_univ_detail}

## 4. Walidacja Out-of-Sample

{oos_note}

## 5. Scenariusze z regularnymi wpłatami (kapitał startowy = 0, CPI rewaloryzacja)

Wpłaty co miesiąc, rewaloryzowane o wskaźnik średniorocznej inflacji CPI (GUS) na początku każdego roku.
Kapitał startowy = 0 PLN.

"""
    if not contrib_df.empty:
        # Build a richer table with total_contributed and multiplier
        rows_memo = []
        for _, row in contrib_df.iterrows():
            rows_memo.append(dict(
                wpłata_bazowa=int(row["base_contribution"]),
                broker=row["broker"],
                suma_wpłat=row["total_contributed"],
                wartość_końcowa=row["final_value"],
                mnożnik=row["final_value"] / row["total_contributed"] if row["total_contributed"] > 0 else 0,
            ))
        detail_df = pd.DataFrame(rows_memo)

        pivot_val = contrib_df.pivot_table(
            index="base_contribution",
            columns="broker",
            values="final_value",
            aggfunc="first",
        )
        pivot_val.index.name = "wpłata bazowa (PLN/mies.)"
        memo += "### Wartość końcowa portfela\n\n"
        memo += pivot_val.to_markdown(floatfmt=",.0f") + "\n\n"

        # Total contributed (same for all brokers within a base_contribution level)
        total_contribs = contrib_df.drop_duplicates(subset=["base_contribution"])[["base_contribution", "total_contributed", "final_contribution"]]
        memo += "### Suma wpłat i rewaloryzacja\n\n"
        memo += "| Wpłata bazowa | Wpłata końcowa (po CPI) | Suma wpłat |\n"
        memo += "|:---:|:---:|:---:|\n"
        for _, r in total_contribs.iterrows():
            memo += f"| {int(r['base_contribution'])} PLN | {r['final_contribution']:.0f} PLN | {r['total_contributed']:,.0f} PLN |\n"
        memo += "\n"

    memo += f"""
## Podsumowanie decyzji

1. **Wybierz brokera** wg powyższej tabeli kosztowej i progu crossover.
2. **Ustaw deadband** na **{blended_db*100:.1f}%**.
3. **Rozważ rozszerzenie koszyka** jeśli dane OOS to potwierdzają.
4. **Regularnie wpłacaj** — nawet małe kwoty znacząco podnoszą wartość końcową dzięki procentowi składanemu w parasolu IKE.
"""

    with open(RESULTS / "decision_memo.md", "w", encoding="utf-8") as f:
        f.write(memo)
    print(f"\n  Zapisano: decision_memo.md")
    print(memo)


# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  GEM IKE Backtest — Pełna analiza penetracyjna")
    print("  Tryb: start=0, regularne wpłaty z CPI rewaloryzacją")
    print("=" * 70)

    cfg = load_config()

    # build broker models
    brokers = {name: make_broker(bcfg) for name, bcfg in cfg["brokers"].items()}

    # ETAP 1 — data
    prices = etap1(cfg)

    # ── Build fitting contribution schedule (used for ALL calibration) ──
    from src.data import load_cpi_annual
    inflation_rates = load_cpi_annual()
    base_contribution = cfg["portfolio"]["fitting_base_contribution_pln"]
    contribution_schedule = build_contribution_schedule(
        base_contribution, prices.index, inflation_rates
    )
    cap = cfg["portfolio"]["initial_capital_pln"]  # 0.0
    print(f"\n  Fitting: initial_capital={cap:.0f}, base_contribution={base_contribution:.0f} PLN/mies")
    print(f"  Contribution schedule: {contribution_schedule.iloc[0]:.2f} → {contribution_schedule.iloc[-1]:.2f} PLN")

    # also fetch daily prices for timing luck test
    tickers_u5 = cfg["universes"]["U5"]["risky"] + cfg["universes"]["U5"]["safe"]
    tickers_u5 = [t for t in tickers_u5 if t in prices.columns]
    daily_prices = None
    try:
        import yfinance as yf
        raw = {}
        for t in tickers_u5:
            d = yf.download(t, start=cfg["data"]["start_date"],
                            end=cfg["data"]["end_date"],
                            auto_adjust=True, progress=False)
            if not d.empty:
                close = d["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                raw[t] = close
        if raw:
            daily_prices = pd.DataFrame(raw).dropna()
    except Exception as e:
        print(f"  Nie udało się pobrać danych dziennych: {e}")

    # Benchmark DCA (same contribution schedule, no costs)
    bench_ticker = cfg["data"].get("benchmark", "VWRL.L")
    benchmark_metrics = compute_benchmark(prices, bench_ticker, cap,
                                          contribution_schedule=contribution_schedule)
    if benchmark_metrics:
        print(f"\n  Benchmark DCA ({bench_ticker}): XIRR={benchmark_metrics['xirr']:.2%}, "
              f"MaxDD={benchmark_metrics['max_drawdown']:.2%}, "
              f"Wartość końcowa={benchmark_metrics['final_value']:.0f}")

    # ETAP 2 — baseline
    baseline_summary = etap2(cfg, prices, brokers, contribution_schedule)

    # ETAP 3 — broker comparison with deadband sweep
    all_sweep = etap3(cfg, prices, brokers, contribution_schedule)

    # ETAP 4 — deadband calibration (MaxDD constraint from benchmark DCA)
    is_optimal_db, optimal_dbs, ref_broker_name, dyn_df = etap4(
        cfg, prices, brokers, benchmark_metrics, baseline_summary, contribution_schedule
    )
    ref_broker = brokers[ref_broker_name]

    # ETAP 6 — robustness (walk-forward, timing luck, cost sensitivity)
    wf_result = etap6(cfg, prices, daily_prices, ref_broker, is_optimal_db,
                      contribution_schedule, inflation_rates, base_contribution)
    
    # ── OOS median → final recommended deadband ──
    db_cfg = cfg["deadband"]
    deadbands = list(np.arange(
        db_cfg["static_range"][0],
        db_cfg["static_range"][1] + db_cfg["static_step"],
        db_cfg["static_step"],
    ))

    oos_dbs = wf_result.get("selected_deadbands", [])
    if oos_dbs:
        oos_avg = float(np.mean(oos_dbs))
        oos_median = float(np.median(oos_dbs))
        recommended_raw = oos_median
        recommended_db = float(min(deadbands, key=lambda x: abs(x - recommended_raw)))
    else:
        oos_avg = None
        oos_median = None
        recommended_raw = is_optimal_db
        recommended_db = is_optimal_db

    blend_info = dict(
        is_optimal=is_optimal_db,
        oos_avg=oos_avg,
        oos_median=oos_median,
        recommended_raw=recommended_raw,
        recommended_snapped=recommended_db,
        ref_broker=ref_broker_name,
        ref_broker_name=ref_broker.name,
        oos_deadbands=oos_dbs,
    )

    print(f"\n  ── Rekomendowany deadband (OOS mediana) ──")
    print(f"  IS optymalny (z {ref_broker.name}): {is_optimal_db:.3f} ({is_optimal_db*100:.1f}%)")
    if oos_avg is not None:
        print(f"  OOS średnia: {oos_avg:.3f} ({oos_avg*100:.1f}%)")
        print(f"  OOS mediana: {oos_median:.3f} ({oos_median*100:.1f}%)")
        print(f"  Rekomendowany deadband: {recommended_db:.3f} ({recommended_db*100:.1f}%)")
    else:
        print(f"  Brak danych OOS — używany IS optymalny")

    # ETAP 5 — universe expansion (use cheapest IKE as reference)
    universe_comp, universe_comp_oos = etap5(
        cfg, prices, ref_broker, is_optimal_db, contribution_schedule,
        recommended_db=recommended_db,
    )

    # Re-compute per-broker metrics at blended deadband
    bench_xirr_val = benchmark_metrics.get("xirr", 0.0) if benchmark_metrics else 0.0
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]

    for bname, broker in brokers.items():
        res = run_gem(prices, broker, risky, safe, cap, deadband=recommended_db,
                      contribution_schedule=contribution_schedule)
        m = compute_all(res.equity, label=bname,
                        initial_capital=cap,
                        contribution_schedule=contribution_schedule)
        optimal_dbs[bname] = dict(
            deadband=recommended_db,
            sharpe=m["sharpe"],
            xirr=m["xirr"],
            excess_xirr=m["xirr"] - bench_xirr_val,
            max_drawdown=m["max_drawdown"],
            rotations=res.num_rotations,
        )

    # ETAP 7 — decision
    etap7(cfg, baseline_summary, optimal_dbs, universe_comp, universe_comp_oos,
          wf_result, prices, brokers, benchmark_metrics, blend_info)

    print_header("ANALIZA ZAKOŃCZONA")
    print(f"  Wyniki zapisane w: {RESULTS}")
    print(f"  Rekomendacja: {RESULTS / 'decision_memo.md'}")


if __name__ == "__main__":
    main()
