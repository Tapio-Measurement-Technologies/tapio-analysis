import numpy as np
import pandas as pd

from utils.measurement import DataSegment, MeasurementChannel
from utils.filters import bandpass_filter
from utils.plot_formatting import wavelength_labels_cm_from_frequencies
from utils.signal_processing import get_n_peaks, safe_spectral_params


def test_measurement_channel_get_segment_accepts_indexes_and_segment():
    channel = MeasurementChannel(
        "Test",
        "unit",
        pd.DataFrame({"value": [10, 20, 30, 40]}),
    )

    by_indexes = channel.get_segment(1, 3)
    by_segment = channel.get_segment(DataSegment(1, 3, 1))

    assert by_indexes["value"].tolist() == [20, 30]
    assert by_segment["value"].tolist() == [20, 30]


def test_bandpass_filter_returns_short_data_unchanged():
    data = np.array([1.0, 2.0, 3.0])

    filtered = bandpass_filter(data, lowcut=0, highcut=10, fs=1000)

    assert np.allclose(filtered, data)
    assert filtered is not data


def test_wavelength_labels_do_not_divide_by_zero():
    labels = wavelength_labels_cm_from_frequencies([-1.0, 0.0, 2.0])

    assert labels == ["", "", "50.00"]


def test_safe_spectral_params_clamps_overlap_and_window_length():
    params = safe_spectral_params(
        requested_nperseg=10,
        overlap_fraction=1.0,
        data_length=4,
    )

    assert params == (4, 3)
    assert safe_spectral_params(10, 0.5, 1) is None


def test_get_n_peaks_applies_frequency_threshold_before_sorting():
    data = np.array([
        [0.5, 100.0],
        [2.0, 10.0],
        [3.0, 20.0],
    ])

    peaks = get_n_peaks(data, n=1, threshold=1.0)

    assert peaks.tolist() == [[3.0, 20.0]]
