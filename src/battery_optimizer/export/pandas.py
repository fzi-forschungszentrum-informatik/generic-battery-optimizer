import datetime
import logging
import pandas as pd
from battery_optimizer.static.model import TEXT_ENERGY

log = logging.getLogger(__name__)

POWER_POSTFIX = TEXT_ENERGY.replace("energy", "power")


# Könnte man den jetzt von einem DF erben lassen
class ModelDataFrame:
    """Dataframe with all data from a model"""

    def __init__(
        self,
        model_dict: dict[str, dict[str, dict[str, dict[pd.Timestamp, float]]]],
        soc: dict[str, dict[datetime.datetime, float]],
    ):
        """Create a new model dataframe

        Variables
        ---------
        model_dict : dict[str, dict[str, dict[str, dict[pd.Timestamp, float]]]]
            The DataFrame exported from the model
        soc : dict[str, dict[datetime.datetime, float]]
            The state of charge of the batteries
        """
        self._model_dict = model_dict
        self._soc = soc

    def to_buy(self) -> pd.DataFrame:
        """Create a DataFrame with all buy power profiles

        Contains all devices that draw. Each value represents the
        total constant power the device consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device.
        Buy profiles have positive power when they consume power.

        Returns
        -------
        pd.DataFrame
            The power in W of each buy profile.
        """
        buy_df = pd.DataFrame(
            {
                device: values["source"]
                for device, values in self._model_dict[
                    "power_profiles"
                ].items()
            }
        )
        return ModelDataFrame.__convert_to_power(buy_df)

    def to_sell(self) -> pd.DataFrame:
        """Create a DataFrame with all sell power profiles

        Contains all devices that feed in power. Each value represents the
        total constant power the device consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device.
        Feed-in profiles have a positive power when they feed in power.

        Returns
        -------
        pd.DataFrame
            The power in W of each sell profile.
        """
        sell_df = pd.DataFrame(
            {
                device: values["sink"]
                for device, values in self._model_dict[
                    "power_profiles"
                ].items()
            }
        )
        return ModelDataFrame.__convert_to_power(sell_df)

    def to_battery_power(self) -> pd.DataFrame:
        """Create a DataFrame with all battery power profiles

        Contains all batteries that draw or feed in power. Each value
        represents the total constant power the battery consumes during a time
        period.
        Indexed by the timestamps from which the specified power should be
        used by a device.
        Batteries have positive power when they are charged and negative power
        when they are discharged.

        Returns
        -------
        pd.DataFrame
            The power in W of each battery.
        """
        # Get Battery power
        return ModelDataFrame.__convert_to_power(
            pd.DataFrame(
                {
                    device: pd.Series(values["sink"])
                    - pd.Series(values["source"])
                    for device, values in self._model_dict["batteries"].items()
                }
            )
        )

    def to_fixed_consumption(self) -> pd.DataFrame:
        """Create a DataFrame with all fixed consumptions

        This is just to get a simplified list because as these devices are not
        flexible they are not optimized and are the same before and after the
        optimization. Contains all devices that draw an inflexible power. Each
        value represents the total constant power the device consumes during a
        time period. Indexed by the timestamps from which the specified power
        should be used by a device.

        Returns
        -------
        pd.DataFrame
            The power in W of each fixed consumption profile.
        """
        fixed_consumption_df = pd.DataFrame(
            {
                device: values["sink"]
                for device, values in self._model_dict[
                    "fixed_consumptions"
                ].items()
            }
        )
        return ModelDataFrame.__convert_to_power(fixed_consumption_df)

    def to_heat_pump_power(self) -> pd.DataFrame:
        """Create a DataFrame with all heat pump power profiles

        Contains all heat pumps that draw power. Each heat pump has an inverter
        power and a heating element. Each value represents the total constant
        power the heat pump consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device.

        Returns
        -------
        pd.DataFrame
            The power in W of each heat pump profile.
        """
        # Get Battery power
        return ModelDataFrame.__convert_to_power(
            pd.DataFrame(
                {
                    device: values["sink"]
                    for device, values in self._model_dict[
                        "heat_pumps"
                    ].items()
                }
            )
        )

    def to_battery_soc(self) -> pd.DataFrame:
        """Create a DataFrame with all battery SoC profiles

        Contains all battery SoC profiles. Each value represents the SoC of the
        battery at the end of each time step just before the next time step
        starts.

        Returns
        -------
        pd.DataFrame
            The SoC of each battery.
        """
        return pd.DataFrame(self._soc)

    @staticmethod
    def __convert_to_power(df: pd.DataFrame) -> pd.DataFrame:
        """Converts a DataFrame with energy units to power units

        Power is converted by assuming a constant power between each set of two
        timestamps.

        Variables
        ---------
        df : pd.DataFrame
            The DataFrame to convert

        Returns
        -------
        pd.DataFrame
            The DataFrame with power values
        """

        def calculate_power(column: pd.Series) -> pd.Series:
            """Calculate power for each row

            Power in the last row will be 0 because no period can be
            calculated.
            """
            # Iterate over all but the last row
            for i in range(column.size - 1):
                # calculate time delta to next timestamp
                time_delta = (
                    column.index[i + 1] - column.index[i]
                ).seconds / 3600
                # calculate energy
                column.iloc[i] /= time_delta

            # The last row is all zeros
            column.iloc[-1] = 0
            return column

        return df.apply(calculate_power)
