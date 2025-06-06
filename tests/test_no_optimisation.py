from battery_optimizer import optimize
from helpers import find_solver


class TestNoOptimisation:
    def test_no_profiles(self):
        """No profiles at all

        No profiles are given to the optimizer at all and it should return an
        error.
        """
        try:
            optimize(solver=find_solver())
        except ValueError as e:
            assert (
                str(e)
                == "At least one of [buy_prices, sell_prices, fixed_consumption] "
                "must contain values"
            )
