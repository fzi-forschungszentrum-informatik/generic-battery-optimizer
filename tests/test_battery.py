"""
Tests for the Battery profile and its optimization.

Test cases:
- test_battery_efficiency: Tests that the battery behaves correctly with
  different charge and discharge efficiencies.
- TestMinMaxSoc: Tests that the battery respects min_soc and max_soc limits.
"""

import pytest
import pandas as pd
from datetime import datetime
from battery_optimizer.export import Exporter
from battery_optimizer.helpers.model_setup import (
    generate_common_time_series,
    reindex_profile,
)
from battery_optimizer.model import Model
from battery_optimizer.profiles.battery import Battery
from battery_optimizer import optimize
from battery_optimizer.profiles.ev import EV
from tests.helpers import find_solver, get_profiles
from battery_optimizer.solver import Solver


@pytest.mark.parametrize(
    "charge_efficiency, discharge_efficiency",
    [
        (0.75, 1.0),
        (1.0, 0.75),
        (0.75, 0.75),
        (1.0, 1.0),
        (0.85, 0.9),
        (0.9, 0.85),
        (0.8, 0.8),
        (0.95, 0.95),
        (0.7, 0.7),
        (0.65, 0.65),
        (0.6, 0.6),
        (0.55, 0.55),
        (0.5, 0.5),
        (0.45, 0.45),
        (0.4, 0.4),
        (0.35, 0.35),
        (0.9, 1.0),
        (0.8, 1.0),
        (0.7, 1.0),
        (0.6, 1.0),
        (0.5, 1.0),
        (0.4, 1.0),
        (0.3, 1.0),
        (0.2, 1.0),
        (0.1, 1.0),
        (1.0, 0.9),
        (1.0, 0.8),
        (1.0, 0.7),
        (1.0, 0.6),
        (1.0, 0.5),
        (1.0, 0.4),
        (1.0, 0.3),
        (1.0, 0.2),
        (1.0, 0.1),
    ],
)
def test_battery_efficiency(
    charge_efficiency: float, discharge_efficiency: float
):
    """
    Test battery behavior with different charge and discharge efficiencies.

    The battery is charged and discharged with a fixed power usage. The test
    checks that the state of charge (SoC) and power profiles are as expected
    given the specified charge and discharge efficiencies.

    Parameters
    ----------
    charge_efficiency : float
        The efficiency of battery charging (0-1).
    discharge_efficiency : float
        The efficiency of battery discharging (0-1).
    """
    time_series = pd.date_range(
        start="2022-01-03 18:00:00", end="2022-01-03 20:00:00", freq="h"
    )

    buy = {
        "supplier_price": pd.DataFrame(
            data={
                "input_power": [100, 0, 0],
                "input_price": [5, 0, 0],
            },
            index=time_series,
        )
    }

    sell = {
        "sell": pd.DataFrame(
            data={
                "input_power": [0, 0, 0],
                "input_price": [0, 0, 0],
            },
            index=time_series,
        )
    }

    power_usage = 10
    fixed_consumption = {
        "fixed_consumption": pd.DataFrame(
            data={
                "input_power": [0, power_usage, 0],
                "input_price": [0, 0, 0],
            },
            index=time_series,
        )
    }

    battery = Battery(
        name="test-battery",
        start_soc=0,
        end_soc=0,
        capacity=100,
        max_charge_power=100,
        max_discharge_power=100,
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
    )

    result = optimize(
        buy_prices=get_profiles(time_series, buy),
        sell_prices=get_profiles(time_series, sell),
        fixed_consumption=get_profiles(time_series, fixed_consumption),
        batteries=[battery],
        solver=find_solver(),
    )

    expected_battery_soc = pd.DataFrame(
        data={
            "test-battery": [
                (power_usage / discharge_efficiency) / battery.capacity,
                0,
                0,
            ],
        },
        index=time_series,
    )

    expected_power = pd.DataFrame(
        data={
            "test-battery": [
                (power_usage / charge_efficiency) / discharge_efficiency,
                -power_usage,
                0,
            ],
        },
        index=time_series,
    )

    pd.testing.assert_frame_equal(
        result[3], expected_battery_soc, check_dtype=False, check_freq=False
    )
    pd.testing.assert_frame_equal(
        result[2], expected_power, check_dtype=False, check_freq=False
    )


class TestMinMaxSoc:
    """
    Test the min_soc and max_soc parameters of the Battery profile.

    The battery should not go below min_soc and not above max_soc.
    The profile should raise a ValueError if min_soc is greater than max_soc.
    The profile should raise a ValueError if min_soc or max_soc are not in the
    range [0, 1].
    The profile should work correctly when min_soc and max_soc are equal.
    The profile should raise a ValueError if start_soc is outside the min_soc
    and max_soc range.
    The profile should raise a ValueError if end_soc is outside the min_soc and
    max_soc range.
    """

    @pytest.mark.parametrize(
        "min_soc, max_soc", [(0.0, 1.0), (0.2, 0.8), (0.5, 0.5), (0.3, 0.9)]
    )
    def test_min_max_soc(self, min_soc: float, max_soc: float):
        """
        Test that battery respects min an max sox limits.

        The battery should not go below min soc and not above max soc.

        Parameters
        ----------
        min_soc : float
            Minimum state of charge (0-1).
        max_soc : float
            Maximum state of charge (0-1).
        """
        time_series = pd.date_range(
            start="2022-01-03 18:00:00", end="2022-01-03 20:00:00", freq="h"
        )
        battery = Battery(
            name="test-battery",
            start_soc=0.5,
            capacity=100,
            max_charge_power=100,
            max_discharge_power=100,
            min_soc=min_soc,
            max_soc=max_soc,
            charge_efficiency=1.0,
            discharge_efficiency=1.0,
        )

        power = {time_series[0]: 100, time_series[1]: 100, time_series[2]: 0}
        buy_price = {
            time_series[0]: 2,
            time_series[1]: 3,
            time_series[2]: 0,
        }
        sell_price_incentive_sell = {
            time_series[0]: 2,
            time_series[1]: 1,
            time_series[2]: 0,
        }
        sell_price_incentive_keep = {
            time_series[0]: 2,
            time_series[1]: 1,
            time_series[2]: 100,
        }

        model = Model(time_series)
        model.add_battery(battery)
        model.add_sell_profile("sell", power, sell_price_incentive_sell)
        model.add_buy_profile("buy", power, buy_price)
        model.add_energy_paths()
        model.generate_objective()
        Solver(find_solver()).solve(model.model)
        assert all(
            Exporter(model).to_df().to_battery_soc()["test-battery"] == min_soc
        )

        model = Model(time_series)
        model.add_battery(battery)
        model.add_sell_profile("sell", power, sell_price_incentive_keep)
        model.add_buy_profile("buy", power, buy_price)
        model.add_energy_paths()
        model.generate_objective()
        Solver(find_solver()).solve(model.model)
        assert all(
            Exporter(model).to_df().to_battery_soc()["test-battery"] == max_soc
        )

    def test_min_soc_greater_than_max_soc(self):
        """
        Test that ValueError is raised when min_soc > max_soc.

        The profile should raise a ValueError if min_soc is greater than max_soc.
        """
        with pytest.raises(ValueError):
            Battery(
                capacity=100,
                max_charge_power=100,
                min_soc=0.8,
                max_soc=0.2,
            )

    @pytest.mark.parametrize(
        "min_soc, max_soc",
        [(-0.1, 0.5), (0.0, 1.1), (1.2, 1.3), (-0.2, -0.1)],
    )
    def test_soc_out_of_bounds(self, min_soc: float, max_soc: float):
        """
        Test that ValueError is raised when min_soc or max_soc are out of bounds.

        The profile should raise a ValueError if min_soc or max_soc are not in
        the range [0, 1].

        Parameters
        ----------
        min_soc : float
            Minimum state of charge (0-1).
        max_soc : float
            Maximum state of charge (0-1).
        """
        with pytest.raises(ValueError):
            Battery(
                capacity=100,
                max_charge_power=100,
                min_soc=min_soc,
                max_soc=max_soc,
            )

    @pytest.mark.parametrize(
        "start_soc, min_soc, max_soc",
        [(0.1, 0.2, 0.8), (0.9, 0.0, 0.8), (0.5, 0.6, 0.6), (1.0, 0.0, 0.9)],
    )
    def test_start_soc_out_of_bounds(
        self, start_soc: float, min_soc: float, max_soc: float
    ):
        """
        Test that ValueError is raised when start_soc is out of bounds.

        The profile should raise a ValueError if start_soc is outside the
        min_soc and max_soc range.

        Parameters
        ----------
        start_soc : float
            Starting state of charge (0-1).
        min_soc : float
            Minimum state of charge (0-1).
        max_soc : float
            Maximum state of charge (0-1).
        """
        with pytest.raises(ValueError):
            Battery(
                start_soc=start_soc,
                capacity=100,
                max_charge_power=100,
                min_soc=min_soc,
                max_soc=max_soc,
            )

    @pytest.mark.parametrize(
        "end_soc, min_soc, max_soc",
        [(0.1, 0.2, 0.8), (0.9, 0.0, 0.8), (0.5, 0.6, 0.6), (1.0, 0.0, 0.9)],
    )
    def test_end_soc_out_of_bounds(
        self, end_soc: float, min_soc: float, max_soc: float
    ):
        """
        Test that ValueError is raised when end_soc is out of bounds.

        The profile should raise a ValueError if end_soc is outside the
        min_soc and max_soc range.

        Parameters
        ----------
        end_soc : float
            Ending state of charge (0-1).
        min_soc : float
            Minimum state of charge (0-1).
        max_soc : float
            Maximum state of charge (0-1).
        """
        with pytest.raises(ValueError):
            EV(
                charge_start_time=datetime(2022, 1, 3, 18, 0, 0),
                charge_end_time=datetime(2022, 1, 3, 20, 0, 0),
                end_soc=end_soc,
                capacity=100,
                max_charge_power=100,
                min_soc=min_soc,
                max_soc=max_soc,
            )


class TestDeprecatedEVFunctionality:
    """
    Test the deprecated EV functionality in the Battery profile.

    The EV functionality has been moved to the EV class in profiles.ev and
    model.add_ev(). These tests ensure that the deprecated functionality still
    works as expected until it is removed in version 5.0.0.
    """

    def test_charge_end_past_last_timestamp(self):
        """
        Test the charging of an EV where charge_end_time is after last ts.

        Ensure that the end soc will be reached at the last timestamp when
        charge_end_time is after the last timestamp from the profile and
        the generate_common_time_series is used.
        """
        time_series = [pd.to_datetime("2025-12-11T13:58:05.129253Z")]
        time_series.extend(
            pd.date_range(
                start="2025-12-11T14:00:00Z",
                end="2025-12-12T01:45:00Z",
                freq="15min",
            )
        )

        pv_power = {
            time: price
            for time, price in zip(
                time_series,
                [
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -10536,
                    -15668,
                    -16781,
                    -6810,
                    0,
                    0,
                    -23311,
                    -35173,
                    -2398,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -21550,
                    -28200,
                    -17261,
                    0,
                    -12326,
                    -724,
                    -3187,
                    0,
                    -30316,
                    0,
                    0,
                    0,
                    0,
                    -157,
                    0,
                    0,
                    -10097,
                    -752,
                    0,
                    -3229,
                    0,
                    0,
                ],
            )
        }
        pv_price = {time: 0.0 for time in time_series}

        grid_power = {time: 1000000 for time in time_series}
        grid_price = {
            time: price
            for time, price in zip(
                time_series,
                [
                    33.717459999999996,
                    34.18275,
                    34.18275,
                    34.18275,
                    34.18275,
                    34.774179999999994,
                    34.774179999999994,
                    34.774179999999994,
                    34.774179999999994,
                    39.93283,
                    39.93283,
                    39.93283,
                    39.93283,
                    39.703160000000004,
                    39.703160000000004,
                    39.703160000000004,
                    39.703160000000004,
                    39.696020000000004,
                    39.696020000000004,
                    39.696020000000004,
                    39.696020000000004,
                    39.659130000000005,
                    39.659130000000005,
                    39.659130000000005,
                    39.659130000000005,
                    33.278349999999996,
                    33.278349999999996,
                    33.278349999999996,
                    33.278349999999996,
                    31.9753,
                    31.9753,
                    31.9753,
                    31.9753,
                    30.258129999999994,
                    30.258129999999994,
                    30.258129999999994,
                    30.258129999999994,
                    30.901919999999997,
                    30.901919999999997,
                    30.901919999999997,
                    30.901919999999997,
                    21.715119999999995,
                    21.715119999999995,
                    21.715119999999995,
                    21.715119999999995,
                    21.713929999999998,
                    21.713929999999998,
                    21.713929999999998,
                    21.713929999999998,
                ],
            )
        }

        sell_power = {
            time: power
            for time, power in zip(
                time_series,
                [
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -10536,
                    -15668,
                    -16781,
                    -6810,
                    0,
                    0,
                    -23311,
                    -35173,
                    -2398,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -21550,
                    -28200,
                    -17261,
                    0,
                    -12326,
                    -724,
                    -3187,
                    0,
                    -30316,
                    0,
                    0,
                    0,
                    0,
                    -157,
                    0,
                    0,
                    -10097,
                    -752,
                    0,
                    -3229,
                    0,
                    0,
                ],
            )
        }
        sell_price = {time: 8 for time in time_series}

        fixed_consumption = {
            time: power
            for time, power in zip(
                time_series,
                [
                    28380,
                    27479,
                    27597,
                    27770,
                    27307,
                    27015,
                    26607,
                    26456,
                    26729,
                    26875,
                    26556,
                    25733,
                    24815,
                    23688,
                    23238,
                    23588,
                    23397,
                    22607,
                    21736,
                    21232,
                    21204,
                    20965,
                    20343,
                    19692,
                    19422,
                    19396,
                    18891,
                    20508,
                    23095,
                    21381,
                    18398,
                    17767,
                    18052,
                    18070,
                    17591,
                    17117,
                    16855,
                    16727,
                    16786,
                    16593,
                    16263,
                    16304,
                    16257,
                    16152,
                    16268,
                    16225,
                    16112,
                    16219,
                    16136,
                ],
            )
        }

        battery = Battery.model_validate(
            {
                "name": "ev_battery",
                "start_soc": 0.2,
                "end_soc": 0.8,
                "end_soc_time": "2025-12-12T01:58:05.129253Z",
                "start_soc_time": "2025-12-11T13:58:05.129253Z",
                "capacity": 77000,
                "max_charge_power": 11000,
                "max_discharge_power": 0,
                "min_charge_power": 0,
                "min_discharge_power": 0,
                "charge_efficiency": 1,
                "discharge_efficiency": 1,
                "min_soc": 0,
                "max_soc": 1,
            }
        )
        with pytest.deprecated_call():
            time_series = generate_common_time_series(
                profiles=[
                    pv_power,
                    pv_price,
                    grid_power,
                    grid_price,
                    sell_power,
                    sell_price,
                    fixed_consumption,
                ],
                batteries=[battery],
            )

        model = Model(time_series)
        model.add_sell_profile(
            "pv",
            reindex_profile(pv_power, time_series),
            reindex_profile(pv_price, time_series),
        )
        model.add_buy_profile(
            "buy",
            reindex_profile(grid_power, time_series),
            reindex_profile(grid_price, time_series),
        )
        model.add_sell_profile(
            "sell",
            reindex_profile(sell_power, time_series),
            reindex_profile(sell_price, time_series),
        )
        model.add_fixed_consumption(
            "fixed_consumption",
            reindex_profile(fixed_consumption, time_series),
        )
        with pytest.deprecated_call():
            model.add_battery(battery)

        model.add_energy_paths()
        model.generate_objective()
        Solver(find_solver()).solve(model.model)

        df_export = Exporter(model).to_df()
        assert df_export.to_battery_soc().iloc[-1][
            "ev_battery"
        ] == pytest.approx(0.8, 0.01)
