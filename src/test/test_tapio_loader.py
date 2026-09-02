"""Legacy Tapio (.pk2/.ca2/.da2) loader parsing."""

import os

import numpy as np
import pytest

from loaders import tapio

AD_FACTOR = 6553.6
SAMPLE_STEP = 1e-3
SAMPLE_COUNT = 64

# Column three is a sensor the calibration file declares but the measurement did
# not acquire, marked by a logical channel number of -1. Every channel after it
# is one column further right than its place in the list of acquired channels.
SENSOR_ROWS = [
    ("Alpha", "u1", "0"),
    ("Beta", "u2", "1"),
    ("Spare", "u3", "-1"),
    # Logical numbers can retain a gap even though the compact data stream has
    # no column for the disabled sensor.
    ("Gamma", "u4", "3"),
]
DISTANCES = [0.0, 0.002, 0.003, 0.004]
SCALES = [10.0, 20.0, 30.0, 40.0]
OFFSETS = [1.0, 2.0, 3.0, 4.0]

ACQUIRED = ["Alpha", "Beta", "Gamma"]
ACQUIRED_COLUMNS = {"Alpha": 0, "Beta": 1, "Gamma": 3}


def row(values):
    return "\t".join(str(value) for value in values)


def write_calibration_file(path):
    lines = [
        "[PMA Header]",
        "[Common]",
        row([1, 6]),
        row([4, AD_FACTOR, 1, 3, 3, 0]),
        "[Sensor Names]",
        row([len(SENSOR_ROWS), 3]),
        *[row(sensor) for sensor in SENSOR_ROWS],
        "[Sensor Param.]",
        row([32, len(SENSOR_ROWS)]),
        row([1] * len(SENSOR_ROWS)),          # Calibrated
        row(DISTANCES),                       # Sensor distances
        row(SCALES),
        row(OFFSETS),
        row([0] * len(SENSOR_ROWS)),          # Calibration types: all linear
        row([0] * len(SENSOR_ROWS)),          # Asymptotic values
        "[End]",
    ]
    with open(path, "w", encoding="iso-8859-1") as cal_file:
        cal_file.write("\n".join(lines))


def write_header_file(path):
    lines = [
        "[PMA Header]",
        "[Files]",
        row([6, 1]),
        "x.pk2", "x.da2", "x.ca2", "x.pm2",
        "Disabled channel test",
        "[Meas. Param.]",
        row([1, 7]),
        row([16.0, 0.1, 5000.0, 1.0, SAMPLE_STEP, 0.0, 0.0]),
        "[End]",
    ]
    with open(path, "w", encoding="iso-8859-1") as header_file:
        header_file.write("\n".join(lines))


def raw_counts():
    """One distinct ramp per acquired channel, as the data file interleaves them."""
    samples = np.arange(SAMPLE_COUNT, dtype=np.int16)
    return np.column_stack([samples + 1000 * index for index in range(len(ACQUIRED))])


def write_data_file(path):
    with open(path, "wb") as data_file:
        data_file.write(raw_counts().astype(">i2").tobytes())


@pytest.fixture
def measurement_files(tmp_path):
    paths = {extension: str(tmp_path / f"synthetic{extension}")
             for extension in (".pk2", ".ca2", ".da2")}
    write_calibration_file(paths[".ca2"])
    write_header_file(paths[".pk2"])
    write_data_file(paths[".da2"])
    return paths


def test_disabled_channel_is_left_out_but_keeps_its_column(measurement_files):
    with open(measurement_files[".ca2"], encoding="iso-8859-1") as cal_file:
        sensor_names, units, logical, sensor_columns = \
            tapio.read_channel_names_units_from_ca(cal_file)

    assert sensor_names == ACQUIRED
    assert "Spare" not in units
    assert sensor_columns == ACQUIRED_COLUMNS
    assert logical == {"Alpha": "0", "Beta": "1", "Gamma": "3"}


def test_calibration_is_read_from_the_channel_s_own_column(measurement_files):
    """Gamma must get its own scale and offset, not the disabled channel's."""
    with open(measurement_files[".ca2"], encoding="iso-8859-1") as cal_file:
        sensor_names, _, _, sensor_columns = \
            tapio.read_channel_names_units_from_ca(cal_file)
        _, distances, scales, offsets, types, asymptotes = \
            tapio.read_calibration_data_from_ca(cal_file, sensor_names, sensor_columns)

    assert scales == {"Alpha": 10.0, "Beta": 20.0, "Gamma": 40.0}
    assert offsets == {"Alpha": 1.0, "Beta": 2.0, "Gamma": 4.0}
    assert types == {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0}
    assert distances == {"Alpha": 0.0, "Beta": 0.002, "Gamma": 0.004}
    assert asymptotes == {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0}


def test_channels_are_calibrated_with_their_own_parameters(measurement_files):
    sensor_df, units, sample_step, info, pm_speed = tapio.parse_legacy_data(
        measurement_files[".pk2"], measurement_files[".ca2"], measurement_files[".da2"])

    assert list(sensor_df.columns) == ACQUIRED
    assert sample_step == SAMPLE_STEP
    assert info == "Disabled channel test"
    assert pm_speed == 16.0

    counts = raw_counts()
    aligned_length = SAMPLE_COUNT - round(max(DISTANCES) / SAMPLE_STEP)
    for index, channel in enumerate(ACQUIRED):
        column = ACQUIRED_COLUMNS[channel]
        start = round(DISTANCES[column] / SAMPLE_STEP)
        raw_values = counts[start:start + aligned_length, index]
        expected = raw_values * (SCALES[column] / AD_FACTOR) + OFFSETS[column]
        np.testing.assert_allclose(sensor_df[channel].to_numpy(), expected)


def test_a_short_parameter_row_is_reported(measurement_files):
    """A row that stops before a channel's column must not read a neighbour's."""
    with open(measurement_files[".ca2"], encoding="iso-8859-1") as cal_file:
        text = cal_file.read()
    text = text.replace(row(SCALES), row(SCALES[:3]))
    with open(measurement_files[".ca2"], "w", encoding="iso-8859-1") as cal_file:
        cal_file.write(text)

    with open(measurement_files[".ca2"], encoding="iso-8859-1") as cal_file:
        sensor_names, _, _, sensor_columns = \
            tapio.read_channel_names_units_from_ca(cal_file)
        with pytest.raises(ValueError, match="Sensor Param"):
            tapio.read_calibration_data_from_ca(
                cal_file, sensor_names, sensor_columns)


def test_a_file_without_disabled_channels_has_matching_parameter_columns():
    """The bundled measurement acquires every declared channel."""
    calibration_file = os.path.join(
        os.path.dirname(__file__), "../../test-data/test_MD_L_1.ca2")

    with open(calibration_file, encoding="iso-8859-1") as cal_file:
        sensor_names, _, _, sensor_columns = \
            tapio.read_channel_names_units_from_ca(cal_file)

    assert [sensor_columns[name] for name in sensor_names] == list(range(len(sensor_names)))


def test_sensor_distance_trimming_aligns_the_same_location_across_channels():
    sensor_distances = {"Alpha": 0.0, "Beta": 0.002, "Gamma": 0.004}
    data = np.zeros((20, len(ACQUIRED)))
    expected_location = 8
    for column, sensor_name in enumerate(ACQUIRED):
        distance_samples = round(sensor_distances[sensor_name] / SAMPLE_STEP)
        data[expected_location + distance_samples, column] = 1.0

    aligned = tapio.align_sensor_data(
        data, ACQUIRED, sensor_distances, SAMPLE_STEP)

    np.testing.assert_array_equal(
        np.argmax(aligned, axis=0),
        [expected_location] * len(ACQUIRED),
    )
