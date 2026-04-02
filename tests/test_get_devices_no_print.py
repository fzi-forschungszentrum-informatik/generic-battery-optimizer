"""
Test that _get_devices() does not produce stdout output.

Regression test for the debug print statement that was left in
Model._get_devices(). The method should use log.debug() instead of print().
"""

import pandas as pd
from datetime import datetime

from battery_optimizer.model import Model
from battery_optimizer.profiles.battery import Battery


def test_get_devices_does_not_print(capsys):
    """_get_devices() must not write anything to stdout.

    A leftover ``print(devices)`` statement in Model._get_devices() produces
    noisy stdout output during every optimization run.  The statement must be
    replaced with a ``log.debug(...)`` call so that output is only visible when
    the caller explicitly enables debug logging.
    """
    time_series = pd.date_range(
        start="2022-01-03 18:00:00", end="2022-01-03 20:00:00", freq="h"
    )
    model = Model(index=list(time_series))

    battery = Battery(
        name="test-battery",
        start_soc=0,
        end_soc=0,
        capacity=100,
        max_charge_power=100,
        max_discharge_power=100,
    )
    model.add_battery(battery)

    # Call _get_devices() and capture stdout
    model._get_devices()

    captured = capsys.readouterr()
    assert captured.out == "", (
        "_get_devices() must not print to stdout; "
        f"got: {captured.out!r}"
    )
