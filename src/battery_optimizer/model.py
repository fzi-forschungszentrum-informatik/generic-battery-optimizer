from datetime import datetime
import logging
from pandas import infer_freq
import pyomo.environ as pyo
from battery_optimizer.blocks.fixed_consumption import FixedConsumptionBlock
from battery_optimizer.blocks.power_profile import PowerProfileBlock
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.static.model import COMPONENT_MAP, TEXT_OBJECTIVE_NAME
from battery_optimizer.profiles.battery_profile import Battery
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

    def constraint_device_power(
        self, a: pyo.Block, b: pyo.Block, power: float
    ) -> pyo.Constraint:
        """Constraint power transfer between two devices

        Adds a constraint to the model that limits the power transfer from
        device `a` to device `b` to a specified value `power` in watts (W).
        This constraint ensures that the energy transferred between the devices
        during a given period is equal to the specified power multiplied by the
        period length.

        Parameters
        ----------
        a : pyo.Block
            The source device from which power is transferred.
        b : pyo.Block
            The target device to which power is transferred.
        power (float):
            The maximum power transfer allowed between `a` and `b` in watts.

        Returns
        -------
        pyo.Constraint
            The constraint object added to the model that enforces
            the power transfer limit.
        """
        constraint_name = a.name + "-" + b.name

        def _device_power_limit(_, period):
            return (
                self.model.energy_matrix[
                    (
                        period,
                        a.parent_block().name,
                        a.local_name,
                        b.parent_block().name,
                        b.local_name,
                    )
                ]
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
    # Die beiden kommen in ne extra Klasse, dann kann man nicht anfangen, erst energypaths zu generieren
    
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

        self.model.energy_matrix = pyo.Var(
            self.model.i,
            device_tuples,  # sources
            device_tuples,  # sinks
            domain=pyo.NonNegativeReals,
        )

        # Add constraints
        def _add_energy_matrix_rules(block, period):
            # for each period add a constraint limiting the energy draw
            # from the source to the sink
            # source sum
            # device.energy_source == sum(all devices energy_sink)
            for device_type, device in device_tuples:
                # add the energy path constraint
                component = self.model.component(device_type).component(device)
                block.add_component(
                    ("source: " + device_type + device),
                    pyo.Constraint(
                        expr=(
                            component.energy_source[period]
                            == sum(
                                self.model.energy_matrix[
                                    (
                                        period,
                                        device_type,
                                        device,
                                        sink_type,
                                        sink,
                                    )
                                ]
                                for sink_type, sink in device_tuples
                            )
                        ),
                    ),
                )
                block.add_component(
                    ("sink: " + device_type + device),
                    pyo.Constraint(
                        expr=(
                            component.energy_sink[period]
                            == sum(
                                self.model.energy_matrix[
                                    (
                                        period,
                                        source_type,
                                        source,
                                        device_type,
                                        device,
                                    )
                                ]
                                for (source_type, source) in device_tuples
                            )
                        ),
                    ),
                )

        self.model.energy_matrix_rules = pyo.Block(
            self.model.i, rule=_add_energy_matrix_rules
        )

    def generate_objective(self):
        """Generate the models objective

        Minimize cost for all price profiles and their consumption
        """
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
                    for source_type, source in device_tuples
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
                    for sink_type, sink in device_tuples
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
                        for sink_type, sink in device_tuples
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
