"""
Tests for device power constraints in battery optimization models.

These tests verify that constraints for multiple devices (e.g., batteries,
buy/sell profiles) are correctly implemented in the optimization model.
"""

from typing import Literal
import pandas as pd
import pytest
from tests.helpers import find_solver
from battery_optimizer.export import Exporter
from battery_optimizer.model import Model
from battery_optimizer.solver import Solver
from battery_optimizer.profiles.battery import Battery
from pandas.testing import assert_frame_equal


class TestDevicePowerConstraints:
    """
    Tests for multi-device power constraints.

    Test the constraint_device_power(a, b) method of the optimization model
    to ensure that it correctly restricts simultaneous power flows between
    multiple devices (e.g., batteries, buy/sell profiles) within the model.
    """
    time_series = pd.date_range(
        start="2021-01-01 08:00:00", end="2021-01-01 10:00:00", freq="h"
    )

    @pytest.mark.parametrize(
        "block1, block2",
        [
            ("battery_block", "sell_block"),
            ("buy_block", "battery_block"),
        ],
    )
    def test_buy_sell_battery_sell_restriction(
        self,
        block1: Literal["battery_block"] | Literal["buy_block"],
        block2: Literal["sell_block"] | Literal["battery_block"],
    ):
        """
        Test the restriction of buying and selling of energy for a battery.

        This test verifies that the optimization model correctly applies
        constraints to prevent a battery from buying or selling energy
        even though this would be economically the best decision.
        It uses predefined buy and sell profiles, a battery configuration, and
        a time series to simulate the scenario.

        Test Steps:
        1. Define a time series for the optimization.
        2. Create expected buy and sell profiles with energy and price
            data.
        3. Configure a battery with specific parameters such as capacity
            and efficiency.
        4. Initialize the optimization model and add the buy, sell, and
            battery profiles.
        5. Apply a constraint to restrict simultaneous buying and selling
            using the `constraint_device_power` method.
        6. Solve the optimization model and export the results.
        7. Compare the resulting buy, sell, and battery profiles with
            expected results using assertions.

        Assertions:
        - The resulting buy and sell profiles should match the expected
            profiles, ensuring no simultaneous buying and selling occurs.
        - The resulting battery power and state of charge (SOC) profiles
            should match the expected profiles.

        Parameters
        ----------
        block1 :  str
            The name of the first block to be constrained in the optimization
            model.
        block2 : str
            The name of the second block to be constrained in the optimization
            model.

        Raises
        ------
        AssertionError
            If the resulting profiles do not match the expected profiles.
        """
        # Input data
        buy_power = {
            self.time_series[0]: 10,
            self.time_series[1]: 10,
            self.time_series[2]: 0,
        }
        buy_price = {
            self.time_series[0]: 1,
            self.time_series[1]: 4,
            self.time_series[2]: 0,
        }

        sell = {
            self.time_series[0]: 10,
            self.time_series[1]: 10,
            self.time_series[2]: 0,
        }
        sell_price = {
            self.time_series[0]: 0,
            self.time_series[1]: 3,
            self.time_series[2]: 0,
        }

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

        # Optimization
        opt = Model(self.time_series)
        buy_block = opt.add_buy_profile("buy", buy_power, buy_price)
        sell_block = opt.add_sell_profile("sell", sell, sell_price)
        battery_block = opt.add_battery(battery)
        opt.add_energy_paths()

        # Apply constraint
        opt.constraint_device_power(locals()[block1], locals()[block2], 0)

        opt.generate_objective()
        Solver(find_solver()).solve(opt.model)
        export = Exporter(opt).to_df()
        result = (
            export.to_buy(),
            export.to_sell(),
            export.to_battery_power(),
            export.to_battery_soc(),
            export.to_fixed_consumption(),
            export.to_heat_pump_power(),
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(
            result[0],
            pd.DataFrame(
                data={
                    "buy": [0, 0, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )
        pd.testing.assert_frame_equal(
            result[1],
            pd.DataFrame(
                data={
                    "sell": [0, 0, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )

        # Assert battery profiles
        pd.testing.assert_frame_equal(
            result[2],
            pd.DataFrame(
                data={
                    "test-battery": [0, 0, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )

    @pytest.mark.parametrize("power", range(0, 100 - 12, 10))
    def test_consumption_from_pv_and_restrict_sell(self, power: int):
        """
        Home consumption from PV (rest (limited) sold to grid).

        This test verifies that the optimization model correctly applies
        constraints to limit the power sold from PV to the grid while
        ensuring that home consumption energy is provided by the PV system
        because it is the cheapest energy option.

        Parameters
        ----------
        power : int
            The maximum power that can be sold from the PV system to the grid.

        Raises
        ------
        AssertionError
            If the resulting profiles do not match the expected profiles.
        """
        pv_power = {
            self.time_series[0]: 100,
            self.time_series[1]: 100,
            self.time_series[2]: 0,
        }
        pv_price = {
            self.time_series[0]: 0,
            self.time_series[1]: 0,
            self.time_series[2]: 0,
        }

        sell_power = {
            self.time_series[0]: 100,
            self.time_series[1]: 100,
            self.time_series[2]: 0,
        }

        sell_price = {
            self.time_series[0]: 30,
            self.time_series[1]: 30,
            self.time_series[2]: 0,
        }

        fixed_consumption = {
            self.time_series[0]: 7,
            self.time_series[1]: 12,
            self.time_series[2]: 0,
        }

        # Optimization
        opt = Model(self.time_series)
        pv_block = opt.add_buy_profile("pv", pv_power, pv_price)
        sell_block = opt.add_sell_profile("sell", sell_power, sell_price)
        opt.add_fixed_consumption("fixed_consumption", fixed_consumption)
        opt.add_energy_paths()

        # Apply constraint
        opt.constraint_device_power(pv_block, sell_block, power)

        opt.generate_objective()
        Solver(find_solver()).solve(opt.model)
        export = Exporter(opt).to_df()
        result = (
            export.to_buy(),
            export.to_sell(),
            export.to_battery_power(),
            export.to_battery_soc(),
            export.to_fixed_consumption(),
            export.to_heat_pump_power(),
        )

        buy_result = pd.DataFrame(
            data={"pv": [7 + power, 12 + power, 0]},
            index=self.time_series,
        )

        sell_result = pd.DataFrame(
            data={"sell": [power, power, 0]},
            index=self.time_series,
        )

        fixed_consumption_result = pd.DataFrame(
            data={"fixed_consumption": [7, 12, 0]}, index=self.time_series
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(
            result[0],
            buy_result,
            check_dtype=False,
            check_freq=False,
        )
        pd.testing.assert_frame_equal(
            result[1],
            sell_result,
            check_dtype=False,
            check_freq=False,
        )
        pd.testing.assert_frame_equal(
            result[4],
            fixed_consumption_result,
            check_dtype=False,
            check_freq=False,
        )

    def test_multi_source_restriction(self):
        """
        Test restriction of multiple sources (PV, battery, grid).

        This test verifies that the optimization model correctly applies
        constraints to limit the combined power output from multiple sources
        (PV and battery) to a sell profile, ensuring that the total power
        sold does not exceed a specified limit.

        Raises
        ------
        AssertionError
            If the resulting profiles do not match the expected profiles.
        """
        pv_power = {
            self.time_series[0]: 5,
            self.time_series[1]: 20,
            self.time_series[2]: 0,
        }
        pv_price = {
            self.time_series[0]: 0,
            self.time_series[1]: 0,
            self.time_series[2]: 0,
        }

        sell_power = {
            self.time_series[0]: 100,
            self.time_series[1]: 100,
            self.time_series[2]: 0,
        }
        sell_price = {
            self.time_series[0]: 30,
            self.time_series[1]: 30,
            self.time_series[2]: 5,
        }

        # Optimization
        opt = Model(self.time_series)
        pv_block = opt.add_buy_profile("pv", pv_power, pv_price)
        battery_block = opt.add_battery(
            Battery(
                name="test-battery",
                start_soc=1,
                capacity=10000,
                max_charge_power=10000,
                max_discharge_power=10000,
                charge_efficiency=0.5,
                discharge_efficiency=0.5,
            )
        )
        sell_block = opt.add_sell_profile("sell", sell_power, sell_price)
        opt.add_energy_paths()

        # Apply constraint
        opt.constraint_device_power([pv_block, battery_block], sell_block, 20)

        opt.generate_objective()
        Solver(find_solver()).solve(opt.model)
        export = Exporter(opt).to_df()
        buy_result = export.to_buy()
        sell_result = export.to_sell()
        battery_result = export.to_battery_power()

        assert_frame_equal(
            buy_result,
            pd.DataFrame(
                data={
                    "pv": [5, 20, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )

        assert_frame_equal(
            battery_result,
            pd.DataFrame(
                data={
                    "test-battery": [-15, 0, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )

        assert_frame_equal(
            sell_result,
            pd.DataFrame(
                data={
                    "sell": [20, 20, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )


class TestSourcePowerConstraints:
    """
    Test that method constraint_device_power_source is implemented correctly.

    The method limits all power from a list of source devices to a maximum
    power value for all sink devices combined.
    """

    time_series = pd.date_range(
        start="2021-01-01 08:00:00", end="2021-01-01 10:00:00", freq="h"
    )

    def test_single_source_single_sink(self):
        """
        Test single source and single sink power constraint.

        Test that a model with a single source (PV) and a single sink (grid)
        correctly applies a power constraint between them. The PV system can
        provide more power than allowed to be sold to the grid.

        Raises
        ------
        AssertionError
            If the resulting profiles do not match the expected profiles.
        """
        pv_power = {
            self.time_series[0]: 50,
            self.time_series[1]: 50,
            self.time_series[2]: 0,
        }
        pv_price = {
            self.time_series[0]: 0,
            self.time_series[1]: 0,
            self.time_series[2]: 0,
        }

        sell_power = {
            self.time_series[0]: 100,
            self.time_series[1]: 100,
            self.time_series[2]: 0,
        }
        sell_price = {
            self.time_series[0]: 30,
            self.time_series[1]: 30,
            self.time_series[2]: 0,
        }

        # Optimization
        opt = Model(self.time_series)
        pv_block = opt.add_buy_profile("pv", pv_power, pv_price)
        sell_block = opt.add_sell_profile("sell", sell_power, sell_price)
        opt.add_energy_paths()

        # Apply constraint
        opt.constraint_device_power_source(pv_block, 20)

        opt.generate_objective()
        Solver(find_solver()).solve(opt.model)
        export = Exporter(opt).to_df()
        buy_result = export.to_buy()
        sell_result = export.to_sell()

        assert_frame_equal(
            buy_result,
            pd.DataFrame(
                data={
                    "pv": [20, 20, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )

        assert_frame_equal(
            sell_result,
            pd.DataFrame(
                data={
                    "sell": [20, 20, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )


class TestSinkPowerConstraints:
    """
    Test that method constraint_device_power_sink is implemented correctly.

    The method restricts a list of sink devices to a maximum power value for
    all source devices combined.
    """

    time_series = pd.date_range(
        start="2021-01-01 08:00:00", end="2021-01-01 10:00:00", freq="h"
    )

    def test_single_source_single_sink(self):
        """
        Test single source and single sink power constraint.

        Test that a model with a single source (PV) and a single sink (grid)
        correctly applies a power constraint between them. The PV system can
        provide more power than allowed to be sold to the grid.

        Raises
        ------
        AssertionError
            If the resulting profiles do not match the expected profiles.
        """
        pv_power = {
            self.time_series[0]: 50,
            self.time_series[1]: 50,
            self.time_series[2]: 0,
        }
        pv_price = {
            self.time_series[0]: 0,
            self.time_series[1]: 0,
            self.time_series[2]: 0,
        }

        sell_power = {
            self.time_series[0]: 100,
            self.time_series[1]: 100,
            self.time_series[2]: 0,
        }
        sell_price = {
            self.time_series[0]: 30,
            self.time_series[1]: 30,
            self.time_series[2]: 0,
        }

        # Optimization
        opt = Model(self.time_series)
        pv_block = opt.add_buy_profile("pv", pv_power, pv_price)
        sell_block = opt.add_sell_profile("sell", sell_power, sell_price)
        opt.add_energy_paths()

        # Apply constraint
        opt.constraint_device_power_sink(sell_block, 20)

        opt.generate_objective()
        Solver(find_solver()).solve(opt.model)
        export = Exporter(opt).to_df()
        buy_result = export.to_buy()
        sell_result = export.to_sell()

        assert_frame_equal(
            buy_result,
            pd.DataFrame(
                data={
                    "pv": [20, 20, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )

        assert_frame_equal(
            sell_result,
            pd.DataFrame(
                data={
                    "sell": [20, 20, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
            check_freq=False,
        )
