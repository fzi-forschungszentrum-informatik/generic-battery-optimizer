from battery_optimizer.profiles.heat_pump import HeatPump
from battery_optimizer.static.heat_pump import C_TO_K
from helpers import get_profiles, find_solver
from battery_optimizer import optimize
import pandas as pd
import datetime
import pytest
import yaml

base = "data/tests/"

solver = find_solver("gurobi")

testdata = [
    {
        "path": "Data set 1/",
        "hp_specs": "heat_pump.yaml",
        "house_data": "HP_Data_1_10_23_samsung_5kW_13_11_23_15min.csv",
        "weather_column": "samsung-ashp:ashp_outdoor_temp",
        "heat_column": "sontex:sontex_Power",
        "days": [
            datetime.date(2023, 10, 16),
            datetime.date(2023, 10, 17),
            datetime.date(2023, 10, 18),
            datetime.date(2023, 10, 23),
            datetime.date(2023, 10, 27),
            datetime.date(2023, 11, 1),
            datetime.date(2023, 11, 2),
            datetime.date(2023, 11, 3),
            datetime.date(2023, 11, 4),
            datetime.date(2023, 11, 5),
            datetime.date(2023, 11, 6),
            datetime.date(2023, 11, 7),
            datetime.date(2023, 11, 8),
            datetime.date(2023, 11, 9),
            datetime.date(2023, 11, 10),
            datetime.date(2023, 11, 11),
            datetime.date(2023, 11, 12),
        ],
    },
    {
        "path": "Data set 4/",
        "hp_specs": "heat_pump.yaml",
        "house_data": "HP_Data_20_11_2022_Vaillant_5kW_13_11_23_15min.csv",
        "weather_column": "ashp_from_ha:outdoor_temp",
        "heat_column": "ashp_sharky:sharky775_Power",
        "days": [
            datetime.date(2023, 10, 15),
            datetime.date(2023, 10, 16),
            datetime.date(2023, 10, 17),
            datetime.date(2023, 10, 21),
            datetime.date(2023, 10, 22),
            datetime.date(2023, 10, 23),
            datetime.date(2023, 10, 24),
            datetime.date(2023, 10, 25),
            datetime.date(2023, 10, 26),
            datetime.date(2023, 10, 27),
            datetime.date(2023, 10, 28),
            datetime.date(2023, 10, 30),
            datetime.date(2023, 10, 31),
            datetime.date(2023, 11, 1),
            datetime.date(2023, 11, 2),
            datetime.date(2023, 11, 3),
            datetime.date(2023, 11, 4),
            datetime.date(2023, 11, 5),
            datetime.date(2023, 11, 6),
            datetime.date(2023, 11, 7),
            datetime.date(2023, 11, 8),
            datetime.date(2023, 11, 9),
            datetime.date(2023, 11, 10),
            datetime.date(2023, 11, 11),
            datetime.date(2023, 11, 12),
        ],
    },
    {
        "path": "Data set 6/",
        "hp_specs": "heat_pump.yaml",
        "house_data": "HP_Data_1_10_2023_ecodan_5kW_try_13_11_23_15min.csv",
        "weather_column": "heatpump:heatpump_ambient",
        "heat_column": "heatpump:heatpump_heat",
        "days": [
            datetime.date(2023, 10, 18),
            datetime.date(2023, 10, 21),
            datetime.date(2023, 10, 24),
            datetime.date(2023, 10, 27),
            datetime.date(2023, 10, 28),
            datetime.date(2023, 11, 2),
            datetime.date(2023, 11, 3),
            datetime.date(2023, 11, 4),
            datetime.date(2023, 11, 5),
            datetime.date(2023, 11, 7),
            datetime.date(2023, 11, 10),
        ],
    },
]


@pytest.mark.parametrize("data", testdata)
def test_scenarios(data):
    # This test relies on hplib v1.9
    # newer versions of hplib yield different results
    if solver != "gurobi":
        pytest.skip(
            "Skipping this test as it requires the Gurobi solver to run"
        )

    # Expected Results
    expected_results = pd.read_csv(
        f"{base}{data['path']}results.csv", index_col=0, parse_dates=True
    )
    # Calculated results
    # Test Data
    results = {}

    # Heat pump specs
    with open(base + data["path"] + data["hp_specs"], "r") as file:
        house_data = yaml.safe_load(file)

    # Household data
    df = pd.read_csv(
        base + data["path"] + data["house_data"],
        index_col="Date-time string",
        parse_dates=True,
    )
    df.index = df.index.tz_localize("Europe/Berlin", ambiguous=True)
    # Split data by days
    df["day"] = df.index.date
    days = {day[0]: day[1] for day in df.groupby("day")}

    # Simulation:
    for day, input_data in days.items():
        if day not in data["days"]:
            continue
        print(f"Simulating scenario {data['path']} on {day}")

        input_data = pd.concat(
            [input_data, days[day + datetime.timedelta(days=1)].iloc[[0]]]
        )
        input_range = range(len(input_data.index))

        buy_price_profile = {
            "buy_price": pd.DataFrame(
                data={
                    "input_power": [30000 for i in input_range],
                    "input_price": [26 for i in input_range],
                },
                index=input_data.index,
            )
        }

        # Heat Pump
        outdoor_temperature = (
            input_data[data["weather_column"]].astype(float) + C_TO_K
        ).round(2)

        # Constant power in W -> kW in period
        heat_demand = input_data[data["heat_column"]] / 1000

        # Heat pump
        hp = HeatPump(
            name="Heat Pump",
            type=house_data["TYPE"],
            t_in=house_data["T_IN"],
            t_out=house_data["T_OUT"],
            p_th=house_data["P_TH"],
            living_area=house_data["SURFACE_BUILDING"],
            flow_temperature=house_data["TEMP_SUPPLY_DEMAND"],
            temp_room=house_data["TEMP_ROOM"],
            hp_switch_off_temperature=house_data["TEMP_HP_OUT"],
            bivalent_temp=house_data["BIVALENT_TEMP"],
            output_temperature=house_data["TEMP_HP"],
            max_electric_power_hp=house_data["MAX_ELECTRIC_CONSUMPTION_HP"],
            min_electric_power_hp=house_data["MIND_ELECTRIC_CONSUMPTION_HP"],
            max_electric_power_hr=house_data["MAX_ELECTRIC_CONSUMPTION_HR"],
            min_electric_power_hr=house_data["MIND_ELECTRIC_CONSUMPTION_HR"],
            tank_volume=house_data["TANK_MASS"],
            tes_start_soc=house_data["TES_START_VALUE"],
            max_temp_tes=house_data["MAX_TEMP_TES"],
            u_values_building=house_data["U_VALUES_BUILDING"],
            outdoor_temperature=outdoor_temperature.to_dict(),
            heat_source_temperature=outdoor_temperature.to_dict(),
            heat_demand=heat_demand.to_dict(),
            predict_tank_loss=False,
        )

        # Optimization
        result = optimize(
            buy_prices=get_profiles(input_data.index, buy_price_profile),
            heat_pumps=[hp],
            solver=solver,
        )

        # Evaluate
        results[day] = {
            "heat_pump_power": result[5],
            "energy_consumption": result[5].sum().sum() / 4000,
            "expected": expected_results.loc[
                pd.to_datetime(day), "Stromverbrauch"
            ],
        }
        results[day]["energy_difference"] = (
            results[day]["expected"] - results[day]["energy_consumption"]
        )
        results[day]["relative_difference"] = (
            results[day]["expected"] - results[day]["energy_consumption"]
        ) / results[day]["expected"]

        # Check results
        assert results[day]["energy_difference"] < 0.02, (
            f"Energy difference of {results[day]['energy_difference']}kWh "
            f"on {day} is higher than 20 Wh!"
        )  # kWh
        assert results[day]["relative_difference"] < 0.001, (
            "Relative difference of "
            f"{results[day]['relative_difference']} on {day} "
            "is higher than 0.1%!"
        )

    # Check average difference
    average_difference = sum(
        [results[day]["relative_difference"] for day in results]
    ) / len(results)
    assert average_difference < 0.01, (
        f"Average relative difference {average_difference} "
        "is higher than 1%"
    )
