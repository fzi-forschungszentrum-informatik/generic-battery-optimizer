from datetime import datetime
import hashlib
import logging
from pandas import infer_freq
import pyomo.environ as pyo
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.static.model import COMPONENT_MAP, TEXT_OBJECTIVE_NAME
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.blocks.fixed_consumption import FixedConsumptionBlock
from battery_optimizer.blocks.power_profile import PowerProfileBlock
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.blocks.heat_pump import HeatPumpBlock
from battery_optimizer.blocks.battery import BatteryBlock

log = logging.getLogger(__name__)


# this houses the model itself
class Model:
    """The mathematical model used by the Optimization

    Attributes
    ----------
    index : List[datetime]
        A list of sorted timestamps that will be used as the index of the
        model.
    """

    def __init__(self, index: list[datetime]) -> None:
        # only create a base structure for the model with absolutely necessary
        # components
        # Objective, index (initialized as empty), (...)
        # the index must be adjusted when adding new elements
        self.model = pyo.ConcreteModel()
        for component in COMPONENT_MAP.values():
            self.model.add_component(component, pyo.Block())

        self.model.add_component("device_power_limits", pyo.Block())

        # set up index with 0 items
        self.model.i = pyo.Set(ordered=pyo.Set.SortedOrder, initialize=index)
        log.debug("Model index:")
        log.debug(self.model.i)

    def add_battery(self, battery: Battery) -> pyo.Block:
        """Add a new battery to the model

        Add all necessary constraints to the model to implement the battery.
        Charge and discharge constraints, SoC calculation and end SoC (if
        needed) are added to the model.

        Variables
        ---------
        battery : Battery
            The battery to add to the model.
        """
        log.debug("Adding %s to the model", battery.name)
        log.debug(battery)
        self.model.batteries.add_component(
            name=battery.name,
            val=BatteryBlock(self.model.i, battery).build_block(),
        )
        return self.model.batteries.component(battery.name)

    def add_heat_pump(self, heat_pump: HeatPump) -> pyo.Block:
        # Check that the time stamps of the index are equidistant
        index = self.model.i.ordered_data()
        if infer_freq(index) is None:
            raise ValueError(
                "The index must have a fixed frequency to use the heat pump"
            )
        # Set up the heat pump block
        self.model.heat_pumps.add_component(
            name=heat_pump.name,
            val=HeatPumpBlock(self.model.i, heat_pump).build_block(),
        )
        # Add the power values of the heatpump to the energy sinks
        # We probably need extra variables in the top level of the model
        # and link them to the heatpump block to use the energy matrix
        # generator
        # This would be a TOP_LEVEL_POWER = BLOCK_POWER_VALUE Constraint

        # Funktion verknüpft Wärmeenergie von TES am ende einer Periode t mit
        # Wärmeenergie von TES am Anfang von Periode t+1, Verlust wird
        # berücksichtigt mit verändrbarem Parameter
        return self.model.heat_pumps.component(heat_pump.name)

    def add_buy_profile(
        self,
        name: str,
        power: dict[datetime, float],
        price: dict[datetime, float],
    ) -> pyo.Block:
        """
        Add an energy buy profile to the model.

        Parameters
        ----------
        name : str
            The name of the fixed consumption profile.
        power : dict[datetime, float]
            A dictionary of power values mapped to datetime objects,
            representing the maximum power that can be bought at each
            timestamp.
        price : dict[datetime, float]
            A dictionary of price values mapped to datetime objects,
            representing the price at which energy can be bought at each
            timestamp.
        """
        log.debug("Adding buy profile %s to model", name)
        # add a new price profile to the model
        self.model.power_profiles.add_component(
            name=name,
            val=PowerProfileBlock(
                self.model.i, source=(power, price)
            ).build_block(),
        )
        return self.model.power_profiles.component(name)

    def add_sell_profile(
        self,
        name: str,
        power: dict[datetime, float],
        price: dict[datetime, float],
    ) -> pyo.Block:
        """Add an energy sell profile to the model

        Parameters
        ----------
        name : str
            The name of the fixed consumption profile.
        power : dict[datetime, float]
            A dictionary of power values mapped to datetime objects,
            representing the maximum power that can be sold at each timestamp.
        price : dict[datetime, float]
            A dictionary of price values mapped to datetime objects,
            representing the price at which energy can be sold at each
            timestamp.
        """
        log.debug("Adding sell profile %s to model", name)
        # This adds a energy target to the energy matrix and yields revenue in
        # Objective
        self.model.power_profiles.add_component(
            name=name,
            val=PowerProfileBlock(
                self.model.i, sink=(power, price)
            ).build_block(),
        )
        return self.model.power_profiles.component(name)

    def add_fixed_consumption(
        self, name: str, power: dict[datetime, float]
    ) -> pyo.Block:
        """Add a fixed energy consumption to the model

        Parameters
        ----------
        name : str
            The name of the fixed consumption profile.
        power : dict[datetime, float]
            A dictionary where the keys are datetime objects and the values
            are floats representing the fixed energy consumption at each
            timestamp.
        """
        log.debug("Adding fixed consumption %s to model", name)
        log.debug(power)
        self.model.fixed_consumptions.add_component(
            name=name,
            val=FixedConsumptionBlock(
                self.model.i,
                power=power,
            ).build_block(),
        )
        return self.model.fixed_consumptions.component(name)

    # TODO move this to a separate class (Model -> MatrixModel (This can be
    # constrained with power limits) -> FullModel (is the result of objective
    # generation) and can be solved)
    def add_energy_paths(self) -> None:
        """Add all necessary energy paths to the model

        Add an energy path between two points of the model.
        Do this for each battery and energy source to create an energy network.
        This needs to be executed after all batteries and energy sources have
        been added.
        """
        # Create energy path matrix
        log.debug("Generating energy matrix")
        # for each row add a constraint limiting the energy draw
        device_tuples = self._get_device_tuples()
        # Filter device tuples to only include those with a power limit > 0
        sources = [
            device_tuple
            for device_tuple in device_tuples
            if any(
                c.ub
                for c in self.model.component(device_tuple[0])
                .component(device_tuple[1])
                .energy_source.values()
            )
            > 0
        ]
        sinks = [
            device_tuple
            for device_tuple in device_tuples
            if any(
                c.ub
                for c in self.model.component(device_tuple[0])
                .component(device_tuple[1])
                .energy_sink.values()
            )
            > 0
        ]

        self.model.energy_matrix = pyo.Var(
            self.model.i,
            sources,  # sources
            sinks,  # sinks
            domain=pyo.NonNegativeReals,
            initialize=0.0,
            doc="Energy transfer between devices",
        )

        # Add constraints
        def _add_energy_matrix_rules(block):
            # for each period add a constraint limiting the energy draw
            # from the source to the sink
            # source sum
            # device.energy_source == sum(all devices energy_sink)
            for device_type, device in sources:
                # add the energy path constraint
                component = self.model.component(device_type).component(device)
                block.add_component(
                    ("source: " + device_type + device),
                    pyo.Constraint(
                        self.model.i,
                        expr=(
                            lambda block, i: component.energy_source[i]
                            == sum(
                                self.model.energy_matrix[
                                    (
                                        i,
                                        device_type,
                                        device,
                                        sink_type,
                                        sink,
                                    )
                                ]
                                for sink_type, sink in sinks
                            )
                        ),
                    ),
                )
            for device_type, device in sinks:
                component = self.model.component(device_type).component(device)
                block.add_component(
                    ("sink: " + device_type + device),
                    pyo.Constraint(
                        self.model.i,
                        expr=(
                            lambda block, i: component.energy_sink[i]
                            == sum(
                                self.model.energy_matrix[
                                    (
                                        i,
                                        source_type,
                                        source,
                                        device_type,
                                        device,
                                    )
                                ]
                                for (source_type, source) in sources
                            )
                        ),
                    ),
                )

        self.model.energy_matrix_rules = pyo.Block(
            rule=_add_energy_matrix_rules
        )

    def constraint_device_power(
        self,
        a: pyo.Block | list[pyo.Block],
        b: pyo.Block | list[pyo.Block],
        power: float,
    ) -> pyo.Constraint:
        """Constraint power transfer between two devices

        Adds a constraint to the model that limits the power transfer from
        device `a` to device `b` to a specified value `power` in watts (W).
        This constraint ensures that the energy transferred between the devices
        during a given period is equal to the specified power multiplied by the
        period length.

        Parameters
        ----------
        a : pyo.Block | list[pyo.Block]
            The source device from which power is transferred.
        b : pyo.Block | list[pyo.Block]
            The target device to which power is transferred.
        power (float):
            The maximum power transfer allowed between `a` and `b` in watts.

        Returns
        -------
        pyo.Constraint
            The constraint object added to the model that enforces
            the power transfer limit.
        """
        if not isinstance(a, list):
            a = [a]
        if not isinstance(b, list):
            b = [b]

        constraint_name = (
            self._hash_names([source.name for source in a])
            + "-"
            + self._hash_names([sink.name for sink in b])
        )

        def _device_power_limit(_, period):
            return (
                sum(
                    self.model.energy_matrix[
                        (
                            period,
                            source.parent_block().name,
                            source.local_name,
                            sink.parent_block().name,
                            sink.local_name,
                        )
                    ]
                    for source in a
                    for sink in b
                )
                <= power * get_period_length(period, self.model.i)[1]
            )

        self.model.device_power_limits.add_component(
            constraint_name,
            val=pyo.Constraint(
                self.model.i,
                rule=_device_power_limit,
            ),
        )
        return self.model.device_power_limits.component(constraint_name)

    def constraint_device_power_source(self, a: list[pyo.Block], power: float):
        """Constraint power transfer from a source to all sinks"""
        return self.constraint_device_power(
            a, self._get_device_tuples(), power
        )

    def constraint_device_power_sink(self, b: list[pyo.Block], power: float):
        """Constraint power transfer to a sink from all sources"""
        return self.constraint_device_power(
            self._get_device_tuples(), b, power
        )

    def generate_objective(self):
        """Generate the models objective

        Minimize cost for all price profiles and their consumption
        """
        device_tuples = self._get_device_tuples()
        # Filter device tuples to only include those with a power limit > 0
        sources = [
            device_tuple
            for device_tuple in device_tuples
            if any(
                c.ub
                for c in self.model.component(device_tuple[0])
                .component(device_tuple[1])
                .energy_source.values()
            )
            > 0
        ]
        sinks = [
            device_tuple
            for device_tuple in device_tuples
            if any(
                c.ub
                for c in self.model.component(device_tuple[0])
                .component(device_tuple[1])
                .energy_sink.values()
            )
            > 0
        ]
        # The cost for energy is minimized
        device_tuples = self._get_device_tuples()
        self.model.add_component(
            TEXT_OBJECTIVE_NAME,
            pyo.Objective(
                expr=sum(
                    self.model.component(source_type)
                    .component(source)
                    .energy_source[timestamp]
                    * self.model.component(source_type)
                    .component(source)
                    .price_source[timestamp]
                    for timestamp in self.model.i
                    for source_type, source in sources
                )
                # Energy Sinks (payed)
                - sum(
                    self.model.component(sink_type)
                    .component(sink)
                    .energy_sink[timestamp]
                    * self.model.component(sink_type)
                    .component(sink)
                    .price_sink[timestamp]
                    for timestamp in self.model.i
                    for sink_type, sink in sinks
                )
                # Value of the energy in the battery
                - sum(
                    self.model.batteries.component(battery).soc[
                        self.model.i.at(-1)
                    ]
                    * max(
                        self.model.component(sink_type)
                        .component(sink)
                        .price_sink[self.model.i.at(-1)]
                        .value
                        for sink_type, sink in sinks
                    )
                    for battery in self.model.batteries.component_map()
                )
            ),
        )
        log.debug(self.model.component(TEXT_OBJECTIVE_NAME))
    def _get_device_tree(self):
        """Get a tree of all devices in the model

        Returns
        -------
        dict
            A dictionary with the device type as key and a list of devices
            as value.
        """
        device_tree = {
            component: list(self.model.component(component).component_map())
            for component in COMPONENT_MAP.values()
        }
        return device_tree

    def _get_device_tuples(self):
        """Get a list of all devices in the model

        Returns
        -------
        list
            A list of tuples with the device type and the device name.
        """
        device_tree = self._get_device_tree()
        device_tuples = [
            (device_type, device)
            for device_type, devices in device_tree.items()
            for device in devices
        ]
        return device_tuples

    @staticmethod
    def _hash_names(names: list[str], inner_seperator = '-'):
        names_joined = inner_seperator.join(names)
        names_hashed = hashlib.md5(names_joined.encode(), usedforsecurity=False).hexdigest()
        names_count = len(names)
        return f'{names_hashed}({names_count})'
