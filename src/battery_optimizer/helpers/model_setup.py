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
from battery_optimizer.profiles.ev import EV
from battery_optimizer.profiles.heat_pump import HeatPump


# TODO add this as a separate endpoint to the service
# possibly fit-parameters Endpoint vom esg-service
def generate_common_time_series(
    profiles: list[dict[str | datetime.datetime, Any]] | None = None,
    # TODO DEPRECATED: Remove in 5.0.0
    batteries: list[Battery] | None = None,
    evs: list[EV] | None = None,
    heat_pumps: list[HeatPump] | None = None,
    round_freq: str | None = None,
) -> Sequence[datetime.datetime]:
    """
    Build a unified index from all given components as timestamps.

    Each component is assumed to be a list of components and each component
    has a "times" key that contains a list of timestamps.

    Parameters
    ----------
    profiles : list[dict[str, datetime.datetime]]
        A list of dicts containing profiles as dicts with datetimes as keys.
    batteries : list[Battery]
        A list of battery components. All timestamps from the batteries will be
        included in the index.
    evs : list[EV]
        A list of ev components. All timestamps from the evs will be
        included in the index.
    heat_pumps : list[HeatPump]
        A list of heat pump components. All timestamps from the heat pumps will
        be included in the index.
    round_freq : str | None, optional
        If given, all timestamps will be rounded to the closest frequency
        specified by the pandas offset alias string (e.g. '5min', 'h'), by
        default None.

    Returns
    -------
    list[datetime.datetime]
        A sorted list containing all unique timestamps from the profiles.

    Examples
    --------
    >>> from datetime import datetime
    >>> from battery_optimizer.profiles.ev import EV
    >>> from battery_optimizer.profiles.heat_pump import HeatPump
    >>> profiles = [
    ...     {datetime(2024, 6, 1, 12, 0): 1, datetime(2024, 6, 1, 12, 5): 2},
    ...     {datetime(2024, 6, 1, 12, 10): 3}
    ... ]
    >>> evs = [
    ...     EV(
    ...         charge_start_time = datetime(2024, 6, 1, 12, 15),
    ...         charge_end_time = datetime(2024, 6, 1, 12, 20)
    ...     )
    ... ]
    >>> heat_pumps = [
    ...     HeatPump(
    ...         heat_demand={datetime(2024, 6, 1, 12, 25): 21}
    ...     )
    ... ]
    >>> generate_common_time_series(profiles, evs, heat_pumps)
    [
        datetime.datetime(2024, 6, 1, 12, 0),
        datetime.datetime(2024, 6, 1, 12, 5),
        datetime.datetime(2024, 6, 1, 12, 10),
        datetime.datetime(2024, 6, 1, 12, 15),
        datetime.datetime(2024, 6, 1, 12, 20),
        datetime.datetime(2024, 6, 1, 12, 25)
    ]
    >>> generate_common_time_series(
    ...     profiles, evs, heat_pumps, round_freq='10min'
    ... )
    [
        Timestamp('2024-06-01 12:00:00'),
        Timestamp('2024-06-01 12:10:00'),
        Timestamp('2024-06-01 12:20:00')
    ]
    """
    index: set[datetime.datetime] = set()
    profiles = profiles or []
    batteries = batteries or []
    evs = evs or []
    heat_pumps = heat_pumps or []
    index.update(
        pd.to_datetime(time) for profile in profiles for time in profile.keys()
    )

    # TODO DEPRECATED: Remove in 5.0.0
    # Batteries
    for battery in batteries:
        if battery.start_soc_time:
            index.add(battery.start_soc_time)
        if battery.end_soc_time:
            index.add(battery.end_soc_time)

    # EV
    for ev in evs:
        if ev.charge_start_time:
            index.add(ev.charge_start_time)
        if ev.charge_end_time:
            index.add(ev.charge_end_time)

    # Heat pump
    for hp in heat_pumps:
        index.update(hp.heat_demand.keys())
        if isinstance(hp.cop_output_temperature, dict):
            index.update(hp.cop_output_temperature.keys())
        if isinstance(hp.cop_flow_temperature, dict):
            index.update(hp.cop_flow_temperature.keys())
        if isinstance(hp.temp_room, dict):
            index.update(hp.temp_room.keys())
        if isinstance(hp.outdoor_temperature, dict):
            index.update(hp.outdoor_temperature.keys())
        if isinstance(hp.warm_water_demand, dict):
            index.update(hp.warm_water_demand.keys())

    if round_freq is not None:
        index = {pd.to_datetime(time).round(round_freq) for time in index}
    return sorted(pd.to_datetime(i) for i in index)


# What happens when the profile contains indices that are not in the index
def reindex_profile(
    profile: dict[str | datetime.datetime | pd.Timestamp, Any],
    index: list[str | datetime.datetime | pd.Timestamp],
    fill_value: Any = 0,
    tolerance: datetime.timedelta = datetime.timedelta(0),
) -> dict[pd.Timestamp, Any]:
    """
    Reindex a profile to match the given index.

    All values after the first time step in the profile will be forward filled.
    Values in the index that precede the first time step in the profile
    will be filled with the given fill_value (by default 0).
    WARNiNG: If there are timestamps in the profile that are not in the index,
    they may be ignored and profiles WILL NOT have the same information.
    The tolerance is used to set a gap between a timestamp in the profile and
    the index where it is assumed that these timestamps are close enough to be
    considered equal. If the difference between a timestamp in the profile and
    the index is less than or equal to the tolerance, the timestamp from the
    profile will be replaced by the one from the index regardless of whether
    the index from the profile is later or earlier. This is useful when dealing
    with profiles that have been recorded with slight time shifts.

    Parameters
    ----------
    profile : dict[str | datetime.datetime | pd.Timestamp, Any]
        A profile as a dictionary with datetimes as keys.
    index : list[str | datetime.datetime | pd.Timestamp]
        The target index to reindex the profile to.
    fill_value : Any, optional
        The value to use for missing timestamps in the profile, by default 0.
    tolerance : datetime.timedelta | None, optional
        The maximum allowed difference between timestamps to consider them
        equal, by default no tolerance is accepted.

    Returns
    -------
    dict[pd.Timestamp, Any]
        The reindexed profile as a dictionary with datetimes as keys.
    """
    # Convert keys to datetime if they are strings
    datetime_index = sorted(pd.to_datetime(i) for i in index)
    if tolerance > datetime.timedelta(0):
        adjusted_profile = {}
        for time, value in profile.items():
            original_time = pd.to_datetime(time)
            # Find if there is a time in the index within the tolerance
            closest_time = min(
                datetime_index,
                key=lambda x: abs(x - original_time),
            )
            if abs(closest_time - original_time) <= tolerance:
                adjusted_profile[closest_time] = value
            else:
                adjusted_profile[original_time] = value
        profile = adjusted_profile

    series = pd.Series(
        {pd.to_datetime(time): value for time, value in profile.items()}
    )
    reindexed_series = series.reindex(datetime_index, method="ffill")
    reindexed_series = reindexed_series.fillna(fill_value)
    return reindexed_series.to_dict()


def adjust_ev_timestamps(
    ev: EV,
    index: list[datetime.datetime],
    tolerance: datetime.timedelta = datetime.timedelta(0),
) -> EV:
    """
    Adjust the ev's start and end SoC timestamps to match the given index.

    The start soc will be set to the closest successor of its value in the
    index. The end soc will be set to the closest predecessor of its value in
    the index. This ensures that the ev's operation period is not extended
    beyond its original limits.

    Parameters
    ----------
    ev : EV
        The ev to adjust.
    index : list[datetime.datetime]
        The target index to adjust the ev's timestamps to.
    tolerance : datetime.timedelta | None, optional
        The maximum allowed difference between timestamps to consider them
        equal, by default no tolerance is accepted.

    Returns
    -------
    EV
        The ev with adjusted timestamps.
    """
    datetime_index = pd.to_datetime(index).sort_values()

    if ev.charge_start_time:
        # get all candidates that are after or equal to the charge_start_time
        candidates = [
            time
            for time in datetime_index
            if time >= ev.charge_start_time - tolerance
        ]
        if not candidates:
            raise ValueError(
                "charge_start_time must be before the last timestamp of the "
                "index"
            )

        # find the closest candidate to the original charge_start_time
        closest_time = min(
            candidates, key=lambda x: abs(x - ev.charge_start_time)
        )

        # if the closest candidate is within the tolerance, use it
        if abs(closest_time - ev.charge_start_time) <= tolerance:
            ev.charge_start_time = closest_time
        else:
            ev.charge_start_time = min(candidates)

    if ev.charge_end_time:
        # get all candidates that are before or equal to the charge_end_time
        candidates = [
            time
            for time in datetime_index
            if time <= ev.charge_end_time + tolerance
        ]
        if not candidates:
            raise ValueError(
                "charge_end_time must be after the first timestamp of the "
                "index"
            )

        # find the closest candidate to the original charge_end_time
        closest_time = min(
            candidates, key=lambda x: abs(x - ev.charge_end_time)
        )
        # if the closest candidate is within the tolerance, use it
        if abs(closest_time - ev.charge_end_time) <= tolerance:
            ev.charge_end_time = closest_time
        else:
            ev.charge_end_time = max(candidates)

    return ev


def adjust_heat_pump_timestamps(
    heat_pump: HeatPump,
    index: list[datetime.datetime],
    tolerance: datetime.timedelta = datetime.timedelta(0),
) -> HeatPump:
    """
    Adjust the heat pump's timestamps to match the given index.

    The timestamps in all timeseries attributes will be rounded to the closest
    timestamp in the index.

    Parameters
    ----------
    heat_pump : HeatPump
        The heat pump to adjust.
    index : list[datetime.datetime]
        The target index to adjust the heat pump's timestamps to.
    tolerance : datetime.timedelta | None, optional
        The maximum allowed difference between timestamps to consider them
        equal, by default no tolerance is accepted.

    Returns
    -------
    HeatPump
        The heat pump with adjusted timestamps.
    """

    for parameter in [
        "cop_output_temperature",
        "cop_flow_temperature",
        "temp_room",
        "outdoor_temperature",
        "heat_demand",
        "warm_water_demand",
    ]:
        if isinstance(getattr(heat_pump, parameter), dict):
            adjusted_profile = reindex_profile(
                getattr(heat_pump, parameter), index, tolerance=tolerance
            )
            setattr(heat_pump, parameter, adjusted_profile)
    return heat_pump
