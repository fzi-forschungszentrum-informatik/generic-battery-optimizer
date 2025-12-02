"""
Defines a battery model for domestic/car batteries.

This model combines all relevant parameters for battery operation
in a single data structure.
"""

from datetime import datetime
from typing import Optional
import secrets
import logging
from pydantic import BaseModel, Field
from battery_optimizer.static.numbers import SECRET_LENGTH

log = logging.getLogger(__name__)


class Battery(BaseModel):
    """
    Stores all information about a domestic/car battery.

    Power and energy are assumed to be specified in W and Wh respectively.
    """

    # The batteries name used in the model. This must be unique and is
    # generated automatically
    name: str = Field(
        default=secrets.token_hex(SECRET_LENGTH),
        description=(
            "The name of the battery to reference it in the model. If not "
            "supplied it will be populated by a random alphanumerical string."
        ),
    )
    # SoCs
    start_soc: float = Field(
        ge=0,
        le=1,
        title="Initial State of Charge",
        description="The initial SoC of the battery in percent (0-1).",
    )
    end_soc: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        title="SoC at end of optimization period",
        description=(
            "The SoC in percent (0-1) that shall be reached by the time "
            "end_soc_time is reached. After end_soc_time the battery is not "
            "allowed to be discharged below end_soc. This value is optional."
        ),
    )

    # Charge end time
    end_soc_time: Optional[datetime] = Field(
        default=None,
        title="End time for reaching end_soc",
        description=(
            "The datetime that specifies the time when end_soc should be "
            "reached. This is optional but if it is supplied end_soc must be "
            "supplied too."
        ),
    )

    # Charge start time
    start_soc_time: Optional[datetime] = Field(
        default=None,
        description=(
            "The datetime that specifies the time after which the battery is"
            "available for charging/discharging."
        ),
    )

    capacity: float = Field(
        gt=0,
        title="Capacity (Energy)",
        description="The capacity of the battery in Wh.",
    )

    max_charge_power: float = Field(
        ge=0,
        title="Max. charge power",
        description="The maximum power the battery can be charged with in W.",
    )
    # Max. discharge power (0 if unidirectional charging)
    max_discharge_power: float = Field(
        ge=0,
        default=0,
        title="The maximum discharge power of the battery",
        description=(
            "The maximum power the battery can be discharged with in W."
            "This is optional. If it isn't supplied discharging the battery is"
            "not allowed."
        ),
    )

    # Minimum charge power if the battery is charging
    min_charge_power: float = Field(ge=0, default=0)

    # Minimum discharge power if the battery is discharging
    min_discharge_power: float = Field(ge=0, default=0)

    # Wirkungsgrad Laden
    charge_efficiency: float = Field(
        ge=0,
        le=1,
        default=1,
        title="The efficiency of battery charging",
        description="Efficiency of the charging process in percent.",
    )

    # Wirkungsgrad Entladen
    discharge_efficiency: float = Field(
        ge=0,
        le=1,
        default=1,
        title="Efficiency of battery discharging",
        description="Efficiency of the discharge process in percent.",
    )

    # Minimum/Maximum SoC at any time
    min_soc: Optional[float] = Field(
        ge=0,
        le=1,
        default=0,
        title="Minimum State of Charge to not discharge below",
        description=(
            "Constraint the usable SoC range of the battery."
            "Value is given in percent. This value is optional."
        ),
    )
    max_soc: Optional[float] = Field(
        ge=0,
        le=1,
        default=1,
        title="Maximum State of Charge to charge to",
        description=(
            "Constraint the usable SoC range of the battery."
            "Value is given in percent. This value is optional."
        ),
    )
