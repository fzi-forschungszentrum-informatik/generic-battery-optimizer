import datetime
import pandas as pd
import pyomo.environ as pyo
import logging
from battery_optimizer.model import Model
from battery_optimizer.static.model import (
    COMPONENT_MAP,
    TEXT_ENERGY_PATH_MATRIX,
    TEXT_SOC,
    TEXT_ENERGY,
    TEXT_BATTERY_BASE,
    TEXT_SELL_PROFILE_BASE,
    TEXT_ENERGY_PROFILE_BASE,
    TEXT_CONSUMPTION_PROFILE_BASE,
)

log = logging.getLogger(__name__)

POWER_POSTFIX = TEXT_ENERGY.replace("energy", "power")


# Könnte man den jetzt von einem DF erben lassen
class ModelDataframe:
    """Dataframe with all data from a model"""

    def __init__(self, model_dict, soc):
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
        return ModelDataframe.__convert_to_power(buy_df)

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
        return ModelDataframe.__convert_to_power(sell_df)

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
        return ModelDataframe.__convert_to_power(
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
        return ModelDataframe.__convert_to_power(fixed_consumption_df)

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
        return ModelDataframe.__convert_to_power(
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

    def __init__(self, model: Model):
        """Create a new model exporter

        Variables
        ---------
        model : Model
            The model that data shall be exported from
        """
        self._model = model

    def to_dict(self) -> dict[str, dict[pd.Timestamp, float]]:
        """Create a dictionary from the model

        Contains all devices from the model as columns. Each value represents
        the total constant power the device consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device.

        Returns
        -------
        dict[str, dict[pd.Timestamp, float]]
            The dictionary with all data from the model
            Output format:
            {
                "device": {
                    "timestamp": value
                }
            }
        """
        device_tree = {
            component: list(
                self._model.model.component(component).component_map()
            )
            for component in COMPONENT_MAP.values()
        }
        device_tuples = [
            (device_type, device)
            for device_type, devices in device_tree.items()
            for device in devices
        ]
        # TODO convert timestamps to datetime
        variables: dict[str, dict[pd.Timestamp, float]] = {}
        for device_type, device in device_tuples:
            component = self._model.model.component(device_type).component(
                device
            )
            variables[device] = {
                index: component[index].energy_source.value
                - component[index].energy_sink.value
                for index in component
            }
        return variables

    def to_df(self) -> ModelDataframe:
        """Create a DataFrame from the model

        Contains all devices that draw power as columns. Each value represents
        the total constant power the device consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device.

        Returns
        ---------
            ModelDataframe
            A DataFrame-like object containing power consumption data for all
            devices, indexed by timestamps. The DataFrame includes energy
            metrics and battery state of charge (SOC) information.
        """
        variables: dict[
            str, dict[str, dict[str, dict[pd.Timestamp, float]]]
        ] = {
            component: {
                dev: {}
                for dev in self._model.model.component(
                    component
                ).component_map()
            }
            for component in COMPONENT_MAP.values()
        }

        # device powers
        for device_type, device_list in variables.items():
            for device in device_list.keys():
                component = self._model.model.component(device_type).component(
                    device
                )
                variables[device_type][device] = {
                    "source": {
                        index: component.energy_source[index].value
                        for index in component.energy_source
                    },
                    "sink": {
                        index: component.energy_sink[index].value
                        for index in component.energy_sink
                    },
                }

        # battery soc
        soc: dict[str, dict[pd.Timestamp, float]] = {}
        for battery in variables["batteries"]:
            component = self._model.model.batteries.component(battery)
            soc[battery] = {
                index: component.soc[index].value / component.soc[index].ub
                for index in component.soc
            }

        return ModelDataframe(variables, soc)

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
            for period in battery:
                soc_component = battery[period].component(TEXT_SOC)
                variables[battery_name][period] = (
                    soc_component.value / soc_component.ub
                )

        soc_df = pd.DataFrame.from_dict(data=variables)

        return soc_df
      