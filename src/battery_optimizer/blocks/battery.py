import datetime
import pyomo.environ as pyo
# from battery_optimizer.blocks.base import Base
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.profiles.battery_profile import Battery


class BatteryBlock:
    def __init__(self, index: pyo.Set, battery: Battery):
        self.index = index
        self.battery = battery

    def build_block(self) -> pyo.Block:
        """Build the battery block"""
        block = pyo.Block()
        # DEFAULT
        # Source in Matrix
        block.energy_source = pyo.Var(self.index, bounds=(0, 0), initialize=0)
        block.price_source = pyo.Param(self.index, initialize=0, mutable=True)
        # Sink in matrix
        block.energy_sink = pyo.Var(self.index, bounds=(0, 0), initialize=0)
        block.price_sink = pyo.Param(self.index, initialize=0, mutable=True)
        # DEFAULT
        block.energy_source.construct()
        block.price_source.construct()
        block.energy_sink.construct()
        block.price_sink.construct()

        for i in self.index:
            period_conversion_factor = get_period_length(i, self.index)[1]
            # Energy in
            block.energy_sink[i].setub(
                0
                if i == self.index.last()
                else self.battery.max_charge_power * period_conversion_factor
            )
            # , doc="Energy in", units="kWh"

            # Energy out
            block.energy_source[i].setub(
                0
                if i == self.index.last()
                else self.battery.max_discharge_power
                * period_conversion_factor
            )
        block.soc = pyo.Var(self.index, bounds=(0, self.battery.capacity))

        # soc calculation
        def soc_rule(_, i):
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
                previous_soc = block.soc[self.index.prev(i)]
            return block.soc[i] == previous_soc + block.energy_sink[
                i
            ] * self.battery.charge_efficiency - block.energy_source[i] * (
                1 / self.battery.discharge_efficiency
            )

        # Discharge energy
        block.soc_constraint = pyo.Constraint(self.index, expr=soc_rule)

        # make sure the charging is complete at the required timestamp
        if self.battery.end_soc_time is not None:

            def charge_finished(_, i):
                if i < self.battery.end_soc_time:
                    return pyo.Constraint.Skip
                return (
                    self.battery.end_soc * self.battery.capacity,
                    block.soc[i],
                    # This is needed to make sure the result remains feasible
                    self.battery.end_soc * self.battery.capacity + 0.001,
                )

            block.charge_completion = pyo.Constraint(
                self.index, expr=charge_finished
            )

        # do not use the battery until its start
        if self.battery.start_soc_time is not None:
            # Prevent charge
            def charge_start(_, i):
                if i < self.battery.start_soc_time:
                    return (0, block.energy_sink[i], 0)
                return pyo.Constraint.Skip

            block.charge_start_time = pyo.Constraint(
                self.index, expr=charge_start
            )

            # Prevent Discharge
            if self.battery.max_discharge_power > 0:

                def discharge_start(_, i):
                    if i < self.battery.start_soc_time:
                        return (
                            0,
                            block.energy_source[i],
                            0,
                        )
                    return pyo.Constraint.Skip

                block.discharge_start_time = pyo.Constraint(
                    self.index, expr=discharge_start
                )

        # Enforce that the battery can only charge or discharge
        # We only add this if needed to reduce complexity
        # This is needed if charge and discharge efficiency is 100% or
        # minimum discharge or minimum charge power is set

        # Charging
        block.is_charging = pyo.Var(self.index, within=pyo.Binary)

        def enforce_binary_charging(_, i):
            """Enforce block.is_charging to be 1 if charge_power > 0"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            return (
                block.energy_sink[i]
                <= self.battery.max_charge_power
                * get_period_length(i, self.index)[1]
                * block.is_charging[i]
            )

        block.enforce_charging = pyo.Constraint(
            self.index, rule=enforce_binary_charging
        )

        # Discharging
        block.is_discharging = pyo.Var(self.index, within=pyo.Binary)

        def enforce_binary_discharging(_, i):
            """Enforce block.is_discharging to be 1 if
            discharge_power > 0"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            return (
                block.energy_source[i]
                <= self.battery.max_discharge_power
                * get_period_length(i, self.index)[1]
                * block.is_discharging[i]
            )

        block.enforce_discharging = pyo.Constraint(
            self.index, rule=enforce_binary_discharging
        )

        def enforce_binary_charging_discharging(_, i):
            """Enforce battery can only charge or discharge"""
            return block.is_charging[i] + block.is_discharging[i] <= 1

        block.enforce_binary_power = pyo.Constraint(
            self.index, rule=enforce_binary_charging_discharging
        )

        def min_charge_power_constraint(_, i):
            """Constraint that ensures the battery is charged with
            min_charge_power if it is charged"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            return (
                block.energy_sink[i]
                >= self.battery.min_charge_power
                * get_period_length(i, self.index)[1]
                * block.is_charging[i]
            )

        block.min_charge_power = pyo.Constraint(
            self.index, expr=min_charge_power_constraint
        )

        def min_discharge_power_constraint(_, i):
            """Constraint that ensures the battery is discharged with
            min_discharge_power if it is discharged"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            return (
                block.energy_source[i]
                >= self.battery.min_discharge_power
                * get_period_length(i, self.index)[1]
                * block.is_discharging[i]
            )

        block.min_discharge_power = pyo.Constraint(
            self.index, expr=min_discharge_power_constraint
        )

        return block


# class Block(Base):
#     """Battery Block

#     This block is used to create a battery block in the optimization model.
#     It contains the energy, soc and charge/discharge constraints for the
#     battery.
#     """

#     def __init__(self, index: list[datetime.datetime], battery: Battery):
#         super().__init__(index)
#         self.battery = battery
#         self.index = index

#     def get_block(self) -> pyo.Block:
#         """Get the block of the profile"""
#         block = pyo.Block(self.index)
#         for period in self.block.index_set():
#             # add the battery block to the period
#             block[period].transfer_attributes_from(self.block[period])
#             block[period] = self.block_period(self.block[period])
