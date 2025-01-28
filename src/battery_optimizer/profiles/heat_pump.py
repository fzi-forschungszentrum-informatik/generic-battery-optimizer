import datetime
import secrets
from typing import List, Optional
import pandas as pd
from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from battery_optimizer.static.numbers import SECRET_LENGTH
import hplib.hplib as hpl
from battery_optimizer.helpers.heat_pump_profile import (
    tank_dimensions,
)

heat_pump_data = hpl.load_all_heat_pumps()
two_item_list = Field(
    default_factory=lambda: [0.0, 0.0], min_items=2, max_items=2
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
    wall: list[float] = two_item_list
    roof: list[float] = two_item_list
    window: list[float] = two_item_list


class HeatPump(BaseModel):
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
        title="hplib heat pump temperature cool side (outdoors)",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Temperature in K on the low temperature side of the heat pump. "
            "Usually the outside atmosphere."
        ),
    )
    t_out: Optional[float] = Field(
        default=None,
        title="hplib heat pump temperature hot side (indoors)",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Temperature in K on the warm temperature side of the heat pump. "
            "Usually the heat water output of the heat pump."
        ),
    )
    p_th: Optional[float] = Field(
        default=None,
        title="hplib heat pump thermal output power",
        description=(
            'Only needed when hplib heat pump type is "Generic"!'
            "Thermal output power at setpoint t_in, t_out "
            "(and for water/water, brine/water heat pumps t_amb = -7°C). [W]"
        ),
    )

    @field_validator("t_in", "t_out")
    def validate_generic_hp(cls, v):
        if v is not None and v < 200:
            raise ValueError("All temperatures must be in Kelvin")
        return v

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

    # TODO check that the strings have the correct length
    # '2020-12-04 8:00:00+00:00 - 2020-12-04 15:00:00+00:00'
    # and that they are timezone aware. If not force timezone to be UTC
    blocking_hours: List[
        str
    ]  # Currently a list of time steps. They are checked against, use ufunc.convert_list(BLOCKING_HOURS, TIME_RESOLUTION) to convert
    limited_energy_hours: Optional[List[str]]
    # List with values that represent periods. Periods are '"Date" - "Date"'
    # (e.g. "2020-12-04 11:00:00 - 2020-12-04 15:00:00")
    # TODO add the start and end values to the model index
    warm_water_periods: List[
        str
    ]  # use ufunc.convert_list(BLOCKING_HOURS, TIME_RESOLUTION) to convert

    # Values for estimating the heat demand of the building
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
        example={
            "wall": [159.4, 0.8],
            "roof": [100.8, 0.5],
            "window": [27, 1.3],
        },
    )

    living_area: float = Field(
        title="Living area",
        description=(
            "Needed when no heat demand is provided. "
            "The living area in m² of the building."
        ),
        default=None,
        examples=[100.0, 150.0, 200.0],
    )

    @model_validator(mode="after")
    def energy_estimation_or_heat_demand(cls, values):
        if (
            not (values.u_values_building or values.living_area)
            and not values.heat_demand
        ):
            raise ValueError(
                "Either u_values_building and living_area or heat_demand must "
                "be provided"
            )
        return values

    # End of values for estimating the heat demand of the building

    flow_temperature: float = Field(
        title="Flow temperature",
        description=(
            "The flow temperature of the heating circuit in Kelvin. "
            "This is the temperature of the water as it leaves the heat "
            "pump/temperature energy storage and enters the heating system, "
            "such as radiators or underfloor heating."
        ),
        examples=[303.15, 308.15, 313.15, 318.15],
    )
    temp_room: float | dict[datetime.datetime, float] = Field(
        default=293.15,
        title="Room temperature",
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
    temp_hp_out: Optional[float]
    bivalent_temp: Optional[float]

    max_temp_hp: float
    min_electric_consumption_hp: Optional[float] = 0.0
    max_electric_consumption_hp: float

    min_electric_consumption_hr: Optional[float] = 0.0
    max_electric_consumption_hr: float

    tank_u_value: Optional[float] = 0.6
    tank_mass: float
    tes_start_value: float
    tank_rest: float
    tank_rest_hours: list  # use ufunc.convert_list(BLOCKING_HOURS, TIME_RESOLUTION) to convert
    predict_tank_loss: Optional[bool] = True

    max_temp_tes: float
    charge_tes_off: float

    @field_validator(
        "flow_temperature",
        "max_temp_hp",
        "max_temp_tes",
        "charge_tes_off",
        "temp_hp_out",
        "bivalent_temp",
    )
    def validate_temperatures(cls, v):
        if v is None:
            return v
        if v < 200:
            raise ValueError("All temperatures must be in Kelvin")
        return v

    outdoor_temperature: float | dict[datetime.datetime, float] = Field(
        title="Outdoor temperature",
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
        title="Heat source temperature",
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

    # An optional heat demand of the building. If not provided, the heat
    # demand is calculated from the u-values and the surface of the building
    # Use df.to_dict() to convert a pandas dataframe to suitable dictionary
    heat_demand: Optional[dict[datetime.datetime, float]] = None

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

    # Computed fields
    @computed_field
    @property
    def max_heat_supply_hp(self) -> float:
        return 10 * self.max_electric_consumption_hp

    @computed_field
    @property
    def tank_height(self) -> float:
        return tank_dimensions((self.tank_mass / 1000))[0]

    @computed_field
    @property
    def tank_radius_o(self) -> float:
        return tank_dimensions((self.tank_mass / 1000))[1]

    # The maximum energy that can be stored in the TES
    @computed_field
    @property
    def max_heat_energy_tes(self) -> float:
        return (
            (
                (self.max_temp_tes - self.flow_temperature)
                * self.tank_mass
                * 4186
            )
            / 3600
        ) / 1000

    @computed_field
    @property
    def max_heat_supply_tes(self) -> float:
        return (
            self.tank_mass
            * 4186
            * (self.max_temp_tes - self.flow_temperature)
            / (1000 * 3600)
        )

    @computed_field
    @property
    def cp(self) -> float:
        return 4186 / 1000

    # These times are given in time ranges in which the heat pump must
    # satisfy specific criteria
    # They must be added to the index list and in these ranges the
    # necessary constraints are added
