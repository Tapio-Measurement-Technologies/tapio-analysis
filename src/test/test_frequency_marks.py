"""The selection, harmonics, peak detection and element controls shared by the
Cepstrum, Coherence and Spectrogram windows, and the keys that step a
selection."""

from types import SimpleNamespace

import matplotlib.colors
import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

import settings
from analyses import cepstrum, coherence, spectrogram, spectrum
from test.test_calculations import cepstrum_controller, harmonic_series_measurement
from test.test_spectrum_selection import (F1, F2, FS, NPERSEG, md_measurement,
                                          sine, spectrum_controller)


def two_peak_measurement(seed=5):
    rng = np.random.default_rng(seed)
    clean = sine(100000, F1, 3.0, 100.0) + sine(100000, F2, 1.0)
    return md_measurement({
        "BW": clean + rng.normal(0.0, 0.3, 100000),
        "Ash": 0.5 * clean + rng.normal(0.0, 0.3, 100000),
    })


def plotted(module, measurement, window_type="MD", nperseg=NPERSEG, **attributes):
    controller = module.AnalysisController(measurement, window_type)
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = nperseg
    controller.auto_detect_peaks = False
    controller.machine_speed = 0.0
    for key, value in attributes.items():
        setattr(controller, key, value)
    controller.plot()
    return controller


def line_positions(controller):
    axis = 1 if controller.marks_axis == "y" else 0
    return sorted(float(line.get_data()[axis][0]) for line in controller.current_vlines)


def text_labels(controller, rotation):
    return [text.get_text().strip() for text in controller.ax.texts
            if text.get_rotation() == rotation]


# --------------------------------------------------------------------------
# Every window offers the same controls
# --------------------------------------------------------------------------

@pytest.mark.parametrize("module, build", [
    (cepstrum, lambda: cepstrum_controller(harmonic_series_measurement())),
    (coherence, lambda: plotted(coherence, two_peak_measurement(), nperseg=2000,
                                channel="BW", channel2="Ash")),
    (spectrogram, lambda: plotted(spectrogram, two_peak_measurement(), nperseg=2000)),
])
def test_windows_offer_the_selection_controls(qt_app, module, build):
    controller = build()
    window = module.AnalysisWindow(controller, "MD")

    for name in ("multipleSelectCheckbox", "harmonicsCheckbox",
                 "harmonicsCountSpinner", "autodetectCheckbox", "detectPeaksButton"):
        assert hasattr(window, name), name
    assert controller.multiple_select == settings.MULTIPLE_SELECT_MODE
    assert controller.harmonics_count == settings.MAX_HARMONICS_DISPLAY

    window.harmonicsCountSpinner.setValue(2)
    assert controller.harmonics_count == 2
    window.multipleSelectCheckbox.setChecked(True)
    assert controller.multiple_select


# --------------------------------------------------------------------------
# Cepstrum
# --------------------------------------------------------------------------

def test_cepstrum_draws_every_selection_and_the_rahmonics_of_each(qt_app):
    measurement = harmonic_series_measurement(period=2.0)
    f0 = 0.5
    controller = cepstrum_controller(measurement, multiple_select=True,
                                     show_harmonics=True, harmonics_count=2,
                                     selected_freqs=[f0, 2 * f0])
    controller.plot()

    # Rahmonics run to the left: f0, f0/2 for each selection.
    assert line_positions(controller) == pytest.approx([f0 / 2, f0, f0, 2 * f0])

    controller.show_harmonics = False
    controller.plot()
    assert line_positions(controller) == pytest.approx([f0, 2 * f0])


def test_cepstrum_elements_are_single_named_lines(qt_app):
    controller = cepstrum_controller(
        harmonic_series_measurement(), show_harmonics=True, harmonics_count=5,
        machine_speed=0.0,
        selected_elements=[{"name": "Dryer", "spatial_frequency": 0.5}])
    controller.plot()

    assert line_positions(controller) == pytest.approx([0.5])
    assert text_labels(controller, 90) == ["Dryer, λ = 200.0 cm"]
    assert controller.current_vlines[0].get_color() == settings.SPECTRUM_ELEMENT_COLOR


def test_cepstrum_auto_detect_button_searches_the_visible_range(qt_app):
    controller = cepstrum_controller(harmonic_series_measurement(period=2.0))
    window = cepstrum.AnalysisWindow(controller, "MD")

    window.autoDetectPeaks()
    assert controller.selected_freqs[-1] == pytest.approx(0.5, rel=0.05)

    controller.ax.set_xlim(0.7, 1.3)
    window.autoDetectPeaks()
    assert 0.7 <= controller.selected_freqs[-1] <= 1.3


# --------------------------------------------------------------------------
# Coherence
# --------------------------------------------------------------------------

def test_coherence_selection_modes_and_harmonics(qt_app):
    controller = plotted(coherence, two_peak_measurement(), nperseg=2000,
                         channel="BW", channel2="Ash", multiple_select=False,
                         show_harmonics=True, harmonics_count=2,
                         selected_freqs=[F1, F2])

    assert line_positions(controller) == pytest.approx([F2, 2 * F2])
    label = controller.current_vlines[0].get_label()
    assert "C = " in label and "g/m2" not in label

    controller.multiple_select = True
    controller.show_harmonics = False
    controller.plot()
    assert line_positions(controller) == pytest.approx([F1, F2])


def test_coherence_detects_the_shared_frequencies(qt_app):
    controller = plotted(coherence, two_peak_measurement(), nperseg=2000,
                         channel="BW", channel2="Ash", multiple_select=True)

    detected = sorted(controller.detectPeaks())

    assert detected[:2] == pytest.approx([F1, F2], abs=FS / 2000)
    assert all(controller.mark_amplitude_at(freq) >= controller.significance_level
               for freq in detected)


def test_coherence_click_replaces_or_adds_and_stops_detection(qt_app):
    controller = plotted(coherence, two_peak_measurement(), nperseg=2000,
                         channel="BW", channel2="Ash", auto_detect_peaks=True)
    window = coherence.AnalysisWindow(controller, "MD")

    assert window.select_frequency_at(controller.ax, F1)
    assert not controller.auto_detect_peaks
    assert window.select_frequency_at(controller.ax, F2)
    assert controller.selected_freqs == pytest.approx([F2])

    window.multipleSelectCheckbox.setChecked(True)
    assert window.select_frequency_at(controller.ax, F1)
    assert controller.selected_freqs == pytest.approx([F2, F1])


# --------------------------------------------------------------------------
# Spectrogram
# --------------------------------------------------------------------------

def test_spectrogram_marks_run_across_the_image(qt_app):
    elements = [{"name": "Reel", "spatial_frequency": 3.0}]
    controller = plotted(spectrogram, two_peak_measurement(), nperseg=2000,
                         multiple_select=True, show_harmonics=True,
                         harmonics_count=2, selected_freqs=[F1, F2],
                         selected_elements=elements)

    assert controller.marks_axis == "y"
    assert line_positions(controller) == pytest.approx(
        sorted([F1, 2 * F1, F2, 2 * F2, 3.0, 6.0]))
    assert "Reel, λ = 33.3 cm" in text_labels(controller, 0)


def test_spectrogram_detects_peaks_on_the_mean_spectrum(qt_app):
    controller = plotted(spectrogram, two_peak_measurement(), nperseg=2000,
                         multiple_select=True)

    detected = sorted(controller.detectPeaks())

    assert detected[:2] == pytest.approx([F1, F2], abs=FS / 2000)


def test_spectrogram_log_scale_switches_the_colour_norm(qt_app):
    controller = plotted(spectrogram, two_peak_measurement(), nperseg=2000)
    window = spectrogram.AnalysisWindow(controller, "MD")
    # specgram draws an image of its own first; the amplitude image is last.
    assert not isinstance(controller.ax.images[-1].norm, matplotlib.colors.LogNorm)

    window.logScaleCheckbox.setChecked(True)

    norm = controller.ax.images[-1].norm
    assert isinstance(norm, matplotlib.colors.LogNorm)
    assert 0 < norm.vmin < norm.vmax
    assert controller.export_attributes()["log_scale"] is True


# --------------------------------------------------------------------------
# Stepping the selection with the wheel and the arrow keys
# --------------------------------------------------------------------------

def test_arrow_keys_step_the_selection_one_bin(qt_app):
    controller = spectrum_controller(selected_freqs=[F1], auto_detect_peaks=True)
    window = spectrum.AnalysisWindow(controller, "MD")
    bin_width = FS / NPERSEG

    QTest.keyClick(window, Qt.Key.Key_Right)
    assert not controller.auto_detect_peaks  # a step is a manual choice
    assert controller.selected_freqs[-1] == pytest.approx(F1 + bin_width)

    QTest.keyClick(window, Qt.Key.Key_Left)
    QTest.keyClick(window, Qt.Key.Key_Left)
    assert controller.selected_freqs[-1] == pytest.approx(F1 - bin_width)

    # The same keys reach the window through the canvas once it has the focus.
    window.on_canvas_key(SimpleNamespace(key="right"))
    assert controller.selected_freqs[-1] == pytest.approx(F1)

    # The wheel steps the same way.
    window.on_scroll(SimpleNamespace(inaxes=controller.ax, button="up", step=1))
    assert controller.selected_freqs[-1] == pytest.approx(F1 + bin_width)


@pytest.mark.parametrize("module, build, axis_limits", [
    (cepstrum, lambda: cepstrum_controller(harmonic_series_measurement(period=2.0),
                                           selected_freqs=[0.5]), None),
    (coherence, lambda: plotted(coherence, two_peak_measurement(), nperseg=2000,
                                channel="BW", channel2="Ash", selected_freqs=[F1]), None),
    (spectrogram, lambda: plotted(spectrogram, two_peak_measurement(), nperseg=2000,
                                  selected_freqs=[F1]), None),
])
def test_arrow_keys_work_in_every_window(qt_app, module, build, axis_limits):
    controller = build()
    window = module.AnalysisWindow(controller, "MD")
    before = controller.selected_freqs[-1]
    index = controller.get_nearest_frequency_bin_index(before)

    QTest.keyClick(window, Qt.Key.Key_Right)

    assert controller.selected_freqs[-1] == pytest.approx(controller.frequencies[index + 1])
    QTest.keyClick(window, Qt.Key.Key_Left)
    assert controller.selected_freqs[-1] == pytest.approx(controller.frequencies[index])
