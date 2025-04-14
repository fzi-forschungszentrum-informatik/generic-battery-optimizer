import datetime
import numpy as np
import pandas as pd
import logging

log = logging.getLogger(__name__)


def tank_dimensions(volume: int | float):
    """Calculate height and radius of a tank from the volume

    This function calculates the radius and height of a tank
    with a given volume based on typical tank dimensions.
    Warm water tanks usually have a height to diameter ratio of 2:1 to 3:1.
    The mean diameter is determined by the volume and the height is calculated.

    Arguments
    ---------
    volume: int | float
        The volume of the tank in m^3

    Returns
    -------
    radius: float
        The radius of the tank in m
    height: float
        The height of the tank in m
    """
    if volume <= 0:
        return 0, 0

    h2r = (volume / (4 * np.pi)) ** (1 / 3)
    h3r = (volume / (6 * np.pi)) ** (1 / 3)

    radius = (h2r + h3r) / 2

    height = volume / (np.pi * radius**2)
    return radius, height


def heat_loss_tank(
    height: int | float,
    radius: int | float,
    u_value_material: int | float,
    tempretaure_difference: int | float,
) -> float:
    """Transmission heat losses of the tank

    Calculates the transmission heat losses of the tank based on the
    temperature difference between the tank inside and outside.

    Arguments
    ---------
    height: int | float
        The height of the tank in m
    radius: int | float
        The radius of the tank in m
    u_value_material: int | float
        The U-value of the insulation material of the tank in W/(m^2*K)
        This is usually between 0.3 and 0.7 W/(m^2*K)
    tempretaure_difference: int | float
        The temperature difference between the tank and the room temperature
        in K

    Returns
    -------
    float
        The heat loss of the tank in kW
    """
    return (
        (2 * np.pi * radius * (radius + height))
        * u_value_material
        * tempretaure_difference
    ) / 1000


def reverse_resolution(scale: int | float):
    """
    Funktion, welche aus einem int/float Wert, welcher die Periodenlänge in Stunden enthält einen String erzeugt,
    der die Periodendauer beschreibt

    scale:      int/float, welcher Periodenläng in h enthält

    Rückgabe:
    string, welcher die Periodenlänge enthält --> Bsp.: 0.25 --> "15Min"
    """

    value_Min = int(scale * 60)
    res_string = f"{value_Min}Min"
    return res_string


def interpolate_temperature(
    temperature: float | dict[datetime.datetime, float],
    current_period: datetime.datetime,
):
    """Returns the temperature for the current period.

    If the temperature is a float, it is returned as is.
    If the temperature is a dictionary, the temperature for the current period
    is returned either by the exact key if available or it is linearly
    interpolated between the two closest keys.

    ----------
    Variables:

    temperature: float | dict[datetime.datetime, float]
        The temperature for the optimization duration

    current_period: datetime.datetime
        The current period for which the temperature should be returned

    --------
    Returns:

    temperature: float
        The temperature for the current period in K"""
    # Just return the temperature if it is a float
    if isinstance(temperature, float):
        return temperature
    # Return exact temperature if available
    elif current_period in temperature:
        return temperature[current_period]
    # Interpolate temperature if not available
    else:
        temperature[current_period] = None
        series = pd.Series(temperature).sort_index().interpolate(method="time")
        return series[current_period]


def interpolate_heat_energy(
    heat_demand: float | dict[datetime.datetime, float],
    current_period: datetime.datetime,
) -> float:
    """Returns the heat energy demand for the current period.

    If the temperature is a float it is assumed to be a constant heat demand
    in each period in kW.
    """
    if not heat_demand:
        return 0
    # Just return the heat demand if it is a float
    elif isinstance(heat_demand, float):
        return heat_demand
    # Return exact heat demand if available
    elif current_period in heat_demand:
        return heat_demand[current_period]
    else:
        raise NotImplementedError("Interpolating heat energy is not supported")
