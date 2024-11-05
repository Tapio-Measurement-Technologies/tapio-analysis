from utils.data_loader import DataMixin
import os
from PyQt6.QtWidgets import QInputDialog
import pandas as pd
import numpy as np
import json
from scipy.interpolate import interp1d

menu_text = "Load Tapio Parquet data"

dataMixin = DataMixin.getInstance()
file_types = "All Files (*);;Parquet files (*.parquet);;Calibration files (*.tcal);;Paper machine files (*.pmdata.json)"

RESAMPLE_STEP_DEFAULT_MM = 0.1
GENERATE_DISTANCES = False
SAMPLE_STEP_DEFAULT = 0.001


def get_sample_step():
    """Prompt the user for a sample step value."""
    sample_step, ok = QInputDialog.getDouble(None,
                                             "Sample Step",
                                             "Enter sample step value [m]:",
                                             SAMPLE_STEP_DEFAULT,
                                             decimals=5)
    if ok:
        return sample_step
    else:
        return None


def load_data(main_window, fileNames: list[str]):
    calibrations = {}

    for fn in fileNames:
        if fn.endswith('.parquet'):
            # Load Parquet data
            data_df = pd.read_parquet(fn)
            if len(data_df) > 1000:
                data_df = data_df.iloc[1000:]



            # First column is distances in meters, but for noise measurement we will ask for sample step
            distances = data_df.iloc[:, 0].values

            if GENERATE_DISTANCES:
                # If all distances are the same (noise measurement), ask for the sample step
                sample_step = get_sample_step()
                if sample_step is None:
                    return  # User canceled the input
                distances = np.arange(len(data_df)) * sample_step  # Create an artificial distance array
                dataMixin.sample_step = sample_step
            else:
                # Normal processing for real distance-based measurement
                delta_distance = np.diff(distances).mean()
                sampling_frequency = 1000  # Hz
                delta_t = 1 / sampling_frequency
                dataMixin.pm_speed = 60 * (delta_distance / delta_t)
                print(f"Average measurement speed [m/min]: {dataMixin.pm_speed:.2f}")

                total_samples = len(distances)
                total_time_seconds = total_samples / sampling_frequency
                total_distance = distances[-1] - distances[0]

                print(f"Total number of samples: {total_samples}")
                print(f"Total length of measurement [seconds]: {total_time_seconds:.2f}")
                print(f"Total distance of measurement [m]: {total_distance:.2f}")

            # Remaining columns are voltage data
            raw_data = data_df.iloc[:, 1:].values

            # Remove or aggregate duplicate distances by averaging the corresponding voltage values
            print("Ensuring unique distance")
            unique_distances, first_occurrence_indices = np.unique(distances, return_index=True)
            aggregated_data = raw_data[first_occurrence_indices, :]
            print("Resampling")



            resampled_distances = np.arange(
                unique_distances[0], unique_distances[-1], (RESAMPLE_STEP_DEFAULT_MM / 1000))
            resampled_data = np.zeros((len(resampled_distances), aggregated_data.shape[1]))

            for i in range(aggregated_data.shape[1]):
                voltage_interp = interp1d(
                    unique_distances, aggregated_data[:, i], kind='linear', fill_value="extrapolate")
                resampled_data[:, i] = voltage_interp(resampled_distances)

            # Store resampled data in DataMixin
            dataMixin.sample_step = RESAMPLE_STEP_DEFAULT_MM / 1000
            dataMixin.channel_df = pd.DataFrame(
                resampled_data, columns=data_df.columns[1:])
            dataMixin.distances = resampled_distances
            dataMixin.channels = dataMixin.channel_df.columns
            dataMixin.measurement_label = os.path.basename(fn)

        elif fn.endswith('.tcal'):
            # Load the calibration file and apply it
            with open(fn, 'r') as f:
                tcal_data = json.load(f)

            # Initialize units list
            units_dict = {}

            for channel_name in dataMixin.channel_df.columns:
                cal_data = tcal_data.get(channel_name)
                if cal_data:
                    apply_calibration(channel_name, cal_data)
                    units_dict[channel_name] = cal_data.get("unit", "Unknown")
                else:
                    units_dict[channel_name] = "V"

            dataMixin.units = units_dict

        elif fn.endswith('.pmdata.json'):
            dataMixin.pm_file_path = fn
            basename = os.path.basename(fn)
            main_window.fileLabels["Paper machine"].setText(f"{basename}")
            dataMixin.load_pm_file()


def apply_calibration(channel_name, cal_data):
    """Apply calibration based on the points in the .tcal file."""
    voltage_values = dataMixin.channel_df[channel_name].values

    if cal_data['type'] == 'linregr':
        points = cal_data['points']
        x_vals, y_vals = zip(*points)

        interpolator = interp1d(x_vals, y_vals, fill_value="extrapolate")
        calibrated_values = interpolator(voltage_values)

        offset = cal_data.get('offset', 0)
        calibrated_values += offset

        dataMixin.channel_df[channel_name] = calibrated_values
