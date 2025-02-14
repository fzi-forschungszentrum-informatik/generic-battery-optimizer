from datetime import datetime
import unittest
import pandas as pd
from battery_optimizer import optimize
from battery_optimizer.profiles.battery_profile import Battery
from helpers import find_solver, get_profiles


class TestMinChargePower(unittest.TestCase):
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
        """Battery is charged from PV above min charge power"""
        buy = {
            "pv": pd.DataFrame(
                data={
                    "input_power": [5, 10, 10, 5, 0],
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
                    "input_power": [2, 2, 2, 21, 0],
                    "input_price": [0, 0, 0, 0, 0],
                },
                index=self.time_series,
            )
        }

        sell = {
            "grid": pd.DataFrame(
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
            data={"pv": [5, 10, 10, 5, 0], "grid": [0, 0, 0, 0, 0]},
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
                "grid": [3, 0, 0, 0, 0],
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
        """The battery will not be charged because min charge power is too high"""
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

        sell = {
            "grid": pd.DataFrame(
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
            data={"pv": [5, 5, 5, 5, 0], "grid": [0, 0, 0, 9, 0]},
            index=self.time_series,
        )

        sell_result = pd.DataFrame(
            data={
                "grid": [3, 3, 3, 0, 0],
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
