from battery_optimizer.profiles.profiles import ProfileStack
from battery_optimizer.static.profiles import (
    PROFILESTACK_PRICE,
    PROFILESTACK_POWER,
    MODEL_PRICE_BELOW,
    MODEL_POWER_BELOW,
    MODEL_POWER_ABOVE,
)
from battery_optimizer.static.numbers import BIG_POWER
from typing import List
import pandas as pd
import logging

log = logging.getLogger(__name__)


def calculate_energy(column: pd.Series) -> pd.Series:
    """Calculate energy for each row

    Energy in the last row will be 0 because no period can be
    calculated.
    """
    # Iterate over all but the last row
    for i in range(column.size - 1):
        # calculate time delta to next timestamp
        time_delta = (column.index[i + 1] - column.index[i]).seconds / 3600
        # calculate energy
        column.iloc[i] *= time_delta

    # The last row is all zeros
    column.iloc[-1] = 0
    return column


def parse_profiles(
    profile_stack: ProfileStack,
    index: pd.DatetimeIndex | List[pd.Timestamp],
    add_padding_profile: bool = False,
) -> dict:
    """Get a dictionary of individual profiles from a ProfileStack

    All power values will be converted to energy in Wh values that specify the
    total energy allowed te be used during a time frame.
    Price is assumed to be in ct/kWh.

    If Price and power are set the profile is added as is.
    If Prices is set and power is not set the profile is added with
    unrestricted power (BIG_POWER).
    If Prices is not set and power is set the profile is added as a fixed
    consumption profile.

    Attributes
    ----------
    prices : ProfileStack
        The DataFrame containing all energy and price information.
    index : pd.Index
        The index to reindex the profiles to. This allows to have a common
        index for all profiles.
    """
    # The dictionary of profiles
    opt_profiles = {}

    for name, profile in profile_stack.profiles.items():
        # Check that the profile name is not a duplicate
        assert name not in opt_profiles
        # Create a new profile
        opt_profiles[name] = pd.DataFrame(index=profile.index)
        # Create checks what columns have values
        price_below_isna = profile[PROFILESTACK_PRICE].isna().all()
        power_isna = profile[PROFILESTACK_POWER].isna().all()

        # Add the power and price columns to the profile
        if not price_below_isna and not power_isna:
            opt_profiles[name][MODEL_PRICE_BELOW] = profile[PROFILESTACK_PRICE]
            opt_profiles[name][MODEL_POWER_BELOW] = profile[PROFILESTACK_POWER]
        elif not price_below_isna and power_isna:
            # The power is unrestricted
            opt_profiles[name][MODEL_PRICE_BELOW] = profile[PROFILESTACK_PRICE]
            opt_profiles[name][MODEL_POWER_BELOW] = BIG_POWER
        elif price_below_isna and not power_isna:
            # This is a fixed consumption profile
            # Only power is added
            opt_profiles[name][MODEL_POWER_BELOW] = profile[PROFILESTACK_POWER]
        else:
            log.warning("Profile %s has no price or power", profile)
            opt_profiles.pop(profile)

        # There should be no NaN values in the profiles
        if name in opt_profiles:
            for column in opt_profiles[name].columns:
                assert not opt_profiles[name][column].isna().any()

    # Reindex to provided index
    for name, profile in opt_profiles.items():
        # get all dates in new_dates that are before the first date in dates
        # and after the last date in dates
        outside_dates = [
            date
            for date in index
            if date < profile.index[0] or date > profile.index[-1]
        ]

        profile = profile.reindex(index)

        # Fill all values in outside_dates with 0
        for date in outside_dates:
            profile.loc[date] = 0

        # Forward fill the remaining NaN values
        opt_profiles[name] = profile.ffill()

    # Add padding profile
    if add_padding_profile:
        opt_profiles["padding"] = pd.DataFrame(index=index)
        # Add the power and price columns to the profile
        opt_profiles["padding"][MODEL_PRICE_BELOW] = BIG_POWER
        # We need extra large power to prevent infeasibility
        # if other opt_profiles get BIG_POWER
        opt_profiles["padding"][MODEL_POWER_BELOW] = BIG_POWER * BIG_POWER

    # Convert power to energy
    for name, profile in opt_profiles.items():
        columns = profile.filter(regex=f"{MODEL_POWER_BELOW}$").columns
        columns.append(profile.filter(regex=f"{MODEL_POWER_ABOVE}$").columns)

    return opt_profiles
