"""
Helper functions for the heat pump implementation.

These functions include calculations for tank dimensions,
heat loss, and interpolation of temperature and heat energy demand that can be
used in the heat pump model.
"""

import datetime
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def tank_dimensions(volume: int | float):
    """
    Calculate height and radius of a tank from the volume.

    This function calculates the radius and height of a tank
    with a given volume based on typical tank dimensions.
    Warm water tanks usually have a height to diameter ratio of 2:1 to 3:1.
    The mean diameter is determined by the volume and the height is calculated.

    Parameters
    ----------
    volume : int | float
        The volume of the tank in l.

    Returns
    -------
    height : float
        The height of the tank in m.
    radius : float
        The radius of the tank in m.
    """
    if volume <= 0:
        return 0, 0

    volume_m3 = volume / 1000  # Convert l to m^3

    h2r = (volume_m3 / (4 * np.pi)) ** (1 / 3)
    h3r = (volume_m3 / (6 * np.pi)) ** (1 / 3)

    radius = (h2r + h3r) / 2

    height = volume_m3 / (np.pi * radius**2)
    return height, radius


def heat_loss_tank(
    height: int | float,
    radius: int | float,
    u_value_material: int | float = 0.6,
) -> float:
    """
    Transmission heat losses of the tank.

    Calculates the transmission heat losses of the tank based on the
    temperature difference between the tank inside and outside.

    Parameters
    ----------
    height : int | float
        The height of the tank in m.
    radius : int | float
        The radius of the tank in m.
    u_value_material : int | float
        The U-value of the insulation material of the tank in W/(m^2*K)
        This is usually between 0.3 and 0.7 W/(m^2*K).

    Returns
    -------
    float
        The heat loss of the tank in W/K.
    """
    return (2 * np.pi * radius * (radius + height)) * u_value_material


def reverse_resolution(scale: int | float):
    """
    Convert a period length in hours to a descriptive string.

    This function converts a numeric value representing the length of a period
    in hours into a human-readable string that specifies the equivalent period
    duration in minutes. For example, an input of 0.25 hours corresponds to
    a string of "15Min".

    Parameters
    ----------
    scale : int or float
        The duration of the period in hours.

    Returns
    -------
    str
        A string representing the period length in minutes, e.g., ``"15Min"``.

    Examples
    --------
    >>> reverse_resolution(0.25)
    '15Min'
    >>> reverse_resolution(1)
    '60Min'
    """
    value_Min = int(scale * 60)
    res_string = f"{value_Min}Min"
    return res_string


def interpolate_temperature(
    temperature: float | dict[datetime.datetime, float],
    current_period: datetime.datetime,
):
    """
    Return the temperature for the current period.

    If the temperature is a float, it is returned as is.
    If the temperature is a dictionary, the temperature for the current period
    is returned either by the exact key if available or it is linearly
    interpolated between the two closest keys.

    Parameters
    ----------
    temperature : float | dict[datetime.datetime, float]
        The temperature for the optimization duration.
    current_period : datetime.datetime
        The current period for which the temperature should be returned.

    Returns
    -------
    float
        The temperature for the current period in K.
    """
    # Just return the temperature if it is a float
    if isinstance(temperature, (float, int)):
        return temperature
    # Return exact temperature if available
    if current_period in temperature:
        return temperature[current_period]
    # Interpolate temperature if not available
    temperature[current_period] = None
    series = pd.Series(temperature).sort_index().interpolate(method="time")
    return series[current_period]


def interpolate_heat_energy(
    heat_demand: float | dict[datetime.datetime, float],
    current_period: datetime.datetime,
) -> float:
    """
    Return the heat energy demand for the current period.

    If the temperature is a float it is assumed to be a constant heat demand
    in each period in kW.

    Parameters
    ----------
    heat_demand : float | dict[datetime.datetime, float]
        The heat energy demand for the optimization duration in kW.
    current_period : datetime.datetime
        The current period for which the heat energy demand should be returned.

    Returns
    -------
    float
        The heat energy demand for the current period in kW.
    """
    if not heat_demand:
        return 0
    # Just return the heat demand if it is a float
    if isinstance(heat_demand, float):
        return heat_demand
    # Return exact heat demand if available
    if current_period in heat_demand:
        return heat_demand[current_period]
    # Interpolate heat demand if not available
    df = pd.Series(heat_demand)
    df[current_period] = None
    df.interpolate(method="time", inplace=True)
    return df[current_period]
