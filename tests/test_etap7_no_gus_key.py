"""ETAP 7 keeps going when the CPI series is empty."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import run_all
import src.data as data
from src.broker import make_broker
from src.config import load_config
from run_all import etap7


class Etap7WithoutGusKeyTest(unittest.TestCase):
    def setUp(self):
        self._saved_key = data.GUS_API_KEY
        self._saved_cache = data.GUS_CPI_CACHE
        self._had_env = "GUS_API_KEY" in os.environ
        self._env_value = os.environ.get("GUS_API_KEY")
        os.environ.pop("GUS_API_KEY", None)
        data.GUS_API_KEY = ""
        self._tmp = tempfile.TemporaryDirectory()
        self.results = Path(self._tmp.name)
        data.GUS_CPI_CACHE = self.results / "cpi_annual_cache.json"

    def tearDown(self):
        data.GUS_API_KEY = self._saved_key
        data.GUS_CPI_CACHE = self._saved_cache
        if self._had_env:
            os.environ["GUS_API_KEY"] = self._env_value
        else:
            os.environ.pop("GUS_API_KEY", None)
        self._tmp.cleanup()

    def test_etap7_continues_when_cpi_series_is_empty(self):
        self.assertNotIn("GUS_API_KEY", os.environ)
        self.assertFalse(data.GUS_CPI_CACHE.exists())

        saved_results = run_all.RESULTS
        run_all.RESULTS = self.results
        try:
            cfg = load_config()
            brokers = {name: make_broker(bcfg) for name, bcfg in cfg["brokers"].items()}
            tickers = cfg["universes"]["U5"]["risky"] + cfg["universes"]["U5"]["safe"]
            index = pd.date_range("2016-01-31", periods=36, freq="BME")
            ramp = np.linspace(0, 1, len(index))
            prices = pd.DataFrame(
                {ticker: 100 * (1 + (i + 1) * 0.15 * ramp) for i, ticker in enumerate(tickers)},
                index=index,
            )
            baseline = pd.DataFrame(
                [
                    {"broker": "xtb_ike", "final_value": 1000.0},
                    {"broker": "bossa_ike_promo", "final_value": 1100.0},
                    {"broker": "mbank_ike", "final_value": 1050.0},
                ]
            )
            optimal_dbs = {name: {"deadband": 0.03} for name in brokers}
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                etap7(
                    cfg,
                    baseline,
                    optimal_dbs,
                    None,
                    None,
                    None,
                    prices,
                    brokers,
                    None,
                    None,
                )
        finally:
            run_all.RESULTS = saved_results

        text = stdout.getvalue()
        self.assertIn("Brak danych CPI", text)
        self.assertIn("bez rewaloryzacji", text)
        self.assertNotIn("Traceback", text)
        self.assertTrue((self.results / "decision_memo.md").is_file())
        scenarios = pd.read_csv(self.results / "contribution_scenarios.csv")
        self.assertFalse(scenarios.empty)
        self.assertTrue(
            np.allclose(scenarios["final_contribution"], scenarios["base_contribution"])
        )


if __name__ == "__main__":
    unittest.main()
