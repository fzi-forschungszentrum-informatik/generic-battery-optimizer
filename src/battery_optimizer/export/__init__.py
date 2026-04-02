"""
Module for exporting model data.

Contains the Exporter class to export data from a model
to different formats such as DataFrames or dictionaries.
"""

import datetime
import logging
import pandas as pd
import pyomo.environ as pyo
from battery_optimizer.export.pandas import ModelDataFrame
from battery_optimizer.helpers.blocks import get_period_length
from battery_optimizer.model import Model
from battery_optimizer.static.model import (
    COMPONENT_MAP,
    TEXT_ENERGY_PATH_MATRIX,
    TEXT_SOC,
    TEXT_ENERGY,
)

log = logging.getLogger(__name__)

POWER_POSTFIX = TEXT_ENERGY.replace("energy", "power")


class Exporter:
    """
    Export data from a model.

    The Exporter class is used to export data from a model. The data can be
    exported to a DataFrame or an Excel file.

    Parameters
    ----------
    model : Model
        The model that data shall be exported from.
    """

    @staticmethod
    def _ctype_to_dict(
        ctype: pyo.Component, remove_timestamps: bool = False
    ) -> dict[str, dict[pd.Timestamp, float]]:
        """
        Convert Pyomo Component to dict.

        Convert indexed component of the model to a dictionary.

        Parameters
        ----------
        ctype : pyo.Component
            The Pyomo component to convert.
        remove_timestamps : bool, optional
            Whether to remove timezone info from timestamps, by default False.

        Returns
        -------
        dict[str, dict[pd.Timestamp, float]]
            The dictionary with the component data.
        """
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
        """
        Create a new model exporter.

        Store the model that data shall be exported from.

        Parameters
        ----------
        model : Model
            The model that data shall be exported from.
        """
        self._model = model

    def to_dict(self) -> dict[str, dict[pd.Timestamp, float]]:
        """
        Create a dictionary from the model.

        Contains all devices from the model as columns. Each value represents
        the total constant power the device consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device. A positive power means that the device is emitting
        power to other devices and a negative power means that the device is
        acting as a energy sink.

        Returns
        -------
        dict[str, dict[pd.Timestamp, float]]
            The dictionary with all data from the model
            Output format:
            {
                "device": {
                    "timestamp": value
                }
            }.
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
                index: component.energy_source[index].value
                / get_period_length(index, self._model.model.i)[1]
                - component.energy_sink[index].value
                / get_period_length(index, self._model.model.i)[1]
                for index in self._model.model.i
            }
        return variables

    def __extract_component_parameter(
        self, device_class: str, device_name: str, parameter: str
    ) -> dict[str, dict[datetime.datetime, float]]:
        """
        Get a parameter from a device.

        Export an indexed component as a dictionary.

        Parameters
        ----------
        device_class : str
            The class of the device (e.g. 'batteries').
        device_name : str
            The name of the device (e.g. 'battery1').
        parameter : str
            The parameter to extract (e.g. 'soc').

        Returns
        -------
        dict[str, dict[datetime.datetime, float]]
            The dictionary with the parameter values.
        """

        device: pyo.Block = self._model.model.component(device_class)
        if device is None:
            raise ValueError(f"Device class {device_class} not found")
        device: pyo.Block = device.component(device_name)
        if device is None:
            raise ValueError(
                f"Device {device_name} not found in {device_class}"
            )
        model_parameter: pyo.Component = device.component(parameter)
        if model_parameter is None:
            raise ValueError(
                (
                    f"Parameter {parameter} not found in "
                    f"{device_class}.{device_name}"
                )
            )

        return model_parameter.extract_values()

    def __extract_hp_parameter(
        self, parameter: str
    ) -> dict[str, dict[datetime.datetime, float]]:
        """
        Get a parameter from all heat pumps.

        Export an indexed component as a dictionary.

        Parameters
        ----------
        parameter : str
            The parameter to extract (e.g. 'soc').

        Returns
        -------
        dict[str, dict[datetime.datetime, float]]
            The dictionary with the parameter values.
        """
        return {
            heat_pump: {
                index: self._model.model.heat_pumps.component(heat_pump)
                .hp_block[index]
                .component(parameter)
                .value
                for index in self._model.model.heat_pumps.component(
                    heat_pump
                ).hp_block
            }
            for heat_pump in self._model.model.heat_pumps.component_map()
        }

    def get_heat_pump_soc(self) -> dict[str, dict[datetime.datetime, float]]:
        """
        Get the state of charge of all heat pumps.

        Get the soc of the heat pumps for each time step as [0-1] value.

        Returns
        -------
        dict[str, dict[datetime.datetime, float]]
            The dictionary with the state of charge values for all heat pumps.
        """
        return self.__extract_hp_parameter(TEXT_SOC)

    def get_heat_pump_tes_temperature(
        self,
    ) -> dict[str, dict[datetime.datetime, float]]:
        """
        Get the temperature of the thermal energy storage of all heat pumps.

        Get the temperature of the thermal energy storage of the heat pumps
        for each time step.

        Returns
        -------
        dict[str, dict[datetime.datetime, float]]
            The dictionary with the temperature values for all heat pumps.
        """
        return self.__extract_hp_parameter("temp_TES")

    def to_df(self) -> ModelDataFrame:
        """
        Create a DataFrame from the model.

        Contains all devices that draw power as columns. Each value represents
        the total constant power the device consumes during a time period.
        Indexed by the timestamps from which the specified power should be
        used by a device.

        Returns
        ---------
        ModelDataFrame
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

        # ev soc
        ev_soc: dict[str, dict[pd.Timestamp, float]] = {}
        for ev in variables["evs"]:
            component = self._model.model.evs.component(ev)
            ev_soc[ev] = {
                index: component.soc[index].value / component.soc[index].ub
                for index in component.soc
            }

        return ModelDataFrame(variables, soc, ev_soc)

    def write_excel(self, filename: str) -> None:
        """
        Create an Excel file from the model.

        A separate table will be created for sets, parameters, variables,
        objectives and constraints as well as the energy matrix.

        Parameters
        ----------
        filename : str
            Ppath and filename where the text file will be stored.
        """
        # Add xlsx extension if missing
        if not filename.endswith(".xlsx"):
            filename = f"{filename}.xlsx"
        log.info("Writing to %s", filename)
        try:
            import xlsxwriter  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "xlsxwriter is required for Excel export. "
                "Install it with: pip install battery_optimizer[excel]"
            ) from e
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
        """
        Create a DataFrame with all battery SoC profiles.

        Contains the SoC for all batteries at the end of each time step just
        before the next time step starts.

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
