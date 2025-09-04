from battery_optimizer.blocks.battery import BatteryBlock
from battery_optimizer.blocks.fixed_consumption import FixedConsumptionBlock
from battery_optimizer.blocks.heat_pump import HeatPumpBlock
from battery_optimizer.blocks.power_profile import PowerProfileBlock

from battery_optimizer.static.profiles import (
    MODEL_POWER_ABOVE,
    MODEL_POWER_BELOW,
    MODEL_PRICE_ABOVE,
    MODEL_PRICE_BELOW,
)

# General
TEXT_SEPARATOR = " - "
# Battery texts
TEXT_BATTERY_BASE = "Battery: "
TEXT_CHARGE_ENERGY = f"{TEXT_SEPARATOR}charge energy"
TEXT_DISCHARGE_ENERGY = f"{TEXT_SEPARATOR}discharge energy"
TEXT_SOC = "soc"
TEXT_SOC_CONSTRAINT = f"{TEXT_SOC} Constraint"
TEXT_CHARGE_COMPLETION = f"{TEXT_SEPARATOR}charge completion"
TEXT_CHARGE_START = f"{TEXT_SEPARATOR}charge start time"
TEXT_IS_CHARGING = f"{TEXT_SEPARATOR}is charging"
TEXT_IS_DISCHARGING = f"{TEXT_SEPARATOR}is discharging"
TEXT_ENFORCE_CHARGING = f"{TEXT_SEPARATOR}enforce charging"
TEXT_ENFORCE_DISCHARGING = f"{TEXT_SEPARATOR}enforce discharging"
TEXT_ENFORCE_BINARY_POWER = f"{TEXT_SEPARATOR}enforce binary power flow"
# Minimum charge and discharge power
TEXT_ENFORCE_MIN_CHARGE_POWER = f"{TEXT_SEPARATOR}enforce min charge power"
TEXT_ENFORCE_MIN_DISCHARGE_POWER = (
    f"{TEXT_SEPARATOR}enforce min discharge power"
)
# Energy source texts
TEXT_ENERGY_PROFILE_BASE = "Energy source: "
TEXT_ENERGY = f"{TEXT_SEPARATOR}energy"
TEXT_PRICE = f"{TEXT_SEPARATOR}price"
TEXT_SOURCE_DATA_PRICE_COLUMN = rf"({MODEL_PRICE_BELOW})|({MODEL_PRICE_ABOVE})"
TEXT_SOURCE_DATA_ENERGY_COLUMN = (
    rf"({MODEL_POWER_BELOW})|({MODEL_POWER_ABOVE})"
)
# Sell profile texts
TEXT_SELL_PROFILE_BASE = "Sell sink: "
# Fixed consumption profile texts
TEXT_CONSUMPTION_PROFILE_BASE = "Fixed consumption: "
# Energy path texts
TEXT_ENERGY_PATH_MATRIX = "Energy Matrix"
TEXT_ENERGY_PATH_SOURCE_CONSTRAINTS = "Energy distribution source constraints"
TEXT_ENERGY_PATH_SINK_CONSTRAINTS = "Energy distribution target constraints"
# Objective texts
TEXT_OBJECTIVE_NAME = "Objective"

COMPONENT_MAP = {
    BatteryBlock: "batteries",
    PowerProfileBlock: "power_profiles",
    FixedConsumptionBlock: "fixed_consumptions",
    HeatPumpBlock: "heat_pumps",
}
