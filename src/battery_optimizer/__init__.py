import pandas as pd
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.model import Optimizer
from battery_optimizer.export.model import (
    to_buy,
    to_sell,
    to_battery_soc,
    to_battery_power,
    to_fixed_consumption,
    to_heat_pump_power,
)
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.profiles.profiles import ProfileStack


def optimize(
    buy_prices: ProfileStack | None = None,
    sell_prices: ProfileStack | None = None,
    fixed_consumption: ProfileStack | None = None,
    batteries: list[Battery] | None = None,
    heat_pumps: list[HeatPump] | None = None,
    **kwargs,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Optimize an energy system

    Arguments
    ---------
    buy_prices : ProfileStack
        All profiles to buy energy from. Price is assumed to be in ct/kWh.
        Power is assumed to be in W. If none of the profiles has a price_above
        specified a "padding" profile is added to the stack to prevent
        infeasible model results. If this padding profile is used the power
        demand from fixed constraints can not be fulfilled at that point in
        time.
    sell_prices : ProfileStack
        All profiles to sell energy to. Price is assumed to be in ct/kWh. Power
        is assumed to be in W.
    fixed_consumption : ProfileStack
        A list of fixed consumption profiles. Power is assumed to be in W. for
        the electricity during this time period (unused here).
    batteries : List[Battery]
        A list of batteries that can be used in the optimization.
    heat_pumps : List[HeatPump]
        A list of heat pumps that provide heating energy for a household.

    Returns
    -------
    buy_power : pd.Dataframe
        The power in W of each buy profile used.
    sell_power : pd.Dataframe
        The power in W of each sell profile used.
    battery_power : pd.Dataframe
        The power in W of each battery. Positive is charge and negative is
        discharge.
    battery_soc : pd.Dataframe
        The SoC of each battery.
    fixed_consumption : pd.Dataframe
        The power in W of each fixed consumption profile used. The same as the
        input. Just for reference.
    heat_pump_power : pd.Dataframe
        The power in W of each heat pump profile used. Heat pumps have an
        inverter and a heating element
    """
    opt = Optimizer(
        buy_prices=buy_prices,
        sell_prices=sell_prices,
        fixed_consumption=fixed_consumption,
        batteries=batteries,
        heat_pumps=heat_pumps,
    )
    opt.set_up()
    opt.solve(**kwargs)
    return (
        to_buy(opt.model),
        to_sell(opt.model),
        to_battery_power(opt.model),
        to_battery_soc(opt),
        to_fixed_consumption(opt.model),
        to_heat_pump_power(opt.model),
    )
