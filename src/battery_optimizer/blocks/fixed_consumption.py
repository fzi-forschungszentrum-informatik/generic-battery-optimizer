import datetime
from pydantic import RootModel
import pyomo.environ as pyo

from battery_optimizer.blocks.base import BaseBlock
from battery_optimizer.helpers.blocks import get_period_length


class FixedPowerProfile(RootModel):
    """Stores all information about a power profile"""

    root: dict[datetime.datetime, float]


class FixedConsumptionBlock(BaseBlock):
    def __init__(self, index: pyo.Set, power: dict[datetime.datetime, float]):
        super().__init__(index)
        self.power = FixedPowerProfile.model_validate(power).model_dump()

    def _populate_block(self, block: pyo.Block) -> pyo.Block:
        for i in self.index:
            energy = self.power[i] * get_period_length(i, self.index)[1]
            block.energy_sink[i].setlb(energy)
            block.energy_sink[i].setub(energy)
        return block
