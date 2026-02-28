"""Data fetching, cleaning, and validation for GEM backtest."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from .config import ROOT

CACHE_DIR = ROOT / "data_cache"


def fetch_prices(
    tickers: list[str],
    start: str = "2012-01-01",
    end: str = "2026-02-28",
    use_cache: bool = True,
) -> pd.DataFrame:
    """Download adjusted close prices for *tickers*, return monthly DataFrame.

    Prices are resampled to month-end business day.  Results are cached
    locally so repeated runs are fast.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"prices_{start}_{end}.csv"

    if use_cache and cache_file.exists():
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        missing = [t for t in tickers if t not in df.columns]
        if not missing:
            return df[tickers]

    raw_frames: dict[str, pd.Series] = {}
    for ticker in tickers:
        try:
            data = yf.download(
                ticker,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
            )
            if data.empty:
                warnings.warn(f"No data for {ticker}")
                continue
            close = data["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            raw_frames[ticker] = close
        except Exception as exc:
            warnings.warn(f"Failed to fetch {ticker}: {exc}")

    if not raw_frames:
        raise RuntimeError("Could not download any price data")

    daily = pd.DataFrame(raw_frames)
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()

    monthly = daily.resample("BME").last().dropna(how="all")
    monthly.to_csv(cache_file)
    return monthly


def validate_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Return a diagnostic DataFrame: start, end, count, gaps per ticker."""
    records = []
    for col in df.columns:
        s = df[col].dropna()
        if s.empty:
            records.append(dict(ticker=col, start=None, end=None, months=0, gaps=0))
            continue
        full_range = pd.date_range(s.index.min(), s.index.max(), freq="BME")
        gaps = len(full_range) - len(s)
        records.append(dict(
            ticker=col,
            start=s.index.min().strftime("%Y-%m"),
            end=s.index.max().strftime("%Y-%m"),
            months=len(s),
            gaps=gaps,
        ))
    return pd.DataFrame(records).set_index("ticker")


def common_window(df: pd.DataFrame) -> pd.DataFrame:
    """Trim to the longest contiguous window where all columns have data."""
    return df.dropna()
