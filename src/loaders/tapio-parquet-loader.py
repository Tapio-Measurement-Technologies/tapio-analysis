from utils.data_loader import DataMixin
import os
from PyQt6.QtWidgets import QInputDialog
import pandas as pd
import numpy as np
import json
from scipy.interpolate import interp1d

import zipfile
from io import BytesIO

menu_text = "Load Tapio Parquet data"
menu_priority = 2

dataMixin = DataMixin.getInstance()
file_types = "All Files (*);;Parquet files (*.parquet);;Calibration files (*.tcal);;Paper machine files (*.pmdata.json)"

RESAMPLE_STEP_DEFAULT_MM = 1
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
        if fn.endswith('.zip'):
            # Open the ZIP file
            with zipfile.ZipFile(fn, 'r') as zip_ref:
                # List files in the zip archive
                file_list = zip_ref.namelist()

                # Extract parquet and tcal files
                parquet_file = next(
                    (f for f in file_list if f.endswith('.parquet')), None)
                tcal_file = next(
                    (f for f in file_list if f.endswith('.json')), None)

                if parquet_file:
                    with zip_ref.open(parquet_file) as parquet_data:
                        # Read parquet file as bytes
                        parquet_bytes = BytesIO(parquet_data.read())
                        # Load Parquet data into a DataFrame
                        data_df = pd.read_parquet(parquet_bytes)

                        if len(data_df) > 1000:
                            data_df = data_df.iloc[1000:]

                        distances = data_df.iloc[:, 0].values

                        if GENERATE_DISTANCES:
                            sample_step = get_sample_step()
                            if sample_step is None:
                                return  # User canceled the input
                            distances = np.arange(len(data_df)) * sample_step
                            dataMixin.sample_step = sample_step
                        else:
                            delta_distance = np.diff(distances).mean()
                            sampling_frequency = 1000  # Hz
                            delta_t = 1 / sampling_frequency
                            dataMixin.pm_speed = 60 * \
                                (delta_distance / delta_t)
                            print(
                                f"Average measurement speed [m/min]: {dataMixin.pm_speed:.2f}")

                            total_samples = len(distances)
                            total_time_seconds = total_samples / sampling_frequency
                            total_distance = distances[-1] - distances[0]

                            print(f"Total number of samples: {total_samples}")
                            print(f"Total length of measurement [seconds]: {
                                  total_time_seconds:.2f}")
                            print(f"Total distance of measurement [m]: {
                                  total_distance:.2f}")

                        raw_data = data_df.iloc[:, 1:].values

                        print("Ensuring unique distance")
                        unique_distances, first_occurrence_indices = np.unique(
                            distances, return_index=True)
                        aggregated_data = raw_data[first_occurrence_indices, :]
                        print("Resampling")

                        resampled_distances = np.arange(unique_distances[0], unique_distances[-1],
                                                        (RESAMPLE_STEP_DEFAULT_MM / 1000))
                        resampled_data = np.zeros(
                            (len(resampled_distances), aggregated_data.shape[1]))

                        for i in range(aggregated_data.shape[1]):
                            voltage_interp = interp1d(unique_distances,
                                                      aggregated_data[:, i],
                                                      kind='linear',
                                                      fill_value="extrapolate")
                            resampled_data[:, i] = voltage_interp(
                                resampled_distances)

                        dataMixin.sample_step = RESAMPLE_STEP_DEFAULT_MM / 1000
                        dataMixin.channel_df = pd.DataFrame(
                            resampled_data, columns=data_df.columns[1:])
                        dataMixin.distances = resampled_distances
                        dataMixin.channels = dataMixin.channel_df.columns
                        dataMixin.measurement_label = os.path.basename(fn)

                if tcal_file:
                    with zip_ref.open(tcal_file) as tcal_data:
                        # Load the calibration file and apply it
                        tcal_content = tcal_data.read().decode("utf-8")
                        tcal_json = json.loads(tcal_content)

                        units_dict = {}
                        calibration_data = {}

                        for channel_name in dataMixin.channel_df.columns:
                            cal_data = tcal_json.get(channel_name)
                            if cal_data:
                                calibration_data[channel_name] = cal_data
                                units_dict[channel_name] = cal_data.get(
                                    "unit", "Unknown")
                            else:
                                units_dict[channel_name] = "V"

                        apply_calibration_with_uniform_trimming(
                            calibration_data)
                        dataMixin.units = units_dict

        elif fn.endswith('.pmdata.json'):
            dataMixin.pm_file_path = fn
            basename = os.path.basename(fn)
            main_window.fileLabels["Paper machine"].setText(f"{basename}")
            dataMixin.load_pm_file()


def apply_calibration_with_uniform_trimming(calibration_data):
    """Apply calibration and uniform trimming across all channels based on offset values, aligning distances."""
    # Dictionary to hold calibrated data temporarily and offset alignment values
    calibrated_channels = {}
    align_data_slices = {}

    # Calculate the zero offset to handle negative minimum distances
    sample_step = dataMixin.sample_step
    min_distance_offset = min(cal_data.get('offset', 0) for cal_data in calibration_data.values())
    distance_zero_offset = abs(min_distance_offset) if min_distance_offset < 0 else 0

    # Calibrate and align data for each channel
    for channel_name, cal_data in calibration_data.items():
        print(f"Calibrating channel: {channel_name}")
        voltage_values = dataMixin.channel_df[channel_name].values

        # Apply calibration based on the type
        if cal_data['type'] == 'linregr':
            # Linear interpolation based on provided points
            points = cal_data['points']
            x_vals, y_vals = zip(*points)
            interpolator = interp1d(x_vals, y_vals, fill_value="extrapolate")
            calibrated_values = interpolator(voltage_values)
        elif cal_data['type'] == 'multi-point-log':
            # Logarithmic interpolation for multi-point calibration
            points = cal_data['points']
            x_vals, y_vals = zip(*points)
            interpolator = interp1d(np.log(x_vals), y_vals, fill_value="extrapolate")
            calibrated_values = interpolator(np.log(voltage_values))
        else:
            print(f"Warning: Unsupported calibration type '{cal_data['type']}' for channel '{channel_name}'")
            calibrated_values = voltage_values  # Fallback to original values if unsupported

        # Calculate the starting trim index for alignment
        offset = cal_data.get('offset', 0)
        align_start_index = round((distance_zero_offset + offset) / sample_step)
        align_data_slices[channel_name] = align_start_index

        # Store the calibrated values temporarily
        calibrated_channels[channel_name] = calibrated_values

    # Determine the final uniform length for trimming based on the maximum alignment slice
    data_len = min(len(values) - align_data_slices[channel] for channel, values in calibrated_channels.items())

    # Initialize a new array to store the aligned and trimmed data
    trimmed_data = np.empty((data_len, len(calibrated_channels)))
    for index, (channel_name, calibrated_values) in enumerate(calibrated_channels.items()):
        start_trim = align_data_slices[channel_name]
        # Align and trim each channel based on the calculated slice
        trimmed_data[:, index] = calibrated_values[start_trim:start_trim + data_len]

    # Update the dataMixin with the trimmed DataFrame
    dataMixin.channel_df = pd.DataFrame(trimmed_data, columns=calibrated_channels.keys())

    # Update distances to match the trimmed data length
    dataMixin.distances = dataMixin.distances[align_data_slices[min(align_data_slices, key=align_data_slices.get)]:][:data_len]

