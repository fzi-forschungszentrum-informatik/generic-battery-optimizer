"""
Helper functions for hplib library for heat pump simulation.

This module provides a wrapper around the hplib library to generate
coefficient of performance (CoP) values for heat pumps for use in the
battery optimizer. It includes functionality to handle both single-value
and time series inputs for source and outdoor temperatures.
"""

from typing import Annotated, Optional, Any, Iterable, Self
import datetime
import logging
import pandas as pd
from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    model_validator,
)
import hplib.hplib as hpl
from battery_optimizer.static.heat_pump import MINIMUM_KELVIN


heat_pump_data = hpl.load_database()
log = logging.getLogger(__name__)


class HpLibProfile(BaseModel):
    """
    Required Data for hplib.

    This class defines the necessary parameters for configuring a heat pump
    using the hplib library. It includes validation to ensure that the provided
    heat pump type exists in the hplib database and that all required fields
    are provided when using a generic heat pump model.
    """

    @staticmethod
    def validate_type(v: str) -> str:
        """
        Validate that the heat pump type is in the hplib database.

        Validates the input against the available heat pumps from hplib.
        Additionally, "Generic" is allowed to specify a custom heat pump.

        Parameters
        ----------
        v : str
            The heat pump type to be validated.

        Returns
        -------
        str
            The validated heat pump type.
        """
        allowed_types = list(heat_pump_data["Type"].unique())
        if "Titel" in heat_pump_data.columns:
            allowed_types.extend(list(heat_pump_data["Titel"].unique()))
        allowed_types.extend(list(heat_pump_data["Model"].unique()))
        allowed_types.extend(["Generic"])
        _validate_distinct_item(v, allowed_types)
        return v

    type: Annotated[str, AfterValidator(validate_type)] = Field(
        title="hplib heat pump type",
        description=(
            "Heat pump model type for the heat pump simulation. The heat pump "
            "simulation uses [hplib](https://github.com/FZJ-IEK3-VSA/hplib) "
            "to estimate heat pump behavior. Many commercial heat pumps can "
            "be simulated or custom heat pumps can be specified. hplib "
            "supports Air/Water, Water/Water and Brine/Water heat pumps. "
            "Air/Air heat pumps are not supported by hplib and can only be "
            "modeled with a constant CoP (see cop_air field)."
            'Can be ["Generic"'
            '"All other [hplib](https://github.com/FZJ-IEK3-VSA/hplib) heat '
            'pump types available"]'
        ),
        examples=["AE050RXYDEG/EU & AE200RNWMEG/EU", "Air/Air", "Generic"],
    )

    flow_temperature: float = Field(
        title="Flow temperature [C]",
        description=(
            "The flow temperature of the heating circuit in Celsius. "
            "This is the temperature of the water as it leaves the heat "
            "pump/temperature energy storage and enters the heating system, "
            "such as radiators or underfloor heating."
        ),
        le=MINIMUM_KELVIN,
        examples=[303.15, 308.15, 313.15, 318.15],
    )

    # TODO can output temperature be retrieved from hplib?
    output_temperature: float = Field(
        title="Heat pump output temperature [C]",
        description=(
            "The high side output temperature of the heat pump in Celsius. "
            "This is the maximum temperature the heat pump can provide. "
            "Charging the TES above this temperature must be done by the "
            "backup heater."
        ),
        le=MINIMUM_KELVIN,
    )

    """Start of hplib specific data"""

    @staticmethod
    def validate_id(v: int | None) -> int | None:
        """
        Validate that the Group ID is in the hplib database.

        Validates the input against the available Group IDs from hplib.
        Additionally, None is allowed to specify that no Group ID is used when
        a type is specified.

        Parameters
        ----------
        v : int | None
            The Group ID to be validated.

        Returns
        -------
        int | None
            The validated Group ID or None (same as input).
        """
        if v is None:
            return v
        _validate_distinct_item(v, heat_pump_data["Group"].unique())
        return v

    id: Annotated[Optional[int], AfterValidator(validate_id)] = Field(
        default=None,
        title="hplib Group ID",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "[hplib](https://github.com/FZJ-IEK3-VSA/hplib#heat-pump-models-"
            "and-group-ids) uses it to return the correct model."
            "Available heat pump types are "
            "[1]: Air/Water regulated, [4]: Air/Water on-off, "
            "[2]: Brine/Water regulated, [5]: Brine/Water on-off, "
            "[3]: Water/Water regulated and [6]: Water/Water on-off."
        ),
        examples=[1, 2, 3, 4, 5, 6],
    )

    # These values are only needed/allowed when the type is Generic
    t_in: Optional[float] = Field(
        default=None,
        title="hplib heat pump temperature cool side (outdoors) [C]",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Temperature in C on the low temperature side of the heat pump. "
            "Usually the outside atmosphere."
        ),
        le=MINIMUM_KELVIN,
    )
    t_out: Optional[float] = Field(
        default=None,
        title="hplib heat pump temperature hot side (indoors) [C]",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Temperature in C on the warm temperature side of the heat pump. "
            "Usually the heat water output of the heat pump."
        ),
        le=MINIMUM_KELVIN,
    )
    p_th: Optional[float] = Field(
        default=None,
        title="hplib heat pump thermal output power [kW]",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Thermal output power at set point t_in, t_out "
            "(and for water/water, brine/water heat pumps t_amb = -7°C)."
        ),
    )

    @model_validator(mode="after")
    def validate_generic_hp_value_existence(self) -> Self:
        """
        Validate that all required fields are provided for Generic heat pumps.

        Ensures that when the heat pump type is "Generic", all necessary fields
        (id, t_in, t_out, p_th) are provided. Raises a ValueError if any of
        these fields are missing.

        Returns
        -------
        Self
            The validated HpLibProfile instance.

        Raises
        ------
        ValueError
            If any required fields for a Generic heat pump are missing.
        """
        if self.type == "Generic":
            if not all([self.id, self.t_in, self.t_out, self.p_th]):
                raise ValueError(
                    "All Generic heat pump values must be provided"
                )
        return self

    """End of hplib specific data"""


class HpLibWrapper:
    """
    Wrapper for hplib heat pump simulation for battery optimizer.

    This wrapper can be used to simulate heat pump cop values for heat pumps
    using [hplib](https://github.com/FZJ-IEK3-VSA/hplib).

    Parameters
    ----------
    heat_pump : HpLibProfile
        The heat pump configuration to be used for simulation.
    """

    def __init__(self, heat_pump: HpLibProfile):
        """
        Initialize the HpLibWrapper with a heat pump configuration.

        Stores the information of the heat pump and initializes the
        corresponding hplib heat pump model.

        Parameters
        ----------
        heat_pump : HpLibProfile
            The heat pump configuration to be used for simulation.
        """
        self.heat_pump: HpLibProfile = heat_pump
        self.hpl_heat_pump: hpl.HeatPump
        self._initialize_hpl_heat_pump()

    @staticmethod
    def _validate_source_and_outdoor_temp(
        source_temperature: dict[datetime.datetime, float] | float | int,
        outdoor_temperature: dict[datetime.datetime, float] | float | int,
    ) -> pd.DataFrame:
        """
        Validate source and outdoor temperature inputs.

        Validates that both inputs are of the same type (either float or dict).
        If both are floats, they are returned as single-item lists.
        If both are dicts, their values are extracted, sorted, and returned
        as lists.

        Parameters
        ----------
        source_temperature : dict[datetime.datetime, float] | float | int
            The temperature in Celsius of the heat source (e.g. air or water).
            This can be a single value or a dictionary with datetime keys and
            float values. When a dictionary is used, the keys must be timezone
            aware.
        outdoor_temperature : dict[datetime.datetime, float] | float | int
            The outdoor temperature as a single value or time series.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing the validated source and outdoor
            temperatures.
        """
        if type(source_temperature) is not type(outdoor_temperature):
            raise ValueError(
                "source_temperature and outdoor_temperature must be of the "
                "same type."
            )
        if isinstance(source_temperature, (float, int)):
            return pd.DataFrame(
                {
                    "source_temperature": source_temperature,
                    "outdoor_temperature": outdoor_temperature,
                },
                index=[0],
            )

        # Both will be a dict at this point
        if len(source_temperature) != len(outdoor_temperature):
            raise ValueError(
                "source_temperature and outdoor_temperature must be of the "
                "same type."
            )
        return pd.DataFrame(
            {
                "source_temperature": source_temperature,
                "outdoor_temperature": outdoor_temperature,
            }
        )

    def _initialize_hpl_heat_pump(self):
        """
        Initialize the hplib heat pump model.

        Initializes the hplib heat pump model based on the provided heat pump
        configuration. If the heat pump type is "Generic", it uses the
        specified parameters; otherwise, it retrieves the parameters from the
        hplib database.
        """
        if self.heat_pump.type == "Generic":
            parameters = hpl.get_parameters(
                model=self.heat_pump.type,
                group_id=self.heat_pump.id,
                t_in=self.heat_pump.t_in,
                t_out=self.heat_pump.t_out,
                p_th=self.heat_pump.p_th / 1000,
            )
            self.hpl_heat_pump = hpl.HeatPump(parameters)
        else:
            parameters = hpl.get_parameters(model=self.heat_pump.type)
            self.hpl_heat_pump = hpl.HeatPump(parameters)

    def get_cop_low_temp(
        self,
        source_temperature: dict[datetime.datetime, float] | float | int,
        outdoor_temperature: dict[datetime.datetime, float] | float | int,
    ) -> dict[datetime.datetime, float]:
        """
        Simulate the CoP for low temperature scenarios.

        Simulate the cop values for the heat pump when it has to reach the
        flow temperature. The source temperature and outdoor temperature can
        be a single float value or a dictionary with datetime keys and float
        values (time series).
        Both inputs must be of the same type.

        Parameters
        ----------
        source_temperature : dict[datetime.datetime, float] | float | int
            The temperature in Celsius of the heat source (e.g. air or water).
            This can be a single value or a dictionary with datetime keys and
            float values. When a dictionary is used, the keys must be timezone
            aware.
        outdoor_temperature : dict[datetime.datetime, float] | float | int
            The outdoor temperature [C] as a single value or time series.

        Returns
        -------
        dict[datetime.datetime, float]
            A dictionary with datetime keys and float values representing
            the CoP for low temperature scenarios.
        """
        temperatures = self._validate_source_and_outdoor_temp(
            source_temperature, outdoor_temperature
        )
        cop = {
            time: self.hpl_heat_pump.simulate(
                t_in_primary=temperature["source_temperature"],
                t_in_secondary=self.heat_pump.flow_temperature - 5,
                t_amb=temperature["outdoor_temperature"],
                mode=1,
            )["COP"]
            for time, temperature in temperatures.iterrows()
        }
        if isinstance(source_temperature, (float, int)):
            return cop[0]
        return cop

    def get_cop_high_temp(
        self,
        source_temperature: dict[datetime.datetime, float] | float | int,
        outdoor_temperature: dict[datetime.datetime, float] | float | int,
    ) -> dict[datetime.datetime, float]:
        """
        Simulate the CoP for high temperature scenarios.

        Simulate the cop values for the heat pump when it has to reach its
        maximum output temperature. The source temperature and outdoor
        temperature can be a single float value or a dictionary with datetime
        keys and float values (time series).
        Both inputs must be of the same type.

        Parameters
        ----------
        source_temperature : dict[datetime.datetime, float] | float | int
            The temperature in Celsius of the heat source (e.g. air or water).
            This can be a single value or a dictionary with datetime keys and
            float values. When a dictionary is used, the keys must be timezone
            aware.
        outdoor_temperature : dict[datetime.datetime, float] | float | int
            The outdoor temperature [C] as a single value or time series.

        Returns
        -------
        dict[datetime.datetime, float]
            A dictionary with datetime keys and float values representing
            the CoP for high temperature scenarios.
        """
        temperatures = self._validate_source_and_outdoor_temp(
            source_temperature, outdoor_temperature
        )
        cop = {
            time: self.hpl_heat_pump.simulate(
                t_in_primary=temperature["source_temperature"],
                t_in_secondary=self.heat_pump.output_temperature - 5,
                t_amb=temperature["outdoor_temperature"],
                mode=1,
            )["COP"]
            for time, temperature in temperatures.iterrows()
        }
        if isinstance(source_temperature, (float, int)):
            return cop[0]
        return cop

    def get_cop_values(
        self,
        source_temperature: dict[datetime.datetime, float] | float | int,
        outdoor_temperature: dict[datetime.datetime, float] | float | int,
    ) -> tuple[dict[datetime.datetime, float], dict[datetime.datetime, float]]:
        """
        Simulate low and high temperature CoP values.

        Simulate the cop values for both low and high temperature scenarios.
        The source temperature and outdoor temperature can be a single float
        value or a dictionary with datetime keys and float values (time
        series).
        Both inputs must be of the same type.

        Parameters
        ----------
        source_temperature : dict[datetime.datetime, float] | float | int
            The temperature in Celsius of the heat source (e.g. air or water).
            This can be a single value or a dictionary with datetime keys and
            float values. When a dictionary is used, the keys must be timezone
            aware.
        outdoor_temperature : dict[datetime.datetime, float] | float | int
            The outdoor temperature [C] as a single value or time series.

        Returns
        -------
        tuple[dict[datetime.datetime, float], dict[datetime.datetime, float]]
            A tuple containing two dictionaries with datetime keys and float
            values representing the CoP for low and high temperature scenarios.
        """
        return (
            self.get_cop_low_temp(source_temperature, outdoor_temperature),
            self.get_cop_high_temp(source_temperature, outdoor_temperature),
        )


def _validate_distinct_item(item: Any, group: Iterable[Any]) -> None:
    """
    Check if the item is in group.

    Checks if item is in group and raises a ValueError if not.

    Parameters
    ----------
    item : Any
        The item that should be checked against the list.
    group : List[Any]
        The list the item is checked against.

    Raises
    ------
    ValueError
        If the value is not in the list.
    """
    assert item in group, f"{item} is not allowed. Allowed values: {group}"
