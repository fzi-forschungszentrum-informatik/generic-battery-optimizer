import datetime
import logging
import pyomo.environ as pyo
from pydantic import BaseModel, RootModel, Field

log = logging.getLogger(__name__)


class PowerPriceItem(BaseModel):
    energy: float = Field(
        title="Energy",
        description=(
            "Energy of the energy profile. Price and energy are valid starting "
            "from each date and ending at the next date. "
            "Energy values are in Wh"
        ),
        examples=[30, 35, 30, 40],
    )
    price: float = Field(
        title="Price",
        description=(
            "Energy of the energy profile. Price and energy are valid starting "
            "from each date and ending at the next date. "
            "Price values are in ct/kWh"
        ),
        examples=[0.5, 0.8, 0.1, 1],
    )


class PowerProfile(RootModel):
    """Stores all information about a power profile"""

    root: dict[datetime.datetime, PowerPriceItem]


class PowerProfileBlock:
    def __init__(
        self,
        index: pyo.Set,
        source: dict[datetime.datetime, dict[str, float]] = {},
        sink: dict[datetime.datetime, dict[str, float]] = {},
    ):
        """Initializes the PowerProfile class.

        ---------
        Arguments
            index (pyo.Set):
                A Pyomo set representing the indices for the power profile.
            source (dict[datetime.datetime, dict[str, float]]):
                A dictionary where the keys are timezone-aware datetime
                objects and the values are a dict containing two keys:
                [energy, price] with a float value each for the source.
            sink (dict[datetime.datetime, dict[str, float]]):
                A dictionary where the keys are timezone-aware datetime
                objects and the values are a dict containing two keys:
                [energy, price] with a float value each for the sink.
        """
        self.index = index
        self.source = PowerProfile.model_validate(source).model_dump()
        self.sink = PowerProfile.model_validate(sink).model_dump()

    def get_block(self, block: pyo.Block):
        """Add a new energy profile to the model.

        This can be a buy or a sell profile.
        Generates energy limit for the profile and stores the price in the
        model.
        """
        # DEFAULT
        # Source in Matrix
        block.energy_source = pyo.Var(bounds=(0, 0))
        block.price_source = pyo.Param(initialize=0, mutable=True)
        # Sink in matrix
        block.energy_sink = pyo.Var(bounds=(0, 0))
        block.price_sink = pyo.Param(initialize=0, mutable=True)
        # DEFAULT

        log.debug(self.source)
        log.debug(self.sink)

        i = block.index()

        if self.source:
            block.energy_source.setub(max(0, self.source[i]["energy"]))
            block.price_source.set_value(self.source[i]["price"])

        if self.sink:
            block.energy_sink.setub(max(0, self.sink[i]["energy"]))
            block.price_sink.set_value(self.sink[i]["price"])
