"""
Test the write_excel export method.

This test set tests that write_excel correctly exports model results to an
Excel file without raising AttributeError for missing model attributes.
"""

import os
import tempfile

import pandas as pd
import pytest
from battery_optimizer.export import Exporter
from battery_optimizer.model import Model
from battery_optimizer.profiles.battery import Battery
from battery_optimizer.solver import Solver
from tests.helpers import find_solver


class TestWriteExcel:
    """Test the write_excel export method."""

    solver = Solver(find_solver(), tee=False)
    time_series = pd.date_range(
        start="2021-01-01 08:00:00", end="2021-01-01 10:00:00", freq="h"
    )
    battery = Battery(
        name="test-battery",
        start_soc=0,
        end_soc=0,
        capacity=10000,
        max_charge_power=10000,
        max_discharge_power=10000,
        charge_efficiency=1,
        discharge_efficiency=1,
    )
    buy_power = {t: 10 for t in time_series}
    buy_price = {t: 1 for t in time_series}

    def test_write_excel_does_not_raise_attribute_error(self):
        """
        Test that write_excel does not raise AttributeError.

        Regression test for the bug where write_excel accessed
        self._model.energy_sinks and self._model.energy_sources, which are not
        defined on Model, causing AttributeError at runtime.
        """
        opt = Model(self.time_series)
        opt.add_buy_profile("buy", self.buy_power, self.buy_price)
        opt.add_battery(self.battery)
        opt.add_energy_paths()
        opt.generate_objective()
        self.solver.solve(opt.model)

        with tempfile.NamedTemporaryFile(
            suffix=".xlsx", delete=False
        ) as tmp_file:
            fname = tmp_file.name

        try:
            # This must not raise AttributeError for energy_sinks/energy_sources
            Exporter(opt).write_excel(fname)
            assert os.path.exists(fname)
        finally:
            if os.path.exists(fname):
                os.unlink(fname)

    def test_write_excel_creates_energy_matrix_sheets(self):
        """
        Test that write_excel creates energy matrix sheets in the Excel file.

        Each timestamp in the model should produce an energy matrix sheet.
        """
        opt = Model(self.time_series)
        opt.add_buy_profile("buy", self.buy_power, self.buy_price)
        opt.add_battery(self.battery)
        opt.add_energy_paths()
        opt.generate_objective()
        self.solver.solve(opt.model)

        with tempfile.NamedTemporaryFile(
            suffix=".xlsx", delete=False
        ) as tmp_file:
            fname = tmp_file.name

        try:
            Exporter(opt).write_excel(fname)
            # Read the generated Excel file and verify energy matrix sheets
            xl = pd.ExcelFile(fname)
            energy_matrix_sheets = [
                s for s in xl.sheet_names if s.startswith("E-Matrix")
            ]
            # One sheet per timestamp in the time series
            assert len(energy_matrix_sheets) == len(self.time_series)
        finally:
            if os.path.exists(fname):
                os.unlink(fname)
