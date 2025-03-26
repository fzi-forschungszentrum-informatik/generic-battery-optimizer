import pyomo.environ as pyo
import hplib.hplib as hpl
from battery_optimizer.helpers.heat_pump_profile import (
    get_period_length,
    heat_loss_tank,
    interpolate_temperature,
    interpolate_heat_energy,
)
from battery_optimizer.profiles.heat_pump import HeatPump
import logging

from battery_optimizer.static.heat_pump import C_TO_K
from battery_optimizer.static.numbers import MAX_COP

log = logging.getLogger(__name__)


def heat_pump_block_rule(
    block: pyo.Block,
    heat_pump: HeatPump,
    model: pyo.ConcreteModel,
    hpl_heat_pump: hpl.HeatPump,
):
    """
    Gestaltung einer Periode im Modell
    """

    period = block.index()

    period_length, period_conversion_factor = get_period_length(
        period, model.i
    )

    temp_room = interpolate_temperature(heat_pump.temp_room, period)

    # Parameters
    block.outdoor_temperature = pyo.Param(
        initialize=interpolate_temperature(
            heat_pump.outdoor_temperature, period
        ),
        within=pyo.NonNegativeReals,
    )

    block.warm_water_demand = pyo.Param(
        initialize=interpolate_heat_energy(
            heat_pump.warm_water_demand, period
        ),
        within=pyo.NonNegativeReals,
        doc="Warm water demand in kW for this period.",
    )

    block.heat_loss_building = pyo.Param(
        initialize=interpolate_heat_energy(heat_pump.heat_demand, period),
        within=pyo.NonNegativeReals,
        doc="Building heat loss/demand in kW for this period.",
    )

    block.source_temp = pyo.Param(
        initialize=interpolate_temperature(
            heat_pump.heat_source_temperature, period
        ),
        within=pyo.NonNegativeReals,
        doc=(
            "Temperature of heat source in K. e.g. outdoor air, ground water "
            "or soil temperature."
        ),
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
            heat_pump.max_electric_power_hr,
        ),
        doc=(
            "Electric energy consumption of the electric heater in kW during "
            "this period"
        ),
    )
    block.electric_power_hp = pyo.Var(
        bounds=(
            0,
            heat_pump.max_electric_power_hp,
        ),
        doc=(
            "Electric energy consumption of the heat pump in kW during this "
            "period"
        ),
    )

    # heat flows
    block.heat_supply_hp_total = pyo.Var(
        bounds=(
            0,
            heat_pump.max_heat_supply_hp,
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
            heat_pump.max_heat_supply_hp,
        ),
        doc=(
            "The heat energy the heat pump supplies to the demand side in kW "
            "during this period"
        ),
    )
    block.heat_supply_hp_to_tes = pyo.Var(
        bounds=(
            0,
            heat_pump.max_heat_supply_hp,
        ),
        doc=(
            "The heat energy the heat pump supplies to the TES in kW during "
            "this period"
        ),
    )

    block.heat_supply_HR = pyo.Var(
        bounds=(
            0,
            heat_pump.max_electric_power_hr,
        )
    )

    block.heat_supply_TES_Demand = pyo.Var(
        bounds=(
            0,
            heat_pump.max_heat_supply_tes,
        )
    )

    block.heat_supply_demand = pyo.Var(domain=pyo.NonNegativeReals)

    # Temp
    block.temp_TES = pyo.Var(bounds=(temp_room, heat_pump.max_temp_tes))

    # Tank
    block.heat_energy_TES = pyo.Var(
        bounds=(0, heat_pump.max_heat_energy_tes),
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

    block.cop_value = pyo.Var(domain=pyo.NonNegativeReals, bounds=(0, MAX_COP))

    """
        in diesem modell HR in TES, und HR trägt direkt zur Erwärmung/Aufladung von TES bei
        außerdem TES kann nicht gleichzeitig aufgeladen und entladen werden
    """
    # #Restriktionen

    # #Wärmepumpe

    # #minimaler heat Flow von WP
    def hp_lower_bound_rule(block):
        return (
            heat_pump.min_electric_power_hp * block.y_HP
            <= block.electric_power_hp
        )

    block.hp_lower_bound_rule = pyo.Constraint(rule=hp_lower_bound_rule)

    # maximaler Heat flow von WP
    def hp_upper_bound_rule(block):
        return (
            block.electric_power_hp
            <= block.electric_power_hp.bounds[1] * block.y_HP
        )

    block.hp_upper_bound = pyo.Constraint(rule=hp_upper_bound_rule)

    # Heizstab

    # minimaler heat Flow von HS

    # minimaler heat Flow von HS
    def hr_lower_bound_rule(block):
        return (
            heat_pump.min_electric_power_hr * block.y_HR
            <= block.electric_power_hr
        )

    block.hr_lower_bound_rule = pyo.Constraint(rule=hr_lower_bound_rule)

    # maximaler heat Flow von HS
    def HR_upper_bound_rule(block):
        return (
            block.electric_power_hr
            <= heat_pump.max_electric_power_hr * block.y_HR
        )

    block.HR_upper_bound = pyo.Constraint(rule=HR_upper_bound_rule)

    # COP Berechnung

    # wenn TES aufgeladen wird, Temperatur von WP = MAX_TEMP_HP
    # wenn TES nicht aufgeladen wird, dann Temperatur von WP = TEMP_SUPPLY_DEMAND
    def cop_rule1(block):
        if interpolate_heat_energy(heat_pump.warm_water_demand, period) > 0:
            results = hpl_heat_pump.simulate(
                t_in_primary=(block.source_temp - C_TO_K),
                t_in_secondary=((heat_pump.output_temperature - 5) - C_TO_K),
                t_amb=(block.outdoor_temperature - C_TO_K),
                mode=1,
            )
            return block.cop_value == results["COP"]
        if heat_pump.type == "Luft/Luft" or heat_pump.type == "Air/Air":
            return block.cop_value == heat_pump.cop_air
        else:
            results = hpl_heat_pump.simulate(
                t_in_primary=(block.source_temp - C_TO_K),
                t_in_secondary=((heat_pump.output_temperature - 5) - C_TO_K),
                t_amb=(block.outdoor_temperature - C_TO_K),
                mode=1,
            )
            return (block.cop_value - results["COP"]) * block.y_TES == 0

    block.cop_cons1 = pyo.Constraint(rule=cop_rule1)

    def cop_rule3(block):
        if interpolate_heat_energy(heat_pump.warm_water_demand, period) > 0:
            return pyo.Constraint.Skip
        if heat_pump.type == "Luft/Luft" or heat_pump.type == "Air/Air":
            return block.cop_value == heat_pump.cop_air
        else:
            results = hpl_heat_pump.simulate(
                t_in_primary=(block.source_temp - C_TO_K),
                t_in_secondary=((heat_pump.flow_temperature - 5) - C_TO_K),
                t_amb=(block.outdoor_temperature - C_TO_K),
                mode=1,
            )
            return (block.cop_value - results["COP"]) * (1 - block.y_TES) == 0

    block.cop_cons3 = pyo.Constraint(rule=cop_rule3)

    # Wärmeströme

    # Wärmeströme WP

    # Funktion setzt möglichen Wärmestrom von WP
    def heat_supply_hp_total_rule(block):
        return (
            block.heat_supply_hp_total
            == block.electric_power_hp * block.cop_value
        )

    block.heat_supply_hp_total_cons = pyo.Constraint(
        rule=heat_supply_hp_total_rule
    )

    def heat_flow_HP_rule(block):
        return (
            block.heat_supply_hp_total
            == block.heat_supply_hp_to_demand + block.heat_supply_hp_to_tes
        )

    block.heat_flow_HP = pyo.Constraint(rule=heat_flow_HP_rule)

    # möglicher Wärmestrom Heizstab
    def heat_flow_HR_rule(block):
        return block.heat_supply_HR == block.electric_power_hr

    block.heat_flow_HR = pyo.Constraint(rule=heat_flow_HR_rule)

    # Restriktionen, die verhindern, das TES gleichzeitig beladen von WP und entladen wird,
    # also es kann kein Strom aus TES und gleichzeitig hinein fließen
    def hp_charge_rule(block):
        return (
            block.y_TES * heat_pump.max_heat_supply_hp
            >= block.heat_supply_hp_to_tes
        )

    block.charge_cons = pyo.Constraint(rule=hp_charge_rule)

    def hp_charge_MIND_rule(block):
        return (
            block.y_TES * heat_pump.min_electric_power_hp
            <= block.heat_supply_hp_to_tes
        )

    block.charge_MIND_cons = pyo.Constraint(rule=hp_charge_MIND_rule)

    def hp_discharge_rule(block):
        return (
            block.heat_supply_TES_Demand
            <= (1 - block.y_TES) * heat_pump.max_heat_supply_hp
        )

    block.discharge_cons = pyo.Constraint(rule=hp_discharge_rule)

    def hp_on_charge_rule(block):
        return block.y_TES <= block.y_HP

    block.hp_on_charge_cons = pyo.Constraint(rule=hp_on_charge_rule)

    # Wärmestrom Demand

    # Heizbedarf gesamt
    def heat_supply_Demand_total_rule(block):
        # Estimate heat demand based on the building's U-values
        heat_supply_demand = block.heat_loss_building + block.warm_water_demand

        # Check that last period has no demand
        if block.index() == model.i.last() and heat_supply_demand > 0:
            log.warning(
                "Last period has heat demand! "
                f"Provided heat demand: {heat_pump.heat_demand[period]} "
                "The optimization will continue with no heat demand in "
                f"the last period ({period})."
            )
            return block.heat_supply_demand == 0
        return block.heat_supply_demand == heat_supply_demand

    block.heat_supply_demand_total_cons = pyo.Constraint(
        rule=heat_supply_Demand_total_rule,
        doc=(
            "Sets the total heat demand in kW of the building for this "
            "period. "
            "If a known heat demand is given, it is used. Otherwise, the heat "
            "demand is estimated based on the building's U-values and the "
            "outdoor temperature"
        ),
    )

    # Aufteilung Heizbedarf
    def heat_flows_TES_hp_Demand_rule(block):
        return (
            block.heat_supply_demand
            == block.heat_supply_hp_to_demand + block.heat_supply_TES_Demand
        )

    block.heat_flows_TES_hp_Demand = pyo.Constraint(
        rule=heat_flows_TES_hp_Demand_rule
    )

    # obere Schranke
    # Maximum possible energy that can be supplied by the heat pump, electric
    # heater and TES
    # TODO Convert HP and HR power to energy over period
    def heat_supply_demand_ub_rule(block):
        return (
            block.heat_supply_demand
            <= heat_pump.max_heat_supply_hp
            + heat_pump.max_electric_power_hr
            + (heat_pump.max_heat_energy_tes / period_conversion_factor)
        )

    block.heat_supply_demand_ub = pyo.Constraint(
        rule=heat_supply_demand_ub_rule
    )

    # #Wärmespeicher

    # Wärmespeicher muss genügend Energie haben um Wärmestrom in Periode decken zu können
    def heat_energy_TES_heat_flow_TES_rule(block):
        return (
            block.heat_energy_TES
            >= (block.heat_supply_TES_Demand) * period_conversion_factor
        )

    block.heat_energy_TES_heat_flow_TES = pyo.Constraint(
        rule=heat_energy_TES_heat_flow_TES_rule
    )

    # setzt TES Temperatur nach Energieinhalt von TES
    def heat_energy_TES_rule(block):
        return (
            block.temp_TES
            == block.heat_energy_TES
            * 3600  # conversion seconds to hours (J (Ws) -> Wh)
            / (
                heat_pump.tank_volume
                * 4.186  # Heat capacity of water in kWh/kgK
            )
            + heat_pump.flow_temperature
        )

    block.heat_energy_TES_cons = pyo.Constraint(rule=heat_energy_TES_rule)

    # TES Energieinhalt in SOC umwandeln
    def soc_rule(block):
        return block.soc == (
            (block.temp_TES - heat_pump.flow_temperature)
            / (heat_pump.max_temp_tes - heat_pump.flow_temperature)
        )

    block.soc_const = pyo.Constraint(rule=soc_rule)

    # #Energieverlust von Tank
    def heat_loss_tank_rule(block):
        if not heat_pump.predict_tank_loss:
            return block.heat_loss_tank == 0
        return block.heat_loss_tank == heat_loss_tank(
            heat_pump.tank_height,
            heat_pump.tank_radius,
            heat_pump.tank_u_value,
            (block.temp_TES - temp_room),
        )

    block.heat_loss_tank_cons = pyo.Constraint(
        rule=heat_loss_tank_rule,
        doc=(
            "Heat loss of the tank in kW for this period. "
            "Estimated based on transmission heat loss."
        ),
    )

    # TES Temperatur soll immer größer gleich Vorlauftemperatur sein
    def temp_TES_rule(block):
        if period == model.i.first():
            return pyo.Constraint.Skip

        return block.temp_TES >= heat_pump.flow_temperature

    block.temp_TES_cons = pyo.Constraint(rule=temp_TES_rule)

    # obere Schranke für Tankverluste
    def heat_loss_tank_ub_rule(block):
        if not heat_pump.predict_tank_loss:
            return block.heat_loss_tank <= 0
        return block.heat_loss_tank <= heat_loss_tank(
            heat_pump.tank_height,
            heat_pump.tank_radius,
            heat_pump.tank_u_value,
            (heat_pump.max_temp_tes - temp_room),
        )

    block.heat_loss_tank_ub = pyo.Constraint(rule=heat_loss_tank_ub_rule)

    # #weitere Restriktionen

    # Abschaltpunkt für WP
    def hp_switch_off_temperature_rule(block):
        if heat_pump.hp_switch_off_temperature is not None:
            return (
                block.outdoor_temperature - heat_pump.hp_switch_off_temperature
            ) * block.y_HP >= 0
        else:
            return pyo.Constraint.Skip

    block.hp_switch_off_temperature = pyo.Constraint(
        rule=hp_switch_off_temperature_rule
    )

    def bivalent_temp_rule(block):
        if heat_pump.bivalent_temp is not None:
            if heat_pump.bivalent_temp >= block.outdoor_temperature:
                return block.heat_supply_hp_total <= (block.heat_demand) * 0.7
        return pyo.Constraint.Skip

    block.bivalent_temp = pyo.Constraint(rule=bivalent_temp_rule)

    # Force SoC to be the same at start and end of optimization
    def soc_end_rule(block):
        if period == model.i.last():
            return block.soc == heat_pump.tes_start_soc
        return pyo.Constraint.Skip

    if heat_pump.enforce_end_soc:
        block.soc_end = pyo.Constraint(rule=soc_end_rule)

    # #Wärmestrom Demand

    # #Restriktion, die sicherstellt, dass immer genügend Wärmeenergie erzeugt wieder pro Periode
    # def heat_flows_TES_hp_Demand_rule2(block):
    #     return block.heat_supply_Demand + block.heat_loss_tank <= block.heat_supply_hp_to_demand + block.heat_supply_hp_to_tes + block.heat_supply_HR + block.heat_energy_TES/TIME_RESOLUTION #* (1-block.y_TES)
    # block.heat_flows_TES_HP_Demand2 = pyo.Constraint(rule=heat_flows_TES_HP_Demand_rule2)

    # #Wärmespeicher

    # #Wärmespeicher muss genügend Energie haben um Wärmestrom in Periode decken zu können
    # def heat_energy_TES_heat_flow_TES_rule(block):
    #     return block.heat_energy_TES + (block.heat_supply_HR + block.heat_supply_hp_to_tes) * TIME_RESOLUTION  >= (block.heat_supply_TES_Demand + block.heat_loss_tank) * TIME_RESOLUTION
    # block.heat_energy_TES_heat_flow_TES = pyo.Constraint(rule=heat_energy_TES_heat_flow_TES_rule)
