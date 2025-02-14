from battery_optimizer.profiles.profiles import PowerPriceProfile, ProfileStack
from pyomo.opt import SolverFactory
import pandas as pd
import os


# Method to create the profiles
def get_profiles(
    time_series: pd.DatetimeIndex, profiles: dict[str, pd.DataFrame]
):
    """Create a ProfileStack from a dictionary of profiles.

    Input price goes first, then input power."""
    opt_profiles = []
    for key, value in profiles.items():
        opt_profiles.append(
            PowerPriceProfile(
                index=time_series,
                price=value["input_price"],
                power=value["input_power"],
                name=key,
            )
        )
    return ProfileStack(opt_profiles)


def find_solver(solver: str = None) -> str:
    """Find the solver for a test.

    Checks if the environment variable "SOLVER" is set. If so it returns the
    specified solver.
    Otherwise it will check the solver parameter for availability and if this
    is None the system is searched for the Gurobi and glpk solvers and
    return the first one found.

    Parameters
    ----------
    solver : str, optional
        The solver to use to search for

    Returns
    -------
    str
        The name of the solver that is available on the system.
    """
    # Find environment variable solver
    if os.getenv("SOLVER"):
        if not SolverFactory(os.getenv("SOLVER")).available():
            raise ValueError(
                f"Solver {os.getenv('SOLVER')} is not available on the system"
            )
        return os.getenv("SOLVER")
    # Find solver parameter
    if solver:
        if not SolverFactory(solver).available():
            raise ValueError(f"Solver {solver} is not available on the system")
        return solver
    # Try to find an installed solver
    for solver in ["gurobi", "glpk"]:
        if SolverFactory(solver).available():
            return solver
    # No solver found
    return None
