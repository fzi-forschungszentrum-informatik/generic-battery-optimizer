"""
Helping methods to assist in setting up a model.

- Index creation from multiple devices/profiles
- Rewriting models and profiles to match index
"""

from collections.abc import Sequence
import datetime
from typing import Any

import pandas as pd

from battery_optimizer.profiles.battery import Battery
from battery_optimizer.profiles.heat_pump import HeatPump


def generate_common_time_series(
    profiles: list[dict[str | datetime.datetime, Any]] = [],
    batteries: list[Battery] = [],
    heat_pumps: list[HeatPump] = [],
) -> Sequence[datetime.datetime]:
    """
    Builds a unified index from all given components as timestamps.

    Each component is assumed to be a list of components and each component
    has a "times" key that contains a list of timestamps.

    Parameters
    ----------
    profiles : list[dict[str, datetime.datetime]]
        A list of dicts containing profiles as dicts with datetimes as keys.
    batteries : list[Battery]
        A list of battery components. All timestamps from the batteries will be
        included in the index.
    heat_pumps : list[HeatPump]
        A list of heat pump components. All timestamps from the heat pumps will
        be included in the index.

    Returns
    -------
    index : list[datetime.datetime]
        A sorted list containing all unique timestamps from the profiles.
    """
    index: set[datetime.datetime] = set()
    index.update(
        pd.to_datetime(time) for profile in profiles for time in profile.keys()
    )

    # Battery
    for battery in batteries:
        if battery.start_soc_time:
            index.add(battery.start_soc_time)
        if battery.end_soc_time:
            index.add(battery.end_soc_time)

    # Heat pump
    for hp in heat_pumps:
        if isinstance(hp.temp_room, dict):
            index.update(hp.temp_room.keys())
        if isinstance(hp.outdoor_temperature, dict):
            index.update(hp.outdoor_temperature.keys())
        if isinstance(hp.heat_source_temperature, dict):
            index.update(hp.heat_source_temperature.keys())
        if isinstance(hp.heat_demand, dict):
            index.update(hp.heat_demand.keys())
        if isinstance(hp.warm_water_demand, dict):
            index.update(hp.warm_water_demand.keys())
    return sorted(index)
