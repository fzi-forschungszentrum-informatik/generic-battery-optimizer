import datetime
from pydantic import RootModel
import pyomo.environ as pyo


class FixedPowerProfile(RootModel):
    """Stores all information about a power profile"""

    root: dict[datetime.datetime, float]


class FixedConsumptionBlock:
    def __init__(self, index: pyo.Set, power: dict[datetime.datetime, float]):
        self.index = index
        self.power = FixedPowerProfile.model_validate(power).model_dump()

    def get_block(self, block: pyo.Block):
        # DEFAULT
        # Source in Matrix
        block.energy_source = pyo.Var(bounds=(0, 0))
        block.price_source = pyo.Param(initialize=0, mutable=True)
        # Sink in matrix
        block.energy_sink = pyo.Var(bounds=(0, 0))
        block.price_sink = pyo.Param(initialize=0, mutable=True)
        # DEFAULT

        energy = self.power[block.index()]
        block.energy_sink.setlb(energy)
        block.energy_sink.setub(energy)
