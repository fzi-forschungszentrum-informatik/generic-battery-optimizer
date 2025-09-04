import pandas as pd
import pytest
from battery_optimizer.export import Exporter
from battery_optimizer.model import Model
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.solver import Solver
from tests.helpers import find_solver

solver = find_solver("gurobi")


class TestHeatPumpSoC:
    time_series = pd.date_range(
        start="2021-01-01 08:00:00+00:00",
        end="2021-01-01 10:00:00+00:00",
        freq="H",
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

    heat_pump = HeatPump(
        name="test-heat-pump",
        type="i-SHWAK V4 12",
        flow_temperature=35 + 273.15,
        output_temperature=55 + 273.15,
        max_electric_power_hp=10,
        max_electric_power_hr=0,
        hp_switch_off_temperature=5 + 273.15,
        heat_demand={
            time_series[0]: 0,
            time_series[1]: 1,
            time_series[2]: 0,
        },
        outdoor_temperature={
            time_series[0]: 15 + 273.15,
            time_series[1]: 0 + 273.15,
            time_series[2]: 0 + 273.15,
        },
        heat_source_temperature={
            time_series[0]: 15 + 273.15,
            time_series[1]: 0 + 273.15,
            time_series[2]: 0 + 273.15,
        },
        tank_volume=100,
        max_temp_tes=60 + 273.15,
    )

    def test_heat_pump_soc(self):
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
                self.time_series[0]: 308.15,
                self.time_series[1]: 316.90813583424267,
                self.time_series[2]: 308.15,
            },
            rel=1e-9,
            abs=1e-6,
        )
