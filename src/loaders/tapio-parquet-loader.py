import os
import logging
from PyQt6.QtWidgets import QInputDialog
import pandas as pd
import numpy as np
import json
from scipy.interpolate import interp1d
from scipy.optimize import curve_fit
import settings
from utils.measurement import Measurement

menu_text = "Load Tapio Parquet data"
menu_priority = 3

file_types = "All Files (*);;Parquet files (*.parquet);;Calibration files (*.tcal);;Paper machine files (*.pmdata.json)"

RESAMPLE_STEP_DEFAULT_MM = 1

ASH_MAC = -100
LOG_VALS_MAX = 1000  # Maximum allowed value for logarithmic calibration output

logger = logging.getLogger(__name__)


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

        is_json_cal = fn.endswith('.json') and "-calibration" in fn
        is_tcal = fn.endswith('.tcal')

        if fn.endswith('.parquet') and not parquet_file_path:
            parquet_file_path = fn
        # Allow .tcal or -calibration.json
        elif (is_json_cal or is_tcal) and not tcal_file_path:
            tcal_file_path = fn
        elif fn.endswith('.pmdata.json') and not pmdata_file_path:
            pmdata_file_path = fn
        elif fn.lower().endswith('.samples.json'):
            measurement.samples_file_path = fn

    logger.debug("TCAL file path: %s", tcal_file_path)

    if not parquet_file_path:
        logger.debug("No parquet file found in the provided list of files.")
        return None

    # Process Parquet file
    try:
        logger.debug("Loading Parquet data from: %s", parquet_file_path)
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
                logger.debug("Error: No 'distance' column found in parquet file")
                return None

            distances = data_df[distance_col].values
            distances = distances - distances[0]

            if len(distances) > 1:
                delta_distance = np.diff(distances).mean()
                sampling_frequency = 1000  # Hz
                delta_t = 1 / sampling_frequency
                measurement.pm_speed = 60 * (delta_distance / delta_t)
                logger.debug(
                    "Average measurement speed [m/min]: %.2f", measurement.pm_speed)
            else:  # Handle case with single data point or insufficient data for diff
                logger.debug("Not enough data points to calculate speed from distances.")
                measurement.pm_speed = 0

            total_samples = len(distances)
            sampling_frequency = 1000  # Re-state for clarity if block is separated
            total_time_seconds = total_samples / sampling_frequency
            total_distance = distances[-1] - \
                distances[0] if len(distances) > 0 else 0

            logger.debug("Total number of samples: %s", total_samples)
            logger.debug(
                "Total length of measurement [seconds]: %.2f", total_time_seconds)
            logger.debug("Total distance of measurement [m]: %.2f", total_distance)

            # Exclude distance column from data columns when using it for distances
            data_columns = [
                col for col in data_df.columns if col != distance_col]

        raw_data = data_df[data_columns].values

        logger.debug("Ensuring unique distance")
        unique_distances, first_occurrence_indices = np.unique(
            distances, return_index=True)
        aggregated_data = raw_data[first_occurrence_indices, :]

        logger.debug("Resampling")
        if len(unique_distances) < 2:  # Need at least two points to define a range for arange
            logger.debug("Not enough unique distance points to resample. Using original data.")
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
        logger.exception(
            "Error reading or processing parquet file %s: %s",
            parquet_file_path,
            e,
        )
        return None  # Critical error if Parquet loading fails

    # Process TCAL file if found and Parquet was loaded
    if tcal_file_path and valid_files_processed:
        try:
            logger.debug("Loading TCAL data from: %s", tcal_file_path)
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
                            logger.debug(
                                "Successfully added calculated channel %s", name)
                        else:
                            logger.debug(
                                "Calculation returned None for channel %s", name)
                    except Exception as e_calc:
                        logger.exception(
                            "Failed to calculate channel %s: %s", name, e_calc)

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
            logger.exception(
                "Error processing TCAL file %s: %s", tcal_file_path, e)

    # Process PMDATA file if found
    if pmdata_file_path and valid_files_processed:
        try:
            logger.debug("Loading PMDATA from: %s", pmdata_file_path)
            measurement.pm_file_path = pmdata_file_path
            measurement.load_pm_file()  # This method uses measurement.pm_file_path
        except Exception as e:
            logger.exception(
                "Error loading PM data file %s: %s", pmdata_file_path, e)

    if valid_files_processed and measurement.channel_df is not None and not measurement.channel_df.empty:
        return measurement
    else:
        if not valid_files_processed:
            logger.debug("Parquet file processing failed or was skipped.")
        elif measurement.channel_df is None or measurement.channel_df.empty:
            logger.debug("Data processing resulted in an empty dataset.")
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
    logger.debug("Starting calibration for %s channels", len(calibration_data))
    # Dictionary to hold calibrated data temporarily and offset alignment values
    calibrated_channels = {}
    align_data_slices = {}
    calibrated_values = {}

    # Calculate the zero offset to handle negative minimum distances
    sample_step = measurement.sample_step
    logger.debug("Sample step: %s", sample_step)
    min_distance_offset = min(cal_data.get('offset', 0)
                              for cal_data in calibration_data.values())
    distance_zero_offset = abs(
        min_distance_offset) if min_distance_offset < 0 else 0
    logger.debug(
        "Min distance offset: %s, distance zero offset: %s",
        min_distance_offset,
        distance_zero_offset,
    )

    # Calibrate and align data for each channel
    for channel_name, cal_data in calibration_data.items():
        logger.debug("Calibrating channel: %s", channel_name)
        if channel_name not in measurement.channel_df.columns:
            logger.debug("Warning: Channel %s not found in data", channel_name)
            continue

        voltage_values = measurement.channel_df[channel_name].values
        logger.debug(
            "%s - Input voltage stats: min=%.6f, max=%.6f, mean=%.6f",
            channel_name,
            voltage_values.min(),
            voltage_values.max(),
            voltage_values.mean(),
        )

        # Optional offset parameter for calibration, used in linregr and linint calibrations
        d = cal_data.get('d', 0)
        logger.debug(
            "%s - Calibration type: %s, d=%s",
            channel_name,
            cal_data['type'],
            d,
        )

        # Apply calibration based on the type
        if cal_data['type'] == 'none':
            # No calibration applied
            calibrated_values = voltage_values
            logger.debug("%s - no calibration applied", channel_name)

        elif cal_data['type'] == 'linregr':
            # Linear regression - using best-fit line
            try:
                points = cal_data.get('points', [])
                if not points:
                    raise ValueError("No calibration points provided")

                x_vals, y_vals = zip(*points)
                x_vals = np.array(x_vals)
                y_vals = np.array(y_vals)
                logger.debug("%s - linregr points: x=%s, y=%s", channel_name, x_vals, y_vals)

                # Calculate slope and intercept using linear regression
                slope, intercept = np.polyfit(x_vals, y_vals, 1)
                logger.debug(
                    "%s - linregr fitted: slope=%.6f, intercept=%.6f",
                    channel_name,
                    slope,
                    intercept,
                )

                # Apply linear equation y = mx + b + d
                calibrated_values = slope * voltage_values + intercept + d
                logger.debug(
                    "%s - linregr output stats: min=%.6f, max=%.6f, mean=%.6f",
                    channel_name,
                    calibrated_values.min(),
                    calibrated_values.max(),
                    calibrated_values.mean(),
                )

            except (ValueError, TypeError) as e:
                logger.debug(
                    "Warning: Invalid linear regression calibration for %s: %s",
                    channel_name,
                    e,
                )
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
                logger.debug("%s - linint points: x=%s, y=%s", channel_name, x_vals, y_vals)

                # Sort points by x values for proper interpolation
                sort_idx = np.argsort(x_vals)
                x_vals = x_vals[sort_idx]
                y_vals = y_vals[sort_idx]

                # Create interpolation function
                interpolator = interp1d(
                    x_vals, y_vals, kind='linear', bounds_error=False, fill_value="extrapolate")
                calibrated_values = interpolator(voltage_values) + d
                logger.debug(
                    "%s - linint output stats: min=%.6f, max=%.6f, mean=%.6f",
                    channel_name,
                    calibrated_values.min(),
                    calibrated_values.max(),
                    calibrated_values.mean(),
                )

            except (ValueError, TypeError) as e:
                logger.debug(
                    "Warning: Invalid linear interpolation calibration for %s: %s",
                    channel_name,
                    e,
                )
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
                logger.debug("%s - splog points: x=%s, y=%s", channel_name, x_vals, y_vals)

                # Remove minimum point to avoid asymptote issues
                min_index = np.argmin(x_vals)
                x_filtered = np.delete(x_vals, min_index)
                y_filtered = np.delete(y_vals, min_index)
                logger.debug(
                    "%s - splog filtered points: x=%s, y=%s",
                    channel_name,
                    x_filtered,
                    y_filtered,
                )

                # Fixed k parameter for single-point log
                k = cal_data.get('k', ASH_MAC)
                logger.debug("%s - splog k=%s", channel_name, k)

                # Fixed a parameter (typically close to minimum voltage)
                a = min(x_vals)
                logger.debug("%s - splog a=%s", channel_name, a)

                # Fit only the b parameter
                popt, _ = curve_fit(
                    lambda V, b: logarithmic_fit(V, k, a, b),
                    x_filtered, y_filtered, p0=[1], absolute_sigma=True
                )
                b = popt[0]
                logger.debug("%s - splog fitted b=%.6f", channel_name, b)

                # Apply calibration
                calibrated_values = logarithmic_fit(voltage_values, k, a, b)
                logger.debug(
                    "%s - splog output stats: min=%.6f, max=%.6f, mean=%.6f",
                    channel_name,
                    calibrated_values.min(),
                    calibrated_values.max(),
                    calibrated_values.mean(),
                )

            except (ValueError, TypeError) as e:
                logger.debug(
                    "Warning: Invalid splog calibration for %s: %s",
                    channel_name,
                    e,
                )
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
                logger.debug("%s - mplog points: x=%s, y=%s", channel_name, x_vals, y_vals)

                # Remove minimum point to avoid asymptote issues
                min_index = np.argmin(x_vals)
                x_filtered = np.delete(x_vals, min_index)
                y_filtered = np.delete(y_vals, min_index)
                logger.debug(
                    "%s - mplog filtered points: x=%s, y=%s",
                    channel_name,
                    x_filtered,
                    y_filtered,
                )

                # Fixed a parameter (typically close to minimum voltage)
                a = min(x_vals)
                logger.debug("%s - mplog a=%s", channel_name, a)

                # Fit both k and b parameters
                popt, _ = curve_fit(
                    lambda V, k, b: logarithmic_fit(V, k, a, b),
                    x_filtered, y_filtered, p0=[-1, 1], absolute_sigma=True
                )
                k, b = popt  # Unpack the fitted parameters
                logger.debug(
                    "%s - mplog fitted k=%.6f, b=%.6f",
                    channel_name,
                    k,
                    b,
                )

                # Apply calibration
                calibrated_values = logarithmic_fit(voltage_values, k, a, b)
                logger.debug(
                    "%s - mplog output stats: min=%.6f, max=%.6f, mean=%.6f",
                    channel_name,
                    calibrated_values.min(),
                    calibrated_values.max(),
                    calibrated_values.mean(),
                )

            except (ValueError, TypeError) as e:
                logger.debug(
                    "Warning: Invalid mplog calibration for %s: %s",
                    channel_name,
                    e,
                )
                calibrated_values = voltage_values

        else:
            # Unknown calibration type
            logger.debug(
                "Warning: Unknown calibration type '%s' for %s, using raw voltage values",
                cal_data['type'],
                channel_name,
            )
            calibrated_values = voltage_values

        # Calculate the starting trim index for alignment
        offset = cal_data.get('offset', 0)
        align_start_index = round(
            (distance_zero_offset + offset) / sample_step)
        align_data_slices[channel_name] = align_start_index
        logger.debug(
            "%s - offset=%s, distance_zero_offset=%s, sample_step=%s, align_start_index=%s",
            channel_name,
            offset,
            distance_zero_offset,
            sample_step,
            align_start_index,
        )

        # Store the calibrated values temporarily
        calibrated_channels[channel_name] = calibrated_values

    # Determine the final uniform length for trimming based on the maximum alignment slice
    data_len = min(len(values) - align_data_slices[channel]
                   for channel, values in calibrated_channels.items())
    logger.debug("Calculated data_len: %s", data_len)
    if data_len <= 0:
        logger.debug(
            "ERROR: data_len is %s, which would result in empty data. Check offset values and sample_step.",
            data_len,
        )
        logger.debug("align_data_slices: %s", align_data_slices)
        logger.debug(
            "data lengths: %s",
            [(channel, len(values)) for channel, values in calibrated_channels.items()],
        )
        # Skip trimming if data_len <= 0
        measurement.channel_df = pd.DataFrame(calibrated_channels)
        measurement.distances = measurement.distances
        return
    logger.debug("Final data length after trimming: %s", data_len)

    # Initialize a new array to store the aligned and trimmed data
    trimmed_data = np.empty((data_len, len(calibrated_channels)))
    for index, (channel_name, calibrated_values) in enumerate(calibrated_channels.items()):
        start_trim = align_data_slices[channel_name]
        # Align and trim each channel based on the calculated slice
        trimmed_data[:, index] = calibrated_values[start_trim:start_trim + data_len]
        logger.debug(
            "%s - trimmed data stats: min=%.6f, max=%.6f, mean=%.6f",
            channel_name,
            trimmed_data[:, index].min(),
            trimmed_data[:, index].max(),
            trimmed_data[:, index].mean(),
        )

    # Update the dataMixin with the trimmed DataFrame
    measurement.channel_df = pd.DataFrame(
        trimmed_data, columns=calibrated_channels.keys())
    logger.debug("Final channel_df shape: %s", measurement.channel_df.shape)
    for col in measurement.channel_df.columns:
        logger.debug(
            "Final %s stats: min=%.6f, max=%.6f, mean=%.6f",
            col,
            measurement.channel_df[col].min(),
            measurement.channel_df[col].max(),
            measurement.channel_df[col].mean(),
        )

    # Update distances to match the trimmed data length
    measurement.distances = measurement.distances[align_data_slices[min(
        align_data_slices, key=align_data_slices.get)]:][:data_len]

    # Flip the data if specified in settings
    if settings.FLIP_LOADED_DATA:
        measurement.channel_df = measurement.channel_df.iloc[::-1]
        logger.debug("Data flipped as per settings.FLIP_LOADED_DATA")
        # dataMixin.distances = np.flip(dataMixin.distances)
