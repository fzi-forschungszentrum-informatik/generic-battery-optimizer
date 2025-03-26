from battery_optimizer.helpers.heat_pump_profile import get_period_length
from battery_optimizer.static.heat_pump import (
    C_TO_K,
    TEXT_HEAT_PUMP_BASE,
    TEXT_HEATING_ELEMENT_ENERGY_RULE,
    TEXT_INVERTER_ENERGY_RULE,
)
from battery_optimizer.static.model import (
    TEXT_BATTERY_BASE,
    TEXT_CHARGE_ENERGY,
    TEXT_DISCHARGE_ENERGY,
    TEXT_SOC,
    TEXT_SOC_CONSTRAINT,
    TEXT_CHARGE_COMPLETION,
    TEXT_CHARGE_START,
    TEXT_IS_CHARGING,
    TEXT_IS_DISCHARGING,
    TEXT_ENFORCE_CHARGING,
    TEXT_ENFORCE_DISCHARGING,
    TEXT_ENFORCE_BINARY_POWER,
    TEXT_ENFORCE_MIN_CHARGE_POWER,
    TEXT_ENFORCE_MIN_DISCHARGE_POWER,
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
from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.helpers.heat_pump_block import heat_pump_block_rule
from battery_optimizer.helpers.parse_profile_stacks import (
    parse_profiles,
)
from battery_optimizer.profiles.profiles import ProfileStack
import pyomo.environ as pyo
from typing import List
import pandas as pd
import logging
import hplib.hplib as hpl

log = logging.getLogger(__name__)


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
        buy_prices: ProfileStack | None = None,
        sell_prices: ProfileStack | None = None,
        fixed_consumption: ProfileStack | None = None,
        batteries: list[Battery] | None = None,
        heat_pumps: list[HeatPump] | None = None,
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
        log.debug("Generating model index")
        temp_index = []

        for stack in [buy_prices, sell_prices, fixed_consumption]:
            if stack is not None:
                for timestamp in stack.index.tolist():
                    temp_index.append(timestamp)
        if temp_index == []:
            raise ValueError(
                "At least one of [buy_prices, sell_prices, fixed_consumption] "
                "must contain values"
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
        log.debug("Initializing buy prices")
        if buy_prices is not None:
            self.buy_prices = parse_profiles(
                buy_prices, index, add_padding_profile=False
            )
            log.debug(self.buy_prices)
        else:
            self.buy_prices = {}

        log.debug("Initializing sell prices")
        if sell_prices is not None:
            self.sell_prices = parse_profiles(sell_prices, index)
            log.debug(self.sell_prices)
        else:
            self.sell_prices = {}

        log.debug("Initializing fixed consumption")
        if fixed_consumption is not None:
            self.fixed_consumption = parse_profiles(fixed_consumption, index)
            log.debug(self.fixed_consumption)
        else:
            self.fixed_consumption = {}

        log.debug("Initializing batteries")
        if batteries is not None:
            self.batteries = batteries
            log.debug(self.batteries)
        else:
            self.batteries = []

        log.debug("Initializing heat pumps")
        if heat_pumps is not None:
            self.heat_pumps = heat_pumps
            log.debug(self.heat_pumps)
        else:
            self.heat_pumps = []

        log.debug("Initializing model structure")
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
        log.info("Generating model structure")
        # for each profile in prices add it to the model
        log.debug("Adding buy profiles to model")
        for name, profile in self.buy_prices.items():
            self.model.add_buy_profile(name, profile)

        # add all sell prices to the model
        log.debug("Adding sell profiles to model")
        for name, profile in self.sell_prices.items():
            self.model.add_sell_profile(name, profile)

        # add all fixed consumptions
        log.debug("Adding all fixed consumptions to model")
        for name, profile in self.fixed_consumption.items():
            self.model.add_fixed_consumption(name, profile)

        # add each battery to the model
        log.debug("Adding all batteries to the model")
        for battery in self.batteries:
            self.model.add_battery(battery)

        log.debug("Adding all heat pumps to the model")
        for heat_pump in self.heat_pumps:
            self.model.add_heat_pump(heat_pump)

        # add all paths
        log.debug("Generating energy paths")
        self.model.add_energy_paths()
        # generate objective
        log.debug("Generating objective")
        self.model.generate_objective()
        # print the model to console
        if log.getEffectiveLevel() <= logging.DEBUG:
            with open("model.log", "w") as file:
                self.model.model.pprint(file)

    def solve(
        self,
        tee=True,
        solver="glpk",
        result_file: str = "",
        options: dict = None,
    ):
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
        options: dict
            Additional options to pass to the solver
            e.g. {"TimeLimit": 60, "MIPGap": 0.01}
        """
        # if !isSetUp
        # set_up()
        return self.model.solve(
            tee=tee, solver=solver, result_file=result_file, options=options
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
        log.debug("Adding %s to the model", battery.name)
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

    def add_heat_pump(self, heat_pump: HeatPump) -> None:
        # Check that the time stamps of the index are equidistant
        index = self.model.i.ordered_data()
        if pd.infer_freq(index) is None:
            raise ValueError(
                "The index must have a fixed frequency to use the heat pump"
            )

        # HPL Heat Pump
        if heat_pump.type == "Luft/Luft" or heat_pump.type == "Air/Air":
            log.warning("L/L-WP")
            raise NotImplementedError("Air/Air heat pumps are not supported.")
        elif heat_pump.type == "Generic":
            parameters = hpl.get_parameters(
                model=heat_pump.type,
                group_id=heat_pump.id,
                t_in=heat_pump.t_in - C_TO_K,
                t_out=heat_pump.t_out - C_TO_K,
                p_th=heat_pump.p_th / 1000,
            )
            hpl_heat_pump = hpl.HeatPump(parameters)
        else:
            parameters = hpl.get_parameters(model=heat_pump.type)
            hpl_heat_pump = hpl.HeatPump(parameters)

        # Set up the heat pump block
        component_name = f"{TEXT_HEAT_PUMP_BASE}{heat_pump.name}"
        self.model.add_component(name=component_name, val=pyo.Block())
        heat_pump_block = self.model.component(component_name)
        heat_pump_block.periods = pyo.Block(
            self.model.i,
            rule=lambda b: heat_pump_block_rule(
                b, heat_pump, self.model, hpl_heat_pump
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
        def heat_energy_TES_linkin_rule(model, t):
            if t == self.model.i.first():
                return (
                    heat_pump_block.periods[t].soc == heat_pump.tes_start_soc
                )

            prev_t = self.model.i.prev(t)

            # y_tes_over_hp_temp constraints
            heat_pump_block.periods[t].y_tes_over_hp_temp_c1 = pyo.Constraint(
                expr=(
                    heat_pump_block.periods[t].temp_TES
                    >= heat_pump.output_temperature
                    - heat_pump.output_temperature
                    * (1 - heat_pump_block.periods[t].y_tes_over_hp_temp)
                ),
                doc=(
                    "TES temperature must be over the heat pumps output "
                    "temperature when y_tes_over_hp_temp is 1"
                ),
            )
            heat_pump_block.periods[t].y_tes_over_hp_temp_c2 = pyo.Constraint(
                expr=(
                    heat_pump_block.periods[t].temp_TES
                    <= heat_pump.output_temperature
                    + (heat_pump.max_temp_tes - heat_pump.output_temperature)
                    * heat_pump_block.periods[t].y_tes_over_hp_temp
                ),
                doc=(
                    "TES temperature must be at or below the heat pump's "
                    "output temperature if y_tes_over_hp_temp is 0."
                ),
            )

            heat_pump_block.periods[t].tes_temperature_below_hp_output = (
                pyo.Constraint(
                    expr=(
                        heat_pump_block.periods[prev_t].y_TES
                        + heat_pump_block.periods[t].y_tes_over_hp_temp
                        <= 1
                    ),
                    doc=(
                        "The TES temperature must be at or below the heat "
                        "pumps output temperature in any period **following a "
                        "charging** of the TES by the heat pump. The TES "
                        "temperature can not exceed the heat pump output "
                        "temperature with out being charged by the heating "
                        "element."
                    ),
                )
            )

            # y_delta_tes_over_value constraints
            # heat_pump_block.periods[t].cons4 = pyo.Constraint(
            #     expr=(
            #         heat_pump_block.periods[t].temp_TES
            #         >= heat_pump.output_temperature
            #         - heat_pump.output_temperature
            #         * (1 - heat_pump_block.periods[t].y_delta_tes_over_value)
            #     ),
            #     doc=(
            #         "TES temperature must be over the heat pumps output "
            #         "temperature when y_delta_tes_over_value is 1"
            #     ),
            # )
            # heat_pump_block.periods[t].cons5 = pyo.Constraint(
            #     expr=(
            #         heat_pump_block.periods[t].temp_TES
            #         <= heat_pump.output_temperature
            #         + (heat_pump.max_temp_tes - heat_pump.output_temperature)
            #         * heat_pump_block.periods[t].y_delta_tes_over_value
            #     ),
            #     doc=(
            #         "TES temperature must be at or below the heat pump's "
            #         "output temperature if y_delta_tes_over_value is 0."
            #     ),
            # )

            heat_pump_block.periods[t].cons6 = pyo.Constraint(
                expr=(
                    heat_pump_block.periods[t].y_TES
                    + heat_pump_block.periods[t].y_tes_over_hp_temp
                    <= 1
                ),
                doc=(
                    "The TES temperature must be at or below the heat "
                    "pumps output temperature in **any period the TES is "
                    "charged** by the heat pump. The TES "
                    "temperature can not exceed the heat pump output "
                    "temperature with out being charged by the heating "
                    "element."
                ),
            )

            return (
                heat_pump_block.periods[t].heat_energy_TES
                == heat_pump_block.periods[prev_t].heat_energy_TES
                + (
                    heat_pump_block.periods[prev_t].heat_supply_hp_to_tes
                    + heat_pump_block.periods[prev_t].heat_supply_HR
                    - heat_pump_block.periods[prev_t].heat_supply_TES_Demand
                    - heat_pump_block.periods[prev_t].heat_loss_tank
                )
                * get_period_length(t, self.model.i)[1]
            )

        heat_pump_block.heat_energy_TES = pyo.Constraint(
            self.model.i, rule=heat_energy_TES_linkin_rule
        )

        # Energy matrix rules
        heat_pump_energy_rule = (
            f"{component_name}{TEXT_SEPARATOR}{TEXT_INVERTER_ENERGY_RULE}"
        )
        heat_recovery_energy_rule = (
            component_name + TEXT_SEPARATOR + TEXT_HEATING_ELEMENT_ENERGY_RULE
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
                    heat_pump_block.periods[i].electric_power_hp
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
                    heat_pump_block.periods[i].electric_power_hr
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
        log.debug("Adding sell profile %s to model", name)
        # This adds a energy target to the energy matrix and yields revenue in
        # Objective
        self.energy_sinks.append(
            self.__add_profile(base=TEXT_SELL_PROFILE_BASE,
                               name=name, profile=profile)
        )

    def add_fixed_consumption(self, name: str, profile: pd.DataFrame) -> None:
        """Add a fixed energy consumption to the model"""
        log.debug("Adding fixed consumption %s to model", name)
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

    def solve(
        self,
        tee=False,
        solver="scip",
        result_file: str = "",
        options: dict = None,
    ):
        """Solve the model

        Variables
        ---------
        tee : bool
            Print debug information of the solver when set to True.
        solver : str
            Specify a solver to use. The default is glpk.
        result_file : str
            Write an ILP file to disk. This works with Gurobi.
        options: dict
            Additional options to pass to the solver
            e.g. {"TimeLimit": 60, "MIPGap": 0.01}
        """
        log.info("Solving model")
        self.solver = SolverFactory(solver)

        if options:
            for key, value in options.items():
                self.solver.options[key] = value

        if result_file != "":
            with open(result_file.replace(".ilp", "_model.txt"), "w") as f:
                self.model.pprint(f)
            self.solver.options["ResultFile"] = result_file

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
