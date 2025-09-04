import pandas as pd
from battery_optimizer.export import Exporter
from battery_optimizer.model import Model
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.solver import Solver
from tests.helpers import find_solver


class TestHeatPumpSoc:
    time_series = pd.date_range(
        start="2021-01-01 08:00:00+00:00",
        end="2021-01-01 10:00:00+00:00",
        freq="H",
    )

    # Input data
    buy_power = {
        time_series[0]: 10,
        time_series[1]: 10,
        time_series[2]: 0,
    }
    buy_price = {
        time_series[0]: 1,
        time_series[1]: 4,
        time_series[2]: 0,
    }

    sell = {
        time_series[0]: 10,
        time_series[1]: 10,
        time_series[2]: 0,
    }
    sell_price = {
        time_series[0]: 0,
        time_series[1]: 3,
        time_series[2]: 0,
    }

    heat_pump = HeatPump(
        name="test-heat-pump",
        type="Bosch Compress 3000 AWS-11 MS-T",
        flow_temperature=35 + 273.15,
        output_temperature=55 + 273.15,
        max_electric_power_hp=10,
        max_electric_power_hr=0,
        hp_switch_off_temperature=5 + 273.15,
        heat_demand={
            time_series[0]: 0,
            time_series[1]: 5,
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
    )

    def test_heat_pump_soc(self):
        # Optimization
        opt = Model(self.time_series)
        opt.add_buy_profile("buy", self.buy_power, self.buy_price)
        opt.add_sell_profile("sell", self.sell, self.sell_price)
        opt.add_heat_pump(self.heat_pump)
        opt.add_energy_paths()

        opt.generate_objective()
        Solver(find_solver()).solve(opt.model)

        heat_pump_soc = Exporter(opt).get_heat_pump_soc()

        assert isinstance(heat_pump_soc, dict)
        assert "test-heat-pump" in heat_pump_soc
        assert heat_pump_soc == {
            "test-heat-pump": {
                self.time_series[0]: 0.0,
                self.time_series[1]: 0.0,
                self.time_series[2]: 0.0,
            }
        }
