"""
Example 2: Optimize a household energy system with a heat pump and a battery.
"""

# Additional installations needed: gurobipy

# Reads in profiles from CSV in example_data/example_profiles.csv
# PV from pvgis: location: latitude = 49.011861, longitude = 8.425412, tilt = 30, orientation: south, type: tmy, kwp: 10
# Temperature from meteostat: location: latitude = 49.011861, longitude = 8.425412, year 2024
# Heat demand: bdew mfh 2024 from demandlib (oemof) with anual consumption: 80000 kWh
# Consumption profile: bdew h25 2024 from demandlib (oemof) with anual consumption: 20000 kWh
# Electricity price: day ahead price from netztransparenz + 15 cent/kWh

import pandas as pd  # Useful to load time series for the indices
from pathlib import Path
import matplotlib.pyplot as plt
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
df = df.loc[index_df[0:100]]

# Ensure last period has zero heat demand to avoid infeasibility
df.loc[df.index[-1], "heat_demand"] = 0.0


# Buy profiles
grid_buy_profile = PowerPriceProfile(
    index=df.index,
    price=df["grid_buy_profile_price"].values,
    power=1e10,  # set maximum power available from grid to a very large value (10 MW)
    name="Grid buy profile",
)

# PV profile
pv_profile = PowerPriceProfile(
    index=df.index, 
    price=df["pv_profile_price"].values,
    power=df["pv_profile_power"].values, 
    name="PV generation profile",
)

buy_profile_stack = ProfileStack([grid_buy_profile, pv_profile])

# Sell profile
grid_sell_profile = PowerPriceProfile(
    index=df.index, 
    price=0,  # Feed-in tariff (0 = no selling)
    power=0,  # Maximum power to sell (0 = no selling)
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
    start_soc=0.5,  # [0-1, unitless] Initial state of charge (50%)
    capacity=30000,  # [Wh] Battery capacity
    max_charge_power=30000,  # [W] Maximum charging power
    max_discharge_power=30000,  # [W] Maximum discharging power
)

# Heat Pump - Vaillant VWL 55/5 (Outdoor Air/Water)
heat_pump = HeatPump(
    # === REQUIRED PARAMETERS ===
    name="hp_vaillant_vwl55",  # Unique identifier for the heat pump
    type="VWL 55/5 AS 230V + VWL 57/5 IS",  # Specific Vaillant heat pump model from hplib database
    
    # Temperature settings:
    flow_temperature=303.15,  # [K] Heating circuit supply temp (30.0°C)
    output_temperature=323.15,  # [K] Max HP outlet temp (50.0°C)
    
    # Electric power limits:
    max_electric_power_hp=50.0,  # [kW] Maximum electric power consumption of heat pump
    max_electric_power_hr=30.0,  # [kW] Maximum electric power consumption of heating rod/backup heater
    min_electric_power_hp=0,  # [kW] Minimum electric power when HP is on (0 = can turn off completely)
    min_electric_power_hr=0,  # [kW] Minimum electric power when heater is on (0 = can turn off completely)
    
    # Thermal Energy Storage (TES) settings:
    tank_volume=1000,  # [L] Volume of thermal energy storage tank
    tes_start_soc=0.5,  # [0-1, unitless] Initial TES state of charge
    max_temp_tes=333.15,  # [K] Maximum TES temperature (60°C)
    
    # Time-series data:
    outdoor_temperature=df["source_temperature"].to_dict(),  # [K] Outdoor/ambient temperature
    heat_source_temperature=df["source_temperature"].to_dict(),  # [K] Heat source temperature 
    heat_demand=df["heat_demand"].to_dict(),  # [kW] heat demand (heating + warm water)
    
    # Tank loss prediction:
    predict_tank_loss=False,  # Enable/disable tank heat loss calculation based on tank dimensions
)

# Build and solve optimization
opt = ProfileStackProblem(
    buy_prices=buy_profile_stack,
    sell_prices=sell_profile_stack,
    fixed_consumption=consumption_profile_stack,
    batteries=[household_battery],
    heat_pumps=[heat_pump],
)
opt.set_up()
Solver(
    solver="gurobi",
    options={
        "TimeLimit": 600,  
        "MIPGap": 0.01,  
        "OutputFlag": 1, 
    },
    tee=True,
).solve(opt.model.model)

# Export results
export = Exporter(opt.model).to_df()
buy_power = export.to_buy()
sell_power = export.to_sell()
battery_power = export.to_battery_power()
battery_soc = export.to_battery_soc()
fixed_consumption = export.to_fixed_consumption()
heat_pump_power = export.to_heat_pump_power()

hp_block = opt.model.model.heat_pumps.component(heat_pump.name).hp_block
tes_soc = pd.Series({
    t: hp_block[t].soc.value for t in df.index
}, name="TES SoC")

print("Optimization successful - plotting results")


# Create mask for first two days
mask_2d = df.index[:500]

# PLOT 1: Demands and Generation (first two days)
fig1 = plt.figure()
ax1 = fig1.add_subplot(111)
ax1.plot(mask_2d, (df.loc[mask_2d, "heat_demand"] * 1000).values, label='Heat Demand (thermal)', linestyle='-',
         linewidth=2, color='darkorange')
ax1.plot(mask_2d, df.loc[mask_2d, "consumption_profile_power"].values, label='Electricity Demand', linestyle='-',
         linewidth=2, color='blue')
ax1.plot(mask_2d, pv_profile.power[mask_2d], label='PV Power', linestyle='-',
         linewidth=2, color='green')
ax1.set_xlabel('Time')
ax1.set_ylabel('Power [W]')
ax1.set_title('Demands and Generation (First 2 Days)')
ax1.legend()
plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
plt.tight_layout()

# PLOT 2: Device Powers (first two days)
fig2 = plt.figure()
ax2 = fig2.add_subplot(111)
ax2.plot(mask_2d, battery_power.loc[mask_2d, 'Household battery'].values, label='Battery Power', linestyle='-',
         linewidth=2, color='purple')
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
fig3 = plt.figure()
ax3 = fig3.add_subplot(111)
ax3.plot(mask_2d, battery_soc.loc[mask_2d, 'Household battery'].values, label='Battery SOC', linestyle='-',
         linewidth=2, color='purple')
ax3.plot(mask_2d, [tes_soc.loc[idx] for idx in mask_2d], label='TES SOC', linestyle='-', linewidth=2, color='orange')
ax3.set_xlabel('Time')
ax3.set_ylabel('SOC [0-1]')
ax3_twin = ax3.twinx()
ax3_twin.plot(mask_2d, df.loc[mask_2d, "grid_buy_profile_price"].values, label='Grid Buy Price', linestyle='-', linewidth=2, color='darkred')
ax3_twin.set_ylabel('Price [Cent/kWh]', color='darkred')
ax3_twin.tick_params(axis='y', labelcolor='darkred')
lines1, labels1 = ax3.get_legend_handles_labels()
lines2, labels2 = ax3_twin.get_legend_handles_labels()
ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
ax3.set_title('Storage SOCs and Grid Buy Price (First 2 Days)')
plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
plt.tight_layout()

# Show plots
plt.show()
