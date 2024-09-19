from datetime import datetime
import unittest
import pandas as pd
from battery_optimizer import optimize
from battery_optimizer.profiles.battery_profile import Battery
from helpers import get_profiles


class TestChargeTime(unittest.TestCase):
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
        """Battery is charged from PV from 3rd timestep"""
        buy = {
            "pv": pd.DataFrame(
                data={
                    "input_power": [5, 5, 5, 5, 0],
                    "input_price": [0, 0, 0, 0, 0],
                },
                index=self.time_series,
            ),
            "grid": pd.DataFrame(
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
            "grid": pd.DataFrame(
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
        )

        buy_result = pd.DataFrame(
            data={"pv": [5, 5, 5, 5, 0], "grid": [0, 0, 0, 0, 0]},
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
                "grid": [2, 2, 0, 0, 0],
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
