"""
A model representing a heat pump system with its parameters and constraints.

Stores parameters needed to model a heat pump system for optimization
"""

import datetime
import secrets
from typing import Annotated, Optional, Self
import pandas as pd
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from battery_optimizer.static.heat_pump import MINIMUM_KELVIN
from battery_optimizer.static.numbers import SECRET_LENGTH
from battery_optimizer.helpers.heat_pump_profile import (
    tank_dimensions,
)


class HeatPump(BaseModel):
    """
    A model representing a heat pump system.

    Stores various parameters needed to model a heat pump system for
    optimization. Some of the parameters can be provided as single values or
    as dictionaries with datetime keys for time-varying inputs.
    Some parameters can be pre-computed with the helper functions provided in
    battery_optimizer.helpers.hplib.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default=secrets.token_hex(SECRET_LENGTH),
        title="Heat pump name",
        description=(
            "The heat pump's name used in the model. This must be unique and "
            "is generated automatically if not supplied. A uniqueness check is"
            "not performed."
        ),
    )

    cop_high_temp: float | dict[datetime.datetime, float] = Field(
        title="The CoP of the heat pump at the maximum output temperature.",
        description=(
            "The coefficient of performance (CoP) of the heat pump when the "
            "heat pump has to reach high output temperatures to supply the "
            "thermal energy storage. The specified CoP should be valid for "
            "heat pump when it has to heat the water to the maximum output "
            "temperature of the heat pump."
        ),
        examples=[1.0, 2.3, 3.1],
    )
    cop_low_temp: float | dict[datetime.datetime, float] = Field(
        title="CoP at flow temperature",
        description=(
            "The coefficient of performance (CoP) of the heat pump when the "
            "heat pump has to reach flow temperature output temperature to "
            "supply building directly. The specified CoP should be valid "
            "for heat pump when it has to heat the water to the flow "
            "temperature of the heating system. This CoP should generally be "
            "phigher than the cop_high_temp."
        ),
        examples=[3.0, 4.3, 5.1],
    )

    # TODO use C instead of K for all temperatures
    flow_temperature: float = Field(
        title="Flow temperature [K]",
        description=(
            "The flow temperature of the heating circuit in Kelvin. "
            "This is the temperature of the water as it leaves the heat "
            "pump/temperature energy storage and enters the heating system, "
            "such as radiators or underfloor heating."
        ),
        ge=MINIMUM_KELVIN,
        examples=[303.15, 308.15, 313.15, 318.15],
    )
    temp_room: float | dict[datetime.datetime, float] = Field(
        default=293.15,
        title="Room temperature [K]",
        description=(
            "The desired room temperature heated by the heating system in "
            "Kelvin. "
            "This can be a single value or a dictionary with datetime keys "
            "and float values. When a dictionary is used, the keys must be "
            "timezone aware. When the keys do not match a period start in the "
            "model, the temperature is linearly interpolated between the two "
            "closest values."
        ),
    )

    hp_switch_off_temperature: Optional[float] = Field(
        default=None,
        title="Outdoor temperature switch off [K]",
        description=(
            "The outdoor temperature in Kelvin at which the heat pump is "
            "switched off. If not provided, the heat pump can always run."
        ),
        ge=MINIMUM_KELVIN,
        examples=[268.15, 263.15, 258.15],
    )
    bivalent_temp: Optional[float] = Field(
        default=None,
        title="Bivalent temperature [K]",
        description=(
            "The outdoor temperature in Kelvin below which the heat pump only "
            "provides 70% of the building heat demand. The remaining 30% are "
            "provided by a backup heater."
        ),
        ge=MINIMUM_KELVIN,
    )

    output_temperature: float = Field(
        title="Heat pump output temperature [K]",
        description=(
            "The high side output temperature of the heat pump in Kelvin. "
            "This is the maximum temperature the heat pump can provide. "
            "Charging the TES above this temperature must be done by the "
            "backup heater."
        ),
        ge=MINIMUM_KELVIN,
    )

    min_electric_power_hp: Optional[float] = Field(
        default=0.0,
        title="Minimum electric consumption heat pump [kW]",
        description=(
            "The minimum electric consumption of the heat pump in kW. "
            "The heat pump can either be switched off or - if it is switched "
            "on - it needs to use at least this much power."
        ),
    )
    max_electric_power_hp: float = Field(
        title="Maximum electric consumption heat pump [kW]",
        description=(
            "The maximum electric consumption of the heat pump in kW. "
        ),
    )

    min_electric_power_hr: Optional[float] = Field(
        default=0.0,
        title="Minimum electric consumption backup heater [kW]",
        description=(
            "The minimum electric consumption of the backup heater in kW. "
            "The backup heater can either be switched off or - if it is "
            "switched on - it needs to use at least this much power."
        ),
    )
    max_electric_power_hr: float = Field(
        title="Maximum electric consumption backup heater [kW]",
        description=(
            "The maximum electric consumption of the backup heater in kW. "
        ),
    )

    @model_validator(mode="after")
    def validate_electric_power(cls, values: "HeatPump") -> "HeatPump":
        """
        Validate electric power values.

        Validate that the minimum electric power for both the heat pump and
        the electric heater are less than or equal to their respective maximum
        electric power values.

        Parameters
        ----------
        values : HeatPump
            The instance of the HeatPump model after initial validation.

        Returns
        -------
        HeatPump
            The validated HeatPump instance.

        Raises
        ------
        ValueError
            If minimum electric power is greater than maximum for either device.
        """
        if values.min_electric_power_hp > values.max_electric_power_hp:
            raise ValueError(
                "Minimum electric power for heat pump must be less than or "
                "equal to maximum electric power for heat pump"
            )
        if values.min_electric_power_hr > values.max_electric_power_hr:
            raise ValueError(
                "Minimum electric power for backup heater must be less than "
                "or equal to maximum electric power for backup heater"
            )
        return values

    max_temp_tes: float = Field(
        default=363.15,
        title="Maximum temperature of the TES [K]",
        description=(
            "The maximum temperature of the thermal energy storage in Kelvin. "
            "This is required for the soc calculation of the thermal energy "
            "storage (TES). The TES cannot be charged above this temperature."
        ),
        ge=MINIMUM_KELVIN,
    )

    # TODO All tank information should be a separate model that can be added
    # to the heat pump model to enable tank loss prediction. Probably
    # specifying just the heat loss in W/K(^2) would be sufficient.
    predict_tank_loss: Optional[bool] = Field(
        default=True,
        title="Predict tank heat losses",
        description=(
            "If enabled, the heat losses of the tank are predicted based on "
            "its dimensions. If disabled, the heat losses of the tank are not "
            "being considered in the model."
        ),
    )
    tank_u_value: Optional[float] = Field(
        default=0.6,
        title="U-Value of the tank",
        description=(
            "The U-Value of the tank in W/m²K. This is used to calculate the "
            "heat losses of the tank. "
            "If predict_tank_loss is disabled, this value is not used."
        ),
        examples=[0.3, 0.5, 0.7],
    )

    # TODO specify surface area and provide methods to calculate surface area
    # from volume and height/radius
    tank_volume: float = Field(
        title="Mass of the TES [l]",
        description="The volume of the thermal energy storage in litres.",
        examples=[200, 250, 300, 500],
    )
    tes_start_soc: Optional[float] = Field(
        default=0.0,
        title="Initial SoC of the TES",
        ge=0,
        le=1,
        examples=[0.0, 0.5, 1.0],
    )

    outdoor_temperature: Optional[float | dict[datetime.datetime, float]] = (
        Field(
            default=None,
            title="Outdoor temperature [K]",
            description=(
                "The outdoor temperature in Kelvin. This can be a single "
                "value or a dictionary with datetime keys and float values. "
                "When a dictionary is used, the keys must be timezone aware. "
                "When the keys do not match a period start in the model, the "
                "temperature is linearly interpolated between the two closest "
                "values."
            ),
        )
    )

    @model_validator(mode="after")
    def enforce_outdoor_temperature(self) -> Self:
        """
        Ensure outdoor temperature is set when needed.

        Ensure that outdoor_temperature is provided if either
        hp_switch_off_temperature or bivalent_temp is set, as these
        parameters depend on outdoor temperature to correctly control
        the operation of the heat pump in low temperature conditions.

        Returns
        -------
        Self
            The validated HeatPump instance.
        """
        if (
            self.hp_switch_off_temperature or self.bivalent_temp
        ) and self.outdoor_temperature is None:
            raise ValueError(
                "outdoor_temperature must be provided if either "
                "hp_switch_off_temperature or bivalent_temp is set."
            )
        return self

    heat_demand: dict[datetime.datetime, float] = Field(
        title="Heat demand of the building [kW]",
        description=(
            "An optional heat demand of the building in kW. "
            "Heat demand is assumed to be constant during each period. "
            "The heat demand is not interpolated if the keys from this heat "
            "demand do not match the optimization time steps."
            "Use df.to_dict() to convert a pandas dataframe to a suitable "
            "pydantic dictionary."
        ),
    )

    warm_water_demand: Optional[dict[datetime.datetime, float]] = Field(
        default=None,
        title="Warm water demand [kW]",
        description=(
            "An optional warm water demand in kW. "
            "Warm water demand is assumed to be constant during each period. "
            "Use df.to_dict() to convert a pandas dataframe to a suitable "
            "pydantic dictionary."
        ),
    )

    @field_validator("outdoor_temperature", "temp_room")
    def validate_temperature_lists(
        cls, v: float | dict[datetime.datetime, float] | None
    ) -> float | pd.Series | None:
        """
        Validate temperature inputs.

        This validator checks if the temperature input is either a float,
        None, or a dictionary with datetime keys and float values. It ensures
        that all datetime keys are timezone aware and that all temperature
        values are in Kelvin (greater than 200K).

        Parameters
        ----------
        v : float | dict[datetime.datetime, float] | None
            The temperature input to validate.

        Returns
        -------
        float | pd.Series | None
            Returns the input as is if it's None or a float. If it's a
            dictionary, it converts it to a pandas Series for easier handling
            later in the model.

        Raises
        ------
        ValueError
            If the input is not None, a float, or a valid dictionary with
            timezone-aware datetime keys and Kelvin temperature values.
        """
        if v is None:
            return v
        # Just a float value
        if isinstance(v, float):
            if v < 200:
                raise ValueError("All temperatures must be in Kelvin")
            return v
        # A dictionary with datetime keys and float values
        if not all(
            isinstance(dt, datetime.datetime) and dt.tzinfo is not None
            for dt in v.keys()
        ):
            raise ValueError("All datetime keys must be timezone aware")
        # Values should be in Kelvin
        if any(temp < 200 for temp in v.values()):
            raise ValueError("All temperatures must be in Kelvin")
        return pd.Series(v)

    enforce_end_soc: Optional[bool] = Field(
        default=False,
        title="Enforce end SoC to be equal to start SoC",
        description=(
            "If enabled, the SoC of the TES at the end of the optimization "
            "period is enforced to be equal to the SoC at the beginning of "
            "the optimization period."
            "If disabled the optimizer will naturally use the 'free' energy "
            "in the TES and the SoC at the end of the optimization period "
            "will be 0."
        ),
    )

    # Computed fields
    @computed_field
    @property
    def max_heat_supply_hp(self) -> float:
        """
        The maximum heat that can be supplied by the heat pump in kW.

        Calculate the maximum heat that can be supplied by the heat pump in kW
        for use as an upper bound in the optimization model.

        Returns
        -------
        float
            The maximum heat that can be supplied by the heat pump in kW.
        """
        return 10 * self.max_electric_power_hp

    @computed_field
    @property
    def tank_height(self) -> float:
        """
        The estimated height of the TES in meters.

        Calculate the estimated height of the TES in meters based on its
        volume for use in the tank loss calculation.

        Returns
        -------
        float
            The estimated height of the TES in meters.
        """
        return tank_dimensions((self.tank_volume / 1000))[1]

    @computed_field
    @property
    def tank_radius(self) -> float:
        """
        The estimated radius of the TES in meters.

        Calculate the estimated radius of the TES in meters based on its
        volume for use in the tank loss calculation.

        Returns
        -------
        float
            The estimated radius of the TES in meters.
        """
        return tank_dimensions((self.tank_volume / 1000))[0]

    # The maximum energy that can be stored in the TES
    @computed_field
    @property
    def max_heat_energy_tes(self) -> float:
        """
        The maximum heat energy that can be stored in the TES in kWh.

        Calculate the maximum heat energy that can be stored in the TES in kWh
        for use as bounds in the soc calculation of the TES.

        Returns
        -------
        float
            The maximum heat energy that can be stored in the TES in kWh.
        """
        return (
            (
                (self.max_temp_tes - self.flow_temperature)
                * self.tank_volume
                * 4186  # Heat capacity of water in kWh/kgK
            )
            / 3600
        ) / 1000

    @computed_field
    @property
    def max_heat_supply_tes(self) -> float:
        """
        The maximum heat that can be supplied by the TES in kW.

        Calculate the maximum heat that can be supplied by the TES in kW for
        use as an upper bound in the optimization model.

        Returns
        -------
        float
            The maximum heat that can be supplied by the TES in kW.
        """
        return (
            self.tank_volume
            * 4186
            * (self.max_temp_tes - self.flow_temperature)
            / (1000 * 3600)
        )
