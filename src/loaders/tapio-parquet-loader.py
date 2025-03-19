from utils.data_loader import DataMixin
import os
from PyQt6.QtWidgets import QInputDialog
import pandas as pd
import numpy as np
import json
from scipy.interpolate import interp1d
from scipy.optimize import curve_fit
import settings
import traceback

import zipfile
from io import BytesIO

menu_text = "Load Tapio Parquet data"
menu_priority = 2

dataMixin = DataMixin.getInstance()
file_types = "All Files (*);;Parquet files (*.parquet);;Calibration files (*.tcal);;Paper machine files (*.pmdata.json)"

RESAMPLE_STEP_DEFAULT_MM = 1
GENERATE_DISTANCES = False
SAMPLE_STEP_DEFAULT = 0.001

ASH_MAC = -100
LOG_VALS_MAX = 1000  # Maximum allowed value for logarithmic calibration output


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
                tcal_file = next((f for f in file_list if f.endswith(
                    '.json') and "-calibration" in f), None)

                if parquet_file:
                    with zip_ref.open(parquet_file) as parquet_data:
                        # Read parquet file as bytes
                        parquet_bytes = BytesIO(parquet_data.read())
                        # Load Parquet data into a DataFrame
                        data_df = pd.read_parquet(parquet_bytes)

                        # Add file name labels
                        basename = os.path.basename(parquet_file)
                        main_window.fileLabels["Data"].setText(f"{basename}")

                        if len(data_df) > 1000:
                            data_df = data_df.iloc[1000:]

                        distances = data_df.iloc[:, 0].values
                        distances = distances - distances[0]

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
                        dataMixin.measurement_label = os.path.splitext(
                            os.path.basename(fn))[0]

                if tcal_file:
                    with zip_ref.open(tcal_file) as tcal_data:
                        basename = os.path.basename(tcal_file)
                        main_window.fileLabels["Calibration"].setText(
                            f"{basename}")
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

                        dataMixin.units = units_dict

                        # First apply calibrations
                        apply_calibration_with_uniform_trimming(
                            calibration_data)

                        # Then add calculated channels
                        for channel in settings.CALCULATED_CHANNELS:
                            name = channel['name']
                            unit = channel['unit']
                            function = channel['function']
                            try:
                                result = function(dataMixin.channel_df)
                                if result is not None:
                                    dataMixin.channel_df[name] = result
                                    dataMixin.units[name] = unit
                                    print(
                                        f"Successfully added calculated channel {name}")
                                else:
                                    print(
                                        f"Calculation returned None for channel {name}")
                            except Exception as e:
                                print(
                                    f"Failed to calculate channel {name}: {e}")
                                traceback.print_exc()

                        dataMixin.channel_df = dataMixin.channel_df.drop(
                            columns=settings.IGNORE_CHANNELS, errors='ignore')

                        dataMixin.channels = dataMixin.channel_df.columns
        elif fn.endswith('.pmdata.json'):
            dataMixin.pm_file_path = fn
            basename = os.path.basename(fn)
            main_window.fileLabels["Paper machine"].setText(f"{basename}")
            dataMixin.load_pm_file()


def logarithmic_fit(V, k, a, b):
    """Helper function for logarithmic calibration."""
    # Create a mask for valid values (where V-a > 0)
    valid_mask = (V - a) > 0
    values = np.full_like(V, LOG_VALS_MAX)  # Initialize with LOG_VALS_MAX

    # Calculate logarithm only for valid values
    values[valid_mask] = k * np.log(V[valid_mask] - a) + b

    # Cap the output values
    values[values > LOG_VALS_MAX] = LOG_VALS_MAX
    return values


def apply_calibration_with_uniform_trimming(calibration_data):
    """Apply calibration and uniform trimming across all channels based on offset values, aligning distances."""
    # Dictionary to hold calibrated data temporarily and offset alignment values
    calibrated_channels = {}
    align_data_slices = {}

    # Calculate the zero offset to handle negative minimum distances
    sample_step = dataMixin.sample_step
    print(calibration_data.values())
    min_distance_offset = min(cal_data.get('offset', 0)
                              for cal_data in calibration_data.values())
    distance_zero_offset = abs(
        min_distance_offset) if min_distance_offset < 0 else 0

    # Calibrate and align data for each channel
    for channel_name, cal_data in calibration_data.items():
        print(f"Calibrating channel: {channel_name}")
        if channel_name not in dataMixin.channel_df.columns:
            print(f"Warning: Channel {channel_name} not found in data")
            continue

        voltage_values = dataMixin.channel_df[channel_name].values

        # Apply calibration based on the type
        if cal_data['type'] == 'linregr':
            # Linear regression - using best-fit line
            try:
                points = cal_data.get('points', [])
                if not points:
                    raise ValueError("No calibration points provided")

                x_vals, y_vals = zip(*points)
                x_vals = np.array(x_vals)
                y_vals = np.array(y_vals)

                # Calculate slope and intercept using linear regression
                slope, intercept = np.polyfit(x_vals, y_vals, 1)

                # Apply linear equation y = mx + b
                calibrated_values = slope * voltage_values + intercept

            except (ValueError, TypeError) as e:
                print(
                    f"Warning: Invalid linear regression calibration for {channel_name}: {e}")
                calibrated_values = voltage_values

        elif cal_data['type'] == 'linint':
            # Linear interpolation
            try:
                points = cal_data.get('points', [])
                if not points:
                    raise ValueError("No calibration points provided")

                x_vals, y_vals = zip(*points)
                x_vals = np.array(x_vals)
                y_vals = np.array(y_vals)

                # Sort points by x values for proper interpolation
                sort_idx = np.argsort(x_vals)
                x_vals = x_vals[sort_idx]
                y_vals = y_vals[sort_idx]

                # Create interpolation function
                interpolator = interp1d(
                    x_vals, y_vals, kind='linear', bounds_error=False, fill_value="extrapolate")
                calibrated_values = interpolator(voltage_values)

            except (ValueError, TypeError) as e:
                print(
                    f"Warning: Invalid linear interpolation calibration for {channel_name}: {e}")
                calibrated_values = voltage_values

        elif cal_data['type'] == 'splog':
            # Single-point logarithmic calibration
            try:
                points = cal_data.get('points', [])
                if not points:
                    raise ValueError("No calibration points provided")

                x_vals, y_vals = zip(*points)
                x_vals = np.array(x_vals)
                y_vals = np.array(y_vals)

                # Remove minimum point to avoid asymptote issues
                min_index = np.argmin(x_vals)
                x_filtered = np.delete(x_vals, min_index)
                y_filtered = np.delete(y_vals, min_index)

                # Fixed k parameter for single-point log
                k = ASH_MAC
                # Fixed a parameter (typically close to minimum voltage)
                a = min(x_vals)

                # Fit only the b parameter
                popt, _ = curve_fit(
                    lambda V, b: logarithmic_fit(V, k, a, b),
                    x_filtered, y_filtered, p0=[1], absolute_sigma=True
                )
                b = popt[0]

                # Apply calibration
                calibrated_values = logarithmic_fit(voltage_values, k, a, b)

            except (ValueError, TypeError) as e:
                print(
                    f"Warning: Invalid splog calibration for {channel_name}: {e}")
                calibrated_values = voltage_values

        elif cal_data['type'] == 'mplog':
            # Multi-point logarithmic calibration
            try:
                points = cal_data.get('points', [])
                if not points:
                    raise ValueError("No calibration points provided")

                x_vals, y_vals = zip(*points)
                x_vals = np.array(x_vals)
                y_vals = np.array(y_vals)

                # Remove minimum point to avoid asymptote issues
                min_index = np.argmin(x_vals)
                x_filtered = np.delete(x_vals, min_index)
                y_filtered = np.delete(y_vals, min_index)

                # Fixed a parameter (typically close to minimum voltage)
                a = min(x_vals)

                # Fit both k and b parameters
                popt, _ = curve_fit(
                    lambda V, k, b: logarithmic_fit(V, k, a, b),
                    x_filtered, y_filtered, p0=[-1, 1], absolute_sigma=True
                )
                k, b = popt  # Unpack the fitted parameters

                # Apply calibration
                calibrated_values = logarithmic_fit(voltage_values, k, a, b)

            except (ValueError, TypeError) as e:
                print(
                    f"Warning: Invalid mplog calibration for {channel_name}: {e}")
                calibrated_values = voltage_values

        # Calculate the starting trim index for alignment
        offset = cal_data.get('offset', 0)
        align_start_index = round(
            (distance_zero_offset + offset) / sample_step)
        align_data_slices[channel_name] = align_start_index

        # Store the calibrated values temporarily
        calibrated_channels[channel_name] = calibrated_values

    # Determine the final uniform length for trimming based on the maximum alignment slice
    data_len = min(len(values) - align_data_slices[channel]
                   for channel, values in calibrated_channels.items())

    # Initialize a new array to store the aligned and trimmed data
    trimmed_data = np.empty((data_len, len(calibrated_channels)))
    for index, (channel_name, calibrated_values) in enumerate(calibrated_channels.items()):
        start_trim = align_data_slices[channel_name]
        # Align and trim each channel based on the calculated slice
        trimmed_data[:, index] = calibrated_values[start_trim:start_trim + data_len]

    # Update the dataMixin with the trimmed DataFrame
    dataMixin.channel_df = pd.DataFrame(
        trimmed_data, columns=calibrated_channels.keys())

    # Update distances to match the trimmed data length
    dataMixin.distances = dataMixin.distances[align_data_slices[min(
        align_data_slices, key=align_data_slices.get)]:][:data_len]

    # Flip the data if specified in settings
    if settings.FLIP_LOADED_DATA:
        dataMixin.channel_df = dataMixin.channel_df.iloc[::-1]
        # dataMixin.distances = np.flip(dataMixin.distances)
