import datetime
import pyomo.environ as pyo
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.profiles.battery_profile import Battery


class BatteryBlock:
    def __init__(self, index: pyo.Set, battery: Battery):
        self.index = index
        self.battery = battery

    def get_block(self, block: pyo.Block):
        # DEFAULT
        # Source in Matrix
        block.energy_source = pyo.Var(bounds=(0, 0), initialize=0)
        block.price_source = pyo.Param(initialize=0, mutable=True)
        # Sink in matrix
        block.energy_sink = pyo.Var(bounds=(0, 0), initialize=0)
        block.price_sink = pyo.Param(initialize=0, mutable=True)
        # DEFAULT

        i = block.index()
        _, period_conversion_factor = get_period_length(i, self.index)

        # Energy in
        block.energy_sink.setub(
            0
            if i == self.index.last()
            else self.battery.max_charge_power * period_conversion_factor
        )
        # , doc="Energy in", units="kWh"

        # Energy out
        block.energy_source.setub(
            0
            if i == self.index.last()
            else self.battery.max_discharge_power * period_conversion_factor
        )
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
                + block.energy_sink * self.battery.charge_efficiency
                - block.energy_source * (1 / self.battery.discharge_efficiency)
            )

        # Discharge energy
        block.soc_constraint = pyo.Constraint(expr=soc_rule)

        # make sure the charging is complete at the required timestamp
        if (self.battery.end_soc_time is not None) and (
            i >= self.battery.end_soc_time
        ):
            block.charge_completion = pyo.Constraint(
                expr=(
                    self.battery.end_soc * self.battery.capacity,
                    block.soc,
                    # This is needed to make sure the result remains feasible
                    self.battery.end_soc * self.battery.capacity + 0.001,
                )
            )

        # do not use the battery until its start
        if self.battery.start_soc_time is not None:
            # Prevent charge
            if i < self.battery.start_soc_time:
                block.charge_start_time = pyo.Constraint(
                    expr=(0, block.energy_sink, 0)
                )

                # Prevent Discharge
                if self.battery.max_discharge_power > 0:
                    block.discharge_start_time = pyo.Constraint(
                        expr=(
                            0,
                            block.energy_source,
                            0,
                        )
                    )

        # Enforce that the battery can only charge or discharge
        # We only add this if needed to reduce complexity
        # This is needed if charge and discharge efficiency is 100% or
        # minimum discharge or minimum charge power is set

        # Charging
        block.is_charging = pyo.Var(within=pyo.Binary)

        # Enforce block.is_charging to be 1 if charge_power > 0
        # Big M Method -> delta is the time difference between two
        # timestamps
        block.enforce_charging = pyo.Constraint(
            rule=(
                block.energy_sink
                <= self.battery.max_charge_power
                * period_conversion_factor
                * block.is_charging
            )
        )

        # Discharging
        block.is_discharging = pyo.Var(within=pyo.Binary)

        # Enforce block.is_discharging to be 1 if discharge_power > 0
        # Big M Method -> delta is the time difference between two
        # timestamps
        block.enforce_discharging = pyo.Constraint(
            rule=(
                block.energy_source
                <= self.battery.max_discharge_power
                * period_conversion_factor
                * block.is_discharging
            )
        )

        # Enforce battery can only charge or discharge
        block.enforce_binary_power = pyo.Constraint(
            rule=(block.is_charging + block.is_discharging <= 1)
        )

        # Constraint that ensures the battery is charged with min_charge_power
        # if it is charged
        # Big M Method -> delta is the time difference between two
        # timestamps
        block.min_charge_power = pyo.Constraint(
            expr=(
                block.energy_sink
                >= self.battery.min_charge_power
                * period_conversion_factor
                * block.is_charging
            )
        )

        # Constraint that ensures the battery is discharged with
        # min_discharge_power if it is discharged
        # Big M Method -> delta is the time difference between two
        # timestamps
        block.min_discharge_power = pyo.Constraint(
            expr=(
                block.energy_source
                >= self.battery.min_discharge_power
                * period_conversion_factor
                * block.is_discharging
            )
        )
