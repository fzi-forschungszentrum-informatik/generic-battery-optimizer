"""
Test the helping methods to create the model index and reindex profiles.

The method generate_common_time_series is tested in various scenarios to ensure
it correctly combines timestamps from profiles, batteries, and heat pumps.
The reindex_profile method is tested to ensure it correctly forward fills
values, raises for missing leading data and tests rounding of timestamps.
"""

import datetime
import pandas as pd
import pytest
from battery_optimizer.helpers.model_setup import (
    generate_common_time_series,
    reindex_profile,
    adjust_battery_timestamps,
    adjust_heat_pump_timestamps,
)
from battery_optimizer.profiles.battery import Battery
from battery_optimizer.profiles.heat_pump import HeatPump
from zoneinfo import ZoneInfo


class Test_Generate_Common_Time_Series:
    """
    Test generation of common time series from various devices/profiles.

    Test the returned index against expected results in different scenarios.
    """

    def test_no_components(self):
        """
        Test empty index.

        Test that the result of no input is an empty list.
        """
        index = generate_common_time_series()
        assert index == []

    def test_profiles_only(self):
        """
        Test power profile.

        Test that passing in two power profiles returns a unified index of all
        input profiles.
        """
        profiles = [
            {
                pd.Timestamp("2024-01-01 00:00"): 0,
                pd.Timestamp("2024-01-01 01:00"): 1,
            },
            {
                pd.Timestamp("2024-01-01 00:30"): 0,
                pd.Timestamp("2024-01-01 02:00"): 1,
            },
        ]
        index = generate_common_time_series(profiles=profiles)
        expected_index = [
            pd.Timestamp("2024-01-01 00:00"),
            pd.Timestamp("2024-01-01 00:30"),
            pd.Timestamp("2024-01-01 01:00"),
            pd.Timestamp("2024-01-01 02:00"),
        ]
        assert index == expected_index

    def test_rounding(self):
        """
        Test that rounding produces output at closest 15min.

        Test that an input price series with precise timestamps is rounded to
        the closest 15 minute interval (04:13:07 -> 04:15:00).
        """
        precise_index = [
            {
                v: 0
                for v in pd.date_range(
                    start="2024-01-01 04:13:07",
                    end="2024-01-01 10:00:00",
                    freq="h",
                )
            }
        ]

        index = generate_common_time_series(
            precise_index,
            round_freq="15min",
        )

        assert index == [
            pd.Timestamp("2024-01-01 04:15:00"),
            pd.Timestamp("2024-01-01 05:15:00"),
            pd.Timestamp("2024-01-01 06:15:00"),
            pd.Timestamp("2024-01-01 07:15:00"),
            pd.Timestamp("2024-01-01 08:15:00"),
            pd.Timestamp("2024-01-01 09:15:00"),
        ]

    def test_battery(self):
        """
        Test index returned from a battery.

        Passes all possible timestamps to a battery and expects the output to
        contain all time stamps from the input.
        """
        battery = Battery(
            start_soc_time=pd.Timestamp("2024-01-01 01:00"),
            end_soc_time=pd.Timestamp("2024-01-01 03:00"),
            start_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        index = generate_common_time_series(batteries=[battery])

        assert index == [
            pd.Timestamp("2024-01-01 01:00"),
            pd.Timestamp("2024-01-01 03:00"),
        ]

    def test_heat_pump(self):
        """
        Test index returned from a heat pump.

        Passes all possible timestamps to a heat pump and expects the output to
        contain all time stamps from the input.
        """
        heat_pump = HeatPump(
            cop_output_temperature={pd.Timestamp("2024-01-01 01:00+00:00"): 4.0},
            cop_flow_temperature={pd.Timestamp("2024-01-01 02:00+00:00"): 3.5},
            temp_room={pd.Timestamp("2024-01-01 03:00+00:00"): 20.0},
            outdoor_temperature={pd.Timestamp("2024-01-01 04:00+00:00"): 5.0},
            heat_demand={pd.Timestamp("2024-01-01 05:00+00:00"): 15.0},
            warm_water_demand={pd.Timestamp("2024-01-01 06:00+00:00"): 10.0},
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        index = generate_common_time_series(heat_pumps=[heat_pump])

        assert index == [
            pd.Timestamp("2024-01-01 01:00+00:00"),
            pd.Timestamp("2024-01-01 02:00+00:00"),
            pd.Timestamp("2024-01-01 03:00+00:00"),
            pd.Timestamp("2024-01-01 04:00+00:00"),
            pd.Timestamp("2024-01-01 05:00+00:00"),
            pd.Timestamp("2024-01-01 06:00+00:00"),
        ]

    def test_heat_pump_floats(self):
        """
        Test index returned from a heat pump with float values as parameters.

        Passes all possible timestamp-capable values to a heat pump and expects
        the output to contain one timestamp because the input has one.
        """
        heat_pump = HeatPump(
            cop_output_temperature=4.0,
            cop_flow_temperature=3.5,
            temp_room=20.0,
            outdoor_temperature=5.0,
            heat_demand={pd.Timestamp("2024-01-01 05:00+00:00"): 15.0},
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        index = generate_common_time_series(heat_pumps=[heat_pump])

        assert index == [
            pd.Timestamp("2024-01-01 05:00+00:00"),
        ]

    def test_batteries_and_heat_pumps(self):
        """
        Test unification of index for a heat pump and battery.

        Test that the index returned from a battery and heat pump contains all
        timestamps from both devices.
        """
        battery = Battery(
            start_soc_time=pd.Timestamp("2024-01-01 01:30+00:00"),
            end_soc_time=pd.Timestamp("2024-01-01 02:30+00:00"),
            start_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        heat_pump = HeatPump(
            cop_output_temperature={pd.Timestamp("2024-01-01 01:00+00:00"): 4.0},
            cop_flow_temperature={pd.Timestamp("2024-01-01 02:00+00:00"): 3.5},
            temp_room={pd.Timestamp("2024-01-01 03:00+00:00"): 20.0},
            outdoor_temperature={pd.Timestamp("2024-01-01 04:00+00:00"): 5.0},
            heat_demand={pd.Timestamp("2024-01-01 05:00+00:00"): 15.0},
            warm_water_demand={pd.Timestamp("2024-01-01 06:00+00:00"): 10.0},
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        index = generate_common_time_series(
            batteries=[battery],
            heat_pumps=[heat_pump],
        )

        expected_index = [
            pd.Timestamp("2024-01-01 01:00+00:00"),
            pd.Timestamp("2024-01-01 01:30+00:00"),
            pd.Timestamp("2024-01-01 02:00+00:00"),
            pd.Timestamp("2024-01-01 02:30+00:00"),
            pd.Timestamp("2024-01-01 03:00+00:00"),
            pd.Timestamp("2024-01-01 04:00+00:00"),
            pd.Timestamp("2024-01-01 05:00+00:00"),
            pd.Timestamp("2024-01-01 06:00+00:00"),
        ]

        assert index == expected_index


class Test_Reindex_Profile:
    """
    Test reindexing of profiles to a given index.

    Test that reindexing works in various scenarios including identical
    indices, missing timestamps, extra timestamps, different timestamps,
    trailing missing timestamps, and leading missing timestamps.
    """
    def test_identical_index_str(self):
        """
        Test identical index and profile.

        Test that reindexing a profile with the same index returns the same
        profile.
        """
        index = [
            "2024-01-01 00:00+01:00",
            "2024-01-01 01:00+01:00",
            "2024-01-01 02:00+01:00",
        ]

        profile = {
            "2024-01-01 00:00+01:00": 10,
            "2024-01-01 01:00+01:00": 20,
            "2024-01-01 02:00+01:00": 30,
        }

        result = {
            pd.to_datetime("2024-01-01 00:00+01:00"): 10,
            pd.to_datetime("2024-01-01 01:00+01:00"): 20,
            pd.to_datetime("2024-01-01 02:00+01:00"): 30,
        }

        assert reindex_profile(profile, index) == result

    def test_identical_index_datetime(self):
        """
        Test identical index and profile with datetime objects.

        Test that reindexing a profile with the same index returns the same
        profile.
        """
        index = pd.date_range(
            start="2024-01-01 00:00+01:00",
            end="2024-01-01 02:00+01:00",
            freq="h",
        ).to_pydatetime()
        assert all(isinstance(t, datetime.datetime) for t in index)

        tz = ZoneInfo("Europe/Berlin")
        profile = {
            datetime.datetime(2024, 1, 1, 0, 0, tzinfo=tz): 10,
            datetime.datetime(2024, 1, 1, 1, 0, tzinfo=tz): 20,
            datetime.datetime(2024, 1, 1, 2, 0, tzinfo=tz): 30,
        }
        assert all(isinstance(t, datetime.datetime) for t in profile.keys())

        assert reindex_profile(profile, index) == {
            pd.to_datetime(k): v for k, v in profile.items()
        }

    def test_identical_index_timestamp(self):
        """
        Test identical index and profile with Timestamps.

        Test that reindexing a profile with the same index returns the same
        profile.
        """
        index = pd.date_range(
            start="2024-01-01 00:00+01:00",
            end="2024-01-01 02:00+01:00",
            freq="h",
        )
        assert all(isinstance(t, pd.Timestamp) for t in index)

        profile = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 10,
            pd.Timestamp("2024-01-01 01:00+01:00"): 20,
            pd.Timestamp("2024-01-01 02:00+01:00"): 30,
        }
        assert all(isinstance(t, pd.Timestamp) for t in profile.keys())

        assert reindex_profile(profile, index) == profile

    def test_identical_index_mixed(self):
        """
        Test identical index and profile with mixed datetime types.

        Test that reindexing a profile with the same index returns the same
        profile.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+01:00"),
            pd.Timestamp("2024-01-01 01:00+01:00"),
            pd.Timestamp("2024-01-01 02:00+01:00"),
        ]
        assert all(isinstance(t, pd.Timestamp) for t in index)

        profile = {
            "2024-01-01 00:00+01:00": 10,
            "2024-01-01 01:00+01:00": 20,
            "2024-01-01 02:00+01:00": 30,
        }
        assert all(isinstance(t, str) for t in profile.keys())

        assert reindex_profile(profile, index) == {
            pd.to_datetime(k): v for k, v in profile.items()
        }

    def test_missing_timestamps(self):
        """
        Test profile missing some timestamps.

        Test that reindexing a profile with missing timestamps adds the time
        step and forward fills the values.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+01:00"),
            pd.Timestamp("2024-01-01 01:00+01:00"),
            pd.Timestamp("2024-01-01 02:00+01:00"),
        ]

        profile = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 10,
            pd.Timestamp("2024-01-01 02:00+01:00"): 30,
        }

        result = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 10,
            pd.Timestamp("2024-01-01 01:00+01:00"): 10,
            pd.Timestamp("2024-01-01 02:00+01:00"): 30,
        }

        assert reindex_profile(profile, index) == result

    def test_extra_timestamps(self):
        """
        Test profile with extra timestamps.

        Test that reindexing a profile with extra timestamps ignores the extra
        timestamps.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+01:00"),
            pd.Timestamp("2024-01-01 01:00+01:00"),
            pd.Timestamp("2024-01-01 02:00+01:00"),
        ]

        profile = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 10,
            pd.Timestamp("2024-01-01 01:00+01:00"): 20,
            pd.Timestamp("2024-01-01 01:30+01:00"): 25,
            pd.Timestamp("2024-01-01 02:00+01:00"): 30,
        }

        result = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 10,
            pd.Timestamp("2024-01-01 01:00+01:00"): 20,
            pd.Timestamp("2024-01-01 02:00+01:00"): 30,
        }

        assert reindex_profile(profile, index) == result

    def test_different_timestamps(self):
        """
        Test profile with different timestamps than index.

        Test with profile having different timesteps than index
        (e.g. index on the hour and profile 3 min past the hour).
        """
        index = pd.date_range(
            start="2024-01-01 00:00+01:00",
            end="2024-01-01 04:00+01:00",
            freq="h",
        )
        profile = {
            pd.Timestamp("2024-01-01 00:03+01:00"): 10,
            pd.Timestamp("2024-01-01 01:03+01:00"): 20,
            pd.Timestamp("2024-01-01 02:03+01:00"): 30,
            pd.Timestamp("2024-01-01 03:03+01:00"): 40,
            pd.Timestamp("2024-01-01 04:03+01:00"): 50,
        }

        result = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 0,
            pd.Timestamp("2024-01-01 01:00+01:00"): 10,
            pd.Timestamp("2024-01-01 02:00+01:00"): 20,
            pd.Timestamp("2024-01-01 03:00+01:00"): 30,
            pd.Timestamp("2024-01-01 04:00+01:00"): 40,
        }

        assert reindex_profile(profile, index, fill_value=0) == result

    def test_trailing_missing_timestamps(self):
        """
        Test profile missing trailing timestamps.

        Test that reindexing a profile missing trailing timestamps adds the
        time steps and forward fills the values.
        """
        index = pd.date_range(
            start="2024-01-01 00:00+01:00",
            end="2024-01-01 04:00+01:00",
            freq="h",
        )

        profile = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 10,
            pd.Timestamp("2024-01-01 01:00+01:00"): 20,
        }

        result = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 10,
            pd.Timestamp("2024-01-01 01:00+01:00"): 20,
            pd.Timestamp("2024-01-01 02:00+01:00"): 20,
            pd.Timestamp("2024-01-01 03:00+01:00"): 20,
            pd.Timestamp("2024-01-01 04:00+01:00"): 20,
        }

        assert reindex_profile(profile, index) == result

    def test_leading_missing_timestamps(self):
        """
        Test profile missing leading timestamps.

        Test that reindexing a profile missing leading timestamps fills them
        with the fill value (0).
        """
        index = pd.date_range(
            start="2024-01-01 00:00+01:00",
            end="2024-01-01 04:00+01:00",
            freq="h",
        )

        profile = {
            pd.Timestamp("2024-01-01 02:00+01:00"): 30,
            pd.Timestamp("2024-01-01 03:00+01:00"): 40,
            pd.Timestamp("2024-01-01 04:00+01:00"): 50,
        }

        result = {
            pd.Timestamp("2024-01-01 00:00+01:00"): 0,
            pd.Timestamp("2024-01-01 01:00+01:00"): 0,
            pd.Timestamp("2024-01-01 02:00+01:00"): 30,
            pd.Timestamp("2024-01-01 03:00+01:00"): 40,
            pd.Timestamp("2024-01-01 04:00+01:00"): 50,
        }

        assert reindex_profile(profile, index, fill_value=0) == result

    def test_rounding(self):
        """
        Test profile with timestamps needing rounding.

        Test that reindexing a profile with timestamps that are close to the
        index timestamps rounds them correctly.
        """
        index = pd.date_range(
            start="2024-01-01 00:00+00:00",
            end="2024-01-01 04:00+00:00",
            freq="h",
        )

        profile_index = pd.date_range(
            start="2024-01-01 00:05+00:00",
            end="2024-01-01 04:05+00:00",
            freq="h",
        )
        profile = {t: (i + 1) * 10 for i, t in enumerate(profile_index)}

        result = {t: (i + 1) * 10 for i, t in enumerate(index)}

        assert (
            reindex_profile(
                profile,
                index,
                fill_value=0,
                tolerance=datetime.timedelta(minutes=5),
            )
            == result
        )


class Test_Adjust_Battery_Timestamps:
    """
    Test adjustment of battery timestamps to a given index.

    This class contains tests for the adjustment of battery timestamps to
    ensure they align correctly with a specified index.
    """
    def test_timestamps_aligned(self):
        """
        Test battery with timestamps already aligned to index.

        Test that a battery with start and end SoC times already aligned to
        the index remains unchanged.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        battery = Battery(
            start_soc_time=index[0],
            end_soc_time=index[1],
            start_soc=0.5,
            end_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        assert adjust_battery_timestamps(battery, index) == battery

    def test_forward_adjustment(self):
        """
        Test battery with timestamps needing forward adjustment.

        Test that a battery with start SoC times slightly before the
        index timestamps are adjusted forward correctly. The end SoC time
        is already aligned.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        battery = Battery(
            start_soc_time=index[0] - datetime.timedelta(minutes=10),
            end_soc_time=index[1],
            start_soc=0.5,
            end_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        adjusted_battery = battery.model_copy(
            update={
                "start_soc_time": index[0],
            }
        )

        assert adjust_battery_timestamps(battery, index) == adjusted_battery

    def test_backward_adjustment(self):
        """
        Test battery with timestamps needing backward adjustment.

        Test that a battery with end SoC times slightly after the
        index timestamps are adjusted backward correctly. The start SoC time
        is already aligned.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        battery = Battery(
            start_soc_time=index[0],
            end_soc_time=index[1] + datetime.timedelta(minutes=10),
            start_soc=0.5,
            end_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        adjusted_battery = battery.model_copy(
            update={
                "end_soc_time": index[1],
            }
        )

        assert adjust_battery_timestamps(battery, index) == adjusted_battery

    def test_start_after_end(self):
        """
        Test battery with start SoC time after the last index timestamp.

        Test that a battery with start SoC time after the last index timestamp
        raises an error.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        battery = Battery(
            start_soc_time=index[1] + datetime.timedelta(minutes=10),
            end_soc_time=index[1] + datetime.timedelta(minutes=20),
            start_soc=0.5,
            end_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        with pytest.raises(
            ValueError,
            match="start_soc_time must be before the last timestamp",
        ):
            adjust_battery_timestamps(battery, index)

    def test_end_before_start(self):
        """
        Test battery with end SoC time before the first index timestamp.

        Test that a battery with end SoC time before the first index timestamp
        raises an error.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        battery = Battery(
            start_soc_time=index[0] - datetime.timedelta(minutes=20),
            end_soc_time=index[0] - datetime.timedelta(minutes=10),
            start_soc=0.5,
            end_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        with pytest.raises(
            ValueError,
            match="end_soc_time must be after the first timestamp",
        ):
            adjust_battery_timestamps(battery, index)

    def test_rounding(self):
        """
        Test battery with timestamps needing rounding.

        Test that a battery with start and end SoC times slightly off the
        index timestamps are adjusted correctly using rounding.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        battery = Battery(
            start_soc_time=index[0] + datetime.timedelta(minutes=5),
            end_soc_time=index[1] - datetime.timedelta(minutes=5),
            start_soc=0.5,
            end_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        adjusted_battery = battery.model_copy(
            update={
                "start_soc_time": index[0],
                "end_soc_time": index[1],
            }
        )

        assert (
            adjust_battery_timestamps(
                battery,
                index,
                tolerance=datetime.timedelta(minutes=10),
            )
            == adjusted_battery
        )


class Test_Adjust_Heat_Pump_Timestamps:
    """
    Test adjustment of heat pump timestamps to a given index.

    This class contains tests for the adjustment of heat pump timestamps to
    ensure they align correctly with a specified index.
    """
    def test_float_values(self):
        """
        Test heat pump with float values that are not adjusted.

        Test that parameters that can have a float value instead of a time
        series are not altered by the method.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        heat_pump = HeatPump(
            cop_output_temperature=4.0,
            cop_flow_temperature=3.5,
            temp_room=20.0,
            outdoor_temperature=15.0,
            heat_demand={
                pd.Timestamp("2024-01-01 00:00+00:00"): 10.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 10.0,
            },
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        assert adjust_heat_pump_timestamps(heat_pump, index) == heat_pump

    def test_timestamps_aligned(self):
        """
        Test heat pump with timestamps already aligned to index.

        All parameters that can be a time series have timestamps aligned to
        the index and thus remain unchanged.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        heat_pump = HeatPump(
            cop_output_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 4.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 4.0,
            },
            cop_flow_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 3.5,
                pd.Timestamp("2024-01-01 01:00+00:00"): 3.5,
            },
            temp_room={
                pd.Timestamp("2024-01-01 00:00+00:00"): 20.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 20.0,
            },
            outdoor_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 15.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 15.0,
            },
            heat_demand={
                pd.Timestamp("2024-01-01 00:00+00:00"): 10.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 10.0,
            },
            warm_water_demand={
                pd.Timestamp("2024-01-01 00:00+00:00"): 5.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 5.0,
            },
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        assert adjust_heat_pump_timestamps(heat_pump, index) == heat_pump

    def test_adjustment(self):
        """
        Test that adjustment behaves like reindexing.

        The heat pump parameters are time series and should each be adjusted
        like reindexing a profile.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
            pd.Timestamp("2024-01-01 02:00+00:00"),
        ]
        heat_pump = HeatPump(
            cop_output_temperature={
                pd.Timestamp("2024-01-01 00:30+00:00"): 4.0,
                pd.Timestamp("2024-01-01 01:30+00:00"): 5.0,
                pd.Timestamp("2024-01-01 02:30+00:00"): 6.0,
            },
            cop_flow_temperature={
                pd.Timestamp("2024-01-01 00:30+00:00"): 3.5,
                pd.Timestamp("2024-01-01 01:30+00:00"): 4.5,
                pd.Timestamp("2024-01-01 02:30+00:00"): 5.5,
            },
            temp_room={
                pd.Timestamp("2024-01-01 00:30+00:00"): 20.0,
                pd.Timestamp("2024-01-01 01:30+00:00"): 22.0,
                pd.Timestamp("2024-01-01 02:30+00:00"): 24.0,
            },
            outdoor_temperature={
                pd.Timestamp("2024-01-01 00:30+00:00"): 15.0,
                pd.Timestamp("2024-01-01 01:30+00:00"): 17.0,
                pd.Timestamp("2024-01-01 02:30+00:00"): 19.0,
            },
            heat_demand={
                pd.Timestamp("2024-01-01 00:30+00:00"): 10.0,
                pd.Timestamp("2024-01-01 01:30+00:00"): 12.0,
                pd.Timestamp("2024-01-01 02:30+00:00"): 14.0,
            },
            warm_water_demand={
                pd.Timestamp("2024-01-01 00:30+00:00"): 5.0,
                pd.Timestamp("2024-01-01 01:30+00:00"): 6.0,
                pd.Timestamp("2024-01-01 02:30+00:00"): 7.0,
            },
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        expected_heat_pump = HeatPump(
            cop_output_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 4.0,
                pd.Timestamp("2024-01-01 02:00+00:00"): 5.0,
            },
            cop_flow_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 3.5,
                pd.Timestamp("2024-01-01 02:00+00:00"): 4.5,
            },
            temp_room={
                pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 20.0,
                pd.Timestamp("2024-01-01 02:00+00:00"): 22.0,
            },
            outdoor_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 15.0,
                pd.Timestamp("2024-01-01 02:00+00:00"): 17.0,
            },
            heat_demand={
                pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 10.0,
                pd.Timestamp("2024-01-01 02:00+00:00"): 12.0,
            },
            warm_water_demand={
                pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 5.0,
                pd.Timestamp("2024-01-01 02:00+00:00"): 6.0,
            },
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        assert (
            adjust_heat_pump_timestamps(heat_pump, index) == expected_heat_pump
        )

    def test_rounding(self):
        """
        Test heat pump with timestamps needing rounding.

        Test that a heat pump with time series parameters slightly off the
        index timestamps are adjusted correctly using rounding.
        """
        index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
        ]
        heat_pump = HeatPump(
            cop_output_temperature={
                pd.Timestamp("2024-01-01 00:05+00:00"): 4.0,
                pd.Timestamp("2024-01-01 01:05+00:00"): 5.0,
            },
            cop_flow_temperature={
                pd.Timestamp("2024-01-01 00:05+00:00"): 3.5,
                pd.Timestamp("2024-01-01 01:05+00:00"): 4.5,
            },
            temp_room={
                pd.Timestamp("2024-01-01 00:05+00:00"): 20.0,
                pd.Timestamp("2024-01-01 01:05+00:00"): 22.0,
            },
            outdoor_temperature={
                pd.Timestamp("2024-01-01 00:05+00:00"): 15.0,
                pd.Timestamp("2024-01-01 01:05+00:00"): 17.0,
            },
            heat_demand={
                pd.Timestamp("2024-01-01 00:05+00:00"): 10.0,
                pd.Timestamp("2024-01-01 01:05+00:00"): 12.0,
            },
            warm_water_demand={
                pd.Timestamp("2024-01-01 00:05+00:00"): 5.0,
                pd.Timestamp("2024-01-01 01:05+00:00"): 6.0,
            },
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        expected_heat_pump = HeatPump(
            cop_output_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 4.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 5.0,
            },
            cop_flow_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 3.5,
                pd.Timestamp("2024-01-01 01:00+00:00"): 4.5,
            },
            temp_room={
                pd.Timestamp("2024-01-01 00:00+00:00"): 20.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 22.0,
            },
            outdoor_temperature={
                pd.Timestamp("2024-01-01 00:00+00:00"): 15.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 17.0,
            },
            heat_demand={
                pd.Timestamp("2024-01-01 00:00+00:00"): 10.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 12.0,
            },
            warm_water_demand={
                pd.Timestamp("2024-01-01 00:00+00:00"): 5.0,
                pd.Timestamp("2024-01-01 01:00+00:00"): 6.0,
            },
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        assert (
            adjust_heat_pump_timestamps(
                heat_pump,
                index,
                tolerance=datetime.timedelta(minutes=10),
            )
            == expected_heat_pump
        )


class Test_Mixed_Timestamp_Adjustments:
    """
    Test adjustment of profiles, batteries and heat pumps together.

    This class contains tests for the adjustment of profiles, batteries and
    heat pumps to a common index.
    """
    def test_profiles_batteries_heat_pumps(self):
        """
        Test adjustment of profiles, batteries and heat pumps together.

        Test that profiles, batteries and heat pumps are all adjusted to a
        common index correctly.
        """
        profile = {
            pd.Timestamp("2024-01-01 00:05+00:00"): 10,
            pd.Timestamp("2024-01-01 01:15+00:00"): 20,
            pd.Timestamp("2024-01-01 02:05+00:00"): 30,
            pd.Timestamp("2024-01-01 03:00+00:00"): 40,
        }

        battery = Battery(
            start_soc_time=pd.Timestamp("2024-01-01 01:20+00:00"),
            end_soc_time=pd.Timestamp("2024-01-01 02:30+00:00"),
            start_soc=0.5,
            end_soc=0.5,
            capacity=1000,
            max_charge_power=500,
        )

        heat_pump = HeatPump(
            cop_output_temperature={
                pd.Timestamp("2024-01-01 00:45+00:00"): 4.0,
                pd.Timestamp("2024-01-01 01:45+00:00"): 5.0,
            },
            cop_flow_temperature={
                pd.Timestamp("2024-01-01 00:45+00:00"): 3.5,
                pd.Timestamp("2024-01-01 01:45+00:00"): 4.5,
            },
            temp_room={
                pd.Timestamp("2024-01-01 00:45+00:00"): 20.0,
                pd.Timestamp("2024-01-01 01:45+00:00"): 22.0,
            },
            outdoor_temperature={
                pd.Timestamp("2024-01-01 00:45+00:00"): 15.0,
                pd.Timestamp("2024-01-01 01:45+00:00"): 17.0,
            },
            heat_demand={
                pd.Timestamp("2024-01-01 00:45+00:00"): 10.0,
                pd.Timestamp("2024-01-01 01:45+00:00"): 12.0,
            },
            warm_water_demand={
                pd.Timestamp("2024-01-01 00:45+00:00"): 5.0,
                pd.Timestamp("2024-01-01 01:45+00:00"): 6.0,
            },
            flow_temperature=35,
            output_temperature=55,
            max_electric_power_hp=2,
            max_electric_power_hr=0,
            tank_volume=300,
        )

        index = generate_common_time_series(
            profiles=[profile],
            batteries=[battery],
            heat_pumps=[heat_pump],
            round_freq="30min",
        )

        expected_index = [
            pd.Timestamp("2024-01-01 00:00+00:00"),
            pd.Timestamp("2024-01-01 01:00+00:00"),
            pd.Timestamp("2024-01-01 01:30+00:00"),
            pd.Timestamp("2024-01-01 02:00+00:00"),
            pd.Timestamp("2024-01-01 02:30+00:00"),
            pd.Timestamp("2024-01-01 03:00+00:00"),
        ]

        assert index == expected_index

        # profile
        assert reindex_profile(profile, index) == {
            pd.Timestamp("2024-01-01 00:00+00:00"): 0,
            pd.Timestamp("2024-01-01 01:00+00:00"): 10,
            pd.Timestamp("2024-01-01 01:30+00:00"): 20,
            pd.Timestamp("2024-01-01 02:00+00:00"): 20,
            pd.Timestamp("2024-01-01 02:30+00:00"): 30,
            pd.Timestamp("2024-01-01 03:00+00:00"): 40,
        }

        # battery
        assert adjust_battery_timestamps(battery, index) == battery.model_copy(
            update={
                "start_soc_time": pd.Timestamp("2024-01-01 01:30+00:00"),
                "end_soc_time": pd.Timestamp("2024-01-01 02:30+00:00"),
            }
        )
        assert (
            adjust_battery_timestamps(battery, index).start_soc_time in index
        )
        assert adjust_battery_timestamps(battery, index).end_soc_time in index

        # heat pump
        assert adjust_heat_pump_timestamps(
            heat_pump, index
        ) == heat_pump.model_copy(
            update={
                "cop_output_temperature": {
                    pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                    pd.Timestamp("2024-01-01 01:00+00:00"): 4.0,
                    pd.Timestamp("2024-01-01 01:30+00:00"): 4.0,
                    pd.Timestamp("2024-01-01 02:00+00:00"): 5.0,
                    pd.Timestamp("2024-01-01 02:30+00:00"): 5.0,
                    pd.Timestamp("2024-01-01 03:00+00:00"): 5.0,
                },
                "cop_flow_temperature": {
                    pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                    pd.Timestamp("2024-01-01 01:00+00:00"): 3.5,
                    pd.Timestamp("2024-01-01 01:30+00:00"): 3.5,
                    pd.Timestamp("2024-01-01 02:00+00:00"): 4.5,
                    pd.Timestamp("2024-01-01 02:30+00:00"): 4.5,
                    pd.Timestamp("2024-01-01 03:00+00:00"): 4.5,
                },
                "temp_room": {
                    pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                    pd.Timestamp("2024-01-01 01:00+00:00"): 20.0,
                    pd.Timestamp("2024-01-01 01:30+00:00"): 20.0,
                    pd.Timestamp("2024-01-01 02:00+00:00"): 22.0,
                    pd.Timestamp("2024-01-01 02:30+00:00"): 22.0,
                    pd.Timestamp("2024-01-01 03:00+00:00"): 22.0,
                },
                "outdoor_temperature": {
                    pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                    pd.Timestamp("2024-01-01 01:00+00:00"): 15.0,
                    pd.Timestamp("2024-01-01 01:30+00:00"): 15.0,
                    pd.Timestamp("2024-01-01 02:00+00:00"): 17.0,
                    pd.Timestamp("2024-01-01 02:30+00:00"): 17.0,
                    pd.Timestamp("2024-01-01 03:00+00:00"): 17.0,
                },
                "heat_demand": {
                    pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                    pd.Timestamp("2024-01-01 01:00+00:00"): 10.0,
                    pd.Timestamp("2024-01-01 01:30+00:00"): 10.0,
                    pd.Timestamp("2024-01-01 02:00+00:00"): 12.0,
                    pd.Timestamp("2024-01-01 02:30+00:00"): 12.0,
                    pd.Timestamp("2024-01-01 03:00+00:00"): 12.0,
                },
                "warm_water_demand": {
                    pd.Timestamp("2024-01-01 00:00+00:00"): 0,
                    pd.Timestamp("2024-01-01 01:00+00:00"): 5.0,
                    pd.Timestamp("2024-01-01 01:30+00:00"): 5.0,
                    pd.Timestamp("2024-01-01 02:00+00:00"): 6.0,
                    pd.Timestamp("2024-01-01 02:30+00:00"): 6.0,
                    pd.Timestamp("2024-01-01 03:00+00:00"): 6.0,
                },
            }
        )
        for parameter in [
            "cop_output_temperature",
            "cop_flow_temperature",
            "temp_room",
            "outdoor_temperature",
            "heat_demand",
            "warm_water_demand",
        ]:
            assert all(
                t in index
                for t in getattr(
                    adjust_heat_pump_timestamps(heat_pump, index), parameter
                ).keys()
            )
