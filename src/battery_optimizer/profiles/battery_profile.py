from pydantic import field_validator, BaseModel, Field
from battery_optimizer.static.numbers import SECRET_LENGTH
from datetime import datetime
from typing import Optional
from math import isnan
import secrets
import logging

log = logging.getLogger(__name__)


class Battery(BaseModel):
    """Stores all information about a domestic/car battery

    Power and energy are given in W and Wh respectively.

    Attributes
    ----------
    name: str
        The name of the battery to reference it in the model.
        If not supplied it will be populated by a random alphanumerical string
    start_soc: float
        The initial SoC of the battery in percent (0-1).
    end_soc: float
        The SoC in percent (0-1) that shall be reached by the time end_soc_time is
        reached.
        After end_soc_time the battery is not allowed to be discharged below
        end_soc.
        This value is optional.
    end_soc_time: datetime
        The datetime that specifies the time when end_soc should be reached.
        This is optional but if it is supplied end_soc must be supplied too.
    capacity: float
        The capacity of the battery in Wh
    max_charge_power: float
        The maximum power the battery can be charged with in W.
    max_discharge_power: float
        The maximum power the battery can be discharged with in W.
        This is optional. If it isn't supplied discharging the battery is not
        allowed.
    charge_efficiency: float
        Efficiency of the charging process in percent.
    discharge_efficiency: float
        Efficiency of the discharge process in percent.
    min_soc: float
        Constraint the usable SoC range of the battery.
        Value is given in percent.
        This value is optional.
    max_soc: float
        Constraint the usable SoC range of the battery.
        Value is given in percent.
        This value is optional.
    """

    # The batteries name used in the model. This must be unique and is
    # generated automatically
    name: str = secrets.token_hex(SECRET_LENGTH)
    # SoCs
    start_soc: float = Field(ge=0, le=1)
    end_soc: Optional[float] = Field(None, ge=0, le=1)

    # Charge end time
    end_soc_time: Optional[datetime] = None

    # Charge start time
    start_soc_time: Optional[datetime] = None

    # Capacity (Energie)
    capacity: float = Field(ge=0)

    # Max. charge power
    max_charge_power: float = Field(ge=0)
    # Max. discharge power (0 if unidirectional charging)
    max_discharge_power: float = Field(ge=0, default=0)

    # Minimum charge power if the battery is charging
    min_charge_power: Optional[float] = Field(ge=0, default=0)

    # Minimum discharge power if the battery is discharging
    min_discharge_power: Optional[float] = Field(ge=0, default=0)

    # Wirkungsgrad Laden
    charge_efficiency: float = Field(ge=0, le=1, default=1)

    # Validate that the discharge efficiency is not NaN
    @field_validator("discharge_efficiency")
    @classmethod
    def discharge_efficiency_not_nan(cls, v):
        if isnan(v):
            log.warning("Discharge efficiency is NaN. Setting to 1")
            return 1
        return v

    # Wirkungsgrad Entladen
    discharge_efficiency: float = Field(ge=0, le=1, default=1)

    # Validate that the discharge efficiency is not NaN
    @field_validator("charge_efficiency")
    @classmethod
    def charge_efficiency_not_nan(cls, v):
        if isnan(v):
            log.warning("Charge efficiency is NaN. Setting to 1")
            return 1
        return v

    # Minimum/Maximum SoC at any time
    min_soc: Optional[float] = Field(ge=0, le=1, default=0)
    max_soc: Optional[float] = Field(ge=0, le=1, default=1)
