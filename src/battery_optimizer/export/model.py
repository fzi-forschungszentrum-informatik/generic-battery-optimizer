import datetime
import pandas as pd
import pyomo.environ as pyo
import logging
from battery_optimizer.model import Model, Optimizer
from battery_optimizer.static.model import (
    TEXT_ENERGY_PATH_MATRIX,
    TEXT_SOC,
    TEXT_ENERGY,
    TEXT_CHARGE_ENERGY,
    TEXT_DISCHARGE_ENERGY,
    TEXT_BATTERY_BASE,
    TEXT_SELL_PROFILE_BASE,
    TEXT_ENERGY_PROFILE_BASE,
    TEXT_CONSUMPTION_PROFILE_BASE,
)
from battery_optimizer.static.heat_pump import (
    TEXT_HEAT_PUMP_BASE,
    TEXT_HEATING_ELEMENT_ENERGY_RULE,
    TEXT_INVERTER_ENERGY_RULE,
)

log = logging.getLogger(__name__)

POWER_POSTFIX = TEXT_ENERGY.replace("energy", "power")


# Könnte man den jetzt von einem DF erben lassen
class ModelDataframe:
    """Dataframe with all data from a model"""

    def __init__(self, df):
        """Create a new model dataframe

        Variables
        ---------
        df : pd.DataFrame
            The DataFrame exported from the model
        """
        self._df = df

    @staticmethod
    def _replace_padding_text(
        df: pd.DataFrame, pre: str = "", post: str = ""
    ) -> pd.DataFrame:
        """Replace padding text from optimizer

        Removes the prefix and postfix used in by the optimizer.
        The "'" from the optimizers naming are removed automatically"""
        mapper = {}
        for column in df.columns:
            new_name = column.removeprefix("'").removesuffix("'")
            new_name = new_name.removeprefix(pre)
            new_name = new_name.removesuffix(post)
            mapper[column] = new_name
        return df.rename(columns=mapper)

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
        buy_df = self._df.filter(regex=f"^'{TEXT_ENERGY_PROFILE_BASE}")
        return ModelDataframe._replace_padding_text(
            buy_df, TEXT_ENERGY_PROFILE_BASE, POWER_POSTFIX
        )

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
        sell_df = self._df.filter(regex=f"^'{TEXT_SELL_PROFILE_BASE}")
        return ModelDataframe._replace_padding_text(
            sell_df, TEXT_SELL_PROFILE_BASE, POWER_POSTFIX
        )

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
        battery_df = self._df.filter(regex=f"^'{TEXT_BATTERY_BASE}")
        battery_df = ModelDataframe._replace_padding_text(
            battery_df, TEXT_BATTERY_BASE
        )
        # Get charge and discharge profiles
        charge_profiles = battery_df.filter(
            like=TEXT_CHARGE_ENERGY.replace("energy", "power"), axis=1
        )
        discharge_profiles = battery_df.filter(
            like=TEXT_DISCHARGE_ENERGY.replace("energy", "power"), axis=1
        )
        # Remove charge and discharge text from profiles
        charge_profiles = ModelDataframe._replace_padding_text(
            charge_profiles, post=TEXT_CHARGE_ENERGY.replace("energy", "power")
        )
        discharge_profiles = ModelDataframe._replace_padding_text(
            discharge_profiles,
            post=TEXT_DISCHARGE_ENERGY.replace("energy", "power"),
        )
        # Combine profiles to one column
        return charge_profiles - discharge_profiles

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
        fixed_consumption_df = self._df.filter(
            regex=f"^'{TEXT_CONSUMPTION_PROFILE_BASE}"
        )
        return ModelDataframe._replace_padding_text(
            fixed_consumption_df, TEXT_CONSUMPTION_PROFILE_BASE, POWER_POSTFIX
        )

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
        heat_pump_df = self._df.filter(regex=f"^'{TEXT_HEAT_PUMP_BASE}")
        heat_pump_df = ModelDataframe._replace_padding_text(
            heat_pump_df, TEXT_HEAT_PUMP_BASE
        )
        # Get inverter and heating element profiles
        inverter_profiles = heat_pump_df.filter(
            like=TEXT_INVERTER_ENERGY_RULE.replace("energy", "power"), axis=1
        )
        heating_element_profiles = heat_pump_df.filter(
            like=TEXT_HEATING_ELEMENT_ENERGY_RULE.replace("energy", "power"),
            axis=1,
        )
        # Combine profiles to one column
        return pd.concat([inverter_profiles, heating_element_profiles], axis=1)

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
        soc_df = self._df.filter(regex=f"^'{TEXT_BATTERY_BASE}")
        soc_df = self._df.filter(regex=f"{TEXT_SOC}'$")
        return ModelDataframe._replace_padding_text(
            soc_df, TEXT_BATTERY_BASE, TEXT_SOC
        )


class Exporter:
    """Export data from a model

    The Exporter class is used to export data from a model. The data can be
    exported to a DataFrame or an Excel file."""

    @staticmethod
    def _ctype_to_dict(
        ctype: pyo.Component, remove_timestamps: bool = False
    ) -> dict[str, dict[pd.Timestamp, float]]:
        """Convert Pyomo Component to dict"""
        items: dict[str, dict[pd.Timestamp, float]] = {}
        log.debug("Generating dictionary from %s", ctype.name)
        for index, value in ctype.items():
            # Do not add the sub components of blocks
            if ".periods" in ctype.name:
                continue
            # Do not add parameters that are not indexed
            if index is None:
                log.warning("%s has no timestamp", value)
                continue
            # Add the item to the dictionary
            if ctype.name not in items:
                items[ctype.name] = {}
            # Excel can not handle timezone aware timestamps
            value = pyo.value(value)
            log.debug("%s: %s", ctype.name, index)
            # remove timezone info from timestamp
            if remove_timestamps:
                if isinstance(index, datetime.datetime):
                    index = index.replace(tzinfo=None)
            items[ctype.name][index] = value
        log.debug("Resulting dictionary:\n %s", items)
        return items

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

        df = df.apply(calculate_power)

        # rename energy to power
        mapper = {}
        for column in df.columns:
            mapper[column] = column.replace("energy", "power")
        return df.rename(columns=mapper)

    def __init__(self, model: Model):
        """Create a new model exporter

        Variables
        ---------
        model : Model
            The model that data shall be exported from
        """
        self._model = model

    def to_df(self) -> ModelDataframe:
        """Create a DataFrame from the model

        Contains all devices that draw power as columns. Each value represents
        the total constant power the device consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device.

        Variables
        ---------
        keep_column_names_original : bool
            If True the original column names will be kept. If False all
            occurrences of energy will be replaced by power as the resulting
            DataFrame provides power values.
        """
        variables: dict[str, dict[pd.Timestamp, float]] = {}
        for component in self._model.model.component_objects(pyo.Var):
            if component.name == TEXT_ENERGY_PATH_MATRIX:
                continue
            # pyomo appends an ' to component names
            if component.name.endswith(TEXT_SOC):
                continue
            variables = variables | Exporter._ctype_to_dict(component)

        df = pd.DataFrame.from_dict(data=variables)

        # Contains only energy metrics, no filter needed
        export_df = Exporter.__convert_to_power(df)
        return ModelDataframe(
            pd.concat([export_df, self._to_battery_soc()], axis=1)
        )

    def write_excel(self, filename: str) -> None:
        """Create an Excel file from the model

        A separate table will be created for sets, parameters, variables,
        objectives and constraints as well as the energy matrix.

        Variables
        ---------
        filename : str
            path and filename where the text file will be stored
        """
        # Add xlsx extension if missing
        if not filename.endswith(".xlsx"):
            filename = f"{filename}.xlsx"
        log.info("Writing to %s", filename)
        writer = pd.ExcelWriter(filename, engine="xlsxwriter")

        components: dict[str, list[pyo.Component]] = {}
        for key in [
            "Sets",
            "Parameters",
            "Variables",
            "Objectives",
            "Constraints",
        ]:
            components[key] = []

        energy_matrix: pyo.Var = None

        for component in self._model.model.component_objects():
            if isinstance(component, pyo.Set):
                components["Sets"].append(component)
            elif isinstance(component, pyo.Param):
                components["Parameters"].append(component)
            elif isinstance(component, pyo.Var):
                if component.name == TEXT_ENERGY_PATH_MATRIX:
                    energy_matrix = component
                    log.debug("adding energy matrix")
                else:
                    components["Variables"].append(component)
            elif isinstance(component, pyo.Objective):
                components["Objectives"].append(component)
            elif isinstance(component, pyo.Constraint):
                components["Constraints"].append(component)
            else:
                log.warning("Unknown type of %s", type(component))

        for key in components:
            out: dict[str, dict[pd.Timestamp, float]] = {}
            for item in components[key]:
                out = out | Exporter._ctype_to_dict(item, True)
            if out != {}:
                pd.DataFrame.from_dict(data=out).to_excel(
                    writer, sheet_name=key
                )
                # set body column widths
                writer.sheets[key].set_column(
                    1, len(out.keys()), len(max(out.keys(), key=len))
                )
                # set index column width (datetimes have a width of 19 without
                # timezone)
                writer.sheets[key].set_column(0, 0, 19)

        # print the energy matrix
        # each timestamp goes to a separate sheet
        #                        sheet              row      column value
        energy_matrix_dict: dict[pd.Timestamp, dict[str, dict[str, float]]] = (
            {}
        )
        for (timestamp, source, target), value in energy_matrix.iteritems():
            if timestamp not in energy_matrix_dict:
                energy_matrix_dict[timestamp] = {}
            if source not in energy_matrix_dict[timestamp]:
                energy_matrix_dict[timestamp][source] = {}
            energy_matrix_dict[timestamp][source][target] = pyo.value(value)
        for key, value in energy_matrix_dict.items():
            # type: ignore
            sheet_name = f"E-Matrix {key.strftime('%d.%m.%Y %H-%M–%S')}"
            pd.DataFrame.from_dict(data=value, orient="index").to_excel(
                writer, sheet_name=sheet_name
            )
            # set body column widths
            writer.sheets[sheet_name].set_column(
                1,
                len(self._model.energy_sinks),
                len(max(self._model.energy_sinks, key=len)),
            )
            # set index column width
            writer.sheets[sheet_name].set_column(
                0, 0, len(max(self._model.energy_sources, key=len))
            )
        writer.close()

    def _to_battery_soc(self) -> pd.DataFrame:
        """Create a DataFrame with all battery SoC profiles

        Contains the SoC for all batteries at the end of each time step just before
        the next time step starts.

        Returns
        -------
        pd.DataFrame
            The SoC of each battery.
        """
        # Get all SoC variables
        variables: dict[str, dict[pd.Timestamp, float]] = {}
        batteries = [
            self._model.model.batteries.component(battery)
            for battery in self._model.model.batteries.component_map()
        ]

        for battery in batteries:
            battery_name = f"'{battery.local_name}{TEXT_SOC}'"
            variables[battery_name] = {}
            for period in battery.periods:
                soc_component = battery.periods[period].component(TEXT_SOC)
                variables[battery_name][period] = (
                    soc_component.value / soc_component.ub
                )

        soc_df = pd.DataFrame.from_dict(data=variables)

        return soc_df
