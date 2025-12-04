"""
Unit tests for minimum charge power behavior of the battery.

Test cases:
- test_min_charge_power: Tests that the battery charges only when available
  power is above the minimum charge power.
- test_charging_infeasible: Tests that the battery does not charge when the
  available power is below the minimum charge power.
"""

from datetime import datetime
import unittest
import pandas as pd
from battery_optimizer import optimize
from battery_optimizer.profiles.battery import Battery
from tests.helpers import find_solver, get_profiles


class TestMinChargePower(unittest.TestCase):
    """
    Tests for battery minimum charge power behavior.

    Test cases:
    - test_min_charge_power: Tests that the battery charges only when available
      power is above the minimum charge power.
    - test_charging_infeasible: Tests that the battery does not charge when the
      available power is below the minimum charge power.
    """
    time_series = pd.DatetimeIndex(
        [
            datetime(2021, 1, 1, 8, 0, 0),
            datetime(2021, 1, 1, 9, 0, 0),
            datetime(2021, 1, 1, 10, 0, 0),
            datetime(2021, 1, 1, 11, 0, 0),
            datetime(2021, 1, 1, 12, 0, 0),
        ]
    )

    def test_min_charge_power(self):
        """
        Battery is charged from PV above min charge power.

        Test that the battery only charges when the available power from PV
        is above the minimum charge power. In this test case the min charge
        power is set to 7. Therefore the battery should only charge in the
        second and third time step where the available power from PV is 10.
        In the first and fourth time step the battery should not charge since
        the available power is below the min charge power.
        """
        buy = {
            "pv": pd.DataFrame(
                data={
                    "input_power": [5, 10, 10, 5, 0],
                    "input_price": [0, 0, 0, 0, 0],
                },
                index=self.time_series,
            ),
            "grid_buy": pd.DataFrame(
                data={
                    "input_power": [100, 100, 100, 100, 0],
                    "input_price": [30, 30, 30, 30, 0],
                },
                index=self.time_series,
            ),
        }

        fixed_consumption = {
            "fixed_consumption": pd.DataFrame(
                data={
                    "input_power": [2, 2, 2, 21, 0],
                    "input_price": [0, 0, 0, 0, 0],
                },
                index=self.time_series,
            )
        }

        sell = {
            "grid_sell": pd.DataFrame(
                data={
                    "input_power": [100, 100, 100, 100, 0],
                    "input_price": [5, 5, 5, 5, 0],
                },
                index=self.time_series,
            )
        }

        battery = Battery(
            capacity=10000,
            max_charge_power=10000,
            start_soc=0,
            min_charge_power=7,
            max_discharge_power=10000,
        )

        result = optimize(
            buy_prices=get_profiles(self.time_series, buy),
            sell_prices=get_profiles(self.time_series, sell),
            fixed_consumption=get_profiles(
                self.time_series, fixed_consumption
            ),
            batteries=[battery],
            solver=find_solver(),
        )

        buy_result = pd.DataFrame(
            data={
                "pv": [5, 10, 10, 5, 0],
                "grid_buy": [0, 0, 0, 0, 0],
            },
            index=self.time_series,
        )

        fixed_consumption_result = pd.DataFrame(
            data={
                "fixed_consumption": [2, 2, 2, 21, 0],
            },
            index=self.time_series,
        )

        sell_result = pd.DataFrame(
            data={
                "grid_sell": [3, 0, 0, 0, 0],
            },
            index=self.time_series,
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(result[0], buy_result, check_dtype=False)
        pd.testing.assert_frame_equal(
            result[1], sell_result, check_dtype=False
        )
        pd.testing.assert_frame_equal(
            result[4], fixed_consumption_result, check_dtype=False
        )

    def test_charging_infeasible(self):
        """
        The battery will not be charged because min charge power is too high.

        Battery min charge power is 15, but available power from PV is max 10.
        Therefore the battery should not charge at all.
        Excess power should be sold to the grid.
        """
        buy = {
            "pv": pd.DataFrame(
                data={
                    "input_power": [5, 5, 5, 5, 0],
                    "input_price": [0, 0, 0, 0, 0],
                },
                index=self.time_series,
            ),
            "grid_buy": pd.DataFrame(
                data={
                    "input_power": [100, 100, 100, 100, 0],
                    "input_price": [30, 30, 30, 30, 0],
                },
                index=self.time_series,
            ),
        }

        sell = {
            "grid_sell": pd.DataFrame(
                data={
                    "input_power": [100, 100, 100, 100, 0],
                    "input_price": [5, 5, 5, 5, 0],
                },
                index=self.time_series,
            )
        }

        fixed_consumption = {
            "fixed_consumption": pd.DataFrame(
                data={
                    "input_power": [2, 2, 2, 14, 0],
                    "input_price": [0, 0, 0, 0, 0],
                },
                index=self.time_series,
            )
        }

        battery = Battery(
            capacity=10000,
            max_charge_power=10000,
            start_soc=0,
            min_charge_power=15,
            max_discharge_power=10000,
            name="Battery",
        )

        result = optimize(
            buy_prices=get_profiles(self.time_series, buy),
            sell_prices=get_profiles(self.time_series, sell),
            fixed_consumption=get_profiles(
                self.time_series, fixed_consumption
            ),
            batteries=[battery],
            solver=find_solver(),
        )

        buy_result = pd.DataFrame(
            data={
                "pv": [5, 5, 5, 5, 0],
                "grid_buy": [0, 0, 0, 9, 0],
            },
            index=self.time_series,
        )

        sell_result = pd.DataFrame(
            data={
                "grid_sell": [3, 3, 3, 0, 0],
            },
            index=self.time_series,
        )

        fixed_consumption_result = pd.DataFrame(
            data={
                "fixed_consumption": [2, 2, 2, 14, 0],
            },
            index=self.time_series,
        )

        battery_result = pd.DataFrame(
            data={
                "Battery": [0, 0, 0, 0, 0],
            },
            index=self.time_series,
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(result[0], buy_result, check_dtype=False)
        pd.testing.assert_frame_equal(
            result[1], sell_result, check_dtype=False
        )
        pd.testing.assert_frame_equal(
            result[2], battery_result, check_dtype=False
        )
        pd.testing.assert_frame_equal(
            result[4], fixed_consumption_result, check_dtype=False
        )
