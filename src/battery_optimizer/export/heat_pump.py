import pyomo.environ as pyo
import pandas as pd

from battery_optimizer.static.heat_pump import C_TO_K, TEXT_HEAT_PUMP_BASE


def _get_component_series_from_block(
    block: str, component: str, model: pyo.ConcreteModel
) -> pd.Series:
    data = {}
    model_block = model.component(block)
    if model_block is None:
        raise ValueError(f"{block} is not a valid component of the model!")
    for period in model_block.periods:
        data[period] = (
            model.component(block).periods[period].component(component).value
        )
    return pd.Series(data, name=component)


def _get_component_bounds_from_block(
    block: str, component: str, model: pyo.ConcreteModel
) -> pd.DataFrame:
    """Get the bounds of a component of a block

    Returns a DataFrame with the lower and upper bounds of the specified
    component.

    Arguments
    ---------
        block: str
            The block to get the component from
        component: str
            The component to get the bounds from
        model: pyo.ConcreteModel
            The model to get the data from

    Returns
    -------
        pd.DataFrame
            The bounds of the component over the optimization period"""
    data = {}
    model_block = model.component(block)
    if model_block is None:
        raise ValueError(f"{block} is not a valid component of the model!")
    for period in model_block.periods:
        min, max = (
            model.component(block).periods[period].component(component).bounds
        )
        data[period] = {"lower": min, "upper": max}
    return pd.DataFrame.from_dict(data, orient="index")


def binary_values(heat_pump: str, model: pyo.ConcreteModel):
    y_HP = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "y_HP", model
    )
    y_HR = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "y_HR", model
    )
    y_TES = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "y_TES", model
    )
    y_delta_tes_over_value = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "y_delta_tes_over_value", model
    )
    y_tes_over_value = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "y_tes_over_value", model
    )
    df = pd.concat(
        [y_HP, y_HR, y_TES, y_delta_tes_over_value, y_tes_over_value], axis=1
    )
    df.fillna(0, inplace=True)
    return df.astype(int)


def tank_soc(heat_pump: str, model: pyo.ConcreteModel):
    return _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "soc", model
    )


def parameters(heat_pump: str, model: pyo.ConcreteModel):
    heat_loss_building = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_loss_building", model
    )
    heat_warm_water = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "warm_water_demand", model
    )
    outdoor_temperature = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "outdoor_temperature", model
    )
    source_temp = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "source_temp", model
    )
    return pd.concat(
        [
            heat_loss_building,
            heat_warm_water,
            outdoor_temperature,
            source_temp,
        ],
        axis=1,
    )


def heat_pump_cop(heat_pump: str, model: pyo.ConcreteModel):
    return _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "cop_value", model
    )


def heat_energy_usage(heat_pump: str, model: pyo.ConcreteModel):
    heat_energy_TES = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_energy_TES", model
    )
    heat_loss_tank = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_loss_tank", model
    )
    heat_supply_demand = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_supply_demand", model
    )
    heat_supply_HP = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_supply_HP", model
    )
    heat_supply_HR = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_supply_HR", model
    )
    heat_supply_TES_Demand = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_supply_TES_Demand", model
    )
    heat_supply_hp_demand = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_supply_hp_demand", model
    )
    heat_supply_hp_tes = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_supply_hp_tes", model
    )
    return pd.concat(
        [
            heat_energy_TES,
            heat_loss_tank,
            heat_supply_demand,
            heat_supply_HP,
            heat_supply_HR,
            heat_supply_HR,
            heat_supply_TES_Demand,
            heat_supply_hp_demand,
            heat_supply_hp_tes,
        ],
        axis=1,
    )


def tes_temperature(heat_pump: str, model: pyo.ConcreteModel):
    """Get temperature energy storage temperature of heat pump

    Arguments:
    ----------
        heat_pump: str
            The heat pump's name to get the temperature of
        model: pyo.ConcreteModel
            The optimized optimizer model

    Returns:
    --------
        pd.Series
            The temperature energy storage temperature over the optimization
            period in °C
    """
    temp_tes = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "temp_TES", model
    )
    temp_tes = temp_tes - C_TO_K
    return temp_tes


def heat_energy_demand(
    heat_pump: str, model: pyo.ConcreteModel
) -> pd.DataFrame:
    heat_supply_demand = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_supply_demand", model
    )
    heat_loss_building = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "heat_loss_building", model
    )
    heat_warm_water = _get_component_series_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "warm_water_demand", model
    )

    return pd.concat(
        [heat_supply_demand, heat_loss_building, heat_warm_water], axis=1
    )
