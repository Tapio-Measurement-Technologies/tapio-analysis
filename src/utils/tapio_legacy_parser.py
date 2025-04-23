import struct

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def linear_calibration(y, a, s, f):
    # a - ad factor
    # s - scale
    # f - offset

    return y * (s / a) + f


def logarithmic_calibration(y, a, s, f, c):
    # a - ad factor
    # s - scale
    # f - offset
    # c - asymptotic value
    return s * np.log(y / a - c) + f


def read_common_from_ca(cal_file):

    cal_file.seek(0)
    reading_sensor_names = False
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
    return channels_n, ad_factor, formation


def read_channel_names_units_from_ca(cal_file):
    sensor_names = []
    units = {}
    logical_channel_numbers = {}
    # Use running number for unnamed channels in case there are multiple
    n_unnamed_channels = 0

    cal_file.seek(0)
    reading_sensor_names = False
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
                        sensor_names.append(sensor_name)

    return sensor_names, units


def read_info_from_header(header_file):

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


def read_calibration_data_from_ca(cal_file, sensor_names):
    calibrated = {}
    sensor_distances = {}
    sensor_scales = {}
    sensor_offsets = {}
    sensor_calibration_types = {}
    asymptotic_values = {}

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
                filtered_parts = [parts[i] for i, n in enumerate(sensor_names)]
                if len(filtered_parts) != len(sensor_names):
                    raise ValueError(
                        "Mismatch between channel and sensor data")
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
                if len(parts) >= 3:
                    pm_speed = float(parts[0])  # In m/s
                    length = float(parts[3])  # m
                    sample_step = float(parts[4])  # m

    return pm_speed, length, sample_step


def read_binary_data(file_path, num_channels):
    with open(file_path, 'rb') as file:
        file_content = file.read()
    num_data_points = len(file_content) // (2 * num_channels)
    format_str = '>' + 'h' * num_channels * num_data_points
    data_points = struct.unpack(format_str, file_content)

    reshaped_data = np.reshape(data_points, (num_data_points, num_channels))
    return reshaped_data


def plot_vals(df):
    plt.figure(figsize=(10, 6))

    for column in df.columns:
        val_array = np.array(df[column])
        plt.plot(val_array, label=column)

    plt.title('Plot of Sensor Data')
    plt.xlabel('Index')
    plt.ylabel('Value')
    plt.legend()
    plt.show()


def load_legacy_data(header_file_path, cal_file_path, data_file_path):

    with open(cal_file_path, 'r', encoding='iso-8859-1') as cal_file:
        sensor_names, units = read_channel_names_units_from_ca(cal_file)
        channels_n, ad_factor, formation = read_common_from_ca(cal_file)
        calibrated, sensor_distances, sensor_scales, sensor_offsets, sensor_calibration_types, asymptotic_values = read_calibration_data_from_ca(
            cal_file, sensor_names)

    with open(header_file_path, 'r', encoding='iso-8859-1') as header_file:
        pm_speed, length, sample_step = read_meas_param(header_file)
        info = read_info_from_header(header_file)

    sensor_names_df = pd.DataFrame(columns=sensor_names)
    data = read_binary_data(data_file_path, len(sensor_names))
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

    trimmed_data = np.empty((data_len, data.shape[1]))

    for index, sensor_name in enumerate(sensor_names):
        start_trim = align_data_slices[sensor_name]
        channel_data = data[start_trim:start_trim + data_len, index]
        trimmed_data[:, index] = channel_data

    data = trimmed_data

    sensor_df = pd.DataFrame(data, columns=sensor_names)

    for sensor_name in sensor_df.columns:
        calibration_type = sensor_calibration_types[sensor_name]
        if calibration_type == 0:
            sensor_df[sensor_name] = sensor_df[sensor_name].apply(
                linear_calibration, args=(ad_factor, sensor_scales[sensor_name], sensor_offsets[sensor_name]))
        elif calibration_type in [1, 2]:
            sensor_df[sensor_name] = sensor_df[sensor_name].apply(
                logarithmic_calibration, args=(ad_factor, sensor_scales[sensor_name], sensor_offsets[sensor_name], asymptotic_values[sensor_name]))

    return sensor_df, units, sample_step, info, pm_speed


if __name__ == "__main__":

    header_file_path = '../test-data/test_CD_20211111.pk2'
    cal_file_path = '../test-data/test_CD_20211111.ca2'
    data_file_path = '../test-data/test_CD_20211111.da2'
    channel_data, units, sample_step, info = load_legacy_data(
        header_file_path, cal_file_path, data_file_path)
    print(channel_data)
    print(units)
    print(sample_step)
    print(info)
