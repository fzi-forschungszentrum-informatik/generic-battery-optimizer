"""
Unit tests for __convert_to_power in ModelDataFrame.

These tests verify that energy values are correctly divided by the period
length (in hours) to yield power values, including for time gaps of 24 hours
or more. The bug being tested: using timedelta.seconds instead of
timedelta.total_seconds() would silently drop the days component and produce
incorrect (too large) power values for multi-day gaps.
"""

import datetime

import pandas as pd
import pytest

from battery_optimizer.export.pandas import ModelDataFrame


def _make_model_dict(timestamps: list, values: list, device: str = "dev") -> dict:
    """Build the minimal model_dict needed to exercise to_buy()."""
    return {
        "buy_profiles": {
            device: {
                "source": dict(zip(timestamps, values)),
            }
        },
        "sell_profiles": {},
        "batteries": {},
        "evs": {},
        "fixed_consumptions": {},
        "heat_pumps": {},
    }


class TestConvertToPowerTimeDelta:
    """
    Test that __convert_to_power uses total_seconds(), not .seconds.

    timedelta.seconds returns only the seconds component within the current
    day (0–86399). For a gap of 25 h, timedelta.seconds == 3600 (1 h),
    which would make the power 25× too large. total_seconds() returns
    90 000 (= 25 h), giving the correct result.
    """

    def test_sub_24h_gap_is_correct(self):
        """A 2-hour gap: 1000 Wh / 2 h = 500 W."""
        ts0 = datetime.datetime(2023, 1, 1, 0, 0)
        ts1 = datetime.datetime(2023, 1, 1, 2, 0)
        model_dict = _make_model_dict([ts0, ts1], [1000.0, 0.0])

        result = ModelDataFrame(model_dict, {}, {}).to_buy()

        assert result["dev"][ts0] == pytest.approx(500.0)
        assert result["dev"][ts1] == pytest.approx(0.0)

    def test_exactly_24h_gap_is_correct(self):
        """A 24-hour gap: 2400 Wh / 24 h = 100 W."""
        ts0 = datetime.datetime(2023, 1, 1, 0, 0)
        ts1 = datetime.datetime(2023, 1, 2, 0, 0)
        model_dict = _make_model_dict([ts0, ts1], [2400.0, 0.0])

        result = ModelDataFrame(model_dict, {}, {}).to_buy()

        assert result["dev"][ts0] == pytest.approx(100.0)
        assert result["dev"][ts1] == pytest.approx(0.0)

    def test_over_24h_gap_is_correct(self):
        """
        A 25-hour gap: 1000 Wh / 25 h = 40 W.

        With the .seconds bug the denominator would be 1 h (3600 s) instead
        of 25 h (90000 s), yielding 1000 W instead of 40 W.
        """
        ts0 = datetime.datetime(2023, 1, 1, 0, 0)
        ts1 = datetime.datetime(2023, 1, 2, 1, 0)  # 25 hours later
        model_dict = _make_model_dict([ts0, ts1], [1000.0, 0.0])

        result = ModelDataFrame(model_dict, {}, {}).to_buy()

        assert result["dev"][ts0] == pytest.approx(40.0), (
            "Power should be 40 W (1000 Wh / 25 h). "
            "A value of 1000 W indicates the .seconds bug is present."
        )
        assert result["dev"][ts1] == pytest.approx(0.0)

    def test_multi_step_with_over_24h_gap(self):
        """
        Multi-step series containing a gap > 24 h alongside a normal gap.

        ts0 -> ts1: 1 h  → 60 Wh / 1 h  = 60 W
        ts1 -> ts2: 25 h → 500 Wh / 25 h = 20 W
        ts2: last row     → 0 W
        """
        ts0 = datetime.datetime(2023, 1, 1, 0, 0)
        ts1 = datetime.datetime(2023, 1, 1, 1, 0)   # +1 h
        ts2 = datetime.datetime(2023, 1, 2, 2, 0)   # +25 h
        model_dict = _make_model_dict(
            [ts0, ts1, ts2], [60.0, 500.0, 0.0]
        )

        result = ModelDataFrame(model_dict, {}, {}).to_buy()

        assert result["dev"][ts0] == pytest.approx(60.0)
        assert result["dev"][ts1] == pytest.approx(20.0), (
            "Power should be 20 W (500 Wh / 25 h). "
            "A value of 500 W indicates the .seconds bug is present."
        )
        assert result["dev"][ts2] == pytest.approx(0.0)
