"""
Extends the battery model with extras specific to EVs.

EVs extend the basic battery model with additional parameters
like charge start and end times as well as minimum charge and discharge
powers.
"""

import datetime
from pydantic import Field, model_validator
from battery_optimizer.profiles.battery import NewBattery as Battery


class EV(Battery):
    """
    Stores all information about an electric vehicle battery.

    Power and energy are assumed to be specified in W and Wh respectively.
    """
    end_soc: float = Field(
        ge=0,
        le=1,
        title="SoC at end of optimization period",
        description=(
            "The SoC in percent (0-1) that shall be reached by the time "
            "end_soc_time is reached. After end_soc_time the battery is not "
            "allowed to be discharged below end_soc. This value is optional."
        ),
    )

    @model_validator(mode="after")
    def check_end_soc(self) -> "EV":
        """
        Validate that end_soc is within min_soc and max_soc.

        end_soc must be between min_soc and max_soc. If it would be outside
        this range the model would become infeasible.

        Returns
        -------
        EV
            The validated EV instance.

        Raises
        ------
        ValueError
            If end_soc is outside the min_soc and max_soc range.
        """
        if self.end_soc < self.min_soc or self.end_soc > self.max_soc:
            raise ValueError(
                f"end_soc ({self.end_soc}) is outside the range of "
                f"min_soc ({self.min_soc}) and max_soc ({self.max_soc})."
            )
        return self

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
    min_charge_power: float = Field(
        ge=0,
        default=0,
        title="Minimum charge power",
        description=(
            "The minimum power at which the battery charges when it is "
            "charging. Value is given in W."
        ),
    )

    # Minimum discharge power if the battery is discharging
    min_discharge_power: float = Field(
        ge=0,
        default=0,
        title="Minimum discharge power",
        description=(
            "The minimum power at which the battery discharges when it is "
            "discharging. Value is given in W."
        ),
    )

    charging_is_interruptable: bool = Field(
        default=True,
        title="Is charging interruptable",
        description=(
            "Specifies whether the charging process can be interrupted. If "
            "set to False the battery must charge at min_charge_power from "
            "the start time until the charging is finished."
        ),
    )
