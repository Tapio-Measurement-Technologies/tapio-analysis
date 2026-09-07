"""The Spectrum window's frequency selection: single or multiple, with or
without harmonics, and the controls that switch between them."""

import numpy as np
import pandas as pd
import pytest

import settings
from analyses import spectrum
from utils.measurement import Measurement

SAMPLE_STEP = 0.0128
FS = 1.0 / SAMPLE_STEP
NPERSEG = 5000


def md_measurement(channels, sample_step=SAMPLE_STEP):
    length = len(next(iter(channels.values())))
    distances = np.arange(length) * sample_step
    return Measurement(
        channel_df=pd.DataFrame(channels),
        channels=list(channels),
        units={name: "g/m2" for name in channels},
        distances=distances,
        cd_distances=distances,
        sample_step=sample_step,
        measurement_label="synthetic",
    )


def sine(length, frequency, amplitude=1.0, offset=0.0, sample_step=SAMPLE_STEP):
    distances = np.arange(length) * sample_step
    return offset + amplitude * np.sin(2 * np.pi * frequency * distances)


def on_bin(index):
    """A frequency that lands exactly on a Welch bin centre."""
    return index * FS / NPERSEG


#: Two clean peaks, so a selection and its harmonics have something to sit on.
F1 = on_bin(40)   # 0.625 1/m
F2 = on_bin(100)  # 1.5625 1/m


def spectrum_controller(**attributes):
    measurement = md_measurement(
        {"BW": sine(100000, F1, 3.0, 100.0) + sine(100000, F2, 1.0)})
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


def drawn_frequencies(controller):
    return sorted(line.get_xdata()[0] for line in controller.current_vlines)


def test_defaults_come_from_settings(qt_app):
    controller = spectrum_controller()

    assert controller.multiple_select == settings.MULTIPLE_SELECT_MODE
    assert controller.show_harmonics == settings.SPECTRUM_SHOW_HARMONICS_DEFAULT
    assert controller.harmonics_count == settings.MAX_HARMONICS_DISPLAY


def test_single_selection_draws_only_the_latest_frequency(qt_app):
    controller = spectrum_controller(multiple_select=False, show_harmonics=False,
                                     selected_freqs=[F1, F2])

    assert drawn_frequencies(controller) == pytest.approx([F2])


def test_multiple_selection_draws_every_frequency(qt_app):
    controller = spectrum_controller(multiple_select=True, show_harmonics=False,
                                     selected_freqs=[F1, F2])

    assert drawn_frequencies(controller) == pytest.approx([F1, F2])


@pytest.mark.parametrize("multiple_select", [False, True])
def test_harmonics_are_drawn_the_same_way_in_both_modes(qt_app, multiple_select):
    controller = spectrum_controller(multiple_select=multiple_select,
                                     show_harmonics=True, harmonics_count=3,
                                     selected_freqs=[F1])

    assert drawn_frequencies(controller) == pytest.approx([F1, 2 * F1, 3 * F1])
    # The fundamental stands out; no harmonic fades out entirely.
    alphas = [line.get_alpha() for line in controller.current_vlines]
    assert alphas[0] == 1.0
    assert all(0.25 <= alpha <= 1.0 for alpha in alphas)


def test_harmonics_can_be_switched_off(qt_app):
    controller = spectrum_controller(show_harmonics=False, harmonics_count=10,
                                     selected_freqs=[F1])

    assert drawn_frequencies(controller) == pytest.approx([F1])


def test_harmonic_count_applies_to_paper_machine_elements(qt_app):
    element = {"name": "Press roll", "spatial_frequency": F2}
    controller = spectrum_controller(show_harmonics=True, harmonics_count=2,
                                     selected_elements=[element])

    assert drawn_frequencies(controller) == pytest.approx([F2, 2 * F2])
    labels = [line.get_label() for line in controller.current_vlines]
    assert labels[0].startswith("Press roll: ")
    assert "Hz" not in labels[0]  # the machine speed is not known


def test_refined_selection_survives_the_redraw(qt_app):
    """A refinement lands between bins; the plot must not snap it back."""
    between_bins = F1 + 0.3 * FS / NPERSEG
    controller = spectrum_controller(selected_freqs=[between_bins])

    controller.plot()

    assert controller.selected_freqs == [between_bins]


def test_selecting_replaces_or_adds_by_mode(qt_app):
    controller = spectrum_controller(multiple_select=False, show_harmonics=False)
    window = spectrum.AnalysisWindow(controller, "MD")

    assert window.select_frequency_at(controller.ax, F1)
    assert window.select_frequency_at(controller.ax, F2)
    assert controller.selected_freqs == pytest.approx([F2])

    window.multipleSelectCheckbox.setChecked(True)
    assert controller.multiple_select
    assert window.select_frequency_at(controller.ax, F1)
    assert controller.selected_freqs == pytest.approx([F2, F1])
    assert drawn_frequencies(controller) == pytest.approx([F1, F2])


def test_selecting_takes_over_from_peak_detection(qt_app):
    controller = spectrum_controller(auto_detect_peaks=True)
    window = spectrum.AnalysisWindow(controller, "MD")
    assert controller.selected_freqs  # detection picked something

    assert window.select_frequency_at(controller.ax, F2)

    assert not controller.auto_detect_peaks
    assert not window.autodetectCheckbox.isChecked()
    assert controller.selected_freqs == pytest.approx([F2])

    window.clearFrequency()
    assert controller.selected_freqs == []
    assert window.selectedFrequencyLabel.text() == "Selected frequency: None"


def test_harmonics_controls_drive_the_controller(qt_app):
    controller = spectrum_controller(show_harmonics=True, harmonics_count=10,
                                     selected_freqs=[F1])
    window = spectrum.AnalysisWindow(controller, "MD")

    window.harmonicsCountSpinner.setValue(2)
    assert controller.harmonics_count == 2
    assert drawn_frequencies(controller) == pytest.approx([F1, 2 * F1])

    window.harmonicsCheckbox.setChecked(False)
    assert not controller.show_harmonics
    assert not window.harmonicsCountSpinner.isEnabled()
    assert drawn_frequencies(controller) == pytest.approx([F1])


def test_selection_settings_are_saved_with_the_analysis(qt_app):
    controller = spectrum_controller(multiple_select=True, show_harmonics=False,
                                     harmonics_count=4)

    attributes = controller.export_attributes()

    assert attributes["multiple_select"] is True
    assert attributes["show_harmonics"] is False
    assert attributes["harmonics_count"] == 4
