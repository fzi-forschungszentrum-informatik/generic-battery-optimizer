import datetime
import logging
import pyomo.environ as pyo
from pydantic import RootModel

from battery_optimizer.helpers.blocks import get_period_length

log = logging.getLogger(__name__)


class PowerProfile(RootModel):
    """Stores all information about a power profile"""

    root: dict[datetime.datetime, float]


class PowerProfileBlock:

    def __init__(
        self,
        index: pyo.Set,
        source: tuple[
            dict[datetime.datetime, float],
            dict[datetime.datetime, float],
        ] = ({}, {}),
        sink: tuple[
            dict[datetime.datetime, float],
            dict[datetime.datetime, float],
        ] = ({}, {}),
    ):
        """Initializes the PowerProfile class.

        ---------
        Arguments
            index (pyo.Set):
                A Pyomo set representing the indices for the power profile.
            source: tuple[dict, dict]
                Two dictionaries where the keys are timezone-aware datetime
                objects and the values are values for power (first dict) and
                price (second dict).
            sink: tuple[dict, dict]
                Two dictionaries where the keys are timezone-aware datetime
                objects and the values are values for power (first dict) and
                price (second dict).
        """
        self.index = index
        self.source_power = PowerProfile.model_validate(source[0]).model_dump()
        self.source_price = PowerProfile.model_validate(source[1]).model_dump()
        self.sink_power = PowerProfile.model_validate(sink[0]).model_dump()
        self.sink_price = PowerProfile.model_validate(sink[1]).model_dump()

    def build_block(self) -> pyo.Block:
        """Add a new energy profile to the model.

        This can be a buy or a sell profile.
        Generates energy limit for the profile and stores the price in the
        model.
        """
        block = pyo.Block()
        # DEFAULT
        # Source in Matrix
        block.energy_source = pyo.Var(self.index, bounds=(0, 0), initialize=0)
        block.price_source = pyo.Param(self.index, initialize=0, mutable=True)
        # Sink in matrix
        block.energy_sink = pyo.Var(self.index, bounds=(0, 0), initialize=0)
        block.price_sink = pyo.Param(self.index, initialize=0, mutable=True)
        # DEFAULT
        block.energy_source.construct()
        block.price_source.construct()
        block.energy_sink.construct()
        block.price_sink.construct()

        log.debug(self.source_power)
        log.debug(self.source_price)
        log.debug(self.sink_power)
        log.debug(self.sink_price)

        if self.source_power and self.source_price:
            for i in self.index:
                energy = (
                    max(0, self.source_power[i])
                    * get_period_length(i, self.index)[1]
                )
                block.energy_source[i].setub(energy)
                block.price_source[i].set_value(self.source_price[i])

        if self.sink_power and self.sink_price:
            for i in self.index:
                energy = (
                    max(0, self.sink_power[i])
                    * get_period_length(i, self.index)[1]
                )
                block.energy_sink[i].setub(energy)
                block.price_sink[i].set_value(self.sink_price[i])
        return block
