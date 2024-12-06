import datetime
import secrets
from typing import ClassVar, List, Optional
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
    window: list[float] = two_item_list
    roof: list[float] = two_item_list
    wand: list[float] = two_item_list


class HeatPump(BaseModel):
    # The heatpump's name used in the model. This must be unique and
    # is generated automatically if not supplied. A uniqueness check is
    # not performed.
    name: str = secrets.token_hex(SECRET_LENGTH)

    """ Required Data for hpl """
    # Can be ["Air/Air", "Luft/Luft", "Generic",
    # "All other hpl heat pump types available"]
    type: str

    @field_validator("type")
    def validate_type(cls, v):
        allowed_types = list(heat_pump_data["Type"].unique())
        allowed_types.extend(list(heat_pump_data["Model"].unique()))
        allowed_types.extend(["Air/Air", "Luft/Luft", "Generic"])
        _validate_distinct_item(v, allowed_types)
        return v

    """Start of hpl specific data"""
    id: Optional[int] = None  # hpl uses it to return the correct model

    @field_validator("id")
    def validate_id(cls, v):
        if v is None:
            return v
        _validate_distinct_item(v, heat_pump_data["Group"].unique())
        return v

    # These values are only needed/allowed when the type is Generic
    t_in: Optional[float] = None
    t_out: Optional[float] = None
    p_th: Optional[float] = None

    @field_validator("t_in", "t_out", "p_th")
    def validate_generic_hp(cls, v):
        if v is not None and v < 200:
            raise ValueError("All temperatures must be in Kelvin")
        return v

    @model_validator(mode="after")
    def validate_generic_hp_value_existance(cls, values):
        if values.type == "Generic":
            if not all([values.id, values.t_in, values.t_out, values.p_th]):
                raise ValueError(
                    "All Generic heat pump values must be provided"
                )
        return values

    """End of hpl specific data"""

    # hpl does not implement Air/Air heat pumps. This value will be used
    # instead and must be provided when the type is Air/Air
    cop_air: Optional[str] = None

    @field_validator("cop_air")
    def validate_cop_air(cls, v):
        assert cls.type in [
            "Air/Air",
            "Luft/Luft",
        ], 'This value is only allowed when an "Air/Air"-Heatpump is used'
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

    u_values_building: _U_Values_Building
    surface_building: float

    temp_supply_demand: float
    temp_room: float
    temp_hp_out: Optional[float]
    bivalent_temp: Optional[float]

    max_temp_hp: float
    min_electric_consumption_hp: ClassVar[float] = 0.0
    max_electric_consumption_hp: float
    mind_electric_consumption_hp: float
    min_heat_supply_hp: ClassVar[float] = 0.0

    min_electric_consumption_hr: ClassVar[float] = 0.0
    max_electric_consumption_hr: float
    mind_electric_consumption_hr: float

    tank_u_value: ClassVar[float] = 0.6
    tank_mass: float
    tes_start_value: float
    tank_rest: float
    tank_rest_hours: list  # use ufunc.convert_list(BLOCKING_HOURS, TIME_RESOLUTION) to convert

    max_temp_tes: float
    charge_tes_off: float
    min_heat_energy_tes: ClassVar[float] = 0.0

    @field_validator(
        "temp_supply_demand",
        "temp_room",
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

    # TODO The index must be the same as the rest of the model
    # It would probably be better to just use a list and make sure it has the
    # same length as the index.
    # If we leave it like this, we must merge all the indexes into one
    outdoor_temperature: dict[datetime.datetime, float]
    heat_source_temperature: dict[datetime.datetime, float]

    @field_validator("outdoor_temperature", "heat_source_temperature")
    def validate_outdoor_temperature(cls, v):
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
                (self.max_temp_tes - self.temp_supply_demand)
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
            * (self.max_temp_tes - self.temp_supply_demand)
            / (1000 * 3600)
        )

    @computed_field
    @property
    def cp(self) -> float:
        return 4186 / 1000

    @computed_field
    @property
    def mind_heat_supply_hp(self) -> float:
        return (
            (
                self.tank_mass
                * ((self.max_temp_tes - self.temp_supply_demand) * 0.1)
                * 4.186
            )
        ) / 3600

    # These times are given in time ranges in which the heat pump must
    # statisy specific criteria
    # They must be added to the index list and in these ranges the
    # necessary constraints are added
