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


# TODO Add rounding of timestamps e.g. to full minutes, 5-minutes, seconds, hourly
# add this as a separate endpoint to the service
# fit-parameters Endpoint vom esg-service

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


# What happens when the profile contains indices that are not in the index
def reindex_profile(
    profile: dict[str | datetime.datetime, Any],
    index: list[datetime.datetime],
    fill_value: Any = 0,
) -> dict[datetime.datetime, Any]:
    """
    Reindexes a profile to match the given index.

    All values after the first time step in the profile will be forward filled.
    Values in the index that precede the first time step in the profile
    will be filled with the given fill_value (by default 0).

    Parameters
    ----------
    profile : dict[str | datetime.datetime, Any]
        A profile as a dictionary with datetimes as keys.
    index : list[datetime.datetime]
        The target index to reindex the profile to.
    fill_value : Any, optional
        The value to use for missing timestamps in the profile, by default 0.

    Returns
    -------
    reindexed_profile : dict[datetime.datetime, Any]
        The reindexed profile as a dictionary with datetimes as keys.
    """
    # Convert keys to datetime if they are strings
    datetime_index = pd.to_datetime(index).sort_values()
    series = pd.Series(
        {pd.to_datetime(time): value for time, value in profile.items()}
    )
    reindexed_series = series.reindex(datetime_index, method="ffill")
    reindexed_series = reindexed_series.fillna(fill_value)
    return reindexed_series.to_dict()
