"""
Test the helping methods to create the model index and reindex profiles.

The method generate_common_time_series is tested in various scenarios to ensure
it correctly combines timestamps from profiles, batteries, and heat pumps.
The reindex_profile method is tested to ensure it correctly forward fills
values, raises for missing leading data and tests rounding of timestamps.
"""

import pandas as pd
from battery_optimizer.helpers.model_setup import (
    generate_common_time_series,
    reindex_profile,
)
from battery_optimizer.profiles.battery import Battery
from battery_optimizer.profiles.heat_pump import HeatPump


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
            cop_high_temp={pd.Timestamp("2024-01-01 01:00+00:00"): 4.0},
            cop_low_temp={pd.Timestamp("2024-01-01 02:00+00:00"): 3.5},
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
            cop_high_temp=4.0,
            cop_low_temp=3.5,
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
            cop_high_temp={pd.Timestamp("2024-01-01 01:00+00:00"): 4.0},
            cop_low_temp={pd.Timestamp("2024-01-01 02:00+00:00"): 3.5},
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
