import datetime
import numpy as np
import pandas as pd
import pytz
import logging

from battery_optimizer.static.heat_pump import (
    C_TO_K,
    LOG_ERROR_TEMPERATURE_TOO_HIGH,
)

log = logging.getLogger(__name__)


def tank_dimensions(volume: int | float):
    """
    Funktion berechnet die Höhe und den Radius für den Tank aus dem
    angegebenen Volumen.
    Höhe und Radius sollen in einem Verhältnis zwischen
    2:1-5:1 liegen.
    Als Rückgabe wird für die Höhe und den Radius
    der Mittelwert für die Höhe und den Radius bei dem Verhältnis 2:1 und dem
    Verhältnis 5:1 genommen

    berechnet Höhe und Radius aus Volumen, Höhe Radius stehen im Verhältnis
    2:1-5:1

    volume: int/float, welcher Volumen des Tanks übergibt

    Rückgabe:
    radius, height: int/float, welche den Radius und die Höhe des Tanks
        zurückgeben
    """
    radius1 = (volume / (5 * np.pi)) ** (1 / 3)
    radius2 = (volume / (2 * np.pi)) ** (1 / 3)

    radius = ((radius1 + 0.05) + (radius2 + 0.05)) / 2

    height = volume / (np.pi * radius)

    return radius, height


def warm_water_heat_flow(
    living_area: int | float,
    ww_period: int | float,
    start: datetime.datetime,
    end: datetime.datetime,
):
    """
    Auf die warm water period(s) des Tages wird der TWE Bedarf gleichmäßig aufgeteilt
    Gibt die Wärmeenergie zurück, die für die TWE in einer Periode benötigt wird.
    Errechnet sich aus der anteiligen Zeit der Periode aus der Tagesmenge an warmen Wasser

    Funktion ermittelt aus der Anzahl der Perioden der TWE und dem
    Energieverbrauch für die TWE, den Wärmsetrom der TWE in einer Periode.
    Dabei wird der Tagesverbrauch gleichmäßig auf die Perioden aufgeteilt.

    living_area:    int/float, welche die Wohnfläche des Gebäudes enthält, um
                    Energieverbrauch für die TWE zu errechnen in m^2
    ww_period:      int/float, welcher Anzahl der Perioden für TWE enthält
    start:          datetime, welcher den Startzeitpunkt der zu simmulierenden
                    Periode enthält
    end:            datetime, welcher den Endzeitpunkt der zu simmulierenden
                    Periode enthält

    Rückgabe:
    int/float       wärmemenge der TWE in einer Periode in kWh
    """
    heat_warm_water_per_day = _warm_water_energy_day(living_area)
    # Share of time  in this period of days warm water period
    converted_ww_periods = parse_time_string_list(ww_period)

    heat_energy = 0
    for day in pd.date_range(start=start.date(), end=end.date(), freq="d"):
        overlapping_time = 0
        for period in converted_ww_periods:
            if period["start"].date() <= day.date() <= period["end"].date():
                overlap_start = max(period["start"], start)
                overlap_end = min(period["end"], end)
                if overlap_start < overlap_end:
                    overlapping_time += (
                        overlap_end - overlap_start
                    ).total_seconds()

        heat_energy += (overlapping_time / 3600) * (
            heat_warm_water_per_day / 24
        )

    return heat_energy


def _warm_water_energy_day(living_area: int | float):
    """
    Funktion liefert den Energiebedarf für die TWE des Gebäude für einen Tag.
    Zusätzlich zu errechneten Energiebedarf werden Verluste in Höhe von
    10 kWh/(m^2*a) dazu addiert.
    Ist der Energiebedarf pro m^2 pro Jahr < 7 kWh/(m^2*a), wird der
    Energiebedarf auf 7 kWh/(m^2*a) gesetzt

    living_area:       int/float, welche die Wohnfläche des Gebäudes
                            enthält

    Rückgabe:
    int/float, welche den täglichen Energiebedarf der TWE für das Gebäude
        enthält in kWh/Tag
    """
    coeff = _warm_water_energy_coeff(living_area)

    if coeff > 7:
        return ((coeff + 10) * living_area) / (365)
    else:
        return ((7 + 10) * living_area) / (365)


def _warm_water_energy_coeff(surface_building: int | float = 0):
    """
    Funktion liefert den Energiebedarf für die TWE in Abhängigkeit der
    Wohnfläche.
    Zurückgelieferter Wert gibt den Energiebedarf in kWh pro m^2 pro Jahr

    surface_building:       in/float, welche die Wohnfläche des Gebäudes angibt

    Rückgabe:
    in/float, welcher den benötigten Energiebedarf enthält
    """

    return 15 - surface_building * 0.04


def heat_loss_building(
    surface_U_value: dict, temp_outdoor: int | float, temp_comfort: int | float
):
    """
    Funktion berechnet die Energieverluste des Gebäude über die Transmissionwärmeverluste einzelner Gebäudebestandteile

    surface_U_value:    dict, welche die Flächen der einzelnen Gebäudebestandteile (Außenwand, Dach, Fenster)
                        mit deren U-werten speichert
    temp_outdoor:       int/float, welcher die Außentemperatur speichert
    temp_comfort:       int/float, welcher die angegeben Raumtemperatur speichert

    Rückgabe:
    loss:               int/float, welcher den Wärmeverluststrom in kW zurückgibt
    """

    loss = 0
    if temp_comfort > 100:
        log.debug(
            f"Comfort temperature is {temp_comfort}°C. "
            + LOG_ERROR_TEMPERATURE_TOO_HIGH
        )
        temp_comfort = temp_comfort - C_TO_K
    if temp_outdoor > 100:
        log.debug(
            f"Outside temperature is {temp_comfort}°C. "
            + LOG_ERROR_TEMPERATURE_TOO_HIGH
        )
        temp_outdoor = temp_outdoor - C_TO_K
    for key in surface_U_value.keys():
        values = surface_U_value[key]
        if temp_outdoor <= temp_comfort:
            loss += (
                values[0] * (values[1] / 1000) * (temp_comfort - temp_outdoor)
            )
        else:
            loss += 0.0
    return loss


def parse_time_string_list(
    date_list: list[str] | None, format: str | None = None
) -> list:
    """Parses time strings in the list to datetime objects



    Arguments:
    ----------
        date_list: list[str]
            List of date string ranges. The strings should be in the format:
            '2020-12-04 8:00:00+00:00 - 2020-12-04 15:00:00+00:00'
        format: str
            A special format parser for pandas to_datetime function

    Returns:
    --------
        ranges: list
            List of dictionaries with start and end keys containing the
            datetime objects of the periods
    """
    ranges = []
    if date_list is None:
        return ranges

    if len(date_list) == 0:
        return ranges

    if len(str(date_list[0])) < 26:
        date_frame = pd.to_datetime(date_list, format=format)
        ranges.append({"start": date_frame[0], "end": date_frame[-1]})

    else:
        for date in date_list:
            dates = date.split(" - ")
            ranges.append(
                {
                    "start": pd.to_datetime(dates[0], format=format),
                    "end": pd.to_datetime(dates[1], format=format),
                }
            )
    return ranges


def convert_list(
    date_list: list, model_index: pd.DatetimeIndex, format: str | None = None
):
    """
    Funktion, welche aus einer Liste mit Datumswerten als strings eine Liste
    mit den zugehörigen Zeitabschnitten erzeugt.
    Die Datumswerte in der Liste geben die Block-Perioden an, in welchen keine
    elektrische Leistung bezogen werden kann.
    Die zurückgebene Liste enthält dann die Datumswerte als datetime-Objekte

    date_list:      list, mit Datumswerten oder einem Zeitabschnitt in Form
                    eines strings
    model_index:    The DatetimeIndex of the model
    format:         string, welcher Format der Datumswerte enthält

    Rückgabe:       list with all date time objects from the model index that
                    are within the lists times
    """

    ranges = parse_time_string_list(date_list, format)
    block_list = []

    # Return all time stamps from the models index that are within the lists
    # times

    for range in ranges:
        for i in model_index:
            if range["start"] <= i <= range["end"]:
                block_list.append(i)
    block_list.sort()

    return block_list


# Wärmeverlust von Tank/Zylinder
# U-Werte zwischen 0,3-0,7 W/(m^2*K)
# Dämmdicke 50mm
def heat_loss_tank(
    height: int | float,
    radius: int | float,
    U_value_material: int | float,
    tempretaure_diff: int | float,
):
    """
    Funktion berechnet die Energieverluste des Tanks über die Transmissionswärmeverluste des Tanks aufgrund
    der Temperaturunterschiede zwischen Tank und Raumtemperatur

    height:     int/float, welcher Höhe des Tanks angibt
    radius:     int/float, welcher Radius des Tanks enthält
    U_value_material:       int/float, welcher U-Wert des Isolationsmaterial des Tanks enthält
    tempretaure_diff:       int/float, welche den Temperaturunterschied zwischen Tank- und Raumtemperatur enthält

    Rückgabe
    int/float, Verlustwärmestrom des Tanks in einer Periode
    """
    return (
        (2 * np.pi * radius * (radius + height))
        * U_value_material
        * tempretaure_diff
    ) / 1000


class TimeFrame:
    def __init__(
        self, start: datetime.datetime, end: datetime.datetime, resolution: str
    ):
        """
        :param start: time of the start of the simulation/investigation
        :param end: time of the end of the simulation/investigation
        :param resolution: string defining the resolution, using pandas offset aliases:
        https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases
        """
        self.tz = pytz.timezone("Europe/Berlin")
        if not start.tzinfo and not end.tzinfo:
            self.start = self.tz.localize(start)
            self.end = self.tz.localize(end)
        else:
            self.start = start
            self.end = end
        self.resolution = resolution
        self.resolution_influx = self._convert_resolution_to_influx_alias()
        self.index = self.generate_datetimeindex()

        self.freq = self.generate_freq()

        self.delta = pd.Timedelta(self.resolution)

    def _convert_resolution_to_influx_alias(self):
        if "min" in self.resolution:
            return self.resolution.replace("min", "m")

        if "S" in self.resolution:
            return self.resolution.replace("S", "s")

        else:
            return self.resolution

    def generate_datetimeindex(self):
        index = pd.date_range(
            self.start, self.end, freq=self.resolution, inclusive="left"
        )
        return index

    def generate_freq(self):
        freq_in_timedelta = pd.to_timedelta(self.resolution)
        freq_in_hours = freq_in_timedelta / pd.Timedelta(hours=1)
        return freq_in_hours

    def __str__(self):
        return f"{self.start.isoformat()} - {self.end.isoformat()}"


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


def get_period_length(period: pd.Timestamp, index: pd.DatetimeIndex):
    """Gets duration of models period

    Arguments:
    ----------
        period: pd.Timestamp
            The period to get the duration of
        index: pd.DatetimeIndex
            The index of the model
    Returns:
    --------
        period_length: pd.Timedelta
            The duration of the period
        period_conversion_factor: float
            The conversion factor of the period to hours
    """
    if period == index.last():
        period_length = 0
        period_conversion_factor = 1
    else:
        period_length = index.next(period) - period
        period_conversion_factor = period_length.total_seconds() / 3600
    return period_length, period_conversion_factor
