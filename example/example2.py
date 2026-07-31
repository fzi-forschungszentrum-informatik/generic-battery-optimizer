"""
Example 2: Optimize a household energy system with a heat pump and a battery.
"""

# Additional installations needed: gurobipy

# Reads in profiles from CSV in example_data/example_profiles.csv
# PV from pvgis: location: latitude = 49.011861, longitude = 8.425412, tilt = 30, orientation: south, type: tmy, kwp: 10
# Temperature from meteostat: location: latitude = 49.011861, longitude = 8.425412, year 2024
# Heat demand: bdew mfh 2024 from demandlib (oemof) with anual consumption: 80000 kWh
# Electricity profile: bdew h25 2024 from demandlib (oemof) with anual consumption: 20000 kWh

import pandas as pd  # Useful to load time series for the indices
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.profiles.profiles import ProfileStack, PowerPriceProfile
from battery_optimizer.profile_stack_problem import ProfileStackProblem
from battery_optimizer.solver import Solver
from battery_optimizer.export.model import Exporter

example_dir = Path(__file__).resolve().parent / "example_data"
df = pd.read_csv(example_dir / "example_profiles.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.set_index("timestamp")

# Chose time period that shall be optimized
index_df = df.index
df = df.loc[index_df[0:500]]

# Ensure last period has zero heat demand to avoid infeasibility
df.loc[df.index[-1], "heat_demand"] = 0.0

# Buy profiles
grid_buy_profile = PowerPriceProfile(
    index=df.index,
    price=df["grid_buy_profile_price"].values,
    power=df["grid_buy_profile_power"].values * 10000,
    name="Grid buy profile",
)

# PV profile
pv_profile = PowerPriceProfile(
    index=df.index,
    price=df["pv_profile_price"].values,
    power=df["pv_profile_power"].values,
    name="PV generation profile",
)

# buy_profile_stack = ProfileStack([grid_buy_profile, pv_profile])
buy_profile_stack = ProfileStack([grid_buy_profile])

# Sell profile
grid_sell_profile = PowerPriceProfile(
    index=df.index,
    price=0,
    power=0,
    name="Grid sell profile",
)
sell_profile_stack = ProfileStack([grid_sell_profile])

# Fixed consumption profile
consumption_profile = PowerPriceProfile(
    index=df.index,
    power=df["consumption_profile_power"].values,
    name="Consumption profile",
)

consumption_profile_stack = ProfileStack([consumption_profile])

# Battery
household_battery = Battery(
    name="Household battery",
    start_soc=0.5,
    capacity=50000,
    max_charge_power=50000,
    max_discharge_power=50000,
)

# Heat Pump
heat_pump = HeatPump(
    name="hp_bosch_compress7000_28",
    type="Bosch Compress 7000 LW 28",  # 28 kW thermal output
    flow_temperature=328.15,  # Heating circuit supply 55°C (radiators)
    output_temperature=333.15,  # Max HP outlet ~60°C
    min_electric_power_hp=0.0,  # allow HP to turn off completely
    max_electric_power_hp=28.0,  # max electric power for heat pump
    min_electric_power_hr=0.0,  # allow backup heater to be off
    max_electric_power_hr=12.0,  # max electric power for heating rod
    tank_volume=500,  # thermal energy storage (TES) volume [l]
    tes_start_soc=0.3,  # initial SoC of TES
    outdoor_temperature=df["source_temperature"].to_dict(),  # outdoor temperature
    heat_source_temperature=df["source_temperature"].to_dict(),  # heat source temperature = outdoor temperature
    heat_demand=df["heat_demand"].to_dict(),  # heat demand
    predict_tank_loss=True,  # predict tank loss
)

# Build and solve optimization
opt = ProfileStackProblem(
    buy_prices=buy_profile_stack,
    sell_prices=sell_profile_stack,
    fixed_consumption=consumption_profile_stack,
 #   batteries=[household_battery],
    heat_pumps=[heat_pump],
)
opt.set_up()
Solver(
    solver="gurobi",
    options={
        "TimeLimit": 600,  # Time limit in seconds
        "MIPGap": 0.01,  # 1% optimality gap tolerance
        "OutputFlag": 1,  # Enable solver output
    },
    tee=True,
).solve(opt.model.model)

# Export results
export = Exporter(opt.model).to_df()
buy_power = export.to_buy()
sell_power = export.to_sell()
#battery_power = export.to_battery_power()
#battery_soc = export.to_battery_soc()
fixed_consumption = export.to_fixed_consumption()
heat_pump_power = export.to_heat_pump_power()

hp_block = opt.model.model.heat_pumps.component(heat_pump.name).hp_block
tes_soc = pd.Series({
    t: hp_block[t].soc.value for t in df.index
}, name="TES SoC")
print("Optimization successful - plotting results")

# Create mask for first two days
mask_2d = df.index[:48]

# PLOT 1: Demands and Generation (first two days)
fig1 = plt.figure()
ax1 = fig1.add_subplot(111)
ax1.plot(mask_2d, (df.loc[mask_2d, "heat_demand"] * 1000).values, label='Heat Demand (thermal)', linestyle='-',
         linewidth=2, color='darkorange')
ax1.plot(mask_2d, df.loc[mask_2d, "consumption_profile_power"].values, label='Electricity Demand', linestyle='-',
         linewidth=2, color='blue')
#ax1.plot(mask_2d, pv_profile.power[mask_2d], label='PV Power', linestyle='-',
#         linewidth=2, color='green')
ax1.set_xlabel('Time')
ax1.set_ylabel('Power [W]')
ax1.set_title('Demands and Generation (First 2 Days)')
ax1.legend()
plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
plt.tight_layout()

# PLOT 2: Device Powers (first two days)
fig2 = plt.figure()
ax2 = fig2.add_subplot(111)
#ax2.plot(mask_2d, battery_power.loc[mask_2d, 'Household battery'].values, label='Battery Power', linestyle='-',
#         linewidth=2, color='purple')
ax2.plot(mask_2d, buy_power.loc[mask_2d].sum(axis=1).values, label='Buy Power (total)', linestyle='-',
         linewidth=2, color='red')
ax2.plot(mask_2d, heat_pump_power.loc[mask_2d, heat_pump.name].values, label='Heat Pump Power', linestyle='-',
         linewidth=2, color='teal')
ax2.set_xlabel('Time')
ax2.set_ylabel('Power [W]')
ax2.set_title('Device Powers (First 2 Days)')
ax2.legend()
plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
plt.tight_layout()

# PLOT 3: Battery SOC, TES SOC with Grid Buy Price (first two days)
# fig3 = plt.figure()
# ax3 = fig3.add_subplot(111)
# ax3.plot(mask_2d, battery_soc.loc[mask_2d, 'Household battery'].values, label='Battery SOC', linestyle='-',
#          linewidth=2, color='purple')
# ax3.plot(mask_2d, [tes_soc.loc[idx] for idx in mask_2d], label='TES SOC', linestyle='-', linewidth=2, color='orange')
# ax3.set_xlabel('Time')
# ax3.set_ylabel('SOC [0-1]')
# ax3_twin = ax3.twinx()
# ax3_twin.plot(mask_2d, df.loc[mask_2d, "grid_buy_profile_price"].values, label='Grid Buy Price', linestyle='-', linewidth=2, color='darkred')
# ax3_twin.set_ylabel('Price [Cent/kWh]', color='darkred')
# ax3_twin.tick_params(axis='y', labelcolor='darkred')
# lines1, labels1 = ax3.get_legend_handles_labels()
# lines2, labels2 = ax3_twin.get_legend_handles_labels()
# ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
# ax3.set_title('Storage SOCs and Grid Buy Price (First 2 Days)')
# plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
# plt.tight_layout()
#
# Show plots
plt.show()