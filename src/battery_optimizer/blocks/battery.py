"""
Battery block for optimization model.

This block models a household battery with charging and discharging
capabilities. Charging and discharging efficiencies as well as maximum
charge and discharge power are taken into account.
"""

import datetime
import pyomo.environ as pyo
import warnings
from battery_optimizer.blocks.base import BaseBlock
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.profiles.battery import Battery


class NewBatteryBlock(BaseBlock):
    """
    Battery block for optimization model.

    This block models a household battery with charging and discharging
    capabilities. Charging and discharging efficiencies as well as maximum
    charge and discharge power are taken into account.

    Parameters
    ----------
    index : pyo.Set
        The index of datetimes for the optimization model.
    battery : Battery
        The battery profile containing all relevant information about the
        battery.
    """
    def __init__(self, index: pyo.Set, battery: Battery):
        """
        Initialize the battery block.

        Store the index and battery profile and initialize the base block.

        Parameters
        ----------
        index : pyo.Set
            The index of datetimes for the optimization model.
        battery : Battery
            The battery profile containing all relevant information about the
            battery.
        """
        super().__init__(index)
        self.battery = battery

    def _populate_block(self, block: pyo.Block) -> pyo.Block:
        """
        Build the battery block.

        Adds all necessary variables and constraints to the provided Pyomo
        block to simulate the battery behavior.

        Parameters
        ----------
        block : pyo.Block
            The Pyomo block to populate with battery variables and constraints.

        Returns
        -------
        pyo.Block
            The populated Pyomo block with battery variables and constraints.
        """
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
        def soc_rule(_, i: datetime.datetime) -> pyo.Expression:
            """
            Calculate the SOC of the battery.

            SOC rule calculating the current energy state of the battery and
            change in energy for the first timestamp and the change of energy
            relative to the previous timestamps energy for all other
            timestamps.

            Parameters
            ----------
            _ : pyo.Block
                The Pyomo block (not used).
            i : datetime.datetime
                The current timestamp.

            Returns
            -------
            pyo.Expression
                The soc expression for the current timestamp with the soc that
                will be reached at the end of the timestamp.
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

        # Enforce that the battery can only charge or discharge
        # We only add this if needed to reduce complexity
        # This is needed if charge and discharge efficiency is 100% or
        # minimum discharge or minimum charge power is set

        # Charging
        block.is_charging = pyo.Var(self.index, within=pyo.Binary)

        def enforce_binary_charging(
            _, i: datetime.datetime
        ) -> pyo.Constraint | pyo.Constraint.Skip:
            """
            Enforce block.is_charging to be 1 if charge_power > 0.

            Sets the binary variable is_charging to 1 if there is any
            charging power in the current timestamp.

            Parameters
            ----------
            _ : pyo.Block
                The Pyomo block (not used).
            i : datetime.datetime
                The current timestamp.

            Returns
            -------
            pyo.Constraint | pyo.Constraint.Skip
                The constraint enforcing the charging condition or a skip
                constraint.
            """
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
            """
            Enforce block.is_discharging to be 1 if discharge_power > 0.

            Sets the binary variable is_discharging to 1 if there is any
            discharging power in the current timestamp.

            Parameters
            ----------
            _ : pyo.Block
                The Pyomo block (not used).
            i : datetime.datetime
                The current timestamp.

            Returns
            -------
            pyo.Constraint | pyo.Constraint.Skip
                The constraint enforcing the discharging condition or a skip
                constraint.
            """
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
            """
            Enforce battery can only charge or discharge.

            Ensures that the battery can only be in a charging or discharging
            state in the current timestamp.

            Parameters
            ----------
            _ : pyo.Block
                The Pyomo block (not used).
            i : datetime.datetime
                The current timestamp.

            Returns
            -------
            pyo.Constraint | pyo.Constraint.Skip
                The constraint enforcing the charging condition or a skip
                constraint.
            """
            return block.is_charging[i] + block.is_discharging[i] <= 1

        block.enforce_binary_power = pyo.Constraint(
            self.index, rule=enforce_binary_charging_discharging
        )

        # min and max soc constraints
        if self.battery.min_soc > 0:

            def min_soc_constraint(_, i: datetime.datetime) -> pyo.Constraint:
                """
                Ensure battery soc is always above min_soc.

                Constraint that ensures the battery soc is always above the
                minimum soc.

                Parameters
                ----------
                _ : pyo.Block
                    The Pyomo block (not used).
                i : datetime.datetime
                    The current timestamp.

                Returns
                -------
                pyo.Constraint
                    The constraint enforcing the minimum soc.
                """
                return (
                    block.soc[i]
                    >= self.battery.min_soc * self.battery.capacity
                )

            block.min_soc_constraint = pyo.Constraint(
                self.index, expr=min_soc_constraint
            )

        if self.battery.max_soc < 1:

            def max_soc_constraint(_, i: datetime.datetime) -> pyo.Constraint:
                """
                Ensure battery soc is always below max_soc.

                Constraint that ensures the battery soc is always below the
                maximum soc.

                Parameters
                ----------
                _ : pyo.Block
                    The Pyomo block (not used).
                i : datetime.datetime
                    The current timestamp.

                Returns
                -------
                pyo.Constraint
                    The constraint enforcing the maximum soc.
                """
                return (
                    block.soc[i]
                    <= self.battery.max_soc * self.battery.capacity
                )

            block.max_soc_constraint = pyo.Constraint(
                self.index, expr=max_soc_constraint
            )

        return block


# DEPRECATED - remove in 5.0.0
class BatteryBlock(NewBatteryBlock):
    """
    Battery block for optimization model.

    This block models a household battery with charging and discharging
    capabilities. Charging and discharging efficiencies as well as maximum
    charge and discharge power are taken into account.

    Parameters
    ----------
    index : pyo.Set
        The index of datetimes for the optimization model.
    battery : Battery
        The battery profile containing all relevant information about the
        battery.
    """

    def __init__(self, index: pyo.Set, battery: Battery):
        """
        Initialize the battery block.

        Store the index and battery profile and initialize the base block.

        Parameters
        ----------
        index : pyo.Set
            The index of datetimes for the optimization model.
        battery : Battery
            The battery profile containing all relevant information about the
            battery.
        """
        super().__init__(index, battery)

    def _populate_block(self, block: pyo.Block) -> pyo.Block:
        """
        Build the battery block.

        Adds all necessary variables and constraints to the provided Pyomo
        block to simulate the battery behavior.

        Parameters
        ----------
        block : pyo.Block
            The Pyomo block to populate with battery variables and constraints.

        Returns
        -------
        pyo.Block
            The populated Pyomo block with battery variables and constraints.
        """
        block = super()._populate_block(block)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            end_soc_time = getattr(self.battery, "end_soc_time", None)
        if end_soc_time is not None:

            # BUG This ensures soc at the end of the end_soc_time timestamp
            # but should enforce it at the beginning of the timestamp (t-1
            # needs the soc already to be at end_soc)
            def charge_finished(
                _, i: datetime.datetime
            ) -> pyo.Constraint | pyo.Constraint.Skip:
                """
                Ensure charging is finished at end_soc_time.

                Adds a constraint for all timestamps at or after end_soc_time
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
                    The constraint enforcing the soc at end_soc_time or a skip
                    constraint.
                """
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

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            start_soc_time = getattr(self.battery, "start_soc_time", None)
        if start_soc_time is not None:
            # Prevent charge
            def charge_start(
                _, i: datetime.datetime
            ) -> pyo.Constraint | pyo.Constraint.Skip:
                """
                Prevent charging before start_soc_time.

                This constraint ensures that the battery cannot be charged
                before the specified start_soc_time.

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
                if i < self.battery.start_soc_time:
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
                    Prevent discharging before start_soc_time.

                    This constraint ensures that the battery cannot be
                    discharged before the specified start_soc_time.

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

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            min_charge_power = self.battery.min_charge_power
        if min_charge_power > 0:

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

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            min_discharge_power = self.battery.min_discharge_power
        if min_discharge_power > 0:

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

        return block
