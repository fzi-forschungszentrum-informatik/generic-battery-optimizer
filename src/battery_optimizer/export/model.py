from battery_optimizer.export import Exporter as NewExporter
import warnings


class Exporter(NewExporter):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "Exporter is deprecated. Please use battery_optimizer.export.Exporter instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
