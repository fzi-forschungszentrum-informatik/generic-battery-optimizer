import logging
from typing import List
import pandas as pd
from battery_optimizer.helpers.parse_profile_stacks import (
    parse_profiles,
)
from battery_optimizer.model import Model
from battery_optimizer.profiles.battery_profile import Battery
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.profiles.profiles import ProfileStack

log = logging.getLogger(__name__)


class ProfileStackProblem:
    """Optimize the energy distribution of an energy system.

    Attributes
    ----------
    buy_prices : ProfileStack
        All profiles energy can be bought from.
    sell_prices : ProfileStack
        All profiles energy can be sold to.
    fixed_consumption : ProfileStack
        All fixed consumption data for the model.
    batteries : List[Battery]
        All batteries that can be used.
    """

    # TODO Erzeugtes Modell abspeichern können, dann kann man es mit verschiedenen Solvern nutzen
    # TODO Neuordnen: Instanz Optimizer kapselt nur noch Optimierer.
    # TODO Wenn optimizer.solve(model) aufgeruft, dann wird modell übergeben und gesolved.
    # TODO solve() muss in die Optimizer Klasse, dann kann der Optimierer übergeben werden
    # TODO alles export muss in ne exporter Klasse
    def __init__(
        self,
        buy_prices: ProfileStack | None = None,
        sell_prices: ProfileStack | None = None,
        fixed_consumption: ProfileStack | None = None,
        batteries: list[Battery] | None = None,
        heat_pumps: list[HeatPump] | None = None,
    ) -> None:
        """Format all input data and set up the base model

        Creates lists from all input data sources to be used with the model and
        initializes the base structure of the model. Before using the model it
        needs to be populated.
        Differing timestamps will be merged to the highest resolution and
        whenever the granularity of a profile is increased as a result from
        another profile or battery the power is assumed to be the same as the
        previous power.

        Variables
        ---------
        buy_prices : ProfileStack
            All profiles to buy energy from.
            Price is assumed to be in ct/kWh.
            Power is assumed to be in W.
            If none of the profiles has a price_above specified a "padding"
            profile is added to the stack to prevent infeasible model results.
            If this padding profile is used the power demand from hard
            constraints can not be fulfilled at that point in time.
        sell_prices : ProfileStack
            All profiles to sell energy to.
            Price is assumed to be in ct/kWh.
            Power is assumed to be in W.
        fixed_consumption : ProfileStack
            A list of fixed consumption profiles.
            Power is assumed to be in W.
            for the electricity during this time period (unused here).
        batteries : List[Battery]
            A list of batteries that can be used in the optimization.

        Raises
        ------
        ValueError
            If none of the input stacks contain any data.
        """
        # TODO Hier noch nichts lösen, nur initialisieren
        # Lösen dann in set up oder so
        log.info("Initializing Optimizer")
        # get all timestamps (build index)
        log.debug("Generating model index")
        temp_index = []

        for stack in [buy_prices, sell_prices, fixed_consumption]:
            if stack is not None:
                for timestamp in stack.index.tolist():
                    temp_index.append(timestamp)

        # TODO Refactor to other function and require working indices
        if temp_index == []:
            raise ValueError(
                "At least one of [buy_prices, sell_prices, fixed_consumption] "
                "must contain values"
            )

        if batteries is not None:
            for battery in batteries:
                if battery.end_soc_time is not None:
                    temp_index.append(battery.end_soc_time)
                if battery.start_soc_time is not None:
                    temp_index.append(battery.start_soc_time)
        log.debug("Temporary Index:")
        log.debug(temp_index)

        # remove duplicates
        index: List[pd.Timestamp] = []
        for item in temp_index:
            if item not in index:
                index.append(item)
        # sort the index
        index.sort()
        log.debug("Index of the model:")
        log.debug(index)

        # init optimizer
        log.debug("Initializing buy prices")
        if buy_prices is not None:
            # TODO macht parse_profiles as an den Einheiten oder bleibt es bei ct/kWh und W?
            self.prices = parse_profiles(
                buy_prices, index, add_padding_profile=False
            )
            log.debug(self.prices)
        else:
            self.prices = {}

        log.debug("Initializing sell prices")
        if sell_prices is not None:
            self.sell_prices = parse_profiles(sell_prices, index)
            log.debug(self.sell_prices)
        else:
            self.sell_prices = {}

        log.debug("Initializing fixed consumption")
        if fixed_consumption is not None:
            self.fixed_consumption = parse_profiles(fixed_consumption, index)
            log.debug(self.fixed_consumption)
        else:
            self.fixed_consumption = {}

        log.debug("Initializing batteries")
        if batteries is not None:
            self.batteries = batteries
            log.debug(self.batteries)
        else:
            self.batteries = []

        log.debug("Initializing heat pumps")
        if heat_pumps is not None:
            self.heat_pumps = heat_pumps
            log.debug(self.heat_pumps)
        else:
            self.heat_pumps = []

        log.debug("Initializing model structure")
        self.model = Model(index)
        if log.getEffectiveLevel() <= logging.DEBUG:
            self.model.model.display()

    def set_up(self):
        """Set up the model for optimization

        This will add all buy price profiles, sell price profiles,
        fixed consumptions and batteries to the model.
        All Energy paths are created and the objective is generated.

        The model will be saved to model.log when running in debug mode
        """
        log.info("Generating model structure")
        # for each profile in prices add it to the model
        log.debug("Adding buy profiles to model")
        for name, profile in self.prices.items():
            print(profile.to_dict())
            self.model.add_buy_profile(
                name, profile.to_dict()["energy"], profile.to_dict()["price"]
            )

        # add all sell prices to the model
        log.debug("Adding sell profiles to model")
        for name, profile in self.sell_prices.items():
            self.model.add_sell_profile(
                name, profile.to_dict()["energy"], profile.to_dict()["price"]
            )

        # add all fixed consumptions
        log.debug("Adding all fixed consumptions to model")
        for name, profile in self.fixed_consumption.items():
            self.model.add_fixed_consumption(name, profile["energy"].to_dict())

        # add each battery to the model
        log.debug("Adding all batteries to the model")
        for battery in self.batteries:
            self.model.add_battery(battery)

        log.debug("Adding all heat pumps to the model")
        for heat_pump in self.heat_pumps:
            self.model.add_heat_pump(heat_pump)

        # add all paths
        log.debug("Generating energy paths")
        self.model.add_energy_paths()
        # generate objective
        log.debug("Generating objective")
        self.model.generate_objective()
        # print the model to console
        if log.getEffectiveLevel() <= logging.DEBUG:
            with open("model.log", "w") as file:
                self.model.model.pprint(file)
