"""
Test suite for the HpLibWrapper and its associated methods.

This module contains unit tests for the HpLibWrapper class, which provides methods
for calculating the coefficient of performance (COP) of heat pumps under various
conditions. The tests ensure the correctness of the COP calculations for both
dictionary-based and single-value inputs.

Methods
-------
test_cop_dict()
    Tests the COP calculation for dictionary-based inputs.

test_cop_single()
    Tests the COP calculation for single-value inputs.
"""

import pytest
import pandas as pd
from battery_optimizer.helpers.hplib import HpLibProfile, HpLibWrapper


class TestHpLibWrapper:
    """
    Test suite for the HpLibWrapper class.

    This class contains unit tests for the HpLibWrapper, which provides methods
    for calculating the coefficient of performance (COP) of heat pumps under
    various conditions.

    Attributes
    ----------
    time_series : pd.DatetimeIndex
        A time series used for testing COP calculations.
    hplib : HpLibWrapper
        An instance of HpLibWrapper initialized with a specific heat pump profile.
    """

    time_series = pd.date_range(
        start="2021-01-01 08:00:00+00:00",
        end="2021-01-01 10:00:00+00:00",
        freq="h",
    )
    hplib = HpLibWrapper(
        HpLibProfile(
            type="i-SHWAK V4 12",
            flow_temperature=35,
            output_temperature=55,
        )
    )

    def test_cop_dict(self):
        """
        Test the COP calculation for dictionary-based inputs.

        This method tests the `get_cop_output_temperature` and `get_cop_flow_temperature` methods
        of the HpLibWrapper class using dictionary inputs for outdoor and heat
        source temperatures. It verifies that the COP values are within the
        expected range and that `cop_high` is less than `cop_low` for all
        timestamps.

        Raises
        ------
        AssertionError
            If the COP values are not within the expected range or if the
            conditions `cop_high < cop_low` are not met.
        """
        outdoor_temperature = {
            self.time_series[0]: 15,
            self.time_series[1]: 0,
            self.time_series[2]: 0,
        }
        heat_source_temperature = {
            self.time_series[0]: 15,
            self.time_series[1]: 0,
            self.time_series[2]: 0,
        }
        cop_high = self.hplib.get_cop_output_temperature(
            heat_source_temperature, outdoor_temperature
        )
        cop_low = self.hplib.get_cop_flow_temperature(heat_source_temperature, outdoor_temperature)

        # Check that for all timestamps, cop_high < cop_low
        for t in cop_high:
            assert 1 < cop_high[t] < cop_low[t] < 10
        assert isinstance(cop_high, dict)
        assert isinstance(cop_low, dict)
    
    def test_cop_single(self):
        """
        Test the COP calculation for single-value inputs.

        This method tests the `get_cop_output_temperature` method of the HpLibWrapper
        class using single-value inputs for outdoor and heat source temperatures.
        It verifies that the COP value is within the expected range.

        Raises
        ------
        AssertionError
            If the COP value is not within the expected range.
        """
        cop = self.hplib.get_cop_output_temperature(5, 9)
        assert 1 < cop < 10
        assert isinstance(cop, float)

    def test_validate_source_and_outdoor_temp_mismatched_keys(self):
        """
        Test that dicts with the same length but different timestamp keys raise ValueError.

        When source_temperature and outdoor_temperature dicts have the same
        number of entries but different datetime keys, constructing a DataFrame
        from them silently introduces NaN values (pandas aligns on the union of
        all keys). This test ensures that a clear ValueError is raised instead.
        """
        time_series_a = pd.date_range(
            start="2021-01-01 08:00:00+00:00",
            end="2021-01-01 10:00:00+00:00",
            freq="h",
        )
        time_series_b = pd.date_range(
            start="2021-01-02 08:00:00+00:00",
            end="2021-01-02 10:00:00+00:00",
            freq="h",
        )
        source_temperature = {ts: 10.0 for ts in time_series_a}
        outdoor_temperature = {ts: 5.0 for ts in time_series_b}

        assert len(source_temperature) == len(outdoor_temperature)

        with pytest.raises(ValueError, match="same datetime keys"):
            self.hplib.get_cop_output_temperature(
                source_temperature, outdoor_temperature
            )
