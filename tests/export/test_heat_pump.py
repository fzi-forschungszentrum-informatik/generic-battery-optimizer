"""
Test suite for the HeatPump state of charge (SoC) calculation.

This class contains tests for verifying the correct calculation of the
state of charge (SoC) of a heat pump after optimization. The tests test
both the SoC values and the thermal energy storage (TES) temperature
values returned by the Exporter class.
"""

import pandas as pd
import pytest
from battery_optimizer.export import Exporter
from battery_optimizer.helpers.heat_pump_profile import (
    heat_loss_tank,
    tank_dimensions,
)
from battery_optimizer.model import Model
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.solver import Solver
from battery_optimizer.helpers.hplib import HpLibProfile, HpLibWrapper
from tests.helpers import find_solver

solver = find_solver("gurobi")


class TestHeatPumpSoC:
    """
    Test suite for the HeatPump state of charge (SoC) calculation.

    This class contains tests for verifying the correct calculation of the
    state of charge (SoC) of a heat pump after optimization. The tests test
    both the SoC values and the thermal energy storage (TES) temperature
    values returned by the Exporter class.
    """
    time_series = pd.date_range(
        start="2021-01-01 08:00:00+00:00",
        end="2021-01-01 10:00:00+00:00",
        freq="h",
    )

    # Input data
    buy_power = {
        time_series[0]: 1000000,
        time_series[1]: 1000000,
        time_series[2]: 0,
    }
    buy_price = {
        time_series[0]: 0,
        time_series[1]: 0,
        time_series[2]: 0,
    }

    outdoor_temperature = {
        time_series[0]: 15,
        time_series[1]: 0,
        time_series[2]: 0,
    }
    heat_source_temperature = {
        time_series[0]: 15,
        time_series[1]: 0,
        time_series[2]: 0,
    }
    hplib = HpLibWrapper(
        HpLibProfile(
            type="i-SHWAK V4 12",
            flow_temperature=35,
            output_temperature=55,
        )
    )
    cop_high = hplib.get_cop_output_temperature(
        heat_source_temperature, outdoor_temperature
    )
    cop_low = hplib.get_cop_flow_temperature(
        heat_source_temperature, outdoor_temperature
    )

    heat_pump = HeatPump(
        name="test-heat-pump",
        cop_output_temperature=cop_high,
        cop_flow_temperature=cop_low,
        flow_temperature=35,
        output_temperature=55,
        max_electric_power_hp=10,
        max_electric_power_hr=0,
        hp_switch_off_temperature=5,
        heat_demand={
            time_series[0]: 0,
            time_series[1]: 1,
            time_series[2]: 0,
        },
        outdoor_temperature=outdoor_temperature,
        heat_loss_tank=heat_loss_tank(*tank_dimensions(100)),
        tank_volume=100,
        max_temp_tes=60,
    )

    def test_heat_pump_soc(self):
        """
        Test the calculation of the heat pump's state of charge (SoC).

        This test verifies that the state of charge of the heat pump is
        calculated correctly after optimization. It checks that the returned
        SoC values are as expected for each time step.
        """
        if solver != "gurobi":
            pytest.skip(
                "Skipping this test as it requires the Gurobi solver to run"
            )

        # Optimization
        opt = Model(self.time_series)
        opt.add_buy_profile("buy", self.buy_power, self.buy_price)
        # BUG energy_sink.ub of this heat pump is None after adding it to the
        # model
        opt.add_heat_pump(self.heat_pump)
        opt.add_energy_paths()

        opt.generate_objective()
        Solver(solver).solve(opt.model)

        heat_pump_soc = Exporter(opt).get_heat_pump_soc()

        assert isinstance(heat_pump_soc, dict)
        assert "test-heat-pump" in heat_pump_soc
        assert len(heat_pump_soc) == 1
        assert heat_pump_soc["test-heat-pump"] == pytest.approx(
            {
                self.time_series[0]: 0.0,
                self.time_series[1]: 0.3503254333697084,
                self.time_series[2]: 0.0,
            },
            rel=1e-9,
            abs=1e-6,
        )

    def test_heat_pump_tes_temperature(self):
        """
        Test the calculation of the heat pump's TES temperature.

        This test verifies that the temperature of the thermal energy storage
        of the heat pump is calculated correctly after optimization. It checks
        that the returned temperature values are as expected for each time
        step.
        """
        if solver != "gurobi":
            pytest.skip(
                "Skipping this test as it requires the Gurobi solver to run"
            )

        # Optimization
        opt = Model(self.time_series)
        opt.add_buy_profile("buy", self.buy_power, self.buy_price)
        # BUG energy_sink.ub of this heat pump is None after adding it to the model
        opt.add_heat_pump(self.heat_pump)
        opt.add_energy_paths()

        opt.generate_objective()
        Solver(solver).solve(opt.model)

        tes_temp = Exporter(opt).get_heat_pump_tes_temperature()

        assert isinstance(tes_temp, dict)
        assert "test-heat-pump" in tes_temp
        assert len(tes_temp) == 1
        assert tes_temp["test-heat-pump"] == pytest.approx(
            {
                self.time_series[0]: 35,
                self.time_series[1]: 43.758135834242694,
                self.time_series[2]: 35,
            },
            rel=1e-9,
            abs=1e-6,
        )
