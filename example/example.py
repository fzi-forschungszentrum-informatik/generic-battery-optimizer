import random  # Just for the random initialization of power/price values
import pandas as pd  # Useful to generate time series for the indices
from battery_optimizer import optimize
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.profiles.profiles import ProfileStack, PowerPriceProfile

# Buy profiles
grid_buy_profile = PowerPriceProfile(
    index=pd.date_range(start="2020-01-01", end="2020-01-02", freq="h"),
    price=[random.randint(10, 55) for _ in range(25)],
    power=[random.randint(2000, 10000) for _ in range(25)],
    name="Grid buy profile",
)

pv_profile = PowerPriceProfile(
    index=pd.date_range(start="2020-01-01", end="2020-01-02", freq="h"),
    price=[0 for _ in range(25)],
    power=[random.randint(0, 2000) for _ in range(25)],
    name="PV generation profile",
)

buy_profile_stack = ProfileStack([grid_buy_profile, pv_profile])

# Sell profile
grid_sell_profile = PowerPriceProfile(
    index=pd.date_range(start="2020-01-01", end="2020-01-02", freq="h"),
    price=[random.randint(5, 15) for _ in range(25)],
    power=[random.randint(2000, 10000) for _ in range(25)],
    name="Grid sell profile",
)

sell_profile_stack = ProfileStack([grid_sell_profile])

# Fixed consumption profile
consumption_profile = PowerPriceProfile(
    index=pd.date_range(start="2020-01-01", end="2020-01-02", freq="h"),
    power=[random.randint(200, 3500) for _ in range(25)],
    name="Consumption profile",
)

consumption_profile_stack = ProfileStack([consumption_profile])

# Batteries
household_battery = Battery(
    name="Household battery",
    start_soc=1,
    capacity=10000,
    max_charge_power=5000,
    max_discharge_power=5000,
)

(
    buy_power,
    sell_power,
    battery_power,
    battery_soc,
    fixed_consumption,
    heat_pump_power,
) = optimize(
    buy_prices=buy_profile_stack,
    sell_prices=sell_profile_stack,
    fixed_consumption=consumption_profile_stack,
    batteries=[household_battery],
)
