"""
Module for power profiles used in the optimization model.

Contains classes for buy and sell power profiles, inheriting from a
base power profile class. These profiles can be used to define simple
buying and selling behavior in the optimization model.
"""

import datetime
import logging
import pyomo.environ as pyo
from pydantic import RootModel

from battery_optimizer.blocks.base import BaseBlock
from battery_optimizer.helpers.blocks import get_period_length

log = logging.getLogger(__name__)


class PowerProfile(RootModel):
    """
    Stores all information about a power profile.

    A model used to validate input data for the profile blocks.

    Attributes
    ----------
    root : dict[datetime.datetime, float]
        A dictionary where the keys are timezone-aware datetime objects
        and the values are values for power or price.
    """

    root: dict[datetime.datetime, float]


class PowerProfileBlock(BaseBlock):
    """
    Base class for power profile blocks.

    This class handles both buy and sell profiles by managing source and
    sink power and price data.

    Parameters
    ----------
    index : pyo.Set
        A list of timestamps representing the indices for the power profile.
    source : tuple[
            dict[datetime.datetime, float],
            dict[datetime.datetime, float]
        ]
        The source power and price profile data.
    sink : tuple[
            dict[datetime.datetime, float],
            dict[datetime.datetime, float]
        ]
        The sink power and price profile data.
    """

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
        """
        Initialize the PowerProfile class.

        Validate and store data of the profile and initialize the base block.

        Parameters
        ----------
        index : pyo.Set
            A Pyomo set representing the indices for the power profile.
        source : tuple[dict, dict]
            Two dictionaries where the keys are timezone-aware datetime objects
            and the values are values for power (first dict) and price (second
            dict).
        sink : tuple[dict, dict]
            Two dictionaries where the keys are timezone-aware datetime objects
            and the values are values for power (first dict) and price (second
            dict).
        """
        super().__init__(index)
        self.source_power = PowerProfile.model_validate(source[0]).model_dump()
        self.source_price = PowerProfile.model_validate(source[1]).model_dump()
        self.sink_power = PowerProfile.model_validate(sink[0]).model_dump()
        self.sink_price = PowerProfile.model_validate(sink[1]).model_dump()

    def _populate_block(self, block: pyo.Block) -> pyo.Block:
        """
        Add a new energy profile to the model.

        This can be a buy or a sell profile.
        Generates energy limit for the profile and stores the price in the
        model.

        Parameters
        ----------
        block : pyo.Block
            The Pyomo block to populate with the power profile.

        Returns
        -------
        pyo.Block
            The populated Pyomo block.
        """
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
