from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.profiles.parse_profile_stacks import (
    REGEX,
    MODEL_PRICE_BELOW,
    MODEL_PRICE_ABOVE,
    MODEL_POWER_BELOW,
    MODEL_POWER_ABOVE,
    parse_profiles,
)
from battery_optimizer.profiles.profiles import ProfileStack
import pyomo.environ as pyo
from typing import List
import pandas as pd
import logging

log = logging.getLogger(__name__)

TEXT_SEPARATOR = " - "
# Battery texts
TEXT_BATTERY_BASE = "Battery: "
TEXT_CHARGE_ENERGY = f"{TEXT_SEPARATOR}charge energy"
TEXT_DISCHARGE_ENERGY = f"{TEXT_SEPARATOR}discharge energy"
TEXT_SOC = f"{TEXT_SEPARATOR}SoC"
TEXT_SOC_CONSTRAINT = f"{TEXT_SOC} Constraint"
TEXT_CHARGE_COMPLETION = f"{TEXT_SEPARATOR}charge completion"
TEXT_CHARGE_START = f"{TEXT_SEPARATOR}charge start time"
TEXT_IS_CHARGING = f"{TEXT_SEPARATOR}is charging"
TEXT_IS_DISCHARGING = f"{TEXT_SEPARATOR}is discharging"
TEXT_ENFORCE_CHARGING = f"{TEXT_SEPARATOR}enforce charging"
TEXT_ENFORCE_DISCHARGING = f"{TEXT_SEPARATOR}enforce discharging"
TEXT_ENFORCE_BINARY_POWER = f"{TEXT_SEPARATOR}enforce binary power flow"
# Minimum charge and discharge power
TEXT_ENFORCE_MIN_CHARGE_POWER = f"{TEXT_SEPARATOR}enforce min charge power"
TEXT_ENFORCE_MIN_DISCHARGE_POWER = (
    f"{TEXT_SEPARATOR}enforce min discharge power"
)
# Energy source texts
TEXT_ENERGY_PROFILE_BASE = "Energy source: "
TEXT_ENERGY = f"{TEXT_SEPARATOR}energy"
TEXT_PRICE = f"{TEXT_SEPARATOR}price"
TEXT_SOURCE_DATA_PRICE_COLUMN = rf"({MODEL_PRICE_BELOW})|({MODEL_PRICE_ABOVE})"
TEXT_SOURCE_DATA_ENERGY_COLUMN = (
    rf"({MODEL_POWER_BELOW})|({MODEL_POWER_ABOVE})"
)
# Sell profile texts
TEXT_SELL_PROFILE_BASE = "Sell sink: "
# Fixed consumption profile texts
TEXT_CONSUMPTION_PROFILE_BASE = "Fixed consumption: "
# Energy path texts
TEXT_ENERGY_PATH_MATRIX = "Energy Matrix"
TEXT_ENERGY_PATH_SOURCE_CONSTRAINTS = "Energy distribution source constraints"
TEXT_ENERGY_PATH_SINK_CONSTRAINTS = "Energy distribution target constraints"
# Objective texts
TEXT_OBJECTIVE_NAME = "Objective"


class Optimizer:
    """Optimize the energy distribution of an energy system.

    Attributes
    ----------
    buy_prices : ProfileStack
        All profiles energy can be bought from.
    sell_prices : ProfileStack
        All profiles energy can be sold to.
    fixed_consumption : ProfileStack
        All fixed consumption data for the model.
    batteries : List[Battery]
        All batteries that can be used.
    """

    def __init__(
        self,
        buy_prices: ProfileStack | None,
        sell_prices: ProfileStack | None,
        fixed_consumption: ProfileStack | None,
        batteries: list[Battery] | None,
    ) -> None:
        """Format all input data and set up the base model

        Creates lists from all input data sources to be used with the model and
        initializes the base structure of the model. Before using the model it
        needs to be populated.
        Differing timestamps will be merged to the highest resolution and
        whenever the granularity of a profile is increased as a result from
        another profile or battery the power is assumed to be the same as the
        previous power.

        Variables
        ---------
        buy_prices : ProfileStack
            All profiles to buy energy from.
            Price is assumed to be in ct/kWh.
            Power is assumed to be in W.
            If none of the profiles has a price_above specified a "padding"
            profile is added to the stack to prevent infeasible model results.
            If this padding profile is used the power demand from hard
            constraints can not be fulfilled at that point in time.
        sell_prices : ProfileStack
            All profiles to sell energy to.
            Price is assumed to be in ct/kWh.
            Power is assumed to be in W.
        fixed_consumption : ProfileStack
            A list of fixed consumption profiles.
            Power is assumed to be in W.
            for the electricity during this time period (unused here).
        batteries : List[Battery]
            A list of batteries that can be used in the optimization.

        Raises
        ------
        ValueError
            If none of the input stacks contain any data.
        """
        log.info("Initializing Optimizer")
        # get all timestamps (build index)
        log.info("Generating model index")
        temp_index = []

        for stack in [buy_prices, sell_prices, fixed_consumption]:
            if stack is not None:
                for timestamp in stack.index.tolist():
                    temp_index.append(timestamp)
        if temp_index == []:
            raise ValueError(
                "At least one of [buy_prices, sell_prices, fixed_consumption] must contain values"
            )

        if batteries is not None:
            for battery in batteries:
                if battery.end_soc_time is not None:
                    temp_index.append(battery.end_soc_time)
                if battery.start_soc_time is not None:
                    temp_index.append(battery.start_soc_time)
        log.debug("Temporary Index:")
        log.debug(temp_index)

        # remove duplicates
        index: List[pd.Timestamp] = []
        for item in temp_index:
            if item not in index:
                index.append(item)
        # sort the index
        index.sort()
        log.debug("Index of the model:")
        log.debug(index)

        # init optimizer
        log.info("Initializing buy prices")
        if buy_prices is not None:
            self.prices = parse_profiles(
                buy_prices, index, add_padding_profile=False
            )
            log.debug(self.prices)
        else:
            self.prices = {}

        log.info("Initializing sell prices")
        if sell_prices is not None:
            self.sell_prices = parse_profiles(sell_prices, index)
            log.debug(self.sell_prices)
        else:
            self.sell_prices = {}

        log.info("Initializing fixed consumption")
        if fixed_consumption is not None:
            self.fixed_consumption = parse_profiles(fixed_consumption, index)
            log.debug(self.fixed_consumption)
        else:
            self.fixed_consumption = {}

        log.info("Initializing batteries")
        if batteries is not None:
            self.batteries = batteries
            log.debug(self.batteries)
        else:
            self.batteries = []

        log.info("Initializing model structure")
        self.model = Model(index)
        if log.getEffectiveLevel() <= logging.DEBUG:
            self.model.model.display()

    def set_up(self):
        """Set up the model for optimization

        This will add all buy price profiles, sell price profiles,
        fixed consumptions and batteries to the model.
        All Energy paths are created and the objective is generated.

        The model will be saved to model.log when running in debug mode
        """
        # for each profile in prices add it to the model
        log.info("Adding buy profiles to model")
        for name, profile in self.prices.items():
            self.model.add_buy_profile(name, profile)

        # add all sell prices to the model
        log.info("Adding sell profiles to model")
        for name, profile in self.sell_prices.items():
            self.model.add_sell_profile(name, profile)

        # add all fixed consumptions
        log.info("Adding all fixed consumptions to model")
        for name, profile in self.fixed_consumption.items():
            self.model.add_fixed_consumption(name, profile)

        # add each battery to the model
        log.info("Adding all batteries to the model")
        for battery in self.batteries:
            self.model.add_battery(battery)
        # add all paths
        log.info("Generating energy paths")
        self.model.add_energy_paths()
        # generate objective
        log.info("Generating objective")
        self.model.generate_objective()
        # print the model to console
        if log.getEffectiveLevel() <= logging.DEBUG:
            with open("model.log", "w") as file:
                self.model.model.pprint(file)

    def solve(self, tee=True, solver="glpk", result_file: str = ""):
        """Solve the model

        This solves the model. set_up() needs to be called before solving can
        start.

        Variables
        ---------
        tee : bool
            Print debug information of the solver when set to True.
        solver : str
            Specify a solver to use. The default is glpk.
        result_file : str
            Write an ILP file to disk. This works with Gurobi.
        """
        # if !isSetUp
        # set_up()
        return self.model.solve(
            tee=tee, solver=solver, result_file=result_file
        )


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
        self.solver: SolverFactory = None

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
        log.info("Adding %s to the model", battery.name)
        log.debug(battery)
        base_name = f"{TEXT_BATTERY_BASE}{battery.name}"
        name_charge_energy = f"{base_name}{TEXT_CHARGE_ENERGY}"
        name_discharge_energy = f"{base_name}{TEXT_DISCHARGE_ENERGY}"
        name_soc = f"{base_name}{TEXT_SOC}"
        name_soc_constraint = f"{base_name}{TEXT_SOC_CONSTRAINT}"
        name_charge_completion = f"{base_name}{TEXT_CHARGE_COMPLETION}"
        # Battery can only charge or discharge
        name_battery_is_charging = f"{base_name}{TEXT_IS_CHARGING}"
        name_battery_is_discharging = f"{base_name}{TEXT_IS_DISCHARGING}"
        name_battery_enforce_charging = f"{base_name}{TEXT_ENFORCE_CHARGING}"
        name_battery_enforce_discharging = (
            f"{base_name}{TEXT_ENFORCE_DISCHARGING}"
        )
        name_battery_enforce_binary_power = (
            f"{base_name}{TEXT_ENFORCE_BINARY_POWER}"
        )
        # Min charge and discharge power requirements
        name_min_charge_power = f"{base_name}{TEXT_ENFORCE_MIN_CHARGE_POWER}"
        name_min_discarge_power = (
            f"{base_name}{TEXT_ENFORCE_MIN_DISCHARGE_POWER}"
        )
        # add a battery to the model
        # 1 variable for battery energy in and 1 for energy out

        def max_charge_energy(model, i):
            """Maximum energy that can be charged in time period i"""
            # from last timestamp no energy usage is allowed
            if i == model.i.last():
                return (0, 0)
            # get time delta
            delta = model.i.next(i) - i
            # calculate energy that is allowed
            return (0, battery.max_charge_power * (delta / pd.Timedelta("1h")))

        self.model.add_component(
            name_charge_energy,
            pyo.Var(self.model.i, bounds=max_charge_energy),
        )

        def max_discharge_energy(model, i):
            """Maximum energy that can be discharged in time period i"""
            # from last timestamp no energy usage is allowed
            if i == model.i.last():
                return (0, 0)
            # get time delta
            delta = model.i.next(i) - i
            # calculate energy that is allowed
            return (
                0,
                battery.max_discharge_power * (delta / pd.Timedelta("1h")),
            )

        self.model.add_component(
            name_discharge_energy,
            pyo.Var(self.model.i, bounds=max_discharge_energy),
        )
        self.model.add_component(
            name_soc, pyo.Var(self.model.i, bounds=(0, battery.capacity))
        )

        # soc calculation
        def soc_rule(model, i):
            """Calculate the SOC of the battery

            SOC rule calculating the current energy state of the battery and
            change in energy for the first timestamp and the change of energy
            relative to the previous timestamps energy for all other
            timestamps.
            """
            if i == model.i.at(1):
                return model.component(name_soc)[
                    i
                ] == battery.start_soc * battery.capacity + model.component(
                    name_charge_energy
                )[
                    i
                ] * battery.charge_efficiency - model.component(
                    name_discharge_energy
                )[
                    i
                ] * (
                    1 / battery.discharge_efficiency
                )
            else:
                return model.component(name_soc)[i] == model.component(
                    name_soc
                )[model.i.prev(i)] + model.component(name_charge_energy)[
                    i
                ] * battery.charge_efficiency - model.component(
                    name_discharge_energy
                )[
                    i
                ] * (
                    1 / battery.discharge_efficiency
                )

        self.model.add_component(
            name_soc_constraint, pyo.Constraint(self.model.i, expr=soc_rule)
        )

        # make sure the charging is complete at the required timestamp
        if battery.end_soc_time is not None:

            def charge_finished(model, i):
                if i < battery.end_soc_time:
                    return (0, model.component(name_soc)[i], battery.capacity)
                return (
                    battery.end_soc * battery.capacity,
                    model.component(name_soc)[i],
                    # This is needed to make sure the result remains feasible
                    battery.end_soc * battery.capacity + 0.001,
                )

            self.model.add_component(
                name_charge_completion,
                pyo.Constraint(self.model.i, expr=charge_finished),
            )

        # do not use the battery until its start
        if battery.start_soc_time is not None:
            # Prevent charge
            def charge_start(model, i):
                if i < battery.start_soc_time:
                    return (0, model.component(name_charge_energy)[i], 0)
                return (
                    0,
                    model.component(name_charge_energy)[i],
                    battery.max_charge_power,
                )

            self.model.add_component(
                f"{name_charge_energy}{TEXT_CHARGE_START}",
                pyo.Constraint(self.model.i, expr=charge_start),
            )

            # Prevent Discharge
            if battery.max_discharge_power > 0:

                def discharge_start(model, i):
                    if i < battery.start_soc_time:
                        return (
                            0,
                            model.component(name_discharge_energy)[i],
                            0,
                        )
                    return (
                        0,
                        model.component(name_discharge_energy)[i],
                        battery.max_discharge_power,
                    )

                self.model.add_component(
                    f"{name_discharge_energy}{TEXT_CHARGE_START}",
                    pyo.Constraint(self.model.i, expr=discharge_start),
                )

        # Enforce that the battery can only charge or discharge
        # We only add this if needed to reduce complexity
        # This is needed if charge and discharge efficiency is 100% or
        # minimum discharge or minimum charge power is set

        if (
            (
                battery.charge_efficiency == 1
                and battery.discharge_efficiency == 1
            )
            or battery.min_charge_power > 0
            or battery.min_discharge_power > 0
        ):
            # Charging
            self.model.add_component(
                name_battery_is_charging,
                pyo.Var(self.model.i, within=pyo.Binary),
            )

            def enforce_binary_charging(model, i):
                """Enforce name_battery_is_charging to be 1 if charge_power > 0"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                if i == model.i.last():
                    delta = pd.Timedelta("0h")
                else:
                    delta = model.i.next(i) - i

                return (
                    model.component(name_charge_energy)[i]
                    <= battery.max_charge_power
                    * (delta / pd.Timedelta("1h"))
                    * model.component(name_battery_is_charging)[i]
                )

            self.model.add_component(
                name_battery_enforce_charging,
                pyo.Constraint(self.model.i, rule=enforce_binary_charging),
            )

            # Discharging
            self.model.add_component(
                name_battery_is_discharging,
                pyo.Var(self.model.i, within=pyo.Binary),
            )

            def enforce_binary_discharging(model, i):
                """Enforce name_battery_is_discharging to be 1 if
                discharge_power > 0"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                if i == model.i.last():
                    delta = pd.Timedelta("0h")
                else:
                    delta = model.i.next(i) - i

                return (
                    model.component(name_discharge_energy)[i]
                    <= battery.max_discharge_power
                    * (delta / pd.Timedelta("1h"))
                    * model.component(name_battery_is_discharging)[i]
                )

            self.model.add_component(
                name_battery_enforce_discharging,
                pyo.Constraint(self.model.i, rule=enforce_binary_discharging),
            )

            def enforce_binary_charging_discharging(model, i):
                """Enforce battery can only charge or discharge"""
                return (
                    model.component(name_battery_is_charging)[i]
                    + model.component(name_battery_is_discharging)[i]
                    <= 1
                )

            self.model.add_component(
                name_battery_enforce_binary_power,
                pyo.Constraint(
                    self.model.i, rule=enforce_binary_charging_discharging
                ),
            )

        if battery.min_charge_power > 0:

            def min_charge_power_constraint(model, i):
                """Constraint that ensures the battery is charged with
                min_charge_power if it is charged"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                if i == model.i.last():
                    delta = pd.Timedelta("0h")
                else:
                    delta = model.i.next(i) - i

                return (
                    model.component(name_charge_energy)[i]
                    >= battery.min_charge_power
                    * (delta / pd.Timedelta("1h"))
                    * model.component(name_battery_is_charging)[i]
                )

            self.model.add_component(
                name_min_charge_power,
                pyo.Constraint(self.model.i, expr=min_charge_power_constraint),
            )

        if battery.min_discharge_power > 0:

            def min_discharge_power_constraint(model, i):
                """Constraint that ensures the battery is discharged with
                min_discharge_power if it is discharged"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                if i == model.i.last():
                    delta = pd.Timedelta("0h")
                else:
                    delta = model.i.next(i) - i

                return (
                    model.component(name_discharge_energy)[i]
                    >= battery.min_discharge_power
                    * (delta / pd.Timedelta("1h"))
                    * model.component(name_battery_is_discharging)[i]
                )

            self.model.add_component(
                name_min_discarge_power,
                pyo.Constraint(
                    self.model.i, expr=min_discharge_power_constraint
                ),
            )

        # can the battery be used as an energy source
        if battery.max_discharge_power > 0:
            self.energy_sources.append(base_name)

        # Add the battery to energy sources and sinks
        self.energy_sinks.append(base_name)

        self.batteries.append(base_name)

    def add_buy_profile(self, name: str, profile: pd.DataFrame) -> None:
        """Add an energy buy profile to the model"""
        log.info("Adding buy profile %s to model", name)
        # add a new price profile to the model
        component_name = self.__add_profile(
            base=TEXT_ENERGY_PROFILE_BASE, name=name, profile=profile
        )
        # add the price profile to the energy sources
        self.energy_sources.append(component_name)

    def __add_profile(
        self, base: str, name: str, profile: pd.DataFrame
    ) -> str:
        """Add a new energy profile to the model.

        This can be a buy or a sell profile.
        Generates energy limit for the profile and stores the price in the
        model.
        """
        base_name = f"{base}{name}"
        name_energy = f"{base_name}{TEXT_ENERGY}"
        name_price = f"{base_name}{TEXT_PRICE}"

        log.debug(profile)

        # calculate energy limit
        def energy_limit(_, i):
            """Get maximum energy of profile at index i"""
            return (
                0,
                max(
                    0,
                    profile.filter(
                        regex=f"{REGEX}{TEXT_SOURCE_DATA_ENERGY_COLUMN}$")
                    .loc[i]
                    .values[0],
                ),
            )

        self.model.add_component(
            name_energy, pyo.Var(self.model.i, bounds=energy_limit)
        )
        log.debug(self.model.component(name_energy))
        # prices
        log.debug(profile.filter(
            regex=f"{REGEX}{TEXT_SOURCE_DATA_PRICE_COLUMN}$"))
        self.model.add_component(
            name_price,
            pyo.Param(
                self.model.i,
                initialize=profile.filter(
                    regex=f"{REGEX}{TEXT_SOURCE_DATA_PRICE_COLUMN}$"
                ),
            ),
        )
        log.debug(self.model.component(name_price))

        return base_name

    def add_sell_profile(self, name: str, profile: pd.DataFrame) -> None:
        """Add an energy sell profile to the model"""
        log.info("Adding sell profile %s to model", name)
        # This adds a energy target to the energy matrix and yields revenue in
        # Objective
        self.energy_sinks.append(
            self.__add_profile(base=TEXT_SELL_PROFILE_BASE,
                               name=name, profile=profile)
        )

    def add_fixed_consumption(self, name: str, profile: pd.DataFrame) -> None:
        """Add a fixed energy consumption to the model"""
        log.info("Adding fixed consumption %s to model", name)
        log.debug(profile)

        base_name = f"{TEXT_CONSUMPTION_PROFILE_BASE}{name}"
        name_energy = f"{base_name}{TEXT_ENERGY}"

        # calculate energy limit
        def energy_limit(_, i):
            """Get maximum energy of profile at index i"""
            value = (
                profile.filter(
                    regex=f"{REGEX}{TEXT_SOURCE_DATA_ENERGY_COLUMN}$")
                .loc[i]
                .values[0]
            )
            return (value, value)

        self.model.add_component(
            name_energy, pyo.Var(self.model.i, bounds=energy_limit)
        )
        log.debug(self.model.component(name_energy))

        # add to list of energy sinks
        self.energy_sinks.append(base_name)

    def add_energy_paths(self) -> None:
        """Add all necessary energy paths to the model

        Add an energy path between two points of the model.
        Do this for each battery and energy source to create an energy network.
        This needs to be executed after all batteries and energy sources have
        been added.
        """
        # Create energy path matrix
        log.info("Generating energy matrix")
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
            log.info(f"Generate row {source} constraints for energy matrix")
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
                f"{TEXT_ENERGY_PATH_SOURCE_CONSTRAINTS}{TEXT_SEPARATOR}{source}",
                pyo.Constraint(
                    self.model.i, expr=energy_path_source_constraint),
            )
            log.debug("Constraint:")
            log.debug(
                self.model.component(
                    f"{TEXT_ENERGY_PATH_SOURCE_CONSTRAINTS}{TEXT_SEPARATOR}{source}"
                )
            )
        # for each column add a constraint limiting the charge/feed in energy
        # fixed energy draw needs te satisfy an equality constraint rather
        # than a lesser than constraint
        for sink in self.energy_sinks:
            log.info(f"Generate column {sink} constraints for energy matrix")
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
                    f"{TEXT_ENERGY_PATH_SINK_CONSTRAINTS}{TEXT_SEPARATOR}{sink}"
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
                    self.model.component(f"{battery}{TEXT_SOC}")[
                        self.model.i.at(-1)]
                    * max(
                        self.model.component(f"{source}{TEXT_PRICE}")[
                            self.model.i.at(-1)
                        ]
                        for source in payed_sinks
                    )
                    for battery in self.batteries
                )
            ),
        )
        log.debug(self.model.component(TEXT_OBJECTIVE_NAME))

    def solve(self, tee=False, solver="glpk", result_file: str = ""):
        """Solve the model

        Variables
        ---------
        tee : bool
            Print debug information of the solver when set to True.
        solver : str
            Specify a solver to use. The default is glpk.
        result_file : str
            Write an ILP file to disk. This works with Gurobi.
        """
        log.info("Solving model")
        self.solver = SolverFactory(solver)

        if result_file != "":
            self.solver.options["ResultFile"] = result_file

        # Suppress pyomo output from the solver
        # if log.getEffectiveLevel() > logging.DEBUG:
        #    logging.getLogger('pyomo.core').setLevel(logging.ERROR)

        result = self.solver.solve(
            self.model, tee=tee, symbolic_solver_labels=True)

        # Check if the result has a feasible Solution
        if (result.solver.status == SolverStatus.ok) and (
            result.solver.termination_condition == TerminationCondition.optimal
        ):
            # The solution is optimal and feasible
            return result
        elif (
            result.solver.termination_condition
            == TerminationCondition.unbounded
        ) or (
            result.solver.termination_condition
            == TerminationCondition.infeasible
        ):
            # Do something when model is infeasible
            log.error(
                "The model is infeasible: %s",
                result.solver.termination_condition,
            )
        else:
            # Something else is wrong
            log.error("Solver Status: %s", result.solver.status)
        return None
