"""
Unit tests for device-limited profiles (PowerPriceProfile.limit_to).

Test cases:
- test_limited_buy_profile_is_exclusive: a buy profile limited to a battery
  only feeds that battery, and the battery only buys from that profile.
- test_local_generation_cannot_feed_limited_device: an unrestricted
  zero-price buy profile (local PV generation) cannot feed a device that is
  claimed by a limited buy profile (separate metering).
- test_limited_sell_profile_eligibility: a sell profile limited to a PV
  profile only accepts energy from that PV profile, and the claimed PV can
  not sell to other sinks.
"""

from datetime import datetime

import pandas as pd

from battery_optimizer import optimize
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.profiles.profiles import PowerPriceProfile, ProfileStack
from tests.helpers import find_solver


TIME_SERIES = pd.DatetimeIndex(
    [
        datetime(2021, 1, 1, 8, 0, 0),
        datetime(2021, 1, 1, 9, 0, 0),
        datetime(2021, 1, 1, 10, 0, 0),
    ]
)


def make_battery(name: str = "bat1", start_soc: float = 0, end_soc: float = 1):
    return Battery(
        name=name,
        capacity=10000,
        max_charge_power=5000,
        max_discharge_power=5000,
        charge_efficiency=1,
        discharge_efficiency=1,
        start_soc=start_soc,
        end_soc=end_soc,
        end_soc_time=TIME_SERIES[-1],
    )


def test_limit_to_is_stored_and_copied():
    profile = PowerPriceProfile(
        index=TIME_SERIES,
        price=[5, 5, 5],
        power=[6000, 6000, 6000],
        name="cheap",
        limit_to=["bat1"],
    )
    assert profile.limit_to == ["bat1"]
    assert profile.copy_ppp().limit_to == ["bat1"]
    stack_copy = ProfileStack([profile]).copy()
    assert stack_copy.profiles["cheap"].limit_to == ["bat1"]
    unrestricted = PowerPriceProfile(
        index=TIME_SERIES, price=[1, 1, 1], name="grid"
    )
    assert unrestricted.limit_to is None
    assert unrestricted.copy_ppp().limit_to is None


def test_limited_buy_profile_is_exclusive():
    """The cheap limited profile only feeds bat1 and bat1 only buys cheap.

    Without the restriction the whole household would buy from "cheap"
    (5 ct < 30 ct). With it, the fixed load must buy from "grid" while the
    battery (forced to charge 10 kWh by its end SoC) buys from "cheap".
    """
    buy_prices = ProfileStack(
        [
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[30, 30, 30],
                power=[10000, 10000, 10000],
                name="grid",
            ),
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[5, 5, 5],
                power=[6000, 6000, 6000],
                name="cheap",
                limit_to=["bat1"],
            ),
        ]
    )
    fixed_consumption = ProfileStack(
        [
            PowerPriceProfile(
                index=TIME_SERIES,
                power=[1000, 1000, 0],
                name="load1",
            )
        ]
    )
    result = optimize(
        buy_prices=buy_prices,
        fixed_consumption=fixed_consumption,
        batteries=[make_battery()],
        solver=find_solver(),
    )
    expected_buy = pd.DataFrame(
        data={"grid": [1000, 1000, 0], "cheap": [5000, 5000, 0]},
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[0], expected_buy, check_dtype=False, check_exact=False, rtol=1e-3)


def _pv_and_limited_battery_setup(pv_kwargs: dict):
    """grid + PV pseudo profile + cheap profile limited to bat1, load."""
    buy_prices = ProfileStack(
        [
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[30, 30, 30],
                power=[10000, 10000, 10000],
                name="grid",
            ),
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[0, 0, 0],
                power=[2000, 2000, 0],
                name="pv1-pv",
                **pv_kwargs,
            ),
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[5, 5, 5],
                power=[6000, 6000, 6000],
                name="cheap",
                limit_to=["bat1"],
            ),
        ]
    )
    fixed_consumption = ProfileStack(
        [
            PowerPriceProfile(
                index=TIME_SERIES,
                power=[1000, 1000, 0],
                name="load1",
            )
        ]
    )
    return optimize(
        buy_prices=buy_prices,
        fixed_consumption=fixed_consumption,
        batteries=[make_battery()],
        solver=find_solver(),
    )


def test_grid_tariff_cannot_feed_limited_device():
    """A profile NOT marked as local generation cannot feed the claimed
    battery (separate metering): it only feeds the unclaimed load while
    the battery buys its full charge from "cheap"."""
    result = _pv_and_limited_battery_setup({})
    expected_buy = pd.DataFrame(
        data={
            "grid": [0, 0, 0],
            "pv1-pv": [1000, 1000, 0],
            "cheap": [5000, 5000, 0],
        },
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[0], expected_buy, check_dtype=False, check_exact=False, rtol=1e-3)


def test_local_generation_feeds_limited_device_by_default():
    """Local generation (PV behind the GCP) may feed every device by
    default, including the battery claimed by the limited profile: the free
    PV covers load and part of the battery charge."""
    result = _pv_and_limited_battery_setup({"local_generation": True})
    expected_buy = pd.DataFrame(
        data={
            "grid": [0, 0, 0],
            "pv1-pv": [2000, 2000, 0],
            "cheap": [4000, 4000, 0],
        },
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[0], expected_buy, check_dtype=False, check_exact=False, rtol=1e-3)


def test_local_generation_restricted_to_device():
    """Local generation with its own limit_to only feeds the matching
    devices: PV restricted to the load cannot charge the battery."""
    result = _pv_and_limited_battery_setup(
        {"local_generation": True, "limit_to": ["load1"]}
    )
    expected_buy = pd.DataFrame(
        data={
            "grid": [0, 0, 0],
            "pv1-pv": [1000, 1000, 0],
            "cheap": [5000, 5000, 0],
        },
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[0], expected_buy, check_dtype=False, check_exact=False, rtol=1e-3)


def _pv_with_limited_sell_setup(pv_kwargs: dict):
    buy_prices = ProfileStack(
        [
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[30, 30, 30],
                power=[10000, 10000, 10000],
                name="grid",
            ),
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[0, 0, 0],
                power=[2000, 2000, 0],
                name="pv1-pv",
                local_generation=True,
                **pv_kwargs,
            ),
        ]
    )
    sell_prices = ProfileStack(
        [
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[8, 8, 8],
                power=[10000, 10000, 10000],
                name="eeg",
                feed_in=True,
                limit_to=["pv1"],
            ),
            PowerPriceProfile(
                index=TIME_SERIES,
                price=[12, 12, 12],
                power=[10000, 10000, 10000],
                name="market",
                feed_in=True,
            ),
        ]
    )
    fixed_consumption = ProfileStack(
        [
            PowerPriceProfile(
                index=TIME_SERIES,
                power=[1000, 1000, 0],
                name="load1",
            )
        ]
    )
    return optimize(
        buy_prices=buy_prices,
        sell_prices=sell_prices,
        fixed_consumption=fixed_consumption,
        batteries=[make_battery(start_soc=1, end_soc=0)],
        solver=find_solver(),
    )


def test_limited_sell_profile_eligibility():
    """A sell profile limited to PV only accepts PV energy.

    The market pays more than the EEG profile, but the PV is claimed by
    the EEG profile and can only sell there. Serving the load with PV
    only forgoes 8 ct (EEG), while serving it from the battery forgoes
    12 ct (market), so PV covers the load and the battery sells its full
    10 kWh to the market.
    """
    result = _pv_with_limited_sell_setup({})
    expected_sell = pd.DataFrame(
        data={"eeg": [1000, 1000, 0], "market": [5000, 5000, 0]},
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[1], expected_sell, check_dtype=False, check_exact=False, rtol=1e-3)
    expected_buy = pd.DataFrame(
        data={"grid": [0, 0, 0], "pv1-pv": [2000, 2000, 0]},
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[0], expected_buy, check_dtype=False, check_exact=False, rtol=1e-3)


def test_local_generation_full_feed_in():
    """limit_to=[] on local generation means full feed-in: PV cannot feed
    any device and sells everything to its claiming EEG profile; the load
    is served by the battery (5000 W discharge shared with the market)."""
    result = _pv_with_limited_sell_setup({"limit_to": []})
    expected_sell = pd.DataFrame(
        data={"eeg": [2000, 2000, 0], "market": [4000, 4000, 0]},
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[1], expected_sell, check_dtype=False, check_exact=False, rtol=1e-3)
    expected_buy = pd.DataFrame(
        data={"grid": [0, 0, 0], "pv1-pv": [2000, 2000, 0]},
        index=TIME_SERIES,
    )
    pd.testing.assert_frame_equal(result[0], expected_buy, check_dtype=False, check_exact=False, rtol=1e-3)
