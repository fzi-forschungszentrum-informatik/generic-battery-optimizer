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
