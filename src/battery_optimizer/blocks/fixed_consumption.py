import datetime
from pydantic import RootModel
import pyomo.environ as pyo

from battery_optimizer.helpers.blocks import get_period_length


class FixedPowerProfile(RootModel):
    """Stores all information about a power profile"""

    root: dict[datetime.datetime, float]


class FixedConsumptionBlock:
    def __init__(self, index: pyo.Set, power: dict[datetime.datetime, float]):
        self.index = index
        self.power = FixedPowerProfile.model_validate(power).model_dump()

    def build_block(self) -> pyo.Block:
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

        for i in self.index:
            energy = self.power[i] * get_period_length(i, self.index)[1]
            block.energy_sink[i].setlb(energy)
            block.energy_sink[i].setub(energy)
        return block
