"""
This module defines a Pyomo block for modeling a heat pump system.

This model can simulate the operation of a heat pump system over a specified
time index. It decides between two cop values depending on whether a thermal
energy storage (TES) is being charged to shift electricity usage or not.
The foundation for this model is the work of Nicolas Schilz 2024 (Flexibilität
moderner Wärmepumpen).
"""

import logging
import pyomo.environ as pyo
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.helpers.heat_pump_profile import (
    interpolate_temperature,
    interpolate_heat_energy,
)
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.static.numbers import MAX_COP

log = logging.getLogger(__name__)


class HeatPumpBlock:
    """
    A Pyomo block representing a heat pump system.

    This block models the operation of a heat pump system over a specified
    time index. It includes variables, parameters, and constraints to simulate
    the heat pump's behavior, including its energy consumption, heat supply,
    and interactions with a thermal energy storage (TES) system.

    Parameters
    ----------
    index : pyo.Set
        The time index for the heat pump model.
    heat_pump : HeatPump
        The heat pump profile containing parameters and settings.
    """
    def __init__(self, index: pyo.Set, heat_pump: HeatPump):
        """
        Initialize the heat pump block.

        Store the index and heat pump profile for use in building the heat
        pump model.

        Parameters
        ----------
        index : pyo.Set
            The time index for the heat pump model.
        heat_pump : HeatPump
            The heat pump profile containing parameters and settings.
        """
        self.index = index
        self.heat_pump = heat_pump

    def build_block(self) -> pyo.Block:
        """
        Build the heat pump block.

        This method constructs a Pyomo block that models the operation of a
        heat pump system over a specified time index. It includes variables,
        parameters, and constraints to simulate the heat pump's behavior,
        including its energy consumption, heat supply, and interactions with
        a thermal energy storage (TES) system.

        Returns
        -------
        pyo.Block
            A Pyomo block representing a heat pump system.
        """
        block = pyo.Block()
        # DEFAULT
        # Source in Matrix
        block.energy_source = pyo.Var(self.index, initialize=0)
        block.price_source = pyo.Param(self.index, initialize=0, mutable=True)
        # Sink in matrix
        block.energy_sink = pyo.Var(self.index, initialize=0)
        block.price_sink = pyo.Param(self.index, initialize=0, mutable=True)
        # DEFAULT
        block.energy_source.construct()
        block.price_source.construct()
        block.energy_sink.construct()
        block.price_sink.construct()

        # Add old heat pump block for compatibility
        block.hp_block = pyo.Block(self.index, rule=self.get_block)

        # Link energy and price to old heat pump block
        block.energy_source_constraint = pyo.Constraint(
            self.index,
            rule=(
                lambda block, i: block.energy_source[i]
                == block.hp_block[i].energy_source
            ),
        )
        block.price_source_constraint = pyo.Constraint(
            self.index,
            rule=(
                lambda block, i: block.price_source[i]
                == block.hp_block[i].price_source
            ),
        )
        block.energy_sink_constraint = pyo.Constraint(
            self.index,
            rule=(
                lambda block, i: block.energy_sink[i]
                == block.hp_block[i].energy_sink
            ),
        )
        block.price_sink_constraint = pyo.Constraint(
            self.index,
            rule=(
                lambda block, i: block.price_sink[i]
                == block.hp_block[i].price_sink
            ),
        )
        return block

    def get_block(self, block: pyo.Block):
        """
        Model a single period of the heat pump operation.

        Sets all parameters, variables and constraints for a single period of
        the heat pump simulation/optimization.

        Parameters
        ----------
        block : pyo.Block
            The Pyomo block to which the heat pump model will be added.
        """
        # DEFAULT
        # Source in Matrix
        block.energy_source = pyo.Var(bounds=(0, 0), initialize=0)
        block.price_source = pyo.Param(initialize=0, mutable=True)
        # Sink in matrix
        block.energy_sink = pyo.Var(bounds=(0, 0), initialize=0)
        block.price_sink = pyo.Param(initialize=0, mutable=True)
        # DEFAULT

        period = block.index()

        _, period_conversion_factor = get_period_length(period, self.index)

        temp_room = interpolate_temperature(self.heat_pump.temp_room, period)

        # Parameters
        if self.heat_pump.outdoor_temperature is not None:
            block.outdoor_temperature = pyo.Param(
                initialize=interpolate_temperature(
                    self.heat_pump.outdoor_temperature, period
                ),
                within=pyo.Reals,
            )

        block.warm_water_demand = pyo.Param(
            initialize=interpolate_heat_energy(
                self.heat_pump.warm_water_demand, period
            ),
            within=pyo.NonNegativeReals,
            doc="Warm water demand in kW for this period.",
        )

        block.heat_loss_building = pyo.Param(
            initialize=interpolate_heat_energy(
                self.heat_pump.heat_demand, period
            ),
            within=pyo.NonNegativeReals,
            doc="Building heat loss/demand in kW for this period.",
        )

        block.cop_high = pyo.Param(
            initialize=(
                self.heat_pump.cop_high_temp[period]
                if isinstance(self.heat_pump.cop_high_temp, dict)
                else self.heat_pump.cop_high_temp
            ),
            doc=(
                "The COP of the heat pump at the maximum output temperature."
            ),
        )
        block.cop_low = pyo.Param(
            initialize=(
                self.heat_pump.cop_low_temp[period]
                if isinstance(self.heat_pump.cop_low_temp, dict)
                else self.heat_pump.cop_low_temp
            ),
            doc=("The COP of the heat pump at the flow output temperature."),
        )

        # Variables
        # Binary
        block.y_HR = pyo.Var(
            within=pyo.Binary, doc="Electric heater is on (1) or off (0)"
        )
        block.y_HP = pyo.Var(
            within=pyo.Binary, doc="Heat pump is on (1) or off (0)"
        )
        block.y_TES = pyo.Var(
            within=pyo.Binary, doc="TES is being charged (1) or discharged (0)"
        )

        # electric power
        block.electric_power_hr = pyo.Var(
            bounds=(
                0,
                self.heat_pump.max_electric_power_hr,
            ),
            doc=(
                "Electric energy consumption of the electric heater in kW "
                "during this period."
            ),
        )
        block.electric_power_hp = pyo.Var(
            bounds=(
                0,
                self.heat_pump.max_electric_power_hp,
            ),
            doc=(
                "Electric energy consumption of the heat pump in kW during "
                "this period."
            ),
        )

        # link electric power to energy
        block.energy_sink.setub(
            (block.electric_power_hp.ub + block.electric_power_hr.ub)
            * 1000  # Heat pump uses kW, not W
            * period_conversion_factor
        )
        block.electric_power_link = pyo.Constraint(
            expr=(
                (block.electric_power_hp + block.electric_power_hr)
                * 1000  # Heat pump uses kW, not W
                * period_conversion_factor
                == block.energy_sink
            ),
            name="",
            doc=(
                "Link between electric power for hp and hr and energy. "
                "Both are added together and published as a single energy "
                "variable. "
                "Electric power is converted to energy over the period length."
            ),
        )

        # heat flows
        block.heat_supply_hp_total = pyo.Var(
            bounds=(
                0,
                self.heat_pump.max_heat_supply_hp,
            ),
            doc=(
                "The total heat energy the heat pump supplies in kW in this "
                "period. This heat energy is shared by "
                "heat_supply_hp_to_demand and heat_supply_hp_to_tes."
            ),
        )
        block.heat_supply_hp_to_demand = pyo.Var(
            bounds=(
                0,
                self.heat_pump.max_heat_supply_hp,
            ),
            doc=(
                "The heat energy the heat pump supplies to the demand side in "
                "kW during this period."
            ),
        )
        block.heat_supply_hp_to_tes = pyo.Var(
            bounds=(
                0,
                self.heat_pump.max_heat_supply_hp,
            ),
            doc=(
                "The heat energy the heat pump supplies to the TES in kW "
                "during this period."
            ),
        )

        block.heat_supply_HR = pyo.Var(
            bounds=(
                0,
                self.heat_pump.max_electric_power_hr,
            )
        )

        block.heat_supply_TES_Demand = pyo.Var(
            bounds=(
                0,
                self.heat_pump.max_heat_supply_tes,
            )
        )

        block.heat_supply_demand = pyo.Var(domain=pyo.NonNegativeReals)

        # Temp
        block.temp_TES = pyo.Var(
            bounds=(temp_room, self.heat_pump.max_temp_tes)
        )

        # Tank
        block.heat_energy_TES = pyo.Var(
            bounds=(0, self.heat_pump.max_heat_energy_tes),
            doc=("Maximum heat energy that can be stored in the TES in kWh"),
        )
        block.soc = pyo.Var(bounds=(0, 1))
        block.heat_loss_tank = pyo.Var(domain=pyo.NonNegativeReals)

        block.y_tes_over_hp_temp = pyo.Var(
            within=pyo.Binary,
            doc=(
                "Defines wether the TES temperature is above the heat pump's "
                "output temperature (1) or below the heat pump's output "
                "temperature (0)."
            ),
        )

        block.cop_value = pyo.Var(
            domain=pyo.NonNegativeReals, bounds=(0, MAX_COP)
        )

        # in diesem modell HR in TES, und HR trägt direkt zur
        # Erwärmung/Aufladung von TES bei
        # außerdem TES kann nicht gleichzeitig aufgeladen und entladen werden

        # #Restriktionen

        # #Wärmepumpe

        # #minimaler heat Flow von WP
        block.hp_lower_bound_rule = pyo.Constraint(
            rule=(
                self.heat_pump.min_electric_power_hp * block.y_HP
                <= block.electric_power_hp
            )
        )

        # maximaler Heat flow von WP
        block.hp_upper_bound = pyo.Constraint(
            rule=(
                block.electric_power_hp
                <= block.electric_power_hp.bounds[1] * block.y_HP
            )
        )

        # Heizstab

        # minimaler heat Flow von HS

        # minimaler heat Flow von HS
        block.hr_lower_bound_rule = pyo.Constraint(
            rule=(
                self.heat_pump.min_electric_power_hr * block.y_HR
                <= block.electric_power_hr
            )
        )

        # maximaler heat Flow von HS
        block.HR_upper_bound = pyo.Constraint(
            rule=(
                block.electric_power_hr
                <= self.heat_pump.max_electric_power_hr * block.y_HR
            )
        )

        # COP Berechnung

        # wenn TES aufgeladen wird, Temperatur von WP = MAX_TEMP_HP
        # wenn TES nicht aufgeladen wird, dann Temperatur von
        # WP = TEMP_SUPPLY_DEMAND
        def cop_rule1(block: pyo.Block) -> pyo.Expression:
            """
            Set cop to high if heating TES.

            Sets the COP of the heat pump to the high temperature COP if the
            heat pump is heating the TES. In this case, the heat pump needs to
            reach the maximum output temperature of the heat pump to feed the
            TES.

            Parameters
            ----------
            block : pyo.Block
                The Pyomo block containing the heat pump parameters and
                variables.

            Returns
            -------
            pyo.Expression
                An expression representing the COP constraint for this
                period.
            """
            if (
                interpolate_heat_energy(
                    self.heat_pump.warm_water_demand, period
                )
                > 0
            ):
                return block.cop_value == block.cop_high
            return (block.cop_value - block.cop_high) * block.y_TES == 0

        block.cop_cons1 = pyo.Constraint(rule=cop_rule1)

        def cop_rule3(block: pyo.Block) -> pyo.Expression:
            """
            Set cop to low if not heating TES.

            Sets the COP of the heat pump to the low temperature COP if the
            heat pump is not heating the TES. We only need to reach flow
            temperature for the demand side in this case.

            Parameters
            ----------
            block : pyo.Block
                The Pyomo block containing the heat pump parameters and
                variables.

            Returns
            -------
            pyo.Expression
                An expression representing the COP constraint for this
                period.
            """
            if (
                interpolate_heat_energy(
                    self.heat_pump.warm_water_demand, period
                )
                > 0
            ):
                return pyo.Constraint.Skip
            return (block.cop_value - block.cop_low) * (1 - block.y_TES) == 0

        block.cop_cons3 = pyo.Constraint(rule=cop_rule3)

        # Wärmeströme

        # Wärmeströme WP

        # Funktion setzt möglichen Wärmestrom von WP
        block.heat_supply_hp_total_cons = pyo.Constraint(
            rule=(
                block.heat_supply_hp_total
                == block.electric_power_hp * block.cop_value
            )
        )

        block.heat_flow_HP = pyo.Constraint(
            rule=(
                block.heat_supply_hp_total
                == block.heat_supply_hp_to_demand + block.heat_supply_hp_to_tes
            )
        )

        # möglicher Wärmestrom Heizstab
        block.heat_flow_HR = pyo.Constraint(
            rule=(block.heat_supply_HR == block.electric_power_hr)
        )

        # Restriktionen, die verhindern, das TES gleichzeitig beladen von WP und entladen wird,
        # also es kann kein Strom aus TES und gleichzeitig hinein fließen
        block.charge_cons = pyo.Constraint(
            rule=(
                block.y_TES * self.heat_pump.max_heat_supply_hp
                >= block.heat_supply_hp_to_tes
            )
        )

        block.charge_MIND_cons = pyo.Constraint(
            rule=(
                block.y_TES * self.heat_pump.min_electric_power_hp
                <= block.heat_supply_hp_to_tes
            )
        )

        block.discharge_cons = pyo.Constraint(
            rule=(
                block.heat_supply_TES_Demand
                <= (1 - block.y_TES) * self.heat_pump.max_heat_supply_hp
            )
        )

        block.hp_on_charge_cons = pyo.Constraint(
            rule=(block.y_TES <= block.y_HP)
        )

        # Wärmestrom Demand

        def heat_supply_Demand_total_rule(block: pyo.Block) -> pyo.Expression:
            """
            Total building heat demand.

            Sets the total heat demand in kW of the building for this
            period.
            If a heat demand is provided for the last period, a warning is
            logged and the demand is set to zero to ensure the optimization
            remains feasible.

            Parameters
            ----------
            block : pyo.Block
                The Pyomo block containing the building parameters and
                variables.

            Returns
            -------
            pyo.Expression
                An expression representing the total heat demand for this
                period.
            """
            # Estimate heat demand based on the building's U-values
            heat_supply_demand = (
                block.heat_loss_building + block.warm_water_demand
            )

            # Check that last period has no demand
            if block.index() == self.index.last() and heat_supply_demand > 0:
                log.warning(
                    (
                        "Last period has heat demand! Provided heat demand: "
                        "%s The optimization will continue with no heat "
                        "demand in the last period (%s)."
                    ),
                    (
                        self.heat_pump.heat_demand[period]
                        if period in self.heat_pump.heat_demand
                        else "N/A"
                    ),
                    period,
                )
                return block.heat_supply_demand == 0
            return block.heat_supply_demand == heat_supply_demand

        block.heat_supply_demand_total_cons = pyo.Constraint(
            rule=heat_supply_Demand_total_rule,
            doc=(
                "Sets the total heat demand in kW of the building for this "
                "period. "
                "If a known heat demand is given, it is used. Otherwise, the "
                "heat demand is estimated based on the building's U-values "
                "and the outdoor temperature."
            ),
        )

        # Aufteilung Heizbedarf
        block.heat_flows_TES_hp_Demand = pyo.Constraint(
            rule=(
                block.heat_supply_demand
                == block.heat_supply_hp_to_demand
                + block.heat_supply_TES_Demand
            )
        )

        # obere Schranke
        # Maximum possible energy that can be supplied by the heat pump,
        # electric heater and TES
        # TODO Convert HP and HR power to energy over period
        block.heat_supply_demand_ub = pyo.Constraint(
            rule=(
                block.heat_supply_demand
                <= self.heat_pump.max_heat_supply_hp
                + self.heat_pump.max_electric_power_hr
                + (
                    self.heat_pump.max_heat_energy_tes
                    / period_conversion_factor
                )
            )
        )

        # #Wärmespeicher

        # Wärmespeicher muss genügend Energie haben um Wärmestrom in Periode
        # decken zu können
        block.heat_energy_TES_heat_flow_TES = pyo.Constraint(
            rule=(
                block.heat_energy_TES
                >= (block.heat_supply_TES_Demand) * period_conversion_factor
            )
        )

        # setzt TES Temperatur nach Energieinhalt von TES
        block.heat_energy_TES_cons = pyo.Constraint(
            rule=(
                block.temp_TES
                == block.heat_energy_TES
                * 3600  # conversion seconds to hours (J (Ws) -> Wh)
                / (
                    # BUG heat pumps needs a tank volume but should not
                    self.heat_pump.tank_volume
                    * 4.186  # Heat capacity of water in kWh/kgK
                )
                + self.heat_pump.flow_temperature
            )
        )

        # TES Energieinhalt in SOC umwandeln
        block.soc_const = pyo.Constraint(
            rule=(
                block.soc
                == (
                    (block.temp_TES - self.heat_pump.flow_temperature)
                    / (
                        self.heat_pump.max_temp_tes
                        - self.heat_pump.flow_temperature
                    )
                )
            )
        )

        def heat_loss_tank_rule(block: pyo.Block) -> pyo.Expression:
            """
            Calculate the heat loss of the tank.

            Calculates the heat loss for this period of the tank based on its
            relative heat loss [W/K] and the temperature difference between the
            tank and the room temperature.

            Parameters
            ----------
            block : pyo.Block
                The Pyomo block containing the tank parameters and variables.

            Returns
            -------
            pyo.Expression
                An expression representing the tank heat loss for this period.
            """
            return block.heat_loss_tank == (
                self.heat_pump.heat_loss_tank
                / 1000  # Convert W to kW
                * (block.temp_TES - temp_room)
            )

        block.heat_loss_tank_cons = pyo.Constraint(
            rule=heat_loss_tank_rule,
            doc=(
                "Heat loss of the tank in kW for this period. "
                "Estimated based on transmission heat loss."
            ),
        )

        # TES Temperatur soll immer größer gleich Vorlauftemperatur sein
        if period != self.index.first():
            block.temp_TES_cons = pyo.Constraint(
                rule=(block.temp_TES >= self.heat_pump.flow_temperature)
            )

        # #weitere Restriktionen

        # Abschaltpunkt für WP
        if self.heat_pump.hp_switch_off_temperature is not None:
            block.hp_switch_off_temperature = pyo.Constraint(
                rule=(
                    (
                        block.outdoor_temperature
                        - self.heat_pump.hp_switch_off_temperature
                    )
                    * block.y_HP
                    >= 0
                )
            )

        if self.heat_pump.bivalent_temp is not None:
            if self.heat_pump.bivalent_temp >= block.outdoor_temperature:
                block.bivalent_temp = pyo.Constraint(
                    rule=(
                        (
                            block.heat_supply_hp_total
                            <= (block.heat_loss_building) * 0.7
                        )
                    )
                )

        # Force SoC to be the same at start and end of optimization
        if self.heat_pump.enforce_end_soc:
            if period == self.index.last():
                block.soc_end = pyo.Constraint(
                    rule=(block.soc == self.heat_pump.tes_start_soc)
                )

        # #Wärmestrom Demand

        # #Restriktion, die sicherstellt, dass immer genügend Wärmeenergie
        # erzeugt wieder pro Periode
        # def heat_flows_TES_hp_Demand_rule2(block):
        #     return block.heat_supply_Demand + block.heat_loss_tank <=
        #     block.heat_supply_hp_to_demand + block.heat_supply_hp_to_tes +
        #     block.heat_supply_HR + block.heat_energy_TES/TIME_RESOLUTION
        #     #* (1-block.y_TES)
        # block.heat_flows_TES_HP_Demand2 = pyo.Constraint(
        #   rule=heat_flows_TES_HP_Demand_rule2
        # )

        # #Wärmespeicher

        # #Wärmespeicher muss genügend Energie haben um Wärmestrom in Periode
        # decken zu können
        # def heat_energy_TES_heat_flow_TES_rule(block):
        #     return block.heat_energy_TES + (
        #       block.heat_supply_HR + block.heat_supply_hp_to_tes
        #     ) * TIME_RESOLUTION  >= (
        #       block.heat_supply_TES_Demand + block.heat_loss_tank
        #     ) * TIME_RESOLUTION
        # block.heat_energy_TES_heat_flow_TES = pyo.Constraint(
        #   rule=heat_energy_TES_heat_flow_TES_rule
        # )

        # heat_energy_TES_linkin_rule
        if period == self.index.first():
            block.start_soc = pyo.Constraint(
                rule=(block.soc == self.heat_pump.tes_start_soc)
            )
        else:
            previous_block = block.parent_component()[self.index.prev(period)]

            # y_tes_over_hp_temp constraints
            block.y_tes_over_hp_temp_c1 = pyo.Constraint(
                expr=(
                    block.temp_TES
                    >= self.heat_pump.output_temperature
                    - self.heat_pump.output_temperature
                    * (1 - block.y_tes_over_hp_temp)
                ),
                doc=(
                    "TES temperature must be over the heat pumps output "
                    "temperature when y_tes_over_hp_temp is 1"
                ),
            )
            block.y_tes_over_hp_temp_c2 = pyo.Constraint(
                expr=(
                    block.temp_TES
                    <= self.heat_pump.output_temperature
                    + (
                        self.heat_pump.max_temp_tes
                        - self.heat_pump.output_temperature
                    )
                    * block.y_tes_over_hp_temp
                ),
                doc=(
                    "TES temperature must be at or below the heat pump's "
                    "output temperature if y_tes_over_hp_temp is 0."
                ),
            )

            block.tes_temperature_below_hp_output = pyo.Constraint(
                expr=(previous_block.y_TES + block.y_tes_over_hp_temp <= 1),
                doc=(
                    "The TES temperature must be at or below the heat "
                    "pumps output temperature in any period **following a "
                    "charging** of the TES by the heat pump. The TES "
                    "temperature can not exceed the heat pump output "
                    "temperature with out being charged by the heating "
                    "element."
                ),
            )

            # y_delta_tes_over_value constraints
            # block.cons4 = pyo.Constraint(
            #     expr=(
            #         block.temp_TES
            #         >= self.heat_pump.output_temperature
            #         - self.heat_pump.output_temperature
            #         * (1 - block.y_delta_tes_over_value)
            #     ),
            #     doc=(
            #         "TES temperature must be over the heat pumps output "
            #         "temperature when y_delta_tes_over_value is 1"
            #     ),
            # )
            # block.cons5 = pyo.Constraint(
            #     expr=(
            #         block.temp_TES
            #         <= self.heat_pump.output_temperature
            #         + (
            #           self.heat_pump.max_temp_tes
            #           - self.heat_pump.output_temperature
            #         )
            #         * block.y_delta_tes_over_value
            #     ),
            #     doc=(
            #         "TES temperature must be at or below the heat pump's "
            #         "output temperature if y_delta_tes_over_value is 0."
            #     ),
            # )

            block.cons6 = pyo.Constraint(
                expr=(block.y_TES + block.y_tes_over_hp_temp <= 1),
                doc=(
                    "The TES temperature must be at or below the heat "
                    "pumps output temperature in **any period the TES is "
                    "charged** by the heat pump. The TES "
                    "temperature can not exceed the heat pump output "
                    "temperature with out being charged by the heating "
                    "element."
                ),
            )

            block.heat_energy_tes_link_rule = pyo.Constraint(
                rule=(
                    block.heat_energy_TES
                    == previous_block.heat_energy_TES
                    + (
                        previous_block.heat_supply_hp_to_tes
                        + previous_block.heat_supply_HR
                        - previous_block.heat_supply_TES_Demand
                        - previous_block.heat_loss_tank
                    )
                    * period_conversion_factor
                )
            )
