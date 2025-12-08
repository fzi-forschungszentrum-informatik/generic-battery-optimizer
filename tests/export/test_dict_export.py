"""
Test dictionary export of model results.

This test set tests the export of model results to dictionaries with various
devices, profiles and time series.
"""

import pandas as pd
import pytest
from battery_optimizer.export import Exporter
from battery_optimizer.model import Model
from battery_optimizer.profiles.battery import Battery
from battery_optimizer.solver import Solver
from tests.helpers import find_solver


class TestPowerConversion:
    """
    Test conversion of energy to power with different period lengths.

    This test ensures that energy values are correctly converted to power
    values based on the length of the time periods.
    Time series with hourly time periods are trivial to convert from energy
    to power, but time series with non-hourly periods need special attention.
    """

    solver = Solver(find_solver(), tee=True)
    time_series_1h = pd.date_range("2023-01-01", periods=6, freq="h")
    time_series_15min = pd.date_range(
        "2023-01-01", periods=6 * 4, freq="15min"
    )
    time_series_mixed = pd.to_datetime(
        [
            "2023-01-01 00:00",
            "2023-01-01 00:15",
            "2023-01-01 00:20",
            "2023-01-01 00:30",
            "2023-01-01 01:00",
            "2023-01-01 02:00",
            "2023-01-01 02:30",
            "2023-01-01 03:00",
            "2023-01-01 04:00",
            "2023-01-01 04:55",
            "2023-01-01 05:00",
            "2023-01-01 05:30",
            "2023-01-01 06:00",
        ]
    )

    ev = Battery(
        name="EV",
        capacity=5000,
        max_charge_power=1000,
        start_soc=0,
        end_soc=1,
        # BUG should not be needed. Model should infer this if end_soc is
        # specified but no end soc time
        end_soc_time=time_series_1h[-1],
    )

    def test_hourly_series(self):
        """
        Test hourly time series conversion.

        With a battery charging process (EV) this test checks that the result
        shows expected power behavior of the power profile and the battery.
        Prices increase to ensure that the battery charges at the start
        of the time series when prices are low.
        """
        prices = {index: index.hour + 1 for index in self.time_series_1h}
        power = {index: 10000 for index in self.time_series_1h}
        power[self.time_series_1h[-1]] = 0

        model = Model(self.time_series_1h)
        model.add_battery(self.ev)
        model.add_buy_profile("buy", power, prices)

        model.add_energy_paths()
        model.generate_objective()

        self.solver.solve(model.model)

        export = Exporter(model).to_dict()

        expected_buy = {index: 1000 for index in self.time_series_1h[0:5]}
        expected_buy.update({index: 0 for index in self.time_series_1h[5:]})

        assert export["buy"] == expected_buy
        assert export["EV"] == {i: v * -1 for i, v in expected_buy.items()}

    def test_15min_series(self):
        """
        Test 15-minute time series conversion.

        With a battery charging process (EV) this test checks that the result
        shows expected power behavior of the power profile and the battery.
        Prices increase to ensure that the battery charges at the start
        of the time series when prices are low.
        """
        prices = {
            index: index.hour + 1 + (1 / (60 - index.minute))
            for index in self.time_series_15min
        }
        power = {index: 10000 for index in self.time_series_15min}
        power[self.time_series_15min[-1]] = 0

        model = Model(self.time_series_15min)
        model.add_battery(self.ev)
        model.add_buy_profile("buy", power, prices)

        model.add_energy_paths()
        model.generate_objective()

        self.solver.solve(model.model)

        export = Exporter(model).to_dict()

        expected_buy = {index: 1000 for index in self.time_series_15min[0:20]}
        expected_buy.update({i: 0 for i in self.time_series_15min[20:]})

        assert export["buy"] == expected_buy
        assert export["EV"] == {i: v * -1 for i, v in expected_buy.items()}

    def test_mixed_series(self):
        """
        Test mixed time series conversion.

        With a battery charging process (EV) this test checks that the result
        shows expected power behavior of the power profile and the battery.
        Prices increase to ensure that the battery charges at the start
        of the time series when prices are low.
        """
        prices = {
            index: index.hour + 1 + (1 / (60 - index.minute))
            for index in self.time_series_mixed
        }
        power = {index: 10000 for index in self.time_series_mixed}
        power[self.time_series_mixed[-1]] = 0

        model = Model(self.time_series_mixed)
        model.add_battery(self.ev)
        model.add_buy_profile("buy", power, prices)

        model.add_energy_paths()
        model.generate_objective()

        self.solver.solve(model.model)

        export = Exporter(model).to_dict()

        expected_buy = {i: 1000 for i in self.time_series_mixed[0:10]}
        expected_buy.update({i: 0 for i in self.time_series_mixed[10:]})

        assert export["buy"] == pytest.approx(
            expected_buy, rel=1e-12, abs=1e-12
        )
        assert export["EV"] == pytest.approx(
            {i: v * -1 for i, v in expected_buy.items()}, rel=1e-12, abs=1e-12
        )
