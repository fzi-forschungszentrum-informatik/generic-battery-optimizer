import pytest
import pandas as pd
from datetime import datetime
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer import optimize
from helpers import find_solver, get_profiles


@pytest.mark.parametrize(
    "charge_efficiency, discharge_efficiency",
    [
        (0.75, 1.0),
        (1.0, 0.75),
        (0.75, 0.75),
        (1.0, 1.0),
    ],
)
def test_battery_efficiency(charge_efficiency, discharge_efficiency):
    time_series = pd.DatetimeIndex(
        [
            datetime(2022, 1, 3, 18, 0, 0),
            datetime(2022, 1, 3, 19, 0, 0),
            datetime(2022, 1, 3, 20, 0, 0),
        ]
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
        result[3], expected_battery_soc, check_dtype=False
    )
    pd.testing.assert_frame_equal(result[2], expected_power, check_dtype=False)
