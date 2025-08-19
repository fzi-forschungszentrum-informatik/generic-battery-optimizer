import logging
import pyomo.environ as pyo
from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition

log = logging.getLogger(__name__)


class Solver:

    def __init__(
        self,
        solver: str = "glpk",
        tee: bool = False,
        result_file: str = "",
        options: dict[str, str | float] = {},
    ):
        """Initialize a solver

        Variables
        ---------
        solver : str
            Specify a solver to use. The default is glpk.
        tee : bool
            Print debug information of the solver when set to True.
        result_file : str
            Write an ILP file to disk. This works with Gurobi.
        options: dict
            Additional options to pass to the solver
            e.g. {"TimeLimit": 60, "MIPGap": 0.01}
        """
        self.solver = SolverFactory(solver)

        for key, value in options.items():
            self.solver.options[key] = value

        if result_file != "":
            self.solver.options["ResultFile"] = result_file

        self.tee = tee
        self.result_file = result_file

    def solve(self, model: pyo.ConcreteModel) -> pyo.ConcreteModel:
        """Solve the model

        This solves the model. set_up() needs to be called before solving can
        start.
        """
        log.info("Solving model")

        if self.result_file != "":
            with open(
                self.result_file.replace(".ilp", "_model.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                model.pprint(f)

        result = self.solver.solve(
            model, tee=self.tee, symbolic_solver_labels=True
        )

        # Check if the result has a feasible Solution
        if (result.solver.status == SolverStatus.ok) and (
            result.solver.termination_condition == TerminationCondition.optimal
        ):
            # The solution is optimal and feasible
            return result
        if result.solver.termination_condition in (
            TerminationCondition.unbounded,
            TerminationCondition.infeasible,
        ):
            # Do something when model is infeasible
            log.error(
                "The model is infeasible: %s",
                result.solver.termination_condition,
            )
        else:
            # Something else is wrong
            log.error("Solver Status: %s", result.solver.status)
        return None
