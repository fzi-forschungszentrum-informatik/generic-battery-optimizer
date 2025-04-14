import datetime
import pandas as pd
import pyomo.environ as pyo
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.profiles.battery_profile import Battery


class BatteryBlock:
    def __init__(self, index: pyo.Set, battery: Battery):
        self.index = index
        self.battery = battery

    def get_block(self, block: pyo.Block):
        i = block.index()
        _, period_conversion_factor = get_period_length(i, self.index)

        def max_charge_energy(_):
            """Maximum energy that can be charged in time period i"""
            # from last timestamp no energy usage is allowed
            if i == self.index.last():
                return (0, 0)
            # calculate energy that is allowed
            return (
                0,
                self.battery.max_charge_power * period_conversion_factor,
            )

        block.energy = pyo.Var(
            bounds=max_charge_energy  # , doc="Energy in", units="kWh"
        )

        def max_discharge_energy(_):
            """Maximum energy that can be discharged in time period i"""
            # from last timestamp no energy usage is allowed
            if i == self.index.last():
                return (0, 0)
            # calculate energy that is allowed
            return (
                0,
                self.battery.max_discharge_power * period_conversion_factor,
            )

        block.energy_out = pyo.Var(bounds=max_discharge_energy)
        block.soc = pyo.Var(bounds=(0, self.battery.capacity))

        # soc calculation
        def soc_rule(_):
            """Calculate the SOC of the battery

            SOC rule calculating the current energy state of the battery and
            change in energy for the first timestamp and the change of energy
            relative to the previous timestamps energy for all other
            timestamps.
            """
            # ToDo reference next period from block
            if i == self.index.at(1):
                previous_soc = self.battery.start_soc * self.battery.capacity
            else:
                previous_soc = block.parent_component()[self.index.prev(i)].soc
            return (
                block.soc
                == previous_soc
                + block.energy * self.battery.charge_efficiency
                - block.energy_out * (1 / self.battery.discharge_efficiency)
            )

        # Discharge energy
        block.soc_constraint = pyo.Constraint(expr=soc_rule)

        # make sure the charging is complete at the required timestamp
        if self.battery.end_soc_time is not None:

            def charge_finished(_):
                if i < self.battery.end_soc_time:
                    return (0, block.soc, self.battery.capacity)
                return (
                    self.battery.end_soc * self.battery.capacity,
                    block.soc,
                    # This is needed to make sure the result remains feasible
                    self.battery.end_soc * self.battery.capacity + 0.001,
                )

            block.charge_completion = pyo.Constraint(expr=charge_finished)

        # do not use the battery until its start
        if self.battery.start_soc_time is not None:
            # Prevent charge
            def charge_start(_):
                if i < self.battery.start_soc_time:
                    return (0, block.energy, 0)
                return (
                    0,
                    block.energy,
                    self.battery.max_charge_power,
                )

            block.charge_start_time = pyo.Constraint(expr=charge_start)

            # Prevent Discharge
            if self.battery.max_discharge_power > 0:

                def discharge_start(_):
                    if i < self.battery.start_soc_time:
                        return (
                            0,
                            block.energy_out,
                            0,
                        )
                    return (
                        0,
                        block.energy_out,
                        self.battery.max_discharge_power,
                    )

                block.discharge_start_time = pyo.Constraint(
                    expr=discharge_start
                )

        # Enforce that the battery can only charge or discharge
        # We only add this if needed to reduce complexity
        # This is needed if charge and discharge efficiency is 100% or
        # minimum discharge or minimum charge power is set

        if (
            (
                self.battery.charge_efficiency == 1
                and self.battery.discharge_efficiency == 1
            )
            or self.battery.min_charge_power > 0
            or self.battery.min_discharge_power > 0
        ):
            # Charging
            block.is_charging = pyo.Var(within=pyo.Binary)

            def enforce_binary_charging(_):
                """Enforce block.is_charging to be 1 if charge_power > 0"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                if i == self.index.last():
                    delta = pd.Timedelta("0h")
                else:
                    delta = self.index.next(i) - i

                return (
                    block.energy
                    <= self.battery.max_charge_power
                    * (delta / pd.Timedelta("1h"))
                    * block.is_charging
                )

            block.enforce_charging = pyo.Constraint(
                rule=enforce_binary_charging
            )

            # Discharging
            block.is_discharging = pyo.Var(within=pyo.Binary)

            def enforce_binary_discharging(_):
                """Enforce block.is_discharging to be 1 if
                discharge_power > 0"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                if i == self.index.last():
                    delta = pd.Timedelta("0h")
                else:
                    delta = self.index.next(i) - i

                return (
                    block.energy_out
                    <= self.battery.max_discharge_power
                    * (delta / pd.Timedelta("1h"))
                    * block.is_discharging
                )

            block.enforce_discharging = pyo.Constraint(
                rule=enforce_binary_discharging
            )

            def enforce_binary_charging_discharging(_):
                """Enforce battery can only charge or discharge"""
                return block.is_charging + block.is_discharging <= 1

            block.enforce_binary_power = pyo.Constraint(
                rule=enforce_binary_charging_discharging
            )

        if self.battery.min_charge_power > 0:

            def min_charge_power_constraint(_):
                """Constraint that ensures the battery is charged with
                min_charge_power if it is charged"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                return (
                    block.energy
                    >= self.battery.min_charge_power
                    * period_conversion_factor
                    * block.is_charging
                )

            block.min_charge_power = pyo.Constraint(
                expr=min_charge_power_constraint
            )

        if self.battery.min_discharge_power > 0:

            def min_discharge_power_constraint(_):
                """Constraint that ensures the battery is discharged with
                min_discharge_power if it is discharged"""
                # Big M Method -> delta is the time difference between two
                # timestamps
                return (
                    block.energy_out
                    >= self.battery.min_discharge_power
                    * period_conversion_factor
                    * block.is_discharging
                )

            block.min_discharge_power = pyo.Constraint(
                expr=min_discharge_power_constraint
            )
