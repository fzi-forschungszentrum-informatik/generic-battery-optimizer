import datetime
import secrets
from typing import List, Optional
import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from battery_optimizer.static.heat_pump import MINIMUM_KELVIN
from battery_optimizer.static.numbers import SECRET_LENGTH
import hplib.hplib as hpl
from battery_optimizer.helpers.heat_pump_profile import (
    tank_dimensions,
)

heat_pump_data = hpl.load_database()
two_item_list = Field(
    default_factory=lambda: [0.0, 0.0], min_length=2, max_length=2
)


def _validate_distinct_item(item, group):
    """Checks if the item is in group

    -----
    Input
    item: any
        the item that should be checked against the list
    group: List[any]
        the list the item is checked against

    ------
    Raises
    ValueError
        If the value is not in the list"""
    assert item in group, f"{item} is not allowed. Allowed values: {group}"


class _U_Values_Building(BaseModel):
    """Building U-Values for the heat pump model

    The U-Values are used to calculate the heat demand of the building.
    The first number in each list is the surface area of the building's
    component in m². The second number is the U-Value in W/m²K.
    """
    model_config = ConfigDict(extra="forbid")
    wall: list[float] = two_item_list
    roof: list[float] = two_item_list
    window: list[float] = two_item_list


class HeatPump(BaseModel):
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

    """ Required Data for hplib """
    type: str = Field(
        title="hplib heat pump type",
        description=(
            "Heat pump model type for the heat pump simulation. The heat pump "
            "simulation uses [hplib](https://github.com/FZJ-IEK3-VSA/hplib) "
            "to estimate heat pump behavior. Many commercial heat pumps can "
            "be simulated or custom heat pumps can be specified. hplib "
            "supports Air/Water, Water/Water and Brine/Water heat pumps. "
            "Air/Air heat pumps are not supported by hplib and can only be "
            "modeled with a constant CoP (see cop_air field)."
            'Can be ["Air/Air", "Luft/Luft", "Generic"'
            '"All other [hplib](https://github.com/FZJ-IEK3-VSA/hplib) heat '
            'pump types available"]'
        ),
        examples=["AE050RXYDEG/EU & AE200RNWMEG/EU", "Air/Air", "Generic"],
    )

    @field_validator("type")
    def validate_type(cls, v):
        allowed_types = list(heat_pump_data["Type"].unique())
        if "Titel" in heat_pump_data.columns:
            allowed_types.extend(list(heat_pump_data["Titel"].unique()))
        allowed_types.extend(list(heat_pump_data["Model"].unique()))
        allowed_types.extend(["Air/Air", "Luft/Luft", "Generic"])
        _validate_distinct_item(v, allowed_types)
        return v

    """Start of hplib specific data"""
    id: Optional[int] = Field(
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

    @field_validator("id")
    def validate_id(cls, v):
        if v is None:
            return v
        _validate_distinct_item(v, heat_pump_data["Group"].unique())
        return v

    # These values are only needed/allowed when the type is Generic
    t_in: Optional[float] = Field(
        default=None,
        title="hplib heat pump temperature cool side (outdoors) [K]",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Temperature in K on the low temperature side of the heat pump. "
            "Usually the outside atmosphere."
        ),
        ge=MINIMUM_KELVIN,
    )
    t_out: Optional[float] = Field(
        default=None,
        title="hplib heat pump temperature hot side (indoors) [K]",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Temperature in K on the warm temperature side of the heat pump. "
            "Usually the heat water output of the heat pump."
        ),
        ge=MINIMUM_KELVIN,
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
    def validate_generic_hp_value_existence(cls, values):
        if values.type == "Generic":
            if not all([values.id, values.t_in, values.t_out, values.p_th]):
                raise ValueError(
                    "All Generic heat pump values must be provided"
                )
        return values

    """End of hplib specific data"""
    cop_air: Optional[float] = Field(
        default=None,
        title="CoP for Air/Air heat pump",
        description=(
            "hplib does not implement Air/Air heat pumps. "
            "This value will be used instead and must be provided when the "
            "type is Air/Air"
        ),
        examples=[1.0, 2.3, 3.1],
    )

    @field_validator("cop_air")
    def validate_cop_air(cls, v):
        assert cls.type in [
            "Air/Air",
            "Luft/Luft",
        ], 'This value is only allowed when an "Air/Air"-Heat pump is used'
        return v

    u_values_building: Optional[_U_Values_Building] = Field(
        title="Building U-Values",
        description=(
            "Needed when no heat demand is provided. "
            "Building area and U-Values used to calculate the heat demand of "
            "the building. The first number in each list is the surface area "
            "of the building's component in m². The second number is the "
            "U-Value in W/m²K."
        ),
        default=None,
        examples=[
            {
                "wall": [159.4, 0.8],
                "roof": [100.8, 0.5],
                "window": [27, 1.3],
            }
        ],
    )

    living_area: float = Field(
        title="Living area [m²]",
        description=(
            "Needed when no heat demand is provided. "
            "The living area in m² of the building."
        ),
        default=None,
        examples=[100.0, 150.0, 200.0],
    )

    @model_validator(mode="after")
    def energy_estimation_or_heat_demand(cls, values):
        if not (
            (values.u_values_building and values.living_area)
            or values.heat_demand
        ):
            raise ValueError(
                "Either u_values_building and living_area or heat_demand must "
                "be provided"
            )
        return values

    # End of values for estimating the heat demand of the building

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
    def validate_electric_power(cls, values):
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
            "The maximum temperature of the thermal energy storage in Kelvin."
        ),
        ge=MINIMUM_KELVIN,
    )

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

    outdoor_temperature: float | dict[datetime.datetime, float] = Field(
        title="Outdoor temperature [K]",
        description=(
            "The outdoor temperature in Kelvin. This can be a single value "
            "or a dictionary with datetime keys and float values. "
            "When a dictionary is used, the keys must be timezone aware. "
            "When the keys do not match a period start in the model, the "
            "temperature is linearly interpolated between the two closest "
            "values."
        ),
    )
    heat_source_temperature: float | dict[datetime.datetime, float] = Field(
        title="Heat source temperature [K]",
        description=(
            "The temperature in Kelvin of the heat source "
            "(e.g. air or water). This can be a single value "
            "or a dictionary with datetime keys and float values. "
            "When a dictionary is used, the keys must be timezone aware. "
            "When the keys do not match a period start in the model, the "
            "temperature is linearly interpolated between the two closest "
            "values."
        ),
    )

    heat_demand: Optional[dict[datetime.datetime, float]] = Field(
        default=None,
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

    @field_validator(
        "outdoor_temperature", "heat_source_temperature", "temp_room"
    )
    def validate_temperature_lists(cls, v):
        if v is None:
            return v
        # Just a float value
        if isinstance(v, float):
            if v < 200:
                raise ValueError("All temperatures must be in Kelvin")
            return v
        # A dictionary with datetime keys and float values
        else:
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
        return 10 * self.max_electric_power_hp

    @computed_field
    @property
    def tank_height(self) -> float:
        return tank_dimensions((self.tank_volume / 1000))[1]

    @computed_field
    @property
    def tank_radius(self) -> float:
        return tank_dimensions((self.tank_volume / 1000))[0]

    # The maximum energy that can be stored in the TES
    @computed_field
    @property
    def max_heat_energy_tes(self) -> float:
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
        return (
            self.tank_volume
            * 4186
            * (self.max_temp_tes - self.flow_temperature)
            / (1000 * 3600)
        )
