"""
Optimize an energy system based on profile stacks.

Provides a simple interface to optimize an energy system with batteries,
electric vehicles and heat pumps.
For more complex use cases please use the full model.
"""

import logging
import warnings
from battery_optimizer.helpers.parse_profile_stacks import (
    parse_profiles,
)
from battery_optimizer.model import Model
from battery_optimizer.profiles.battery import Battery
from battery_optimizer.profiles.ev import EV
from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.profiles.profiles import ProfileStack

log = logging.getLogger(__name__)


class ProfileStackProblem:
    """
    Optimize the energy distribution of an energy system.

    Provides a simple interface to optimize an energy system with batteries,
    electric vehicles and heat pumps.
    For more complex use cases please use the full model.

    Parameters
    ----------
    buy_prices : ProfileStack
        All profiles energy can be bought from.
    sell_prices : ProfileStack
        All profiles energy can be sold to.
    fixed_consumption : ProfileStack
        All fixed consumption data for the model.
    batteries : List[Battery]
        All batteries that can be used.
    evs : List[EV]
        All electric vehicles that can be used.
    heat_pumps : List[HeatPump]
        All heat pumps that can be used.
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
        evs: list[EV] | None = None,
        heat_pumps: list[HeatPump] | None = None,
    ) -> None:
        """
        Format all input data and set up the base model.

        Creates lists from all input data sources to be used with the model and
        initializes the base structure of the model. Before using the model it
        needs to be populated.
        Differing timestamps will be merged to the highest resolution and
        whenever the granularity of a profile is increased as a result from
        another profile or battery the power is assumed to be the same as the
        previous power.

        Parameters
        ----------
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
        evs : List[EV]
            A list of electric vehicles that can be used in the optimization.
        heat_pumps : List[HeatPump]
            A list of heat pumps that provide heating energy for a household.

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

        # DEPRECATED - remove in 5.0.0
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            if batteries is not None:
                for battery in batteries:
                    if battery.end_soc_time is not None:
                        temp_index.append(battery.end_soc_time)
                    if battery.start_soc_time is not None:
                        temp_index.append(battery.start_soc_time)

        if evs is not None:
            for ev in evs:
                if ev.charge_end_time is not None:
                    temp_index.append(ev.charge_end_time)
                if ev.charge_start_time is not None:
                    temp_index.append(ev.charge_start_time)
        log.debug("Temporary Index:")
        log.debug(temp_index)

        index = list(dict.fromkeys(temp_index))
        index.sort()
        log.debug("Index of the model:")
        log.debug(index)

        # Capture the device restrictions (limit_to) of all profiles before
        # they are parsed into plain DataFrames
        self._buy_limit_to: dict[str, list[str] | None] = {}
        self._sell_limit_to: dict[str, list[str] | None] = {}
        self._buy_local_generation: dict[str, bool] = {}
        if buy_prices is not None:
            self._buy_limit_to = {
                name: getattr(profile, "limit_to", None)
                for name, profile in buy_prices.profiles.items()
            }
            self._buy_local_generation = {
                name: getattr(profile, "local_generation", False)
                for name, profile in buy_prices.profiles.items()
            }
        if sell_prices is not None:
            self._sell_limit_to = {
                name: getattr(profile, "limit_to", None)
                for name, profile in sell_prices.profiles.items()
            }

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

        log.debug("Initializing electric vehicles")
        if evs is not None:
            self.evs = evs
            log.debug(self.evs)
        else:
            self.evs = []

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
        """
        Set up the model for optimization.

        This will add all buy price profiles, sell price profiles,
        fixed consumptions and batteries to the model.
        All Energy paths are created and the objective is generated.

        The model will be saved to model.log when running in debug mode.
        """
        log.info("Generating model structure")
        # for each profile in prices add it to the model
        log.debug("Adding buy profiles to model")
        for name, profile in self.prices.items():
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

        # add each ev to the model
        log.debug("Adding all electric vehicles to the model")
        for ev in self.evs:
            self.model.add_ev(ev)

        log.debug("Adding all heat pumps to the model")
        for heat_pump in self.heat_pumps:
            self.model.add_heat_pump(heat_pump)

        # add all paths
        log.debug("Generating energy paths")
        self.model.add_energy_paths()
        # restrict energy paths of device-limited profiles (limit_to)
        self._apply_profile_flow_restrictions()
        # generate objective
        log.debug("Generating objective")
        self.model.generate_objective()
        # print the model to console
        if log.getEffectiveLevel() <= logging.DEBUG:
            with open("model.log", "w") as file:
                self.model.model.pprint(file)

    def _apply_profile_flow_restrictions(self) -> None:
        """
        Enforce the device restrictions (limit_to) of all profiles.

        A profile with limit_to may only exchange energy with model blocks
        whose name contains one of its tokens (typically device ids). The
        matched devices in turn buy grid energy exclusively from the limited
        buy profiles matching them (so a power cap of such a profile is a
        hard cap for those devices) and sell exclusively to the limited sell
        profiles matching them, falling back to the unrestricted profiles
        only while no limited profile of that direction matches them.
        Devices may exchange energy with each other only when they are
        restricted by the same limited profiles in both directions - this
        corresponds to separately metered device groups and keeps a
        billing based on the summed power of each group consistent with
        the optimized energy flows.

        Buy profiles marked as local_generation (generation behind the grid
        connection point, e.g. PV) are exempt on the purchase side: they may
        feed every device by default, or only the devices matching their own
        limit_to if one is set (an empty list restricts them to selling).
        On the feed-in side they behave like devices (limited sell profiles
        claiming them take precedence over unrestricted ones).
        """
        limited_buys = {
            name: tokens
            for name, tokens in self._buy_limit_to.items()
            if tokens is not None
            and not self._buy_local_generation.get(name, False)
        }
        limited_sells = {
            name: tokens
            for name, tokens in self._sell_limit_to.items()
            if tokens is not None
        }
        restricted_generation = any(
            self._buy_limit_to.get(name) is not None
            for name, local in self._buy_local_generation.items()
            if local
        )
        if not limited_buys and not limited_sells \
                and not restricted_generation:
            return

        def match(tokens: list[str], block_name: str) -> bool:
            return any(token in block_name for token in tokens)

        def buy_claims(block_name: str) -> frozenset[str]:
            return frozenset(
                name
                for name, tokens in limited_buys.items()
                if match(tokens, block_name)
            )

        def sell_claims(block_name: str) -> frozenset[str]:
            return frozenset(
                name
                for name, tokens in limited_sells.items()
                if match(tokens, block_name)
            )

        def signature(block_name: str) -> tuple[frozenset, frozenset]:
            return buy_claims(block_name), sell_claims(block_name)

        def is_flow_allowed(
            source: tuple[str, str], sink: tuple[str, str]
        ) -> bool:
            source_type, source_name = source
            sink_type, sink_name = sink
            if source_type == "buy_profiles":
                source_limit = self._buy_limit_to.get(source_name)
                local = self._buy_local_generation.get(source_name, False)
                if sink_type == "sell_profiles":
                    sink_limit = self._sell_limit_to.get(sink_name)
                    if sink_limit is not None:
                        # a limited sell profile only accepts its devices
                        # (including local generation named after one)
                        return match(sink_limit, source_name)
                    if local:
                        # local generation falls back to unrestricted sell
                        # profiles only while no limited one claims it
                        return not sell_claims(source_name)
                    if source_limit is not None:
                        # no resale of a device-limited grid tariff
                        return False
                    # plain grid tariff to sell profile (arbitrage path)
                    return True
                # sink is a device
                if local:
                    # local generation feeds every device by default,
                    # or only its own limit_to if one is set
                    if source_limit is not None:
                        return match(source_limit, sink_name)
                    return True
                if source_limit is not None:
                    # a limited buy profile only feeds its devices
                    return match(source_limit, sink_name)
                # an unrestricted grid tariff only feeds unclaimed devices
                return not buy_claims(sink_name)
            if sink_type == "sell_profiles":
                tokens = self._sell_limit_to.get(sink_name)
                if tokens is not None:
                    return match(tokens, source_name)
                # devices fall back to unrestricted sell profiles only
                # while no limited sell profile claims them
                return not sell_claims(source_name)
            # device to device: only within the same restriction group
            return signature(source_name) == signature(sink_name)

        self.model.apply_flow_restrictions(is_flow_allowed)
