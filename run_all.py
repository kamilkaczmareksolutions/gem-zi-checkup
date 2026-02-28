#!/usr/bin/env python3
"""GEM IKE Backtest — complete analysis runner.

Produces all artefacts described in the plan:
  - equity curves
  - trade logs
  - deadband heatmaps
  - broker comparisons (XTB vs BOSSA)
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
from src.data import fetch_prices, validate_prices, common_window
from src.broker import make_broker, BrokerModel
from src.backtest import run_gem
from src.metrics import compute_all, cagr, sharpe, max_drawdown
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


# ════════════════════════════════════════════════════════════════════
#  ETAP 1 — Data contract & validation
# ════════════════════════════════════════════════════════════════════

def etap1(cfg):
    print_header("ETAP 1: Pobieranie danych i walidacja")
    tickers = all_tickers(cfg)
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

def etap2(cfg, prices, brokers):
    print_header("ETAP 2: Baseline GEM (5 ETF, bez deadbandu)")
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]
    cap = cfg["portfolio"]["initial_capital_pln"]

    fig, ax = plt.subplots(figsize=(14, 6))
    results_summary = []

    for bname, broker in brokers.items():
        res = run_gem(prices, broker, risky, safe, cap, deadband=0.0)
        m = compute_all(res.equity, label=broker.name)
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
        print(f"    CAGR = {m['cagr']:.2%}, Sharpe = {m['sharpe']:.2f}, "
              f"MaxDD = {m['max_drawdown']:.2%}")
        print(f"    Rotacje = {res.num_rotations}, Koszty = {res.total_costs:.2f}, "
              f"Podatki = {res.total_taxes:.2f}")
        print(f"    Wartość końcowa = {m['final_value']:.2f}")

    ax.set_title("Baseline GEM (U5, deadband=0) — porównanie brokerów")
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

def etap3(cfg, prices, brokers):
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
        df = sweep_deadbands(prices, broker, risky, safe, cap, deadbands)
        df["broker"] = bname
        all_results[bname] = df
        df.to_csv(RESULTS / f"deadband_sweep_{bname}.csv", index=False)

    # plot: CAGR vs deadband per broker
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    metrics_to_plot = ["cagr", "sharpe", "max_drawdown", "rotations"]
    titles = ["CAGR", "Sharpe", "Max Drawdown", "Rotacje"]

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

def etap4(cfg, prices, brokers):
    print_header("ETAP 4: Kalibracja deadbandu (statyczny + dynamiczny)")
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]
    cap = cfg["portfolio"]["initial_capital_pln"]
    db_cfg = cfg["deadband"]

    deadbands = list(np.arange(
        db_cfg["static_range"][0],
        db_cfg["static_range"][1] + db_cfg["static_step"],
        db_cfg["static_step"],
    ))

    # Static sweep for each broker — find optimum
    optimal = {}
    for bname, broker in brokers.items():
        df = sweep_deadbands(prices, broker, risky, safe, cap, deadbands)

        best_idx = df["sharpe"].idxmax()
        best_row = df.loc[best_idx]
        optimal[bname] = dict(
            deadband=best_row["deadband"],
            sharpe=best_row["sharpe"],
            cagr=best_row["cagr"],
            max_drawdown=best_row["max_drawdown"],
            rotations=best_row["rotations"],
        )
        print(f"\n  {broker.name}: optymalny deadband = {best_row['deadband']:.3f}")
        print(f"    Sharpe = {best_row['sharpe']:.2f}, CAGR = {best_row['cagr']:.2%}, "
              f"MaxDD = {best_row['max_drawdown']:.2%}, Rotacje = {int(best_row['rotations'])}")

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
            )
            m = compute_all(res.equity, label=f"{bname}_k={k:.2f}")
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
              f"CAGR={best['cagr']:.2%}")

    return optimal, dyn_df


# ════════════════════════════════════════════════════════════════════
#  ETAP 5 — Universe expansion
# ════════════════════════════════════════════════════════════════════

def etap5(cfg, prices, broker, optimal_db):
    print_header("ETAP 5: Rozszerzanie uniwersum ETF")
    cap = cfg["portfolio"]["initial_capital_pln"]

    # Use the optimal deadband for the given broker
    db = optimal_db

    comp = compare_universes(prices, broker, cfg["universes"], cap, deadband=db)
    comp.to_csv(RESULTS / "universe_comparison.csv", index=False)

    print(f"\n  Deadband = {db:.3f}, Broker = {broker.name}")
    for _, row in comp.iterrows():
        print(f"    {row['universe']} ({int(row['n_etfs'])} ETF): "
              f"CAGR={row['cagr']:.2%}, Sharpe={row['sharpe']:.2f}, "
              f"MaxDD={row['max_drawdown']:.2%}, Rotacje={int(row['rotations'])}")

    # equity curves per universe
    fig, ax = plt.subplots(figsize=(14, 6))
    for name, univ in cfg["universes"].items():
        r = [t for t in univ["risky"] if t in prices.columns]
        s = [t for t in univ["safe"] if t in prices.columns]
        if not r or not s:
            continue
        res = run_gem(prices, broker, r, s, cap, deadband=db)
        ax.plot(res.equity.index, res.equity.values, label=name, linewidth=1.5)

    ax.set_title(f"Porównanie uniwersów ETF (deadband={db:.3f}, {broker.name})")
    ax.set_ylabel("Wartość portfela (PLN)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    save_fig(fig, "universe_comparison.png")

    return comp


# ════════════════════════════════════════════════════════════════════
#  ETAP 6 — Robustness
# ════════════════════════════════════════════════════════════════════

def etap6(cfg, prices, daily_prices, broker, optimal_db):
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
    )
    if not wf["folds"].empty:
        wf["folds"].to_csv(RESULTS / "walk_forward_folds.csv", index=False)
        print("    Wyniki walk-forward po foldach:")
        print(wf["folds"].to_string())
        if len(wf["oos_equity"]) > 1:
            oos_m = compute_all(wf["oos_equity"], label="OOS")
            print(f"\n    OOS stitched: CAGR={oos_m['cagr']:.2%}, "
                  f"Sharpe={oos_m['sharpe']:.2f}, MaxDD={oos_m['max_drawdown']:.2%}")

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
        tl = timing_luck_test(daily_prices, broker, risky, safe, cap, optimal_db, offsets)
        if not tl.empty:
            tl.to_csv(RESULTS / "timing_luck.csv", index=False)
            print("    Wyniki timing luck:")
            for _, row in tl.iterrows():
                print(f"      Offset {int(row['offset'])}: CAGR={row['cagr']:.2%}, "
                      f"Sharpe={row['sharpe']:.2f}")

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(tl["offset"], tl["cagr"], color="steelblue", alpha=0.8)
            ax.set_xlabel("Dzień roboczy miesiąca (offset)")
            ax.set_ylabel("CAGR")
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
        res = run_gem(prices, test_broker, risky, safe, cap, deadband=optimal_db)
        m = compute_all(res.equity, label=f"fx={fx:.4f}")
        m["fx_cost_per_leg"] = fx
        m["rotations"] = res.num_rotations
        m["total_costs"] = res.total_costs
        fx_results.append(m)

    fx_df = pd.DataFrame(fx_results)
    fx_df.to_csv(RESULTS / "fx_sensitivity.csv", index=False)
    print(fx_df[["fx_cost_per_leg", "cagr", "sharpe", "total_costs", "final_value"]].to_string())

    return wf


# ════════════════════════════════════════════════════════════════════
#  ETAP 7 — Decision memo
# ════════════════════════════════════════════════════════════════════

def etap7(cfg, baseline_summary, optimal_dbs, universe_comp, wf_result, prices, brokers):
    print_header("ETAP 7: Rekomendacja końcowa")

    cap = cfg["portfolio"]["initial_capital_pln"]
    u5 = cfg["universes"]["U5"]
    risky = [t for t in u5["risky"] if t in prices.columns]
    safe = [t for t in u5["safe"] if t in prices.columns]

    # Contribution scenarios
    print("\n  Scenariusze z regularnymi wpłatami:")
    contribution_results = []
    for contrib in cfg["portfolio"]["contribution_scenarios"]:
        for bname, broker in brokers.items():
            db = optimal_dbs.get(bname, {}).get("deadband", 0.03)
            res = run_gem(prices, broker, risky, safe, cap,
                          deadband=db, monthly_contribution=contrib)
            m = compute_all(res.equity, label=f"{bname}_contrib={contrib}")
            m["broker"] = bname
            m["monthly_contribution"] = contrib
            m["optimal_deadband"] = db
            m["rotations"] = res.num_rotations
            m["total_costs"] = res.total_costs
            m["total_taxes"] = res.total_taxes
            contribution_results.append(m)

    contrib_df = pd.DataFrame(contribution_results)
    contrib_df.to_csv(RESULTS / "contribution_scenarios.csv", index=False)

    # Find crossover point: at what capital does BOSSA beat XTB?
    print("\n  Szukanie progu przejścia XTB -> BOSSA...")
    crossover_capital = None
    test_capitals = list(range(5000, 200001, 5000))
    crossover_data = []
    for test_cap in test_capitals:
        results_by_broker = {}
        for bname, broker in brokers.items():
            if bname not in ("xtb_ike", "bossa_ike_promo"):
                continue
            db = optimal_dbs.get(bname, {}).get("deadband", 0.03)
            res = run_gem(prices, broker, risky, safe, test_cap, deadband=db)
            m = compute_all(res.equity, label=bname)
            results_by_broker[bname] = m
            crossover_data.append(dict(
                capital=test_cap, broker=bname,
                cagr=m["cagr"], final_value=m["final_value"],
            ))

        if "xtb_ike" in results_by_broker and "bossa_ike_promo" in results_by_broker:
            if (results_by_broker["bossa_ike_promo"]["final_value"] >
                    results_by_broker["xtb_ike"]["final_value"]):
                if crossover_capital is None:
                    crossover_capital = test_cap

    crossover_df = pd.DataFrame(crossover_data)
    crossover_df.to_csv(RESULTS / "crossover_analysis.csv", index=False)

    if crossover_capital:
        print(f"    BOSSA > XTB od kapitału ~{crossover_capital:,} PLN")
    else:
        print("    BOSSA nie przewyższa XTB w testowanym zakresie"
              " (lub jest lepsze od samego początku)")

    # plot crossover
    fig, ax = plt.subplots(figsize=(12, 6))
    for bname in ("xtb_ike", "bossa_ike_promo"):
        sub = crossover_df[crossover_df["broker"] == bname]
        if not sub.empty:
            ax.plot(sub["capital"], sub["final_value"], label=bname, linewidth=1.5)
    if crossover_capital:
        ax.axvline(crossover_capital, color="red", linestyle="--", alpha=0.7,
                   label=f"Crossover ~{crossover_capital:,} PLN")
    ax.set_xlabel("Kapitał początkowy (PLN)")
    ax.set_ylabel("Wartość końcowa (PLN)")
    ax.set_title("XTB vs BOSSA — próg przejścia wg kapitału")
    ax.legend()
    ax.grid(True, alpha=0.3)
    save_fig(fig, "crossover_xtb_vs_bossa.png")

    # Generate decision memo
    _write_decision_memo(cfg, baseline_summary, optimal_dbs, universe_comp,
                         wf_result, crossover_capital, contrib_df)


def _write_decision_memo(cfg, baseline, optimal_dbs, universe_comp,
                         wf_result, crossover_capital, contrib_df):
    cap = cfg["portfolio"]["initial_capital_pln"]

    # Determine recommended broker
    xtb_metrics = baseline[baseline["broker"] == "xtb_ike"].iloc[0] if "xtb_ike" in baseline["broker"].values else None
    bossa_metrics = baseline[baseline["broker"] == "bossa_ike_promo"].iloc[0] if "bossa_ike_promo" in baseline["broker"].values else None

    if xtb_metrics is not None and bossa_metrics is not None:
        if xtb_metrics["final_value"] > bossa_metrics["final_value"]:
            rec_broker = "XTB IKE"
            rec_reason = (f"Przy kapitale {cap:.0f} PLN, akcje ułamkowe XTB kompensują "
                          f"koszt FX (wartość końcowa {xtb_metrics['final_value']:.0f} "
                          f"vs {bossa_metrics['final_value']:.0f} PLN na BOSSA).")
        else:
            rec_broker = "BOSSA IKE"
            rec_reason = (f"Brak kosztów FX na BOSSA daje lepszy wynik nawet przy "
                          f"{cap:.0f} PLN kapitału.")
    else:
        rec_broker = "XTB IKE"
        rec_reason = "Brak danych porównawczych."

    # recommended deadband
    xtb_db = optimal_dbs.get("xtb_ike", {}).get("deadband", 0.03)
    bossa_db = optimal_dbs.get("bossa_ike_promo", {}).get("deadband", 0.0)

    # recommended universe
    if universe_comp is not None and not universe_comp.empty:
        best_univ = universe_comp.loc[universe_comp["sharpe"].idxmax()]
        rec_universe = best_univ["universe"]
        rec_univ_detail = (f"{rec_universe} ({int(best_univ['n_etfs'])} ETF-ów): "
                           f"Sharpe={best_univ['sharpe']:.2f}, CAGR={best_univ['cagr']:.2%}")
    else:
        rec_universe = "U5"
        rec_univ_detail = "Brak danych porównawczych."

    # OOS validation
    if wf_result and "folds" in wf_result and not wf_result["folds"].empty:
        avg_oos_ret = wf_result["folds"]["oos_return"].mean()
        avg_db = np.mean(wf_result["selected_deadbands"]) if wf_result["selected_deadbands"] else 0
        oos_note = (f"Średni OOS return per fold: {avg_oos_ret:.2%}. "
                    f"Średni wybrany deadband: {avg_db:.3f}.")
    else:
        oos_note = "Za mało danych na pełną walidację walk-forward."

    memo = f"""# Rekomendacja końcowa — GEM na IKE

## Stan portfela
- Kapitał: {cap:,.0f} PLN
- Obecny koszyk: U5 (CNDX.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L

## 1. Broker: {rec_broker}

{rec_reason}

### Warunek migracji
"""
    if crossover_capital:
        memo += f"""- Gdy kapitał na IKE przekroczy ~{crossover_capital:,} PLN, rozważ migrację do BOSSA IKE.
- Przy BOSSA eliminujesz koszty FX (~1% na rotację), co deklasuje cash drag z braku frakcji.
"""
    else:
        memo += "- BOSSA jest lepsze od samego początku (lub brak jednoznacznego crossovera w danych).\n"

    memo += f"""
## 2. Optymalny deadband

| Broker | Deadband |
|--------|----------|
| XTB IKE | {xtb_db:.3f} ({xtb_db*100:.1f}%) |
| BOSSA IKE | {bossa_db:.3f} ({bossa_db*100:.1f}%) |

Deadband chroni przed whipsawingiem i kompensuje koszty transakcyjne.
Przy XTB wyższy próg jest konieczny ze względu na 1% koszt FX na rotację.

## 3. Uniwersum ETF

Rekomendowane: **{rec_universe}**
{rec_univ_detail}

## 4. Walidacja Out-of-Sample

{oos_note}

## 5. Scenariusze z regularnymi wpłatami

"""
    if not contrib_df.empty:
        pivot = contrib_df.pivot_table(
            index="monthly_contribution",
            columns="broker",
            values="final_value",
            aggfunc="first",
        )
        memo += pivot.to_markdown() + "\n"

    memo += """
## Podsumowanie decyzji

1. **Zostań na obecnym brokerze** jeśli spełnia warunek kosztowy, inaczej migruj.
2. **Ustaw deadband** na poziomie wskazanym powyżej.
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
    print("=" * 70)

    cfg = load_config()

    # build broker models
    brokers = {name: make_broker(bcfg) for name, bcfg in cfg["brokers"].items()}

    # ETAP 1 — data
    prices = etap1(cfg)

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

    # ETAP 2 — baseline
    baseline_summary = etap2(cfg, prices, brokers)

    # ETAP 3 — broker comparison with deadband sweep
    all_sweep = etap3(cfg, prices, brokers)

    # ETAP 4 — deadband calibration
    optimal_dbs, dyn_df = etap4(cfg, prices, brokers)

    # ETAP 5 — universe expansion (use XTB as primary broker)
    primary_broker_name = "xtb_ike"
    primary_broker = brokers[primary_broker_name]
    primary_db = optimal_dbs.get(primary_broker_name, {}).get("deadband", 0.03)
    universe_comp = etap5(cfg, prices, primary_broker, primary_db)

    # ETAP 6 — robustness
    wf_result = etap6(cfg, prices, daily_prices, primary_broker, primary_db)

    # ETAP 7 — decision
    etap7(cfg, baseline_summary, optimal_dbs, universe_comp, wf_result,
          prices, brokers)

    print_header("ANALIZA ZAKOŃCZONA")
    print(f"  Wyniki zapisane w: {RESULTS}")
    print(f"  Rekomendacja: {RESULTS / 'decision_memo.md'}")


if __name__ == "__main__":
    main()
