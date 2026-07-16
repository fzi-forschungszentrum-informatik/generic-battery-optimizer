import numpy as np
import pandas as pd
from typing import List, Optional, Union
import logging


logger = logging.getLogger(__name__)


class PowerPriceProfile(pd.DataFrame):
    """
    Base Profile defining one time- and load-variable tariff in one power
    direction
    """

    def __init__(
        self,
        index: pd.DatetimeIndex,
        price: Optional[List] = None,
        power: Optional[List] = None,
        feed_in: bool = False,
        name: str = None,
    ):
        """
        :param index: Required: Datetime index for the timespan when the
        profile is valid

        :param power: Optional: Limit to which power this profile is valid.
        For exceeding this power, the price of the next profile becomes valid.
        If there is no other profile, the power can not be exceeded.

        :param price: Optional: price for energy in ct/kWh, valid below the
        power limit. Above the limit, this price is not valid.

        :param feed_in: Optional: Flag defining whether this profile is valid
        for feed_in, meaning power direction from household to the grid.
        If false, the PowerPriceProfile is valid for energy drawn from the grid

        :param name: Unique name to identify the profile.
        """
        if not type(index) == pd.DatetimeIndex:
            raise TypeError("Only DatetimeIndex is allowed as index.")

        if power is None:
            power = [np.nan for _ in range(len(index))]

        if price is None:
            price = [np.nan for _ in range(len(index))]

        super().__init__(
            index=index, data={"price": price, "power": power,},
        )
        self.feed_in = feed_in
        self.name = name

    def __add__(self, other):
        if not self.feed_in == other.feed_in:
            raise ValueError(
                "Can only add profiles for the same energy direction (feed_in "
                "must be the same)"
            )
        if isinstance(other, ProfileStack):
            other.add_ppp(self)
            return other

        elif isinstance(other, PowerPriceProfile):
            if self.power.isna().all() and other.power.isna().all():  # no power defined
                sum_price = self.price + other.price
                return PowerPriceProfile(
                    index=self.index,
                    price=sum_price,
                    name=(
                        self.name + "+" + other.name if self.name and other.name else ""
                    ),
                )
            else:
                return ProfileStack([self, other])
        else:
            return ProfileStack([self, other])

    def __eq__(self, other):
        return self.equals(other)

    def integrate_to_costs(self, power: pd.Series) -> float:
        """
        Calculate costs or revenues based on power and feed_in flag.

        :param power: Power values for which to calculate costs or revenues.
        :return: Calculated costs (if feed_in is False) or revenues (if
        feed_in is True).
        """
        if not (power.index == self.index).all():
            raise ValueError(
                "Timeframes of power and PowerPriceProfile are not identical"
            )
        if (power > self.power).any():
            logger.warning("Power is above power of profile!")

        if self.index[1] - self.index[0] != pd.Timedelta(1, "h"):
            logger.warning(
                "Timedelta of Timeframe is not 1 hour! Make sure to calculate "
                "in the right unit (ct/kWh)."
            )
        return (power * self.price).sum()

    def add_price_to_all_profiles(self, price: pd.Series):
        self["price"] = self["price"].add(price, fill_value=0)

    def copy_ppp(self):
        return PowerPriceProfile(
            name=self.name,
            index=self.index,
            price=self.price,
            power=self.power,
            feed_in=self.feed_in,
        )



class PowerLimit(PowerPriceProfile):
    """
    Same base model as PowerPriceProfile. Only difference is that price
    defines a penalty price *above* the power limit and not the price below
    the limit. This means that adding and integrating to costs is not possible.
    """

    def __add__(self, other):
        raise ValueError("PowerLimits can not be added to PowerPriceProfiles")

    def integrate_to_costs(self, power: pd.Series) -> float:
        raise ValueError("It is not possible to calculate costs with PowerLimits")


class ProfileStack:
    """
    A container for PowerPriceProfiles. It is capable of calculating costs
    w.r.t. a certain power series and can select the cheapest
    PowerPriceProfile in each time step to do so.
    Each ProfileStack is valid for either feeding in or purchasing electricity.
    It does not matter for this model whether its PowerPriceProfiles are valid
    at the GCP only or also contain local generation like PV.
    """

    def __init__(self, profiles: List[PowerPriceProfile]):
        if len(profiles) > 1:
            for i in range(1, len(profiles)):
                if not profiles[i].index.equals(profiles[i - 1].index):
                    raise ValueError(
                        "All profiles must have the same index for stacking."
                    )
        self.index = profiles[0].index
        feed_in_flags = [p.feed_in for p in profiles]
        if not any(feed_in_flags) == all(feed_in_flags):
            raise ValueError("All feed_in flags have to be the same.")
        self.feed_in = profiles[0].feed_in
        for profile in profiles:
            if not profile.name:
                raise ValueError("All profiles must have a name.")
        self.profiles = {profile.name: profile for profile in profiles}

    def sort_existing_profiles(self):
        self.profiles = self.sort_profiles(self.profiles)

    @staticmethod
    def sort_profiles(profiles: dict) -> dict:
        """
        Sort profiles based on their power attribute and then on their price
        attribute.
        Profiles with defined power are sorted first, followed by profiles
        with undefined power.

        :param profiles: Dictionary of PowerPriceProfiles to sort
        :return: Sorted dictionary of PowerPriceProfiles
        """
        profiles_with_power = {
            name: profile
            for name, profile in profiles.items()
            if not profile["power"].isnull().all()
        }
        profiles_without_power = {
            name: profile
            for name, profile in profiles.items()
            if profile["power"].isnull().all()
        }

        sorted_profiles_with_power = {
            name: profile
            for name, profile in sorted(
                profiles_with_power.items(), key=lambda x: x[1]["price"].mean()
            )
        }
        sorted_profiles_without_power = {
            name: profile
            for name, profile in sorted(
                profiles_without_power.items(), key=lambda x: x[1]["price"].mean(),
            )
        }

        # combine sorted profiles
        sorted_profiles = {
            **sorted_profiles_with_power,
            **sorted_profiles_without_power,
        }
        return sorted_profiles

    def convert_price(self, factor: float):
        for ppp in self.profiles.values():
            ppp["price"] *= factor

    def convert_power(self, factor: float):
        for ppp in self.profiles.values():
            ppp["power"] *= factor

    def add_ppp(self, ppp: PowerPriceProfile):
        if not self.feed_in == ppp.feed_in:
            raise ValueError(
                "Can only add profiles for the same energy direction (feed_in "
                "must be the same)"
            )
        if ppp.name in self.profiles:
            raise ValueError("Profile with this name already exists")
        if ppp.index.equals(list(self.profiles.values())[0].index):
            self.profiles[ppp.name] = ppp
        else:
            raise ValueError(
                "Index of profile to add is not identical to index of " "ProfileStack"
            )

    def add_power_limit(self, limit: PowerLimit):
        # Note that PowerLimits can currently only be added if there is only one PPP in a stack.
        if len(self.profiles.keys()) > 1:
            raise NotImplementedError(
                "Can currently add only PowerLimit if there is one existing " "ppp yet."
            )
        ppp = next(iter(self.profiles.values()))
        # Check if PowerLimit actually is lower than existing ppp
        if (ppp["power"] > limit.power).any():
            diff_power = ppp["power"] - limit.power
            ppp["power"] = limit.power
            # Add price_above if defined by PowerLimit
            if limit.price.any():
                price_above = ppp["price"] + limit.price
                penalty_ppp = PowerPriceProfile(
                    index=limit.index,
                    price=price_above.to_list(),
                    power=diff_power.to_list(),
                    name=ppp.name + "_penalty",
                    feed_in=self.feed_in,
                )
                self.add_ppp(penalty_ppp)
            if (ppp["power"] > limit.power).any() and (
                ppp["power"] < limit.power
            ).any():
                raise NotImplementedError(
                    "It is currrently not possible to split up a ppp within a "
                    "ProfileStack."
                )

    def add_price_to_all_profiles(self, price: Union[pd.Series, PowerPriceProfile]):
        if type(price) == PowerPriceProfile:
            price = price.price
        for name, ppp in self.profiles.items():
            ppp["price"] = ppp["price"].add(price)

    def integrate_to_costs(
        self, power: pd.Series, optimize_usage=True, tolerance: float = 0
    ) -> float:
        """
        Calculate costs or revenues based on power and feed_in flag for the
        entire ProfileStack.

        :param power: Power values for which to calculate costs or revenues.
        :param optimize_usage: If True, for each timestep the profile with the
        lowest price will be selected.
        :return: Calculated costs (if feed_in is False) or revenues (if
        feed_in is True) for the entire ProfileStack.
        :tolerance: Optional tolerance for the power demand.
        If the remaining power in a timestep is below this value, it is
        considered as zero.
        0.0 means no tolerance, meaning that the remaining power must be exactly
        zero to stop the calculation.
        """
        if not (power.index == list(self.profiles.values())[0].index).all():
            raise ValueError(
                "Timeframes of power and PowerPriceProfile are not identical"
            )

        total_costs = 0.0
        remaining_power_slot = power.copy()
        if not optimize_usage:
            for ppp in self.profiles.values():
                profile_power = ppp["power"]
                profile_price = ppp["price"]
                if profile_power.isna().all():
                    total_costs += (profile_price * remaining_power_slot).sum()
                    break
                else:
                    power_in_ppp = remaining_power_slot.clip(upper=profile_power)
                    total_costs += (profile_price * power_in_ppp).sum()
                    remaining_power_slot -= power_in_ppp
                    remaining_power_slot = remaining_power_slot.clip(lower=0)
        else:
            for timestep in power.index:
                available_profiles = self.profiles.copy()
                remaining_power_in_timestep = power[timestep]
                costs_in_timestep = 0
                while remaining_power_in_timestep >= tolerance:
                    if not available_profiles:
                        raise ValueError(
                            "Power of all profiles is not sufficient to meet "
                            "the given power demand"
                        )
                    cheapest_profile_name = list(available_profiles.keys())[0]
                    # find the cheapest profile in this timestep
                    for profile_name, profile in available_profiles.items():
                        price_of_profile = profile.price[timestep]
                        if (
                            price_of_profile
                            < available_profiles[cheapest_profile_name].price[timestep]
                        ):
                            cheapest_profile_name = profile_name
                    available_power_of_cheapest_profile = available_profiles[
                        cheapest_profile_name
                    ].power[timestep]
                    if (
                        available_power_of_cheapest_profile
                        > remaining_power_in_timestep
                        or np.isnan(available_power_of_cheapest_profile)
                    ):
                        costs_in_timestep += (
                            remaining_power_in_timestep
                            * available_profiles[cheapest_profile_name].price[timestep]
                        )
                        break
                    else:
                        costs_in_timestep += (
                            available_power_of_cheapest_profile
                            * available_profiles[cheapest_profile_name].price[timestep]
                        )
                        remaining_power_in_timestep -= (
                            available_power_of_cheapest_profile
                        )
                        available_profiles.pop(cheapest_profile_name)
                total_costs += costs_in_timestep
        return total_costs


    def __eq__(self, other):
        if not hasattr(self, "feed_in") or not hasattr(other, "feed_in"):
            return False
        if self.feed_in is not other.feed_in:
            return False

        for key, value in self.profiles.items():
            if not value.equals(other.profiles[key]):
                return False
            if not other.profiles.keys() == self.profiles.keys():
                return False
        return True

    def __str__(self):
        string = f"Feed-in: {self.feed_in}\n"
        for key, value in self.profiles.items():
            string += f"{key}: {value}\n"
        return string

    def __add__(self, other):
        if not self.feed_in == other.feed_in:
            raise ValueError(
                "Can only add profiles for the same energy direction (feed_in "
                "must be the same)"
            )
        if isinstance(other, ProfileStack):
            for ppp in other.profiles.values():
                self.add_ppp(ppp)
            return self
        elif isinstance(other, PowerPriceProfile):
            self.add_ppp(other)
            return self
        else:
            raise ValueError("Can only add ProfileStack or PowerPriceProfile")

    def copy(self):
        profiles = []
        for name, df in self.profiles.items():
            profiles.append(
                PowerPriceProfile(
                    name=name,
                    index=df.index,
                    price=df.price,
                    power=df.power,
                    feed_in=self.feed_in,
                )
            )
        return ProfileStack(profiles)
