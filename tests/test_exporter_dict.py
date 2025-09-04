import pandas as pd

from battery_optimizer.export import Exporter
from battery_optimizer.model import Model
from battery_optimizer.profiles.battery import Battery
from battery_optimizer.solver import Solver
from helpers import find_solver


class TestExporterDict:
    time_series = pd.date_range(
        start="2021-01-01 08:00:00", end="2021-01-01 10:00:00", freq="H"
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

    battery = Battery(
        name="test-battery",
        start_soc=0,
        end_soc=0,
        capacity=10000,
        max_charge_power=10000,
        max_discharge_power=10000,
        charge_efficiency=1,
        discharge_efficiency=1,
    )

    def test_exporter_dict_buy_sell_battery(self):
        """
        Tests the Exporter class's to_dict method for correct export of buy,
        sell, and battery power profiles
        after running an optimization model.

        The test performs the following steps:
        1. Initializes an optimization model with time series data.
        2. Adds buy and sell power profiles with corresponding prices.
        3. Adds a battery to the model.
        4. Generates energy paths and the objective function.
        5. Solves the optimization model.
        6. Exports the results to a dictionary using the Exporter class.
        7. Asserts that the exported buy, sell, and battery profiles match
           expected values for each time step.
        """
        # Optimization
        opt = Model(self.time_series)
        opt.add_buy_profile("buy", self.buy_power, self.buy_price)
        opt.add_sell_profile("sell", self.sell, self.sell_price)
        opt.add_battery(self.battery)
        opt.add_energy_paths()

        opt.generate_objective()
        Solver(find_solver()).solve(opt.model)

        export = Exporter(opt).to_dict()

        # Assert power profiles
        assert export["buy"] == {
            self.time_series[0]: 10,
            self.time_series[1]: 0,
            self.time_series[2]: 0,
        }

        assert export["sell"] == {
            self.time_series[0]: 0,
            self.time_series[1]: -10,
            self.time_series[2]: 0,
        }

        # Assert battery profiles
        assert export["test-battery"] == {
            self.time_series[0]: -10,
            self.time_series[1]: 10,
            self.time_series[2]: 0,
        }
