"""The faint information line at the top right of the analysis plots.

A spectrum depends on settings the plot itself cannot show: the step the record
was measured at, which part of the record was analysed and the length of the
segments the spectrum is averaged over. The plots carry them on one line.
"""

import numpy as np
import pandas as pd
import pytest

import settings
from analyses import cepstrum, coherence, spectrogram, spectrum, time_domain
from utils.measurement import Measurement
from utils.plot_formatting import (analysed_range_text, distance_text,
                                   sample_step_text, segment_text)

SAMPLE_STEP = 0.0128
SAMPLE_COUNT = 20000


def measurement():
    distances = np.arange(SAMPLE_COUNT) * SAMPLE_STEP
    rng = np.random.default_rng(0)
    wave = np.sin(2 * np.pi * distances / 1.5)
    return Measurement(
        channel_df=pd.DataFrame({
            "BW": 100.0 + wave + rng.normal(0.0, 0.5, SAMPLE_COUNT),
            "Ash": 20.0 + wave + rng.normal(0.0, 0.5, SAMPLE_COUNT),
        }),
        channels=["BW", "Ash"],
        units={"BW": "g/m2", "Ash": "%"},
        distances=distances,
        cd_distances=distances,
        sample_step=SAMPLE_STEP,
    )


def plotted(module, **attributes):
    controller = module.AnalysisController(measurement(), "MD")
    controller.analysis_range_low = 10.0
    controller.analysis_range_high = 200.0
    controller.auto_detect_peaks = False
    controller.machine_speed = 0.0
    for key, value in attributes.items():
        setattr(controller, key, value)
    controller.plot()
    return controller


def test_a_distance_keeps_the_decimals_its_size_is_worth():
    assert distance_text(1264.3) == "1264"
    assert distance_text(99.14) == "99.1"
    assert distance_text(0.8) == "0.8"
    assert distance_text(0.0) == "0"


def test_the_sample_step_is_in_millimetres():
    assert sample_step_text(0.0128) == "12.8 mm step"
    assert sample_step_text(0.0008) == "0.8 mm step"


def test_the_measured_length_is_named_only_for_a_part_of_the_record():
    assert analysed_range_text(600.0, 1264.0, 1315.2) == "600 - 1264 m of 1315 m measured"
    assert analysed_range_text(0.0, 1315.2, 1315.2) == "0 - 1315 m"


def test_the_segment_length_is_in_metres():
    assert segment_text(20000, 0.0128) == "Welch 256 m segments"
    assert segment_text(5000, 0.0128, overlap=0.75, method="") == "64 m segments, 75% overlap"


@pytest.mark.parametrize("module, attributes, ending", [
    (spectrum, {"nperseg": 2000}, " · Welch 25.6 m segments"),
    (cepstrum, {"nperseg": 2000}, " · Welch 25.6 m segments"),
    (spectrogram, {"nperseg": 2000, "overlap": 0.75}, " · 25.6 m segments, 75% overlap"),
    # Coherence shortens the segments until enough of them fit in the range.
    (coherence, {"nperseg": 1000, "channel": "BW", "channel2": "Ash"}, " m segments"),
    (time_domain, {"band_pass_low": 0.0, "band_pass_high": 10.0}, " m measured"),
])
def test_a_plot_carries_the_conditions_it_was_made_under(qt_app, module, attributes, ending):
    controller = plotted(module, **attributes)

    info = controller.figure.get_suptitle()
    assert info.startswith("12.8 mm step · 10 - 200 m of 256 m measured")
    assert info.endswith(ending)


def test_the_line_can_be_switched_off(qt_app, monkeypatch):
    monkeypatch.setattr(settings, "PLOT_INFO_SHOW", False)

    controller = plotted(spectrum, nperseg=2000)

    assert controller.figure.get_suptitle() == ""
