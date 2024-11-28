from battery_optimizer.export.heat_pump import (
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
from battery_optimizer.static.numbers import MAX_COP


def plot_tank_soc(heat_pump: str, model: pyo.ConcreteModel, figsize=(10, 6)):
    # Get the TES temperature data
    soc = tank_soc(heat_pump, model)

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(soc.index, soc.values, marker="o")

    # Format the x-axis labels
    ax.set_xticks(soc.index)
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_formatter(
        plt.matplotlib.dates.DateFormatter("%d-%m %H:%M")
    )
    ax.xaxis.set_minor_locator(plt.matplotlib.dates.HourLocator(interval=1))
    plt.xticks(rotation=45)

    # Set the y-axis range and labels
    ax.set_ylim(0, 1)
    ax.set_ylabel("SoC")
    ax.set_yticks(
        ticks=[i / 10 for i in range(0, 11)],
        labels=[f"{i*10}%" for i in range(0, 11)],
    )

    # Add title and labels
    ax.set_title("TES SoC")
    ax.set_xlabel("Time")

    # Show the plot
    ax.grid(True)
    plt.tight_layout()

    return fig

def plot_heat_pump_cop(
    heat_pump: str, model: pyo.ConcreteModel, figsize=(10, 6)
):
    # Get the TES temperature data
    cop = heat_pump_cop(heat_pump, model)

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(cop.index, cop.values, marker="o")

    # Format the x-axis labels
    ax.set_xticks(cop.index)
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_formatter(
        plt.matplotlib.dates.DateFormatter("%d-%m %H:%M")
    )
    ax.xaxis.set_minor_locator(plt.matplotlib.dates.HourLocator(interval=1))
    plt.xticks(rotation=45)

    # Set the y-axis range and labels
    ax.set_ylim(0, MAX_COP)
    ax.set_ylabel("CoP")
    ax.set_yticks(range(0, 11))

    # Add title and labels
    ax.set_title("Heat Pump CoP")
    ax.set_xlabel("Time")

    # Show the plot
    ax.grid(True)
    plt.tight_layout()

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

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(heat_pump_power.index, heat_pump_power.values, marker="o")

    # Format the x-axis labels
    ax.set_xticks(heat_pump_power.index)
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_formatter(
        plt.matplotlib.dates.DateFormatter("%d-%m %H:%M")
    )
    ax.xaxis.set_minor_locator(plt.matplotlib.dates.HourLocator(interval=1))
    plt.xticks(rotation=45)

    # Set the y-axis range and labels
    list_max = max([max(i) for i in heat_pump_power.values])
    list_min = min([min(i) for i in heat_pump_power.values])
    if list_max - list_min < 10:
        ax.set_ylim(
            max(list_min - 5, 0),
            list_max + 5,
        )
    ax.set_ylabel("Power in W")

    # Add title and labels
    ax.set_title("Heat Pump Power")
    ax.set_xlabel("Time")

    # Show the plot
    ax.grid(True)
    plt.tight_layout()

    return fig


def plot_tes_temperature(
    heat_pump: str, model: pyo.ConcreteModel, figsize=(10, 6)
):
    # Get the TES temperature data
    tes_temp = tes_temperature(heat_pump, model)

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(tes_temp.index, tes_temp.values, marker="o")

    # Format the x-axis labels
    ax.set_xticks(tes_temp.index)
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_formatter(
        plt.matplotlib.dates.DateFormatter("%d-%m %H:%M")
    )
    ax.xaxis.set_minor_locator(plt.matplotlib.dates.HourLocator(interval=1))
    plt.xticks(rotation=45)

    # Set the y-axis range and labels
    ax.set_ylim(min(tes_temp.values) - 5, max(tes_temp.values) + 5)
    ax.set_ylabel("Temperature (°C)")

    # Add title and labels
    ax.set_title("TES temperature in °C")
    ax.set_xlabel("Time")

    # Show the plot
    ax.grid(True)
    plt.tight_layout()

    return fig

