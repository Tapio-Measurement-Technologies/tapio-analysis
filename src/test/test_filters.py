"""The band pass filter at long wavelengths.

A FIR filter tells frequencies apart about as finely as it holds periods of
them, so its length follows the lowest cutoff: a fixed 2500 tap filter at a
1 cm sample step is 25 m long and cannot tell a 20 m wave from a 5 m one.
"""

import numpy as np
import pytest

import settings
from utils.filters import bandpass_filter, filter_numtaps

FS = 100.0  # a 1 cm sample step


def sine(frequency_1m, length_m=400.0):
    distances = np.arange(int(round(length_m * FS))) / FS
    return np.sin(2 * np.pi * frequency_1m * distances)


def amplitude_away_from_the_ends(values, edge):
    """The amplitude of a sine, leaving out the ends the mirror padding reaches."""
    return float(np.sqrt(2.0) * np.std(values[edge:-edge]))


def test_the_filter_length_is_odd_and_follows_the_lowest_cutoff():
    assert filter_numtaps(0.0, 40.0, FS, 10**6) == settings.FILTER_NUMTAPS + 1
    assert filter_numtaps(0.1, 10.0, FS, 10**6) == 10001


def test_a_filter_longer_than_the_data_is_shortened_to_fit():
    signal = sine(0.5, length_m=20.0)

    assert filter_numtaps(0.0, 0.01, FS, len(signal)) == 1999
    filtered = bandpass_filter(signal, 0.0, 0.01, FS)
    assert filtered.shape == signal.shape
    assert np.all(np.isfinite(filtered))


@pytest.mark.parametrize("frequency, kept", [(0.05, True), (0.2, False)])
def test_a_low_pass_at_a_long_wavelength_separates_the_waves_either_side(frequency, kept):
    signal = sine(frequency)

    filtered = bandpass_filter(signal, 0.0, 0.1, FS)

    amplitude = amplitude_away_from_the_ends(
        filtered, filter_numtaps(0.0, 0.1, FS, len(signal)))
    if kept:
        assert amplitude > 0.98
    else:
        assert amplitude < 0.02


def test_a_low_pass_keeps_the_level_and_the_longest_waves_whole():
    signal = 5.0 + sine(0.005)

    filtered = bandpass_filter(signal, 0.0, 1.0, FS)

    edge = filter_numtaps(0.0, 1.0, FS, len(signal))
    np.testing.assert_allclose(filtered[edge:-edge], signal[edge:-edge], atol=0.01)


def test_a_long_wavelength_low_cut_removes_the_drift_and_keeps_the_band():
    wave = sine(1.0)

    filtered = bandpass_filter(sine(0.02) + wave, 0.1, 10.0, FS)

    edge = filter_numtaps(0.1, 10.0, FS, len(wave))
    assert amplitude_away_from_the_ends(filtered - wave, edge) < 0.03
