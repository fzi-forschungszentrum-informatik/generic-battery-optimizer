import pandas as pd
import pyomo.environ as pyo
from battery_optimizer.blocks.base import Base
from battery_optimizer.static.model import (
    TEXT_SOC,
    TEXT_CHARGE_START,
    TEXT_ENFORCE_DISCHARGING,
    TEXT_ENFORCE_BINARY_POWER,
    TEXT_ENFORCE_MIN_CHARGE_POWER,
    TEXT_ENFORCE_MIN_DISCHARGE_POWER,
)
from battery_optimizer.profiles.battery_profile import Battery


def battery_block(
    block: pyo.Block, battery: Battery, model: pyo.ConcreteModel
):
    i = block.index()
    index = model.i

    name_soc = TEXT_SOC
    # Battery can only charge or discharge
    name_battery_enforce_discharging = TEXT_ENFORCE_DISCHARGING

    name_battery_enforce_binary_power = TEXT_ENFORCE_BINARY_POWER
    # Min charge and discharge power requirements
    name_min_charge_power = TEXT_ENFORCE_MIN_CHARGE_POWER
    name_min_discharge_power = TEXT_ENFORCE_MIN_DISCHARGE_POWER
    # add a battery to the model
    # 1 variable for battery energy in and 1 for energy out

    def max_charge_energy(_):
        """Maximum energy that can be charged in time period i"""
        # from last timestamp no energy usage is allowed
        if i == index.last():
            return (0, 0)
        # get time delta
        delta = index.next(i) - i
        # calculate energy that is allowed
        return (0, battery.max_charge_power * (delta / pd.Timedelta("1h")))

    block.energy = pyo.Var(
        bounds=max_charge_energy  # , doc="Energy in", units="kWh"
    )

    def max_discharge_energy(_):
        """Maximum energy that can be discharged in time period i"""
        # from last timestamp no energy usage is allowed
        if i == index.last():
            return (0, 0)
        # get time delta
        delta = index.next(i) - i
        # calculate energy that is allowed
        return (
            0,
            battery.max_discharge_power * (delta / pd.Timedelta("1h")),
        )

    block.energy_out = pyo.Var(bounds=max_discharge_energy)
    block.add_component(name_soc, pyo.Var(bounds=(0, battery.capacity)))

    # soc calculation
    def soc_rule(_):
        """Calculate the SOC of the battery

        SOC rule calculating the current energy state of the battery and
        change in energy for the first timestamp and the change of energy
        relative to the previous timestamps energy for all other
        timestamps.
        """
        # ToDo reference next period from block
        if i == index.at(1):
            return block.component(
                name_soc
            ) == battery.start_soc * battery.capacity + block.energy * battery.charge_efficiency - block.energy_out * (
                1 / battery.discharge_efficiency
            )
        prev_period = block.parent_component()[index.prev(i)]
        return block.component(name_soc) == prev_period.component(
            name_soc
        ) + block.energy * battery.charge_efficiency - block.energy_out * (
            1 / battery.discharge_efficiency
        )

    # Discharge energy
    block.soc_constraint = pyo.Constraint(expr=soc_rule)

    # make sure the charging is complete at the required timestamp
    if battery.end_soc_time is not None:

        def charge_finished(_):
            if i < battery.end_soc_time:
                return (0, block.component(name_soc), battery.capacity)
            return (
                battery.end_soc * battery.capacity,
                block.component(name_soc),
                # This is needed to make sure the result remains feasible
                battery.end_soc * battery.capacity + 0.001,
            )

        block.charge_completion = pyo.Constraint(expr=charge_finished)

    # do not use the battery until its start
    if battery.start_soc_time is not None:
        # Prevent charge
        def charge_start(_):
            if i < battery.start_soc_time:
                return (0, block.energy, 0)
            return (
                0,
                block.energy,
                battery.max_charge_power,
            )

        block.add_component(
            f"energy{TEXT_CHARGE_START}",
            pyo.Constraint(expr=charge_start),
        )

        # Prevent Discharge
        if battery.max_discharge_power > 0:

            def discharge_start(_):
                if i < battery.start_soc_time:
                    return (
                        0,
                        block.energy_out,
                        0,
                    )
                return (
                    0,
                    block.energy_out,
                    battery.max_discharge_power,
                )

            block.add_component(
                f"discharge_energy{TEXT_CHARGE_START}",
                pyo.Constraint(expr=discharge_start),
            )

    # Enforce that the battery can only charge or discharge
    # We only add this if needed to reduce complexity
    # This is needed if charge and discharge efficiency is 100% or
    # minimum discharge or minimum charge power is set

    if (
        (battery.charge_efficiency == 1 and battery.discharge_efficiency == 1)
        or battery.min_charge_power > 0
        or battery.min_discharge_power > 0
    ):
        # Charging
        block.is_charging = pyo.Var(within=pyo.Binary)

        def enforce_binary_charging(_):
            """Enforce block.is_charging to be 1 if charge_power > 0"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            if i == index.last():
                delta = pd.Timedelta("0h")
            else:
                delta = index.next(i) - i

            return (
                block.energy
                <= battery.max_charge_power
                * (delta / pd.Timedelta("1h"))
                * block.is_charging
            )

        block.enforce_charging = pyo.Constraint(rule=enforce_binary_charging)

        # Discharging
        block.is_discharging = pyo.Var(within=pyo.Binary)

        def enforce_binary_discharging(_):
            """Enforce block.is_discharging to be 1 if
            discharge_power > 0"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            if i == index.last():
                delta = pd.Timedelta("0h")
            else:
                delta = index.next(i) - i

            return (
                block.energy_out
                <= battery.max_discharge_power
                * (delta / pd.Timedelta("1h"))
                * block.is_discharging
            )

        block.add_component(
            name_battery_enforce_discharging,
            pyo.Constraint(rule=enforce_binary_discharging),
        )

        def enforce_binary_charging_discharging(_):
            """Enforce battery can only charge or discharge"""
            return block.is_charging + block.is_discharging <= 1

        block.add_component(
            name_battery_enforce_binary_power,
            pyo.Constraint(rule=enforce_binary_charging_discharging),
        )

    if battery.min_charge_power > 0:

        def min_charge_power_constraint(_):
            """Constraint that ensures the battery is charged with
            min_charge_power if it is charged"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            if i == index.last():
                delta = pd.Timedelta("0h")
            else:
                delta = index.next(i) - i

            return (
                block.energy
                >= battery.min_charge_power
                * (delta / pd.Timedelta("1h"))
                * block.is_charging
            )

        block.add_component(
            name_min_charge_power,
            pyo.Constraint(expr=min_charge_power_constraint),
        )

    if battery.min_discharge_power > 0:

        def min_discharge_power_constraint(_):
            """Constraint that ensures the battery is discharged with
            min_discharge_power if it is discharged"""
            # Big M Method -> delta is the time difference between two
            # timestamps
            if i == index.last():
                delta = pd.Timedelta("0h")
            else:
                delta = index.next(i) - i

            return (
                block.energy_out
                >= battery.min_discharge_power
                * (delta / pd.Timedelta("1h"))
                * block.is_discharging
            )

        block.add_component(
            name_min_discharge_power,
            pyo.Constraint(expr=min_discharge_power_constraint),
        )
