import logging
import traceback
import settings
import os
import numpy as np
import pandas as pd
import json
from utils.measurement import Measurement, drop_unusable_channels

menu_text = "Load Tapio data"
menu_priority = 2

file_types = "All Files (*);;Calibration files (*.ca2);;Data files (*.da2);;Header files (*.pk2);;Paper machine files (*.pmdata.json);;CD Sample location files (*.samples.json)"


def load_data(fileNames: list[str]) -> Measurement | None:
    """
    Load Tapio data from a list of files and return a Measurement object.
    """
    measurement = Measurement()

    for fn in fileNames:
        # Extract the base name of the file
        basename = os.path.basename(fn)

        if fn.lower().endswith('.ca2'):
            measurement.calibration_file_path = fn
        elif fn.lower().endswith('.da2'):
            measurement.data_file_path = fn
        elif fn.lower().endswith('.pk2'):
            measurement.header_file_path = fn
        elif fn.lower().endswith('.pmdata.json'):
            measurement.pm_file_path = fn
            measurement.load_pm_file()
        elif fn.lower().endswith('.samples.json'):
            measurement.samples_file_path = fn

    if measurement.calibration_file_path and measurement.data_file_path and measurement.header_file_path:
        # Load legacy data
        sensor_df, units, sample_step, info, pm_speed = parse_legacy_data(
            measurement.header_file_path,
            measurement.calibration_file_path,
            measurement.data_file_path
        )

        # Remove ignored source channels before calculated channels are added.
        # This lets calculated channels intentionally replace stale raw channels
        # with the same name, such as Density.
        sensor_df, units = remove_ignored_channels(sensor_df, units)

        # Add calculated channels
        sensor_df, units = add_calculated_channels(sensor_df, units)

        # Drop channels that carry no usable data (e.g. a disconnected sensor).
        sensor_df, units = drop_unusable_channels(sensor_df, units)

        # Update measurement object with loaded data
        measurement.measurement_label = info
        measurement.channels = sensor_df.columns.tolist()
        measurement.channel_df = sensor_df
        measurement.units = units
        measurement.sample_step = sample_step
        measurement.pm_speed = pm_speed

        # Calculate distances
        number_of_measurements = len(sensor_df)
        indices = np.arange(number_of_measurements)
        measurement.distances = indices * sample_step

        # Load CD samples data if available
        if measurement.samples_file_path:
            peak_channel, threshold, peak_locations, selected_samples, tape_width_mm = load_cd_samples_data(
                measurement.samples_file_path)
            measurement.peak_channel = peak_channel
            measurement.threshold = threshold
            measurement.peak_locations = peak_locations
            measurement.selected_samples = selected_samples
            measurement.tape_width_mm = tape_width_mm
            measurement.split_data_to_segments()

        logging.info("Loaded data")
        return measurement

    return None


def remove_ignored_channels(sensor_df, units):
    """Remove ignored source channels from the dataframe and units mapping."""
    sensor_df = sensor_df.drop(
        columns=settings.IGNORE_CHANNELS, errors='ignore')

    if isinstance(units, dict):
        for channel in settings.IGNORE_CHANNELS:
            units.pop(channel, None)

    return sensor_df, units


def add_calculated_channels(sensor_df, units):
    """Add calculated channels to the sensor dataframe."""
    for channel in settings.CALCULATED_CHANNELS:
        name = channel['name']
        unit = channel['unit']
        function = channel['function']
        try:
            sensor_df[name] = function(sensor_df)
            units[name] = unit
            print(f"Added calculated channel {name}")
        except Exception as e:
            print(f"Failed to calculate channel {name}: {e}")
            traceback.print_exc()

    return sensor_df, units


def read_common_from_ca(cal_file):
    """Read common parameters from calibration file."""
    cal_file.seek(0)
    reading_sensor_names = False
    channels_n = None
    ad_factor = None
    formation = None
    transmission_channel = None
    bw_channel = None

    for line in cal_file:
        line = line.strip()
        if line.startswith('[Common]'):
            reading_sensor_names = True
        elif reading_sensor_names:
            if line.startswith('['):
                break
            if line:
                parts = line.split('\t')
                if len(parts) >= 3:
                    channels_n = int(float(parts[0]))
                    ad_factor = float(parts[1])  # Number of steps per volt
                    formation = True if int(float(parts[2])) == 1 else False
                    transmission_channel = int(float(parts[3]))
                    bw_channel = int(float(parts[4]))

    return channels_n, ad_factor, formation, transmission_channel, bw_channel


def read_channel_names_units_from_ca(cal_file):
    """Read channel names and units from calibration file.

    A sensor with a logical channel number of -1 was not acquired, so it is left
    out of sensor_names. It keeps its column everywhere else in the file though,
    which is why the column each remaining sensor occupies is returned as well:
    reading the [Sensor Param.] block by position in sensor_names would give
    every channel after a disabled one the wrong sensor's calibration.
    """
    sensor_names = []
    units = {}
    logical_channel_numbers = {}
    sensor_columns = {}
    # Use running number for unnamed channels in case there are multiple
    n_unnamed_channels = 0

    cal_file.seek(0)
    reading_sensor_names = False
    column = 0
    for line in cal_file:
        if line.startswith('[Sensor Names]'):
            reading_sensor_names = True
        elif reading_sensor_names:
            if line.startswith('['):
                break
            if line:
                parts = line.split('\t')
                parts = [part.strip() for part in parts]

                if len(parts) >= 3:
                    sensor_name = parts[0]
                    if not sensor_name:
                        n_unnamed_channels += 1
                        sensor_name = f"Unnamed channel {n_unnamed_channels}"
                    logical_channel_number = parts[2]
                    if logical_channel_number != "-1":
                        units[sensor_name] = parts[1]
                        logical_channel_numbers[sensor_name] = logical_channel_number
                        sensor_columns[sensor_name] = column
                        sensor_names.append(sensor_name)
                    else:
                        logging.info(
                            "Channel %s in column %d has no logical channel number "
                            "and is not part of the measurement.", sensor_name, column)
                    column += 1

    return sensor_names, units, logical_channel_numbers, sensor_columns


def resolve_data_columns(sensor_names, logical_channel_numbers):
    """Column each sensor occupies in the interleaved data file.

    The logical channel number is the channel's place in the acquired data
    stream, which is what makes -1 mean "not acquired". Numbers that cannot be a
    set of columns fall back to the order the sensors are listed in, which is
    also what this resolves to for a file that numbers its acquired channels
    0, 1, 2 ... in listing order.
    """
    columns = []
    for sensor_name in sensor_names:
        try:
            columns.append(int(float(logical_channel_numbers[sensor_name])))
        except (KeyError, TypeError, ValueError):
            columns.append(-1)

    if all(column >= 0 for column in columns) and len(set(columns)) == len(columns):
        return columns

    logging.warning(
        "Logical channel numbers %s cannot be data file columns; reading the "
        "channels in the order the calibration file lists them.", columns)
    return list(range(len(sensor_names)))


def read_info_from_header(header_file):
    """Read measurement info from header file."""
    info = None
    header_file.seek(0)
    reading_sensor_names = False
    for line in header_file:
        line = line.strip()
        if line.startswith('[Files]'):
            reading_sensor_names = True
            index = 0
        elif reading_sensor_names:
            if line.startswith('['):
                break
            if line and (index == 5):
                info = line
            index += 1
    return info


def read_calibration_data_from_ca(cal_file, sensor_names, sensor_columns=None):
    """Read calibration data for sensors from calibration file.

    :param sensor_columns: Column each sensor occupies in the [Sensor Param.]
        rows, as returned by read_channel_names_units_from_ca. Defaults to the
        position in sensor_names, which only holds when the file lists no
        disabled channels.
    """
    calibrated = {}
    sensor_distances = {}
    sensor_scales = {}
    sensor_offsets = {}
    sensor_calibration_types = {}
    asymptotic_values = {}

    if sensor_columns is None:
        sensor_columns = {name: index for index, name in enumerate(sensor_names)}
    columns = [sensor_columns[name] for name in sensor_names]

    cal_file.seek(0)
    reading_sensor_names = False
    for line in cal_file:
        line = line.strip()
        if line.startswith('[Sensor Param.]'):
            reading_sensor_names = True
            index = 0
        elif reading_sensor_names:
            if line.startswith('['):
                break
            if line and index > 0:
                parts = line.split('\t')
                if len(parts) <= max(columns, default=-1):
                    raise ValueError(
                        f"Row {index} of [Sensor Param.] has {len(parts)} columns, "
                        f"but the calibration file's channels occupy {max(columns) + 1}")
                filtered_parts = [parts[column] for column in columns]
                if index == 1:
                    calibrated = {
                        n: float(filtered_parts[i]) == 1 for i, n in enumerate(sensor_names)}
                elif index == 2:
                    sensor_distances = {
                        n: float(filtered_parts[i]) for i, n in enumerate(sensor_names)}
                elif index == 3:
                    sensor_scales = {
                        n: float(filtered_parts[i]) for i, n in enumerate(sensor_names)}
                elif index == 4:
                    sensor_offsets = {
                        n: float(filtered_parts[i]) for i, n in enumerate(sensor_names)}
                elif index == 5:
                    sensor_calibration_types = {
                        n: float(filtered_parts[i]) for i, n in enumerate(sensor_names)}
                elif index == 6:
                    asymptotic_values = {
                        n: float(filtered_parts[i]) for i, n in enumerate(sensor_names)}

            index += 1

    return calibrated, sensor_distances, sensor_scales, sensor_offsets, sensor_calibration_types, asymptotic_values


def read_meas_param(header_file):
    """Read measurement parameters from header file."""
    pm_speed = None
    length = None
    sample_step = None

    header_file.seek(0)
    reading_sensor_names = False
    for line in header_file:
        line = line.strip()
        if line.startswith('[Meas. Param.]'):
            reading_sensor_names = True
        elif reading_sensor_names:
            if line.startswith('['):
                break
            if line:
                parts = line.split('\t')
                if len(parts) >= 5:
                    pm_speed = float(parts[0])  # In m/s
                    length = float(parts[3])  # m
                    sample_step = float(parts[4])  # m

    return pm_speed, length, sample_step


def read_binary_data(file_path, num_channels):
    """Read interleaved big-endian 16 bit samples from a data file.

    Read straight into a numpy array instead of building a format string with
    one 'h' per sample and unpacking into a Python tuple. This also tolerates a
    trailing partial record, which struct.unpack rejects outright because it
    requires the buffer length to match the format exactly.
    """
    with open(file_path, 'rb') as file:
        file_content = file.read()

    num_data_points = len(file_content) // (2 * num_channels)
    samples = np.frombuffer(
        file_content, dtype='>i2', count=num_data_points * num_channels)

    trailing_bytes = len(file_content) - num_data_points * num_channels * 2
    if trailing_bytes:
        logging.warning(
            "Data file has %d trailing byte(s) that do not form a complete record; ignoring them.",
            trailing_bytes)

    return samples.reshape(num_data_points, num_channels)


def parse_legacy_data(header_file_path, cal_file_path, data_file_path):
    """Parse legacy Tapio data files and return processed data."""
    with open(cal_file_path, 'r', encoding='iso-8859-1') as cal_file:
        sensor_names, units, logical_channel_numbers, sensor_columns = read_channel_names_units_from_ca(
            cal_file)
        channels_n, ad_factor, formation, transmission_channel, bw_channel = read_common_from_ca(
            cal_file)
        calibrated, sensor_distances, sensor_scales, sensor_offsets, sensor_calibration_types, asymptotic_values = read_calibration_data_from_ca(
            cal_file, sensor_names, sensor_columns)

    with open(header_file_path, 'r', encoding='iso-8859-1') as header_file:
        pm_speed, length, sample_step = read_meas_param(header_file)
        info = read_info_from_header(header_file)

    if not sensor_names:
        raise ValueError("Calibration file declares no acquired channels")

    if channels_n is not None and channels_n != len(sensor_names):
        logging.info(
            "Calibration file declares %d channels, %d of which were acquired.",
            channels_n, len(sensor_names))

    data_columns = resolve_data_columns(sensor_names, logical_channel_numbers)
    data = read_binary_data(data_file_path, max(data_columns) + 1)

    # Align data based on sensor distances
    data = align_sensor_data(
        data, sensor_names, sensor_distances, sample_step, data_columns)

    # Create dataframe from aligned data
    sensor_df = pd.DataFrame(data, columns=sensor_names)

    # Apply calibrations
    sensor_df = apply_calibrations(
        sensor_df,
        sensor_names,
        sensor_calibration_types,
        ad_factor,
        sensor_scales,
        sensor_offsets,
        asymptotic_values
    )

    return sensor_df, units, sample_step, info, pm_speed


def align_sensor_data(data, sensor_names, sensor_distances, sample_step,
                      data_columns=None):
    """Align sensor data based on sensor distances.

    :param data_columns: Column of the data file each sensor was read from.
        Defaults to the position in sensor_names.
    """
    if data_columns is None:
        data_columns = list(range(len(sensor_names)))

    align_data_slices = {}

    # Compensate for the case that minimum distance is smaller than zero (some calibrations might have this).
    distance_zero_offset = 0
    min_dist = min(sensor_distances.values())
    if min_dist < 0:
        distance_zero_offset = abs(min_dist)

    for i in sensor_distances:
        align_data_slices[i] = round(
            (distance_zero_offset + sensor_distances[i]) / sample_step)

    data_len = data.shape[0] - max(align_data_slices.values())
    trimmed_data = np.empty((data_len, len(sensor_names)))

    for index, sensor_name in enumerate(sensor_names):
        start_trim = align_data_slices[sensor_name]
        channel_data = data[start_trim:start_trim + data_len, data_columns[index]]
        trimmed_data[:, index] = channel_data

    return trimmed_data


def apply_calibrations(sensor_df, sensor_names, sensor_calibration_types, ad_factor, sensor_scales, sensor_offsets, asymptotic_values):
    """Apply calibrations to sensor data.

    The calibration functions are plain arithmetic, so they are applied to whole
    channel arrays at once. Series.apply() called them once per sample, which for
    a typical MD record meant millions of Python-level calls and dominated load
    time.
    """
    for sensor_name in sensor_df.columns:
        calibration_type = sensor_calibration_types[sensor_name]
        values = sensor_df[sensor_name].to_numpy(dtype=float)

        if calibration_type == 0:
            calibrated = linear_calibration(
                values, ad_factor, sensor_scales[sensor_name], sensor_offsets[sensor_name])
        elif calibration_type in [1, 2]:
            calibrated = logarithmic_calibration(
                values, ad_factor, sensor_scales[sensor_name],
                sensor_offsets[sensor_name], asymptotic_values[sensor_name])
            non_finite = int(np.count_nonzero(~np.isfinite(calibrated)))
            if non_finite:
                # log() of a non-positive argument: the raw reading sat at or
                # below the sensor's asymptote. Report it rather than letting a
                # silently NaN channel reach the analyses.
                logging.warning(
                    "Channel %s: %d of %d samples fall outside the logarithmic "
                    "calibration range and are not finite.",
                    sensor_name, non_finite, len(calibrated))
        else:
            continue

        sensor_df[sensor_name] = calibrated

    return sensor_df


def load_cd_samples_data(samples_file_path: str):
    """Load CD samples data from file and update measurement object."""
    with open(samples_file_path, 'r') as f:
        cd_data = json.load(f)
        peak_channel = cd_data['peak_channel']
        threshold = cd_data['threshold']
        peak_locations = cd_data['peak_locations']
        selected_samples = cd_data['selected_samples']
        tape_width_mm = cd_data.get('tape_width_mm', settings.TAPE_WIDTH_MM)

    return peak_channel, threshold, peak_locations, selected_samples, tape_width_mm


def linear_calibration(y, a, s, f):
    """
    Linear calibration function.

    Args:
        y: Raw value
        a: AD factor
        s: Scale
        f: Offset
    """
    return y * (s / a) + f


def logarithmic_calibration(y, a, s, f, c):
    """
    Logarithmic calibration function.

    Args:
        y: Raw value
        a: AD factor
        s: Scale
        f: Offset
        c: Asymptotic value
    """
    return s * np.log(y / a - c) + f
