import pyomo.environ as pyo
import hplib.hplib as hpl
from battery_optimizer.helpers.heat_pump_profile import (
    convert_list,
    get_period_length,
    heat_loss_building,
    heat_loss_tank,
    warm_water_heat_flow,
)
from battery_optimizer.profiles.heat_pump import HeatPump
import logging

from battery_optimizer.static.heat_pump import (
    C_TO_K,
    TES_BLOCK_TEMP_WITH_WARM_WATER_DEMAND,
)
from battery_optimizer.static.numbers import MAX_COP

log = logging.getLogger(__name__)


def heat_pump_block_rule(
    block: pyo.Block, heat_pump: HeatPump, model: pyo.ConcreteModel
):
    """
    Gestaltung einer Periode im Modell
    """

    period = block.index()

    period_length, period_conversion_factor = get_period_length(
        period, model.i
    )

    # HPL Heat Pump
    if heat_pump.type == "Luft/Luft" or heat_pump.type == "Air/Air":
        log.warning("L/L-WP")
    elif heat_pump.type == "Generic":
        parameters = hpl.get_parameters(
            model=heat_pump.type,
            group_id=heat_pump.id,
            t_in=heat_pump.t_in,
            t_out=heat_pump.t_out,
            p_th=heat_pump.p_th,
        )
        hpl_heat_pump = hpl.HeatPump(parameters)
    else:
        parameters = hpl.get_parameters(model=heat_pump.type)
        hpl_heat_pump = hpl.HeatPump(parameters)

    # Parameter

    # Außentemperatur der aktuellen Periode
    def temp_outdoor_profile_rule(block):
        return heat_pump.outdoor_temperature[period]

    block.outdoor_temperature = pyo.Param(rule=temp_outdoor_profile_rule)

    # setzt Wärmebedarf für warmwassererzeugung
    def warm_water_demand_rule(block):
        if period in convert_list(heat_pump.warm_water_periods, model.i):
            heat_flow = warm_water_heat_flow(
                heat_pump.surface_building,
                heat_pump.warm_water_periods,
                start=period,
                end=(
                    model.i.next(period)
                    if period != model.i.last()
                    else period
                ),
            )
            log.debug(
                f"Period {period} is a warm water period. "
                f"Thermal energy for warm drinking water: {heat_flow} kWh."
            )
            return heat_flow
        else:
            return 0.0

    block.warm_water_demand = pyo.Param(
        rule=warm_water_demand_rule,
        doc=(
            "Estimated warm water demand in kWh for this period based on the "
            "building's living area. Warm water usage is distributed equally "
            "across the warm water periods"
        ),
    )

    # Funktion für Wärmeverlust durch Gebäudehülle, in Abhängigkeit der Außentemperatur
    def heat_loss_building_rule(block):
        heat_loss = heat_loss_building(
            heat_pump.u_values_building.model_dump(),
            pyo.value(block.outdoor_temperature),
            heat_pump.temp_room - C_TO_K,
        )
        return heat_loss * period_conversion_factor

    block.heat_loss_building = pyo.Param(
        rule=heat_loss_building_rule,
        doc="Building heat loss in kWh for this period",
    )

    # Quellentemperatur der aktuellen Periode, nicht verwendet
    def source_temp_rule(block):
        return heat_pump.heat_source_temperature[period]

    block.source_temp = pyo.Param(rule=source_temp_rule)

    # Variablen

    # Binary
    block.y_HR = pyo.Var(within=pyo.Binary)
    block.y_HP = pyo.Var(within=pyo.Binary)
    block.y_TES = pyo.Var(within=pyo.Binary)

    # electric power
    block.electric_energy_HR = pyo.Var(
        bounds=(
            heat_pump.min_electric_consumption_hr,
            heat_pump.max_electric_consumption_hr,
        )
    )
    block.electric_energy_HP = pyo.Var(
        bounds=(
            heat_pump.min_electric_consumption_hp,
            heat_pump.max_electric_consumption_hp,
        )
    )

    # heat flows
    block.heat_supply_HP = pyo.Var(
        bounds=(heat_pump.min_heat_supply_hp, heat_pump.max_heat_supply_hp)
    )
    block.heat_supply_hp_demand = pyo.Var(
        bounds=(heat_pump.min_heat_supply_hp, heat_pump.max_heat_supply_hp)
    )
    block.heat_supply_hp_tes = pyo.Var(
        bounds=(heat_pump.min_heat_supply_hp, heat_pump.max_heat_supply_hp)
    )

    block.heat_supply_HR = pyo.Var(
        bounds=(
            heat_pump.min_electric_consumption_hr,
            heat_pump.max_electric_consumption_hr,
        )
    )

    block.heat_supply_TES_Demand = pyo.Var(
        bounds=(heat_pump.min_heat_supply_hp, heat_pump.max_heat_supply_tes)
    )

    block.heat_supply_demand = pyo.Var(domain=pyo.NonNegativeReals)

    # Temp
    # TODO If room temperature changes, this must be dynamic
    block.temp_TES = pyo.Var(
        bounds=(heat_pump.temp_room, heat_pump.max_temp_tes)
    )

    # Tank
    block.heat_energy_TES = pyo.Var(
        bounds=(heat_pump.min_heat_energy_tes, heat_pump.max_heat_energy_tes)
    )
    block.soc = pyo.Var(bounds=(0, 1))
    block.heat_loss_tank = pyo.Var(domain=pyo.NonNegativeReals)

    block.y_tes_over_value = pyo.Var(within=pyo.Binary)
    block.y_delta_tes_over_value = pyo.Var(within=pyo.Binary)

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
            heat_pump.mind_electric_consumption_hp * block.y_HP
            <= block.electric_energy_HP
        )

    block.hp_lower_bound_rule = pyo.Constraint(rule=hp_lower_bound_rule)

    # maximaler Heat flow von WP
    def hp_upper_bound_rule(block):
        return (
            block.electric_energy_HP
            <= heat_pump.max_electric_consumption_hp * block.y_HP
        )

    block.hp_upper_bound = pyo.Constraint(rule=hp_upper_bound_rule)

    # Heizstab

    # minimaler heat Flow von HS

    # minimaler heat Flow von HS
    def hr_lower_bound_rule(block):
        return (
            heat_pump.mind_electric_consumption_hr * block.y_HR
            <= block.electric_energy_HR
        )

    block.hr_lower_bound_rule = pyo.Constraint(rule=hr_lower_bound_rule)

    # maximaler heat Flow von HS
    def HR_upper_bound_rule(block):
        return (
            block.electric_energy_HR
            <= heat_pump.max_electric_consumption_hr * block.y_HR
        )

    block.HR_upper_bound = pyo.Constraint(rule=HR_upper_bound_rule)

    # COP Berechnung

    # wenn TES aufgeladen wird, Temperatur von WP = MAX_TEMP_HP
    # wenn TES nicht aufgeladen wird, dann Temperatur von WP = TEMP_SUPPLY_DEMAND
    def cop_rule1(block):
        if period in convert_list(heat_pump.warm_water_periods, model.i):
            results = hpl_heat_pump.simulate(
                t_in_primary=(block.source_temp - C_TO_K),
                t_in_secondary=((heat_pump.max_temp_hp - 5) - C_TO_K),
                t_amb=(block.outdoor_temperature - C_TO_K),
                mode=1,
            )
            return block.cop_value == results["COP"]
        if heat_pump.type == "Luft/Luft" or heat_pump.type == "Air/Air":
            return block.cop_value == heat_pump.cop_air
        else:
            results = hpl_heat_pump.simulate(
                t_in_primary=(block.source_temp - C_TO_K),
                t_in_secondary=((heat_pump.max_temp_hp - 5) - C_TO_K),
                t_amb=(block.outdoor_temperature - C_TO_K),
                mode=1,
            )
            return (block.cop_value - results["COP"]) * block.y_TES == 0

    block.cop_cons1 = pyo.Constraint(rule=cop_rule1)

    def cop_rule3(block):
        if period in convert_list(heat_pump.warm_water_periods, model.i):
            return pyo.Constraint.Skip
        if heat_pump.type == "Luft/Luft" or heat_pump.type == "Air/Air":
            return block.cop_value == heat_pump.cop_air
        else:
            results = hpl_heat_pump.simulate(
                t_in_primary=(block.source_temp - C_TO_K),
                t_in_secondary=((heat_pump.temp_supply_demand - 5) - C_TO_K),
                t_amb=(block.outdoor_temperature - C_TO_K),
                mode=1,
            )
            return (block.cop_value - results["COP"]) * (1 - block.y_TES) == 0

    block.cop_cons3 = pyo.Constraint(rule=cop_rule3)

    # Wärmeströme

    # Wärmeströme WP

    # Funktion setzt möglichen Wärmestrom von WP
    def heat_supply_HP_rule(block):
        return (
            block.heat_supply_HP == block.electric_energy_HP * block.cop_value
        )

    block.heat_supply_HP_cons = pyo.Constraint(rule=heat_supply_HP_rule)

    def heat_flow_HP_rule(block):
        return (
            block.heat_supply_HP
            == block.heat_supply_hp_demand + block.heat_supply_hp_tes
        )

    block.heat_flow_HP = pyo.Constraint(rule=heat_flow_HP_rule)

    # möglicher Wärmestrom Heizstab
    def heat_flow_HR_rule(block):
        return block.heat_supply_HR == block.electric_energy_HR

    block.heat_flow_HR = pyo.Constraint(rule=heat_flow_HR_rule)

    # Restriktionen, die verhindern, das TES gleichzeitig beladen von WP und entladen wird,
    # also es kann kein Strom aus TES und gleichzeitig hinein fließen
    def hp_charge_rule(block):
        return (
            block.y_TES * heat_pump.max_heat_supply_hp
            >= block.heat_supply_hp_tes
        )

    block.charge_cons = pyo.Constraint(rule=hp_charge_rule)

    def hp_charge_MIND_rule(block):
        return (
            block.y_TES * (heat_pump.mind_heat_supply_hp)
            <= block.heat_supply_hp_tes
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
        if block.index() == model.i.last():
            if block.heat_loss_building + block.warm_water_demand > 0:
                log.warning(
                    "Last period has heat loss and warm water demand! "
                    "The optimization will continue with no heat loss and "
                    f"warm water demand in the last period ({period})."
                    f" The heat loss is {block.heat_loss_building.value} and "
                    f"the warm water demand is {block.warm_water_demand.value}."
                )
            return block.heat_supply_demand == 0
        else:
            return block.heat_supply_demand == (
                block.heat_loss_building + block.warm_water_demand
            )

    block.heat_supply_demand_total_cons = pyo.Constraint(
        rule=heat_supply_Demand_total_rule
    )

    # Aufteilung Heizbedarf
    def heat_flows_TES_hp_Demand_rule(block):
        return (
            block.heat_supply_demand
            == block.heat_supply_hp_demand + block.heat_supply_TES_Demand
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
            + heat_pump.max_electric_consumption_hr
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
            * 3600
            / (heat_pump.tank_mass * heat_pump.cp)
            + heat_pump.temp_supply_demand
        )

    block.heat_energy_TES_cons = pyo.Constraint(rule=heat_energy_TES_rule)

    # TES Energieinhalt in SOC umwandeln
    def soc_rule(block):
        return block.soc == (
            (block.temp_TES - heat_pump.temp_supply_demand)
            / (heat_pump.max_temp_tes - heat_pump.temp_supply_demand)
        )

    block.soc_const = pyo.Constraint(rule=soc_rule)

    # #Energieverlust von Tank
    def heat_loss_tank_rule(block):
        return block.heat_loss_tank == heat_loss_tank(
            heat_pump.tank_height,
            heat_pump.tank_radius_o,
            heat_pump.tank_u_value,
            (block.temp_TES - heat_pump.temp_room),
        )

    block.heat_loss_tank_cons = pyo.Constraint(rule=heat_loss_tank_rule)

    # TES Temperatur soll immer größer gleich Vorlauftemperatur sein
    def temp_TES_rule(block):
        if period == model.i.first():
            return pyo.Constraint.Skip

        return block.temp_TES >= heat_pump.temp_supply_demand

    block.temp_TES_cons = pyo.Constraint(rule=temp_TES_rule)

    # obere Schranke für Tankverluste
    def heat_loss_tank_ub_rule(block):
        return block.heat_loss_tank <= heat_loss_tank(
            heat_pump.tank_height,
            heat_pump.tank_radius_o,
            heat_pump.tank_u_value,
            (heat_pump.max_temp_tes - heat_pump.temp_room),
        )

    block.heat_loss_tank_ub = pyo.Constraint(rule=heat_loss_tank_ub_rule)

    # #weitere Restriktionen

    # Abschaltpunkt für WP
    def temp_hp_out_rule(block):
        if heat_pump.temp_hp_out is not None:
            return (
                block.outdoor_temperature - heat_pump.temp_hp_out
            ) * block.y_HP >= 0
        else:
            return pyo.Constraint.Skip

    block.temp_hp_out = pyo.Constraint(rule=temp_hp_out_rule)

    def bivalent_temp_rule(block):
        if heat_pump.bivalent_temp is not None:
            if heat_pump.bivalent_temp >= block.outdoor_temperature:
                return block.heat_supply_HP <= (block.heat_demand) * 0.7
        return pyo.Constraint.Skip

    block.bivalent_temp = pyo.Constraint(rule=bivalent_temp_rule)

    # #Einführung von Notfallreserve, TES soll Restenergie haben, in bestimmten Perioden
    # #könnte man auch außerhalb von block machen
    # #Funktion so geschrieben, dass zu einer bestimmten Periode eine Notfallreserve im Speicher ist,
    # #welche dann in nächster Periode zur Verfügung steht
    def min_tes_heat_energy_rule(block):
        if period in convert_list(heat_pump.tank_rest_hours, model.i):
            return block.soc >= heat_pump.tank_rest
        else:
            return pyo.Constraint.Skip

    block.min_tes_heat_energy_const = pyo.Constraint(
        rule=min_tes_heat_energy_rule
    )

    # Restriktion, die TES auf mind. 50°C aufheizt für die Sperrzeiten, falls es WW Bedarf gibt
    def ww_during_blocking_hours_rule(block):
        if heat_pump.warm_water_periods:
            if period in convert_list(
                heat_pump.blocking_hours, model.i
            ) and period in convert_list(
                heat_pump.warm_water_periods, model.i
            ):
                return block.temp_TES >= TES_BLOCK_TEMP_WITH_WARM_WATER_DEMAND
        return pyo.Constraint.Skip

    block.ww_during_blocking_hours = pyo.Constraint(
        rule=ww_during_blocking_hours_rule
    )

    # #Wärmestrom Demand

    # #Restriktion, die sicherstellt, dass immer genügend Wärmeenergie erzeugt wieder pro Periode
    # def heat_flows_TES_hp_Demand_rule2(block):
    #     return block.heat_supply_Demand + block.heat_loss_tank <= block.heat_supply_hp_demand + block.heat_supply_hp_tes + block.heat_supply_HR + block.heat_energy_TES/TIME_RESOLUTION #* (1-block.y_TES)
    # block.heat_flows_TES_HP_Demand2 = pyo.Constraint(rule=heat_flows_TES_HP_Demand_rule2)

    # #Wärmespeicher

    # #Wärmespeicher muss genügend Energie haben um Wärmestrom in Periode decken zu können
    # def heat_energy_TES_heat_flow_TES_rule(block):
    #     return block.heat_energy_TES + (block.heat_supply_HR + block.heat_supply_hp_tes) * TIME_RESOLUTION  >= (block.heat_supply_TES_Demand + block.heat_loss_tank) * TIME_RESOLUTION
    # block.heat_energy_TES_heat_flow_TES = pyo.Constraint(rule=heat_energy_TES_heat_flow_TES_rule)
