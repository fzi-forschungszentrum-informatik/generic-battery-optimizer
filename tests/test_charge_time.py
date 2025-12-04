"""
Unit tests for charge start and end time behavior of the battery.

Test cases:
- test_start_time: Tests that the battery starts charging only after the
  specified start time.
"""

from datetime import datetime
import unittest
import pandas as pd
from battery_optimizer import optimize
from battery_optimizer.profiles.battery import Battery
from tests.helpers import find_solver, get_profiles


class TestChargeTime(unittest.TestCase):
    """
    Tests for battery charge start and end time behavior.

    Tests the battery parameters start_soc_time and end_soc_time to ensure
    that the battery only charges within the specified time frame.
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

    def test_start_time(self):
        """
        Battery is charged from PV from 3rd time step.

        Test that the battery will not charge before the specified
        start_soc_time. This is the third time step in this test case.
        At and after this time step the battery should charge.
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

        fixed_consumption = {
            "fixed_consumption": pd.DataFrame(
                data={
                    "input_power": [3, 3, 3, 7, 0],
                    "input_price": [0, 0, 0, 0, 0],
                },
                index=self.time_series,
            )
        }

        sell = {
            "grid_sell": pd.DataFrame(
                data={
                    "input_power": [100, 100, 100, 100, 0],
                    "input_price": [4, 4, 5, 5, 0],
                },
                index=self.time_series,
            )
        }

        battery = Battery(
            capacity=10000,
            max_charge_power=10000,
            start_soc=0,
            start_soc_time=self.time_series[2],
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
                "pv": [5, 5, 5, 5, 0],
                "grid_buy": [0, 0, 0, 0, 0],
            },
            index=self.time_series,
        )

        fixed_consumption_result = pd.DataFrame(
            data={
                "fixed_consumption": [3, 3, 3, 7, 0],
            },
            index=self.time_series,
        )

        sell_result = pd.DataFrame(
            data={
                "grid_sell": [2, 2, 0, 0, 0],
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
