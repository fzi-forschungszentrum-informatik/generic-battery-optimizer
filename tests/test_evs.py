"""
Tests EV specific functionality.

Battery specific tests are located in test_battery.py.
"""
import pandas as pd
import pytest
from battery_optimizer.export import Exporter
from battery_optimizer.helpers.model_setup import (
    generate_common_time_series,
    reindex_profile,
)
from battery_optimizer.model import Model
from battery_optimizer.profiles.ev import EV
from battery_optimizer.solver import Solver
from tests.helpers import find_solver


class TestChargeTimes:
    """
    Test the EV charge start and end time constraints.

    The tests ensure that the EV charges and discharges only within the
    specified time windows and reaches the desired state of charge (SoC) at the
    specified end time.
    """

    def test_charge_end_past_last_timestamp(self):
        """
        Test the charging of an EV where charge_end_time is after last ts.

        Ensure that the end soc will be reached at the last timestamp when
        charge_end_time is after the last timestamp from the profile and
        the generate_common_time_series is used.
        """
        time_series = [pd.to_datetime("2025-12-11T13:58:05.129253Z")]
        time_series.extend(
            pd.date_range(
                start="2025-12-11T14:00:00Z",
                end="2025-12-12T01:45:00Z",
                freq="15min",
            )
        )

        pv_power = {
            time: price
            for time, price in zip(
                time_series,
                [
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -10536,
                    -15668,
                    -16781,
                    -6810,
                    0,
                    0,
                    -23311,
                    -35173,
                    -2398,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -21550,
                    -28200,
                    -17261,
                    0,
                    -12326,
                    -724,
                    -3187,
                    0,
                    -30316,
                    0,
                    0,
                    0,
                    0,
                    -157,
                    0,
                    0,
                    -10097,
                    -752,
                    0,
                    -3229,
                    0,
                    0,
                ],
            )
        }
        pv_price = {time: 0.0 for time in time_series}

        grid_power = {time: 1000000 for time in time_series}
        grid_price = {
            time: price
            for time, price in zip(
                time_series,
                [
                    33.717459999999996,
                    34.18275,
                    34.18275,
                    34.18275,
                    34.18275,
                    34.774179999999994,
                    34.774179999999994,
                    34.774179999999994,
                    34.774179999999994,
                    39.93283,
                    39.93283,
                    39.93283,
                    39.93283,
                    39.703160000000004,
                    39.703160000000004,
                    39.703160000000004,
                    39.703160000000004,
                    39.696020000000004,
                    39.696020000000004,
                    39.696020000000004,
                    39.696020000000004,
                    39.659130000000005,
                    39.659130000000005,
                    39.659130000000005,
                    39.659130000000005,
                    33.278349999999996,
                    33.278349999999996,
                    33.278349999999996,
                    33.278349999999996,
                    31.9753,
                    31.9753,
                    31.9753,
                    31.9753,
                    30.258129999999994,
                    30.258129999999994,
                    30.258129999999994,
                    30.258129999999994,
                    30.901919999999997,
                    30.901919999999997,
                    30.901919999999997,
                    30.901919999999997,
                    21.715119999999995,
                    21.715119999999995,
                    21.715119999999995,
                    21.715119999999995,
                    21.713929999999998,
                    21.713929999999998,
                    21.713929999999998,
                    21.713929999999998,
                ],
            )
        }

        sell_power = {
            time: power
            for time, power in zip(
                time_series,
                [
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -10536,
                    -15668,
                    -16781,
                    -6810,
                    0,
                    0,
                    -23311,
                    -35173,
                    -2398,
                    0,
                    0,
                    0,
                    0,
                    0,
                    -21550,
                    -28200,
                    -17261,
                    0,
                    -12326,
                    -724,
                    -3187,
                    0,
                    -30316,
                    0,
                    0,
                    0,
                    0,
                    -157,
                    0,
                    0,
                    -10097,
                    -752,
                    0,
                    -3229,
                    0,
                    0,
                ],
            )
        }
        sell_price = {time: 8 for time in time_series}

        fixed_consumption = {
            time: power
            for time, power in zip(
                time_series,
                [
                    28380,
                    27479,
                    27597,
                    27770,
                    27307,
                    27015,
                    26607,
                    26456,
                    26729,
                    26875,
                    26556,
                    25733,
                    24815,
                    23688,
                    23238,
                    23588,
                    23397,
                    22607,
                    21736,
                    21232,
                    21204,
                    20965,
                    20343,
                    19692,
                    19422,
                    19396,
                    18891,
                    20508,
                    23095,
                    21381,
                    18398,
                    17767,
                    18052,
                    18070,
                    17591,
                    17117,
                    16855,
                    16727,
                    16786,
                    16593,
                    16263,
                    16304,
                    16257,
                    16152,
                    16268,
                    16225,
                    16112,
                    16219,
                    16136,
                ],
            )
        }

        ev = EV.model_validate(
            {
                "name": "ev_battery",
                "start_soc": 0.2,
                "end_soc": 0.8,
                "charge_end_time": "2025-12-12T01:58:05.129253Z",
                "charge_start_time": "2025-12-11T13:58:05.129253Z",
                "capacity": 77000,
                "max_charge_power": 11000,
                "max_discharge_power": 0,
                "min_charge_power": 0,
                "min_discharge_power": 0,
                "charge_efficiency": 1,
                "discharge_efficiency": 1,
                "min_soc": 0,
                "max_soc": 1,
            }
        )
        time_series = generate_common_time_series(
            profiles=[
                pv_power,
                pv_price,
                grid_power,
                grid_price,
                sell_power,
                sell_price,
                fixed_consumption,
            ],
            evs=[ev],
        )

        model = Model(time_series)
        model.add_sell_profile(
            "pv",
            reindex_profile(pv_power, time_series),
            reindex_profile(pv_price, time_series),
        )
        model.add_buy_profile(
            "buy",
            reindex_profile(grid_power, time_series),
            reindex_profile(grid_price, time_series),
        )
        model.add_sell_profile(
            "sell",
            reindex_profile(sell_power, time_series),
            reindex_profile(sell_price, time_series),
        )
        model.add_fixed_consumption(
            "fixed_consumption",
            reindex_profile(fixed_consumption, time_series),
        )
        model.add_ev(ev)

        model.add_energy_paths()
        model.generate_objective()
        Solver(find_solver()).solve(model.model)

        df_export = Exporter(model).to_df()
        assert df_export.to_ev_soc().iloc[-1]["ev_battery"] == pytest.approx(
            0.8, 0.01
        )


class TestInterruptableCharging:
    """
    Test EV interruptable charging functionality.

    Generally AC charging of EVs is not interruptable. A minimum of 6A per
    phase is required to keep the connection alive. However, some EVs and
    charging stations support interruptable charging, allowing the charging
    process to be paused and resumed as needed. This test class verifies that
    the battery optimizer can handle EVs with non-interruptable charging.
    """

    time_series = pd.date_range(
        start="2025-12-11T06:00:00Z", end="2025-12-11T12:00:00Z", freq="1h"
    )

    buy_price = {
        time_series[0]: 50,  # Do not charge
        time_series[1]: 10,  # Charge
        time_series[2]: 10,  # Charge
        time_series[3]: 50,  # Do not charge (or charge less)
        time_series[4]: 40,  # Do not charge (or charge more)
        time_series[5]: 10,  # Charge
        time_series[6]: 0,
    }
    buy_power = {time: 10000 for time in time_series}

    ev = EV(
        name="ev",
        capacity=6000,
        start_soc=0,
        end_soc=1,
        charge_efficiency=1,
        charge_start_time=time_series[0],
        charge_end_time=time_series[-1],
        max_charge_power=2000,
        min_charge_power=500,
    )

    def test_non_interruptable_charging(self):
        """
        Test that an EV with non-interruptable charging charges without breaks.

        This test ensures that an EV configured for non-interruptable charging
        completes its charging session in one continuous block without any
        interruptions. It starts at timestamp 0 and charges until the required
        state of charge (SoC) is reached but may adjust the charging power as
        needed.
        """
        model = Model(self.time_series)

        model.add_buy_profile("buy", self.buy_power, self.buy_price)
        ev_interruptable = self.ev.model_copy(
            update={"charging_is_interruptable": False}
        )
        model.add_ev(ev_interruptable)

        model.add_energy_paths()
        model.generate_objective()
        Solver(find_solver()).solve(model.model)

        dict_export = Exporter(model).to_dict()
        assert sum(dict_export["ev"].values()) == -6000
        assert dict_export["ev"] == {
            self.time_series[0]: -500,
            self.time_series[1]: -2000,
            self.time_series[2]: -2000,
            self.time_series[3]: -500,
            self.time_series[4]: -500,
            self.time_series[5]: -500,
            self.time_series[6]: 0,
        }

    def test_interruptable_charging(self):
        """
        Test that an EV with interruptable charging can be charged in parts.

        This test ensures that an EV configured for interruptable charging can
        be charged in multiple segments rather than requiring a continuous
        charging session.
        """
        model = Model(self.time_series)

        model.add_buy_profile("buy", self.buy_power, self.buy_price)
        ev_interruptable = self.ev.model_copy(
            update={"charging_is_interruptable": True}
        )
        model.add_ev(ev_interruptable)

        model.add_energy_paths()
        model.generate_objective()
        Solver(find_solver()).solve(model.model)

        dict_export = Exporter(model).to_dict()
        assert sum(dict_export["ev"].values()) == -6000
        assert dict_export["ev"] == {
            self.time_series[0]: 0,
            self.time_series[1]: -2000,
            self.time_series[2]: -2000,
            self.time_series[3]: 0,
            self.time_series[4]: 0,
            self.time_series[5]: -2000,
            self.time_series[6]: 0,
        }

    def test_non_interruptable_charging_at_second_time_step(self):
        """
        Test non-interruptable charging starting at the second time step.

        This test ensures that an EV configured for non-interruptable charging
        can start its charging session at the second timestamp and continue
        without interruptions until the required state of charge (SoC) is
        reached.
        """
        model = Model(self.time_series)

        model.add_buy_profile("buy", self.buy_power, self.buy_price)
        ev_interruptable = self.ev.model_copy(
            update={
                "charging_is_interruptable": False,
                "charge_start_time": self.time_series[1],
            }
        )
        model.add_ev(ev_interruptable)

        model.add_energy_paths()
        model.generate_objective()
        Solver(find_solver()).solve(model.model)

        dict_export = Exporter(model).to_dict()
        assert sum(dict_export["ev"].values()) == -6000
        assert dict_export["ev"] == {
            self.time_series[0]: 0,
            self.time_series[1]: -2000,
            self.time_series[2]: -2000,
            self.time_series[3]: -500,
            self.time_series[4]: -500,
            self.time_series[5]: -1000,
            self.time_series[6]: 0,
        }
