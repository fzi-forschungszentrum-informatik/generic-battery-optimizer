from datetime import datetime
import logging
from pandas import infer_freq
import pyomo.environ as pyo
from battery_optimizer.blocks.fixed_consumption import FixedConsumptionBlock
from battery_optimizer.blocks.power_profile import PowerProfileBlock
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

        # set up index with 0 items
        self.model.i = pyo.Set(ordered=True, initialize=index)
        log.debug("Model index:")
        log.debug(self.model.i)

    def add_battery(self, battery: Battery) -> None:
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
            val=pyo.Block(
                self.model.i,
                rule=BatteryBlock(self.model.i, battery).get_block,
            ),
        )

    def add_heat_pump(self, heat_pump: HeatPump) -> None:
        # Check that the time stamps of the index are equidistant
        index = self.model.i.ordered_data()
        if infer_freq(index) is None:
            raise ValueError(
                "The index must have a fixed frequency to use the heat pump"
            )
        # Set up the heat pump block
        self.model.heat_pumps.add_component(
            name=heat_pump.name,
            val=pyo.Block(
                self.model.i,
                rule=HeatPumpBlock(self.model.i, heat_pump).get_block,
            ),
        )
        # Add the power values of the heatpump to the energy sinks
        # We probably need extra variables in the top level of the model
        # and link them to the heatpump block to use the energy matrix
        # generator
        # This would be a TOP_LEVEL_POWER = BLOCK_POWER_VALUE Constraint

        # Funktion verknüpft Wärmeenergie von TES am ende einer Periode t mit
        # Wärmeenergie von TES am Anfang von Periode t+1, Verlust wird
        # berücksichtigt mit verändrbarem Parameter

    def add_buy_profile(
        self, name: str, profile: dict[datetime, dict[str, float]]
    ) -> None:
        """
        Add an energy buy profile to the model.

        Parameters
        ----------
        name : str
            The name of the fixed consumption profile.
        profile : dict[datetime, dict[str, float]]
            A dictionary where the
            keys are datetime objects with timezone information, and the
            values are dictionaries containing "energy" and "price" as keys
            with their respective float values.
        """
        log.debug("Adding buy profile %s to model", name)
        # add a new price profile to the model
        self.model.power_profiles.add_component(
            name=name,
            val=pyo.Block(
                self.model.i,
                rule=PowerProfileBlock(self.model.i, source=profile).get_block,
            ),
        )

    def add_sell_profile(
        self, name: str, profile: dict[datetime, dict[str, float]]
    ) -> None:
        """Add an energy sell profile to the model

        Parameters
        ----------
        name : str
            The name of the fixed consumption profile.
        profile : dict[datetime, dict[str, float]]
            A dictionary where the
            keys are datetime objects with timezone information, and the
            values are dictionaries containing "energy" and "price" as keys
            with their respective float values.
        """
        log.debug("Adding sell profile %s to model", name)
        # This adds a energy target to the energy matrix and yields revenue in
        # Objective
        self.model.power_profiles.add_component(
            name=name,
            val=pyo.Block(
                self.model.i,
                rule=PowerProfileBlock(self.model.i, sink=profile).get_block,
            ),
        )

    def add_fixed_consumption(
        self, name: str, profile: dict[datetime, float]
    ) -> None:
        """Add a fixed energy consumption to the model

        Parameters
        ----------
        name : str
            The name of the fixed consumption profile.
        profile : dict[datetime, float]
            A dictionary where the keys are datetime objects and the values
            are floats representing the fixed energy consumption at each
            timestamp.
        """
        log.debug("Adding fixed consumption %s to model", name)
        log.debug(profile)
        self.model.fixed_consumptions.add_component(
            name=name,
            val=pyo.Block(
                self.model.i,
                rule=FixedConsumptionBlock(
                    self.model.i,
                    power=profile,
                ).get_block,
            ),
        )

    def constraint_device_power(self, a, b, power):
        pass

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
                            component[period].energy_source
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
                            component[period].energy_sink
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
                    .component(source)[timestamp]
                    .energy_source
                    * self.model.component(source_type)
                    .component(source)[timestamp]
                    .price_source
                    for timestamp in self.model.i
                    for source_type, source in device_tuples
                )
                # Energy Sinks (payed)
                - sum(
                    self.model.component(sink_type)
                    .component(sink)[timestamp]
                    .energy_sink
                    * self.model.component(sink_type)
                    .component(sink)[timestamp]
                    .price_sink
                    for timestamp in self.model.i
                    for sink_type, sink in device_tuples
                )
                # Value of the energy in the battery
                - sum(
                    self.model.batteries.component(battery)[
                        self.model.i.at(-1)
                    ].soc
                    * max(
                        self.model.component(sink_type)
                        .component(sink)[self.model.i.at(-1)]
                        .price_sink.value
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
