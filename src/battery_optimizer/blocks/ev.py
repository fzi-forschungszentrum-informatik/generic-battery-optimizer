"""
Extends the battery block with ev specific constraints and limitations.

EVBlock extends the basic BatteryBlock with additional constraints
like charge start and end times as well as minimum charge and discharge
powers.
"""

import datetime
from battery_optimizer.blocks.battery import NewBatteryBlock as BatteryBlock
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.profiles.ev import EV
import pyomo.environ as pyo


class EVBlock(BatteryBlock):
    """
    Pyomo block representing an electric vehicle battery.

    Power and energy are assumed to be specified in W and Wh respectively.
    This is an extension of the basic BatteryBlock with additional
    constraints for electric vehicles.

    Parameters
    ----------
    index : pyo.Set
        The set of time indices for the optimization.
    battery : EV
        The electric vehicle battery profile.
    """
    def __init__(self, index: pyo.Set, battery: EV):
        """
        Initialize the EVBlock.

        Store the index and ev (battery) profile. And initialize the parent
        BatteryBlock.

        Parameters
        ----------
        index : pyo.Set
            The set of time indices for the optimization.
        battery : EV
            The electric vehicle battery profile.
        """
        super().__init__(index, battery)

    def _populate_block(self, block: pyo.Block) -> pyo.Block:
        """
        Build the EV block.

        Adds all necessary variables and constraints to the provided Pyomo
        block to simulate the EV behavior.

        Parameters
        ----------
        block : pyo.Block
            The Pyomo block to populate with EV battery variables and
            constraints.

        Returns
        -------
        pyo.Block
            The populated Pyomo block with EV battery variables and
            constraints.
        """
        block = super()._populate_block(block)

        # make sure the charging is complete at the required timestamp
        if self.battery.charge_end_time is not None:

            # BUG This ensures soc at the end of the charge_end_time timestamp
            # but should enforce it at the beginning of the timestamp (t-1
            # needs the soc already to be at end_soc)
            def charge_finished(
                _, i: datetime.datetime
            ) -> pyo.Constraint | pyo.Constraint.Skip:
                """
                Ensure charging is finished at charge_end_time.

                Adds a constraint for all timestamps at or after charge_end_time
                to enforce the soc to be at or above the end_soc.

                Parameters
                ----------
                _ : pyo.Block
                    The Pyomo block (not used).
                i : datetime.datetime
                    The current timestamp.

                Returns
                -------
                pyo.Constraint or pyo.Constraint.Skip
                    The constraint enforcing the soc at charge_end_time or a skip
                    constraint.
                """
                if i < self.battery.charge_end_time:
                    return pyo.Constraint.Skip
                return (
                    self.battery.end_soc * self.battery.capacity
                    <= block.soc[i]
                )

            block.charge_completion = pyo.Constraint(
                self.index, expr=charge_finished
            )

        # do not use the battery until its start
        if self.battery.charge_start_time is not None:
            # Prevent charge
            def charge_start(
                _, i: datetime.datetime
            ) -> pyo.Constraint | pyo.Constraint.Skip:
                """
                Prevent charging before charge start time.

                This constraint ensures that the battery cannot be charged
                before the specified charge start time.

                Parameters
                ----------
                _ : pyo.Block
                    The Pyomo block (not used).
                i : datetime.datetime
                    The current timestamp.

                Returns
                -------
                pyo.Constraint | pyo.Constraint.Skip
                    The constraint enforcing the charging prevention or a skip
                    constraint.
                """
                if i < self.battery.charge_start_time:
                    return (0, block.energy_sink[i], 0)
                return pyo.Constraint.Skip

            block.charge_start_time = pyo.Constraint(
                self.index, expr=charge_start
            )

            # Prevent Discharge
            if self.battery.max_discharge_power > 0:

                def discharge_start(
                    _, i: datetime.datetime
                ) -> pyo.Constraint | pyo.Constraint.Skip:
                    """
                    Prevent discharging before charge start time.

                    This constraint ensures that the battery cannot be
                    discharged before the specified charge start time.

                    Parameters
                    ----------
                    _ : pyo.Block
                        The Pyomo block (not used).
                    i : datetime.datetime
                        The current timestamp.

                    Returns
                    -------
                    pyo.Constraint | pyo.Constraint.Skip
                        The constraint enforcing the discharging prevention or
                        a skip constraint.
                    """
                    if i < self.battery.charge_start_time:
                        return (
                            0,
                            block.energy_source[i],
                            0,
                        )
                    return pyo.Constraint.Skip

                block.discharge_start_time = pyo.Constraint(
                    self.index, expr=discharge_start
                )

        if self.battery.min_charge_power > 0:

            def min_charge_power_constraint(
                _, i: datetime.datetime
            ) -> pyo.Constraint:
                """
                Ensure battery is charged with min_charge_power if charging.

                Set a lower bound on the charging power when the battery is
                charging.

                Parameters
                ----------
                _ : pyo.Block
                    The Pyomo block (not used).
                i : datetime.datetime
                    The current timestamp.

                Returns
                -------
                pyo.Constraint
                    The constraint enforcing the minimum charging power.
                """
                return (
                    block.energy_sink[i]
                    >= self.battery.min_charge_power
                    * get_period_length(i, self.index)[1]
                    * block.is_charging[i]
                )

            block.min_charge_power = pyo.Constraint(
                self.index, expr=min_charge_power_constraint
            )

        if self.battery.min_discharge_power > 0:

            def min_discharge_power_constraint(
                _, i: datetime.datetime
            ) -> pyo.Constraint:
                """
                Ensure battery power above min_discharge_power if discharging.

                Constraint that ensures the battery is discharged with
                min_discharge_power if it is discharged.

                Parameters
                ----------
                _ : pyo.Block
                    The Pyomo block (not used).
                i : datetime.datetime
                    The current timestamp.

                Returns
                -------
                pyo.Constraint
                    The constraint enforcing the minimum discharging power or a
                    skip constraint.
                """
                return (
                    block.energy_source[i]
                    >= self.battery.min_discharge_power
                    * get_period_length(i, self.index)[1]
                    * block.is_discharging[i]
                )

            block.min_discharge_power = pyo.Constraint(
                self.index, expr=min_discharge_power_constraint
            )

        if not self.battery.charging_is_interruptable:

            def uninterrupted_charging(
                _, i: datetime.datetime
            ) -> pyo.Constraint | pyo.Constraint.Skip:
                """
                Enforce uninterrupted charging once started.

                This constraint ensures that once the battery starts charging,
                it continues to charge at least at min_charge_power until the
                required charge is completed. Charging starts at
                charge_start_time and may stop afterwards, but can never
                restart.

                Parameters
                ----------
                _ : pyo.Block
                    The Pyomo block (not used).
                i : datetime.datetime
                    The current timestamp.

                Returns
                -------
                pyo.Constraint | pyo.Constraint.Skip
                    The constraint enforcing uninterrupted charging or a skip
                    constraint.
                """
                if i <= self.battery.charge_start_time:
                    return pyo.Constraint.Skip

                return (
                    block.is_charging[self.index.prev(i)]
                    >= block.is_charging[i]
                )

            def charge_must_start(
                _, i: datetime.datetime
            ) -> pyo.Constraint | pyo.Constraint.Skip:
                """
                Force charging to start at charge_start_time.

                This ensures the first charging period begins at the configured
                start time so the uninterrupted charging block is anchored.
                """
                if self.battery.charge_start_time is None:
                    return pyo.Constraint.Skip
                if i == self.battery.charge_start_time:
                    return block.is_charging[i] == 1
                if i < self.battery.charge_start_time:
                    return block.is_charging[i] == 0
                return pyo.Constraint.Skip

            block.uninterrupted_charging = pyo.Constraint(
                self.index, expr=uninterrupted_charging
            )
            block.charge_must_start = pyo.Constraint(
                self.index, expr=charge_must_start
            )

        return block
