from battery_optimizer.export.heat_pump import (
    _get_component_bounds_from_block,
    heat_energy_demand,
    tank_soc,
    binary_values,
    parameters,
    heat_pump_cop,
    tes_temperature,
    heat_energy_usage,
)
import pyomo.environ as pyo
import matplotlib.pyplot as plt

from battery_optimizer.export.model import to_heat_pump_power
from battery_optimizer.static.heat_pump import C_TO_K, TEXT_HEAT_PUMP_BASE
from battery_optimizer.static.numbers import MAX_COP
from battery_optimizer.visualize.general import apply_design


def plot_tank_soc(heat_pump: str, model: pyo.ConcreteModel, figsize=(10, 6)):
    # Get the TES temperature data
    soc = tank_soc(heat_pump, model)

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(soc.index, soc.values, marker="o")

    ax = apply_design(
        ax,
        soc.index,
        title="TES SoC",
        xlabel="Time",
        ylabel="SoC",
        ylim=(0, 1),
    )

    ax.set_yticks(
        ticks=[i / 10 for i in range(0, 11)],
        labels=[f"{i*10}%" for i in range(0, 11)],
    )

    return fig


def plot_binary_values(heat_pump: str, model: pyo.ConcreteModel):
    pass


def plot_parameters(heat_pump: str, model: pyo.ConcreteModel):
    pass


def plot_heat_pump_cop(
    heat_pump: str, model: pyo.ConcreteModel, figsize=(10, 6)
):
    # Get the TES temperature data
    cop = heat_pump_cop(heat_pump, model)

    # Remove the last value, as it is the CoP for the next time step
    index = cop.index
    cop = cop[:-1]

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.stairs(cop, index, label="CoP", linewidth=2)

    ax = apply_design(
        ax,
        index,
        title="Heat Pump CoP",
        xlabel="Time",
        ylabel="CoP",
        ylim=(0, MAX_COP),
    )

    return fig


def plot_heat_pump_power(
    heat_pump: str,
    model: pyo.ConcreteModel,
    figsize: tuple[int, int] = (10, 6),
):
    # Get the TES temperature data
    heat_pump_power = to_heat_pump_power(model)
    # Select all columns that contain the heat pump name
    heat_pump_power = heat_pump_power.loc[
        :, heat_pump_power.columns.str.contains(heat_pump)
    ]

    index = heat_pump_power.index
    heat_pump_power = heat_pump_power[:-1]

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)

    for column in heat_pump_power.columns:
        ax.stairs(heat_pump_power[column], index, label=column, linewidth=2)

    # Set the y-axis range and labels
    list_max = max([max(i) for i in heat_pump_power.values])
    list_min = min([min(i) for i in heat_pump_power.values])
    ylim = None
    if list_max - list_min < 10:
        ylim = (
            max(list_min - 5, 0),
            list_max + 5,
        )

    ax = apply_design(
        ax,
        index,
        title="Heat Pump Power in W",
        xlabel="Time",
        ylabel="Power (W)",
        ylim=ylim,
    )

    return fig


def plot_tes_temperature(
    heat_pump: str, model: pyo.ConcreteModel, figsize=(10, 6)
):
    """Plot the TES temperature over the optimization period

    The plot has y limits based on the allowed minimum and maximum allowed TES
    temperature.
    The temperature change is visualized as a gradual change between the time
    steps.

    Arguments
    ---------
        heat_pump: str
            The name of the heat pump to plot the TES temperature for
        model: pyo.ConcreteModel
            The model to get the data from
        figsize: tuple[int, int]
            The size of the plot

    Returns
    -------
        plt.Figure
            The plot of the TES temperature
    """
    # Get the TES temperature data
    tes_temp = tes_temperature(heat_pump, model)

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(tes_temp.index, tes_temp.values, marker="o")

    # Get component bounds for ylim
    bounds = _get_component_bounds_from_block(
        TEXT_HEAT_PUMP_BASE + heat_pump, "temp_TES", model
    )

    ax = apply_design(
        ax,
        tes_temp.index,
        title="TES temperature in °C",
        xlabel="Time",
        ylabel="Temperature (°C)",
        ylim=(min(bounds["lower"]) - C_TO_K, max(bounds["upper"]) - C_TO_K),
    )

    return fig


def plot_heat_energy_demand(
    heat_pump: str,
    model: pyo.ConcreteModel,
    figsize: tuple[int, int] = (10, 6),
) -> plt.Figure:
    energy_demand = heat_energy_demand(heat_pump, model)

    # All values in last row are zero (limitation of variable time intervals)
    index = energy_demand.index
    energy_demand = energy_demand[:-1]

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.stairs(
        energy_demand["heat_loss_building"],
        index,
        fill=True,
        label="Building heat loss",
    )
    ax.stairs(
        energy_demand["warm_water_demand"]
        + energy_demand["heat_loss_building"],
        index,
        baseline=energy_demand["heat_loss_building"],
        fill=True,
        label="Warm water heat demand",
    )

    ax.stairs(
        energy_demand["heat_supply_demand"],
        index,
        label="Total heat demand",
    )
    ax = apply_design(
        ax=ax,
        index=index,
        title=f"Heat Energy Demand for {heat_pump}",
        xlabel="Time",
        ylabel="Energy (kWh)",
    )

    return fig
