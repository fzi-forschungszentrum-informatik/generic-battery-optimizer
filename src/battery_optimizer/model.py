import logging
import pyomo.environ as pyo
import pandas as pd
from battery_optimizer.blocks.fixed_consumption import FixedConsumptionBlock
from battery_optimizer.blocks.power_profile import PowerProfileBlock
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.static.heat_pump import (
    TEXT_HEAT_PUMP_BASE,
    TEXT_HEATING_ELEMENT_ENERGY_RULE,
    TEXT_INVERTER_ENERGY_RULE,
)
from battery_optimizer.static.model import (
    TEXT_BATTERY_BASE,
    TEXT_CHARGE_ENERGY,
    TEXT_DISCHARGE_ENERGY,
    TEXT_ENERGY_PROFILE_BASE,
    TEXT_SOURCE_DATA_ENERGY_COLUMN,
    TEXT_SOURCE_DATA_PRICE_COLUMN,
    TEXT_SELL_PROFILE_BASE,
    TEXT_CONSUMPTION_PROFILE_BASE,
    TEXT_ENERGY,
    TEXT_PRICE,
    TEXT_ENERGY_PATH_MATRIX,
    TEXT_ENERGY_PATH_SOURCE_CONSTRAINTS,
    TEXT_ENERGY_PATH_SINK_CONSTRAINTS,
    TEXT_SEPARATOR,
    TEXT_OBJECTIVE_NAME,
)
from battery_optimizer.static.profiles import REGEX
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.blocks.heat_pump import HeatPumpBlock
from battery_optimizer.blocks.battery import BatteryBlock

log = logging.getLogger(__name__)

component_map = {
    BatteryBlock: "batteries",
    PowerProfileBlock: "power_profiles",
    FixedConsumptionBlock: "fixed_consumptions",
    HeatPumpBlock: "heat_pumps",
}


# this houses the model itself
class Model:
    """The mathematical model used by the Optimization

    Attributes
    ----------
    index : List[pd.Timestamp]
        A list of sorted timestamps that will be used as the index of the
        model.
    """

    def __init__(self, index: list[pd.Timestamp]) -> None:
        # only create a base structure for the model with absolutely necessary
        # components
        # Objective, index (initialized as empty), (...)
        # the index must be adjusted when adding new elements
        self.model = pyo.ConcreteModel()
        for component in component_map.values():
            self.model.add_component(component, pyo.Block())

        # store all energy sources, sinks and batteries
        self.energy_sources: list[str] = []
        self.energy_sinks: list[str] = []
        self.batteries: list[str] = []

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
        base_name = f"{TEXT_BATTERY_BASE}{battery.name}"
        self.model.batteries.add_component(
            name=base_name,
            val=pyo.Block(
                self.model.i,
                rule=BatteryBlock(self.model.i, battery).get_block,
            ),
        )
        block = self.model.batteries.component(base_name)

        # Energy matrix rules
        self.model.add_component(
            f"{base_name}{TEXT_CHARGE_ENERGY}",
            pyo.Var(
                self.model.i,
                domain=pyo.NonNegativeReals,
            ),
        )
        self.model.add_component(
            f"{base_name}{TEXT_CHARGE_ENERGY} Constraint",
            pyo.Constraint(
                self.model.i,
                rule=lambda model, i: (
                    block[i].energy_sink
                    == model.component(f"{base_name}{TEXT_CHARGE_ENERGY}")[i]
                ),
            ),
        )

        # Discharge energy
        self.model.add_component(
            f"{base_name}{TEXT_DISCHARGE_ENERGY}",
            pyo.Var(
                self.model.i,
                domain=pyo.NonNegativeReals,
            ),
        )
        self.model.add_component(
            f"{base_name}{TEXT_DISCHARGE_ENERGY} Constraint",
            pyo.Constraint(
                self.model.i,
                rule=lambda model, i: (
                    block[i].energy_source
                    == model.component(f"{base_name}{TEXT_DISCHARGE_ENERGY}")[
                        i
                    ]
                ),
            ),
        )

        # can the battery be used as an energy source
        if battery.max_discharge_power > 0:
            self.energy_sources.append(base_name)

        # Add the battery to energy sources and sinks
        self.energy_sinks.append(base_name)

        self.batteries.append(base_name)

    def add_heat_pump(self, heat_pump: HeatPump) -> None:
        # Check that the time stamps of the index are equidistant
        index = self.model.i.ordered_data()
        if pd.infer_freq(index) is None:
            raise ValueError(
                "The index must have a fixed frequency to use the heat pump"
            )
        # Set up the heat pump block
        base_name = f"{TEXT_HEAT_PUMP_BASE}{heat_pump.name}"
        self.model.heat_pumps.add_component(
            name=base_name,
            val=pyo.Block(
                self.model.i,
                rule=HeatPumpBlock(self.model.i, heat_pump).get_block,
            ),
        )
        heat_pump_block = self.model.heat_pumps.component(base_name)
        # Add the power values of the heatpump to the energy sinks
        # We probably need extra variables in the top level of the model
        # and link them to the heatpump block to use the energy matrix
        # generator
        # This would be a TOP_LEVEL_POWER = BLOCK_POWER_VALUE Constraint

        # Funktion verknüpft Wärmeenergie von TES am ende einer Periode t mit
        # Wärmeenergie von TES am Anfang von Periode t+1, Verlust wird
        # berücksichtigt mit verändrbarem Parameter

        # Energy matrix rules
        heat_pump_energy_rule = (
            f"{base_name}{TEXT_SEPARATOR}{TEXT_INVERTER_ENERGY_RULE}"
        )
        heat_recovery_energy_rule = (
            base_name + TEXT_SEPARATOR + TEXT_HEATING_ELEMENT_ENERGY_RULE
        )

        self.model.add_component(
            heat_pump_energy_rule,
            pyo.Var(
                self.model.i,
                domain=pyo.NonNegativeReals,
            ),
        )
        self.model.add_component(
            heat_recovery_energy_rule,
            pyo.Var(
                self.model.i,
                domain=pyo.NonNegativeReals,
            ),
        )

        self.model.add_component(
            f"{heat_pump_energy_rule} Constraint",
            pyo.Constraint(
                self.model.i,
                rule=lambda model, i: (
                    heat_pump_block[i].electric_power_hp
                    * 1000  # Heat pump uses kW, not W
                    * get_period_length(i, self.model.i)[1]
                    == model.component(heat_pump_energy_rule)[i]
                ),
            ),
        )
        self.model.add_component(
            f"{heat_recovery_energy_rule} Constraint",
            pyo.Constraint(
                self.model.i,
                rule=lambda model, i: (
                    heat_pump_block[i].electric_power_hr
                    * 1000  # Heat pump uses kW, not W
                    * get_period_length(i, self.model.i)[1]
                    == model.component(heat_recovery_energy_rule)[i]
                ),
            ),
        )

        # Add heat pump and heat recovery to energy sinks
        self.energy_sinks.append(heat_pump_energy_rule)
        self.energy_sinks.append(heat_recovery_energy_rule)

    def add_buy_profile(self, name: str, profile: pd.DataFrame) -> None:
        """Add an energy buy profile to the model"""
        log.debug("Adding buy profile %s to model", name)
        # add a new price profile to the model
        base_name = f"{TEXT_ENERGY_PROFILE_BASE}{name}"
        self.model.power_profiles.add_component(
            name=base_name,
            val=pyo.Block(
                self.model.i,
                rule=PowerProfileBlock(
                    self.model.i, source=profile.to_dict(orient="index")
                ).get_block,
            ),
        )
        block = self.model.power_profiles.component(base_name)

        # Energy matrix rules
        self.model.add_component(
            f"{base_name}{TEXT_ENERGY}",
            pyo.Var(
                self.model.i,
                domain=pyo.NonNegativeReals,
            ),
        )
        self.model.add_component(
            f"{base_name}{TEXT_ENERGY} Constraint",
            pyo.Constraint(
                self.model.i,
                rule=lambda model, i: (
                    block[i].energy_source
                    == model.component(f"{base_name}{TEXT_ENERGY}")[i]
                ),
            ),
        )

        self.model.add_component(
            f"{base_name}{TEXT_PRICE}",
            pyo.Param(
                self.model.i,
                initialize={
                    i: block[i].price_source.value for i in self.model.i
                },
            ),
        )
        # add the price profile to the energy sources
        self.energy_sources.append(base_name)

    def add_sell_profile(self, name: str, profile: pd.DataFrame) -> None:
        """Add an energy sell profile to the model"""
        log.debug("Adding sell profile %s to model", name)
        # This adds a energy target to the energy matrix and yields revenue in
        # Objective
        base_name = f"{TEXT_SELL_PROFILE_BASE}{name}"
        self.model.power_profiles.add_component(
            name=base_name,
            val=pyo.Block(
                self.model.i,
                rule=PowerProfileBlock(
                    self.model.i, sink=profile.to_dict(orient="index")
                ).get_block,
            ),
        )
        block = self.model.power_profiles.component(base_name)

        # Energy matrix rules
        self.model.add_component(
            f"{base_name}{TEXT_ENERGY}",
            pyo.Var(
                self.model.i,
                domain=pyo.NonNegativeReals,
            ),
        )
        self.model.add_component(
            f"{base_name}{TEXT_ENERGY} Constraint",
            pyo.Constraint(
                self.model.i,
                rule=lambda model, i: (
                    block[i].energy_sink
                    == model.component(f"{base_name}{TEXT_ENERGY}")[i]
                ),
            ),
        )

        self.model.add_component(
            f"{base_name}{TEXT_PRICE}",
            pyo.Param(
                self.model.i,
                initialize={
                    i: block[i].price_sink.value for i in self.model.i
                },
            ),
        )
        self.energy_sinks.append(base_name)

    def add_fixed_consumption(self, name: str, profile: pd.DataFrame) -> None:
        """Add a fixed energy consumption to the model"""
        log.debug("Adding fixed consumption %s to model", name)
        log.debug(profile)
        base_name = f"{TEXT_CONSUMPTION_PROFILE_BASE}{name}"
        self.model.fixed_consumptions.add_component(
            name=base_name,
            val=pyo.Block(
                self.model.i,
                rule=FixedConsumptionBlock(
                    self.model.i,
                    power=profile["energy"].to_dict(),
                ).get_block,
            ),
        )
        block = self.model.fixed_consumptions.component(base_name)

        # Energy matrix rules
        self.model.add_component(
            f"{base_name}{TEXT_ENERGY}",
            pyo.Var(
                self.model.i,
                domain=pyo.NonNegativeReals,
            ),
        )
        self.model.add_component(
            f"{base_name}{TEXT_ENERGY} Constraint",
            pyo.Constraint(
                self.model.i,
                rule=lambda model, i: (
                    block[i].energy_sink
                    == model.component(f"{base_name}{TEXT_ENERGY}")[i]
                ),
            ),
        )
        # add to list of energy sinks
        self.energy_sinks.append(base_name)

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
        self.model.add_component(
            TEXT_ENERGY_PATH_MATRIX,
            pyo.Var(
                self.model.i,
                self.energy_sources,
                self.energy_sinks,
                domain=pyo.NonNegativeReals,
            ),
        )
        log.debug(self.model.component(TEXT_ENERGY_PATH_MATRIX))
        # for each row add a constraint limiting the energy draw
        for source in self.energy_sources:
            log.debug(f"Generate row {source} constraints for energy matrix")
            # name_discharge_energy
            if source.startswith(TEXT_BATTERY_BASE):
                log.debug("%s is a battery", source)
                component = self.model.component(
                    f"{source}{TEXT_DISCHARGE_ENERGY}")
            # name_energy
            elif source.startswith(TEXT_ENERGY_PROFILE_BASE):
                log.debug("%s is an energy profile", source)
                component = self.model.component(f"{source}{TEXT_ENERGY}")
            # unknown
            else:
                raise ValueError(f"{source} is not a valid energy source")
            log.debug("Source: ")
            log.debug(component)

            # add to model
            def energy_path_source_constraint(model, timestamp):
                """Constraint the total energy for an energy source"""
                return (
                    sum(
                        model.component(TEXT_ENERGY_PATH_MATRIX)[
                            timestamp, source, target
                        ]
                        for target in self.energy_sinks
                    )
                    == component[timestamp]
                )

            self.model.add_component(
                (
                    TEXT_ENERGY_PATH_SOURCE_CONSTRAINTS
                    + TEXT_SEPARATOR
                    + source
                ),
                pyo.Constraint(
                    self.model.i, expr=energy_path_source_constraint
                ),
            )
            log.debug("Constraint:")
            log.debug(
                self.model.component(
                    (
                        TEXT_ENERGY_PATH_SOURCE_CONSTRAINTS
                        + TEXT_SEPARATOR
                        + source
                    )
                )
            )
        # for each column add a constraint limiting the charge/feed in energy
        # fixed energy draw needs te satisfy an equality constraint rather
        # than a lesser than constraint
        for sink in self.energy_sinks:
            log.debug(f"Generate column {sink} constraints for energy matrix")
            # name_charge_energy
            if sink.startswith(TEXT_BATTERY_BASE):
                log.debug("%s is a battery", sink)
                component = self.model.component(f"{sink}{TEXT_CHARGE_ENERGY}")
            # Sell profile
            elif sink.startswith(TEXT_SELL_PROFILE_BASE):
                log.debug("%s is a sell profile", sink)
                component = self.model.component(f"{sink}{TEXT_ENERGY}")
            # Fixed consumption
            elif sink.startswith(TEXT_CONSUMPTION_PROFILE_BASE):
                log.debug("%s is a consumption profile", sink)
                component = self.model.component(f"{sink}{TEXT_ENERGY}")
            elif sink.startswith(TEXT_HEAT_PUMP_BASE):
                log.debug("%s is a heat pump", sink)
                component = self.model.component(sink)
            # unknown
            else:
                raise ValueError(f"{sink} is not a valid energy sink")
            log.debug("Sink: ")
            log.debug(component)

            def energy_path_sink_constraint(model, timestamp):
                """Constraint the total energy for an energy sink"""
                return (
                    sum(
                        model.component(TEXT_ENERGY_PATH_MATRIX)[
                            timestamp, source, sink
                        ]
                        for source in self.energy_sources
                    )
                    == component[timestamp]
                )

            self.model.add_component(
                f"{TEXT_ENERGY_PATH_SINK_CONSTRAINTS}{TEXT_SEPARATOR}{sink}",
                pyo.Constraint(self.model.i, expr=energy_path_sink_constraint),
            )
            log.debug("Constraint:")
            log.debug(
                self.model.component(
                    (TEXT_ENERGY_PATH_SINK_CONSTRAINTS + TEXT_SEPARATOR + sink)
                )
            )

    def generate_objective(self):
        """Generate the models objective

        Minimize cost for all price profiles and their consumption
        """
        payed_sources = []
        for source in self.energy_sources:
            if source.startswith(TEXT_ENERGY_PROFILE_BASE):
                payed_sources.append(source)
        log.debug("Payed sources:\n%s", payed_sources)

        payed_sinks = []
        for sink in self.energy_sinks:
            if sink.startswith(TEXT_SELL_PROFILE_BASE):
                payed_sinks.append(sink)
        log.debug("Payed sinks:\n%s", payed_sinks)

        # The cost for energy is minimized
        self.model.add_component(
            TEXT_OBJECTIVE_NAME,
            pyo.Objective(
                expr=sum(
                    self.model.component(f"{source}{TEXT_ENERGY}")[timestamp]
                    * self.model.component(f"{source}{TEXT_PRICE}")[timestamp]
                    for timestamp in self.model.i
                    for source in payed_sources
                )
                # Energy Sinks (payed)
                - sum(
                    self.model.component(f"{source}{TEXT_ENERGY}")[timestamp]
                    * self.model.component(f"{source}{TEXT_PRICE}")[timestamp]
                    for timestamp in self.model.i
                    for source in payed_sinks
                )
                # Value of the energy in the battery
                - sum(
                    self.model.batteries.component(battery)[
                        self.model.i.at(-1)
                    ].soc
                    * max(
                        self.model.component(f"{source}{TEXT_PRICE}")[
                            self.model.i.at(-1)
                        ]
                        for source in payed_sinks
                    )
                    for battery in self.model.batteries.component_map()
                )
            ),
        )
        log.debug(self.model.component(TEXT_OBJECTIVE_NAME))
