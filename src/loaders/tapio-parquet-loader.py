import os
from PyQt6.QtWidgets import QInputDialog
import pandas as pd
import numpy as np
import json
from scipy.interpolate import interp1d
from scipy.optimize import curve_fit
import settings
import traceback
from utils.measurement import Measurement

menu_text = "Load Tapio Parquet data"
menu_priority = 3

file_types = "All Files (*);;Parquet files (*.parquet);;Calibration files (*.tcal);;Paper machine files (*.pmdata.json)"

RESAMPLE_STEP_DEFAULT_MM = 1

ASH_MAC = -100
LOG_VALS_MAX = 1000  # Maximum allowed value for logarithmic calibration output


def load_cd_samples_data(samples_file_path: str):
    """Load CD samples data from file and update measurement object."""
    with open(samples_file_path, 'r') as f:
        cd_data = json.load(f)
        peak_channel = cd_data['peak_channel']
        threshold = cd_data['threshold']
        peak_locations = cd_data['peak_locations']
        selected_samples = cd_data['selected_samples']

    return peak_channel, threshold, peak_locations, selected_samples


def get_sample_step():
    """Prompt the user for a sample step value."""
    sample_step, ok = QInputDialog.getDouble(None,
                                             "Sample Step",
                                             "Enter sample step value [m]:",
                                             settings.PQ_LOADER_GENERATE_DISTANCES_SAMPLE_STEP_DEFAULT,
                                             decimals=5)
    if ok:
        return sample_step
    else:
        return None


def load_data(fileNames: list[str]) -> Measurement | None:
    measurement = Measurement()
    parquet_file_path = None
    tcal_file_path = None
    pmdata_file_path = None
    valid_files_processed = False

    # Find relevant files from the provided list
    for fn in fileNames:
        if fn.endswith('.parquet') and not parquet_file_path:
            parquet_file_path = fn
        # Allow .tcal or -calibration.json
        elif fn.endswith('.json') and ("-calibration" in fn or fn.endswith(".tcal")) and not tcal_file_path:
            tcal_file_path = fn
        elif fn.endswith('.pmdata.json') and not pmdata_file_path:
            pmdata_file_path = fn
        elif fn.lower().endswith('.samples.json'):
            measurement.samples_file_path = fn

    if not parquet_file_path:
        print("No parquet file found in the provided list of files.")
        return None

    # Process Parquet file
    try:
        print(f"Loading Parquet data from: {parquet_file_path}")
        # Load Parquet data directly from the file path
        data_df = pd.read_parquet(parquet_file_path)

        basename = os.path.basename(parquet_file_path)
        measurement.data_file_path = basename
        measurement.measurement_label = os.path.splitext(
            basename)[0]  # Label from parquet file

        # This logic was previously inside zip processing, ensure it's correctly placed
        if len(data_df) > 1000:
            data_df = data_df.iloc[1000:]

        # Find the distance column (case-insensitive)
        distance_col = None
        for col in data_df.columns:
            if col.lower() == 'distance':
                distance_col = col
                break

        if settings.PQ_LOADER_GENERATE_DISTANCES:
            sample_step = get_sample_step()
            if sample_step is None:
                return None  # User canceled the input
            distances = np.arange(len(data_df)) * sample_step
            measurement.sample_step = sample_step
            # Keep all columns as data columns when generating distances
            data_columns = list(data_df.columns)
        else:
            if distance_col is None:
                print("Error: No 'distance' column found in parquet file")
                return None

            distances = data_df[distance_col].values
            distances = distances - distances[0]

            if len(distances) > 1:
                delta_distance = np.diff(distances).mean()
                sampling_frequency = 1000  # Hz
                delta_t = 1 / sampling_frequency
                measurement.pm_speed = 60 * (delta_distance / delta_t)
                print(
                    f"Average measurement speed [m/min]: {measurement.pm_speed:.2f}")
            else:  # Handle case with single data point or insufficient data for diff
                print("Not enough data points to calculate speed from distances.")
                measurement.pm_speed = 0

            total_samples = len(distances)
            sampling_frequency = 1000  # Re-state for clarity if block is separated
            total_time_seconds = total_samples / sampling_frequency
            total_distance = distances[-1] - \
                distances[0] if len(distances) > 0 else 0

            print(f"Total number of samples: {total_samples}")
            print(
                f"Total length of measurement [seconds]: {total_time_seconds:.2f}")
            print(f"Total distance of measurement [m]: {total_distance:.2f}")

            # Exclude distance column from data columns when using it for distances
            data_columns = [col for col in data_df.columns if col != distance_col]

        raw_data = data_df[data_columns].values

        print("Ensuring unique distance")
        unique_distances, first_occurrence_indices = np.unique(
            distances, return_index=True)
        aggregated_data = raw_data[first_occurrence_indices, :]

        print("Resampling")
        if len(unique_distances) < 2:  # Need at least two points to define a range for arange
            print("Not enough unique distance points to resample. Using original data.")
            resampled_distances = unique_distances
            resampled_data = aggregated_data
            measurement.sample_step = np.diff(unique_distances).mean() if len(
                unique_distances) > 1 else (RESAMPLE_STEP_DEFAULT_MM / 1000)
        else:
            resampled_distances = np.arange(
                unique_distances[0], unique_distances[-1], (RESAMPLE_STEP_DEFAULT_MM / 1000))
            # Handle edge case where arange yields empty due to step size vs range
            if len(resampled_distances) == 0 and len(unique_distances) > 0:
                resampled_distances = unique_distances[:1]  # Use first point

            resampled_data = np.zeros(
                (len(resampled_distances), aggregated_data.shape[1]))

            # Check if there are columns to interpolate and enough points
            if aggregated_data.shape[1] > 0 and len(unique_distances) >= 2:
                for i in range(aggregated_data.shape[1]):
                    voltage_interp = interp1d(unique_distances,
                                              aggregated_data[:, i],
                                              kind='linear',
                                              fill_value="extrapolate")
                    resampled_data[:, i] = voltage_interp(resampled_distances)
                measurement.sample_step = RESAMPLE_STEP_DEFAULT_MM / 1000
            # Single unique point
            elif aggregated_data.shape[1] > 0 and len(unique_distances) == 1:
                resampled_data = aggregated_data  # Use original aggregated data
                measurement.sample_step = (
                    RESAMPLE_STEP_DEFAULT_MM / 1000)  # Default step
            else:  # No data columns or not enough points and arange was empty
                # Empty data with correct num columns
                resampled_data = np.array([]).reshape(
                    0, aggregated_data.shape[1])
                measurement.sample_step = (RESAMPLE_STEP_DEFAULT_MM / 1000)
        # Finish distance generation

        measurement.channel_df = pd.DataFrame(
            resampled_data, columns=data_columns)
        measurement.distances = resampled_distances
        measurement.channels = measurement.channel_df.columns
        valid_files_processed = True


    except Exception as e:
        print(
            f"Error reading or processing parquet file {parquet_file_path}: {e}")
        traceback.print_exc()
        return None  # Critical error if Parquet loading fails

    # Process TCAL file if found and Parquet was loaded
    if tcal_file_path and valid_files_processed:
        try:
            print(f"Loading TCAL data from: {tcal_file_path}")
            with open(tcal_file_path, 'r', encoding='utf-8') as tcal_data_file:
                basename = os.path.basename(tcal_file_path)
                measurement.calibration_file_path = basename
                tcal_content = tcal_data_file.read()
                tcal_json = json.loads(tcal_content)

                units_dict = {}
                calibration_data = {}

                for channel_name in measurement.channel_df.columns:
                    cal_data = tcal_json.get(channel_name)
                    if cal_data:
                        calibration_data[channel_name] = cal_data
                        units_dict[channel_name] = cal_data.get(
                            "unit", "Unknown")
                    else:
                        # Default to Volts if no calibration
                        units_dict[channel_name] = "V"

                measurement.units = units_dict

                # Apply calibrations
                apply_calibration_with_uniform_trimming(
                    measurement, calibration_data)


                # Add calculated channels
                for channel_config in settings.CALCULATED_CHANNELS:
                    name = channel_config['name']
                    unit = channel_config['unit']
                    function = channel_config['function']
                    try:
                        result = function(measurement.channel_df)
                        if result is not None:
                            measurement.channel_df[name] = result
                            measurement.units[name] = unit
                            print(
                                f"Successfully added calculated channel {name}")
                        else:
                            print(
                                f"Calculation returned None for channel {name}")
                    except Exception as e_calc:
                        print(f"Failed to calculate channel {name}: {e_calc}")
                        traceback.print_exc()

                measurement.channel_df = measurement.channel_df.drop(
                    columns=settings.IGNORE_CHANNELS, errors='ignore')
                measurement.channels = measurement.channel_df.columns

                # If CD segments exist already, the split can now be done
                if measurement.samples_file_path:
                    peak_channel, threshold, peak_locations, selected_samples = load_cd_samples_data(
                        measurement.samples_file_path)
                    measurement.peak_channel = peak_channel
                    measurement.threshold = threshold
                    measurement.peak_locations = peak_locations
                    measurement.selected_samples = selected_samples
                    measurement.split_data_to_segments()


        except Exception as e:
            print(f"Error processing TCAL file {tcal_file_path}: {e}")
            traceback.print_exc()  # TCAL processing error is not fatal for measurement object

    # Process PMDATA file if found
    if pmdata_file_path and valid_files_processed:
        try:
            print(f"Loading PMDATA from: {pmdata_file_path}")
            measurement.pm_file_path = pmdata_file_path
            measurement.load_pm_file()  # This method uses measurement.pm_file_path
        except Exception as e:
            print(f"Error loading PM data file {pmdata_file_path}: {e}")
            traceback.print_exc()  # PMDATA error is not fatal

    if valid_files_processed and measurement.channel_df is not None and not measurement.channel_df.empty:
        return measurement
    else:
        if not valid_files_processed:
            print("Parquet file processing failed or was skipped.")
        elif measurement.channel_df is None or measurement.channel_df.empty:
            print("Data processing resulted in an empty dataset.")
        return None


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


def apply_calibration_with_uniform_trimming(measurement: Measurement, calibration_data):
    """Apply calibration and uniform trimming across all channels based on offset values, aligning distances."""
    # Dictionary to hold calibrated data temporarily and offset alignment values
    calibrated_channels = {}
    align_data_slices = {}
    calibrated_values = {}

    # Calculate the zero offset to handle negative minimum distances
    sample_step = measurement.sample_step
    print(calibration_data.values())
    min_distance_offset = min(cal_data.get('offset', 0)
                              for cal_data in calibration_data.values())
    distance_zero_offset = abs(
        min_distance_offset) if min_distance_offset < 0 else 0

    # Calibrate and align data for each channel
    for channel_name, cal_data in calibration_data.items():
        print(f"Calibrating channel: {channel_name}")
        if channel_name not in measurement.channel_df.columns:
            print(f"Warning: Channel {channel_name} not found in data")
            continue

        voltage_values = measurement.channel_df[channel_name].values

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

                # Optional offset parameter for calibration
                d = cal_data.get('d', 0)

                # Calculate slope and intercept using linear regression
                slope, intercept = np.polyfit(x_vals, y_vals, 1)

                # Apply linear equation y = mx + b + d
                calibrated_values = slope * voltage_values + intercept + d

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
                k = cal_data.get('k', ASH_MAC)

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
    measurement.channel_df = pd.DataFrame(
        trimmed_data, columns=calibrated_channels.keys())

    # Update distances to match the trimmed data length
    measurement.distances = measurement.distances[align_data_slices[min(
        align_data_slices, key=align_data_slices.get)]:][:data_len]

    # Flip the data if specified in settings
    if settings.FLIP_LOADED_DATA:
        measurement.channel_df = measurement.channel_df.iloc[::-1]
        # dataMixin.distances = np.flip(dataMixin.distances)
