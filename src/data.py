"""Data fetching, cleaning, and validation for GEM backtest."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

from .config import ROOT

load_dotenv(ROOT / ".env")

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


GUS_API_KEY = os.environ.get("GUS_API_KEY", "")
GUS_CPI_VARIABLE_ID = 217230  # "ogółem" — CPI total, average annual index (prev year = 100)
GUS_CPI_CACHE = CACHE_DIR / "cpi_annual_cache.json"


def _fetch_cpi_from_api(years: list[int]) -> dict[int, float]:
    """Fetch average annual CPI from GUS BDL API (variable 217230)."""
    import json as _json
    try:
        import requests
    except ImportError:
        from urllib.request import Request, urlopen
        year_params = "&".join(f"year={y}" for y in years)
        url = (f"https://bdl.stat.gov.pl/api/v1/data/by-variable/{GUS_CPI_VARIABLE_ID}"
               f"?format=json&unit-level=0&{year_params}")
        req = Request(url, headers={"X-ClientId": GUS_API_KEY})
        with urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode())
    else:
        year_params = "&".join(f"year={y}" for y in years)
        url = (f"https://bdl.stat.gov.pl/api/v1/data/by-variable/{GUS_CPI_VARIABLE_ID}"
               f"?format=json&unit-level=0&{year_params}")
        resp = requests.get(url, headers={"X-ClientId": GUS_API_KEY}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

    cpi = {}
    for result in data.get("results", []):
        for v in result.get("values", []):
            year = int(v["year"])
            cpi[year] = round((v["val"] - 100) / 100, 4)
    return cpi


def load_cpi_annual(min_year: int = 2000, max_year: int = 2025) -> dict[int, float]:
    """Load average annual CPI rates {year: rate} from GUS BDL API.

    Results are cached locally in cpi_annual_cache.json.
    For years not yet published by the API (e.g. current year),
    the last available CPI is carried forward.
    """
    import json as _json

    years = list(range(min_year, max_year + 1))

    # Try cache first
    if GUS_CPI_CACHE.exists():
        with open(GUS_CPI_CACHE, "r") as f:
            cached = {int(k): v for k, v in _json.load(f).items()}
        missing_years = [y for y in years if y not in cached]
        if not missing_years:
            return {y: cached[y] for y in years if y in cached}
    else:
        cached = {}
        missing_years = years

    # Fetch from API
    api_data = {}
    try:
        api_data = _fetch_cpi_from_api(years)
        merged = {**cached, **api_data}
        with open(GUS_CPI_CACHE, "w") as f:
            _json.dump(merged, f, indent=2)
    except Exception as exc:
        warnings.warn(f"GUS API unavailable ({exc}), using cached data only")

    combined = {**cached, **api_data}

    # For years not yet published, carry forward the last known CPI
    if combined:
        last_known = max(y for y in combined)
        for y in years:
            if y not in combined and y > last_known:
                combined[y] = combined[last_known]

    return {y: combined[y] for y in years if y in combined}
