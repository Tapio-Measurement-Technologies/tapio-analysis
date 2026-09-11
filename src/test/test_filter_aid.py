"""The filter aid, the band pass filter's decimals and the window length in metres."""

import numpy as np
import pandas as pd
import pytest

from analyses import spectrum, time_domain
from gui.filter_aid import FilterAidDialog, band_from_limits
from utils.measurement import Measurement

SAMPLE_STEP = 0.0128


def measurement():
    distances = np.arange(20000) * SAMPLE_STEP
    return Measurement(
        channel_df=pd.DataFrame({"BW": 100.0 + np.sin(2 * np.pi * distances / 1.5)}),
        channels=["BW"],
        units={"BW": "g/m2"},
        distances=distances,
        cd_distances=distances,
        sample_step=SAMPLE_STEP,
    )


def test_wavelength_limits_turn_into_the_opposite_cuts():
    assert band_from_limits("10", "0.5", "Wavelength [m]", maximum=39.0) == pytest.approx((0.1, 2.0))


def test_a_blank_limit_leaves_its_end_of_the_band_open():
    assert band_from_limits("", "10", "Wavelength [cm]", maximum=39.0) == pytest.approx((0.0, 10.0))
    assert band_from_limits("10", "", "Wavelength [m]", maximum=39.0) == pytest.approx((0.1, 39.0))


def test_hz_is_converted_at_the_machine_speed_and_needs_one():
    assert band_from_limits("1", "10", "Frequency [Hz]", maximum=39.0,
                            machine_speed=600.0) == pytest.approx((0.1, 1.0))
    with pytest.raises(ValueError):
        band_from_limits("1", "10", "Frequency [Hz]", maximum=39.0, machine_speed=0.0)


def test_limits_in_the_wrong_order_or_past_the_filter_are_put_right():
    assert band_from_limits("20", "0.5", "Frequency [1/m]", maximum=10.0) == pytest.approx((0.5, 10.0))


@pytest.mark.parametrize("first, second", [("5", "5"), ("-1", ""), ("a", "")])
def test_a_limit_that_makes_no_band_is_refused(first, second):
    with pytest.raises(ValueError):
        band_from_limits(first, second, "Frequency [1/m]", maximum=10.0)


def test_the_dialog_shows_the_current_band_and_returns_the_typed_one(qt_app):
    dialog = FilterAidDialog(None, band=(0.1, 10.0), maximum=39.0, unit="Wavelength [m]")

    assert (dialog.firstEdit.text(), dialog.secondEdit.text()) == ("10", "0.1")
    dialog.firstEdit.setText("20")
    dialog.updateResult()
    assert dialog.band == pytest.approx((0.05, 10.0))


def test_the_band_pass_filter_has_three_decimals_and_a_filter_aid(qt_app):
    window = time_domain.AnalysisWindow(
        time_domain.AnalysisController(measurement(), "MD"), "MD")

    assert window.bandPassFilterSlider.decimals() == 3
    assert window.filterAidButton.toolTip()


def test_the_window_length_is_shown_in_metres_as_the_slider_moves(qt_app):
    window = spectrum.AnalysisWindow(spectrum.AnalysisController(measurement(), "MD"), "MD")

    window.spectrumLengthSlider.setValue(5000)

    assert window.spectrumLengthLabel.text() == "Window length: 64 m"
