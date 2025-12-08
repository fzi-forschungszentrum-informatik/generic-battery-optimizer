"""
Extends the battery model with extras specific to EVs.

EVs extend the basic battery model with additional parameters
like charge start and end times as well as minimum charge and discharge
powers.
"""

import datetime
from typing import Optional
from pydantic import Field
from battery_optimizer.profiles.battery import NewBattery as Battery


class EV(Battery):
    """
    Stores all information about an electric vehicle battery.

    Power and energy are assumed to be specified in W and Wh respectively.
    """

    # start_soc_time
    charge_start_time: datetime.datetime = Field(
        title="Start time for reaching charge_start",
        description=(
            "The datetime that specifies the time after which the battery is"
            "available for charging/discharging."
        ),
    )
    # end_soc_time
    charge_end_time: datetime.datetime = Field(
        title="End time for reaching end_soc",
        description=(
            "The datetime that specifies the time when end_soc should be "
            "reached. This is optional but if it is supplied end_soc must be "
            "supplied too."
        ),
    )

    # Minimum charge power if the battery is charging
    min_charge_power: Optional[float] = Field(
        ge=0,
        default=0,
        title="Minimum charge power",
        description=(
            "The minimum power at which the battery charges when it is "
            "charging. Value is given in W."
        ),
    )

    # Minimum discharge power if the battery is discharging
    min_discharge_power: Optional[float] = Field(
        ge=0,
        default=0,
        title="Minimum discharge power",
        description=(
            "The minimum power at which the battery discharges when it is "
            "discharging. Value is given in W."
        ),
    )
