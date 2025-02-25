from matplotlib import pyplot as plt
import pandas as pd


def apply_design(
    ax: plt.Axes,
    index: pd.DatetimeIndex,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    ylim: tuple[float, float] = None,
) -> plt.Axes:
    """Adds the general design to a plot.

    Parameters
    ----------
    ax : plt.Axes
        The axes to apply the design to.
    index : pd.DatetimeIndex
        The x-axis index.
    title : str, optional
        The title of the plot, by default "".
    xlabel : str, optional
        The x-axis label, by default "".
    ylabel : str, optional
        The y-axis label, by default "".
    ylim : tuple, optional
        The y-axis limits if needed

    Returns
    -------
    plt.Axes
        The axes with the design applied.
    """
    # Format the x-axis labels
    ax.set_xticks(index)
    ax.xaxis.set_major_formatter(
        plt.matplotlib.dates.DateFormatter("%H:%M", tz=index.tz)
    )
    ax.xaxis.set_major_locator(
        plt.matplotlib.dates.HourLocator(interval=3, tz=index.tz)
    )
    ax.xaxis.set_minor_locator(
        plt.matplotlib.dates.HourLocator(interval=1, tz=index.tz)
    )
    # ax.xaxis.set_minor_formatter(
    #    plt.matplotlib.dates.DateFormatter("%d-%m %H:%M")
    # )
    # ax.xaxis.set_minor_locator(plt.matplotlib.dates.HourLocator(interval=1))
    plt.xticks(rotation=45 if len(index) > 25 else 0)

    # Add title and labels
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(ylim)

    # Remove empty white area at left and right of the plot
    ax.set_xlim(index[0], index[-1])

    # Center the x-ticks
    plt.xticks(ha="center")

    # Show the plot
    ax.grid(True, which="both")
    ax.legend()
    plt.tight_layout()
    return ax
