"""Peak detection in the Spectrum window: the strongest peak that stands
clear of the spectrum's floor, never the low frequency hump."""

import numpy as np
import pytest

import settings
from analyses import spectrum
from test.test_spectrum_selection import (F1, F2, FS, NPERSEG, md_measurement,
                                          sine)
from utils.signal_processing import significant_peaks, spectral_floor


def drifting_measurement(seed=3):
    """A strong slow drift, a weak clean peak, and noise.

    The drift is the tallest thing in the spectrum by far, the way a basis
    weight record's own trend is; the peak is what a user wants selected.
    """
    length = 100000
    rng = np.random.default_rng(seed)
    distances = np.arange(length) * (1.0 / FS)
    drift = 20.0 * np.sin(2 * np.pi * distances / distances[-1] * 0.5)
    return md_measurement({"BW": 100.0 + drift + sine(length, F2, 0.5)
                           + rng.normal(0.0, 0.3, length)})


def plotted_controller(measurement, **attributes):
    controller = spectrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = NPERSEG
    controller.auto_detect_peaks = False
    controller.machine_speed = 0.0
    for key, value in attributes.items():
        setattr(controller, key, value)
    controller.plot()
    return controller


def test_spectral_floor_ignores_narrow_peaks():
    amplitude = np.full(500, 1.0)
    amplitude[250] = 50.0

    floor = spectral_floor(amplitude, 81)

    assert floor == pytest.approx(np.ones(500))


def test_significant_peaks_ranks_standing_peaks_by_amplitude():
    f = np.linspace(0.0, 10.0, 1001)
    amplitude = np.full_like(f, 0.1)
    amplitude[300] = 0.4  # 4x the floor
    amplitude[600] = 0.9  # 9x the floor
    amplitude[800] = 0.15  # 1.5x: noise

    peaks = significant_peaks(f, amplitude, threshold=2.0)

    assert [frequency for frequency, _ in peaks] == pytest.approx([6.0, 3.0])
    assert significant_peaks(f, amplitude, count=1)[0][0] == pytest.approx(6.0)


def test_significant_peaks_skips_the_low_frequency_hump():
    """Local maxima on the slope of a hump do not stand clear of the slope."""
    f = np.linspace(0.0, 10.0, 1001)
    hump = 5.0 * np.exp(-f / 0.3)
    ripple = 0.05 * np.sin(2 * np.pi * f / 0.1)
    amplitude = hump + ripple + 0.1
    amplitude[700] = 0.6

    peaks = significant_peaks(f, amplitude, threshold=2.0)

    assert [frequency for frequency, _ in peaks] == pytest.approx([7.0])


def test_significant_peaks_returns_nothing_for_a_flat_spectrum():
    f = np.linspace(0.0, 10.0, 101)

    assert significant_peaks(f, np.ones_like(f)) == []
    assert significant_peaks(f, np.zeros_like(f)) == []
    assert significant_peaks(f[:2], np.ones(2)) == []


def test_detection_picks_the_peak_and_not_the_drift(qt_app):
    controller = plotted_controller(drifting_measurement())

    # The drift really is the tallest thing in the spectrum.
    tallest = controller.frequencies[np.argmax(controller.amplitudes)]
    assert tallest < 0.05

    detected = controller.detectPeaks()

    assert len(detected) == 1
    assert detected[0] == pytest.approx(F2, abs=FS / NPERSEG)


def test_detection_selects_several_in_multiple_selection_mode(qt_app):
    measurement = md_measurement(
        {"BW": sine(100000, F1, 3.0, 100.0) + sine(100000, F2, 1.0)})
    controller = plotted_controller(measurement, multiple_select=True)

    detected = controller.detectPeaks()

    assert detected[:2] == pytest.approx([F1, F2], abs=FS / NPERSEG)
    assert len(detected) <= settings.SPECTRUM_AUTO_DETECT_PEAKS


def test_detect_peaks_checkbox_uses_the_same_logic(qt_app):
    controller = plotted_controller(drifting_measurement(), auto_detect_peaks=True)

    assert controller.selected_freqs == pytest.approx([F2], abs=FS / NPERSEG)


def test_auto_detect_button_searches_the_visible_range(qt_app):
    measurement = md_measurement(
        {"BW": sine(100000, F1, 3.0, 100.0) + sine(100000, F2, 1.0)})
    controller = plotted_controller(measurement, multiple_select=False,
                                    auto_detect_peaks=True)
    window = spectrum.AnalysisWindow(controller, "MD")

    window.autoDetectPeaks()
    assert not controller.auto_detect_peaks  # a one-off, not a mode
    assert controller.selected_freqs == pytest.approx([F1], abs=FS / NPERSEG)

    # Zoomed in past the strongest peak, the button finds the next one.
    controller.ax.set_xlim(F2 - 0.5, F2 + 0.5)
    window.autoDetectPeaks()
    assert controller.selected_freqs == pytest.approx([F2], abs=FS / NPERSEG)
    assert controller.ax.get_xlim() == pytest.approx((F2 - 0.5, F2 + 0.5))


def test_auto_detect_button_leaves_the_selection_empty_when_nothing_stands(qt_app):
    measurement = md_measurement({"BW": np.full(100000, 100.0)})
    controller = plotted_controller(measurement, selected_freqs=[F1])
    window = spectrum.AnalysisWindow(controller, "MD")

    window.autoDetectPeaks()

    assert controller.selected_freqs == []
