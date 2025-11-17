"""
This is the base block for every optimizer component.

It provides common functionality for all optimizer components.
It sets the price and energy parameters and variables.
"""
from abc import abstractmethod
import pyomo.environ as pyo


class BaseBlock:
    """
    This is the template for each block used in the model.

    Each block gets some common parameters, namely energy_source and 
    energy_sink and price_source and price_sink.
    These can be adjusted in a concrete implementation. The energy limits
    are set to 0 by default and prices get a default value of 0 too.
    """
    def __init__(self, index: pyo.Set):
        """
        Initialize a new block.

        Stores information of a component.

        Parameters
        ----------
        index : pyo.Set
            The index of the model.
        """
        self.index = index

    def build_block(self) -> pyo.Block:
        """Build the battery block"""
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
        return self._populate_block(block)

    @abstractmethod
    def _populate_block(self, block: pyo.Block) -> pyo.Block:
        """
        Populate the block with specific constraints and variables.

        This method should be implemented by subclasses to add specific
        functionality to the block.

        Parameters
        ----------
        block : pyo.Block
            The block to populate.

        Returns
        -------
        pyo.Block
            The populated block.
        """
        pass
