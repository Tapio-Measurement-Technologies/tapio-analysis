"""The selection, harmonics, peak detection and element controls shared by the
Cepstrum, Coherence and Spectrogram windows, and the keys that step a
selection."""

from types import SimpleNamespace

import matplotlib.colors
import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGroupBox

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

#: Every spectral window, with a controller ready to open one on.
SPECTRAL_WINDOWS = [
    (spectrum, lambda: plotted(spectrum, two_peak_measurement(), nperseg=2000)),
    (cepstrum, lambda: cepstrum_controller(harmonic_series_measurement())),
    (coherence, lambda: plotted(coherence, two_peak_measurement(), nperseg=2000,
                                channel="BW", channel2="Ash")),
    (spectrogram, lambda: plotted(spectrogram, two_peak_measurement(), nperseg=2000)),
]


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
# --------------------------------------------------------------------------
# Frequencies in Hz
# --------------------------------------------------------------------------

#: 600 m/min is 10 m/s, so F1 = 0.625 1/m runs past the reel at 6.25 Hz.
MACHINE_SPEED = 600.0


def twin_axis_labels(controller):
    """The labels of every axis but the main one: where a second unit goes."""
    labels = []
    for ax in controller.figure.axes:
        if ax is controller.ax:
            continue
        labels.extend([ax.get_xlabel(), ax.get_ylabel()])
    return [label for label in labels if label]


def hz_spectrum(machine_speed=MACHINE_SPEED, **attributes):
    """An MD spectrum carrying a selection and an element, both at F1."""
    return spectrum_controller(
        machine_speed=machine_speed, show_harmonics=False, selected_freqs=[F1],
        selected_elements=[{"name": "Wire", "spatial_frequency": F1}],
        **attributes)


def test_hz_readings_wait_to_be_asked_for(qt_app):
    """A machine speed is not consent: the spinner starts from a setting, so a
    sample measured off the machine would otherwise carry a Hz reading it never
    had. The wavelength takes the top axis instead."""
    controller = hz_spectrum(show_frequency_in_hz=False)

    assert not controller.hz_readings_shown()
    assert "Hz" not in controller.describe_frequency(F1, 1.0)
    assert "F [Hz]" not in controller.legend_columns()
    assert len(controller.legend_data[0]) == len(controller.legend_columns())
    assert text_labels(controller, 90) == ["Wire, λ = 160.0 cm"]
    assert "Wavelength [cm]" in twin_axis_labels(controller)


def test_hz_readings_follow_the_option(qt_app):
    controller = hz_spectrum(show_frequency_in_hz=True)

    assert controller.hz_readings_shown()
    assert "(6.25 Hz)" in controller.describe_frequency(F1, 1.0)
    assert controller.legend_columns()[-1] == "F [Hz]"
    assert controller.legend_data[0][-1] == "6.25"
    assert text_labels(controller, 90) == ["Wire, λ = 160.0 cm, 6.25 Hz"]
    assert any(label.startswith("Frequency [Hz]")
               for label in twin_axis_labels(controller))


def test_hz_readings_still_need_a_machine_speed(qt_app):
    """The option asks for the reading; the speed is what makes it possible."""
    controller = hz_spectrum(machine_speed=0.0, show_frequency_in_hz=True)

    assert not controller.hz_readings_shown()
    assert "Hz" not in controller.describe_frequency(F1, 1.0)
    assert "Wavelength [cm]" in twin_axis_labels(controller)


def test_cd_windows_have_no_machine_frequency(qt_app):
    """A CD strip is measured across the web, so nothing on it runs past the
    reel at the machine speed, whatever the option says."""
    controller = spectrum.AnalysisController(two_peak_measurement(), "CD")
    controller.machine_speed = MACHINE_SPEED
    controller.show_frequency_in_hz = True

    assert not controller.hz_readings_shown()
    assert "Hz" not in controller.describe_frequency(F1, 1.0)


@pytest.mark.parametrize("module, build", [
    (spectrum, lambda: plotted(spectrum, two_peak_measurement(), nperseg=2000)),
    (cepstrum, lambda: cepstrum_controller(harmonic_series_measurement())),
    (coherence, lambda: plotted(coherence, two_peak_measurement(), nperseg=2000,
                                channel="BW", channel2="Ash")),
    (spectrogram, lambda: plotted(spectrogram, two_peak_measurement(), nperseg=2000)),
])
def test_every_spectral_window_offers_the_hz_checkbox(qt_app, module, build):
    controller = build()
    assert controller.show_frequency_in_hz == settings.SHOW_FREQUENCY_IN_HZ_DEFAULT

    window = module.AnalysisWindow(controller, "MD")

    assert window.frequencyInHzCheckbox.text() == "Show frequencies in Hz"
    window.frequencyInHzCheckbox.setChecked(True)
    assert controller.show_frequency_in_hz
    window.frequencyInHzCheckbox.setChecked(False)
    assert not controller.show_frequency_in_hz
@pytest.mark.parametrize("module, build", SPECTRAL_WINDOWS)
def test_the_selection_buttons_lead_the_display_options(qt_app, module, build):
    """The buttons come before the checkboxes, Refine first: the panel scrolls,
    and a button at the bottom of a long group can be off screen."""
    window = module.AnalysisWindow(build(), "MD")

    group = next(box for box in window.findChildren(QGroupBox)
                 if "Display" in box.title())
    layout = group.layout()
    leading = [layout.itemAt(index).widget() for index in range(3)]

    assert leading == [window.refineButton, window.clearButton,
                       window.detectPeaksButton]
    assert [button.text() for button in leading] == [
        "Refine Frequency Selection", "Clear Frequency Selection",
        "Auto detect peaks"]


# --------------------------------------------------------------------------
# Subharmonic search: is the peak I picked a multiple of something lower?
# --------------------------------------------------------------------------

def test_subharmonic_search_moves_the_selection_to_the_fundamental(qt_app):
    """Setting 2 reads the picked peak as the second harmonic.

    The selection drops to half of it, so the ordinary harmonic ladder is
    drawn from that fundamental and the picked peak is its second rung.
    """
    controller = plotted(spectrum, two_peak_measurement(), nperseg=2000,
                         selected_freqs=[F2], show_harmonics=True,
                         harmonics_count=3)
    window = spectrum.AnalysisWindow(controller, "MD")

    assert controller.subharmonic_divisor == settings.SUBHARMONIC_SEARCH_DEFAULT

    window.subharmonicSpinner.setValue(2)
    assert controller.selected_freqs == pytest.approx([F2 / 2])
    assert line_positions(controller) == pytest.approx(
        [F2 / 2, F2, 1.5 * F2])


def test_subharmonic_search_divides_the_picked_value_not_the_last_one(qt_app):
    """Stepping 2, 3, 4 keeps dividing the frequency that was picked."""
    controller = plotted(spectrum, two_peak_measurement(), nperseg=2000,
                         selected_freqs=[F2])
    window = spectrum.AnalysisWindow(controller, "MD")

    window.subharmonicSpinner.setValue(2)
    assert controller.selected_freqs == pytest.approx([F2 / 2])
    window.subharmonicSpinner.setValue(3)
    assert controller.selected_freqs == pytest.approx([F2 / 3])
    window.subharmonicSpinner.setValue(4)
    assert controller.selected_freqs == pytest.approx([F2 / 4])

    # Back to 1 and the picked frequency is restored exactly.
    window.subharmonicSpinner.setValue(1)
    assert controller.selected_freqs == pytest.approx([F2])


def test_subharmonic_search_applies_to_the_next_pick_too(qt_app):
    controller = plotted(spectrum, two_peak_measurement(), nperseg=2000)
    window = spectrum.AnalysisWindow(controller, "MD")

    window.subharmonicSpinner.setValue(3)
    window.select_frequency_at(controller.ax, F2)
    assert controller.selected_freqs[-1] == pytest.approx(F2 / 3)

    window.subharmonicSpinner.setValue(1)
    assert controller.selected_freqs[-1] == pytest.approx(F2)


@pytest.mark.parametrize("module, build", SPECTRAL_WINDOWS)
def test_every_spectral_window_offers_the_subharmonic_box(qt_app, module, build):
    controller = build()
    window = module.AnalysisWindow(controller, "MD")
    assert hasattr(window, "subharmonicSpinner")
    assert window.subharmonicSpinner.minimum() == 1
    assert window.subharmonicSpinner.maximum() == settings.MAX_SUBHARMONIC_SEARCH
