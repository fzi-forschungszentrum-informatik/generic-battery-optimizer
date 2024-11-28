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

