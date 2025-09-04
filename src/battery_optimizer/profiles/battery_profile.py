from battery_optimizer.profiles.battery import Battery as NewBattery
import warnings


class Battery(NewBattery):

    def __init__(self, *args, **kwargs):
        warnings.warn(
            (
                "Battery has moved. Please use battery_optimizer.export.Battery "
                "instead."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
