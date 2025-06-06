from battery_optimizer import optimize
from helpers import find_solver, get_profiles
from datetime import datetime
import pandas as pd


class TestHomeConsumption:
    time_series = pd.DatetimeIndex(
        [
            datetime(2021, 1, 1, 8, 0, 0),
            datetime(2021, 1, 1, 9, 0, 0),
            datetime(2021, 1, 1, 10, 0, 0),
        ]
    )

    def test_consumption_from_grid(self):
        """Home consumption from grid"""
        buy = {
            "buy": pd.DataFrame(
                data={
                    "input_price": [30, 30, 0],
                    "input_power": [100, 100, 0],
                },
                index=self.time_series,
            )
        }

        fixed_consumption = {
            "fixe_consumption": pd.DataFrame(
                data={"input_price": [0, 0, 0], "input_power": [7, 12, 0]},
                index=self.time_series,
            )
        }

        result = optimize(
            buy_prices=get_profiles(self.time_series, buy),
            fixed_consumption=get_profiles(
                self.time_series, fixed_consumption
            ),
            batteries=[],
            solver=find_solver(),
        )

        buy_result = pd.DataFrame(
            data={"buy": [7, 12, 0]}, index=self.time_series)

        fixed_consumption_result = pd.DataFrame(
            data={"fixe_consumption": [7, 12, 0]}, index=self.time_series
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(result[0], buy_result, check_dtype=False)
        pd.testing.assert_frame_equal(
            result[4], fixed_consumption_result, check_dtype=False
        )

    def test_consumption_from_pv(self):
        """Home consumption from PV (rest sold to grid)"""
        buy = {
            "pv": pd.DataFrame(
                data={
                    "input_power": [100, 100, 0],
                    "input_price": [0, 0, 0],
                },
                index=self.time_series,
            )
        }

        sell = {
            "sell": pd.DataFrame(
                data={
                    "input_power": [100, 100, 0],
                    "input_price": [30, 30, 0],
                },
                index=self.time_series,
            )
        }

        fixed_consumption = {
            "fixed_consumption": pd.DataFrame(
                data={
                    "input_power": [7, 12, 0],
                    "input_price": [0, 0, 0],
                },
                index=self.time_series,
            )
        }

        result = optimize(
            buy_prices=get_profiles(self.time_series, buy),
            sell_prices=get_profiles(self.time_series, sell),
            fixed_consumption=get_profiles(
                self.time_series, fixed_consumption
            ),
            solver=find_solver(),
        )

        buy_result = pd.DataFrame(
            data={"pv": [100, 100, 0]}, index=self.time_series)

        sell_result = pd.DataFrame(
            data={"sell": [93, 88, 0]}, index=self.time_series)

        fixed_consumption_result = pd.DataFrame(
            data={"fixed_consumption": [7, 12, 0]}, index=self.time_series
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(result[0], buy_result, check_dtype=False)
        pd.testing.assert_frame_equal(
            result[1], sell_result, check_dtype=False)
        pd.testing.assert_frame_equal(
            result[4], fixed_consumption_result, check_dtype=False
        )

    def test_consumption_from_pv_and_grid(self):
        """Home consumption from PV and grid
        The grid price is higher than the PV price, so the PV is used first"""
        buy = {
            "pv": pd.DataFrame(
                data={
                    "input_power": [5, 5, 0],
                    "input_price": [0, 0, 0],
                },
                index=self.time_series,
            ),
            "grid": pd.DataFrame(
                data={
                    "input_power": [100, 100, 0],
                    "input_price": [30, 30, 0],
                },
                index=self.time_series,
            ),
        }

        fixed_consumption = {
            "fixed_consumption": pd.DataFrame(
                data={
                    "input_power": [7, 12, 0],
                    "input_price": [0, 0, 0],
                },
                index=self.time_series,
            )
        }

        result = optimize(
            buy_prices=get_profiles(self.time_series, buy),
            fixed_consumption=get_profiles(
                self.time_series, fixed_consumption
            ),
            batteries=[],
            solver=find_solver(),
        )

        buy_result = pd.DataFrame(
            data={"pv": [5, 5, 0], "grid": [2, 7, 0]},
            index=self.time_series,
        )

        fixed_consumption_result = pd.DataFrame(
            data={
                "fixed_consumption": [7, 12, 0],
            },
            index=self.time_series,
        )

        # Assert power profiles
        pd.testing.assert_frame_equal(result[0], buy_result, check_dtype=False)
        pd.testing.assert_frame_equal(
            result[4], fixed_consumption_result, check_dtype=False
        )
