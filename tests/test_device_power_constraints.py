from datetime import datetime
import pandas as pd
import pytest
from helpers import find_solver
from battery_optimizer.export.model import Exporter
from battery_optimizer.model import Model
from battery_optimizer.solver import Solver
from battery_optimizer.profiles.battery_profile import Battery


class TestDevicePowerConstraints:
    time_series = pd.DatetimeIndex(
        [
            datetime(2021, 1, 1, 8, 0, 0),
            datetime(2021, 1, 1, 9, 0, 0),
            datetime(2021, 1, 1, 10, 0, 0),
        ]
    )

    @pytest.mark.parametrize(
        "block1, block2",
        [
            ("battery_block", "sell_block"),
            ("buy_block", "battery_block"),
        ],
    )
    def test_buy_sell_battery_sell_restriction(self, block1, block2):
        """
        Test the restriction of simultaneous buying and selling of energy
        for a battery within an optimization model.

        This test verifies that the optimization model correctly applies
        constraints to prevent a battery from buying or selling energy
        even though this would be economically the best decision.
        It uses predefined buy and sell profiles, a battery configuration, and
        a time series to simulate the scenario.

        Args:
            block1 (str): The name of the first block to be
                          constrained in the optimization model.
            block2 (str): The name of the second block to be
                          constrained in the optimization model.

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

        Raises:
            AssertionError: If the resulting profiles do not match the expected
                            profiles.
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
                    "sell": [0, 0, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
        )
        pd.testing.assert_frame_equal(
            result[1],
            pd.DataFrame(
                data={
                    "buy": [0, 0, 0],
                    "sell": [0, 0, 0],
                },
                index=self.time_series,
            ),
            check_dtype=False,
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
        )

    @pytest.mark.parametrize(
        "power",
        range(0, 100 - 12, 10),
    )
    def test_consumption_from_pv_and_restrict_sell(self, power):
        """Home consumption from PV (rest (limited) sold to grid)"""
        pv_pwoer = {
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
        pv_block = opt.add_buy_profile("pv", pv_pwoer, pv_price)
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
            data={"pv": [7 + power, 12 + power, 0], "sell": [0, 0, 0]},
            index=self.time_series,
        )

        sell_result = pd.DataFrame(
            data={"pv": [0, 0, 0], "sell": [power, power, 0]},
            index=self.time_series,
        )

        fixed_consumption_result = pd.DataFrame(
            data={"fixed_consumption": [7, 12, 0]}, index=self.time_series
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(result[0], buy_result, check_dtype=False)
        pd.testing.assert_frame_equal(
            result[1], sell_result, check_dtype=False
        )
        pd.testing.assert_frame_equal(
            result[4], fixed_consumption_result, check_dtype=False
        )
